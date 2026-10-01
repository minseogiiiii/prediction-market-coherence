from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Protocol

from .live import AtomicTradingVenue, OrderRequest, TradingVenue
from .models import ONE, ZERO, BookLevel, OrderBook, normalize_levels, utc_now

TICK = Decimal("0.005")
MIN_LIMIT_PRICE = Decimal("0.005")
MAX_LIMIT_PRICE = Decimal("0.995")


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


def parse_timestamp(value: Any) -> datetime:
    if isinstance(value, (int, float)):
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


@dataclass(frozen=True, slots=True)
class OrderBookSchema:
    """Legacy configurable parser retained for external/replay fixtures."""

    market_id_path: str
    observed_at_path: str
    yes_bids_path: str
    yes_asks_path: str
    no_bids_path: str
    no_asks_path: str

    def parse(self, payload: dict[str, Any]) -> OrderBook:
        market_id = str(get_path(payload, self.market_id_path))
        observed_at = parse_timestamp(get_path(payload, self.observed_at_path))
        yes_bids = tuple(
            sorted(
                normalize_levels(get_path(payload, self.yes_bids_path)),
                key=lambda x: x.price,
                reverse=True,
            )
        )
        no_bids = tuple(
            sorted(
                normalize_levels(get_path(payload, self.no_bids_path)),
                key=lambda x: x.price,
                reverse=True,
            )
        )
        yes_asks = tuple(
            sorted(normalize_levels(get_path(payload, self.yes_asks_path)), key=lambda x: x.price)
        )
        no_asks = tuple(
            sorted(normalize_levels(get_path(payload, self.no_asks_path)), key=lambda x: x.price)
        )
        return OrderBook(market_id, observed_at, yes_bids, yes_asks, no_bids, no_asks)


@dataclass(frozen=True, slots=True)
class ExchangeOrderBookSchema:
    """Parser for official `GET /exchanges/{id}/orderbook` responses.

    The API reports one YES-normalized book. Buying NO at side-relative price q
    is equivalent to selling YES at 1-q, so NO asks are the complements of YES
    bids and NO bids are the complements of YES asks.
    """

    def parse(
        self,
        payload: dict[str, Any],
        *,
        received_at: datetime | None = None,
        tournament_id: str | None = None,
    ) -> OrderBook:
        received = received_at or utc_now()
        if received.tzinfo is None:
            raise ValueError("received_at must be timezone-aware")

        exchange_id = str(_require(payload, "exchangeId"))
        raw_bids = _require_list(payload, "bids")
        raw_asks = _require_list(payload, "asks")
        yes_bids = tuple(
            sorted(normalize_levels(raw_bids), key=lambda level: level.price, reverse=True)
        )
        yes_asks = tuple(sorted(normalize_levels(raw_asks), key=lambda level: level.price))

        no_asks = tuple(
            sorted(
                (BookLevel(price=ONE - level.price, size=level.size) for level in yes_bids),
                key=lambda level: level.price,
            )
        )
        no_bids = tuple(
            sorted(
                (BookLevel(price=ONE - level.price, size=level.size) for level in yes_asks),
                key=lambda level: level.price,
                reverse=True,
            )
        )

        as_of = payload.get("asOf")
        sequence: int | None = None
        observed_at = received
        if as_of is not None:
            if not isinstance(as_of, dict):
                raise TypeError("asOf must be an object or null")
            raw_sequence = _require(as_of, "sequence")
            if not isinstance(raw_sequence, int):
                raise TypeError("asOf.sequence must be an integer")
            sequence = raw_sequence
            observed_at = parse_timestamp(_require(as_of, "at"))

        return OrderBook(
            market_id=exchange_id,
            observed_at=observed_at,
            yes_bids=yes_bids,
            yes_asks=yes_asks,
            no_bids=no_bids,
            no_asks=no_asks,
            source_sequence=sequence,
            received_at=received,
            context_id=tournament_id,
        )


