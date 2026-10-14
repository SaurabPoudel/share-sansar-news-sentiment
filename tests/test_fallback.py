"""Tests for the rule-based fallback sentiment analyzer."""

import pytest

from nepse_sentiment.analyzer.fallback import (
    _detect_events,
    _detect_sector,
    _score_text,
    _score_to_label,
    analyze_fallback,
)
from nepse_sentiment.schemas.models import SentimentLabel


class TestScoreText:
    def test_bullish_headline(self):
        score = _score_text("NEPSE surges 30 points, strong gains across banking sector")
        assert score > 0

    def test_bearish_headline(self):
        score = _score_text("Market crashes amid panic selling and liquidity crunch")
        assert score < 0

    def test_neutral_headline(self):
        score = _score_text("SEBON publishes annual report")
        assert -0.3 <= score <= 0.3

    def test_nepali_headline(self):
        score = _score_text("शेयर बजार स्थिर, कारोबार रकम सामान्य")
        # Should be close to neutral since no strong keywords
        assert -0.5 <= score <= 0.5

    def test_mixed_language(self):
        score = _score_text("नबिल बैंकले profit बढाउँदै dividend दिने")
        assert score > 0  # "profit" and "dividend" are bullish


class TestScoreToLabel:
    def test_bullish(self):
        assert _score_to_label(0.5) == SentimentLabel.BULLISH

    def test_bearish(self):
        assert _score_to_label(-0.5) == SentimentLabel.BEARISH

    def test_neutral(self):
        assert _score_to_label(0.0) == SentimentLabel.NEUTRAL

    def test_boundary_positive(self):
        assert _score_to_label(0.15) == SentimentLabel.NEUTRAL

    def test_boundary_negative(self):
        assert _score_to_label(-0.15) == SentimentLabel.NEUTRAL


class TestDetectEvents:
    def test_dividend(self):
        events = _detect_events("Nabil Bank announces 18% cash dividend")
        assert "dividend" in events

    def test_ipo(self):
        events = _detect_events("SEBON approves IPO of Himalayan Power")
        assert "ipo" in events

    def test_bonus(self):
        events = _detect_events("Company declares 10% bonus share")
        assert "bonus" in events

    def test_agm(self):
        events = _detect_events("Annual General Meeting scheduled for next week")
        assert "agm" in events

    def test_merger(self):
        events = _detect_events("Two development banks to merge")
        assert "merger" in events

    def test_regulatory(self):
        events = _detect_events("NRB introduces new CRR policy")
        assert "regulatory" in events

    def test_circuit(self):
        events = _detect_events("Stock hits upper circuit limit")
        assert "circuit_hit" in events

    def test_no_events(self):
        events = _detect_events("Weather forecast for Kathmandu")
        assert len(events) == 0


class TestDetectSector:
    def test_banking(self):
        assert _detect_sector("Nabil Bank reports strong earnings") == "commercial_banks"

    def test_hydropower(self):
        assert _detect_sector("New hydropower project approved") == "hydropower"

    def test_insurance(self):
        assert _detect_sector("Insurance premium collection rises") == "insurance"

    def test_microfinance(self):
        assert _detect_sector("Laghubitta companies expand operations") == "microfinance"

    def test_unknown(self):
        assert _detect_sector("General election date announced") is None


class TestAnalyzeFallback:
    def test_produces_valid_structure(self):
        scraped = {
            "market_summary": {
                "nepse_index": 2100.5,
                "nepse_change": 15.3,
                "nepse_percent_change": 0.73,
                "advances": 150,
                "declines": 80,
                "total_turnover": 3500000000,
            },
            "top_gainers": [
                {"symbol": "NABIL", "ltp": 1200, "percent_change": 5.0},
            ],
            "top_losers": [
                {"symbol": "CHCL", "ltp": 500, "percent_change": -4.0},
            ],
            "sector_indices": [],
            "news_articles": [
                {
                    "title": "Banking sector shows strong growth",
                    "url": "https://sharesansar.com/news/banking-growth",
                    "summary": "Banks report increased profit margins",
                    "category": "market",
                },
                {
                    "title": "NRB tightens lending policy",
                    "url": "https://sharesansar.com/news/nrb-policy",
                    "summary": "New regulations may affect bank margins",
                    "category": "market",
                },
            ],
            "scrape_errors": [],
        }

        result = analyze_fallback(scraped)

        assert "market_sentiment" in result
        assert "sector_sentiment" in result
        assert "watchlist" in result
        assert "caution_list" in result
        assert "top_news" in result
        assert "risk_flags" in result
        assert "learn_today" in result

        ms = result["market_sentiment"]
        assert -1.0 <= ms["score"] <= 1.0
        assert ms["label"] in ("bullish", "neutral", "bearish")
        assert 0.0 <= ms["confidence"] <= 1.0

    def test_empty_data(self):
        result = analyze_fallback({
            "market_summary": {},
            "top_gainers": [],
            "top_losers": [],
            "sector_indices": [],
            "news_articles": [],
            "scrape_errors": [],
        })
        assert result["market_sentiment"]["score"] == 0.0
        assert result["market_sentiment"]["label"] == "neutral"
