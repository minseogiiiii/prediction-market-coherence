import asyncio
from decimal import Decimal
from typing import Any, cast

import httpx
import pytest

from prediction_market_coherence.client import KalshiClient
from prediction_market_coherence.config import RuntimeConfig
from prediction_market_coherence.susq_client import (
    AuthConfig,
    EndpointMap,
    SusqApiError,
    SusqClient,
)


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class FakeSession:
    def __init__(self):
        self.headers = {}
        self.calls = []
        self.responses = [
            FakeResponse({"markets": [{"ticker": "A"}], "cursor": "n"}),
            FakeResponse({"markets": [{"ticker": "B"}], "cursor": ""}),
        ]

    def get(self, url, params, timeout):
        self.calls.append((url, dict(params), timeout))
        return self.responses.pop(0)


def test_kalshi_client_pagination_and_event_filter():
    client = KalshiClient()
    fake = FakeSession()
    client.session = cast(Any, fake)
    out = list(client.iter_markets(event_ticker="E"))
    assert [x["ticker"] for x in out] == ["A", "B"]
    assert fake.calls[0][1]["event_ticker"] == "E"
    assert fake.calls[1][1]["cursor"] == "n"


def test_kalshi_max_pages_stops():
    client = KalshiClient()
    fake = FakeSession()
    client.session = cast(Any, fake)
    out = list(client.iter_markets(max_pages=1))
    assert [x["ticker"] for x in out] == ["A"]


def test_runtime_config_env(monkeypatch):
    monkeypatch.setenv("PMC_ALLOW_LIVE_TRADING", "1")
    monkeypatch.setenv("PMC_LIVE_ACK", "ok")
    monkeypatch.setenv("PMC_MIN_EDGE", "0.03")
    config = RuntimeConfig.from_env()
    assert config.allow_live_trading
    assert config.acknowledgement == "ok"
    assert config.min_edge == Decimal("0.03")
    assert config.live_enabled("ok")
    assert not config.live_enabled("bad")


def test_endpoint_map_is_bound_to_official_paths():
    endpoints = EndpointMap()
    assert endpoints.markets == "/markets"
    assert endpoints.market == "/markets/{id}"
    assert endpoints.exchange_orderbook == "/exchanges/{id}/orderbook"
    assert endpoints.orders == "/orders"
    assert endpoints.multi_leg_orders == "/orders/multi-leg"
    assert endpoints.relationship_constraints == "/relationships/constraints"


def test_auth_from_env_uses_official_bearer_default(monkeypatch):
    monkeypatch.setenv("SUSQ_API_KEY", "k")
    monkeypatch.delenv("SUSQ_AUTH_HEADER", raising=False)
    monkeypatch.delenv("SUSQ_AUTH_PREFIX", raising=False)
    assert AuthConfig.from_env().header_value == "Bearer k"


def test_auth_requires_key(monkeypatch):
    monkeypatch.delenv("SUSQ_API_KEY", raising=False)
    with pytest.raises(ValueError):
        AuthConfig.from_env()


def test_susq_format_missing_placeholder():
    with pytest.raises(ValueError):
        SusqClient._format("/x/{missing}", id="m")


def test_susq_http_error_has_structured_payload():
    async def handler(req):
        return httpx.Response(401, json={"error": {"code": "INVALID_API_KEY", "message": "bad"}})

    async def scenario():
        async with SusqClient(
            auth=AuthConfig("X", "k"),
            base_url="https://x",
            transport=httpx.MockTransport(handler),
            max_read_retries=0,
        ) as client:
            with pytest.raises(SusqApiError) as info:
                await client.list_markets()
            assert info.value.status_code == 401
            assert info.value.code == "INVALID_API_KEY"
            assert info.value.payload == {
                "error": {"code": "INVALID_API_KEY", "message": "bad"}
            }

    asyncio.run(scenario())
