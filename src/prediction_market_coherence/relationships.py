from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
import re

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


def _semantic_subject(title: str) -> str:
    """Normalize a threshold title while removing the numeric strike.

    The legacy Kalshi scanner is deliberately conservative: contracts are only
    compared when both the event and the non-numeric proposition text match.
    This prevents same-event, cross-player contamination while keeping numeric
    threshold ladders together. Canonical Super Market relationships do not use
    this heuristic; they come from the venue's authoritative relationship API.
    """
    text = title.casefold()
    text = re.sub(r"(?<![a-z])[-+]?\\$?\\d[\\d,]*(?:\\.\\d+)?(?:%|[kmb])?(?![a-z])", " ", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def group_threshold_families(
    markets: Iterable[ThresholdMarket],
) -> dict[str, list[ThresholdMarket]]:
    grouped: dict[tuple[str, str], list[ThresholdMarket]] = defaultdict(list)
    subjects_by_event: dict[str, set[str]] = defaultdict(set)

    for market in markets:
        if not market.event_ticker:
            continue
        subject = _semantic_subject(market.title)
        # Empty/malformed titles fail closed into ticker-isolated families.
        subject_key = subject or f"ticker:{market.ticker.casefold()}"
        grouped[(market.event_ticker, subject_key)].append(market)
        subjects_by_event[market.event_ticker].add(subject_key)

    out: dict[str, list[ThresholdMarket]] = {}
    for (event, subject), family in grouped.items():
        if len(family) < 2:
            continue
        key = event if len(subjects_by_event[event]) == 1 else f"{event}::{subject}"
        out[key] = sorted(family, key=lambda m: m.strike)
    return out


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
