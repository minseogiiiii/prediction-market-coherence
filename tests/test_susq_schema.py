import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, cast

import pytest

from prediction_market_coherence.live import OrderRequest
from prediction_market_coherence.susq_schema import (
    CombinedMarketOrderBookSchema,
    ExchangeOrderBookSchema,
    MultiLegPayloadSchema,
    OrderBookSchema,
    OrderPayloadSchema,
    SusqVenueAdapter,
    get_path,
    parse_timestamp,
)

D = Decimal


def test_get_path_and_missing():
    assert get_path({"a": {"b": 3}}, "a.b") == 3
    with pytest.raises(KeyError):
        get_path({"a": {}}, "a.b")


def test_legacy_configurable_book_schema_parses_and_sorts():
    payload = {
        "data": {
            "id": "m",
            "ts": "2026-10-01T16:00:00Z",
            "yb": [[0.4, 2], [0.5, 3]],
            "ya": [[0.6, 2], [0.55, 1]],
            "nb": [[0.3, 1]],
            "na": [[0.46, 5]],
        }
    }
    schema = OrderBookSchema("data.id", "data.ts", "data.yb", "data.ya", "data.nb", "data.na")
    book = schema.parse(payload)
    assert book.market_id == "m"
    assert [x.price for x in book.yes_bids] == [D(".5"), D(".4")]
    assert [x.price for x in book.yes_asks] == [D(".55"), D(".6")]
    assert book.observed_at.tzinfo == UTC


def test_official_exchange_book_derives_no_side_from_yes_normalized_book():
    payload = {
        "exchangeId": "36",
        "marketId": "26",
        "asOf": {"sequence": 4817, "at": "2026-10-01T16:00:00.125Z"},
        "depth": 20,
        "bids": [{"price": 0.55, "quantity": 30}, {"price": 0.50, "quantity": 20}],
        "asks": [{"price": 0.60, "quantity": 40}, {"price": 0.65, "quantity": 10}],
        "bestBid": 0.55,
        "bestAsk": 0.60,
        "spread": 0.05,
    }
    book = ExchangeOrderBookSchema().parse(payload, tournament_id="tid")
    assert book.exchange_id == "36"
    assert book.source_sequence == 4817
    assert book.context_id == "tid"
    assert [x.price for x in book.yes_bids] == [D("0.55"), D("0.5")]
    assert [x.price for x in book.yes_asks] == [D("0.6"), D("0.65")]
    assert [x.price for x in book.no_asks] == [D("0.45"), D("0.5")]
    assert [x.price for x in book.no_bids] == [D("0.4"), D("0.35")]
    assert [x.size for x in book.no_asks] == [D("30"), D("20")]


def test_official_book_uses_receive_time_if_asof_is_null():
    received = datetime(2026, 10, 1, 16, 0, tzinfo=UTC)
    payload = {
        "exchangeId": "36",
        "marketId": "26",
        "asOf": None,
        "depth": 20,
        "bids": [],
        "asks": [],
        "bestBid": None,
        "bestAsk": None,
        "spread": None,
    }
    book = ExchangeOrderBookSchema().parse(payload, received_at=received)
    assert book.observed_at == received
    assert book.source_sequence is None


def test_combined_market_orderbook_parses_every_exchange():
    payload = {
        "exchanges": [
            {
                "exchangeId": "36",
                "option": "YES",
                "asOf": {"sequence": 1, "at": "2026-10-01T16:00:00Z"},
                "impliedProbability": 0.5,
                "bids": [{"price": 0.45, "quantity": 1}],
                "asks": [{"price": 0.55, "quantity": 1}],
            },
            {
                "exchangeId": "37",
                "option": "NO",
                "asOf": {"sequence": 2, "at": "2026-10-01T16:00:01Z"},
                "impliedProbability": 0.4,
                "bids": [{"price": 0.35, "quantity": 2}],
                "asks": [{"price": 0.45, "quantity": 3}],
            },
        ],
        "overround": 0.9,
        "hasArbitrageOpportunity": True,
    }
    books = CombinedMarketOrderBookSchema().parse(payload)
    assert set(books) == {"36", "37"}
    assert books["37"].source_sequence == 2


