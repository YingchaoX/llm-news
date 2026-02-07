"""Data models for LLM News."""

from datetime import datetime, timezone

from pydantic import BaseModel, Field


class NewsItem(BaseModel):
    """A single news item collected from any source."""

    title: str
    url: str
    source: str  # arxiv, blog, github, twitter, reddit
    source_name: str  # e.g. "OpenAI Blog", "arXiv"
    content: str = ""  # original content / abstract
    summary: str = ""  # LLM-generated summary
    score: float = 0.0  # importance score (1-10)
    published_at: datetime | None = None
    collected_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


class DailyReport(BaseModel):
    """Aggregated daily report."""

    date: str  # YYYY-MM-DD
    top_items: list[NewsItem] = []
    script: str = ""  # broadcast script for TTS
    total_collected: int = 0
    total_after_dedup: int = 0
    llm_ok: bool = False  # LLM 是否成功处理，失败时不应更新 history
