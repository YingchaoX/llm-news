"""Blog / RSS feed collector.

Fetches recent posts from configured RSS feeds and filters by keywords.
使用 httpx 获取内容 + feedparser 解析，兼容非标准 RSS/Atom。
"""

import logging
from datetime import datetime, timezone
from time import mktime

import feedparser
import httpx

from ..models import NewsItem
from .base import BaseCollector

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
    """Fetch RSS content via httpx, then parse with feedparser."""
    resp = client.get(url)
    resp.raise_for_status()
    return feedparser.parse(resp.content)


class BlogCollector(BaseCollector):
    """RSS feed collector for official blogs.

    官方博客 RSS 采集器，支持配置多个 RSS 源。
    """

    name = "blog"

    def __init__(self, blogs: list[dict[str, str]] | None = None) -> None:
        """Args:
            blogs: List of {"name": ..., "url": ...} dicts.
        """
        self.blogs = blogs or []

    def collect(self, keywords: list[str]) -> list[NewsItem]:
        items: list[NewsItem] = []

        with httpx.Client(
            timeout=30, headers=_HTTP_HEADERS, follow_redirects=True,
        ) as client:
            for blog in self.blogs:
                blog_name = blog.get("name", "Unknown")
                blog_url = blog.get("url", "")
                if not blog_url:
                    continue

                logger.info("Fetching RSS: %s (%s)", blog_name, blog_url)
                try:
                    feed = _fetch_and_parse(blog_url, client)

                    if feed.bozo and not feed.entries:
                        logger.warning(
                            "Failed to parse RSS for %s: %s",
                            blog_name, feed.bozo_exception,
                        )
                        continue

                    for entry in feed.entries[:20]:
                        title = entry.get("title", "").strip()
                        link = entry.get("link", "")
                        summary = entry.get("summary", "").strip()
                        content = (
                            entry.get("content", [{}])[0].get("value", "")
                            if entry.get("content")
                            else ""
                        )

                        text_for_match = f"{title} {summary} {content}"
                        if keywords and not _matches_keywords(text_for_match, keywords):
                            continue

                        item = NewsItem(
                            title=title,
                            url=link,
                            source="blog",
                            source_name=blog_name,
                            content=summary or content[:500],
                            published_at=_parse_published(entry),
                        )
                        items.append(item)

                except Exception:
                    logger.exception("Failed to fetch RSS for %s", blog_name)

        logger.info("Blogs: collected %d posts", len(items))
        return items
