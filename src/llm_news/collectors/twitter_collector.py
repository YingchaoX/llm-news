"""Twitter/X collector via Nitter RSS (best-effort).

Nitter is a free Twitter frontend that exposes RSS feeds.
NOTE: Nitter instances are frequently unreliable / go offline.
This collector is disabled by default; enable in config.yaml.
Twitter/X 采集器，通过 Nitter RSS 获取推文（不稳定，默认禁用）。
"""

import logging
from datetime import datetime, timezone
from time import mktime

import feedparser

from ..models import NewsItem

logger = logging.getLogger(__name__)


def collect(
    kol_list: list[str],
    nitter_instance: str = "https://nitter.privacydev.net",
    keywords: list[str] | None = None,
    enabled: bool = False,
) -> list[NewsItem]:
    """Collect tweets from KOL list via Nitter RSS.

    Args:
        kol_list: Twitter usernames (without @).
        nitter_instance: Nitter instance base URL.
        keywords: Keywords to filter tweets.
        enabled: Whether this collector is enabled.

    Returns:
        List of NewsItem from Twitter/Nitter.
    """
    if not enabled:
        logger.info("Twitter collector is disabled, skipping")
        return []

    items: list[NewsItem] = []

    for username in kol_list:
        username = username.lstrip("@")
        rss_url = f"{nitter_instance}/{username}/rss"
        logger.info("Fetching Nitter RSS: %s", rss_url)

        try:
            feed = feedparser.parse(rss_url)
            if feed.bozo and not feed.entries:
                logger.warning("Nitter RSS failed for @%s", username)
                continue

            for entry in feed.entries[:10]:
                title = entry.get("title", "").strip()
                link = entry.get("link", "")
                content = entry.get("description", "").strip()

                # Keyword filter
                if keywords:
                    text = f"{title} {content}".lower()
                    if not any(kw.lower() in text for kw in keywords):
                        continue

                published_at = None
                if entry.get("published_parsed"):
                    try:
                        published_at = datetime.fromtimestamp(
                            mktime(entry.published_parsed), tz=timezone.utc
                        )
                    except Exception:
                        pass

                item = NewsItem(
                    title=f"@{username}: {title[:120]}",
                    url=link.replace(nitter_instance, "https://x.com"),
                    source="twitter",
                    source_name=f"@{username}",
                    content=content[:500],
                    published_at=published_at,
                )
                items.append(item)

        except Exception:
            logger.exception("Failed to fetch Nitter RSS for @%s", username)

    logger.info("Twitter: collected %d tweets", len(items))
    return items
