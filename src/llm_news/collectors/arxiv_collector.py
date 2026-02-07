"""arXiv paper collector.

Fetches recent papers from cs.CL, cs.AI, cs.LG and filters by LLM keywords.
arXiv API 免费无限制（建议 3s 间隔）。
"""

import logging
import time
from datetime import datetime, timezone

import arxiv

from ..models import NewsItem

logger = logging.getLogger(__name__)


def collect(
    categories: list[str],
    max_results: int,
    keywords: list[str],
) -> list[NewsItem]:
    """Collect recent LLM-related papers from arXiv.

    Args:
        categories: arXiv categories to search (e.g. cs.CL, cs.AI).
        max_results: Maximum number of results per category.
        keywords: Keywords to filter papers by relevance.

    Returns:
        List of NewsItem from arXiv.
    """
    items: list[NewsItem] = []

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

    try:
        for result in client.results(search):
            item = NewsItem(
                title=result.title.strip().replace("\n", " "),
                url=result.entry_id,
                source="arxiv",
                source_name=", ".join(
                    c.split(".")[-1] for c in (result.categories or [])
                ),
                content=result.summary.strip().replace("\n", " "),
                published_at=result.published.replace(tzinfo=timezone.utc)
                if result.published
                else None,
            )
            items.append(item)
    except Exception:
        logger.exception("Failed to fetch arXiv papers")

    logger.info("arXiv: collected %d papers", len(items))
    return items
