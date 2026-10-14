"""Schema validation script.

Run as: python -m nepse_sentiment.validate
Exits with code 1 if api/sentiment.json is missing or malformed.
Used as a CI gate step.
"""

import json
import sys
from pathlib import Path

from pydantic import ValidationError

from nepse_sentiment.schemas.models import SentimentOutput
from nepse_sentiment.utils import get_api_dir


def validate() -> bool:
    """Validate api/sentiment.json against the Pydantic schema."""
    api_dir = get_api_dir()
    sentiment_path = api_dir / "sentiment.json"
    
    if not sentiment_path.exists():
        print(f"ERROR: {sentiment_path} does not exist", file=sys.stderr)
        return False
    
    try:
        raw = json.loads(sentiment_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"ERROR: Invalid JSON: {e}", file=sys.stderr)
        return False
    
    try:
        output = SentimentOutput.model_validate(raw)
    except ValidationError as e:
        print(f"ERROR: Schema validation failed:\n{e}", file=sys.stderr)
        return False
    
    # Additional sanity checks
    errors = []
    
    if output.schema_version != "1.0":
        errors.append(f"Unexpected schema_version: {output.schema_version}")
    
    if not output.market_date:
        errors.append("market_date is empty")
    
    if not output.disclaimer:
        errors.append("disclaimer is missing")
    
    if output.market_sentiment.score < -1 or output.market_sentiment.score > 1:
        errors.append(f"market_sentiment.score out of range: {output.market_sentiment.score}")
    
    if errors:
        for err in errors:
            print(f"WARNING: {err}", file=sys.stderr)
    
    print(f"OK: {sentiment_path} is valid (status={output.status.value})")
    return True


def main() -> None:
    if not validate():
        sys.exit(1)


if __name__ == "__main__":
    main()
