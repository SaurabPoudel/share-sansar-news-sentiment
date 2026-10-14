Analyze the following NEPSE market data and news articles. Produce a JSON object with exactly this structure:

{{
  "market_sentiment": {{
    "score": <float -1 to 1>,
    "label": "bullish" | "neutral" | "bearish",
    "confidence": <float 0 to 1>,
    "drivers": [
      {{"factor": "<e.g. liquidity, nrb_policy, turnover, index_momentum, political>",
       "impact": "positive" | "negative" | "neutral",
       "detail": "<specific explanation citing article IDs>"}}
    ]
  }},
  "sector_sentiment": [
    {{"sector": "<sector name>", "score": <float>, "label": "<label>",
     "reasons": ["<reason citing article IDs>"]}}
  ],
  "watchlist": [
    {{"symbol": "<TICKER>", "reason": "<why worth researching>",
     "sentiment": "<label>", "tags": ["dividend", "bonus", ...],
     "sources": ["<article URL>"]}}
  ],
  "caution_list": [
    {{"symbol": "<TICKER>", "reason": "<risk description>",
     "risk_tags": ["circuit_hit", "regulatory", ...],
     "sources": ["<article URL>"]}}
  ],
  "upcoming_events": [
    {{"symbol": "<TICKER or null>", "event_type": "<type>",
     "date": "<YYYY-MM-DD or null>", "details": "<description>"}}
  ],
  "top_news": [
    {{"title": "<headline>", "url": "<url>",
     "published_at": "<date or null>",
     "sentiment": "<label>", "importance": "high|medium|low",
     "summary": "<1-2 sentence summary>"}}
  ],
  "risk_flags": [
    {{"flag_type": "<type>", "description": "<detail>",
     "symbols": ["<TICKER>"]}}
  ],
  "learn_today": [
    "<educational insight related to today's data>"
  ]
}}

## Few-shot Examples
{few_shot_examples}

## Today's Market Data
{market_context}

## Today's News Articles
{articles}

## Scrape Issues (if any)
{scrape_errors}

Produce ONLY the JSON object. Every ticker, price, and date must come from the data above.
