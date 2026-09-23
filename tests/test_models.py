from decimal import Decimal

import pytest

from prediction_market_coherence.models import ThresholdMarket


def test_kalshi_market_parsing_and_midpoint():
    raw = {
        "ticker": "X-100",
        "event_ticker": "X",
        "title": "X > 100",
        "strike_type": "greater",
        "floor_strike": 100,
        "yes_bid_dollars": "0.40",
        "yes_ask_dollars": "0.44",
        "no_bid_dollars": "0.56",
        "no_ask_dollars": "0.60",
    }
    market = ThresholdMarket.from_kalshi(raw)
    assert market.strike == Decimal("100")
    assert market.midpoint == Decimal("0.42")


def test_rejects_non_greater_market():
    with pytest.raises(ValueError):
        ThresholdMarket.from_kalshi({"strike_type": "between", "floor_strike": 1})


def test_one_sided_book_has_no_midpoint():
    raw = {
        "ticker": "X-100",
        "event_ticker": "X",
        "title": "X > 100",
        "strike_type": "greater",
        "floor_strike": 100,
        "yes_bid_dollars": "0",
        "yes_ask_dollars": "0.44",
    }
    assert ThresholdMarket.from_kalshi(raw).midpoint is None
