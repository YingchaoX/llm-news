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
from .base import BaseCollector

logger = logging.getLogger(__name__)

# ── Known institutions whitelist / 知名机构白名单 ──────────────────────────
DEFAULT_KNOWN_INSTITUTIONS: list[str] = [
    # --- Companies / 公司 ---
    "openai", "anthropic", "google deepmind", "google research", "google brain",
    "meta ai", "meta platforms", "meta research", "facebook ai research",
    "microsoft", "microsoft research", "nvidia", "nvidia research",
    "apple intelligence", "amazon science", "amazon web services",
    "hugging face", "huggingface", "deepseek", "alibaba", "alibaba group",
    "damo academy", "baidu research", "baidu inc", "tencent", "bytedance",
    "zhipu", "moonshot ai", "mistral ai", "mistral", "cohere", "ai21 labs",
    "databricks", "mosaic ml", "together ai", "x.ai", "samsung research",
    "intel labs", "ibm research", "salesforce research", "adobe research",
    # --- Universities / 大学 ---
    "stanford", "stanford university", "massachusetts institute of technology",
    "carnegie mellon", "carnegie mellon university", "uc berkeley",
    "university of california, berkeley", "berkeley", "harvard",
    "harvard university", "princeton", "princeton university", "caltech",
    "yale university", "columbia university", "cornell university", "cornell",
    "university of washington", "new york university", "university of oxford",
    "oxford university", "university of cambridge", "cambridge university",
    "eth zurich", "eth zürich", "epfl", "imperial college",
    "university college london", "university of toronto", "mila",
    "tsinghua", "tsinghua university", "peking university",
    "zhejiang university", "fudan university", "fudan",
    "shanghai jiao tong", "nanjing university", "ustc",
    "chinese academy of sciences", "kaist", "seoul national university",
    "university of tokyo", "technion", "tel aviv university",
    "hebrew university", "national university of singapore",
    "nanyang technological university", "university of michigan",
    "university of illinois", "georgia tech", "georgia institute of technology",
    "uc san diego", "ucsd", "university of maryland",
    "university of pennsylvania", "upenn",
    # --- Research labs / 研究机构 ---
    "allen institute", "allen institute for ai", "ai2",
    "eleutherai", "eleuther ai", "laion", "inria",
    "max planck", "max planck institute",
]


def _build_affiliation_pattern(institutions: list[str]) -> re.Pattern[str]:
    """Build a compiled regex pattern for matching institutions.

    构建机构名称正则（word-boundary 匹配，避免子串误判）。
    """
    sorted_inst = sorted(institutions, key=len, reverse=True)
    escaped = [re.escape(name) for name in sorted_inst]
    pattern = "|".join(rf"\b{e}\b" for e in escaped)
    return re.compile(pattern, re.IGNORECASE)


def _matches_institution(
    result: arxiv.Result,
    pattern: re.Pattern[str],
) -> bool:
    """Check if paper is from a known institution.

    判断论文是否来自知名机构：扫描作者名、摘要和 comment 字段。
    """
    parts: list[str] = []
    parts.append(" ".join(a.name for a in result.authors))
    parts.append(result.summary or "")
    if result.comment:
        parts.append(result.comment)
    if result.journal_ref:
        parts.append(result.journal_ref)
    text_to_scan = " ".join(parts)
    return bool(pattern.search(text_to_scan))


class ArxivCollector(BaseCollector):
    """arXiv paper collector.

    arXiv 论文采集器，按分类和关键词搜索，可选机构过滤。
    """

    name = "arxiv"

    def __init__(
        self,
        categories: list[str] | None = None,
        max_results: int = 50,
        require_institution: bool = True,
        known_institutions: list[str] | None = None,
    ) -> None:
        self.categories = categories or ["cs.CL", "cs.AI", "cs.LG"]
        self.max_results = max_results
        self.require_institution = require_institution
        self.known_institutions = known_institutions or DEFAULT_KNOWN_INSTITUTIONS

    def collect(self, keywords: list[str]) -> list[NewsItem]:
        items: list[NewsItem] = []
        inst_pattern = _build_affiliation_pattern(self.known_institutions)

        cat_query = " OR ".join(f"cat:{cat}" for cat in self.categories)
        kw_query = " OR ".join(f'"{kw}"' for kw in keywords[:15])
        query = f"({cat_query}) AND ({kw_query})"

        logger.info("arXiv query: %s (max_results=%d)", query[:120], self.max_results)

        client = arxiv.Client(page_size=self.max_results, delay_seconds=3.0)
        search = arxiv.Search(
            query=query,
            max_results=self.max_results,
            sort_by=arxiv.SortCriterion.SubmittedDate,
            sort_order=arxiv.SortOrder.Descending,
        )

        total_fetched = 0
        skipped_institution = 0

        try:
            for result in client.results(search):
                total_fetched += 1
                if self.require_institution and not _matches_institution(result, inst_pattern):
                    skipped_institution += 1
                    continue

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
            total_fetched, skipped_institution, len(items),
        )
        return items
