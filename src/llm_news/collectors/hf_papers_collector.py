"""Hugging Face Daily Papers collector.

Fetches trending/curated papers from the HF Daily Papers page via API.
HF Daily Papers 社区精选论文，免费 API，无需 API Key。

API endpoint: https://huggingface.co/api/daily_papers
"""

import logging
from datetime import datetime, timezone

import httpx

from ..models import NewsItem
from .base import BaseCollector

logger = logging.getLogger(__name__)

HF_DAILY_PAPERS_API = "https://huggingface.co/api/daily_papers"


def _matches_keywords(text: str, keywords: list[str]) -> bool:
    text_lower = text.lower()
    return any(kw.lower() in text_lower for kw in keywords)


class HfPapersCollector(BaseCollector):
    """Hugging Face Daily Papers collector.

    HuggingFace 社区精选论文采集器，高信噪比。
    """

    name = "hf_papers"

    def __init__(self, limit: int = 30) -> None:
        self.limit = limit

    def collect(self, keywords: list[str]) -> list[NewsItem]:
        items: list[NewsItem] = []

        try:
            with httpx.Client(timeout=30, follow_redirects=True) as client:
                resp = client.get(HF_DAILY_PAPERS_API, params={"limit": self.limit})
                resp.raise_for_status()
                papers = resp.json()

            for paper in papers:
                paper_data = paper.get("paper", {})
                title = paper_data.get("title", "").strip().replace("\n", " ")
                summary = paper_data.get("summary", "").strip().replace("\n", " ")
                arxiv_id = paper_data.get("id", "")
                published_str = paper.get("publishedAt", "")

                if not title:
                    continue

                if keywords:
                    text_for_match = f"{title} {summary}"
                    if not _matches_keywords(text_for_match, keywords):
                        continue

                url = f"https://huggingface.co/papers/{arxiv_id}" if arxiv_id else ""

                published_at = None
                if published_str:
                    try:
                        published_at = datetime.fromisoformat(
                            published_str.replace("Z", "+00:00")
                        )
                    except ValueError:
                        pass

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
