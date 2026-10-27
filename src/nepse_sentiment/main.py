"""Main entry point for the NEPSE sentiment analysis pipeline.

Orchestrates: scrape → analyze → write output.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from nepse_sentiment.analyzer.aggregator import aggregate
from nepse_sentiment.schemas.models import PipelineStatus, SentimentOutput
from nepse_sentiment.scraper.client import HttpClient
from nepse_sentiment.scraper.config import ScraperConfig
from nepse_sentiment.scraper.parsers import (
    build_scraped_data,
    parse_market_summary_page,
    parse_news_page,
    parse_sector_indices,
    parse_top_movers_page,
)
from nepse_sentiment.utils import (
    get_api_dir,
    is_trading_day,
    load_existing_output,
    now_npt,
    setup_logging,
    today_npt,
    write_output_json,
    write_summary_markdown,
)

logger = logging.getLogger(__name__)


def scrape_all(config: ScraperConfig) -> dict:
    """Run all scrapers and return a ScrapedData dict."""
    errors: list[str] = []

    with HttpClient(config) as client:
        # 1. Market summary
        logger.info("Scraping market summary...")
        try:
            html = client.get_page(config.api_endpoints["market_summary"])
            market_summary = parse_market_summary_page(html)
        except Exception as e:
            logger.error("Failed to scrape market summary: %s", e)
            errors.append(f"market_summary: {e}")
            from nepse_sentiment.schemas.models import ScrapedMarketSummary
            market_summary = ScrapedMarketSummary()

        # 2. Top gainers
        logger.info("Scraping top gainers...")
        try:
            html = client.get_page(config.api_endpoints["top_gainers"])
            top_gainers = parse_top_movers_page(html, "gainer")
        except Exception as e:
            logger.error("Failed to scrape top gainers: %s", e)
            errors.append(f"top_gainers: {e}")
            top_gainers = []

        # 3. Top losers
        logger.info("Scraping top losers...")
        try:
            html = client.get_page(config.api_endpoints["top_losers"])
            top_losers = parse_top_movers_page(html, "loser")
        except Exception as e:
            logger.error("Failed to scrape top losers: %s", e)
            errors.append(f"top_losers: {e}")
            top_losers = []

        # 4. Top turnover
        logger.info("Scraping top turnover...")
        try:
            html = client.get_page(config.api_endpoints["top_turnover"])
            top_turnover = parse_top_movers_page(html, "turnover")
        except Exception as e:
            logger.error("Failed to scrape top turnover: %s", e)
            errors.append(f"top_turnover: {e}")
            top_turnover = []

        # 5. Sector indices
        logger.info("Scraping sector indices...")
        try:
            html = client.get_page(config.api_endpoints["indices"])
            sector_indices = parse_sector_indices(html)
        except Exception as e:
            logger.error("Failed to scrape sector indices: %s", e)
            errors.append(f"indices: {e}")
            sector_indices = []

        # 6. News articles (multiple categories)
        logger.info("Scraping news articles...")
        all_articles = []
        seen_urls: set[str] = set()

        # Prioritize news categories from configuration
        for category, path in config.news_pages.items():
            if not path:
                continue
            try:
                html = client.get_page(path)
                articles = parse_news_page(html, config, category)
                for art in articles:
                    if art.url not in seen_urls:
                        seen_urls.add(art.url)
                        all_articles.append(art)
            except Exception as e:
                logger.error("Failed to scrape %s news: %s", category, e)
                errors.append(f"news_{category}: {e}")

    # Build and return
    scraped = build_scraped_data(
        market_summary=market_summary,
        sector_indices=sector_indices,
        top_gainers=top_gainers,
        top_losers=top_losers,
        top_turnover=top_turnover,
        news_articles=all_articles,
        errors=errors,
    )

    logger.info(
        "Scraping complete: %d articles, %d gainers, %d losers, %d errors",
        len(all_articles),
        len(top_gainers),
        len(top_losers),
        len(errors),
    )

    return scraped.model_dump()


def main() -> None:
    """Main pipeline entry point."""
    setup_logging()
    logger.info("=== NEPSE Sentiment Pipeline Starting ===")
    logger.info("Current NPT: %s", now_npt().isoformat())

    api_dir = get_api_dir()

    # Check if it's a trading day
    if not is_trading_day():
        logger.info("Not a trading day (Sat/Sun). Checking for existing data...")
        existing = load_existing_output(api_dir)
        if existing:
            logger.info("Keeping existing output (non-trading day)")
            return

    # Load config
    config = ScraperConfig.load()

    # Step 1: Scrape
    try:
        scraped_data = scrape_all(config)
    except Exception as e:
        logger.error("Scraping failed completely: %s", e)
        # Try to keep existing output as stale
        existing = load_existing_output(api_dir)
        if existing:
            existing["status"] = "stale"
            existing["generated_at"] = now_npt().isoformat()
            write_output_json(existing, api_dir)
            write_summary_markdown(existing, api_dir)
            logger.info("Kept previous output as stale")
        else:
            # Write minimal output
            minimal = SentimentOutput(
                generated_at=now_npt().isoformat(),
                status=PipelineStatus.STALE,
                market_date=today_npt(),
            )
            write_output_json(minimal.model_dump(), api_dir)
            write_summary_markdown(minimal.model_dump(), api_dir)
        return

    # Step 2: Analyze
    try:
        output = aggregate(scraped_data, use_llm=True)
    except Exception as e:
        logger.error("Analysis failed: %s", e)
        output = SentimentOutput(
            generated_at=now_npt().isoformat(),
            status=PipelineStatus.PARTIAL,
            market_date=today_npt(),
        )

    # Step 3: Write output
    output_dict = output.model_dump(mode="json")
    write_output_json(output_dict, api_dir)
    write_summary_markdown(output_dict, api_dir)

    logger.info("=== Pipeline Complete (status=%s) ===", output.status.value)


if __name__ == "__main__":
    main()