def test_timestamp_rejects_naive():
    with pytest.raises(ValueError):
        parse_timestamp("2026-10-01T12:00:00")


def test_official_order_payload_and_tick_validation():
    schema = OrderPayloadSchema()
    payload = schema.build(
        OrderRequest(
            "36",
            "YES",
            D("10"),
            D(".42"),
            "abc",
            tournament_id="tid",
        )
    )
    assert payload == {
        "idempotencyKey": "abc",
        "exchangeId": "36",
        "side": "yes",
        "action": "buy",
        "quantity": 10,
        "price": 0.42,
        "tournamentId": "tid",
    }
    with pytest.raises(ValueError, match="0.005 tick"):
        schema.build(OrderRequest("36", "YES", D("10"), D(".421"), "bad"))
    with pytest.raises(ValueError, match="positive integer"):
        schema.build(OrderRequest("36", "YES", D("1.5"), D(".42"), "bad"))


def test_multi_leg_payload_uses_one_idempotency_key_and_no_duplicate_exchange():
    orders = (
        OrderRequest("36", "YES", D("10"), D(".42"), "leg-a", tournament_id="tid"),
        OrderRequest("37", "NO", D("10"), D(".45"), "leg-b", tournament_id="tid"),
    )
    payload = MultiLegPayloadSchema().build(
        orders,
        idempotency_key="bundle-1",
        relationship_constraint="rel-id",
    )
    assert payload["idempotencyKey"] == "bundle-1"
    assert payload["relationshipConstraint"] == "rel-id"
    assert [leg["exchangeId"] for leg in payload["legs"]] == ["36", "37"]
    assert all("idempotencyKey" not in leg for leg in payload["legs"])
    with pytest.raises(ValueError, match="duplicate exchange"):
        MultiLegPayloadSchema().build((orders[0], orders[0]), idempotency_key="bundle-2")


def test_venue_adapter_normalizes_single_and_multi_leg_responses():
    class Client:
        async def submit_order(self, payload):
            return {
                "orderId": 1,
                "exchangeId": payload["exchangeId"],
                "open": False,
                "remainingQuantity": 0,
                "quantityTraded": payload["quantity"],
                "totalCost": 4.2,
                "fillPrice": 0.42,
                "all": None,
            }

        async def submit_multi_leg(self, payload):
            return {
                "results": [
                    {
                        "index": i,
                        "data": {
                            "orderId": i + 1,
                            "exchangeId": leg["exchangeId"],
                            "open": False,
                            "remainingQuantity": 0,
                            "quantityTraded": leg["quantity"],
                            "totalCost": 1,
                            "fillPrice": leg["price"],
                            "all": None,
                        },
                    }
                    for i, leg in enumerate(payload["legs"])
                ]
            }

        async def get_order(self, oid):
            return {
                "id": int(oid),
                "exchangeId": "36",
                "side": "yes",
                "action": "buy",
                "quantity": 10,
                "priceLimit": 0.42,
                "open": False,
                "createdAt": "2026-10-01T12:00:00Z",
                "expirationDate": None,
            }

        async def cancel_order(self, oid):
            return {"orderId": int(oid), "tournamentId": None, "message": "cancelled"}

    async def scenario():
        adapter = SusqVenueAdapter(cast(Any, Client()))
        single = await adapter.place_order(OrderRequest("36", "YES", D("2"), D(".4"), "c1"))
        assert single["status"] == "FILLED"
        assert single["order_id"] == "1"

        orders = (
            OrderRequest("36", "YES", D("2"), D(".4"), "a"),
            OrderRequest("37", "NO", D("2"), D(".45"), "b"),
        )
        multi = await adapter.place_multi_leg(orders, idempotency_key="bundle")
        assert [x["status"] for x in multi["results"]] == ["FILLED", "FILLED"]
        assert (await adapter.get_order("1"))["status"] == "CLOSED"
        assert (await adapter.cancel_order("1"))["status"] == "CANCELLED"

    asyncio.run(scenario())
