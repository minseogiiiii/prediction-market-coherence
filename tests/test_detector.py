import json
from decimal import Decimal
from pathlib import Path

from prediction_market_coherence.detector import (
    detect_monotonicity_violations,
    executable_nested_edge,
)
from prediction_market_coherence.relationships import (
    group_threshold_families,
    normalize_greater_markets,
)

FIXTURE = Path(__file__).parent / "fixtures" / "markets.json"


def _families():
    raw = json.loads(FIXTURE.read_text())["markets"]
    markets = normalize_greater_markets(raw)
    return markets, group_threshold_families(markets)


def test_grouping_filters_non_threshold_market():
    markets, families = _families()
    assert len(markets) == 5
    assert list(m.strike for m in families["TESTBTC"]) == [
        Decimal("100000"),
        Decimal("110000"),
        Decimal("120000"),
    ]


def test_detects_expected_violation_without_false_positive_family():
    _, families = _families()
    violations = detect_monotonicity_violations(families["TESTBTC"])
    assert len(violations) == 1
    v = violations[0]
    assert v.lower.ticker == "TESTBTC-110"
    assert v.higher.ticker == "TESTBTC-120"
    assert v.midpoint_gap == Decimal("0.04")

    assert detect_monotonicity_violations(families["TESTTEMP"]) == []


def test_adjacent_only_finds_same_local_violation():
    _, families = _families()
    violations = detect_monotonicity_violations(
        families["TESTBTC"], adjacent_only=True
    )
    assert len(violations) == 1
    assert violations[0].midpoint_gap == Decimal("0.04")


def test_executable_nested_edge_uses_asks():
    _, families = _families()
    lower = families["TESTBTC"][1]  # YES ask .52
    higher = families["TESTBTC"][2]  # NO ask .46
    # Guaranteed payout 1.00 - .52 - .46 = .02 before fees/slippage.
    assert executable_nested_edge(lower, higher) == Decimal("0.02")