@dataclass(frozen=True, slots=True)
class CombinedMarketOrderBookSchema:
    """Parser for `GET /markets/{id}/orderbook` responses."""

    exchange_schema: ExchangeOrderBookSchema = field(default_factory=ExchangeOrderBookSchema)

    def parse(
        self,
        payload: dict[str, Any],
        *,
        received_at: datetime | None = None,
        tournament_id: str | None = None,
    ) -> dict[str, OrderBook]:
        exchanges = _require_list(payload, "exchanges")
        out: dict[str, OrderBook] = {}
        for exchange in exchanges:
            if not isinstance(exchange, dict):
                raise TypeError("combined orderbook exchange must be an object")
            normalized = {
                "exchangeId": _require(exchange, "exchangeId"),
                "asOf": exchange.get("asOf"),
                "bids": _require_list(exchange, "bids"),
                "asks": _require_list(exchange, "asks"),
            }
            book = self.exchange_schema.parse(
                normalized,
                received_at=received_at,
                tournament_id=tournament_id,
            )
            out[book.exchange_id] = book
        return out


@dataclass(frozen=True, slots=True)
class OrderPayloadSchema:
    """Official `SingleOrderInput` builder."""

    def build(self, order: OrderRequest) -> dict[str, Any]:
        quantity = _integer_quantity(order.quantity)
        price = _limit_price(order.limit_price)
        side = order.side.lower()
        action = order.action.lower()
        if side not in {"yes", "no"}:
            raise ValueError("side must be YES or NO")
        if action not in {"buy", "sell"}:
            raise ValueError("action must be buy or sell")

        payload: dict[str, Any] = {
            "idempotencyKey": order.client_order_id,
            "exchangeId": order.market_id,
            "side": side,
            "action": action,
            "quantity": quantity,
            "price": _number(price),
        }
        if order.expiration_date is not None:
            if order.expiration_date.tzinfo is None:
                raise ValueError("expiration_date must be timezone-aware")
            payload["expirationDate"] = order.expiration_date.astimezone(UTC).isoformat()
        if order.tournament_id:
            payload["tournamentId"] = order.tournament_id
        return payload


@dataclass(frozen=True, slots=True)
class MultiLegPayloadSchema:
    order_schema: OrderPayloadSchema = field(default_factory=OrderPayloadSchema)

    def build(
        self,
        orders: tuple[OrderRequest, ...],
        *,
        idempotency_key: str,
        relationship_constraint: str | None = None,
    ) -> dict[str, Any]:
        if not 1 <= len(orders) <= 10:
            raise ValueError("multi-leg order requires 1 to 10 legs")
        if not idempotency_key:
            raise ValueError("idempotency_key is required")

        legs: list[dict[str, Any]] = []
        seen: set[tuple[str, str | None]] = set()
        for order in orders:
            key = (order.market_id, order.tournament_id)
            if key in seen:
                raise ValueError("duplicate exchange in the same tournament scope")
            seen.add(key)
            leg = self.order_schema.build(order)
            leg.pop("idempotencyKey", None)
            legs.append(leg)

        payload: dict[str, Any] = {
            "legs": legs,
            "idempotencyKey": idempotency_key,
        }
        if relationship_constraint:
            payload["relationshipConstraint"] = relationship_constraint
        return payload


class SusqOrderClient(Protocol):
    async def submit_order(self, payload: dict[str, Any]) -> Any: ...
    async def submit_multi_leg(self, payload: dict[str, Any]) -> Any: ...
    async def get_order(self, order_id: str, /) -> Any: ...
    async def cancel_order(self, order_id: str, /) -> Any: ...


