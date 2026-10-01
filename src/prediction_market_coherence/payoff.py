from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from itertools import product

from .models import ZERO, Relationship, RelationType, Side, TradeLeg


@dataclass(frozen=True, slots=True)
class PayoffAnalysis:
    state_payouts: tuple[Decimal, ...]
    minimum_payout: Decimal
    maximum_payout: Decimal


def payoff_for_state(relationship: Relationship, legs: tuple[TradeLeg, ...], state: tuple[bool, ...]) -> Decimal:
    index = {market_id: i for i, market_id in enumerate(relationship.market_ids)}
    payout = ZERO
    for leg in legs:
        if leg.market_id not in index:
            raise ValueError(f"leg market {leg.market_id} is not part of relationship")
        event_true = state[index[leg.market_id]]
        wins = event_true if leg.side is Side.YES else not event_true
        if wins:
            payout += leg.quantity
    return payout


def analyze_payoff(relationship: Relationship, legs: tuple[TradeLeg, ...]) -> PayoffAnalysis:
    payouts = tuple(payoff_for_state(relationship, legs, state) for state in relationship.allowed_states)
    return PayoffAnalysis(payouts, min(payouts), max(payouts))


def canonical_hedge_sides(relationship: Relationship) -> tuple[Side, ...]:
    """Return a minimum-one-payout two-leg hedge for supported binary relations.

    The result is derived from the truth table, not from market probabilities.
    """
    if len(relationship.market_ids) != 2:
        raise ValueError("canonical two-leg hedge requires two markets")
    if relationship.kind is RelationType.IMPLIES:
        return (Side.NO, Side.YES)
    if relationship.kind is RelationType.MUTUALLY_EXCLUSIVE:
        return (Side.NO, Side.NO)
    if relationship.kind is RelationType.EXHAUSTIVE:
        return (Side.YES, Side.YES)
    if relationship.kind is RelationType.COMPLEMENT:
        return (Side.YES, Side.YES)
    if relationship.kind is RelationType.EQUIVALENT:
        return (Side.NO, Side.YES)
    raise ValueError(f"no canonical hedge for {relationship.kind}")


def verify_relationship_states(relationship: Relationship) -> None:
    """Detect accidentally impossible/empty or duplicate truth-state definitions."""
    all_states = set(product([False, True], repeat=len(relationship.market_ids)))
    states = set(relationship.allowed_states)
    if len(states) != len(relationship.allowed_states):
        raise ValueError("relationship contains duplicate allowed states")
    if not states <= all_states:
        raise ValueError("relationship contains malformed states")
    if states == all_states:
        raise ValueError("relationship imposes no logical constraint")
