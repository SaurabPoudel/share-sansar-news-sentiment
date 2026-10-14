"""Rule-based fallback sentiment analysis.

Used when the LLM API is unavailable, rate-limited, or returns invalid data.
Uses keyword matching, simple heuristics, and market data signals.
"""

from __future__ import annotations

import logging
import re
from collections import defaultdict
from typing import Optional

from nepse_sentiment.schemas.models import (
    CautionItem,
    MarketSentiment,
    RiskFlag,
    SectorSentiment,
    SentimentDriver,
    SentimentLabel,
    TopNewsItem,
    UpcomingEvent,
    WatchlistItem,
)

logger = logging.getLogger(__name__)

# ── Keyword Dictionaries (NEPSE-specific) ──────────────────────────────

BULLISH_KEYWORDS = {
    # English
    "profit", "profits", "growth", "surge", "surges", "rally", "bullish",
    "gain", "gains", "rise", "rises", "rising", "increase", "increased",
    "positive", "recovery", "recover", "boom", "uptrend", "breakout",
    "dividend", "bonus", "earnings", "strong", "highest", "record",
    "liquidity", "inflow", "expansion", "merger", "acquisition",
    "ipo allotment", "right share", "optimistic", "bullish",
    "advance", "advances", "green", "up",
    # NEPSE-specific
    "nepse up", "index gains", "turnover increase",
    # Nepali (transliterated)
    "munafa", "laabh", "bridhi", "badyo",
}

BEARISH_KEYWORDS = {
    # English
    "loss", "losses", "decline", "declines", "fall", "falls", "falling",
    "drop", "drops", "crash", "bearish", "negative", "down", "downturn",
    "sell", "selling", "selloff", "panic", "fear", "correction",
    "circuit", "lower circuit", "frozen", "npl", "default",
    "regulatory action", "penalty", "fine", "suspend", "suspended",
    "delisted", "warning", "risk", "outflow", "tight", "crunch",
    "decrease", "decreased", "weak", "lowest", "plunge",
    # NEPSE-specific
    "nepse down", "index falls", "turnover decrease",
    "margin call", "forced selling",
    # Nepali (transliterated)
    "nuksan", "ghatyo", "khasyo",
}

# Event detection patterns
EVENT_PATTERNS = {
    "dividend": re.compile(
        r"\b(dividend|cash dividend|bonus share|naghad laabhansh)\b", re.I
    ),
    "bonus": re.compile(r"\b(bonus share|bonus|bonash)\b", re.I),
    "right_share": re.compile(r"\b(right share|right offering|hak praad)\b", re.I),
    "ipo": re.compile(r"\b(ipo|initial public offering|primary offering)\b", re.I),
    "fpo": re.compile(r"\b(fpo|further public offering)\b", re.I),
    "agm": re.compile(r"\b(agm|annual general meeting|sadharan sabha)\b", re.I),
    "book_close": re.compile(r"\b(book close|book closure|kitab bandh)\b", re.I),
    "merger": re.compile(
        r"\b(merger|merge|merged|merging|merg|acquisition|gosar|gosbara)\b", re.I
    ),
    "auction": re.compile(r"\b(auction|lilami)\b", re.I),
    "earnings": re.compile(
        r"\b(quarterly result|q[1-4] result|profit.*report|earnings|net profit)\b", re.I
    ),
    "regulatory": re.compile(
        r"\b(nrb|nepal rastra bank|sebon|regulatory|policy|ccd ratio|crr|slr"
        r"|monetary policy|base rate|margin|lending)\b", re.I
    ),
    "circuit_hit": re.compile(
        r"\b(circuit|upper circuit|lower circuit|circuit limit|frozen)\b", re.I
    ),
}

# NEPSE sector keywords for classification
SECTOR_KEYWORDS = {
    "commercial_banks": ["bank", "banking", "nabil", "nic asia", "global ime", "himalayan bank", "everest bank"],
    "development_banks": ["development bank", "bikas bank", "bikash bank"],
    "finance": ["finance", "merchant"],
    "microfinance": ["microfinance", "laghubitta", "micro"],
    "hydropower": ["hydro", "hydropower", "power", "energy", "electricity", "jalbidhyut"],
    "insurance": ["insurance", "bima"],
    "life_insurance": ["life insurance", "jeevan bima"],
    "hotels": ["hotel", "tourism", "resort"],
    "manufacturing": ["cement", "steel", "manufacturing", "factory", "udhyog"],
    "trading": ["trading", "byapar"],
    "investment": ["investment", "fund", "capital", "mutual fund"],
}


def _score_text(text: str) -> float:
    """Score a text snippet from -1 (bearish) to +1 (bullish)."""
    text_lower = text.lower()

    bull_count = sum(1 for kw in BULLISH_KEYWORDS if kw in text_lower)
    bear_count = sum(1 for kw in BEARISH_KEYWORDS if kw in text_lower)

    total = bull_count + bear_count
    if total == 0:
        return 0.0

    raw_score = (bull_count - bear_count) / total
    return max(-1.0, min(1.0, raw_score))


