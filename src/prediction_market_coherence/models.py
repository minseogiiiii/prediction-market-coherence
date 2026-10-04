from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Any

ONE = Decimal(1)
ZERO = Decimal(0)


def to_decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None


def utc_now() -> datetime:
    return datetime.now(UTC)


class Side(str, Enum):
    YES = "YES"
    NO = "NO"

    @property
    def opposite(self) -> Side:
        return Side.NO if self is Side.YES else Side.YES


class RelationType(str, Enum):
    IMPLIES = "IMPLIES"
    MUTUALLY_EXCLUSIVE = "MUTUALLY_EXCLUSIVE"
    EXHAUSTIVE = "EXHAUSTIVE"
    COMPLEMENT = "COMPLEMENT"
    EQUIVALENT = "EQUIVALENT"
    PARTITION = "PARTITION"


@dataclass(frozen=True, slots=True)
class BookLevel:
    price: Decimal
    size: Decimal

    def __post_init__(self) -> None:
        if not ZERO < self.price < ONE:
            raise ValueError(f"price must be in (0, 1), got {self.price}")
        if self.size <= ZERO:
            raise ValueError(f"size must be positive, got {self.size}")


@dataclass(frozen=True, slots=True)
class OrderBook:
    """Normalized binary-contract order book.

    `market_id` is retained for backward compatibility with the original research
    MVP. For the Super Market adapter it contains an **exchangeId**, because an
    Exchange is the platform's tradable contract unit.
    """

    market_id: str
    observed_at: datetime
    yes_bids: tuple[BookLevel, ...] = ()
    yes_asks: tuple[BookLevel, ...] = ()
    no_bids: tuple[BookLevel, ...] = ()
    no_asks: tuple[BookLevel, ...] = ()
    source_sequence: int | None = None
    received_at: datetime | None = None
    context_id: str | None = None

    def __post_init__(self) -> None:
        if self.observed_at.tzinfo is None:
            raise ValueError("observed_at must be timezone-aware")
        if self.received_at is not None and self.received_at.tzinfo is None:
            raise ValueError("received_at must be timezone-aware")
        if not self.market_id:
            raise ValueError("market_id is required")
        self._assert_sorted(self.yes_bids, descending=True, name="yes_bids")
        self._assert_sorted(self.no_bids, descending=True, name="no_bids")
        self._assert_sorted(self.yes_asks, descending=False, name="yes_asks")
        self._assert_sorted(self.no_asks, descending=False, name="no_asks")

    @property
    def exchange_id(self) -> str:
        return self.market_id

    @staticmethod
    def _assert_sorted(levels: tuple[BookLevel, ...], *, descending: bool, name: str) -> None:
        prices = [level.price for level in levels]
        expected = sorted(prices, reverse=descending)
        if prices != expected:
            raise ValueError(f"{name} must be price-sorted")

    def asks(self, side: Side) -> tuple[BookLevel, ...]:
        return self.yes_asks if side is Side.YES else self.no_asks

    def bids(self, side: Side) -> tuple[BookLevel, ...]:
        return self.yes_bids if side is Side.YES else self.no_bids

    def age_seconds(self, now: datetime | None = None) -> Decimal:
        now = now or utc_now()
        if now.tzinfo is None:
            raise ValueError("now must be timezone-aware")
        return Decimal(str(max(0.0, (now - self.observed_at).total_seconds())))


@dataclass(frozen=True, slots=True)
class MarketContract:
    market_id: str
    title: str
    rules: str = ""
    settlement_source: str = ""
    status: str = "open"
    closes_at: datetime | None = None
    category: str | None = None


@dataclass(frozen=True, slots=True)
class Relationship:
    relation_id: str
    kind: RelationType
    market_ids: tuple[str, ...]
    # Each state is a tuple of bools aligned with market_ids. Only states that
    # are permitted by the contract relationship belong here.
    allowed_states: tuple[tuple[bool, ...], ...]
    source: str = "manual"
    evidence: str = ""

    def __post_init__(self) -> None:
        if len(self.market_ids) < 2:
            raise ValueError("relationship must include at least two markets")
        if len(set(self.market_ids)) != len(self.market_ids):
            raise ValueError("relationship market_ids must be unique")
        if not self.allowed_states:
            raise ValueError("allowed_states cannot be empty")
        width = len(self.market_ids)
        for state in self.allowed_states:
            if len(state) != width:
                raise ValueError("allowed state width does not match market_ids")

    @property
    def exchange_ids(self) -> tuple[str, ...]:
        return self.market_ids


