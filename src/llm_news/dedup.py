"""Deduplication logic — multi-layer strategy.

多层去重策略：
1. URL 标准化（去尾斜杠、统一协议、去 www、去追踪参数）
2. 跨源规范 ID 提取（arxiv / HF Papers 论文 ID 统一）
3. 标准化 URL 去重
4. 标题精确匹配（标准化后，兜底层）
5. 来源优先级选择（重复时保留原始数据源头）
"""

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from .models import NewsItem

logger = logging.getLogger(__name__)

HISTORY_PATH = Path("data/history.json")

# ── Source priority / 数据源优先级 ────────────────────────────────────────
# Lower number = closer to original source = preferred when duplicates found
# 数值越小 = 越接近原始来源 = 重复时优先保留
SOURCE_PRIORITY: dict[str, int] = {
    "arxiv": 1,       # 论文原始仓库 / original paper repository
    "blog": 1,        # 官方博客 / official blog (primary source)
    "github": 1,      # 仓库 release / repo releases (primary source)
    "hf_models": 1,   # 模型发布 / model releases (primary source)
    "hf_papers": 2,   # 论文聚合 / paper aggregator
    "github_trending": 2,  # GitHub 趋势聚合 / trending aggregator
    "pwc": 2,         # 论文聚合 / paper aggregator
    "hackernews": 3,  # 社区讨论 / community aggregator
    "reddit": 3,      # 社区讨论 / community aggregator
}

# ── URL Normalization / URL 标准化 ────────────────────────────────────────

# Tracking/analytics query params to strip
# 需要去除的追踪/分析参数
_TRACKING_PARAMS = frozenset({
    "utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term",
    "ref", "source", "fbclid", "gclid", "mc_cid", "mc_eid",
})


def normalize_url(url: str) -> str:
    """Normalize URL for comparison.

    标准化 URL：统一协议、去 www、去尾斜杠、去追踪参数、去 fragment。
    """
    url = url.strip()
    if not url:
        return url

    parsed = urlparse(url)

    # Normalize scheme to https / 统一 https
    scheme = "https"

    # Normalize host: lowercase + remove www / 去 www
    host = (parsed.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]

    # Keep non-standard port / 保留非标端口
    port = parsed.port
    netloc = host
    if port and port not in (80, 443):
        netloc = f"{host}:{port}"

    # Remove trailing slash / 去尾斜杠
    path = parsed.path.rstrip("/")

    # Strip tracking query params / 去追踪参数
    if parsed.query:
        params = parse_qs(parsed.query, keep_blank_values=True)
        filtered = {
            k: v for k, v in params.items()
            if k.lower() not in _TRACKING_PARAMS
        }
        query = urlencode(filtered, doseq=True) if filtered else ""
    else:
        query = ""

    # Drop fragment / 去 fragment
    return urlunparse((scheme, netloc, path, "", query, ""))


# ── Canonical Key Extraction / 规范 ID 提取 ──────────────────────────────
# Extract a cross-source canonical key for the same underlying content.
# 提取跨源规范 key，使不同来源的同一内容映射到同一标识。

# Regex patterns to extract arxiv paper ID from various URL formats
# 从不同 URL 格式提取 arxiv 论文 ID
_ARXIV_ID_PATTERNS: list[re.Pattern[str]] = [
    # http://arxiv.org/abs/2602.06570v1 → 2602.06570
    re.compile(r"arxiv\.org/abs/(\d{4}\.\d{4,5})"),
    # http://arxiv.org/pdf/2602.06570v1.pdf → 2602.06570
    re.compile(r"arxiv\.org/pdf/(\d{4}\.\d{4,5})"),
    # https://huggingface.co/papers/2602.06570 → 2602.06570
    re.compile(r"huggingface\.co/papers/(\d{4}\.\d{4,5})"),
]


