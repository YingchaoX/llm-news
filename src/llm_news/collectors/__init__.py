"""News collectors for various sources.

Collector registry — maps collector names to their classes.
新增 collector 只需：1) 写 collector 文件  2) 在此注册  3) 在 config.yaml 启用。
"""

from .arxiv_collector import ArxivCollector
from .base import BaseCollector
from .blog_collector import BlogCollector
from .github_collector import GithubCollector
from .github_trending_collector import GithubTrendingCollector
from .hackernews_collector import HackerNewsCollector
from .hf_models_collector import HfModelsCollector
from .hf_papers_collector import HfPapersCollector
from .pwc_collector import PwcCollector
from .reddit_collector import RedditCollector

# Collector registry: name -> class
# collector 注册表：名称 -> 类
REGISTRY: dict[str, type[BaseCollector]] = {
    "arxiv": ArxivCollector,
    "blog": BlogCollector,
    "github": GithubCollector,
    "github_trending": GithubTrendingCollector,
    "hackernews": HackerNewsCollector,
    "hf_models": HfModelsCollector,
    "hf_papers": HfPapersCollector,
    "pwc": PwcCollector,
    "reddit": RedditCollector,
}

__all__ = [
    "BaseCollector",
    "REGISTRY",
    "ArxivCollector",
    "BlogCollector",
    "GithubCollector",
    "GithubTrendingCollector",
    "HackerNewsCollector",
    "HfModelsCollector",
    "HfPapersCollector",
    "PwcCollector",
    "RedditCollector",
]
