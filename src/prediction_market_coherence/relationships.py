from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable

from .models import Relationship, RelationType, ThresholdMarket


def normalize_greater_markets(raw_markets: Iterable[dict]) -> list[ThresholdMarket]:
    out: list[ThresholdMarket] = []
    for raw in raw_markets:
        if raw.get("strike_type") != "greater" or raw.get("floor_strike") is None:
            continue
        try:
            out.append(ThresholdMarket.from_kalshi(raw))
        except ValueError:
            continue
    return out


def group_threshold_families(
    markets: Iterable[ThresholdMarket],
) -> dict[str, list[ThresholdMarket]]:
    grouped: dict[str, list[ThresholdMarket]] = defaultdict(list)
    for market in markets:
        if market.event_ticker:
            grouped[market.event_ticker].append(market)
    return {
        event: sorted(family, key=lambda m: m.strike)
        for event, family in grouped.items()
        if len(family) >= 2
    }


def implication(relation_id: str, antecedent: str, consequent: str, *, evidence: str) -> Relationship:
    return Relationship(
        relation_id=relation_id,
        kind=RelationType.IMPLIES,
        market_ids=(antecedent, consequent),
        allowed_states=((False, False), (False, True), (True, True)),
        evidence=evidence,
    )


def mutually_exclusive(relation_id: str, a: str, b: str, *, evidence: str) -> Relationship:
    return Relationship(
        relation_id=relation_id,
        kind=RelationType.MUTUALLY_EXCLUSIVE,
        market_ids=(a, b),
        allowed_states=((False, False), (False, True), (True, False)),
        evidence=evidence,
    )


def exhaustive(relation_id: str, a: str, b: str, *, evidence: str) -> Relationship:
    return Relationship(
        relation_id=relation_id,
        kind=RelationType.EXHAUSTIVE,
        market_ids=(a, b),
        allowed_states=((False, True), (True, False), (True, True)),
        evidence=evidence,
    )


def complement(relation_id: str, a: str, b: str, *, evidence: str) -> Relationship:
    return Relationship(
        relation_id=relation_id,
        kind=RelationType.COMPLEMENT,
        market_ids=(a, b),
        allowed_states=((False, True), (True, False)),
        evidence=evidence,
    )


def equivalent(relation_id: str, a: str, b: str, *, evidence: str) -> Relationship:
    return Relationship(
        relation_id=relation_id,
        kind=RelationType.EQUIVALENT,
        market_ids=(a, b),
        allowed_states=((False, False), (True, True)),
        evidence=evidence,
    )