def _score_to_label(score: float) -> SentimentLabel:
    """Convert a numeric score to a sentiment label."""
    if score > 0.15:
        return SentimentLabel.BULLISH
    elif score < -0.15:
        return SentimentLabel.BEARISH
    return SentimentLabel.NEUTRAL


def _detect_events(text: str) -> list[str]:
    """Detect NEPSE event types mentioned in text."""
    events = []
    for event_type, pattern in EVENT_PATTERNS.items():
        if pattern.search(text):
            events.append(event_type)
    return events


def _detect_sector(text: str) -> Optional[str]:
    """Detect which NEPSE sector a text relates to."""
    text_lower = text.lower()
    for sector, keywords in SECTOR_KEYWORDS.items():
        if any(kw in text_lower for kw in keywords):
            return sector
    return None


def _extract_symbols(text: str) -> list[str]:
    """Extract potential NEPSE ticker symbols from text.

    NEPSE symbols are typically 2-15 uppercase letters.
    """
    # Look for patterns that look like tickers
    candidates = re.findall(r'\b([A-Z]{2,15})\b', text)
    # Filter out common English words
    stop_words = {
        "THE", "AND", "FOR", "HAS", "ITS", "IPO", "FPO", "AGM",
        "NRB", "NPR", "LTD", "PVT", "LTP", "EPS", "PER",
        "CEO", "CFO", "NPA", "NPL", "CRR", "SLR",
        "NOT", "BUT", "WAS", "ARE", "WILL", "WITH",
        "FROM", "THAT", "THIS", "THAN", "MORE", "ALSO",
        "BEEN", "HAVE", "WERE", "SAID", "EACH", "YEAR",
        "LAST", "NEXT", "FIRST", "BANK", "COMPANY",
    }
    return [s for s in candidates if s not in stop_words]


