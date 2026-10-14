"""Tests for main pipeline entry point."""

import json
from unittest.mock import MagicMock, patch

import pytest

from nepse_sentiment.main import main, scrape_all
from nepse_sentiment.schemas.models import PipelineStatus, ScrapedData, SentimentOutput


class TestMainPipeline:
    def test_non_trading_day_with_existing(self, tmp_path, monkeypatch):
        monkeypatch.setattr("nepse_sentiment.main.is_trading_day", lambda: False)
        monkeypatch.setattr("nepse_sentiment.main.get_api_dir", lambda: tmp_path)
        
        sample_output = {"schema_version": "1.0", "status": "ok", "market_date": "2024-01-14"}
        sentiment_path = tmp_path / "sentiment.json"
        sentiment_path.write_text(json.dumps(sample_output), encoding="utf-8")
        
        # Should return early without scraping
        with patch("nepse_sentiment.main.scrape_all") as mock_scrape:
            main()
            mock_scrape.assert_not_called()

    def test_trading_day_full_run(self, tmp_path, monkeypatch):
        monkeypatch.setattr("nepse_sentiment.main.is_trading_day", lambda: True)
        monkeypatch.setattr("nepse_sentiment.main.get_api_dir", lambda: tmp_path)

        mock_scraped = {
            "scraped_at": "2024-01-15T16:00:00+05:45",
            "market_summary": {
                "nepse_index": 2100.0,
                "nepse_change": 12.0,
                "nepse_percent_change": 0.57,
                "total_turnover": 4000000000,
                "advances": 140,
                "declines": 80,
            },
            "news_articles": [
                {
                    "title": "Nabil Bank dividend declared",
                    "url": "https://sharesansar.com/news/nabil-div",
                    "summary": "18% dividend announced",
                    "category": "dividend",
                }
            ],
            "top_gainers": [],
            "top_losers": [],
            "top_turnover": [],
            "sector_indices": [],
            "scrape_errors": [],
        }

        with patch("nepse_sentiment.main.scrape_all", return_value=mock_scraped):
            main()

        assert (tmp_path / "sentiment.json").exists()
        assert (tmp_path / "latest-summary.md").exists()
        
        output_data = json.loads((tmp_path / "sentiment.json").read_text(encoding="utf-8"))
        assert output_data["status"] == "ok"
        assert output_data["market_summary"]["nepse_index"] == 2100.0

    def test_scraping_failure_stale_fallback(self, tmp_path, monkeypatch):
        monkeypatch.setattr("nepse_sentiment.main.is_trading_day", lambda: True)
        monkeypatch.setattr("nepse_sentiment.main.get_api_dir", lambda: tmp_path)

        with patch("nepse_sentiment.main.scrape_all", side_effect=RuntimeError("Network down")):
            main()

        assert (tmp_path / "sentiment.json").exists()
        output_data = json.loads((tmp_path / "sentiment.json").read_text(encoding="utf-8"))
        assert output_data["status"] == "stale"