def extract_canonical_key(item: NewsItem) -> str | None:
    """Extract a cross-source canonical key for known URL patterns.

    为已知 URL 模式提取跨源规范 key（如论文 arxiv ID）。
    Returns None if no canonical key can be extracted.
    """
    url = item.url

    # Check arxiv-related patterns / 检查 arxiv 相关 URL
    for pattern in _ARXIV_ID_PATTERNS:
        match = pattern.search(url)
        if match:
            return f"arxiv:{match.group(1)}"

    return None


# ── Title Normalization / 标题标准化 ──────────────────────────────────────

# Minimum normalized title length for title-based dedup (avoid short/generic titles)
# 标题最短长度，避免太短的通用标题误匹配
_MIN_TITLE_LENGTH = 15


def normalize_title(title: str) -> str:
    """Normalize title for fuzzy matching.

    标题标准化：小写、去标点、合并空格。
    """
    title = title.lower().strip()
    # Remove punctuation, keep alphanumeric and spaces / 去标点，保留字母数字和空格
    title = re.sub(r"[^\w\s]", " ", title)
    # Collapse whitespace / 合并空格
    title = re.sub(r"\s+", " ", title).strip()
    return title


# ── History Persistence / 历史记录持久化 ──────────────────────────────────


def load_history() -> dict[str, set[str]]:
    """Load previously seen identifiers from history file.

    加载历史记录，包含 urls 和 canonical_keys 两个集合。
    Returns dict with 'urls' and 'canonical_keys' sets.
    """
    empty: dict[str, set[str]] = {"urls": set(), "canonical_keys": set()}
    if not HISTORY_PATH.exists():
        return empty
    try:
        data = json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
        urls = set(data.get("urls", []))
        canonical_keys = set(data.get("canonical_keys", []))
        logger.info(
            "Loaded history: %d URLs, %d canonical keys",
            len(urls), len(canonical_keys),
        )
        return {"urls": urls, "canonical_keys": canonical_keys}
    except Exception:
        logger.exception("Failed to load history, starting fresh")
        return empty


def save_history(history: dict[str, set[str]]) -> None:
    """Save seen identifiers to history file.

    保存历史记录（URLs + canonical keys），最多 10,000 条 URL。
    """
    HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)

    url_list = sorted(history.get("urls", set()))
    if len(url_list) > 10_000:
        url_list = url_list[-10_000:]

    canon_list = sorted(history.get("canonical_keys", set()))
    if len(canon_list) > 5_000:
        canon_list = canon_list[-5_000:]

    data = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "count": len(url_list),
        "urls": url_list,
        "canonical_keys": canon_list,
    }
    HISTORY_PATH.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    logger.info(
        "Saved history: %d URLs, %d canonical keys",
        len(url_list), len(canon_list),
    )


# ── Core Dedup Logic / 核心去重逻辑 ──────────────────────────────────────


def _pick_preferred(existing: NewsItem, new: NewsItem) -> NewsItem:
    """Pick the preferred item when duplicates are found.

    从重复条目中选择更优先的：优先保留原始来源（数据源头）。
    同优先级时保留已有条目。
    """
    existing_pri = SOURCE_PRIORITY.get(existing.source, 5)
    new_pri = SOURCE_PRIORITY.get(new.source, 5)

    if new_pri < existing_pri:
        return new
    return existing


