import json
from decimal import Decimal
from pathlib import Path

import pytest

from prediction_market_coherence.detector import (
    detect_monotonicity_violations,
    executable_nested_edge,
)
from prediction_market_coherence.models import ThresholdMarket
from prediction_market_coherence.relationships import (
    group_threshold_families,
    normalize_greater_markets,
)

FIXTURE = Path(__file__).parent / "fixtures" / "markets.json"


def families():
    raw = json.loads(FIXTURE.read_text())["markets"]
    markets = normalize_greater_markets(raw)
    return markets, group_threshold_families(markets)


def test_kalshi_market_parsing_and_midpoint():
    market = ThresholdMarket.from_kalshi({
        "ticker":"X-100","event_ticker":"X","title":"X > 100","strike_type":"greater",
        "floor_strike":100,"yes_bid_dollars":"0.40","yes_ask_dollars":"0.44",
        "no_bid_dollars":"0.56","no_ask_dollars":"0.60",
    })
    assert market.strike == Decimal(100)
    assert market.midpoint == Decimal("0.42")


def test_rejects_non_greater_market():
    with pytest.raises(ValueError):
        ThresholdMarket.from_kalshi({"strike_type":"between","floor_strike":1})


def test_one_sided_book_has_no_midpoint():
    market = ThresholdMarket.from_kalshi({"ticker":"X","event_ticker":"X","title":"X","strike_type":"greater","floor_strike":100,"yes_bid_dollars":"0","yes_ask_dollars":"0.44"})
    assert market.midpoint is None


def test_grouping_filters_non_threshold_market():
    markets, fs = families()
    assert len(markets) == 5
    assert [m.strike for m in fs["TESTBTC"]] == [Decimal(100000), Decimal(110000), Decimal(120000)]


def test_detects_expected_violation_without_false_positive_family():
    _, fs = families()
    violations = detect_monotonicity_violations(fs["TESTBTC"])
    assert len(violations) == 1
    assert violations[0].midpoint_gap == Decimal("0.04")
    assert detect_monotonicity_violations(fs["TESTTEMP"]) == []


def test_adjacent_only_finds_same_local_violation():
    _, fs = families()
    violations = detect_monotonicity_violations(fs["TESTBTC"], adjacent_only=True)
    assert len(violations) == 1


def test_executable_nested_edge_uses_asks():
    _, fs = families()
    assert executable_nested_edge(fs["TESTBTC"][1], fs["TESTBTC"][2]) == Decimal("0.02")
