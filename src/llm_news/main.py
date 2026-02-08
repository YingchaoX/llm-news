"""Main entry point for LLM News.

Orchestrates the full pipeline:
  1. Load config → 2. Collect → 3. Dedup → 4. LLM process → 5. TTS → 6. Output
"""

import logging
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

from .collectors import (
    arxiv_collector,
    blog_collector,
    github_collector,
    hackernews_collector,
    hf_papers_collector,
    reddit_collector,
    twitter_collector,
)
from .config import AppConfig, Settings, load_config
from .dedup import deduplicate, load_history, save_history
from .models import NewsItem
from .output import save_report
from .pages import build_pages
from .processor import process
from .push import push_report
from .tts import generate_audio

logger = logging.getLogger(__name__)


def _setup_logging() -> None:
    """Configure logging to stdout."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
        handlers=[logging.StreamHandler(sys.stdout)],
    )


def _collect_all(config: AppConfig, settings: Settings) -> list[NewsItem]:
    """Run all collectors in parallel threads.

    Each collector is independent; failures are isolated.
    """
    all_items: list[NewsItem] = []
    keywords = config.keywords
    src = config.sources

    def run_arxiv() -> list[NewsItem]:
        return arxiv_collector.collect(
            categories=src.arxiv.categories,
            max_results=src.arxiv.max_results,
            keywords=keywords,
            require_institution=src.arxiv.require_institution,
        )

    def run_blogs() -> list[NewsItem]:
        return blog_collector.collect(blogs=src.blogs, keywords=keywords)

    def run_github() -> list[NewsItem]:
        return github_collector.collect(
            repos=src.github.repos,
            token=settings.github_token,
            keywords=keywords,
        )

    def run_twitter() -> list[NewsItem]:
        return twitter_collector.collect(
            kol_list=src.twitter.kol_list,
            nitter_instance=src.twitter.nitter_instance,
            keywords=keywords,
            enabled=src.twitter.enabled,
        )

    def run_reddit() -> list[NewsItem]:
        return reddit_collector.collect(
            subreddits=src.reddit.subreddits,
            client_id=settings.reddit_client_id,
            client_secret=settings.reddit_client_secret,
            time_filter=src.reddit.time_filter,
            limit=src.reddit.limit,
            keywords=keywords,
        )

    def run_hf_papers() -> list[NewsItem]:
        if not src.hf_papers.enabled:
            logger.info("HF Papers collector is disabled, skipping")
            return []
        return hf_papers_collector.collect(
            limit=src.hf_papers.limit,
            keywords=keywords,
        )

    def run_hackernews() -> list[NewsItem]:
        if not src.hackernews.enabled:
            logger.info("Hacker News collector is disabled, skipping")
            return []
        return hackernews_collector.collect(
            story_type=src.hackernews.story_type,
            limit=src.hackernews.limit,
            keywords=keywords,
        )

    tasks = {
        "arxiv": run_arxiv,
        "blogs": run_blogs,
        "github": run_github,
        "twitter": run_twitter,
        "reddit": run_reddit,
        "hf_papers": run_hf_papers,
        "hackernews": run_hackernews,
    }

    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(fn): name for name, fn in tasks.items()}
        for future in as_completed(futures):
            name = futures[future]
            try:
                items = future.result()
                all_items.extend(items)
                logger.info("✓ %s: %d items", name, len(items))
            except Exception:
                logger.exception("✗ %s: collector failed", name)

    logger.info("Total collected: %d items", len(all_items))
    return all_items


def run(config_path: str = "config.yaml") -> None:
    """Execute the full LLM News pipeline."""
    _setup_logging()
    logger.info("=" * 60)
    logger.info("LLM News - Daily Report Pipeline")
    logger.info("=" * 60)

    # 1. Load config
    config, settings = load_config(config_path)
    logger.info("Config loaded: model=%s, top_n=%d", config.llm.model, config.llm.top_n)

    # 2. Collect from all sources
    logger.info("--- Phase 1: Collecting ---")
    all_items = _collect_all(config, settings)

    if not all_items:
        logger.warning("No items collected from any source. Exiting.")
        return

    # 3. Deduplicate
    logger.info("--- Phase 2: Deduplicating ---")
    history = load_history()
    items = deduplicate(all_items, history)

    if not items:
        logger.warning("All items are duplicates. Nothing new today.")
        return

    # 4. LLM summarize + rank + generate script
    logger.info("--- Phase 3: Processing with LLM ---")
    report = process(items, config, settings)
    report.total_collected = len(all_items)
    report.total_after_dedup = len(items)

    # LLM 失败时终止流程，不生成半成品报告；下次运行会重新处理这些条目
    if not report.llm_ok:
        logger.error(
            "Pipeline aborted: LLM processing failed. "
            "Items will be re-processed on next run."
        )
        sys.exit(1)

    # 5. Generate audio
    logger.info("--- Phase 4: Generating Audio ---")
    day_dir = save_report(report, output_dir=config.output.dir)

    if report.script:
        audio_path = day_dir / "daily_report.mp3"
        try:
            generate_audio(
                text=report.script,
                output_path=audio_path,
                voice=config.tts.voice,
                rate=config.tts.rate,
            )
        except Exception:
            logger.exception("Audio generation failed")
    else:
        logger.warning("No script generated, skipping audio")

    # 6. Build GitHub Pages (HTML + audio)
    if config.push.enabled and config.push.site_url:
        logger.info("--- Phase 5: Building GitHub Pages ---")
        try:
            build_pages(
                report=report,
                site_url=config.push.site_url,
                output_dir=config.output.dir,
            )
        except Exception:
            logger.exception("GitHub Pages build failed")

    # 7. Bark push notification (iOS)
    if config.push.enabled and config.push.bark_enabled:
        logger.info("--- Phase 6: Sending Bark Push ---")
        try:
            push_report(
                device_key=settings.bark_device_key,
                report_date=report.date,
                top_count=len(report.top_items),
                total_collected=report.total_collected,
                site_url=config.push.site_url,
            )
        except Exception:
            logger.exception("Bark push failed")

    # 8. Update history
    logger.info("--- Phase 7: Updating History ---")
    new_urls = {item.url for item in items}
    save_history(history | new_urls)

    # Done
    logger.info("=" * 60)
    logger.info("Done! Output: %s", day_dir)
    logger.info("  - daily_report.md")
    logger.info("  - daily_report.mp3")
    logger.info("  - raw_items.json")
    logger.info("  - broadcast_script.txt")
    if config.push.enabled:
        logger.info("  - pages/ (GitHub Pages)")
    logger.info("=" * 60)


def cli() -> None:
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="LLM News - Daily AI/LLM news aggregator")
    parser.add_argument(
        "-c", "--config",
        default="config.yaml",
        help="Path to config.yaml (default: config.yaml)",
    )
    args = parser.parse_args()
    run(config_path=args.config)


if __name__ == "__main__":
    cli()
