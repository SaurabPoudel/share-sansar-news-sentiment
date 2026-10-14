"""HTTP client with rate limiting, retries, and polite scraping."""

from __future__ import annotations

import logging
import time
from typing import Optional

import requests
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)

from nepse_sentiment.scraper.config import ScraperConfig

logger = logging.getLogger(__name__)


class HttpClient:
    """Rate-limited HTTP client with retry logic.
    
    Respects robots.txt by:
    - Setting honest User-Agent
    - Rate limiting to 1 req/sec
    - Retrying with exponential backoff
    """
    
    def __init__(self, config: ScraperConfig) -> None:
        self.config = config
        self._session = requests.Session()
        self._session.headers.update({
            "User-Agent": config.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive",
        })
        self._last_request_time: float = 0.0
    
    def _rate_limit(self) -> None:
        """Enforce rate limiting between requests."""
        min_interval = 1.0 / self.config.rate_limit.requests_per_second
        elapsed = time.monotonic() - self._last_request_time
        if elapsed < min_interval:
            sleep_time = min_interval - elapsed
            logger.debug("Rate limiting: sleeping %.2fs", sleep_time)
            time.sleep(sleep_time)
        self._last_request_time = time.monotonic()
    
    def get(
        self,
        url: str,
        params: Optional[dict] = None,
        accept_json: bool = False,
    ) -> requests.Response:
        """Make a rate-limited GET request with retries."""
        self._rate_limit()
        
        headers = {}
        if accept_json:
            headers["Accept"] = "application/json"
            headers["X-Requested-With"] = "XMLHttpRequest"
        
        return self._get_with_retry(url, params=params, extra_headers=headers)
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2, min=2, max=30),
        retry=retry_if_exception_type(
            (requests.ConnectionError, requests.Timeout)
        ),
        before_sleep=lambda retry_state: logger.warning(
            "Retry %d for %s: %s",
            retry_state.attempt_number,
            retry_state.args[1] if len(retry_state.args) > 1 else retry_state.kwargs.get("url", "?"),
            retry_state.outcome.exception() if retry_state.outcome else "?",
        ),
    )
    def _get_with_retry(
        self,
        url: str,
        params: Optional[dict] = None,
        extra_headers: Optional[dict] = None,
    ) -> requests.Response:
        """Internal GET with retry decorator."""
        headers = dict(self._session.headers)
        if extra_headers:
            headers.update(extra_headers)
        
        response = self._session.get(
            url,
            params=params,
            headers=headers,
            timeout=self.config.rate_limit.timeout_seconds,
        )
        response.raise_for_status()
        return response
    
    def get_page(self, path: str) -> str:
        """Fetch a ShareSansar page and return its HTML."""
        url = f"{self.config.base_url}{path}"
        logger.info("Fetching: %s", url)
        response = self.get(url)
        return response.text
    
    def get_json(self, path: str, params: Optional[dict] = None) -> dict | list:
        """Fetch a JSON endpoint."""
        url = f"{self.config.base_url}{path}"
        logger.info("Fetching JSON: %s", url)
        response = self.get(url, params=params, accept_json=True)
        return response.json()
    
    def close(self) -> None:
        """Close the HTTP session."""
        self._session.close()
    
    def __enter__(self) -> HttpClient:
        return self
    
    def __exit__(self, *args) -> None:
        self.close()
