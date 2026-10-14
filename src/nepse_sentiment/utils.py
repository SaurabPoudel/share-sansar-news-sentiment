"""Shared utility functions."""

from __future__ import annotations

import json
import logging
import os
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

# Nepal Time is UTC+5:45
NPT = timezone(timedelta(hours=5, minutes=45))


def now_npt() -> datetime:
    """Current datetime in Nepal Time."""
    return datetime.now(NPT)


def today_npt() -> str:
    """Today's date string in NPT (YYYY-MM-DD)."""
    return now_npt().strftime("%Y-%m-%d")


def is_trading_day(dt: datetime | None = None) -> bool:
    """Check if the given date is a NEPSE trading day (Sun-Thu).
    
    Saturday (5) and Friday (4) are holidays in Nepal.
    Actually NEPSE is open Sun=6, Mon=0, Tue=1, Wed=2, Thu=3.
    Python weekday(): Mon=0, Tue=1, Wed=2, Thu=3, Fri=4, Sat=5, Sun=6
    So trading days are: 0,1,2,3,6 (Mon-Thu and Sun)
    """
    if dt is None:
        dt = now_npt()
    return dt.weekday() in (0, 1, 2, 3, 6)  # Mon-Thu, Sun


def get_project_root() -> Path:
    """Get the project root directory."""
    # Walk up from this file to find pyproject.toml
    current = Path(__file__).resolve().parent
    for _ in range(10):
        if (current / "pyproject.toml").exists():
            return current
        current = current.parent
    # Fallback: use CWD
    return Path.cwd()


def get_api_dir() -> Path:
    """Get the api/ output directory, creating it if needed."""
    api_dir = get_project_root() / "api"
    api_dir.mkdir(parents=True, exist_ok=True)
    (api_dir / "history").mkdir(exist_ok=True)
    return api_dir


def write_output_json(data: dict, api_dir: Path | None = None) -> Path:
    """Write sentiment.json and history/YYYY-MM-DD.json.
    
    Keeps the last 30 days of history files.
    Returns the path to sentiment.json.
    """
    if api_dir is None:
        api_dir = get_api_dir()
    
    sentiment_path = api_dir / "sentiment.json"
    json_str = json.dumps(data, indent=2, ensure_ascii=False)
    
    sentiment_path.write_text(json_str, encoding="utf-8")
    logger.info("Wrote %s (%d bytes)", sentiment_path, len(json_str))
    
    # Write history file
    market_date = data.get("market_date", today_npt())
    history_dir = api_dir / "history"
    history_dir.mkdir(exist_ok=True)
    history_path = history_dir / f"{market_date}.json"
    history_path.write_text(json_str, encoding="utf-8")
    logger.info("Wrote history: %s", history_path)
    
    # Prune old history (keep last 30 days)
    _prune_history(history_dir, keep_days=30)
    
    return sentiment_path


def _prune_history(history_dir: Path, keep_days: int = 30) -> None:
    """Remove history files older than keep_days."""
    cutoff = now_npt() - timedelta(days=keep_days)
    cutoff_str = cutoff.strftime("%Y-%m-%d")
    
    for f in history_dir.glob("*.json"):
        if f.stem < cutoff_str:
            f.unlink()
            logger.debug("Pruned old history: %s", f.name)


def write_summary_markdown(data: dict, api_dir: Path | None = None) -> Path:
    """Generate a human-readable markdown summary."""
    if api_dir is None:
        api_dir = get_api_dir()
    
    ms = data.get("market_sentiment", {})
    summary = data.get("market_summary", {})
    
    lines = [
        f"# NEPSE Market Sentiment — {data.get('market_date', 'N/A')}",
        "",
        f"**Generated:** {data.get('generated_at', 'N/A')}",
        f"**Status:** {data.get('status', 'N/A')}",
        "",
        "## Market Summary",
        "",
        f"- **NEPSE Index:** {summary.get('nepse_index', 'N/A')}",
        f"- **Change:** {summary.get('change', 'N/A')} ({summary.get('percent_change', 'N/A')}%)",
        f"- **Turnover:** Rs. {summary.get('total_turnover', 'N/A')}",
        f"- **Advances/Declines:** {summary.get('advances', 'N/A')}/{summary.get('declines', 'N/A')}",
        "",
        "## Sentiment",
        "",
        f"- **Score:** {ms.get('score', 'N/A')} ({ms.get('label', 'N/A')})",
        f"- **Confidence:** {ms.get('confidence', 'N/A')}",
        "",
    ]
    
    drivers = ms.get("drivers", [])
    if drivers:
        lines.append("### Key Drivers")
        lines.append("")
        for d in drivers:
            lines.append(f"- **{d.get('factor', '')}** ({d.get('impact', '')}): {d.get('detail', '')}")
        lines.append("")
    
    watchlist = data.get("watchlist", [])
    if watchlist:
        lines.append("## Watchlist (Worth Researching)")
        lines.append("")
        for w in watchlist:
            lines.append(f"- **{w.get('symbol', '')}**: {w.get('reason', '')}")
        lines.append("")
    
    caution = data.get("caution_list", [])
    if caution:
        lines.append("## Caution List (Elevated Risk)")
        lines.append("")
        for c in caution:
            lines.append(f"- **{c.get('symbol', '')}**: {c.get('reason', '')}")
        lines.append("")
    
    learn = data.get("learn_today", [])
    if learn:
        lines.append("## Things a Retail Investor Might Not Know")
        lines.append("")
        for i, item in enumerate(learn, 1):
            lines.append(f"{i}. {item}")
        lines.append("")
    
    lines.append("---")
    lines.append("")
    lines.append(f"*{data.get('disclaimer', '')}*")
    
    md_path = api_dir / "latest-summary.md"
    md_path.write_text("\n".join(lines), encoding="utf-8")
    logger.info("Wrote summary: %s", md_path)
    return md_path


def load_existing_output(api_dir: Path | None = None) -> dict | None:
    """Load the existing sentiment.json if it exists (for stale fallback)."""
    if api_dir is None:
        api_dir = get_api_dir()
    
    sentiment_path = api_dir / "sentiment.json"
    if sentiment_path.exists():
        try:
            return json.loads(sentiment_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Failed to load existing output: %s", e)
    return None


def setup_logging(level: str = "INFO") -> None:
    """Configure logging for the pipeline."""
    log_level = getattr(logging, level.upper(), logging.INFO)
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
