from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from typing import Any, Self

import httpx


class SusqApiError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None, payload: Any = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.payload = payload


@dataclass(frozen=True, slots=True)
class EndpointMap:
    """API paths copied from the official Scalar reference.

    The public product guide confirms the capabilities but the dynamic Scalar
    document is not machine-readable in this build environment. We therefore
    deliberately do *not* guess endpoint paths. A caller must provide the exact
    documented paths. This fail-closed design prevents accidental requests to
    wrong endpoints.
    """

    markets: str
    market: str
    orderbook: str
    positions: str
    orders: str
    order: str
    cancel_order: str
    balance: str | None = None

    @classmethod
    def from_env(cls) -> EndpointMap:
        required = {
            "markets": "SUSQ_PATH_MARKETS",
            "market": "SUSQ_PATH_MARKET",
            "orderbook": "SUSQ_PATH_ORDERBOOK",
            "positions": "SUSQ_PATH_POSITIONS",
            "orders": "SUSQ_PATH_ORDERS",
            "order": "SUSQ_PATH_ORDER",
            "cancel_order": "SUSQ_PATH_CANCEL_ORDER",
        }
        values: dict[str, str] = {}
        missing: list[str] = []
        for field, env in required.items():
            value = os.getenv(env)
            if not value:
                missing.append(env)
            else:
                values[field] = value
        if missing:
            raise ValueError("Missing official API endpoint environment variables: " + ", ".join(missing))
        return cls(**values, balance=os.getenv("SUSQ_PATH_BALANCE"))


@dataclass(frozen=True, slots=True)
class AuthConfig:
    header_name: str
    token: str
    prefix: str = ""

    @classmethod
    def from_env(cls) -> AuthConfig:
        token = os.getenv("SUSQ_API_KEY")
        header = os.getenv("SUSQ_AUTH_HEADER")
        if not token or not header:
            raise ValueError("SUSQ_API_KEY and SUSQ_AUTH_HEADER are required")
        return cls(header_name=header, token=token, prefix=os.getenv("SUSQ_AUTH_PREFIX", ""))

    @property
    def header_value(self) -> str:
        return f"{self.prefix}{self.token}"


class SusqClient:
    """Thin, schema-neutral HTTP client for the Predictions Cup API.

    Read requests retry transient failures. Order submission does not retry
    automatically because a network timeout does not prove that an order was not
    accepted. Cancellation may retry 503 because the official changelog states
    that cancel retries are safe when the engine asks the client to retry.
    """

    def __init__(
        self,
        *,
        endpoints: EndpointMap,
        auth: AuthConfig,
        base_url: str = "https://sig.thesuper.market/api/v1",
        timeout: float = 10.0,
        max_read_retries: int = 3,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.endpoints = endpoints
        self.auth = auth
        self.max_read_retries = max_read_retries
        headers = {
            auth.header_name: auth.header_value,
            "User-Agent": "prediction-market-coherence/0.2",
            "Accept": "application/json",
        }
        self._client = httpx.AsyncClient(
            base_url=self.base_url, timeout=timeout, headers=headers, transport=transport
        )

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    @staticmethod
    def _format(path: str, **values: str) -> str:
        try:
            return path.format(**values)
        except KeyError as exc:
            raise ValueError(f"endpoint path requires placeholder {exc.args[0]!r}") from exc

    async def _read_json(self, path: str, *, params: dict[str, Any] | None = None) -> Any:
        delay = 0.15
        last: httpx.Response | None = None
        for attempt in range(self.max_read_retries + 1):
            try:
                response = await self._client.get(path, params=params)
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                if attempt >= self.max_read_retries:
                    raise SusqApiError(f"read failed after retries: {exc}") from exc
                await asyncio.sleep(delay)
                delay *= 2
                continue
            last = response
            if response.status_code in {429, 502, 503, 504} and attempt < self.max_read_retries:
                retry_after = response.headers.get("Retry-After")
                wait = float(retry_after) if retry_after and retry_after.replace(".", "", 1).isdigit() else delay
                await asyncio.sleep(wait)
                delay *= 2
                continue
            if response.is_error:
                raise SusqApiError(
                    f"GET {path} failed with HTTP {response.status_code}",
                    status_code=response.status_code,
                    payload=_safe_json(response),
                )
            return _safe_json(response)
        raise SusqApiError(
            "read failed", status_code=last.status_code if last is not None else None
        )

    async def list_markets(self, **params: Any) -> Any:
        return await self._read_json(self.endpoints.markets, params=params or None)

    async def get_market(self, market_id: str) -> Any:
        return await self._read_json(self._format(self.endpoints.market, market_id=market_id))

    async def get_orderbook(self, market_id: str) -> Any:
        return await self._read_json(self._format(self.endpoints.orderbook, market_id=market_id))

    async def get_positions(self, **params: Any) -> Any:
        return await self._read_json(self.endpoints.positions, params=params or None)

    async def get_orders(self, **params: Any) -> Any:
        return await self._read_json(self.endpoints.orders, params=params or None)

    async def get_order(self, order_id: str) -> Any:
        return await self._read_json(self._format(self.endpoints.order, order_id=order_id))

    async def get_balance(self) -> Any:
        if not self.endpoints.balance:
            raise ValueError("balance endpoint is not configured")
        return await self._read_json(self.endpoints.balance)

    async def submit_order(self, payload: dict[str, Any], *, idempotency_key: str | None = None) -> Any:
        headers = {"Idempotency-Key": idempotency_key} if idempotency_key else None
        try:
            response = await self._client.post(self.endpoints.orders, json=payload, headers=headers)
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            raise SusqApiError(
                "order submission outcome is UNKNOWN after transport failure; reconcile before retrying"
            ) from exc
        if response.is_error:
            raise SusqApiError(
                f"order submission failed with HTTP {response.status_code}",
                status_code=response.status_code,
                payload=_safe_json(response),
            )
        return _safe_json(response)

    async def cancel_order(self, order_id: str, *, max_retries: int = 3) -> Any:
        path = self._format(self.endpoints.cancel_order, order_id=order_id)
        delay = 0.15
        for attempt in range(max_retries + 1):
            try:
                response = await self._client.delete(path)
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                if attempt >= max_retries:
                    raise SusqApiError("cancel transport failure; reconcile order status") from exc
                await asyncio.sleep(delay)
                delay *= 2
                continue
            if response.status_code == 503 and attempt < max_retries:
                retry_after = response.headers.get("Retry-After")
                wait = float(retry_after) if retry_after and retry_after.replace(".", "", 1).isdigit() else delay
                await asyncio.sleep(wait)
                delay *= 2
                continue
            if response.is_error:
                raise SusqApiError(
                    f"cancel failed with HTTP {response.status_code}",
                    status_code=response.status_code,
                    payload=_safe_json(response),
                )
            return _safe_json(response)
        raise SusqApiError("cancel failed after retries")


def _safe_json(response: httpx.Response) -> Any:
    try:
        return response.json()
    except ValueError:
        return {"text": response.text}
