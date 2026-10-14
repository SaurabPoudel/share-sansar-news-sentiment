"""Aggregator: combines scraper output + LLM/fallback analysis into final output."""

from __future__ import annotations

import logging
from typing import Optional

from nepse_sentiment.analyzer.fallback import analyze_fallback
from nepse_sentiment.analyzer.llm import analyze_with_llm
from nepse_sentiment.schemas.models import (
    MarketSummaryOutput,
    PipelineStatus,
    SentimentOutput,
)
from nepse_sentiment.utils import now_npt, today_npt

logger = logging.getLogger(__name__)


def aggregate(
    scraped_data: dict,
    use_llm: bool = True,
) -> SentimentOutput:
    """Produce the final SentimentOutput from scraped data.

    Strategy:
    1. Try LLM analysis (Gemini)
    2. If LLM fails, fall back to rule-based analysis
    3. Merge market data from scraper with analysis results
    """
    analysis: Optional[dict] = None
    analysis_method = "none"

    # Step 1: Try LLM
    if use_llm:
        try:
            analysis = analyze_with_llm(scraped_data)
            if analysis:
                analysis_method = "llm"
                logger.info("Using LLM analysis")
        except Exception as e:
            logger.error("LLM analysis failed: %s", e)

    # Step 2: Fallback to rule-based
    if analysis is None:
        logger.info("Falling back to rule-based analysis")
        analysis = analyze_fallback(scraped_data)
        analysis_method = "rule_based"

    # Step 3: Build output
    ms = scraped_data.get("market_summary") or {}

    # Determine status
    has_articles = len(scraped_data.get("news_articles", [])) > 0
    has_market = (
        ms.get("nepse_index") is not None
        or ms.get("total_turnover") is not None
    )

    if has_articles and has_market:
        status = PipelineStatus.OK
    elif has_articles or has_market:
        status = PipelineStatus.PARTIAL
    else:
        status = PipelineStatus.STALE

    change = ms.get("change") if ms.get("change") is not None else ms.get("nepse_change")
    pct_change = (
        ms.get("percent_change")
        if ms.get("percent_change") is not None
        else ms.get("nepse_percent_change")
    )

    market_summary = MarketSummaryOutput(
        nepse_index=ms.get("nepse_index"),
        change=change,
        percent_change=pct_change,
        total_turnover=ms.get("total_turnover"),
        total_traded_shares=ms.get("total_traded_shares"),
        total_transactions=ms.get("total_transactions"),
        advances=ms.get("advances"),
        declines=ms.get("declines"),
        unchanged=ms.get("unchanged"),
    )

    # Merge analysis into output
    output_data = {
        "schema_version": "1.0",
        "generated_at": now_npt().isoformat(),
        "status": status.value,
        "market_date": ms.get("market_date") or today_npt(),
        "market_summary": market_summary.model_dump(),
        "market_sentiment": analysis.get("market_sentiment", {
            "score": 0.0,
            "label": "neutral",
            "confidence": 0.0,
            "drivers": [],
        }),
        "sector_sentiment": analysis.get("sector_sentiment", []),
        "watchlist": analysis.get("watchlist", []),
        "caution_list": analysis.get("caution_list", []),
        "upcoming_events": analysis.get("upcoming_events", []),
        "top_news": analysis.get("top_news", []),
        "risk_flags": analysis.get("risk_flags", []),
        "learn_today": analysis.get("learn_today", []),
    }

    # Validate by constructing the Pydantic model
    try:
        output = SentimentOutput.model_validate(output_data)
    except Exception as e:
        logger.error("Output validation failed: %s. Using minimal output.", e)
        output = SentimentOutput(
            generated_at=now_npt().isoformat(),
            status=PipelineStatus.PARTIAL,
            market_date=today_npt(),
            market_summary=market_summary,
        )

    logger.info(
        "Aggregation complete: status=%s, method=%s, news=%d, sectors=%d",
        output.status.value,
        analysis_method,
        len(output.top_news),
        len(output.sector_sentiment),
    )

    return output