def analyze_fallback(scraped_data: dict) -> dict:
    """Rule-based sentiment analysis fallback.

    Returns a dict with the same structure expected by the aggregator.
    """
    articles = scraped_data.get("news_articles", [])
    market_summary = scraped_data.get("market_summary") or {}
    top_gainers = scraped_data.get("top_gainers", [])
    top_losers = scraped_data.get("top_losers", [])
    sector_indices = scraped_data.get("sector_indices", [])

    # ── Analyze each article ───────────────────────────────────────────
    article_scores = []
    sector_scores = defaultdict(list)
    symbol_mentions = defaultdict(lambda: {"scores": [], "events": [], "sources": []})
    upcoming_events = []
    top_news_items = []
    risk_flags = []

    for art in articles:
        text = f"{art.get('title', '')} {art.get('summary', '') or ''}"
        score = _score_text(text)
        article_scores.append(score)
        events = _detect_events(text)
        sector = _detect_sector(text)
        symbols = _extract_symbols(art.get("title", ""))

        if sector:
            sector_scores[sector].append(score)

        for sym in symbols:
            symbol_mentions[sym]["scores"].append(score)
            symbol_mentions[sym]["events"].extend(events)
            symbol_mentions[sym]["sources"].append(art.get("url", ""))

        # Detect upcoming events
        if events:
            for event in events:
                upcoming_events.append({
                    "symbol": symbols[0] if symbols else None,
                    "event_type": event,
                    "date": None,
                    "details": art.get("title", ""),
                })

        # Build top news
        importance = "high" if abs(score) > 0.5 or events else (
            "medium" if abs(score) > 0.2 else "low"
        )
        top_news_items.append({
            "title": art.get("title", ""),
            "url": art.get("url", ""),
            "published_at": art.get("published_at"),
            "sentiment": _score_to_label(score).value,
            "importance": importance,
            "summary": art.get("summary", "") or art.get("title", ""),
        })

    # ── Market-level sentiment ─────────────────────────────────────────
    drivers = []
    market_score = 0.0

    # Factor 1: Article sentiment average
    if article_scores:
        avg_score = sum(article_scores) / len(article_scores)
        market_score += avg_score * 0.4
        drivers.append({
            "factor": "news_sentiment",
            "impact": "positive" if avg_score > 0 else ("negative" if avg_score < 0 else "neutral"),
            "detail": f"Average news sentiment: {avg_score:.2f} across {len(article_scores)} articles",
        })

    # Factor 2: Market index change
    idx_change = market_summary.get("nepse_percent_change")
    if idx_change is None:
        idx_change = market_summary.get("percent_change")
    if idx_change is not None:
        idx_signal = max(-1.0, min(1.0, idx_change / 3.0))  # Normalize: ±3% = ±1.0
        market_score += idx_signal * 0.3
        drivers.append({
            "factor": "index_momentum",
            "impact": "positive" if idx_change > 0 else ("negative" if idx_change < 0 else "neutral"),
            "detail": f"NEPSE index changed {idx_change:+.2f}%",
        })

    # Factor 3: Advance/Decline ratio
    advances = market_summary.get("advances", 0) or 0
    declines = market_summary.get("declines", 0) or 0
    if advances or declines:
        total = advances + declines
        ad_ratio = (advances - declines) / total if total > 0 else 0
        market_score += ad_ratio * 0.2
        drivers.append({
            "factor": "market_breadth",
            "impact": "positive" if ad_ratio > 0 else ("negative" if ad_ratio < 0 else "neutral"),
            "detail": f"Advance/Decline: {advances}/{declines}",
        })

    # Factor 4: Turnover trend (simple check)
    turnover = market_summary.get("total_turnover")
    if turnover:
        drivers.append({
            "factor": "turnover",
            "impact": "neutral",
            "detail": f"Total turnover: Rs. {turnover:,.0f}" if isinstance(turnover, (int, float)) else f"Total turnover: Rs. {turnover}",
        })

    market_score = max(-1.0, min(1.0, market_score))
    confidence = min(1.0, len(article_scores) / 20.0) * 0.8  # More articles = more confident

    # ── Sector sentiment ───────────────────────────────────────────────
    sector_sentiment = []
    for sector, scores in sector_scores.items():
        avg = sum(scores) / len(scores)
        sector_sentiment.append({
            "sector": sector,
            "score": round(max(-1.0, min(1.0, avg)), 2),
            "label": _score_to_label(avg).value,
            "reasons": [f"Based on {len(scores)} related articles"],
        })

    # Add sectors from index data
    for idx in sector_indices:
        sector_name = idx.get("sector", "")
        pct = idx.get("percent_change")
        if sector_name and pct is not None:
            # Check if we already have this sector
            existing = [s for s in sector_sentiment if s["sector"].lower() in sector_name.lower()]
            if not existing:
                score = max(-1.0, min(1.0, pct / 3.0))
                sector_sentiment.append({
                    "sector": sector_name,
                    "score": round(score, 2),
                    "label": _score_to_label(score).value,
                    "reasons": [f"Index change: {pct:+.2f}%"],
                })

    # ── Watchlist & Caution ─────────────────────────────────────────────
    watchlist = []
    caution_list = []

    for sym, data in symbol_mentions.items():
        avg_score = sum(data["scores"]) / len(data["scores"]) if data["scores"] else 0
        events = list(set(data["events"]))
        sources = list(set(data["sources"]))[:3]

        if avg_score > 0.3 or any(e in ["dividend", "bonus", "right_share", "earnings"] for e in events):
            watchlist.append({
                "symbol": sym,
                "reason": f"Positive signals: sentiment={avg_score:.2f}, events={events}",
                "sentiment": _score_to_label(avg_score).value,
                "tags": events,
                "sources": sources,
            })
        elif avg_score < -0.3 or any(e in ["circuit_hit", "regulatory"] for e in events):
            caution_list.append({
                "symbol": sym,
                "reason": f"Risk signals: sentiment={avg_score:.2f}, flags={events}",
                "risk_tags": events or ["negative_sentiment"],
                "sources": sources,
            })

    # ── Risk Flags ─────────────────────────────────────────────────────
    # Check for circuit hits in gainers/losers
    for mover_list, direction in [(top_gainers, "upper"), (top_losers, "lower")]:
        circuit_stocks = []
        for m in mover_list:
            pct = m.get("percent_change", 0)
            if pct is not None and abs(pct) >= 9.5:  # Near ±10% circuit
                circuit_stocks.append(m.get("symbol", "?"))
        if circuit_stocks:
            risk_flags.append({
                "flag_type": f"{direction}_circuit",
                "description": f"{len(circuit_stocks)} stocks hit {direction} circuit limit",
                "symbols": circuit_stocks[:10],
            })

    # ── Educational insights ───────────────────────────────────────────
    learn_today = [
        "NEPSE operates Sunday through Thursday. Friday and Saturday are market holidays in Nepal.",
        "A stock hitting the ±10% circuit limit means trading is frozen at that price — no more orders can be executed beyond that level for the day.",
        "Book closure date is the cutoff for receiving declared dividends or bonus shares. You must hold shares BEFORE the book closure date to be eligible.",
        "T+2 settlement means shares bought today are credited to your demat account 2 business days later. You cannot sell shares you just bought until settlement.",
        "When a company announces a bonus share, the stock price adjusts downward proportionally on the ex-date. A 10% bonus on a Rs.1000 stock adjusts to ~Rs.909.",
    ]

    # Sort top news by importance
    importance_order = {"high": 0, "medium": 1, "low": 2}
    top_news_items.sort(key=lambda x: importance_order.get(x["importance"], 2))

    return {
        "market_sentiment": {
            "score": round(market_score, 2),
            "label": _score_to_label(market_score).value,
            "confidence": round(confidence, 2),
            "drivers": drivers[:5],
        },
        "sector_sentiment": sector_sentiment[:15],
        "watchlist": watchlist[:10],
        "caution_list": caution_list[:10],
        "upcoming_events": upcoming_events[:20],
        "top_news": top_news_items[:15],
        "risk_flags": risk_flags,
        "learn_today": learn_today[:5],
        "_analysis_method": "rule_based_fallback",
    }
