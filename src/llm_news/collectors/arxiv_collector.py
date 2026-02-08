"""arXiv paper collector.

Fetches recent papers from cs.CL, cs.AI, cs.LG and filters by LLM keywords.
Only keeps papers affiliated with well-known institutions (configurable).
arXiv API 免费无限制（建议 3s 间隔）。
仅保留知名大学/公司的论文（可配置机构白名单）。
"""

import logging
import re
from datetime import datetime, timezone

import arxiv

from ..models import NewsItem

logger = logging.getLogger(__name__)

# ── Known institutions whitelist / 知名机构白名单 ──────────────────────────
# Matches against author affiliations AND the paper abstract/title for org mentions.
# Keep lowercase for case-insensitive matching.
DEFAULT_KNOWN_INSTITUTIONS: list[str] = [
    # --- Companies / 公司 ---
    "openai",
    "anthropic",
    "google deepmind",
    "google research",
    "google brain",
    "meta ai",
    "meta platforms",
    "meta research",
    "facebook ai research",
    "microsoft",
    "microsoft research",
    "nvidia",
    "nvidia research",
    "apple intelligence",
    "amazon science",
    "amazon web services",
    "hugging face",
    "huggingface",
    "deepseek",
    "alibaba",
    "alibaba group",
    "damo academy",
    "baidu research",
    "baidu inc",
    "tencent",
    "bytedance",
    "zhipu",
    "moonshot ai",
    "mistral ai",
    "mistral",
    "cohere",
    "ai21 labs",
    "databricks",
    "mosaic ml",
    "together ai",
    "x.ai",
    "samsung research",
    "intel labs",
    "ibm research",
    "salesforce research",
    "adobe research",
    # --- Universities / 大学 ---
    "stanford",
    "stanford university",
    "massachusetts institute of technology",
    "carnegie mellon",
    "carnegie mellon university",
    "uc berkeley",
    "university of california, berkeley",
    "berkeley",
    "harvard",
    "harvard university",
    "princeton",
    "princeton university",
    "caltech",
    "yale university",
    "columbia university",
    "cornell university",
    "cornell",
    "university of washington",
    "new york university",
    "university of oxford",
    "oxford university",
    "university of cambridge",
    "cambridge university",
    "eth zurich",
    "eth zürich",
    "epfl",
    "imperial college",
    "university college london",
    "university of toronto",
    "mila",
    "tsinghua",
    "tsinghua university",
    "peking university",
    "zhejiang university",
    "fudan university",
    "fudan",
    "shanghai jiao tong",
    "nanjing university",
    "ustc",
    "chinese academy of sciences",
    "kaist",
    "seoul national university",
    "university of tokyo",
    "technion",
    "tel aviv university",
    "hebrew university",
    "national university of singapore",
    "nanyang technological university",
    "university of michigan",
    "university of illinois",
    "georgia tech",
    "georgia institute of technology",
    "uc san diego",
    "ucsd",
    "university of maryland",
    "university of pennsylvania",
    "upenn",
    # --- Research labs / 研究机构 ---
    "allen institute",
    "allen institute for ai",
    "ai2",
    "eleutherai",
    "eleuther ai",
    "laion",
    "inria",
    "max planck",
    "max planck institute",
]


def _build_affiliation_pattern(institutions: list[str]) -> re.Pattern[str]:
    """Build a compiled regex pattern for matching institutions.

    构建机构名称正则（word-boundary 匹配，避免子串误判）。
    """
    # Sort longest first so "google deepmind" matches before "google"
    sorted_inst = sorted(institutions, key=len, reverse=True)
    escaped = [re.escape(name) for name in sorted_inst]
    # Use word boundaries; some names like "MIT" need special handling
    pattern = "|".join(rf"\b{e}\b" for e in escaped)
    return re.compile(pattern, re.IGNORECASE)


def _matches_institution(
    result: arxiv.Result,
    pattern: re.Pattern[str],
) -> bool:
    """Check if paper is from a known institution.

    Since arXiv API metadata rarely includes author affiliations, we scan:
      1. Author names (some include org, e.g. "John Smith (Google DeepMind)")
      2. Paper abstract / summary
      3. Paper comment field (often has org or conference info)
    判断论文是否来自知名机构：扫描作者名、摘要和 comment 字段。
    注意：arXiv API 的 affiliation 字段通常为空，只能靠文本匹配。
    """
    # Gather all scannable text
    parts: list[str] = []

    # Author names
    parts.append(" ".join(a.name for a in result.authors))

    # Abstract
    parts.append(result.summary or "")

    # Comment field (often contains org/conference info)
    if result.comment:
        parts.append(result.comment)

    # Journal reference
    if result.journal_ref:
        parts.append(result.journal_ref)

    text_to_scan = " ".join(parts)
    return bool(pattern.search(text_to_scan))


def collect(
    categories: list[str],
    max_results: int,
    keywords: list[str],
    known_institutions: list[str] | None = None,
    require_institution: bool = True,
) -> list[NewsItem]:
    """Collect recent LLM-related papers from arXiv.

    Args:
        categories: arXiv categories to search (e.g. cs.CL, cs.AI).
        max_results: Maximum number of results per category.
        keywords: Keywords to filter papers by relevance.
        known_institutions: Institution whitelist; defaults to built-in list.
            机构白名单，为 None 时使用内置列表。
        require_institution: If True, only keep papers from known institutions.
            是否启用机构过滤。

    Returns:
        List of NewsItem from arXiv.
    """
    items: list[NewsItem] = []

    institutions = known_institutions or DEFAULT_KNOWN_INSTITUTIONS
    inst_pattern = _build_affiliation_pattern(institutions)

    # Build query: search across categories with keyword filter
    cat_query = " OR ".join(f"cat:{cat}" for cat in categories)
    kw_query = " OR ".join(f'"{kw}"' for kw in keywords[:15])  # limit query length
    query = f"({cat_query}) AND ({kw_query})"

    logger.info("arXiv query: %s (max_results=%d)", query[:120], max_results)

    client = arxiv.Client(
        page_size=max_results,
        delay_seconds=3.0,  # respect rate limit
    )
    search = arxiv.Search(
        query=query,
        max_results=max_results,
        sort_by=arxiv.SortCriterion.SubmittedDate,
        sort_order=arxiv.SortOrder.Descending,
    )

    total_fetched = 0
    skipped_institution = 0

    try:
        for result in client.results(search):
            total_fetched += 1

            # ── Institution filter / 机构过滤 ──
            if require_institution and not _matches_institution(result, inst_pattern):
                skipped_institution += 1
                continue

            # Build source_name with matched institution info
            authors_str = ", ".join(a.name for a in result.authors[:3])
            if len(result.authors) > 3:
                authors_str += " et al."

            item = NewsItem(
                title=result.title.strip().replace("\n", " "),
                url=result.entry_id,
                source="arxiv",
                source_name=", ".join(
                    c.split(".")[-1] for c in (result.categories or [])
                ),
                content=(
                    f"[Authors: {authors_str}] "
                    + result.summary.strip().replace("\n", " ")
                ),
                published_at=result.published.replace(tzinfo=timezone.utc)
                if result.published
                else None,
            )
            items.append(item)
    except Exception:
        logger.exception("Failed to fetch arXiv papers")

    logger.info(
        "arXiv: fetched %d, skipped %d (institution filter), kept %d papers",
        total_fetched,
        skipped_institution,
        len(items),
    )
    return items