class SusqVenueAdapter(TradingVenue, AtomicTradingVenue):
    """Bridge the generic execution state machines to official API payloads."""

    def __init__(
        self,
        client: SusqOrderClient,
        order_schema: OrderPayloadSchema | None = None,
        multi_leg_schema: MultiLegPayloadSchema | None = None,
    ) -> None:
        self.client = client
        self.order_schema = order_schema or OrderPayloadSchema()
        self.multi_leg_schema = multi_leg_schema or MultiLegPayloadSchema(self.order_schema)

    async def place_order(self, order: OrderRequest) -> dict[str, Any]:
        result = await self.client.submit_order(self.order_schema.build(order))
        return normalize_order_placement(result, requested_quantity=order.quantity)

    async def place_multi_leg(
        self,
        orders: tuple[OrderRequest, ...],
        *,
        idempotency_key: str,
        relationship_constraint: str | None = None,
    ) -> dict[str, Any]:
        payload = self.multi_leg_schema.build(
            orders,
            idempotency_key=idempotency_key,
            relationship_constraint=relationship_constraint,
        )
        result = await self.client.submit_multi_leg(payload)
        if not isinstance(result, dict):
            raise TypeError("multi-leg response must be a JSON object")
        raw_results = result.get("results")
        if not isinstance(raw_results, list):
            raise KeyError("multi-leg response is missing results")
        normalized: list[dict[str, Any]] = []
        for index, item in enumerate(raw_results):
            if not isinstance(item, dict) or not isinstance(item.get("data"), dict):
                raise TypeError(f"multi-leg result {index} is malformed")
            requested = orders[index].quantity if index < len(orders) else None
            normalized.append(
                {
                    "index": int(item.get("index", index)),
                    **normalize_order_placement(item["data"], requested_quantity=requested),
                }
            )
        return {"results": normalized, "raw": result}

    async def get_order(self, order_id: str) -> dict[str, Any]:
        result = await self.client.get_order(order_id)
        if not isinstance(result, dict):
            raise TypeError("order response must be a JSON object")
        return {
            "order_id": str(_require(result, "id")),
            "status": "RESTING" if bool(_require(result, "open")) else "CLOSED",
            "open": bool(result["open"]),
            "raw": result,
        }

    async def cancel_order(self, order_id: str) -> dict[str, Any]:
        result = await self.client.cancel_order(order_id)
        if not isinstance(result, dict):
            raise TypeError("cancel response must be a JSON object")
        return {
            "order_id": str(_require(result, "orderId")),
            "status": "CANCELLED",
            "raw": result,
        }


def normalize_order_placement(
    result: Any,
    *,
    requested_quantity: Decimal | None = None,
) -> dict[str, Any]:
    if not isinstance(result, dict):
        raise TypeError("order response must be a JSON object")
    order_id = result.get("orderId")
    open_order = bool(_require(result, "open"))
    quantity_traded = _decimal(_require(result, "quantityTraded"), "quantityTraded")
    remaining_raw = result.get("remainingQuantity")
    if remaining_raw is not None:
        remaining = _decimal(remaining_raw, "remainingQuantity")
    elif requested_quantity is not None:
        remaining = max(ZERO, requested_quantity - quantity_traded)
    else:
        remaining = ZERO if not open_order else None

    if open_order:
        status = "PARTIAL" if quantity_traded > ZERO else "RESTING"
    elif remaining is not None and remaining == ZERO and quantity_traded > ZERO:
        status = "FILLED"
    elif quantity_traded > ZERO:
        status = "PARTIAL"
    else:
        status = "CLOSED"

    return {
        "order_id": "" if order_id is None else str(order_id),
        "status": status,
        "open": open_order,
        "quantity_traded": quantity_traded,
        "remaining_quantity": remaining,
        "fill_price": result.get("fillPrice"),
        "terminal_reason_code": result.get("terminalReasonCode"),
        "raw": result,
    }


def _require(payload: dict[str, Any], key: str) -> Any:
    if key not in payload:
        raise KeyError(f"missing required field {key!r}")
    return payload[key]


def _require_list(payload: dict[str, Any], key: str) -> list[Any]:
    value = _require(payload, key)
    if not isinstance(value, list):
        raise TypeError(f"{key} must be a list")
    return value


def _decimal(value: Any, name: str) -> Decimal:
    try:
        return Decimal(str(value))
    except Exception as exc:
        raise TypeError(f"{name} must be numeric") from exc


def _integer_quantity(value: Decimal) -> int:
    if value <= ZERO or value != value.to_integral_value():
        raise ValueError("Super Market order quantity must be a positive integer")
    integer = int(value)
    if integer > 2_147_483_647:
        raise ValueError("quantity exceeds signed 32-bit engine limit")
    return integer


def _limit_price(value: Decimal) -> Decimal:
    if not MIN_LIMIT_PRICE <= value <= MAX_LIMIT_PRICE:
        raise ValueError("fresh limit price must be between 0.005 and 0.995")
    if (value / TICK) != (value / TICK).to_integral_value():
        raise ValueError("fresh limit price must be on the 0.005 tick")
    return value


def _number(value: Decimal) -> int | float:
    if value == value.to_integral_value():
        return int(value)
    return float(value)
