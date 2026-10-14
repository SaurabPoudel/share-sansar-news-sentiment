"""Tests for the scraper parsers."""

import pytest

from nepse_sentiment.scraper.parsers import (
    _safe_float,
    _safe_int,
    _extract_article_id,
    parse_news_page,
    parse_market_summary_page,
    extract_company_json,
)
from nepse_sentiment.scraper.config import ScraperConfig


class TestSafeFloat:
    def test_normal(self):
        assert _safe_float("123.45") == 123.45

    def test_with_commas(self):
        assert _safe_float("1,234.56") == 1234.56

    def test_negative(self):
        assert _safe_float("-5.2") == -5.2

    def test_parentheses_negative(self):
        assert _safe_float("(5.2)") == -5.2

    def test_none(self):
        assert _safe_float(None) is None

    def test_empty(self):
        assert _safe_float("") is None

    def test_non_numeric(self):
        assert _safe_float("abc") is None


class TestSafeInt:
    def test_normal(self):
        assert _safe_int("123") == 123

    def test_with_commas(self):
        assert _safe_int("1,234") == 1234

    def test_none(self):
        assert _safe_int(None) is None


class TestExtractArticleId:
    def test_normal_url(self):
        assert _extract_article_id(
            "https://sharesansar.com/news/nabil-declares-dividend-123"
        ) == "nabil-declares-dividend-123"

    def test_trailing_slash(self):
        assert _extract_article_id(
            "https://sharesansar.com/news/test/"
        ) == "test"


class TestExtractCompanyJson:
    def test_valid_cmpjson(self):
        html = '''
        <script>
        var cmpjson = [{"id":1,"symbol":"NABIL","companyname":"Nabil Bank"},
                       {"id":2,"symbol":"HBL","companyname":"Himalayan Bank"}];
        </script>
        '''
        companies = extract_company_json(html)
        assert len(companies) == 2
        assert companies[0]["symbol"] == "NABIL"

    def test_no_cmpjson(self):
        html = "<html><body>No data</body></html>"
        assert extract_company_json(html) == []


class TestParseNewsPage:
    def test_with_media_divs(self):
        html = '''
        <div class="featured-news-list">
            <div class="media">
                <h4 class="media-heading">
                    <a href="/news/test-article-1">Bank reports record profit</a>
                </h4>
                <span class="text-muted">2024-01-15</span>
                <p>Nabil Bank announced strong quarterly results</p>
            </div>
            <div class="media">
                <h4 class="media-heading">
                    <a href="/news/test-article-2">Hydropower IPO opens</a>
                </h4>
                <span class="text-muted">2024-01-15</span>
                <p>New hydropower company opens IPO for public subscription</p>
            </div>
        </div>
        '''
        config = ScraperConfig()
        articles = parse_news_page(html, config, "latest")
        assert len(articles) == 2
        assert articles[0].title == "Bank reports record profit"
        assert articles[0].article_id == "test-article-1"
        assert articles[0].category == "latest"

    def test_empty_page(self):
        html = "<html><body><p>No articles</p></body></html>"
        config = ScraperConfig()
        articles = parse_news_page(html, config)
        assert articles == []


class TestParseMarketSummary:
    def test_with_table_data(self):
        html = '''
        <table class="table">
            <tr><td>NEPSE Index</td><td>2,105.34</td></tr>
            <tr><td>Change</td><td>15.30</td></tr>
            <tr><td>% Change</td><td>0.73</td></tr>
            <tr><td>Total Turnover (Rs.)</td><td>3,500,000,000</td></tr>
            <tr><td>Total Traded Shares</td><td>15,000,000</td></tr>
            <tr><td>Total Transactions</td><td>50,000</td></tr>
            <tr><td>Total Advances</td><td>150</td></tr>
            <tr><td>Total Declines</td><td>80</td></tr>
            <tr><td>Total Unchanged</td><td>20</td></tr>
        </table>
        '''
        summary = parse_market_summary_page(html)
        assert summary.nepse_index == 2105.34
        assert summary.nepse_change == 15.30
        assert summary.advances == 150
        assert summary.declines == 80

    def test_with_script_data(self):
        html = '''
        <script>
            var nepse_index = 2050.5;
            var total_turnover = 4000000000;
        </script>
        '''
        summary = parse_market_summary_page(html)
        assert summary.nepse_index == 2050.5
        assert summary.total_turnover == 4000000000.0


