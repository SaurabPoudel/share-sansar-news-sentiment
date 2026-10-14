"""Tests for analyzer module (LLM and Aggregator)."""

import json
from unittest.mock import MagicMock, patch

import pytest

from nepse_sentiment.analyzer.aggregator import aggregate
from nepse_sentiment.analyzer.llm import (
    _load_few_shot_examples,
    _load_prompt_template,
    _prepare_articles_text,
    _prepare_market_context,
    _retry_with_error,
    analyze_with_llm,
)
from nepse_sentiment.schemas.models import PipelineStatus, SentimentOutput


class TestPromptHelpers:
    def test_load_system_prompt(self):
        prompt = _load_prompt_template("system.md")
        assert "NEPSE" in prompt
        assert "equity analyst" in prompt

    def test_load_analysis_prompt(self):
        prompt = _load_prompt_template("analysis.md")
        assert "market_sentiment" in prompt
        assert "{market_context}" in prompt

    def test_load_nonexistent_prompt(self):
        prompt = _load_prompt_template("nonexistent_file.md")
        assert prompt == ""

    def test_load_few_shot_examples(self):
        examples = _load_few_shot_examples()
        assert "Input headline:" in examples
        assert "Expected output:" in examples


class TestContextHelpers:
    def test_prepare_articles_text(self):
        articles = [
            {
                "title": "Nabil Bank dividend",
                "category": "dividend",
                "url": "https://sharesansar.com/news/1",
                "summary": "Nabil declared dividend " * 20,
            }
        ]
        text = _prepare_articles_text(articles)
        assert "[1] [dividend] Nabil Bank dividend" in text
        assert "..." in text  # truncated summary

    def test_prepare_market_context(self):
        data = {
            "market_summary": {
                "nepse_index": 2100.5,
                "nepse_change": 10.5,
                "nepse_percent_change": 0.5,
                "total_turnover": 3000000000,
                "advances": 140,
                "declines": 90,
            },
            "top_gainers": [
                {"symbol": "NABIL", "ltp": 1200, "percent_change": 4.5}
            ],
            "top_losers": [
                {"symbol": "HDL", "ltp": 1500, "percent_change": -3.2}
            ],
            "sector_indices": [
                {"sector": "Banking", "index_value": 1400.0, "percent_change": 1.2}
            ],
        }
        context = _prepare_market_context(data)
        assert "NEPSE Index: 2100.5" in context
        assert "Total Turnover: Rs. 3000000000" in context
        assert "NABIL" in context
        assert "HDL" in context
        assert "Banking: 1400.0" in context


class TestLlmAnalyze:
    def test_no_api_key_returns_none(self, monkeypatch):
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        result = analyze_with_llm({})
        assert result is None

    def test_retry_with_error_success(self):
        mock_model = MagicMock()
        mock_response = MagicMock()
        mock_response.text = json.dumps({"market_sentiment": {"score": 0.5}})
        mock_model.generate_content.return_value = mock_response

        res = _retry_with_error(mock_model, "Original prompt", "JSON decode error")
        assert res == {"market_sentiment": {"score": 0.5}}

    def test_retry_with_error_markdown_json(self):
        mock_model = MagicMock()
        mock_response = MagicMock()
        mock_response.text = "```json\n{\"market_sentiment\": {\"score\": 0.2}}\n```"
        mock_model.generate_content.return_value = mock_response

        res = _retry_with_error(mock_model, "Original prompt", "JSON decode error")
        assert res == {"market_sentiment": {"score": 0.2}}

    def test_retry_with_error_failure(self):
        mock_model = MagicMock()
        mock_model.generate_content.side_effect = RuntimeError("API failed")

        res = _retry_with_error(mock_model, "Original prompt", "JSON decode error")
        assert res is None


class TestAggregator:
    def test_aggregate_fallback_ok_status(self):
        scraped_data = {
            "market_summary": {
                "nepse_index": 2100.0,
                "nepse_change": 10.0,
                "nepse_percent_change": 0.48,
                "total_turnover": 2500000000,
                "advances": 120,
                "declines": 100,
            },
            "news_articles": [
                {
                    "title": "Commercial banks report profit growth",
                    "url": "https://sharesansar.com/news/cb-profit",
                    "category": "market",
                    "summary": "Profit increased",
                }
            ],
            "top_gainers": [],
            "top_losers": [],
            "sector_indices": [],
            "scrape_errors": [],
        }

        output = aggregate(scraped_data, use_llm=False)
        assert isinstance(output, SentimentOutput)
        assert output.status == PipelineStatus.OK
        assert output.market_summary.nepse_index == 2100.0
        assert output.market_summary.change == 10.0
        assert len(output.top_news) == 1
        assert output.market_sentiment.label in ("bullish", "neutral", "bearish")

    def test_aggregate_partial_status(self):
        scraped_data = {
            "market_summary": {},
            "news_articles": [
                {
                    "title": "Some article",
                    "url": "https://sharesansar.com/news/sample",
                    "category": "latest",
                }
            ],
        }
        output = aggregate(scraped_data, use_llm=False)
        assert output.status == PipelineStatus.PARTIAL

    def test_aggregate_stale_status(self):
        scraped_data = {
            "market_summary": {},
            "news_articles": [],
        }
        output = aggregate(scraped_data, use_llm=False)
        assert output.status == PipelineStatus.STALE

    def test_aggregate_with_successful_llm(self):
        scraped_data = {
            "market_summary": {
                "nepse_index": 2100.0,
                "nepse_change": 5.0,
                "nepse_percent_change": 0.24,
            },
            "news_articles": [
                {"title": "Headline", "url": "https://example.com/1"}
            ],
        }
        mock_llm_result = {
            "market_sentiment": {
                "score": 0.4,
                "label": "bullish",
                "confidence": 0.85,
                "drivers": [{"factor": "liquidity", "impact": "positive", "detail": "High liquidity"}],
            },
            "sector_sentiment": [
                {"sector": "Banking", "score": 0.5, "label": "bullish", "reasons": ["Good earnings"]}
            ],
            "watchlist": [
                {"symbol": "NABIL", "reason": "Good earnings", "sentiment": "bullish", "tags": ["dividend"], "sources": ["https://example.com/1"]}
            ],
            "caution_list": [],
            "upcoming_events": [],
            "top_news": [
                {"title": "Headline", "url": "https://example.com/1", "sentiment": "bullish", "importance": "high", "summary": "Headline summary"}
            ],
            "risk_flags": [],
            "learn_today": ["Insight 1"],
        }

        with patch("nepse_sentiment.analyzer.aggregator.analyze_with_llm", return_value=mock_llm_result):
            output = aggregate(scraped_data, use_llm=True)
            assert output.market_sentiment.score == 0.4
            assert output.market_sentiment.label.value == "bullish"
            assert len(output.watchlist) == 1
            assert output.watchlist[0].symbol == "NABIL"
