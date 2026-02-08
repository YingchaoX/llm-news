"""GitHub release collector.

Tracks releases from configured repositories via GitHub REST API.
GitHub API 免费 5000 req/h (with token), 60 req/h (anonymous).
"""

import logging
from datetime import datetime, timezone

import httpx

from ..models import NewsItem
from .base import BaseCollector

logger = logging.getLogger(__name__)

GITHUB_API = "https://api.github.com"


class GithubCollector(BaseCollector):
    """GitHub release collector.

    追踪指定仓库的 Release 信息。
    """

    name = "github"

    def __init__(
        self,
        repos: list[str] | None = None,
        token: str = "",
    ) -> None:
        self.repos = repos or []
        self.token = token

    def _get_headers(self) -> dict[str, str]:
        headers = {"Accept": "application/vnd.github+json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def collect(self, keywords: list[str]) -> list[NewsItem]:
        items: list[NewsItem] = []
        headers = self._get_headers()

        with httpx.Client(timeout=30, headers=headers, follow_redirects=True) as client:
            for repo in self.repos:
                logger.info("Fetching GitHub releases: %s", repo)
                try:
                    resp = client.get(
                        f"{GITHUB_API}/repos/{repo}/releases",
                        params={"per_page": 5},
                    )
                    if resp.status_code == 404:
                        logger.debug("No releases for %s, skipping", repo)
                        continue
                    resp.raise_for_status()

                    for release in resp.json():
                        tag = release.get("tag_name", "")
                        name = release.get("name", "") or tag
                        body = release.get("body", "") or ""
                        html_url = release.get("html_url", "")
                        published_str = release.get("published_at", "")

                        published_at = None
                        if published_str:
                            try:
                                published_at = datetime.fromisoformat(
                                    published_str.replace("Z", "+00:00")
                                )
                            except ValueError:
                                pass

                        item = NewsItem(
                            title=f"{repo} {name}",
                            url=html_url,
                            source="github",
                            source_name=repo,
                            content=body[:1000],
                            published_at=published_at,
                        )
                        items.append(item)

                except Exception:
                    logger.exception("Failed to fetch releases for %s", repo)

        logger.info("GitHub: collected %d releases", len(items))
        return items
