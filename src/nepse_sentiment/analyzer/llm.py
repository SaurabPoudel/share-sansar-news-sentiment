"""LLM-based sentiment analysis using Google Gemini.

Uses Gemini 2.0 Flash (free tier: 15 RPM, 1M tokens/day).
Falls back gracefully on rate limits or API errors.
"""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Optional

from pydantic import ValidationError

from nepse_sentiment.schemas.models import (
    CautionItem,
    MarketSentiment,
    RiskFlag,
    SectorSentiment,
    SentimentLabel,
    TopNewsItem,
    UpcomingEvent,
    WatchlistItem,
)
from nepse_sentiment.utils import get_project_root

logger = logging.getLogger(__name__)


def _load_prompt_template(name: str) -> str:
    """Load a prompt template from the prompts/ directory."""
    prompts_dir = get_project_root() / "prompts"
    path = prompts_dir / name
    if path.exists():
        return path.read_text(encoding="utf-8")
    logger.warning("Prompt template not found: %s", path)
    return ""


def _load_few_shot_examples() -> str:
    """Load few-shot examples as formatted text."""
    prompts_dir = get_project_root() / "prompts"
    path = prompts_dir / "few_shot_examples.json"
    if not path.exists():
        return ""

    try:
        examples = json.loads(path.read_text(encoding="utf-8"))
        parts = []
        for ex in examples:
            parts.append(f"Input headline: {ex.get('headline', '')}")
            parts.append(f"Expected output: {json.dumps(ex.get('analysis', {}), indent=2)}")
            parts.append("")
        return "\n".join(parts)
    except Exception as e:
        logger.warning("Failed to load few-shot examples: %s", e)
        return ""


def _prepare_articles_text(articles: list[dict], max_articles: int = 30) -> str:
    """Format articles into a compact text block for the LLM.

    Summarizes each article to stay within token limits.
    """
    lines = []
    for i, art in enumerate(articles[:max_articles], 1):
        title = art.get("title", "")
        category = art.get("category", "")
        url = art.get("url", "")
        summary = art.get("summary", "") or ""
        # Truncate summary to save tokens
        if len(summary) > 200:
            summary = summary[:200] + "..."
        lines.append(
            f"[{i}] [{category}] {title}\n    URL: {url}\n    Summary: {summary}"
        )
    return "\n\n".join(lines)


def _prepare_market_context(scraped_data: dict) -> str:
    """Format market data into context text for the LLM."""
    ms = scraped_data.get("market_summary") or {}
    parts = ["## Market Data"]

    if ms.get("nepse_index"):
        parts.append(f"NEPSE Index: {ms['nepse_index']}")
    if ms.get("nepse_change") is not None:
        parts.append(f"Change: {ms['nepse_change']} ({ms.get('nepse_percent_change', 'N/A')}%)")
    if ms.get("total_turnover"):
        parts.append(f"Total Turnover: Rs. {ms['total_turnover']}")
    if ms.get("advances") is not None:
        parts.append(f"Advances: {ms['advances']}, Declines: {ms.get('declines', 'N/A')}")

    # Top gainers
    gainers = scraped_data.get("top_gainers", [])
    if gainers:
        parts.append("\n## Top Gainers")
        for g in gainers[:10]:
            parts.append(
                f"  {g['symbol']}: LTP={g.get('ltp', 'N/A')}, "
                f"Change={g.get('percent_change', 'N/A')}%"
            )

    # Top losers
    losers = scraped_data.get("top_losers", [])
    if losers:
        parts.append("\n## Top Losers")
        for l in losers[:10]:
            parts.append(
                f"  {l['symbol']}: LTP={l.get('ltp', 'N/A')}, "
                f"Change={l.get('percent_change', 'N/A')}%"
            )

    # Sector indices
    sectors = scraped_data.get("sector_indices", [])
    if sectors:
        parts.append("\n## Sector Indices")
        for s in sectors:
            parts.append(
                f"  {s['sector']}: {s.get('index_value', 'N/A')} "
                f"({s.get('percent_change', 'N/A')}%)"
            )

    return "\n".join(parts)


def _retry_with_error(
    model,
    original_prompt: str,
    error_msg: str,
) -> Optional[dict]:
    """Retry the LLM call once with the error message."""
    logger.info("Retrying Gemini with error feedback")
    retry_prompt = (
        f"{original_prompt}\n\n"
        f"IMPORTANT: Your previous response had this error: {error_msg}\n"
        f"Please respond with ONLY valid JSON, no markdown formatting."
    )
    try:
        response = model.generate_content(retry_prompt)
        raw_text = response.text
        try:
            result = json.loads(raw_text)
        except json.JSONDecodeError:
            json_match = re.search(r'```json\s*(.*?)\s*```', raw_text, re.DOTALL)
            if json_match:
                result = json.loads(json_match.group(1))
            else:
                raise
        logger.info("Retry succeeded")
        return result
    except Exception as e:
        logger.error("Retry also failed: %s", e)
        return None


def analyze_with_llm(scraped_data: dict) -> Optional[dict]:
    """Run sentiment analysis using Google Gemini.

    Returns a dict matching the analysis portion of SentimentOutput,
    or None if the LLM call fails.
    """
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        logger.warning("GEMINI_API_KEY not set, skipping LLM analysis")
        return None

    try:
        import google.generativeai as genai
    except ImportError:
        logger.warning("google-generativeai not installed")
        return None

    # Configure Gemini
    genai.configure(api_key=api_key)

    # Load prompts
    system_prompt = _load_prompt_template("system.md")
    analysis_prompt = _load_prompt_template("analysis.md")
    few_shot = _load_few_shot_examples()

    # Prepare context
    market_context = _prepare_market_context(scraped_data)
    articles_text = _prepare_articles_text(
        scraped_data.get("news_articles", [])
    )

    # Build the full prompt
    user_prompt = analysis_prompt.format(
        market_context=market_context,
        articles=articles_text,
        few_shot_examples=few_shot,
        scrape_errors=json.dumps(scraped_data.get("scrape_errors", [])),
    )

    # Call Gemini
    model = genai.GenerativeModel(
        model_name="gemini-2.0-flash",
        system_instruction=system_prompt,
        generation_config=genai.GenerationConfig(
            temperature=0.1,
            top_p=0.95,
            response_mime_type="application/json",
        ),
    )

    try:
        response = model.generate_content(user_prompt)
        raw_text = response.text
        logger.info("Gemini response length: %d chars", len(raw_text))
    except Exception as e:
        logger.error("Gemini API call failed: %s", e)
        return None

    # Parse the JSON response
    try:
        result = json.loads(raw_text)
    except json.JSONDecodeError:
        # Try to extract JSON from markdown code blocks
        json_match = re.search(r'```json\s*(.*?)\s*```', raw_text, re.DOTALL)
        if json_match:
            try:
                result = json.loads(json_match.group(1))
            except json.JSONDecodeError as e:
                logger.error("Failed to parse Gemini JSON response: %s", e)
                # Retry once with error feedback
                return _retry_with_error(model, user_prompt, str(e))
        else:
            logger.error("No JSON found in Gemini response")
            return _retry_with_error(model, user_prompt, "Response was not valid JSON")

    logger.info("LLM analysis complete, keys: %s", list(result.keys()))
    return result
