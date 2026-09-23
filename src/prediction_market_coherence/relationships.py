from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable

from .models import ThresholdMarket


def normalize_greater_markets(raw_markets: Iterable[dict]) -> list[ThresholdMarket]:
    """Keep only well-formed greater-than threshold markets."""
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
    """Group by event_ticker and sort from low strike to high strike."""
    grouped: dict[str, list[ThresholdMarket]] = defaultdict(list)
    for market in markets:
        if market.event_ticker:
            grouped[market.event_ticker].append(market)

    return {
        event: sorted(family, key=lambda m: m.strike)
        for event, family in grouped.items()
        if len(family) >= 2
    }
