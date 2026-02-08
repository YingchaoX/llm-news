"""Push notification module.

支持通过 Bark 向 iPhone 发送推送通知。
Bark App: https://apps.apple.com/app/bark/id1403753865

推送内容包含当日报告标题和 GitHub Pages 链接，
用户点击通知即可在 Safari 中打开报告页面并收听音频。
"""

import logging

import httpx

logger = logging.getLogger(__name__)

# Bark API 超时 / Bark API timeout
_TIMEOUT = 10


def push_bark(
    device_key: str,
    title: str,
    body: str,
    url: str = "",
    group: str = "LLM News",
    icon: str = "https://cdn-icons-png.flaticon.com/512/4712/4712109.png",
) -> bool:
    """Send a push notification via Bark.

    Bark API docs: https://bark.day.app/#/tutorial

    Args:
        device_key: Bark device key (from the Bark app).
        title: Notification title.
        body: Notification body text.
        url: URL to open when notification is tapped.
        group: Notification group name.
        icon: Custom icon URL.

    Returns:
        True if push succeeded, False otherwise.
    """
    if not device_key:
        logger.warning("Bark device key is empty, skipping push")
        return False

    api_url = f"https://api.day.app/{device_key}"
    payload = {
        "title": title,
        "body": body,
        "group": group,
        "icon": icon,
        "url": url,
        "isArchive": "1",  # 保存到历史记录 / Save to Bark history
    }

    try:
        resp = httpx.post(api_url, json=payload, timeout=_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") == 200:
            logger.info("Bark push succeeded: %s", title)
            return True
        else:
            logger.error("Bark push failed: %s", data)
            return False
    except Exception:
        logger.exception("Bark push error")
        return False


def push_report(
    device_key: str,
    report_date: str,
    top_count: int,
    total_collected: int,
    site_url: str,
) -> bool:
    """Push daily report notification via Bark.

    Args:
        device_key: Bark device key.
        report_date: Report date string (YYYY-MM-DD).
        top_count: Number of top items in the report.
        total_collected: Total items collected.
        site_url: GitHub Pages base URL.

    Returns:
        True if push succeeded.
    """
    title = f"📰 LLM 日报 {report_date}"
    body = f"今日采集 {total_collected} 条，精选 Top {top_count}，点击查看并收听语音播报"
    url = f"{site_url.rstrip('/')}/{report_date}/"

    return push_bark(
        device_key=device_key,
        title=title,
        body=body,
        url=url,
    )
