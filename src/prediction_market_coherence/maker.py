from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from .models import ONE, ZERO


@dataclass(frozen=True, slots=True)
class MakerConfig:
    half_spread: Decimal = Decimal("0.02")
    inventory_skew: Decimal = Decimal("0.0001")
    min_price: Decimal = Decimal("0.01")
    max_price: Decimal = Decimal("0.99")
    max_inventory: Decimal = Decimal(500)


@dataclass(frozen=True, slots=True)
class MakerQuote:
    bid: Decimal
    ask: Decimal
    reservation_price: Decimal
    enabled: bool
    reason: str = ""


def make_quote(fair_value: Decimal, inventory_yes: Decimal, config: MakerConfig) -> MakerQuote:
    if not ZERO <= fair_value <= ONE:
        raise ValueError("fair_value must be in [0,1]")
    if abs(inventory_yes) >= config.max_inventory:
        return MakerQuote(ZERO, ZERO, fair_value, False, "inventory limit")
    reservation = fair_value - config.inventory_skew * inventory_yes
    reservation = min(config.max_price, max(config.min_price, reservation))
    bid = max(config.min_price, reservation - config.half_spread)
    ask = min(config.max_price, reservation + config.half_spread)
    if bid >= ask:
        return MakerQuote(bid, ask, reservation, False, "crossed quote")
    return MakerQuote(bid, ask, reservation, True)


def adverse_selection_cost(fill_price: Decimal, future_mid: Decimal, *, bought: bool) -> Decimal:
    """Positive value means the fill moved against the maker after execution."""
    return fill_price - future_mid if bought else future_mid - fill_price
