"""Tests for shared utility functions."""

from datetime import datetime, timedelta

import pytest

from nepse_sentiment.utils import is_trading_day


@pytest.mark.parametrize(
    ("weekday", "expected"),
    [
        (0, True),
        (1, True),
        (2, True),
        (3, True),
        (4, True),
        (5, False),
        (6, False),
    ],
)
def test_is_trading_day_uses_monday_through_friday(weekday, expected):
    monday = datetime(2026, 10, 26)

    assert is_trading_day(monday + timedelta(days=weekday)) is expected
