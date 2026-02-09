"""GitHub Pages generation module (Jekyll-based).

生成 Jekyll 站点文件，由 GitHub Pages 自动构建：
- _config.yml: Jekyll 配置 + 主题
- index.md: 首页（历史日报列表）
- YYYY-MM-DD/index.md: 每日报告（Markdown + 内嵌音频播放器）
- YYYY-MM-DD/daily_report.mp3: 音频文件
"""

import logging
import shutil
from pathlib import Path

from .models import DailyReport

logger = logging.getLogger(__name__)

# GitHub Pages 输出目录 / GitHub Pages output directory
PAGES_DIR = "pages"


def _generate_jekyll_config(site_url: str) -> str:
    """Generate _config.yml for Jekyll."""
    return f"""title: LLM 每日资讯
description: 每日自动聚合 LLM / AI 领域最新动态
remote_theme: pages-themes/cayman@v0.2.0
plugins:
  - jekyll-remote-theme
baseurl: /{site_url.rstrip('/').split('/')[-1]}
url: {'/'.join(site_url.rstrip('/').split('/')[:-1])}
"""


def _generate_report_md(report: DailyReport, site_url: str) -> str:
    """Generate a Markdown report page with embedded audio player.

    Args:
        report: The daily report data.
        site_url: Base URL for GitHub Pages.

    Returns:
        Jekyll-compatible Markdown string with front matter.
    """
    audio_url = f"{site_url.rstrip('/')}/{report.date}/daily_report.mp3"

    lines: list[str] = []

    # Jekyll front matter
    lines.append("---")
    lines.append(f"title: LLM 每日资讯 - {report.date}")
    lines.append("layout: default")
    lines.append("---")
    lines.append("")
    lines.append(f"# LLM 每日资讯 - {report.date}")
    lines.append("")
    lines.append(f"> 共采集 **{report.total_collected}** 条，去重排序后精选 **Top {len(report.top_items)}**")
    lines.append("")

    # Audio player (raw HTML in Markdown)
    lines.append("## 🎧 语音播报")
    lines.append("")
    lines.append(f'<audio controls preload="metadata" style="width:100%; max-width:600px;">')
    lines.append(f'  <source src="{audio_url}" type="audio/mpeg">')
    lines.append(f'  你的浏览器不支持音频播放，请 <a href="{audio_url}">下载 MP3</a> 收听。')
    lines.append("</audio>")
    lines.append("")
    lines.append("---")
    lines.append("")

    # News items
    for i, item in enumerate(report.top_items, 1):
        score_stars = "★" * int(item.score) + "☆" * (10 - int(item.score))
        lines.append(f"### {i}. {item.title}")
        lines.append("")
        lines.append(f"📂 `{item.source}` / {item.source_name} &nbsp;&nbsp; ⭐ **{item.score:.1f}/10** {score_stars}")
        if item.published_at:
            lines.append(f" &nbsp;&nbsp; 📅 {item.published_at.strftime('%Y-%m-%d %H:%M UTC')}")
        lines.append("")

        summary = item.summary or (item.content[:200] + "..." if item.content else "")
        if summary:
            lines.append(f"> {summary}")
            lines.append("")

        lines.append(f"[🔗 查看原文]({item.url})")
        lines.append("")
        lines.append("---")
        lines.append("")

    # Footer
    lines.append(f"[← 所有日报]({site_url.rstrip('/')}/)")
    lines.append("")

    return "\n".join(lines)


def _generate_index_md(dates: list[str], site_url: str) -> str:
    """Generate the index page listing all available reports.

    Args:
        dates: List of date strings (YYYY-MM-DD), sorted descending.
        site_url: Base URL for GitHub Pages.

    Returns:
        Jekyll-compatible Markdown string.
    """
    lines: list[str] = []

    # Front matter
    lines.append("---")
    lines.append("title: LLM 每日资讯")
    lines.append("layout: default")
    lines.append("---")
    lines.append("")
    lines.append("# 🤖 LLM 每日资讯")
    lines.append("")
    lines.append("> 每日自动聚合 LLM / AI 领域最新动态，含语音播报")
    lines.append("")
    lines.append("## 📅 历史日报")
    lines.append("")
    lines.append("| 日期 | 链接 |")
    lines.append("|------|------|")

    for d in dates:
        lines.append(f"| {d} | [查看日报]({site_url.rstrip('/')}/{d}/) |")

    lines.append("")

    return "\n".join(lines)


def build_pages(
    report: DailyReport,
    site_url: str,
    output_dir: str = "output",
    pages_dir: str = PAGES_DIR,
) -> Path:
    """Build Jekyll-based GitHub Pages site.

    Workflow:
      1. Preserve existing pages content (history)
      2. Write/overwrite _config.yml
      3. Create today's report Markdown + copy MP3
      4. Rebuild the index page

    Args:
        report: Today's daily report.
        site_url: GitHub Pages base URL.
        output_dir: Source output directory containing YYYY-MM-DD folders.
        pages_dir: Destination directory for GitHub Pages files.

    Returns:
        Path to the pages directory.
    """
    pages_path = Path(pages_dir)
    pages_path.mkdir(parents=True, exist_ok=True)

    # --- Jekyll config ---
    config_yml = _generate_jekyll_config(site_url)
    (pages_path / "_config.yml").write_text(config_yml, encoding="utf-8")
    logger.info("Generated _config.yml")

    # --- Build today's report ---
    day_pages = pages_path / report.date
    day_pages.mkdir(parents=True, exist_ok=True)

    # Generate Markdown
    md = _generate_report_md(report, site_url)
    (day_pages / "index.md").write_text(md, encoding="utf-8")
    logger.info("Generated report page: %s/index.md", day_pages)

    # Copy MP3 if exists
    mp3_src = Path(output_dir) / report.date / "daily_report.mp3"
    if mp3_src.exists():
        shutil.copy2(mp3_src, day_pages / "daily_report.mp3")
        logger.info("Copied audio: %s", day_pages / "daily_report.mp3")
    else:
        logger.warning("MP3 not found: %s, audio player will not work", mp3_src)

    # --- Clean up stale HTML files from pre-Jekyll era ---
    # index.html 优先级高于 index.md，必须清理旧文件
    stale_html = pages_path / "index.html"
    if stale_html.exists():
        stale_html.unlink()
        logger.info("Removed stale index.html (conflicts with Jekyll index.md)")

    for sub in pages_path.iterdir():
        if sub.is_dir() and len(sub.name) == 10:
            stale_day_html = sub / "index.html"
            if stale_day_html.exists():
                stale_day_html.unlink()
                logger.info("Removed stale %s/index.html", sub.name)

    # Remove .nojekyll if present (Jekyll must be enabled)
    nojekyll = pages_path / ".nojekyll"
    if nojekyll.exists():
        nojekyll.unlink()
        logger.info("Removed .nojekyll file to enable Jekyll processing")

    # --- Rebuild index page ---
    dates = sorted(
        [d.name for d in pages_path.iterdir() if d.is_dir() and len(d.name) == 10],
        reverse=True,
    )
    index_md = _generate_index_md(dates, site_url)
    (pages_path / "index.md").write_text(index_md, encoding="utf-8")
    logger.info("Generated index page with %d reports", len(dates))

    return pages_path
