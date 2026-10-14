# NEPSE Market Sentiment Scraper & Analyzer

[![Daily NEPSE Sentiment Analysis](https://github.com/SaurabPoudel/share-sansar-news-scrapper/actions/workflows/daily.yml/badge.svg)](https://github.com/SaurabPoudel/share-sansar-news-scrapper/actions/workflows/daily.yml)

A 100% free, automated pipeline that scrapes daily data from [ShareSansar](https://www.sharesansar.com/), analyzes market, sector, and ticker-level sentiment using LLMs (Google Gemini free tier) with a robust rule-based fallback, and publishes structured JSON and Markdown summaries to GitHub Pages.

---

## 🚀 Live API Endpoints

Once GitHub Pages is enabled on your fork/repo, your live API is accessible at:

* **Latest Market Sentiment:**  
  `https://<username>.github.io/<repo>/api/sentiment.json`
* **Human-Readable Markdown Summary:**  
  `https://<username>.github.io/<repo>/api/latest-summary.md`
* **Historical Daily Archive (Past 30 Days):**  
  `https://<username>.github.io/<repo>/api/history/YYYY-MM-DD.json`

CORS is pre-configured via `_headers` so you can consume the JSON directly from any frontend web app or mobile application (`fetch()` / Axios).

---

## 🛠️ Architecture & Features

* **Zero-Cost Operation:** Runs purely on GitHub Actions free compute runners, deploys to GitHub Pages, and leverages the free tier of Google Gemini API (or the built-in deterministic rule-based NLP fallback).
* **Polite Scraping:** Strict rate-limiting (1 req/sec), custom educational User-Agent, exponential backoff retries via `tenacity`, and isolated selectors configuration (`selectors.yaml`).
* **Robust Degradation:**
  * If Google Gemini API is unavailable or rate-limited: automatically falls back to an offline NEPSE equity rule-based keyword & event detection engine.
  * If the market is closed or scraping fails: marks payload with `"status": "stale"`, retains previous data, and logs diagnostics.
* **NEPSE Domain-Specific Analysis:**
  * **Market Sentiment:** Score (-1.0 to +1.0), label (`bullish`, `neutral`, `bearish`), confidence rating, and macro drivers (liquidity, NRB directives, turnover, etc.).
  * **Sector Breakdown:** Sub-index tracking for Commercial Banks, Hydropower, Microfinance, Insurance, etc.
  * **Stock Signals:** Event tagging for `dividend`, `bonus`, `right_share`, `ipo`, `merger`, `book_close`, `circuit_hit`, and `regulatory`.
  * **Watchlist vs. Caution List:** Evidence-based flagged tickers ("worth researching" / "elevated risk").
  * **Retail Investor Insights:** Plain-language educational tips on NEPSE mechanics (circuit rules, bonus adjustment, T+2 settlement).

---

## 📦 Local Setup & Execution

The project uses [`uv`](https://docs.astral.sh/uv/) for Python packaging and virtual environment management.

### Prerequisites
* Install `uv`:
  ```bash
  curl -LsSf https://astral.sh/uv/install.sh | sh
  ```

### 1. Clone & Sync Dependencies
```bash
git clone https://github.com/SaurabPoudel/share-sansar-news-scrapper.git
cd share-sansar-news-scrapper
uv sync
```

### 2. Configure Free Gemini API Key (Optional)
To use the Gemini 2.0 Flash LLM analyzer:
1. Obtain a free API key at [Google AI Studio](https://aistudio.google.com/).
2. Export it in your shell:
   ```bash
   export GEMINI_API_KEY="your-api-key-here"
   ```
*(If `GEMINI_API_KEY` is not provided, the pipeline automatically runs the local rule-based fallback analyzer).*

### 3. Run the Pipeline Locally
```bash
uv run python -m nepse_sentiment.main
```

### 4. Validate the Generated JSON
```bash
uv run python -m nepse_sentiment.validate
```

### 5. Run the Test Suite
```bash
uv run pytest tests/
```

---

## 🤖 GitHub Actions & Pages Setup

### 1. Enable GitHub Pages
1. Go to your repository settings: **Settings** → **Pages**.
2. Under **Build and deployment** → **Source**, select **GitHub Actions**.

### 2. Add Secrets
1. Go to **Settings** → **Secrets and variables** → **Actions**.
2. Click **New repository secret**.
3. Name: `GEMINI_API_KEY`
4. Value: Paste your Google AI Studio API key.

### 3. Schedule & Execution
The workflow [`.github/workflows/daily.yml`](.github/workflows/daily.yml) is scheduled to run at **10:15 UTC (4:00 PM Nepal Time)** from Sunday to Thursday, 1 hour after NEPSE trading closes. You can also trigger it manually anytime via the **Actions** tab using **Run workflow**.

---

## 🌐 Consuming the API in Apps

### JavaScript / Web (CORS-friendly):
```javascript
async function getNepseSentiment() {
  const url = "https://<username>.github.io/<repo>/api/sentiment.json";
  const res = await fetch(url);
  const data = await res.json();
  
  console.log(`NEPSE Score: ${data.market_sentiment.score} (${data.market_sentiment.label})`);
  console.log("Watchlist:", data.watchlist);
}
```

### Python:
```python
import requests

data = requests.get("https://<username>.github.io/<repo>/api/sentiment.json").json()
print("Market Date:", data["market_date"])
print("Sentiment:", data["market_sentiment"])
```

---

## ⚠️ Failure Modes & Graceful Handling

1. **IP Blocking / Cloudflare Bot Mitigation:**  
   GitHub Actions runner IPs might occasionally encounter Cloudflare challenges. If scraping fails, the pipeline preserves the last known valid JSON, updates `"status": "stale"`, and avoids breaking downstream consumers.
2. **API Rate Limiting:**  
   If Gemini API free limits (15 RPM / 1M tokens/day) are reached, the system retries once with backoff, then switches seamlessly to `rule_based_fallback`.
3. **Site Layout Changes:**  
   All CSS selectors and page paths are isolated in [`selectors.yaml`](selectors.yaml). Layout changes can be fixed with single-line configuration edits without refactoring core parsing code.
4. **Market Holidays / Non-Trading Days:**  
   NEPSE is closed Fridays, Saturdays, and public holidays. On non-trading days, the pipeline detects the holiday/weekend state and retains the existing output file.

---

## ⚖️ Disclaimer

*This pipeline and generated datasets are automated analyses created strictly for educational and informational purposes. It is NOT financial advice, investment recommendation, or an endorsement of any security. Investing in the Nepal Stock Exchange (NEPSE) involves substantial market risk, including loss of principal. Always perform your own research (DYOR) and consult a registered financial advisor before making investment decisions.*
