from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class NewsEvent:
    source: str
    published_at: datetime
    headline: str
    entities: tuple[str, ...]
    source_reliability: Decimal


@dataclass(frozen=True, slots=True)
class MarketMapping:
    market_id: str
    confidence: Decimal
    reason: str


def map_event_to_markets(event: NewsEvent, market_entity_index: dict[str, set[str]], *, threshold: Decimal = Decimal("0.7")) -> tuple[MarketMapping, ...]:
    """Deterministic entity-overlap mapper.

    It maps information to candidate markets only. It does not produce a BUY/SELL
    decision and therefore cannot turn an ambiguous headline directly into an order.
    """
    entity_set = {e.casefold() for e in event.entities if e.strip()}
    results: list[MarketMapping] = []
    for market_id, entities in market_entity_index.items():
        target = {e.casefold() for e in entities if e.strip()}
        if not entity_set or not target:
            continue
        overlap = len(entity_set & target)
        score = Decimal(overlap) / Decimal(len(entity_set | target))
        confidence = score * event.source_reliability
        if confidence >= threshold:
            results.append(MarketMapping(market_id, confidence, f"entity Jaccard={score}"))
    return tuple(sorted(results, key=lambda x: x.confidence, reverse=True))
