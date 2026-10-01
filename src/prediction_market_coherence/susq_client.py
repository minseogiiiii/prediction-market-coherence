from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from typing import Any, Self

import httpx

OFFICIAL_BASE_URL = "https://www.thesuper.market/api/v1"


class SusqApiError(RuntimeError):
    """Structured Super Market API failure."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        code: str | None = None,
        payload: Any = None,
        retryable: bool = False,
        outcome_unknown: bool = False,
        retry_after: float | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.payload = payload
        self.retryable = retryable
        self.outcome_unknown = outcome_unknown
        self.retry_after = retry_after


@dataclass(frozen=True, slots=True)
class EndpointMap:
    """Exact supported `/api/v1` routes from the official OpenAPI reference."""

    markets: str = "/markets"
    market: str = "/markets/{id}"
    market_orderbook: str = "/markets/{id}/orderbook"
    exchanges: str = "/exchanges"
    exchange_price: str = "/exchanges/{id}/price"
    exchange_orderbook: str = "/exchanges/{id}/orderbook"
    bulk_prices: str = "/exchanges/prices"
    orders: str = "/orders"
    multi_leg_orders: str = "/orders/multi-leg"
    batch_orders: str = "/orders/batch"
    order: str = "/orders/{id}"
    order_fills: str = "/orders/{id}/fills"
    cancel_all: str = "/orders/cancel-all"
    account: str = "/account"
    positions: str = "/portfolio/positions"
    pnl: str = "/portfolio/pnl"
    fills: str = "/portfolio/fills"
    collateral: str = "/portfolio/collateral"
    tournaments: str = "/tournaments"
    tournament: str = "/tournaments/{slug}"
    tournament_markets: str = "/tournaments/{slug}/markets"
    tournament_positions: str = "/tournaments/{slug}/portfolio/positions"
    tournament_pnl: str = "/tournaments/{slug}/portfolio/pnl"
    relationships: str = "/relationships"
    relationship_graph: str = "/relationships/graph"
    relationship_constraints: str = "/relationships/constraints"
    realtime_token: str = "/realtime/token"


@dataclass(frozen=True, slots=True)
class AuthConfig:
    header_name: str
    token: str
    prefix: str = ""

    @classmethod
    def from_env(cls) -> AuthConfig:
        token = os.getenv("SUSQ_API_KEY")
        if not token:
            raise ValueError("SUSQ_API_KEY is required")
        header = os.getenv("SUSQ_AUTH_HEADER", "Authorization")
        default_prefix = "Bearer " if header.lower() == "authorization" else ""
        prefix = os.getenv("SUSQ_AUTH_PREFIX", default_prefix)
        return cls(header_name=header, token=token, prefix=prefix)

    @property
    def header_value(self) -> str:
        return f"{self.prefix}{self.token}"


class SusqClient:
    """Official Super Market `/api/v1` client.

    Read requests retry transient 429/503 responses. Writes never invent a new
    idempotency key and do not blindly retry ambiguous outcomes. The caller can
    safely retry the *identical* order payload with the same `idempotencyKey`
    after inspecting `SusqApiError.retryable` / `outcome_unknown`.
    """

    def __init__(
        self,
        *,
        auth: AuthConfig,
        endpoints: EndpointMap | None = None,
        base_url: str | None = None,
        timeout: float = 10.0,
        max_read_retries: int = 3,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = (base_url or os.getenv("SUSQ_BASE_URL") or OFFICIAL_BASE_URL).rstrip("/")
        self.endpoints = endpoints or EndpointMap()
        self.auth = auth
        self.max_read_retries = max_read_retries
        headers = {
            auth.header_name: auth.header_value,
            "User-Agent": "prediction-market-coherence/0.3",
            "Accept": "application/json",
        }
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=timeout,
            headers=headers,
            transport=transport,
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
        for attempt in range(self.max_read_retries + 1):
            try:
                response = await self._client.get(path, params=_clean_params(params))
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                if attempt >= self.max_read_retries:
                    raise SusqApiError(
                        f"read failed after retries: {exc}",
                        retryable=True,
                    ) from exc
                await asyncio.sleep(delay)
                delay *= 2
                continue

            if response.status_code in {429, 503} and attempt < self.max_read_retries:
                await asyncio.sleep(_retry_wait(response, delay))
                delay *= 2
                continue
            if response.is_error:
                raise _api_error(response, method="GET", path=path)
            return _safe_json(response)
        raise SusqApiError("read failed", retryable=True)

    async def _write_json(
        self,
        method: str,
        path: str,
        *,
        payload: dict[str, Any] | None = None,
    ) -> Any:
        try:
            if payload is None:
                response = await self._client.request(method, path)
            else:
                response = await self._client.request(method, path, json=payload)
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            raise SusqApiError(
                f"{method} {path} transport failure; outcome may be unknown",
                retryable=True,
                outcome_unknown=True,
            ) from exc
        if response.is_error:
            raise _api_error(response, method=method, path=path)
        return _safe_json(response)

    async def list_markets(self, **params: Any) -> Any:
        return await self._read_json(self.endpoints.markets, params=params or None)

    async def get_market(self, market_id: str, *, tournament_id: str | None = None) -> Any:
        return await self._read_json(
            self._format(self.endpoints.market, id=market_id),
            params={"tournamentId": tournament_id},
        )

    async def get_market_orderbook(
        self,
        market_id: str,
        *,
        tournament_id: str | None = None,
        depth: int = 200,
    ) -> Any:
        return await self._read_json(
            self._format(self.endpoints.market_orderbook, id=market_id),
            params={"tournamentId": tournament_id, "depth": depth},
        )

    async def list_exchanges(self, **params: Any) -> Any:
        return await self._read_json(self.endpoints.exchanges, params=params or None)

    async def get_exchange_price(
        self,
        exchange_id: str,
        *,
        tournament_id: str | None = None,
    ) -> Any:
        return await self._read_json(
            self._format(self.endpoints.exchange_price, id=exchange_id),
            params={"tournamentId": tournament_id},
        )

    async def get_exchange_orderbook(
        self,
        exchange_id: str,
        *,
        tournament_id: str | None = None,
        depth: int = 200,
    ) -> Any:
        return await self._read_json(
            self._format(self.endpoints.exchange_orderbook, id=exchange_id),
            params={"tournamentId": tournament_id, "depth": depth},
        )

    async def get_bulk_prices(
        self,
        exchange_ids: list[str] | tuple[str, ...],
        *,
        tournament_id: str | None = None,
    ) -> Any:
        if not exchange_ids:
            raise ValueError("exchange_ids cannot be empty")
        if len(exchange_ids) > 100:
            raise ValueError("bulk price endpoint accepts at most 100 exchange IDs")
        return await self._read_json(
            self.endpoints.bulk_prices,
            params={"ids": ",".join(exchange_ids), "tournamentId": tournament_id},
        )

    async def get_account(self) -> Any:
        return await self._read_json(self.endpoints.account)

    async def list_tournaments(self, **params: Any) -> Any:
        return await self._read_json(self.endpoints.tournaments, params=params or None)

    async def get_tournament(self, slug: str) -> Any:
        return await self._read_json(self._format(self.endpoints.tournament, slug=slug))

    async def list_tournament_markets(self, slug: str, **params: Any) -> Any:
        return await self._read_json(
            self._format(self.endpoints.tournament_markets, slug=slug),
            params=params or None,
        )

    async def get_positions(self) -> Any:
        return await self._read_json(self.endpoints.positions)

    async def get_tournament_positions(self, slug: str) -> Any:
        return await self._read_json(
            self._format(self.endpoints.tournament_positions, slug=slug)
        )

    async def get_pnl(self, *, period: str = "quarter") -> Any:
        return await self._read_json(self.endpoints.pnl, params={"period": period})

    async def get_tournament_pnl(self, slug: str, *, period: str = "quarter") -> Any:
        return await self._read_json(
            self._format(self.endpoints.tournament_pnl, slug=slug),
            params={"period": period},
        )

    async def get_collateral(self, *, tournament_id: str | None = None) -> Any:
        return await self._read_json(
            self.endpoints.collateral,
            params={"tournamentId": tournament_id},
        )

    async def get_orders(self, **params: Any) -> Any:
        return await self._read_json(self.endpoints.orders, params=params or None)

    async def get_order(self, order_id: str) -> Any:
        return await self._read_json(self._format(self.endpoints.order, id=order_id))

    async def get_order_fills(self, order_id: str, **params: Any) -> Any:
        return await self._read_json(
            self._format(self.endpoints.order_fills, id=order_id),
            params=params or None,
        )

    async def get_fills(self, **params: Any) -> Any:
        return await self._read_json(self.endpoints.fills, params=params or None)

    async def get_relationships(self, **params: Any) -> Any:
        return await self._read_json(self.endpoints.relationships, params=params or None)

    async def get_relationship_graph(
        self,
        market_id: str,
        *,
        depth: int = 2,
        tournament_id: str | None = None,
    ) -> Any:
        return await self._read_json(
            self.endpoints.relationship_graph,
            params={"marketId": market_id, "depth": depth, "tournamentId": tournament_id},
        )

    async def get_relationship_constraints(self, **params: Any) -> Any:
        return await self._read_json(
            self.endpoints.relationship_constraints,
            params=params or None,
        )

    async def mint_realtime_token(self) -> Any:
        return await self._write_json("POST", self.endpoints.realtime_token, payload=None)

    async def submit_order(self, payload: dict[str, Any]) -> Any:
        _require_idempotency_key(payload)
        return await self._write_json("POST", self.endpoints.orders, payload=payload)

    async def submit_multi_leg(self, payload: dict[str, Any]) -> Any:
        _require_idempotency_key(payload)
        return await self._write_json("POST", self.endpoints.multi_leg_orders, payload=payload)

    async def cancel_order(self, order_id: str, *, max_retries: int = 3) -> Any:
        path = self._format(self.endpoints.order, id=order_id)
        delay = 0.15
        for attempt in range(max_retries + 1):
            try:
                response = await self._client.delete(path)
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                if attempt >= max_retries:
                    raise SusqApiError(
                        "cancel transport failure; reconcile order status",
                        retryable=True,
                        outcome_unknown=True,
                    ) from exc
                await asyncio.sleep(delay)
                delay *= 2
                continue

            if response.status_code == 503 and attempt < max_retries:
                await asyncio.sleep(_retry_wait(response, delay))
                delay *= 2
                continue
            if response.is_error:
                raise _api_error(response, method="DELETE", path=path)
            return _safe_json(response)
        raise SusqApiError("cancel failed after retries", retryable=True)

    async def cancel_all(self, payload: dict[str, Any], *, max_retries: int = 3) -> Any:
        delay = 0.15
        for attempt in range(max_retries + 1):
            try:
                response = await self._client.post(self.endpoints.cancel_all, json=payload)
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                if attempt >= max_retries:
                    raise SusqApiError(
                        "cancel-all transport failure; reconcile open orders",
                        retryable=True,
                        outcome_unknown=True,
                    ) from exc
                await asyncio.sleep(delay)
                delay *= 2
                continue
            if response.status_code == 503 and attempt < max_retries:
                await asyncio.sleep(_retry_wait(response, delay))
                delay *= 2
                continue
            if response.is_error:
                raise _api_error(response, method="POST", path=self.endpoints.cancel_all)
            return _safe_json(response)
        raise SusqApiError("cancel-all failed after retries", retryable=True)


def _require_idempotency_key(payload: dict[str, Any]) -> None:
    value = payload.get("idempotencyKey")
    if not isinstance(value, str) or not value.strip():
        raise ValueError("official order payload requires a non-empty idempotencyKey")


def _clean_params(params: dict[str, Any] | None) -> dict[str, Any] | None:
    if not params:
        return None
    return {key: value for key, value in params.items() if value is not None}


def _safe_json(response: httpx.Response) -> Any:
    try:
        return response.json()
    except ValueError:
        return {"text": response.text}


def _error_code(payload: Any) -> str | None:
    if not isinstance(payload, dict):
        return None
    error = payload.get("error")
    if not isinstance(error, dict):
        return None
    code = error.get("code")
    return str(code) if code else None


def _retry_wait(response: httpx.Response, fallback: float) -> float:
    raw = response.headers.get("Retry-After")
    if raw:
        try:
            return max(float(raw), 0.0)
        except ValueError:
            pass
    return fallback


def _api_error(response: httpx.Response, *, method: str, path: str) -> SusqApiError:
    payload = _safe_json(response)
    code = _error_code(payload)
    retry_after = _retry_wait(response, 0.0) if "Retry-After" in response.headers else None
    retryable = response.status_code == 429 or code in {
        "RATE_LIMITED",
        "REQUEST_IN_FLIGHT",
        "ORDER_STATUS_UNKNOWN",
        "TX_CONFLICT",
        "SERVICE_UNAVAILABLE",
    }
    outcome_unknown = code == "ORDER_STATUS_UNKNOWN" or (
        method in {"POST", "DELETE"} and response.status_code >= 500
    )
    return SusqApiError(
        f"{method} {path} failed with HTTP {response.status_code}"
        + (f" ({code})" if code else ""),
        status_code=response.status_code,
        code=code,
        payload=payload,
        retryable=retryable,
        outcome_unknown=outcome_unknown,
        retry_after=retry_after,
    )
