from datetime import UTC, datetime
from decimal import Decimal

import pytest

from prediction_market_coherence.models import BookLevel, OrderBook, TradeLeg
from prediction_market_coherence.payoff import (
    analyze_payoff,
    canonical_hedge_sides,
    verify_relationship_states,
)
from prediction_market_coherence.relationships import (
    complement,
    equivalent,
    exhaustive,
    implication,
    mutually_exclusive,
)

D = Decimal
NOW = datetime(2026, 10, 1, 16, 0, tzinfo=UTC)


def test_book_level_validation():
    BookLevel(D("0.5"), D("10"))
    with pytest.raises(ValueError): BookLevel(D("0"), D("10"))
    with pytest.raises(ValueError): BookLevel(D("0.5"), D("0"))


def test_orderbook_requires_sorted_levels():
    with pytest.raises(ValueError):
        OrderBook("m", NOW, yes_asks=(BookLevel(D("0.6"), D("1")), BookLevel(D("0.5"), D("1"))))


def _unit_legs(rel, sides):
    return tuple(TradeLeg(mid, side, D("1"), D("0.5")) for mid, side in zip(rel.market_ids, sides))


def test_implication_hedge_has_minimum_one():
    rel = implication("r","A","B",evidence="rules")
    verify_relationship_states(rel)
    analysis = analyze_payoff(rel, _unit_legs(rel, canonical_hedge_sides(rel)))
    assert analysis.state_payouts == (D("1"), D("2"), D("1"))
    assert analysis.minimum_payout == D("1")


def test_mutual_exclusion_hedge_has_minimum_one():
    rel = mutually_exclusive("r","A","B",evidence="rules")
    analysis = analyze_payoff(rel, _unit_legs(rel, canonical_hedge_sides(rel)))
    assert analysis.minimum_payout == D("1")
    assert analysis.maximum_payout == D("2")


def test_exhaustive_hedge_has_minimum_one():
    rel = exhaustive("r","A","B",evidence="rules")
    assert analyze_payoff(rel, _unit_legs(rel, canonical_hedge_sides(rel))).minimum_payout == D("1")


def test_complement_hedge_pays_exactly_one():
    rel = complement("r","A","B",evidence="rules")
    a = analyze_payoff(rel, _unit_legs(rel, canonical_hedge_sides(rel)))
    assert a.minimum_payout == a.maximum_payout == D("1")


def test_equivalent_canonical_hedge_pays_exactly_one():
    rel = equivalent("r","A","B",evidence="rules")
    a = analyze_payoff(rel, _unit_legs(rel, canonical_hedge_sides(rel)))
    assert a.minimum_payout == a.maximum_payout == D("1")


def test_relationship_no_constraint_rejected():
    from prediction_market_coherence.models import Relationship, RelationType
    rel = Relationship("x", RelationType.IMPLIES, ("A","B"), ((False,False),(False,True),(True,False),(True,True)))
    with pytest.raises(ValueError): verify_relationship_states(rel)
