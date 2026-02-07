"""Blog / RSS feed collector.

Fetches recent posts from configured RSS feeds and filters by keywords.
使用 httpx 获取内容 + feedparser 解析，兼容非标准 RSS/Atom。
"""

import logging
from datetime import datetime, timezone
from time import mktime

import feedparser
import httpx

from ..config import BlogSource
from ..models import NewsItem

logger = logging.getLogger(__name__)

_HTTP_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; llm-news/0.1; +https://github.com/llm-news)",
    "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, */*",
}


def _parse_published(entry: dict) -> datetime | None:
    """Try to parse the published date from a feed entry."""
    for key in ("published_parsed", "updated_parsed"):
        parsed = entry.get(key)
        if parsed:
            try:
                return datetime.fromtimestamp(mktime(parsed), tz=timezone.utc)
            except Exception:
                pass
    return None


def _matches_keywords(text: str, keywords: list[str]) -> bool:
    """Check if text contains any of the keywords (case-insensitive)."""
    text_lower = text.lower()
    return any(kw.lower() in text_lower for kw in keywords)


def _fetch_and_parse(url: str, client: httpx.Client) -> feedparser.FeedParserDict:
    """Fetch RSS content via httpx, then parse with feedparser.

    Some blog servers block feedparser's default user-agent or return
    malformed XML when accessed directly.  Fetching with httpx first
    (with a browser-like UA) gives us the raw bytes, which feedparser
    can often still handle even if the XML is slightly broken.
    """
    resp = client.get(url)
    resp.raise_for_status()
    return feedparser.parse(resp.content)


def collect(
    blogs: list[BlogSource],
    keywords: list[str],
) -> list[NewsItem]:
    """Collect recent posts from RSS feeds.

    Args:
        blogs: List of blog sources with name and RSS URL.
        keywords: Keywords to filter posts.

    Returns:
        List of NewsItem from blog feeds.
    """
    items: list[NewsItem] = []

    with httpx.Client(
        timeout=30,
        headers=_HTTP_HEADERS,
        follow_redirects=True,
    ) as client:
        for blog in blogs:
            logger.info("Fetching RSS: %s (%s)", blog.name, blog.url)
            try:
                feed = _fetch_and_parse(blog.url, client)

                if feed.bozo and not feed.entries:
                    logger.warning(
                        "Failed to parse RSS for %s: %s",
                        blog.name,
                        feed.bozo_exception,
                    )
                    continue

                for entry in feed.entries[:20]:  # limit per feed
                    title = entry.get("title", "").strip()
                    link = entry.get("link", "")
                    summary = entry.get("summary", "").strip()
                    content = (
                        entry.get("content", [{}])[0].get("value", "")
                        if entry.get("content")
                        else ""
                    )

                    # Use summary or content snippet for keyword matching
                    text_for_match = f"{title} {summary} {content}"
                    if keywords and not _matches_keywords(text_for_match, keywords):
                        continue

                    item = NewsItem(
                        title=title,
                        url=link,
                        source="blog",
                        source_name=blog.name,
                        content=summary or content[:500],
                        published_at=_parse_published(entry),
                    )
                    items.append(item)

            except Exception:
                logger.exception("Failed to fetch RSS for %s", blog.name)

    logger.info("Blogs: collected %d posts", len(items))
    return items
