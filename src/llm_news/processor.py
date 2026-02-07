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

def _call_llm(
    llm_config: LlmConfig,
    settings: Settings,
    prompt: str,
    max_tokens: int | None = None,
) -> str:
    """Call LLM via OpenRouter (OpenAI-compatible API).

    使用 max_retries 配置控制 429 限流重试次数。
    """
    api_key = settings.openrouter_api_key
    if not api_key:
        raise ValueError("OPENROUTER_API_KEY is required. Get one at https://openrouter.ai/keys")

    client = OpenAI(
        api_key=api_key,
        base_url=llm_config.base_url,
        max_retries=llm_config.max_retries,
    )

    kwargs: dict = {
        "model": llm_config.model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.3,
    }
    if max_tokens:
        kwargs["max_tokens"] = max_tokens

    response = client.chat.completions.create(**kwargs)

    # OpenRouter 可能在响应体中返回错误而非 HTTP 状态码
    error = getattr(response, "error", None)
    if error:
        err_msg = error.get("message", str(error)) if isinstance(error, dict) else str(error)
        err_code = error.get("code", "unknown") if isinstance(error, dict) else "unknown"
        raise RuntimeError(f"OpenRouter returned error (code={err_code}): {err_msg}")

    if not response.choices:
        logger.error("LLM returned empty choices. Raw response: %s", response.model_dump_json()[:500])
        raise ValueError("LLM returned no choices")

    content = response.choices[0].message.content or ""

    # DeepSeek R1 等推理模型可能仅在 reasoning_content 中返回内容
    if not content:
        reasoning = getattr(response.choices[0].message, "reasoning_content", None)
        if reasoning:
            logger.warning("LLM returned reasoning_content but no content, using reasoning")
            content = reasoning

    if not content:
        raise ValueError("LLM returned empty content")

    return content


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


def _extract_json_array(text: str) -> str | None:
    """从 LLM 响应中提取 JSON 数组，兼容各种包装格式。

    支持: 纯 JSON、markdown 代码块、<think> 标签、截断的数组等。
    """
    import re

    # 1. 去除 <think>...</think> 推理标签（GLM-4.5-air 等模型）
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    text = text.strip()

    # 2. 去除 markdown 代码块
    if "```" in text:
        match = re.search(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL)
        if match:
            text = match.group(1).strip()

    # 3. 直接尝试解析
    try:
        json.loads(text)
        return text
    except json.JSONDecodeError:
        pass

    # 4. 提取 [ ... ] 区间
    start = text.find("[")
    if start == -1:
        return None

    end = text.rfind("]")
    if end > start:
        candidate = text[start:end + 1]
        try:
            json.loads(candidate)
            return candidate
        except json.JSONDecodeError:
            pass

    # 5. 处理截断的 JSON 数组（响应被 max_tokens 截断）
    #    回退到最后一个完整的 '}'，去掉尾部逗号，补 ']'
    truncated = text[start:]
    last_brace = truncated.rfind("}")
    if last_brace > 0:
        repaired = truncated[:last_brace + 1].rstrip().rstrip(",") + "\n]"
        try:
            result = json.loads(repaired)
            logger.warning(
                "JSON array was truncated — recovered %d items (response may be incomplete)",
                len(result),
            )
            return repaired
        except json.JSONDecodeError:
            pass

    # 6. 逐对象提取（最后手段）
    object_pattern = re.compile(
        r'\{\s*"index"\s*:\s*\d+\s*,\s*"summary"\s*:\s*"[^"]*"\s*,\s*"score"\s*:\s*\d+\.?\d*\s*\}'
    )
    matches = object_pattern.findall(text)
    if matches:
        candidate = "[\n" + ",\n".join(matches) + "\n]"
        try:
            result = json.loads(candidate)
            logger.warning(
                "JSON extracted via regex — recovered %d items",
                len(result),
            )
            return candidate
        except json.JSONDecodeError:
            pass

    return None


def _parse_summary_response(
    raw: str, items: list[NewsItem]
) -> list[NewsItem]:
    """Parse LLM response and update items with summary + score."""
    json_text = _extract_json_array(raw)

    if json_text is None:
        logger.error("Failed to parse LLM summary response as JSON")
        logger.warning("Raw response (first 500 chars): %s", raw[:500])
        return items

    try:
        results = json.loads(json_text)
    except json.JSONDecodeError:
        logger.error("JSON parse failed after extraction")
        return items

    parsed_count = 0
    for entry in results:
        idx = entry.get("index", -1)
        if 0 <= idx < len(items):
            items[idx].summary = entry.get("summary", "")
            items[idx].score = float(entry.get("score", 5))
            parsed_count += 1

    logger.info("Parsed %d/%d item summaries from LLM response", parsed_count, len(items))
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

    llm_ok = True
    try:
        # 154 条 × ~100 tokens/条 ≈ 15k tokens，设 16000 防截断
        raw_response = _call_llm(config.llm, settings, prompt, max_tokens=16000)
        items = _parse_summary_response(raw_response, items)
    except Exception:
        logger.exception("LLM summarization failed — will skip script generation and TTS")
        llm_ok = False

    # Sort by score descending, take top N
    items.sort(key=lambda x: x.score, reverse=True)
    top_items = items[:top_n]

    logger.info(
        "Top %d items selected (scores: %s)",
        len(top_items),
        [f"{it.score:.1f}" for it in top_items],
    )

    # --- Step 2: Generate Broadcast Script ---
    script = ""
    if not llm_ok:
        logger.warning(
            "Skipping script generation because LLM summarization failed — "
            "TTS will also be skipped"
        )
    else:
        logger.info("Step 2: Generating broadcast script...")
        try:
            script_items_text = _build_script_items_text(top_items)
            script_prompt = _SCRIPT_PROMPT.format(
                today=today, n=len(top_items), items_text=script_items_text
            )
            script = _call_llm(config.llm, settings, script_prompt)
        except Exception:
            logger.exception("Script generation failed — TTS will also be skipped")

    return DailyReport(
        date=today,
        top_items=top_items,
        script=script,
        total_collected=len(items),
        total_after_dedup=len(items),
        llm_ok=llm_ok and bool(script),
    )
