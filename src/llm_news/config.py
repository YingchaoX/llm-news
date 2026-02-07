"""Configuration loading from config.yaml + .env."""

from pathlib import Path

import yaml
from pydantic import BaseModel
from pydantic_settings import BaseSettings


# ---------------------------------------------------------------------------
# Config sub-models (loaded from config.yaml)
# ---------------------------------------------------------------------------

class ArxivConfig(BaseModel):
    categories: list[str] = ["cs.CL", "cs.AI", "cs.LG"]
    max_results: int = 50


class BlogSource(BaseModel):
    name: str
    url: str


class GithubConfig(BaseModel):
    repos: list[str] = []


class TwitterConfig(BaseModel):
    enabled: bool = False
    kol_list: list[str] = []
    nitter_instance: str = "https://nitter.privacydev.net"


class RedditConfig(BaseModel):
    subreddits: list[str] = ["MachineLearning", "LocalLLaMA"]
    time_filter: str = "day"
    limit: int = 25


class SourcesConfig(BaseModel):
    arxiv: ArxivConfig = ArxivConfig()
    blogs: list[BlogSource] = []
    github: GithubConfig = GithubConfig()
    twitter: TwitterConfig = TwitterConfig()
    reddit: RedditConfig = RedditConfig()


class LlmConfig(BaseModel):
    model: str = "deepseek/deepseek-r1:free"  # OpenRouter model ID
    base_url: str = "https://openrouter.ai/api/v1"
    top_n: int = 10
    max_retries: int = 5  # OpenAI client 重试次数（应对 429 限流）


class TtsConfig(BaseModel):
    voice: str = "en-US-AriaNeural"
    rate: str = "+10%"


class OutputConfig(BaseModel):
    dir: str = "output"


class AppConfig(BaseModel):
    """Application config loaded from config.yaml."""

    sources: SourcesConfig = SourcesConfig()
    llm: LlmConfig = LlmConfig()
    tts: TtsConfig = TtsConfig()
    output: OutputConfig = OutputConfig()
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
