"""Papers with Code collector.

Fetches trending papers with associated code implementations.
Papers with Code API 免费，无需 API Key。

API: https://paperswithcode.com/api/v1/papers/
"""

import logging
from datetime import datetime, timezone

import httpx

from ..models import NewsItem
from .base import BaseCollector

logger = logging.getLogger(__name__)

PWC_API = "https://paperswithcode.com/api/v1/papers/"


def _matches_keywords(text: str, keywords: list[str]) -> bool:
    text_lower = text.lower()
    return any(kw.lower() in text_lower for kw in keywords)


class PwcCollector(BaseCollector):
    """Papers with Code collector.

    论文+代码实现一体的采集器，比纯 arXiv 更实用。
    Tracks papers that come with code implementations.
    """

    name = "pwc"

    def __init__(self, limit: int = 50) -> None:
        self.limit = limit

    def collect(self, keywords: list[str]) -> list[NewsItem]:
        items: list[NewsItem] = []

        try:
            with httpx.Client(
                timeout=30,
                follow_redirects=False,  # PwC API may redirect to HF; stay on PwC
                headers={"Accept": "application/json"},
            ) as client:
                # Fetch latest papers, sorted by date
                # 获取最新论文，按日期排序
                resp = client.get(
                    PWC_API,
                    params={
                        "ordering": "-published",
                        "items_per_page": self.limit,
                    },
                )
                resp.raise_for_status()
                data = resp.json()

                results = data.get("results", [])
                logger.info("Papers with Code: fetched %d papers", len(results))

                for paper in results:
                    title = paper.get("title", "").strip()
                    abstract = paper.get("abstract", "").strip()
                    paper_url = paper.get("url_abs", "") or paper.get("paper_url", "")
                    arxiv_id = paper.get("arxiv_id", "")
                    published = paper.get("published", "")
                    authors = paper.get("authors", [])

                    if not title:
                        continue

                    # Keyword filter / 关键词过滤
                    text_for_match = f"{title} {abstract}"
                    if keywords and not _matches_keywords(text_for_match, keywords):
                        continue

                    # Build URL: prefer arxiv link / 优先使用 arXiv 链接
                    if arxiv_id and not paper_url:
                        paper_url = f"https://arxiv.org/abs/{arxiv_id}"

                    # PwC page URL
                    pwc_url = paper.get("url", "")
                    if pwc_url and not pwc_url.startswith("http"):
                        pwc_url = f"https://paperswithcode.com{pwc_url}"

                    # Build content with author info / 构建含作者信息的内容
                    content_parts = []
                    if authors:
                        author_names = authors[:3]
                        author_str = ", ".join(author_names)
                        if len(authors) > 3:
                            author_str += " et al."
                        content_parts.append(f"[Authors: {author_str}]")
                    if abstract:
                        content_parts.append(abstract[:500])
                    if pwc_url:
                        content_parts.append(f"[PwC: {pwc_url}]")

                    published_at = None
                    if published:
                        try:
                            published_at = datetime.fromisoformat(published).replace(
                                tzinfo=timezone.utc
                            )
                        except ValueError:
                            try:
                                published_at = datetime.strptime(
                                    published, "%Y-%m-%d"
                                ).replace(tzinfo=timezone.utc)
                            except ValueError:
                                pass

                    item = NewsItem(
                        title=f"[PwC] {title}",
                        url=paper_url or pwc_url,
                        source="pwc",
                        source_name="Papers with Code",
                        content=" ".join(content_parts),
                        published_at=published_at,
                    )
                    items.append(item)

        except Exception:
            logger.exception("Failed to fetch Papers with Code")

        logger.info("Papers with Code: collected %d papers", len(items))
        return items
