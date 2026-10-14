"""Scraper configuration loader.

Loads CSS selectors and URLs from selectors.yaml.
Isolates site-specific details so layout changes are easy to fix.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)


@dataclass
class RateLimitConfig:
    """Rate limiting configuration for polite web scraping."""
    requests_per_second: float = 1.0
    retry_max: int = 3
    retry_backoff_factor: float = 2.0
    timeout_seconds: int = 30


@dataclass
class ScraperConfig:
    """Complete scraper configuration loaded from selectors.yaml."""
    base_url: str = "https://www.sharesansar.com"
    user_agent: str = (
        "NepseSentimentBot/1.0 "
        "(Educational; github.com/SaurabPoudel/share-sansar-news-scrapper)"
    )
    rate_limit: RateLimitConfig = field(default_factory=RateLimitConfig)
    
    # API endpoints (relative paths)
    api_endpoints: dict[str, str] = field(default_factory=lambda: {
        "today_price": "/today-share-price",
        "market_summary": "/market-summary",
        "top_gainers": "/top-gainers",
        "top_losers": "/top-losers",
        "top_turnover": "/top-turnover",
        "indices": "/live-index",
    })
    
    # News page paths
    news_pages: dict[str, str] = field(default_factory=lambda: {
        "latest": "/category/latest",
        "market": "/category/market",
        "ipo_fpo": "/category/ipo-fpo",
        "dividend": "/category/dividend",
        "bonus": "/category/bonus-share",
        "right_share": "/category/right-share",
    })
    
    # CSS selectors for news
    news_selectors: dict[str, str] = field(default_factory=lambda: {
        "article_item": "div.featured-news-list div.media, div.news-list div.media",
        "article_title": "h4.media-heading a, h3.media-heading a",
        "article_link": "h4.media-heading a, h3.media-heading a",
        "article_date": "span.text-muted, small.text-muted",
        "article_summary": "p",
    })
    
    # Fallback sources
    fallback_sources: dict[str, str] = field(default_factory=lambda: {
        "nepse_api": "https://nepalstock.com/api",
        "merolagani": "https://merolagani.com",
    })
    
    @classmethod
    def load(cls, config_path: Path | None = None) -> ScraperConfig:
        """Load configuration from selectors.yaml."""
        if config_path is None:
            # Look in project root
            from nepse_sentiment.utils import get_project_root
            config_path = get_project_root() / "selectors.yaml"
        
        if not config_path.exists():
            logger.warning(
                "selectors.yaml not found at %s, using defaults", config_path
            )
            return cls()
        
        try:
            raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning("Failed to parse selectors.yaml: %s", e)
            return cls()
        
        if not isinstance(raw, dict):
            return cls()
        
        rate_cfg = raw.get("rate_limit", {})
        rate_limit = RateLimitConfig(
            requests_per_second=rate_cfg.get("requests_per_second", 1.0),
            retry_max=rate_cfg.get("retry_max", 3),
            retry_backoff_factor=rate_cfg.get("retry_backoff_factor", 2.0),
            timeout_seconds=rate_cfg.get("timeout_seconds", 30),
        )
        
        default = cls()
        return cls(
            base_url=raw.get("base_url", default.base_url),
            user_agent=raw.get("user_agent", default.user_agent),
            rate_limit=rate_limit,
            api_endpoints=raw.get("api_endpoints", default.api_endpoints),
            news_pages=raw.get("news_pages", default.news_pages),
            news_selectors=raw.get("news_selectors", default.news_selectors),
            fallback_sources=raw.get("fallback_sources", default.fallback_sources),
        )
