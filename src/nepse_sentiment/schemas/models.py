"""Pydantic models for scraped data and analysis output.

Two model families:
- Scraped*: intermediate representations from the scraper
- Sentiment*: the final published JSON schema (api/sentiment.json)
"""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator


# ── Enums ──────────────────────────────────────────────────────────────

class SentimentLabel(str, Enum):
    BULLISH = "bullish"
    NEUTRAL = "neutral"
    BEARISH = "bearish"


class PipelineStatus(str, Enum):
    OK = "ok"
    STALE = "stale"
    PARTIAL = "partial"


class EventType(str, Enum):
    DIVIDEND = "dividend"
    BONUS = "bonus"
    RIGHT_SHARE = "right_share"
    IPO = "ipo"
    FPO = "fpo"
    AUCTION = "auction"
    MERGER = "merger"
    BOOK_CLOSE = "book_close"
    AGM = "agm"
    EARNINGS = "earnings"
    REGULATORY = "regulatory"
    PROMOTER_SELLING = "promoter_selling"
    CIRCUIT_HIT = "circuit_hit"


# ── Scraper Models (intermediate) ──────────────────────────────────────

class ScrapedArticle(BaseModel):
    """A single news article scraped from ShareSansar."""
    article_id: str = Field(description="Unique ID derived from URL slug")
    title: str
    url: str
    published_at: Optional[str] = None
    category: Optional[str] = None
    summary: Optional[str] = None
    content_snippet: Optional[str] = Field(
        None, description="First ~500 chars of article body"
    )


class ScrapedTopMover(BaseModel):
    """A top gainer, loser, or turnover leader."""
    symbol: str
    company_name: Optional[str] = None
    ltp: Optional[float] = Field(None, description="Last traded price")
    change: Optional[float] = None
    percent_change: Optional[float] = None
    volume: Optional[int] = None
    turnover: Optional[float] = None


class ScrapedMarketSummary(BaseModel):
    """Market-level summary data."""
    market_date: Optional[str] = None
    nepse_index: Optional[float] = None
    nepse_change: Optional[float] = None
    nepse_percent_change: Optional[float] = None
    total_turnover: Optional[float] = None
    total_traded_shares: Optional[int] = None
    total_transactions: Optional[int] = None
    total_scrips_traded: Optional[int] = None
    advances: Optional[int] = None
    declines: Optional[int] = None
    unchanged: Optional[int] = None
    market_capitalization: Optional[float] = None


class ScrapedSectorIndex(BaseModel):
    """Sector sub-index data."""
    sector: str
    index_value: Optional[float] = None
    change: Optional[float] = None
    percent_change: Optional[float] = None


class ScrapedData(BaseModel):
    """Complete scraped data bundle passed to the analyzer."""
    scraped_at: str = Field(description="ISO-8601 timestamp")
    market_summary: Optional[ScrapedMarketSummary] = None
    sector_indices: list[ScrapedSectorIndex] = Field(default_factory=list)
    top_gainers: list[ScrapedTopMover] = Field(default_factory=list)
    top_losers: list[ScrapedTopMover] = Field(default_factory=list)
    top_turnover: list[ScrapedTopMover] = Field(default_factory=list)
    news_articles: list[ScrapedArticle] = Field(default_factory=list)
    scrape_errors: list[str] = Field(
        default_factory=list,
        description="Non-fatal errors encountered during scraping",
    )


# ── Output Models (api/sentiment.json) ─────────────────────────────────

class MarketSummaryOutput(BaseModel):
    """Market summary in the published JSON."""
    nepse_index: Optional[float] = None
    change: Optional[float] = None
    percent_change: Optional[float] = None
    total_turnover: Optional[float] = None
    total_traded_shares: Optional[int] = None
    total_transactions: Optional[int] = None
    advances: Optional[int] = None
    declines: Optional[int] = None
    unchanged: Optional[int] = None


class SentimentDriver(BaseModel):
    """A factor driving market sentiment."""
    factor: str = Field(description="e.g. 'liquidity', 'nrb_policy'")
    impact: str = Field(description="'positive', 'negative', 'neutral'")
    detail: str


class MarketSentiment(BaseModel):
    """Overall market sentiment assessment."""
    score: float = Field(ge=-1.0, le=1.0)
    label: SentimentLabel
    confidence: float = Field(ge=0.0, le=1.0)
    drivers: list[SentimentDriver] = Field(default_factory=list)


class SectorSentiment(BaseModel):
    """Sentiment for a single NEPSE sector."""
    sector: str
    score: float = Field(ge=-1.0, le=1.0)
    label: SentimentLabel
    reasons: list[str] = Field(default_factory=list)


class WatchlistItem(BaseModel):
    """A stock worth researching further."""
    symbol: str
    reason: str
    sentiment: SentimentLabel
    tags: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)


class CautionItem(BaseModel):
    """A stock with elevated risk signals."""
    symbol: str
    reason: str
    risk_tags: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)


class UpcomingEvent(BaseModel):
    """An upcoming corporate event in the next 14 days."""
    symbol: Optional[str] = None
    event_type: str
    date: Optional[str] = None
    details: str


class TopNewsItem(BaseModel):
    """A significant news item with sentiment."""
    title: str
    url: str
    published_at: Optional[str] = None
    sentiment: SentimentLabel
    importance: str = Field(description="'high', 'medium', 'low'")
    summary: str


class RiskFlag(BaseModel):
    """A risk signal detected in today's data."""
    flag_type: str
    description: str
    symbols: list[str] = Field(default_factory=list)


class SentimentOutput(BaseModel):
    """The complete published JSON schema — api/sentiment.json.
    
    This is the contract consumers depend on. Bump schema_version
    on any breaking change.
    """
    schema_version: str = "1.0"
    generated_at: str = Field(description="ISO-8601 in NPT")
    status: PipelineStatus = PipelineStatus.OK
    market_date: str = Field(description="YYYY-MM-DD")
    market_summary: MarketSummaryOutput = Field(
        default_factory=MarketSummaryOutput
    )
    market_sentiment: MarketSentiment = Field(
        default_factory=lambda: MarketSentiment(
            score=0.0, label=SentimentLabel.NEUTRAL, confidence=0.0
        )
    )
    sector_sentiment: list[SectorSentiment] = Field(default_factory=list)
    watchlist: list[WatchlistItem] = Field(default_factory=list)
    caution_list: list[CautionItem] = Field(default_factory=list)
    upcoming_events: list[UpcomingEvent] = Field(default_factory=list)
    top_news: list[TopNewsItem] = Field(default_factory=list)
    risk_flags: list[RiskFlag] = Field(default_factory=list)
    learn_today: list[str] = Field(
        default_factory=list,
        description="Educational insights for retail investors",
    )
    disclaimer: str = (
        "This is automated analysis for educational and informational purposes only. "
        "It is NOT financial advice. NEPSE investing carries significant risk including "
        "possible loss of principal. Always do your own research (DYOR) and consult a "
        "licensed financial advisor before making investment decisions. Past performance "
        "does not guarantee future results."
    )
