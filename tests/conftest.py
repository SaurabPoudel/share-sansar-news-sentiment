"""Shared pytest fixtures."""

import json
from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES_DIR


@pytest.fixture
def sample_news_html(fixtures_dir: Path) -> str:
    return (fixtures_dir / "news_page.html").read_text(encoding="utf-8")


@pytest.fixture
def sample_market_html(fixtures_dir: Path) -> str:
    return (fixtures_dir / "market_page.html").read_text(encoding="utf-8")
