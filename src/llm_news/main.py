"""Main entry point for LLM News.

Orchestrates the full pipeline:
  1. Load config → 2. Collect → 3. Dedup → 4. LLM process → 5. TTS → 6. Output
"""

import logging
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date

from .collectors import (
    arxiv_collector,
    blog_collector,
    github_collector,
    reddit_collector,
    twitter_collector,
)
from .config import AppConfig, Settings, load_config
from .dedup import deduplicate, load_history, save_history
from .models import NewsItem
from .output import save_report
from .processor import process
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

    tasks = {
        "arxiv": run_arxiv,
        "blogs": run_blogs,
        "github": run_github,
        "twitter": run_twitter,
        "reddit": run_reddit,
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

    # 5. Generate audio
    logger.info("--- Phase 4: Generating Audio ---")
    today = date.today().isoformat()
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

    # 6. Update history
    logger.info("--- Phase 5: Updating History ---")
    new_urls = {item.url for item in items}
    save_history(history | new_urls)

    # Done
    logger.info("=" * 60)
    logger.info("Done! Output: %s", day_dir)
    logger.info("  - daily_report.md")
    logger.info("  - daily_report.mp3")
    logger.info("  - raw_items.json")
    logger.info("  - broadcast_script.txt")
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
