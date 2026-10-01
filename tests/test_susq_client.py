import asyncio

import httpx
import pytest

from prediction_market_coherence.susq_client import (
    OFFICIAL_BASE_URL,
    AuthConfig,
    SusqApiError,
    SusqClient,
)


def run(coro):
    return asyncio.run(coro)


def test_auth_defaults_to_official_bearer(monkeypatch):
    monkeypatch.setenv("SUSQ_API_KEY", "secret")
    monkeypatch.delenv("SUSQ_AUTH_HEADER", raising=False)
    monkeypatch.delenv("SUSQ_AUTH_PREFIX", raising=False)
    auth = AuthConfig.from_env()
    assert auth.header_name == "Authorization"
    assert auth.header_value == "Bearer secret"
    assert OFFICIAL_BASE_URL == "https://www.thesuper.market/api/v1"


def test_exchange_book_uses_official_path_and_tournament_context():
    seen = {}

    async def handler(req):
        seen["path"] = req.url.path
        seen["query"] = dict(req.url.params)
        seen["auth"] = req.headers.get("Authorization")
        return httpx.Response(200, json={"ok": True})

    async def scenario():
        async with SusqClient(
            auth=AuthConfig("Authorization", "secret", "Bearer "),
            base_url="https://example.test/api/v1",
            transport=httpx.MockTransport(handler),
        ) as client:
            return await client.get_exchange_orderbook(
                "36", tournament_id="tid", depth=200
            )

    assert run(scenario()) == {"ok": True}
    assert seen == {
        "path": "/api/v1/exchanges/36/orderbook",
        "query": {"tournamentId": "tid", "depth": "200"},
        "auth": "Bearer secret",
    }


def test_read_retries_503_then_succeeds():
    calls = 0

    async def handler(req):
        nonlocal calls
        calls += 1
        if calls < 3:
            return httpx.Response(
                503,
                json={"error": {"code": "SERVICE_UNAVAILABLE", "message": "retry"}},
            )
        return httpx.Response(200, json={"data": []})

    async def scenario():
        async with SusqClient(
            auth=AuthConfig("X-API-Key", "secret"),
            base_url="https://x",
            transport=httpx.MockTransport(handler),
            max_read_retries=3,
        ) as client:
            return await client.list_markets()

    assert run(scenario()) == {"data": []}
    assert calls == 3


def test_submit_requires_idempotency_key():
    async def scenario():
        async with SusqClient(
            auth=AuthConfig("X-API-Key", "secret"),
            base_url="https://x",
            transport=httpx.MockTransport(lambda req: httpx.Response(200, json={})),
        ) as client:
            with pytest.raises(ValueError, match="idempotencyKey"):
                await client.submit_order({"exchangeId": "36"})

    run(scenario())


def test_502_order_status_unknown_is_classified_for_safe_same_key_retry():
    async def handler(req):
        return httpx.Response(
            502,
            json={
                "error": {
                    "code": "ORDER_STATUS_UNKNOWN",
                    "message": "engine confirmation timed out",
                }
            },
        )

    async def scenario():
        async with SusqClient(
            auth=AuthConfig("X-API-Key", "secret"),
            base_url="https://x",
            transport=httpx.MockTransport(handler),
        ) as client:
            with pytest.raises(SusqApiError) as info:
                await client.submit_order({"idempotencyKey": "k", "exchangeId": "36"})
            error = info.value
            assert error.code == "ORDER_STATUS_UNKNOWN"
            assert error.retryable
            assert error.outcome_unknown

    run(scenario())


def test_order_transport_failure_is_unknown_and_not_blind_retried():
    calls = 0

    async def handler(req):
        nonlocal calls
        calls += 1
        raise httpx.ReadTimeout("timeout")

    async def scenario():
        async with SusqClient(
            auth=AuthConfig("X-API-Key", "secret"),
            base_url="https://x",
            transport=httpx.MockTransport(handler),
        ) as client:
            with pytest.raises(SusqApiError) as info:
                await client.submit_order({"idempotencyKey": "k", "exchangeId": "36"})
            assert info.value.outcome_unknown
            assert info.value.retryable

    run(scenario())
    assert calls == 1


def test_cancel_retries_503():
    calls = 0

    async def handler(req):
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(
                503,
                json={"error": {"code": "SERVICE_UNAVAILABLE", "message": "retry"}},
            )
        return httpx.Response(200, json={"orderId": 1001, "tournamentId": None, "message": "ok"})

    async def scenario():
        async with SusqClient(
            auth=AuthConfig("X-API-Key", "secret"),
            base_url="https://x",
            transport=httpx.MockTransport(handler),
        ) as client:
            return await client.cancel_order("1001")

    assert run(scenario())["orderId"] == 1001
    assert calls == 2