class TestParseTopMovers:
    def test_top_gainers(self):
        from nepse_sentiment.scraper.parsers import parse_top_movers_page
        html = '''
        <table id="dataTable">
            <tr><th>SN</th><th>Symbol</th><th>LTP</th><th>Change</th><th>% Change</th></tr>
            <tr><td>1</td><td><a href="/company/nabil">NABIL</a></td><td>1,200.00</td><td>40.00</td><td>3.45</td></tr>
        </table>
        '''
        movers = parse_top_movers_page(html, "gainer")
        assert len(movers) == 1
        assert movers[0].symbol == "NABIL"
        assert movers[0].ltp == 1200.00
        assert movers[0].change == 40.00
        assert movers[0].percent_change == 3.45

    def test_empty_table(self):
        from nepse_sentiment.scraper.parsers import parse_top_movers_page
        assert parse_top_movers_page("<html></html>") == []


class TestParseSectorIndices:
    def test_sectors(self):
        from nepse_sentiment.scraper.parsers import parse_sector_indices
        html = '''
        <table class="table">
            <tr><td>Commercial Bank</td><td>1,250.0</td><td>10.0</td><td>0.8</td></tr>
        </table>
        '''
        indices = parse_sector_indices(html)
        assert len(indices) == 1
        assert indices[0].sector == "Commercial Bank"
        assert indices[0].index_value == 1250.0

    def test_empty(self):
        from nepse_sentiment.scraper.parsers import parse_sector_indices
        assert parse_sector_indices("<html></html>") == []


class TestParseNepseApiSummary:
    def test_list_data(self):
        from nepse_sentiment.scraper.parsers import parse_nepse_api_summary
        data = [
            {"detail": "NEPSE Index", "value": "2050.0"},
            {"detail": "Total Turnover", "value": "5000000000"},
        ]
        summary = parse_nepse_api_summary(data)
        assert summary.nepse_index == 2050.0
        assert summary.total_turnover == 5000000000.0

    def test_dict_data(self):
        from nepse_sentiment.scraper.parsers import parse_nepse_api_summary
        data = {
            "nepseIndex": "2100.0",
            "pointChange": "15.0",
            "percentageChange": "0.72",
            "totalTurnover": "4000000000",
        }
        summary = parse_nepse_api_summary(data)
        assert summary.nepse_index == 2100.0
        assert summary.nepse_change == 15.0
        assert summary.nepse_percent_change == 0.72
        assert summary.total_turnover == 4000000000.0


class TestBuildScrapedData:
    def test_build(self):
        from nepse_sentiment.scraper.parsers import build_scraped_data
        from nepse_sentiment.schemas.models import ScrapedMarketSummary
        data = build_scraped_data(
            market_summary=ScrapedMarketSummary(nepse_index=2000.0),
            errors=["Minor notice"],
        )
        assert data.market_summary.nepse_index == 2000.0
        assert data.scrape_errors == ["Minor notice"]
        assert data.scraped_at is not None


class TestScraperConfig:
    def test_load_default(self):
        cfg = ScraperConfig.load()
        assert cfg.base_url == "https://www.sharesansar.com"
        assert cfg.rate_limit.requests_per_second == 1.0

    def test_load_nonexistent(self, tmp_path):
        cfg = ScraperConfig.load(tmp_path / "nonexistent.yaml")
        assert cfg.base_url == "https://www.sharesansar.com"


class TestHttpClient:
    def test_client_init_and_context(self):
        from nepse_sentiment.scraper.client import HttpClient
        cfg = ScraperConfig()
        with HttpClient(cfg) as client:
            assert client.config == cfg
            assert client._session.headers["User-Agent"] == cfg.user_agent

