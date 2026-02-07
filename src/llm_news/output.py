"""Local output module.

Saves daily report as Markdown, raw items as JSON, to output/YYYY-MM-DD/.
所有产物输出到本地目录，后续可扩展推送渠道。
"""

import json
import logging
from pathlib import Path

from .models import DailyReport

logger = logging.getLogger(__name__)


def _generate_markdown(report: DailyReport) -> str:
    """Generate a Markdown daily report."""
    lines: list[str] = []

    lines.append(f"# LLM News Daily Report - {report.date}")
    lines.append("")
    lines.append(
        f"> Collected {report.total_collected} items, "
        f"showing Top {len(report.top_items)} after dedup & ranking."
    )
    lines.append("")
    lines.append("---")
    lines.append("")

    for i, item in enumerate(report.top_items, 1):
        score_bar = "★" * int(item.score) + "☆" * (10 - int(item.score))
        lines.append(f"## {i}. {item.title}")
        lines.append("")
        lines.append(f"**Source**: `{item.source}` / {item.source_name}  ")
        lines.append(f"**Score**: {item.score:.1f}/10 {score_bar}  ")
        if item.published_at:
            lines.append(f"**Published**: {item.published_at.strftime('%Y-%m-%d %H:%M UTC')}  ")
        lines.append(f"**Link**: [{item.url}]({item.url})")
        lines.append("")
        if item.summary:
            lines.append(f"> {item.summary}")
        elif item.content:
            lines.append(f"> {item.content[:200]}...")
        lines.append("")
        lines.append("---")
        lines.append("")

    return "\n".join(lines)


def save_report(
    report: DailyReport,
    output_dir: str = "output",
) -> Path:
    """Save daily report to local files.

    Creates:
        output/YYYY-MM-DD/daily_report.md   - Markdown report
        output/YYYY-MM-DD/raw_items.json     - Raw item data

    Args:
        report: The daily report to save.
        output_dir: Base output directory.

    Returns:
        Path to the day's output directory.
    """
    day_dir = Path(output_dir) / report.date
    day_dir.mkdir(parents=True, exist_ok=True)

    # Save Markdown report
    md_path = day_dir / "daily_report.md"
    md_content = _generate_markdown(report)
    md_path.write_text(md_content, encoding="utf-8")
    logger.info("Saved Markdown report: %s", md_path)

    # Save raw items as JSON
    json_path = day_dir / "raw_items.json"
    raw_data = {
        "date": report.date,
        "total_collected": report.total_collected,
        "total_after_dedup": report.total_after_dedup,
        "top_items": [item.model_dump(mode="json") for item in report.top_items],
    }
    json_path.write_text(
        json.dumps(raw_data, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    logger.info("Saved raw items: %s", json_path)

    # Save broadcast script as text (for reference)
    if report.script:
        script_path = day_dir / "broadcast_script.txt"
        script_path.write_text(report.script, encoding="utf-8")
        logger.info("Saved broadcast script: %s", script_path)

    return day_dir
