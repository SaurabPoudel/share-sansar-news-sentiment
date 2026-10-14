"""Tests for Pydantic schema models."""

import json

import pytest
from pydantic import ValidationError

from nepse_sentiment.schemas.models import (
    MarketSentiment,
    PipelineStatus,
    ScrapedArticle,
    ScrapedData,
    SentimentLabel,
    SentimentOutput,
)


class TestSentimentOutput:
    def test_minimal_valid(self):
        output = SentimentOutput(
            generated_at="2024-01-15T16:00:00+05:45",
            market_date="2024-01-15",
        )
        assert output.schema_version == "1.0"
        assert output.status == PipelineStatus.OK
        assert output.disclaimer != ""

    def test_full_valid(self):
        data = {
            "schema_version": "1.0",
            "generated_at": "2024-01-15T16:00:00+05:45",
            "status": "ok",
            "market_date": "2024-01-15",
            "market_summary": {
                "nepse_index": 2100.5,
                "change": 15.3,
                "percent_change": 0.73,
            },
            "market_sentiment": {
                "score": 0.3,
                "label": "bullish",
                "confidence": 0.7,
                "drivers": [],
            },
            "sector_sentiment": [],
            "watchlist": [],
            "caution_list": [],
            "upcoming_events": [],
            "top_news": [],
            "risk_flags": [],
            "learn_today": ["Test insight"],
        }
        output = SentimentOutput.model_validate(data)
        assert output.market_sentiment.score == 0.3

    def test_json_roundtrip(self):
        output = SentimentOutput(
            generated_at="2024-01-15T16:00:00+05:45",
            market_date="2024-01-15",
        )
        json_str = output.model_dump_json()
        parsed = json.loads(json_str)
        restored = SentimentOutput.model_validate(parsed)
        assert restored.schema_version == output.schema_version

    def test_score_out_of_range(self):
        with pytest.raises(ValidationError):
            MarketSentiment(
                score=1.5,  # > 1.0
                label=SentimentLabel.BULLISH,
                confidence=0.5,
            )

    def test_invalid_status(self):
        with pytest.raises(ValidationError):
            SentimentOutput(
                generated_at="2024-01-15T16:00:00+05:45",
                market_date="2024-01-15",
                status="invalid",
            )


class TestScrapedData:
    def test_empty_scraped_data(self):
        data = ScrapedData(scraped_at="2024-01-15T16:00:00+05:45")
        assert data.news_articles == []
        assert data.scrape_errors == []

    def test_with_articles(self):
        data = ScrapedData(
            scraped_at="2024-01-15T16:00:00+05:45",
            news_articles=[
                ScrapedArticle(
                    article_id="test-1",
                    title="Test Article",
                    url="https://example.com/test",
                )
            ],
        )
        assert len(data.news_articles) == 1
