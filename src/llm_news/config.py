"""Configuration loading from config.yaml + .env."""

from pathlib import Path

import yaml
from pydantic import BaseModel
from pydantic_settings import BaseSettings


# ---------------------------------------------------------------------------
# Config sub-models (loaded from config.yaml)
# ---------------------------------------------------------------------------

class ArxivConfig(BaseModel):
    enabled: bool = True
    categories: list[str] = ["cs.CL", "cs.AI", "cs.LG"]
    max_results: int = 50
    require_institution: bool = True  # 仅保留知名大学/公司的论文


class BlogSource(BaseModel):
    name: str
    url: str


class BlogConfig(BaseModel):
    enabled: bool = True
    feeds: list[BlogSource] = []


class GithubConfig(BaseModel):
    enabled: bool = True
    repos: list[str] = []


class GithubTrendingConfig(BaseModel):
    enabled: bool = True
    period: str = "past_24_hours"
    language: str = "Python"


class HfPapersConfig(BaseModel):
    enabled: bool = True
    limit: int = 30


class HfModelsConfig(BaseModel):
    enabled: bool = True
    limit: int = 50
    orgs: list[str] = [
        "deepseek-ai",
        "Qwen",
        "zai-org",
        "MiniMaxAI",
        "stepfun-ai",
        "meta-llama",
        "mistralai",
        "google",
        "microsoft",
        "openai",
    ]


class PwcConfig(BaseModel):
    enabled: bool = True
    limit: int = 50


class HackerNewsConfig(BaseModel):
    enabled: bool = True
    story_type: str = "topstories"
    limit: int = 60


class RedditConfig(BaseModel):
    enabled: bool = True
    subreddits: list[str] = ["MachineLearning", "LocalLLaMA"]
    time_filter: str = "day"
    limit: int = 25


class SourcesConfig(BaseModel):
    arxiv: ArxivConfig = ArxivConfig()
    blog: BlogConfig = BlogConfig()
    github: GithubConfig = GithubConfig()
    github_trending: GithubTrendingConfig = GithubTrendingConfig()
    hf_papers: HfPapersConfig = HfPapersConfig()
    hf_models: HfModelsConfig = HfModelsConfig()
    pwc: PwcConfig = PwcConfig()
    hackernews: HackerNewsConfig = HackerNewsConfig()
    reddit: RedditConfig = RedditConfig()


class LlmConfig(BaseModel):
    model: str = "z-ai/glm-4.5-air:free"  # OpenRouter model ID
    base_url: str = "https://openrouter.ai/api/v1"
    top_n: int = 10
    max_retries: int = 5  # OpenAI client 重试次数（应对 429 限流）


class TtsConfig(BaseModel):
    voice: str = "en-US-AriaNeural"
    rate: str = "+10%"


class OutputConfig(BaseModel):
    dir: str = "output"


class PushConfig(BaseModel):
    """Push notification config / 推送通知配置."""

    enabled: bool = False
    # GitHub Pages base URL (e.g. https://user.github.io/llm-news)
    site_url: str = ""
    # Bark push (iOS)
    bark_enabled: bool = False


class AppConfig(BaseModel):
    """Application config loaded from config.yaml."""

    sources: SourcesConfig = SourcesConfig()
    llm: LlmConfig = LlmConfig()
    tts: TtsConfig = TtsConfig()
    output: OutputConfig = OutputConfig()
    push: PushConfig = PushConfig()
    keywords: list[str] = []


# ---------------------------------------------------------------------------
# Secrets (loaded from .env / environment variables)
# ---------------------------------------------------------------------------

class Settings(BaseSettings):
    """Secret settings loaded from environment / .env file."""

    openrouter_api_key: str = ""
    reddit_client_id: str = ""
    reddit_client_secret: str = ""
    github_token: str = ""
    bark_device_key: str = ""  # Bark push notification / iOS 推送

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------

def load_config(config_path: str = "config.yaml") -> tuple[AppConfig, Settings]:
    """Load app config from YAML and secrets from .env."""
    path = Path(config_path)
    if path.exists():
        with open(path) as f:
            data = yaml.safe_load(f) or {}
        app_config = AppConfig(**data)
    else:
        app_config = AppConfig()

    settings = Settings()
    return app_config, settings
