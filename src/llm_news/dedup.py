"""Deduplication logic based on URL history.

使用 JSON 文件记录已处理的 URL，避免重复推送。
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from .models import NewsItem

logger = logging.getLogger(__name__)

HISTORY_PATH = Path("data/history.json")


def load_history() -> set[str]:
    """Load previously seen URLs from history file."""
    if not HISTORY_PATH.exists():
        return set()
    try:
        data = json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
        urls = set(data.get("urls", []))
        logger.info("Loaded %d URLs from history", len(urls))
        return urls
    except Exception:
        logger.exception("Failed to load history, starting fresh")
        return set()


def save_history(urls: set[str]) -> None:
    """Save seen URLs to history file.

    Keeps a maximum of 10,000 entries to prevent unbounded growth.
    """
    HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)

    # Trim to most recent entries if too large
    url_list = sorted(urls)
    if len(url_list) > 10_000:
        url_list = url_list[-10_000:]

    data = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "count": len(url_list),
        "urls": url_list,
    }
    HISTORY_PATH.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    logger.info("Saved %d URLs to history", len(url_list))


def deduplicate(items: list[NewsItem], history: set[str]) -> list[NewsItem]:
    """Remove items whose URL is already in history.

    Args:
        items: Collected news items.
        history: Set of previously seen URLs.

    Returns:
        Deduplicated list of items.
    """
    seen: set[str] = set()
    result: list[NewsItem] = []

    for item in items:
        if item.url not in history and item.url not in seen:
            seen.add(item.url)
            result.append(item)

    logger.info(
        "Dedup: %d → %d items (%d duplicates removed)",
        len(items),
        len(result),
        len(items) - len(result),
    )
    return result
