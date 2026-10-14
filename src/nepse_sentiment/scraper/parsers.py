"""HTML and data parsers for ShareSansar pages.

Each parser function takes raw HTML/JSON and returns structured Pydantic models.
Selector changes should be handled in config.py / selectors.yaml.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag

from nepse_sentiment.schemas.models import (
    ScrapedArticle,
    ScrapedData,
    ScrapedMarketSummary,
    ScrapedSectorIndex,
    ScrapedTopMover,
)
from nepse_sentiment.scraper.config import ScraperConfig
from nepse_sentiment.utils import now_npt

logger = logging.getLogger(__name__)


def _safe_float(text: str | None) -> Optional[float]:
    """Parse a float from text, handling commas and parentheses."""
    if not text:
        return None
    # Remove commas, whitespace, and handle negative in parentheses
    cleaned = text.strip().replace(",", "").replace("\xa0", "")
    if cleaned.startswith("(") and cleaned.endswith(")"):
        cleaned = "-" + cleaned[1:-1]
    # Remove any non-numeric chars except . and -
    cleaned = re.sub(r"[^\d.\-]", "", cleaned)
    try:
        return float(cleaned)
    except (ValueError, TypeError):
        return None


def _safe_int(text: str | None) -> Optional[int]:
    """Parse an integer from text."""
    val = _safe_float(text)
    return int(val) if val is not None else None


def _extract_article_id(url: str) -> str:
    """Extract a unique article ID from the URL path."""
    # e.g., /news/some-headline-123 -> some-headline-123
    parts = url.rstrip("/").split("/")
    return parts[-1] if parts else url


def parse_news_page(
    html: str,
    config: ScraperConfig,
    category: str = "latest",
) -> list[ScrapedArticle]:
    """Parse a news category page into ScrapedArticle list."""
    soup = BeautifulSoup(html, "lxml")
    articles: list[ScrapedArticle] = []
    selectors = config.news_selectors
    
    # Find all article items
    items = soup.select(selectors.get("article_item", "div.media"))
    
    if not items:
        # Fallback: try common news list patterns
        items = soup.select("div.featured-news-list div.media")
    if not items:
        items = soup.select("div.news-content div.media")
    if not items:
        # Last resort: any div with media class containing links
        items = soup.select("div.media")
    
    for item in items:
        try:
            article = _parse_single_article(item, config, category)
            if article and article.title:
                articles.append(article)
        except Exception as e:
            logger.debug("Failed to parse article: %s", e)
            continue
    
    logger.info("Parsed %d articles from '%s' page", len(articles), category)
    return articles


def _parse_single_article(
    item: Tag,
    config: ScraperConfig,
    category: str,
) -> Optional[ScrapedArticle]:
    """Parse a single article from a media div."""
    selectors = config.news_selectors
    
    # Strategy 1: Find link containing title or with newsdetail href
    link_el = item.select_one(selectors.get("article_link", "a[href*='newsdetail']"))
    if not link_el:
        link_el = item.select_one("a[href*='newsdetail'], a[href*='/news/'], a[href*='news']")

    title_el = item.select_one(
        selectors.get("article_title", "h4.featured-news-title, h4.media-heading a")
    )

    if title_el:
        title = title_el.get_text(strip=True)
    elif link_el:
        title = link_el.get_text(strip=True)
    else:
        return None

    if not link_el and title_el and title_el.name == "a":
        link_el = title_el
    elif not link_el and title_el and title_el.parent and title_el.parent.name == "a":
        link_el = title_el.parent

    href = link_el.get("href", "") if link_el else ""
    url = urljoin(config.base_url, href) if href else ""
    
    if not title or not url:
        return None
    
    # Date
    date_el = item.select_one(
        selectors.get("article_date", "span.text-muted, p")
    )
    published_at = date_el.get_text(strip=True) if date_el else None
    
    # Summary
    summary_el = item.select_one(selectors.get("article_summary", "p"))
    summary = None
    if summary_el:
        summary = summary_el.get_text(strip=True)
        # Skip if it's just the date or very short
        if summary and len(summary) < 10:
            summary = None
    
    return ScrapedArticle(
        article_id=_extract_article_id(url),
        title=title,
        url=url,
        published_at=published_at,
        category=category,
        summary=summary,
    )


def parse_market_summary_page(html: str) -> ScrapedMarketSummary:
    """Parse market summary data from the page.
    
    ShareSansar embeds some market data in JavaScript variables
    and HTML tables. We try multiple extraction strategies.
    """
    soup = BeautifulSoup(html, "lxml")
    summary = ScrapedMarketSummary()
    
    # Strategy 1: Look for data in table rows
    # Market summary tables use .table class
    tables = soup.select("table.table")
    if not tables:
        tables = soup.select("table")
    for table in tables:
        rows = table.select("tr")
        for row in rows:
            cells = row.select("td")
            if len(cells) >= 2:
                label = cells[0].get_text(strip=True).lower()
                value = cells[1].get_text(strip=True)
                
                if "nepse" in label and "index" in label:
                    summary.nepse_index = _safe_float(value)
                elif "% change" in label or "percent" in label:
                    summary.nepse_percent_change = _safe_float(value)
                elif "unchanged" in label:
                    summary.unchanged = _safe_int(value)
                elif "change" in label:
                    summary.nepse_change = _safe_float(value)
                elif "turnover" in label:
                    summary.total_turnover = _safe_float(value)
                elif "traded shares" in label or "volume" in label:
                    summary.total_traded_shares = _safe_int(value)
                elif "transaction" in label:
                    summary.total_transactions = _safe_int(value)
                elif "advance" in label:
                    summary.advances = _safe_int(value)
                elif "decline" in label:
                    summary.declines = _safe_int(value)
                elif "scrip" in label:
                    summary.total_scrips_traded = _safe_int(value)
                elif "capitalization" in label:
                    summary.market_capitalization = _safe_float(value)
                elif "date" in label and not summary.market_date:
                    summary.market_date = value.strip()
    
    # Strategy 2: Look for summary data in div elements
    # Some data appears in span/div with specific classes or IDs
    for el in soup.select(".market-summary-data span, .index-data span, #nepse-index, .market-capitalization"):
        text = el.get_text(strip=True)
        parent_text = el.parent.get_text(strip=True) if el.parent else ""
        el_id = el.get("id", "")
        el_classes = el.get("class", [])
        if ("NEPSE" in parent_text or el_id == "nepse-index") and summary.nepse_index is None:
            summary.nepse_index = _safe_float(text)
        elif "market-capitalization" in el_classes and summary.market_capitalization is None:
            summary.market_capitalization = _safe_float(text)
    
    # Strategy 3: Parse from JavaScript
    scripts = soup.find_all("script")
    for script in scripts:
        script_text = script.string or ""
        
        # Look for index data in JS variables
        idx_match = re.search(
            r'nepse[_\s]*index["\']?\s*[:=]\s*([\d,]+\.?\d*)',
            script_text,
            re.IGNORECASE,
        )
        if idx_match and summary.nepse_index is None:
            summary.nepse_index = _safe_float(idx_match.group(1))
            
        change_match = re.search(
            r'nepse[_\s]*change["\']?\s*[:=]\s*([+\-]?[\d,]+\.?\d*)',
            script_text,
            re.IGNORECASE,
        )
        if change_match and summary.nepse_change is None:
            summary.nepse_change = _safe_float(change_match.group(1))
            
        turnover_match = re.search(
            r'total[_\s]*turnover["\']?\s*[:=]\s*([\d,]+\.?\d*)',
            script_text,
            re.IGNORECASE,
        )
        if turnover_match and summary.total_turnover is None:
            summary.total_turnover = _safe_float(turnover_match.group(1))

    # Strategy 4: Parse NEPSE Index mentions in editorial report text
    if summary.nepse_index is None:
        report_pattern = r'NEPSE\s+Index\s+closed\s+at\s+([\d,]+\.?\d*),\s+(up|down)\s+([\d,]+\.?\d*)\s+points?\s*\(([\d,]+\.?\d*)%\)'
        match = re.search(report_pattern, html, re.IGNORECASE)
        if match:
            summary.nepse_index = _safe_float(match.group(1))
            chg = _safe_float(match.group(3))
            pct = _safe_float(match.group(4))
            if match.group(2).lower() == "down":
                chg = -chg if chg is not None else None
                pct = -pct if pct is not None else None
            summary.nepse_change = chg
            summary.nepse_percent_change = pct
    
    return summary


def parse_top_movers_page(
    html: str,
    mover_type: str = "gainer",
) -> list[ScrapedTopMover]:
    """Parse top gainers/losers/turnover page.
    
    These pages typically have a DataTable that's populated via AJAX,
    but sometimes the initial HTML contains the data in a table.
    """
    soup = BeautifulSoup(html, "lxml")
    movers: list[ScrapedTopMover] = []
    
    # Look for data tables
    table = soup.select_one("table#dataTable, table.table, table.dataTable")
    if not table:
        tables = soup.select("table")
        # Pick the table with most rows (likely the data table)
        table = max(tables, key=lambda t: len(t.select("tr")), default=None)
    
    if not table:
        logger.warning("No table found on %s page", mover_type)
        return movers
    
    rows = table.select("tbody tr")
    if not rows:
        all_rows = table.select("tr")
        if all_rows and all_rows[0].select("th"):
            rows = all_rows[1:]
        elif len(all_rows) > 1:
            rows = all_rows[1:]
        else:
            rows = all_rows
    
    for row in rows:
        cells = row.select("td")
        if len(cells) < 3:
            continue
        
        # Try to extract symbol from link or text
        symbol_el = row.select_one("a[href*='/company/']")
        symbol = (
            symbol_el.get_text(strip=True)
            if symbol_el
            else cells[0].get_text(strip=True)
        )
        
        if not symbol or symbol.isdigit():
            # Probably an SN column, try next cell
            if len(cells) > 1:
                symbol_el = cells[1].select_one("a")
                symbol = (
                    symbol_el.get_text(strip=True)
                    if symbol_el
                    else cells[1].get_text(strip=True)
                )
        
        if not symbol:
            continue
        
        mover = ScrapedTopMover(symbol=symbol.strip())
        
        # Try to extract numeric fields from remaining cells
        numeric_values = []
        for cell in cells[1:]:
            val = _safe_float(cell.get_text(strip=True))
            if val is not None:
                numeric_values.append(val)
        
        if len(numeric_values) >= 1:
            mover.ltp = numeric_values[0]
        if len(numeric_values) >= 2:
            mover.change = numeric_values[-2] if len(numeric_values) > 2 else None
        if len(numeric_values) >= 3:
            mover.percent_change = numeric_values[-1]
            
        if mover_type == "turnover" and len(numeric_values) >= 2:
            mover.turnover = max(numeric_values)
        
        movers.append(mover)
    
    logger.info("Parsed %d %ss", len(movers), mover_type)
    return movers[:20]  # Cap at top 20


def parse_sector_indices(html: str) -> list[ScrapedSectorIndex]:
    """Parse sector sub-index data."""
    soup = BeautifulSoup(html, "lxml")
    indices: list[ScrapedSectorIndex] = []
    
    # Look for the indices table
    table = soup.select_one(
        "table#dataTable, table.table, table.dataTable"
    )
    if not table:
        tables = soup.select("table")
        table = max(tables, key=lambda t: len(t.select("tr")), default=None) if tables else None
        
    if not table:
        return indices
    
    rows = table.select("tbody tr")
    if not rows:
        all_rows = table.select("tr")
        if all_rows and all_rows[0].select("th"):
            rows = all_rows[1:]
        elif len(all_rows) > 1:
            rows = all_rows[1:]
        else:
            rows = all_rows
    
    for row in rows:
        cells = row.select("td")
        if len(cells) < 2:
            continue
        
        sector_name = cells[0].get_text(strip=True)
        if not sector_name or sector_name.isdigit():
            if len(cells) > 2:
                sector_name = cells[1].get_text(strip=True)
                cells = cells[1:]
        
        if not sector_name:
            continue
        
        idx = ScrapedSectorIndex(sector=sector_name)
        
        if len(cells) >= 2:
            idx.index_value = _safe_float(cells[1].get_text(strip=True))
        if len(cells) >= 3:
            idx.change = _safe_float(cells[2].get_text(strip=True))
        if len(cells) >= 4:
            idx.percent_change = _safe_float(cells[3].get_text(strip=True))
        
        indices.append(idx)
    
    logger.info("Parsed %d sector indices", len(indices))
    return indices


def extract_company_json(html: str) -> list[dict]:
    """Extract the embedded cmpjson company list from page HTML.
    
    ShareSansar embeds a JavaScript variable `cmpjson` containing
    all listed companies with id, symbol, and companyname.
    """
    match = re.search(
        r'var\s+cmpjson\s*=\s*(\[.*?\]);',
        html,
        re.DOTALL,
    )
    if not match:
        return []
    
    try:
        companies = json.loads(match.group(1))
        logger.info("Extracted %d companies from cmpjson", len(companies))
        return companies
    except json.JSONDecodeError as e:
        logger.warning("Failed to parse cmpjson: %s", e)
        return []


def parse_nepse_api_summary(data: dict | list) -> ScrapedMarketSummary:
    """Parse market summary data from NEPSE official API response (nepalstock.com/api)."""
    summary = ScrapedMarketSummary()
    if isinstance(data, list):
        for item in data:
            if not isinstance(item, dict):
                continue
            detail = str(item.get("detail", "")).lower()
            val = item.get("value")
            if val is None:
                continue
            val_str = str(val)
            if "nepse" in detail and "index" in detail:
                summary.nepse_index = _safe_float(val_str)
            elif "change" in detail and "percent" not in detail:
                summary.nepse_change = _safe_float(val_str)
            elif "percent" in detail or "%" in detail:
                summary.nepse_percent_change = _safe_float(val_str)
            elif "turnover" in detail:
                summary.total_turnover = _safe_float(val_str)
            elif "shares" in detail or "volume" in detail:
                summary.total_traded_shares = _safe_int(val_str)
            elif "transactions" in detail:
                summary.total_transactions = _safe_int(val_str)
            elif "advance" in detail:
                summary.advances = _safe_int(val_str)
            elif "decline" in detail:
                summary.declines = _safe_int(val_str)
            elif "unchanged" in detail:
                summary.unchanged = _safe_int(val_str)
    elif isinstance(data, dict):
        summary.nepse_index = _safe_float(str(data.get("nepseIndex", data.get("index", data.get("currentValue", "")))))
        summary.nepse_change = _safe_float(str(data.get("pointChange", data.get("change", ""))))
        summary.nepse_percent_change = _safe_float(str(data.get("percentageChange", data.get("percentChange", ""))))
        summary.total_turnover = _safe_float(str(data.get("totalTurnover", "")))
        summary.total_traded_shares = _safe_int(str(data.get("totalTradedShares", "")))
        summary.total_transactions = _safe_int(str(data.get("totalTransactions", "")))
    return summary


def build_scraped_data(
    market_summary: Optional[ScrapedMarketSummary] = None,
    sector_indices: Optional[list[ScrapedSectorIndex]] = None,
    top_gainers: Optional[list[ScrapedTopMover]] = None,
    top_losers: Optional[list[ScrapedTopMover]] = None,
    top_turnover: Optional[list[ScrapedTopMover]] = None,
    news_articles: Optional[list[ScrapedArticle]] = None,
    errors: Optional[list[str]] = None,
) -> ScrapedData:
    """Assemble all scraped components into a single ScrapedData."""
    return ScrapedData(
        scraped_at=now_npt().isoformat(),
        market_summary=market_summary,
        sector_indices=sector_indices or [],
        top_gainers=top_gainers or [],
        top_losers=top_losers or [],
        top_turnover=top_turnover or [],
        news_articles=news_articles or [],
        scrape_errors=errors or [],
    )
