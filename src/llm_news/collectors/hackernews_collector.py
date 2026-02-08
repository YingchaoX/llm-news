"""Hacker News collector.

Fetches top/best stories from HN and filters for AI/LLM-related content.
HN Firebase API 免费，无需 API Key，无速率限制。

API docs: https://github.com/HackerNews/API
"""

import logging
from datetime import datetime, timezone

import httpx

from ..models import NewsItem

logger = logging.getLogger(__name__)

HN_API_BASE = "https://hacker-news.firebaseio.com/v0"


def _matches_keywords(text: str, keywords: list[str]) -> bool:
    """Check if text contains any of the keywords (case-insensitive)."""
    text_lower = text.lower()
    return any(kw.lower() in text_lower for kw in keywords)


def collect(
    story_type: str = "topstories",
    limit: int = 60,
    keywords: list[str] | None = None,
) -> list[NewsItem]:
    """Collect AI/LLM-related stories from Hacker News.

    Args:
        story_type: HN endpoint — "topstories", "beststories", or "newstories".
            HN 故事类型：热门 / 最佳 / 最新。
        limit: Max number of story IDs to fetch from the list.
        keywords: Keywords to filter stories by relevance.

    Returns:
        List of NewsItem from Hacker News.
    """
    items: list[NewsItem] = []

    try:
        with httpx.Client(timeout=30, follow_redirects=True) as client:
            # 1. Fetch story ID list
            resp = client.get(f"{HN_API_BASE}/{story_type}.json")
            resp.raise_for_status()
            story_ids: list[int] = resp.json()[:limit]

            logger.info(
                "HN: fetching details for %d/%d %s",
                len(story_ids),
                len(resp.json()),
                story_type,
            )

            # 2. Fetch each story's details
            for story_id in story_ids:
                try:
                    r = client.get(f"{HN_API_BASE}/item/{story_id}.json")
                    r.raise_for_status()
                    story = r.json()
                    if not story or story.get("type") != "story":
                        continue

                    title = story.get("title", "").strip()
                    url = story.get("url", "")
                    text = story.get("text", "") or ""
                    score = story.get("score", 0)

                    # Fallback URL to HN discussion page
                    hn_url = f"https://news.ycombinator.com/item?id={story_id}"
                    if not url:
                        url = hn_url

                    # Keyword filter / 关键词过滤
                    text_for_match = f"{title} {text}"
                    if keywords and not _matches_keywords(text_for_match, keywords):
                        continue

                    published_at = None
                    if story.get("time"):
                        published_at = datetime.fromtimestamp(
                            story["time"], tz=timezone.utc
                        )

                    item = NewsItem(
                        title=title,
                        url=url,
                        source="hackernews",
                        source_name="Hacker News",
                        content=f"[HN Score: {score}, Comments: {story.get('descendants', 0)}] {text[:500]}",
                        score=float(score),
                        published_at=published_at,
                    )
                    items.append(item)

                except Exception:
                    logger.debug("Failed to fetch HN story %d", story_id)
                    continue

    except Exception:
        logger.exception("Failed to fetch Hacker News stories")

    logger.info("HN: collected %d stories (after keyword filter)", len(items))
    return items
