"""Tests for validation script."""

import json

import pytest

from nepse_sentiment.validate import validate


def test_validate_missing_file(tmp_path, monkeypatch):
    monkeypatch.setattr("nepse_sentiment.validate.get_api_dir", lambda: tmp_path)
    assert validate() is False


def test_validate_invalid_json(tmp_path, monkeypatch):
    monkeypatch.setattr("nepse_sentiment.validate.get_api_dir", lambda: tmp_path)
    (tmp_path / "sentiment.json").write_text("invalid json", encoding="utf-8")
    assert validate() is False


def test_validate_valid_file(tmp_path, monkeypatch):
    monkeypatch.setattr("nepse_sentiment.validate.get_api_dir", lambda: tmp_path)
    valid_data = {
        "schema_version": "1.0",
        "generated_at": "2024-01-15T16:00:00+05:45",
        "status": "ok",
        "market_date": "2024-01-15",
        "market_summary": {},
        "market_sentiment": {
            "score": 0.25,
            "label": "bullish",
            "confidence": 0.8,
            "drivers": [],
        },
        "disclaimer": "Automated analysis.",
    }
    (tmp_path / "sentiment.json").write_text(json.dumps(valid_data), encoding="utf-8")
    assert validate() is True