@dataclass(frozen=True, slots=True)
class TradeLeg:
    """One synthetic leg.

    `market_id` is a legacy field name. Super Market execution adapters interpret
    it as the platform `exchangeId`.
    """

    market_id: str
    side: Side
    quantity: Decimal
    max_price: Decimal

    def __post_init__(self) -> None:
        if self.quantity <= ZERO:
            raise ValueError("quantity must be positive")
        if not ZERO < self.max_price < ONE:
            raise ValueError("max_price must be in (0, 1)")

    @property
    def exchange_id(self) -> str:
        return self.market_id


@dataclass(frozen=True, slots=True)
class ExecutionCandidate:
    candidate_id: str
    relationship_id: str
    legs: tuple[TradeLeg, ...]
    guaranteed_payout_per_bundle: Decimal
    cost_per_bundle: Decimal
    executable_edge_per_bundle: Decimal
    max_profitable_quantity: Decimal
    expected_profit: Decimal
    book_age_seconds: Decimal
    theoretical_only: bool = False
    metadata: dict[str, Any] = field(default_factory=dict, compare=False)

    @property
    def roi(self) -> Decimal:
        if self.cost_per_bundle <= ZERO:
            return ZERO
        return self.executable_edge_per_bundle / self.cost_per_bundle


@dataclass(frozen=True, slots=True)
class PortfolioSnapshot:
    cash: Decimal
    market_exposure: dict[str, Decimal]
    open_order_exposure: dict[str, Decimal] = field(default_factory=dict)

    @property
    def total_exposure(self) -> Decimal:
        return sum(self.market_exposure.values(), ZERO) + sum(
            self.open_order_exposure.values(), ZERO
        )


@dataclass(frozen=True, slots=True)
class ThresholdMarket:
    """Normalized Kalshi-style greater-than threshold market (legacy detector)."""

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
    def from_kalshi(cls, raw: dict[str, Any]) -> ThresholdMarket:
        if raw.get("strike_type") != "greater":
            raise ValueError("Only strike_type='greater' is supported")
        strike = to_decimal(raw.get("floor_strike"))
        if strike is None:
            raise ValueError("greater-than market is missing floor_strike")
        return cls(
            ticker=str(raw.get("ticker", "")),
            event_ticker=str(raw.get("event_ticker", "")),
            title=str(raw.get("title", "")),
            strike=strike,
            yes_bid=to_decimal(raw.get("yes_bid_dollars")),
            yes_ask=to_decimal(raw.get("yes_ask_dollars")),
            no_bid=to_decimal(raw.get("no_bid_dollars")),
            no_ask=to_decimal(raw.get("no_ask_dollars")),
            expiration_time=raw.get("expiration_time") or raw.get("expected_expiration_time"),
        )

    @property
    def midpoint(self) -> Decimal | None:
        if self.yes_bid is None or self.yes_ask is None:
            return None
        if self.yes_bid <= ZERO or self.yes_ask <= ZERO:
            return None
        if self.yes_bid > self.yes_ask:
            return None
        return (self.yes_bid + self.yes_ask) / Decimal(2)


def normalize_levels(raw: Iterable[dict[str, Any] | tuple[Any, Any]]) -> tuple[BookLevel, ...]:
    """Parse `[price,size]` or `{price,size|quantity}` levels without guessing units."""
    out: list[BookLevel] = []
    for item in raw:
        if isinstance(item, dict):
            p = item.get("price")
            s = item.get("size", item.get("quantity"))
        else:
            p, s = item
        price, size = to_decimal(p), to_decimal(s)
        if price is None or size is None:
            raise ValueError(f"invalid order-book level: {item!r}")
        out.append(BookLevel(price=price, size=size))
    return tuple(out)
