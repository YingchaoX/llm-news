"""Hugging Face Daily Papers collector.

Fetches trending/curated papers from the HF Daily Papers page via API.
HF Daily Papers 社区精选论文，免费 API，无需 API Key。

API endpoint: https://huggingface.co/api/daily_papers
Returns papers curated & upvoted by the HF community — high signal-to-noise.
"""

import logging
from datetime import datetime, timezone

import httpx

from ..models import NewsItem

logger = logging.getLogger(__name__)

HF_DAILY_PAPERS_API = "https://huggingface.co/api/daily_papers"


def _matches_keywords(text: str, keywords: list[str]) -> bool:
    """Check if text contains any of the keywords (case-insensitive)."""
    text_lower = text.lower()
    return any(kw.lower() in text_lower for kw in keywords)


def collect(
    limit: int = 30,
    keywords: list[str] | None = None,
) -> list[NewsItem]:
    """Collect trending papers from Hugging Face Daily Papers.

    Args:
        limit: Maximum number of papers to fetch.
        keywords: Keywords to filter papers (optional; HF papers are already
            curated so filtering is light).
            关键词过滤（可选，HF 论文已经过社区筛选，过滤较宽松）。

    Returns:
        List of NewsItem from Hugging Face Daily Papers.
    """
    items: list[NewsItem] = []

    try:
        with httpx.Client(timeout=30, follow_redirects=True) as client:
            resp = client.get(HF_DAILY_PAPERS_API, params={"limit": limit})
            resp.raise_for_status()
            papers = resp.json()

        for paper in papers:
            # API returns: { paper: { id, title, summary, ... }, publishedAt, ... }
            paper_data = paper.get("paper", {})
            title = paper_data.get("title", "").strip().replace("\n", " ")
            summary = paper_data.get("summary", "").strip().replace("\n", " ")
            arxiv_id = paper_data.get("id", "")
            published_str = paper.get("publishedAt", "")

            if not title:
                continue

            # Keyword filter (lenient for HF curated papers)
            if keywords:
                text_for_match = f"{title} {summary}"
                if not _matches_keywords(text_for_match, keywords):
                    continue

            # Build arXiv URL from paper ID
            url = f"https://huggingface.co/papers/{arxiv_id}" if arxiv_id else ""

            published_at = None
            if published_str:
                try:
                    published_at = datetime.fromisoformat(
                        published_str.replace("Z", "+00:00")
                    )
                except ValueError:
                    pass

            # Use upvotes as initial score / 使用社区投票数作为初始分数
            upvotes = paper.get("paper", {}).get("upvotes", 0)

            item = NewsItem(
                title=title,
                url=url,
                source="hf_papers",
                source_name="HF Daily Papers",
                content=summary[:800],
                score=float(upvotes),
                published_at=published_at,
            )
            items.append(item)

    except Exception:
        logger.exception("Failed to fetch Hugging Face Daily Papers")

    logger.info("HF Papers: collected %d papers", len(items))
    return items
