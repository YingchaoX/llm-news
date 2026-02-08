"""GitHub Trending collector via GitHub Search API.

Discovers new popular AI/LLM projects on GitHub (not limited to a fixed repo list).
GitHub Search API 免费，anonymous 10 req/min, authenticated 30 req/min。

Fallback: OSSInsight API (if available).
"""

import logging
from datetime import datetime, timedelta, timezone

import httpx

from ..models import NewsItem
from .base import BaseCollector

logger = logging.getLogger(__name__)

GITHUB_SEARCH_API = "https://api.github.com/search/repositories"


def _matches_keywords(text: str, keywords: list[str]) -> bool:
    text_lower = text.lower()
    return any(kw.lower() in text_lower for kw in keywords)


class GithubTrendingCollector(BaseCollector):
    """GitHub Trending collector (Search API).

    通过 GitHub Search API 发现近期热门 AI 项目。
    Discovers recently popular AI repos by searching recent pushes sorted by stars.
    """

    name = "github_trending"

    def __init__(
        self,
        period: str = "past_24_hours",
        language: str = "Python",
        token: str = "",
    ) -> None:
        self.period = period
        self.language = language
        self.token = token

    def _get_pushed_after(self) -> str:
        """Convert period to a date string for GitHub search.

        将 period 转换为 GitHub 搜索的日期字符串。
        """
        days_map = {
            "past_24_hours": 1,
            "past_week": 7,
            "past_month": 30,
        }
        days = days_map.get(self.period, 1)
        dt = datetime.now(timezone.utc) - timedelta(days=days)
        return dt.strftime("%Y-%m-%d")

    def collect(self, keywords: list[str]) -> list[NewsItem]:
        items: list[NewsItem] = []
        pushed_after = self._get_pushed_after()

        # Build search queries for AI/LLM topics
        # 构建 AI/LLM 相关的搜索查询
        search_terms = ["LLM", "large language model", "transformer", "AI agent"]

        headers: dict[str, str] = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "llm-news/0.1",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        seen_repos: set[str] = set()

        try:
            with httpx.Client(timeout=30, headers=headers, follow_redirects=True) as client:
                for term in search_terms:
                    query = f"{term} language:{self.language} pushed:>{pushed_after}"
                    logger.info("GitHub Trending search: %s", query)

                    try:
                        resp = client.get(
                            GITHUB_SEARCH_API,
                            params={
                                "q": query,
                                "sort": "stars",
                                "order": "desc",
                                "per_page": 15,
                            },
                        )
                        resp.raise_for_status()
                        data = resp.json()

                        for repo in data.get("items", []):
                            full_name = repo.get("full_name", "")
                            if not full_name or full_name in seen_repos:
                                continue
                            seen_repos.add(full_name)

                            description = repo.get("description", "") or ""
                            stars = repo.get("stargazers_count", 0)
                            forks = repo.get("forks_count", 0)
                            language = repo.get("language", "")
                            topics = repo.get("topics", [])

                            # Keyword filter / 关键词过滤
                            text_for_match = f"{full_name} {description} {' '.join(topics)}"
                            if keywords and not _matches_keywords(text_for_match, keywords):
                                continue

                            content_parts = [description]
                            if stars:
                                content_parts.append(f"Stars: {stars:,}")
                            if forks:
                                content_parts.append(f"Forks: {forks:,}")
                            if language:
                                content_parts.append(f"Language: {language}")
                            if topics:
                                content_parts.append(f"Topics: {', '.join(topics[:5])}")

                            updated_str = repo.get("pushed_at", "")
                            published_at = None
                            if updated_str:
                                try:
                                    published_at = datetime.fromisoformat(
                                        updated_str.replace("Z", "+00:00")
                                    )
                                except ValueError:
                                    pass

                            item = NewsItem(
                                title=f"[Trending] {full_name}",
                                url=repo.get("html_url", f"https://github.com/{full_name}"),
                                source="github_trending",
                                source_name="GitHub Trending",
                                content=" | ".join(content_parts),
                                score=float(stars),
                                published_at=published_at,
                            )
                            items.append(item)

                    except Exception:
                        logger.warning("GitHub search failed for term: %s", term)
                        continue

        except Exception:
            logger.exception("Failed to fetch GitHub trending repos")

        logger.info(
            "GitHub Trending: collected %d repos (after keyword filter)", len(items)
        )
        return items
