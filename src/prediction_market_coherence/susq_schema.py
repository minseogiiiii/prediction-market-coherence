from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Protocol

from .live import OrderRequest, TradingVenue
from .models import OrderBook, normalize_levels


def get_path(payload: Any, path: str) -> Any:
    """Resolve a dot-separated path without silently swallowing schema changes."""
    current = payload
    if not path:
        return current
    for part in path.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            raise KeyError(f"missing JSON path {path!r} at {part!r}")
    return current


@dataclass(frozen=True, slots=True)
class OrderBookSchema:
    market_id_path: str
    observed_at_path: str
    yes_bids_path: str
    yes_asks_path: str
    no_bids_path: str
    no_asks_path: str

    def parse(self, payload: dict[str, Any]) -> OrderBook:
        market_id = str(get_path(payload, self.market_id_path))
        raw_time = get_path(payload, self.observed_at_path)
        observed_at = parse_timestamp(raw_time)
        yes_bids = tuple(sorted(normalize_levels(get_path(payload, self.yes_bids_path)), key=lambda x: x.price, reverse=True))
        no_bids = tuple(sorted(normalize_levels(get_path(payload, self.no_bids_path)), key=lambda x: x.price, reverse=True))
        yes_asks = tuple(sorted(normalize_levels(get_path(payload, self.yes_asks_path)), key=lambda x: x.price))
        no_asks = tuple(sorted(normalize_levels(get_path(payload, self.no_asks_path)), key=lambda x: x.price))
        return OrderBook(market_id, observed_at, yes_bids, yes_asks, no_bids, no_asks)


@dataclass(frozen=True, slots=True)
class OrderPayloadSchema:
    market_id_field: str
    side_field: str
    quantity_field: str
    price_field: str
    order_type_field: str | None = None
    limit_order_value: str = "limit"
    client_order_id_field: str | None = None

    def build(self, order: OrderRequest) -> dict[str, Any]:
        payload: dict[str, Any] = {
            self.market_id_field: order.market_id,
            self.side_field: order.side,
            self.quantity_field: _number(order.quantity),
            self.price_field: _number(order.limit_price),
        }
        if self.order_type_field:
            payload[self.order_type_field] = self.limit_order_value
        if self.client_order_id_field:
            payload[self.client_order_id_field] = order.client_order_id
        return payload


class SusqOrderClient(Protocol):
    async def submit_order(
        self,
        payload: dict[str, Any],
        *,
        idempotency_key: str | None = None,
    ) -> Any: ...

    async def get_order(self, order_id: str, /) -> Any: ...

    async def cancel_order(self, order_id: str, /) -> Any: ...


class SusqVenueAdapter(TradingVenue):
    """Bridge the generic state machine to the official API after schema capture."""

    def __init__(self, client: SusqOrderClient, order_schema: OrderPayloadSchema) -> None:
        self.client = client
        self.order_schema = order_schema

    async def place_order(self, order: OrderRequest) -> dict[str, Any]:
        result = await self.client.submit_order(
            self.order_schema.build(order), idempotency_key=order.client_order_id
        )
        if not isinstance(result, dict):
            raise TypeError("order response must be a JSON object")
        return result

    async def get_order(self, order_id: str) -> dict[str, Any]:
        result = await self.client.get_order(order_id)
        if not isinstance(result, dict):
            raise TypeError("order response must be a JSON object")
        return result

    async def cancel_order(self, order_id: str) -> dict[str, Any]:
        result = await self.client.cancel_order(order_id)
        if not isinstance(result, dict):
            raise TypeError("cancel response must be a JSON object")
        return result


def parse_timestamp(value: Any) -> datetime:
    if isinstance(value, (int, float)):
        # Treat numeric values as unix seconds. Milliseconds must be explicitly
        # normalized by the schema owner; guessing units is forbidden.
        return datetime.fromtimestamp(value, tz=UTC)
    if not isinstance(value, str):
        raise TypeError("timestamp must be ISO-8601 string or unix seconds")
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        raise ValueError("timestamp must include timezone")
    return parsed.astimezone(UTC)


def _number(value: Decimal) -> int | float:
    if value == value.to_integral_value():
        return int(value)
    return float(value)