def deduplicate(items: list[NewsItem], history: dict[str, set[str]]) -> list[NewsItem]:
    """Remove duplicate items using multi-layer strategy.

    多层去重策略（按优先级依次检查）：
    Layer 0: 历史 URL / canonical key 过滤（跨天去重）
    Layer 1: 规范 ID 去重（arxiv 论文 ID 等跨源匹配）
    Layer 2: 标准化 URL 去重（去尾斜杠、统一协议等）
    Layer 3: 标题精确匹配去重（标准化后，兜底层）

    重复时按 SOURCE_PRIORITY 保留最接近原始来源的条目。

    Args:
        items: Collected news items from all sources.
        history: Dict with 'urls' and 'canonical_keys' sets.

    Returns:
        Deduplicated list of items.
    """
    history_urls = history.get("urls", set())
    history_canon = history.get("canonical_keys", set())

    # Pre-compute normalized history URLs for broader matching
    # 预计算标准化历史 URL，用于更宽泛的匹配
    normalized_history_urls: set[str] = {normalize_url(u) for u in history_urls}

    # Index structures: key → index in result list
    # 索引结构：key → result 列表中的索引
    canonical_index: dict[str, int] = {}   # canonical_key → idx
    norm_url_index: dict[str, int] = {}    # normalized_url → idx
    title_index: dict[str, int] = {}       # normalized_title → idx

    result: list[NewsItem] = []

    stats = {"history": 0, "canonical": 0, "url": 0, "title": 0}

    for item in items:
        norm_url = normalize_url(item.url)
        canon_key = extract_canonical_key(item)
        norm_title = normalize_title(item.title)

        # ── Layer 0: History filter / 历史过滤 ──
        if item.url in history_urls or norm_url in normalized_history_urls:
            stats["history"] += 1
            continue
        if canon_key and canon_key in history_canon:
            stats["history"] += 1
            continue

        # ── Layer 1: Canonical key dedup / 规范 ID 去重 ──
        # e.g., arxiv:2602.06570 matches across arxiv and hf_papers
        if canon_key and canon_key in canonical_index:
            idx = canonical_index[canon_key]
            existing = result[idx]
            preferred = _pick_preferred(existing, item)
            if preferred is not existing:
                result[idx] = preferred
                # Update indexes for the replaced item
                # 更新被替换条目的索引
                norm_url_index[norm_url] = idx
                if norm_title and len(norm_title) >= _MIN_TITLE_LENGTH:
                    title_index[norm_title] = idx
            logger.debug(
                "Canonical dedup: '%s' (%s) ≈ '%s' (%s) → kept %s",
                item.title[:50], item.source,
                existing.title[:50], existing.source,
                (preferred.source),
            )
            stats["canonical"] += 1
            continue

        # ── Layer 2: Normalized URL dedup / 标准化 URL 去重 ──
        # e.g., trailing slash difference
        if norm_url in norm_url_index:
            idx = norm_url_index[norm_url]
            existing = result[idx]
            preferred = _pick_preferred(existing, item)
            if preferred is not existing:
                result[idx] = preferred
                if canon_key:
                    canonical_index[canon_key] = idx
                if norm_title and len(norm_title) >= _MIN_TITLE_LENGTH:
                    title_index[norm_title] = idx
            logger.debug(
                "URL dedup: '%s' (%s) ≈ '%s' (%s) → kept %s",
                item.title[:50], item.source,
                existing.title[:50], existing.source,
                (preferred.source),
            )
            stats["url"] += 1
            continue

        # ── Layer 3: Title dedup / 标题去重 ──
        # Safety net for same content with completely different URLs
        if (
            norm_title
            and len(norm_title) >= _MIN_TITLE_LENGTH
            and norm_title in title_index
        ):
            idx = title_index[norm_title]
            existing = result[idx]
            preferred = _pick_preferred(existing, item)
            if preferred is not existing:
                result[idx] = preferred
                norm_url_index[norm_url] = idx
                if canon_key:
                    canonical_index[canon_key] = idx
            logger.debug(
                "Title dedup: '%s' (%s) ≈ '%s' (%s) → kept %s",
                item.title[:50], item.source,
                existing.title[:50], existing.source,
                (preferred.source),
            )
            stats["title"] += 1
            continue

        # ── No duplicate found — register this item / 无重复，注册新条目 ──
        idx = len(result)
        result.append(item)

        if canon_key:
            canonical_index[canon_key] = idx
        norm_url_index[norm_url] = idx
        if norm_title and len(norm_title) >= _MIN_TITLE_LENGTH:
            title_index[norm_title] = idx

    removed_total = stats["history"] + stats["canonical"] + stats["url"] + stats["title"]
    logger.info(
        "Dedup: %d → %d items (-%d: %d history, %d canonical, %d url, %d title)",
        len(items),
        len(result),
        removed_total,
        stats["history"],
        stats["canonical"],
        stats["url"],
        stats["title"],
    )
    return result
