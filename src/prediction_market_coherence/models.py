from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any


def _to_decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None


@dataclass(frozen=True, slots=True)
class ThresholdMarket:
    """Normalized Kalshi-style greater-than threshold market."""

    ticker: str
    event_ticker: str
    title: str
    strike: Decimal
    yes_bid: Decimal | None
    yes_ask: Decimal | None
    no_bid: Decimal | None
    no_ask: Decimal | None
    expiration_time: str | None = None

    @classmethod
    def from_kalshi(cls, raw: dict[str, Any]) -> "ThresholdMarket":
        if raw.get("strike_type") != "greater":
            raise ValueError("Only strike_type='greater' is supported in the MVP")

        strike = _to_decimal(raw.get("floor_strike"))
        if strike is None:
            raise ValueError("greater-than market is missing floor_strike")

        return cls(
            ticker=str(raw.get("ticker", "")),
            event_ticker=str(raw.get("event_ticker", "")),
            title=str(raw.get("title", "")),
            strike=strike,
            yes_bid=_to_decimal(raw.get("yes_bid_dollars")),
            yes_ask=_to_decimal(raw.get("yes_ask_dollars")),
            no_bid=_to_decimal(raw.get("no_bid_dollars")),
            no_ask=_to_decimal(raw.get("no_ask_dollars")),
            expiration_time=raw.get("expiration_time") or raw.get("expected_expiration_time"),
        )

    @property
    def midpoint(self) -> Decimal | None:
        """Two-sided YES midpoint. Missing/zero-sided books are excluded."""
        if self.yes_bid is None or self.yes_ask is None:
            return None
        if self.yes_bid <= 0 or self.yes_ask <= 0:
            return None
        if self.yes_bid > self.yes_ask:
            return None
        return (self.yes_bid + self.yes_ask) / Decimal("2")
