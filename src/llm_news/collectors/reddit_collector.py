"""Reddit collector via PRAW.

Fetches hot/top posts from LLM-related subreddits.
Reddit API 免费 100 QPM。
"""

import logging
from datetime import datetime, timezone

import praw
from praw.exceptions import PRAWException

from ..models import NewsItem

logger = logging.getLogger(__name__)


def _matches_keywords(text: str, keywords: list[str]) -> bool:
    text_lower = text.lower()
    return any(kw.lower() in text_lower for kw in keywords)


def collect(
    subreddits: list[str],
    client_id: str,
    client_secret: str,
    time_filter: str = "day",
    limit: int = 25,
    keywords: list[str] | None = None,
) -> list[NewsItem]:
    """Collect hot posts from Reddit subreddits.

    Args:
        subreddits: List of subreddit names.
        client_id: Reddit API client ID.
        client_secret: Reddit API client secret.
        time_filter: Time filter for top posts (day, week, etc.).
        limit: Max posts per subreddit.
        keywords: Keywords to filter posts.

    Returns:
        List of NewsItem from Reddit.
    """
    if not client_id or not client_secret:
        logger.warning("Reddit credentials not configured, skipping")
        return []

    items: list[NewsItem] = []

    try:
        reddit = praw.Reddit(
            client_id=client_id,
            client_secret=client_secret,
            user_agent="llm-news/0.1.0",
        )

        for sub_name in subreddits:
            logger.info("Fetching Reddit: r/%s (top/%s, limit=%d)", sub_name, time_filter, limit)
            try:
                subreddit = reddit.subreddit(sub_name)
                for post in subreddit.top(time_filter=time_filter, limit=limit):
                    title = post.title or ""
                    selftext = post.selftext or ""
                    url = post.url or ""
                    permalink = f"https://www.reddit.com{post.permalink}"

                    text_for_match = f"{title} {selftext}"
                    if keywords and not _matches_keywords(text_for_match, keywords):
                        continue

                    published_at = None
                    if post.created_utc:
                        published_at = datetime.fromtimestamp(
                            post.created_utc, tz=timezone.utc
                        )

                    # Use permalink as canonical URL, store original url in content
                    content = selftext[:500] if selftext else ""
                    if url and url != permalink and not url.startswith("https://www.reddit.com"):
                        content = f"[Link: {url}] {content}"

                    item = NewsItem(
                        title=title,
                        url=permalink,
                        source="reddit",
                        source_name=f"r/{sub_name}",
                        content=content,
                        score=float(post.score),  # use reddit score as initial score
                        published_at=published_at,
                    )
                    items.append(item)

            except PRAWException:
                logger.exception("Failed to fetch r/%s", sub_name)

    except Exception:
        logger.exception("Failed to initialize Reddit client")

    logger.info("Reddit: collected %d posts", len(items))
    return items
