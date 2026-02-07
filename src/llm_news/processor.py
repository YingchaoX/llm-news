"""LLM processor for summarization, ranking, and script generation.

通过 OpenRouter (OpenAI 兼容接口) 调用免费模型。
Two LLM calls total:
  1. Summarize + score all items → select Top N
  2. Generate broadcast script from Top N
"""

import json
import logging
from datetime import date

from openai import OpenAI

from .config import AppConfig, LlmConfig, Settings
from .models import DailyReport, NewsItem

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# LLM client
# ---------------------------------------------------------------------------

def _call_llm(llm_config: LlmConfig, settings: Settings, prompt: str) -> str:
    """Call LLM via OpenRouter (OpenAI-compatible API)."""
    api_key = settings.openrouter_api_key
    if not api_key:
        raise ValueError("OPENROUTER_API_KEY is required. Get one at https://openrouter.ai/keys")

    client = OpenAI(
        api_key=api_key,
        base_url=llm_config.base_url,
    )
    response = client.chat.completions.create(
        model=llm_config.model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
    )
    return response.choices[0].message.content or ""


# ---------------------------------------------------------------------------
# Step 1: Summarize & Score
# ---------------------------------------------------------------------------

_SUMMARIZE_PROMPT = """\
你是一位专业的 AI/LLM 新闻编辑。给定以下 {count} 条新闻，
请为每条新闻返回一个 JSON 对象，包含：
- "index": 新闻的索引（从 0 开始）
- "summary": 简洁的 1-2 句中文摘要，突出新闻的关键信息和重要性
- "score": 重要性评分（1-10 分，10 = 重大突破，1 = 次要信息）

评分标准：
- 9-10: 重大模型发布、突破性论文、重要 API 变更
- 7-8: 值得关注的研究、重要库更新、行业新闻
- 5-6: 有趣但属于渐进式进展
- 3-4: 小更新、常规发布
- 1-2: 边缘相关、影响较小

仅返回 JSON 数组，不要 markdown 代码块，不要额外文字。

新闻列表：
{items_text}
"""


def _build_items_text(items: list[NewsItem]) -> str:
    parts: list[str] = []
    for i, item in enumerate(items):
        parts.append(
            f"[{i}] ({item.source}/{item.source_name}) {item.title}\n"
            f"    URL: {item.url}\n"
            f"    Content: {item.content[:300]}"
        )
    return "\n\n".join(parts)


def _parse_summary_response(
    raw: str, items: list[NewsItem]
) -> list[NewsItem]:
    """Parse LLM response and update items with summary + score."""
    # Strip markdown code fences if present
    text = raw.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:])
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

    try:
        results = json.loads(text)
    except json.JSONDecodeError:
        logger.error("Failed to parse LLM summary response as JSON")
        logger.debug("Raw response: %s", raw[:500])
        # Fallback: return items with default scores
        return items

    for entry in results:
        idx = entry.get("index", -1)
        if 0 <= idx < len(items):
            items[idx].summary = entry.get("summary", "")
            items[idx].score = float(entry.get("score", 5))

    return items


# ---------------------------------------------------------------------------
# Step 2: Generate Broadcast Script
# ---------------------------------------------------------------------------

_SCRIPT_PROMPT = """\
你是一位专业的 AI 科技新闻主播。请为今天（{today}）的 Top {n} AI/LLM 新闻生成一篇中文播报稿。

要求：
- 朗读时长约 5-10 分钟
- 开头简短问候并说明日期
- 每条新闻包含：标题/要点 → 发生了什么 → 为什么重要
- 新闻之间使用自然的过渡语句
- 结尾简短收尾
- 语气：专业、有吸引力、略带对话感
- 不要使用 markdown 格式、项目符号或特殊字符
- 输出纯文本，适合语音合成朗读
- 英文专有名词（如模型名、库名）保留原文

播报内容：
{items_text}
"""


def _build_script_items_text(items: list[NewsItem]) -> str:
    parts: list[str] = []
    for i, item in enumerate(items, 1):
        parts.append(
            f"{i}. [{item.source_name}] {item.title}\n"
            f"   Summary: {item.summary}\n"
            f"   URL: {item.url}"
        )
    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Main process function
# ---------------------------------------------------------------------------

def process(
    items: list[NewsItem],
    config: AppConfig,
    settings: Settings,
) -> DailyReport:
    """Summarize, rank, and generate broadcast script.

    Args:
        items: Deduplicated news items.
        config: Application config.
        settings: Secret settings.

    Returns:
        DailyReport with top items and broadcast script.
    """
    today = date.today().isoformat()
    top_n = config.llm.top_n

    if not items:
        logger.warning("No items to process")
        return DailyReport(date=today, total_collected=0, total_after_dedup=0)

    # --- Step 1: Summarize & Score ---
    logger.info("Step 1: Summarizing %d items with LLM (%s)...", len(items), config.llm.model)
    items_text = _build_items_text(items)
    prompt = _SUMMARIZE_PROMPT.format(count=len(items), items_text=items_text)

    try:
        raw_response = _call_llm(config.llm, settings, prompt)
        items = _parse_summary_response(raw_response, items)
    except Exception:
        logger.exception("LLM summarization failed, using items without summaries")

    # Sort by score descending, take top N
    items.sort(key=lambda x: x.score, reverse=True)
    top_items = items[:top_n]

    logger.info(
        "Top %d items selected (scores: %s)",
        len(top_items),
        [f"{it.score:.1f}" for it in top_items],
    )

    # --- Step 2: Generate Broadcast Script ---
    logger.info("Step 2: Generating broadcast script...")
    script = ""
    try:
        script_items_text = _build_script_items_text(top_items)
        script_prompt = _SCRIPT_PROMPT.format(
            today=today, n=len(top_items), items_text=script_items_text
        )
        script = _call_llm(config.llm, settings, script_prompt)
    except Exception:
        logger.exception("Script generation failed")

    return DailyReport(
        date=today,
        top_items=top_items,
        script=script,
        total_collected=len(items),
        total_after_dedup=len(items),
    )
