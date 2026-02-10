"""Main entry point for LLM News.

Orchestrates the full pipeline:
  1. Load config → 2. Collect → 3. Dedup → 4. LLM process → 5. TTS → 6. Output
"""

import logging
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

from .collectors import REGISTRY, BaseCollector
from .config import AppConfig, Settings, load_config
from .dedup import deduplicate, extract_canonical_key, load_history, save_history
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


def _build_collectors(config: AppConfig, settings: Settings) -> list[BaseCollector]:
    """Instantiate all enabled collectors from config.

    根据 config 动态实例化所有启用的 collector。
    """
    collectors: list[BaseCollector] = []
    src = config.sources

    # Map config sections to collector init kwargs
    # 将配置映射到 collector 构造参数
    collector_configs: dict[str, dict] = {
        "arxiv": {
            "enabled": src.arxiv.enabled,
            "kwargs": {
                "categories": src.arxiv.categories,
                "max_results": src.arxiv.max_results,
                "require_institution": src.arxiv.require_institution,
            },
        },
        "blog": {
            "enabled": src.blog.enabled,
            "kwargs": {
                "blogs": [
                    {"name": b.name, "url": b.url} for b in src.blog.feeds
                ],
            },
        },
        "github": {
            "enabled": src.github.enabled,
            "kwargs": {
                "repos": src.github.repos,
                "token": settings.github_token,
            },
        },
        "github_trending": {
            "enabled": src.github_trending.enabled,
            "kwargs": {
                "period": src.github_trending.period,
                "language": src.github_trending.language,
                "token": settings.github_token,
            },
        },
        "hf_papers": {
            "enabled": src.hf_papers.enabled,
            "kwargs": {
                "limit": src.hf_papers.limit,
            },
        },
        "hf_models": {
            "enabled": src.hf_models.enabled,
            "kwargs": {
                "orgs": src.hf_models.orgs,
                "limit": src.hf_models.limit,
            },
        },
        "pwc": {
            "enabled": src.pwc.enabled,
            "kwargs": {
                "limit": src.pwc.limit,
            },
        },
        "hackernews": {
            "enabled": src.hackernews.enabled,
            "kwargs": {
                "story_type": src.hackernews.story_type,
                "limit": src.hackernews.limit,
            },
        },
        "reddit": {
            "enabled": src.reddit.enabled,
            "kwargs": {
                "subreddits": src.reddit.subreddits,
                "client_id": settings.reddit_client_id,
                "client_secret": settings.reddit_client_secret,
                "time_filter": src.reddit.time_filter,
                "limit": src.reddit.limit,
            },
        },
    }

    for name, cfg in collector_configs.items():
        if not cfg["enabled"]:
            logger.info("Collector %s is disabled, skipping", name)
            continue

        cls = REGISTRY.get(name)
        if cls is None:
            logger.warning("Unknown collector: %s (not in registry)", name)
            continue

        try:
            collector = cls(**cfg["kwargs"])
            collectors.append(collector)
            logger.debug("Initialized collector: %s", collector)
        except Exception:
            logger.exception("Failed to initialize collector: %s", name)

    return collectors


def _collect_all(config: AppConfig, settings: Settings) -> list[NewsItem]:
    """Run all collectors in parallel threads.

    Each collector is independent; failures are isolated.
    """
    all_items: list[NewsItem] = []
    keywords = config.keywords

    collectors = _build_collectors(config, settings)
    if not collectors:
        logger.warning("No collectors enabled")
        return all_items

    logger.info("Running %d collectors in parallel...", len(collectors))

    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {
            executor.submit(c.collect, keywords): c.name for c in collectors
        }
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

    # 8. Update history (URLs + canonical keys for cross-source dedup)
    # 更新历史记录（URL + 规范 key，支持跨源去重）
    logger.info("--- Phase 7: Updating History ---")
    new_urls = {item.url for item in items}
    new_canon_keys = {
        key for item in items
        if (key := extract_canonical_key(item)) is not None
    }
    save_history({
        "urls": history.get("urls", set()) | new_urls,
        "canonical_keys": history.get("canonical_keys", set()) | new_canon_keys,
    })

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
