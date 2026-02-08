"""GitHub Pages HTML generation module.

生成适合 iPhone 浏览的 HTML 页面，包含：
- 每日报告内容
- 内嵌音频播放器（可在手机上直接听 MP3）
- 响应式移动端布局
- 首页索引（列出所有日期的报告）
"""

import logging
import shutil
from pathlib import Path

from .models import DailyReport

logger = logging.getLogger(__name__)

# GitHub Pages 输出目录 / GitHub Pages output directory
PAGES_DIR = "pages"


def _html_escape(text: str) -> str:
    """Escape HTML special characters."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _generate_report_html(report: DailyReport, site_url: str) -> str:
    """Generate a mobile-friendly HTML page for one day's report.

    Args:
        report: The daily report data.
        site_url: Base URL for GitHub Pages (e.g. https://user.github.io/llm-news).

    Returns:
        Complete HTML string.
    """
    audio_url = f"{site_url.rstrip('/')}/{report.date}/daily_report.mp3"

    items_html = ""
    for i, item in enumerate(report.top_items, 1):
        score_stars = "★" * int(item.score) + "☆" * (10 - int(item.score))
        summary = _html_escape(item.summary or item.content[:200] + "..." if item.content else "")
        published = (
            f'<span class="meta">📅 {item.published_at.strftime("%Y-%m-%d %H:%M UTC")}</span>'
            if item.published_at
            else ""
        )
        items_html += f"""
    <article class="news-item">
      <h2>{i}. {_html_escape(item.title)}</h2>
      <div class="meta-row">
        <span class="meta">📂 {_html_escape(item.source)} / {_html_escape(item.source_name)}</span>
        <span class="meta">⭐ {item.score:.1f}/10 {score_stars}</span>
        {published}
      </div>
      <blockquote>{summary}</blockquote>
      <a href="{_html_escape(item.url)}" target="_blank" rel="noopener">🔗 查看原文</a>
    </article>"""

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>LLM 每日资讯 - {report.date}</title>
  <style>{_get_css()}</style>
</head>
<body>
  <header>
    <h1>🤖 LLM 每日资讯</h1>
    <p class="date">{report.date}</p>
    <p class="stats">共采集 {report.total_collected} 条，去重排序后精选 Top {len(report.top_items)}</p>
  </header>

  <section class="audio-player">
    <h3>🎧 语音播报</h3>
    <audio controls preload="metadata" style="width:100%">
      <source src="{audio_url}" type="audio/mpeg">
      你的浏览器不支持音频播放，请
      <a href="{audio_url}">下载 MP3</a> 收听。
    </audio>
  </section>

  <main>
{items_html}
  </main>

  <footer>
    <a href="{site_url.rstrip('/')}/">← 所有日报</a>
    <p>Powered by <strong>LLM News</strong> · Auto-generated</p>
  </footer>
</body>
</html>"""


def _generate_index_html(dates: list[str], site_url: str) -> str:
    """Generate the index page listing all available reports.

    Args:
        dates: List of date strings (YYYY-MM-DD), sorted descending.
        site_url: Base URL for GitHub Pages.

    Returns:
        Complete HTML string.
    """
    links_html = ""
    for d in dates:
        links_html += f'    <li><a href="{site_url.rstrip("/")}/{d}/">{d}</a></li>\n'

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>LLM 每日资讯</title>
  <style>{_get_css()}</style>
</head>
<body>
  <header>
    <h1>🤖 LLM 每日资讯</h1>
    <p class="stats">每日自动聚合 LLM / AI 领域最新动态</p>
  </header>

  <main>
    <section class="index-list">
      <h2>📅 历史日报</h2>
      <ul>
{links_html}      </ul>
    </section>
  </main>

  <footer>
    <p>Powered by <strong>LLM News</strong> · Auto-generated</p>
  </footer>
</body>
</html>"""


def _get_css() -> str:
    """Return shared CSS styles (mobile-first, dark mode support)."""
    return """
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      line-height: 1.6;
      color: #1a1a1a;
      background: #f8f9fa;
      padding: 16px;
      max-width: 720px;
      margin: 0 auto;
    }
    @media (prefers-color-scheme: dark) {
      body { background: #1a1a2e; color: #e0e0e0; }
      .news-item { background: #16213e; }
      blockquote { background: #0f3460; border-color: #e94560; }
      .audio-player { background: #16213e; }
      a { color: #64b5f6; }
      .index-list li { border-color: #333; }
    }
    header { text-align: center; padding: 20px 0; }
    header h1 { font-size: 1.5em; }
    .date { font-size: 1.2em; color: #666; margin-top: 4px; }
    .stats { font-size: 0.9em; color: #888; margin-top: 4px; }

    .audio-player {
      background: #fff;
      border-radius: 12px;
      padding: 16px;
      margin: 16px 0;
      box-shadow: 0 2px 8px rgba(0,0,0,0.08);
    }
    .audio-player h3 { margin-bottom: 8px; font-size: 1em; }

    .news-item {
      background: #fff;
      border-radius: 12px;
      padding: 16px;
      margin: 12px 0;
      box-shadow: 0 2px 8px rgba(0,0,0,0.08);
    }
    .news-item h2 { font-size: 1.05em; margin-bottom: 8px; }
    .meta-row { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 8px; }
    .meta { font-size: 0.8em; color: #888; }
    blockquote {
      background: #f0f4f8;
      border-left: 3px solid #4a90d9;
      padding: 10px 12px;
      margin: 8px 0;
      border-radius: 4px;
      font-size: 0.9em;
    }
    .news-item a { font-size: 0.85em; color: #4a90d9; text-decoration: none; }
    .news-item a:hover { text-decoration: underline; }

    .index-list ul { list-style: none; padding: 0; }
    .index-list li {
      padding: 12px 0;
      border-bottom: 1px solid #eee;
    }
    .index-list a {
      font-size: 1.1em;
      color: #4a90d9;
      text-decoration: none;
      font-weight: 500;
    }
    .index-list a:hover { text-decoration: underline; }

    footer {
      text-align: center;
      padding: 24px 0;
      font-size: 0.85em;
      color: #888;
    }
    footer a { color: #4a90d9; text-decoration: none; margin-bottom: 8px; display: inline-block; }
"""


def build_pages(
    report: DailyReport,
    site_url: str,
    output_dir: str = "output",
    pages_dir: str = PAGES_DIR,
) -> Path:
    """Build GitHub Pages site with the current report and all historical reports.

    Workflow:
      1. Copy existing pages_dir content (preserve history)
      2. Create/overwrite today's report HTML
      3. Copy today's MP3 audio
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

    # --- Build today's report page ---
    day_pages = pages_path / report.date
    day_pages.mkdir(parents=True, exist_ok=True)

    # Generate HTML
    html = _generate_report_html(report, site_url)
    (day_pages / "index.html").write_text(html, encoding="utf-8")
    logger.info("Generated report page: %s/index.html", day_pages)

    # Copy MP3 if exists
    mp3_src = Path(output_dir) / report.date / "daily_report.mp3"
    if mp3_src.exists():
        shutil.copy2(mp3_src, day_pages / "daily_report.mp3")
        logger.info("Copied audio: %s", day_pages / "daily_report.mp3")
    else:
        logger.warning("MP3 not found: %s, audio player will not work", mp3_src)

    # --- Rebuild index page ---
    # Scan all date directories in pages_dir
    dates = sorted(
        [d.name for d in pages_path.iterdir() if d.is_dir() and len(d.name) == 10],
        reverse=True,
    )
    index_html = _generate_index_html(dates, site_url)
    (pages_path / "index.html").write_text(index_html, encoding="utf-8")
    logger.info("Generated index page with %d reports", len(dates))

    # Add .nojekyll to prevent GitHub Pages from processing with Jekyll
    (pages_path / ".nojekyll").touch()

    return pages_path
