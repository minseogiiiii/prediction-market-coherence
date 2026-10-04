from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, Protocol, TypeVar

from .models import ZERO, BookLevel, OrderBook, utc_now
from .storage import CollectionMetric, CollectionRequest, ResearchStore
from .susq_client import SusqApiError
from .susq_schema import ExchangeOrderBookSchema

T = TypeVar("T")


class SusqReadClient(Protocol):
    async def get_tournament(self, slug: str) -> Any: ...

    async def list_markets(self, **params: Any) -> Any: ...

    async def get_exchange_orderbook(
        self,
        exchange_id: str,
        *,
        tournament_id: str | None = None,
        depth: int = 200,
    ) -> Any: ...


class WaitLimiter(Protocol):
    async def wait(self) -> None: ...


@dataclass(frozen=True, slots=True)
class ExchangeTarget:
    market_id: str
    exchange_id: str


@dataclass(frozen=True, slots=True)
class CollectionConfig:
    target_snapshots: int = 1_000
    market_limit: int = 10
    depth: int = 200
    reads_per_minute: float = 80.0
    max_no_progress_rounds: int = 5
    progress_every: int = 25

    def __post_init__(self) -> None:
        if self.target_snapshots <= 0:
            raise ValueError("target_snapshots must be positive")
        if not 1 <= self.market_limit <= 100:
            raise ValueError("market_limit must be between 1 and 100")
        if not 1 <= self.depth <= 200:
            raise ValueError("depth must be between 1 and 200")
        if not 0 < self.reads_per_minute <= 100:
            raise ValueError("reads_per_minute must be in (0, 100]")
        if self.max_no_progress_rounds <= 0:
            raise ValueError("max_no_progress_rounds must be positive")
        if self.progress_every <= 0:
            raise ValueError("progress_every must be positive")


@dataclass(frozen=True, slots=True)
class CollectionProgress:
    snapshots: int
    target_snapshots: int
    reads: int
    request_failures: int
    elapsed_seconds: float


@dataclass(frozen=True, slots=True)
class CollectionSummary:
    tournament_id: str
    selected_markets: int
    selected_exchanges: int
    snapshots: int
    reads: int
    request_failures: int
    schema_failures: int
    null_asof: int
    sequence_regressions: int
    elapsed_seconds: float


class ReadRateLimiter:
    """Deterministic spacing limiter for the documented per-key read budget."""

    def __init__(self, reads_per_minute: float = 80.0) -> None:
        if not 0 < reads_per_minute <= 100:
            raise ValueError("reads_per_minute must be in (0, 100]")
        self.interval_seconds = 60.0 / reads_per_minute
        self._next_allowed = 0.0
        self._lock = asyncio.Lock()

    def reserve_delay(self, now: float) -> float:
        delay = max(0.0, self._next_allowed - now)
        slot = now + delay
        self._next_allowed = slot + self.interval_seconds
        return delay

    async def wait(self) -> None:
        async with self._lock:
            delay = self.reserve_delay(time.monotonic())
            if delay > 0:
                await asyncio.sleep(delay)


@dataclass(slots=True)
class _QuoteState:
    sequence: int | None
    fingerprint: tuple[Decimal | None, ...]
    changed_at: datetime


class BookTelemetryTracker:
    """Tracks sequence monotonicity and top-of-book quote lifetime per exchange."""

    def __init__(self) -> None:
        self._state: dict[str, _QuoteState] = {}

    def observe(
        self,
        book: OrderBook,
        *,
        request_id: int,
        tournament_id: str,
        market_id: str,
    ) -> CollectionMetric:
        now = book.received_at or utc_now()
        best_bid = _best(book.yes_bids)
        best_ask = _best(book.yes_asks)
        bid_price = best_bid.price if best_bid else None
        ask_price = best_ask.price if best_ask else None
        spread = ask_price - bid_price if bid_price is not None and ask_price is not None else None
        fingerprint = (
            bid_price,
            best_bid.size if best_bid else None,
            ask_price,
            best_ask.size if best_ask else None,
        )

        previous = self._state.get(book.exchange_id)
        sequence_delta: int | None = None
        sequence_regression = False
        quote_changed = True
        quote_age_seconds = 0.0
        previous_quote_lifetime_seconds: float | None = None
        changed_at = now

        if previous is not None:
            if book.source_sequence is not None and previous.sequence is not None:
                sequence_delta = book.source_sequence - previous.sequence
                sequence_regression = sequence_delta < 0

            if fingerprint == previous.fingerprint:
                quote_changed = False
                changed_at = previous.changed_at
                quote_age_seconds = max(0.0, (now - previous.changed_at).total_seconds())
            else:
                previous_quote_lifetime_seconds = max(
                    0.0,
                    (now - previous.changed_at).total_seconds(),
                )

        self._state[book.exchange_id] = _QuoteState(
            sequence=book.source_sequence,
            fingerprint=fingerprint,
            changed_at=changed_at,
        )

        return CollectionMetric(
            request_id=request_id,
            observed_at=now,
            tournament_id=tournament_id,
            market_id=market_id,
            exchange_id=book.exchange_id,
            source_sequence=book.source_sequence,
            sequence_delta=sequence_delta,
            sequence_regression=sequence_regression,
            asof_null=book.source_sequence is None,
            yes_best_bid=bid_price,
            yes_best_ask=ask_price,
            yes_spread=spread,
            bid_levels=len(book.yes_bids),
            ask_levels=len(book.yes_asks),
            bid_quantity=sum((level.size for level in book.yes_bids), ZERO),
            ask_quantity=sum((level.size for level in book.yes_asks), ZERO),
            quote_changed=quote_changed,
            quote_age_seconds=quote_age_seconds,
            previous_quote_lifetime_seconds=previous_quote_lifetime_seconds,
        )


class ProductionBookCollector:
    """Read-only exchange-book collector with explicit tournament context."""

    def __init__(
        self,
        client: SusqReadClient,
        store: ResearchStore,
        *,
        tournament_slug: str,
        config: CollectionConfig | None = None,
        limiter: WaitLimiter | None = None,
        schema: ExchangeOrderBookSchema | None = None,
        on_progress: Callable[[CollectionProgress], None] | None = None,
    ) -> None:
        if not tournament_slug.strip():
            raise ValueError("tournament_slug is required")
        self.client = client
        self.store = store
        self.tournament_slug = tournament_slug
        self.config = config or CollectionConfig()
        self.limiter = limiter or ReadRateLimiter(self.config.reads_per_minute)
        self.schema = schema or ExchangeOrderBookSchema()
        self.telemetry = BookTelemetryTracker()
        self.on_progress = on_progress
        self._reads = 0

    async def run(self) -> CollectionSummary:
        started = time.monotonic()

        tournament = await self._paced(self.client.get_tournament(self.tournament_slug))
        if not isinstance(tournament, dict):
            raise TypeError("tournament response must be a JSON object")
        tournament_id = str(tournament.get("id") or "")
        if not tournament_id:
            raise KeyError("tournament response is missing id")

        markets_payload = await self._paced(
            self.client.list_markets(
                status="open",
                limit=100,
                tournamentId=tournament_id,
            )
        )
        targets = _select_exchange_targets(markets_payload, self.config.market_limit)
        if not targets:
            raise RuntimeError("no open tournament exchanges were discovered")

        selected_markets = len({target.market_id for target in targets})
        snapshots = 0
        request_failures = 0
        schema_failures = 0
        null_asof = 0
        sequence_regressions = 0
        no_progress_rounds = 0
        next_progress = min(self.config.progress_every, self.config.target_snapshots)

        while snapshots < self.config.target_snapshots:
            before_round = snapshots

            for target in targets:
                if snapshots >= self.config.target_snapshots:
                    break

                await self.limiter.wait()
                self._reads += 1
                request_started = time.perf_counter()

                try:
                    payload = await self.client.get_exchange_orderbook(
                        target.exchange_id,
                        tournament_id=tournament_id,
                        depth=self.config.depth,
                    )
                except SusqApiError as exc:
                    latency_ms = (time.perf_counter() - request_started) * 1_000
                    request_failures += 1
                    self.store.record_collection_request(
                        CollectionRequest(
                            observed_at=utc_now(),
                            tournament_id=tournament_id,
                            market_id=target.market_id,
                            exchange_id=target.exchange_id,
                            request_latency_ms=latency_ms,
                            success=False,
                            http_status=exc.status_code,
                            error_code=exc.code or "READ_TRANSPORT",
                            error_text=str(exc)[:500],
                        )
                    )
                    if not exc.retryable and exc.status_code not in {429, 503}:
                        raise RuntimeError(
                            f"non-retryable read failure for exchange {target.exchange_id}: "
                            f"HTTP {exc.status_code} {exc.code or ''}".strip()
                        ) from exc
                    if exc.retry_after is not None and exc.retry_after > 0:
                        await asyncio.sleep(exc.retry_after)
                    continue
                latency_ms = (time.perf_counter() - request_started) * 1_000
                received_at = utc_now()

                try:
                    book = self.schema.parse(
                        payload,
                        received_at=received_at,
                        tournament_id=tournament_id,
                    )
                except (KeyError, TypeError, ValueError) as exc:
                    schema_failures += 1
                    self.store.record_collection_request(
                        CollectionRequest(
                            observed_at=received_at,
                            tournament_id=tournament_id,
                            market_id=target.market_id,
                            exchange_id=target.exchange_id,
                            request_latency_ms=latency_ms,
                            success=False,
                            http_status=200,
                            error_code=f"SCHEMA_{type(exc).__name__}",
                            error_text=str(exc)[:500],
                        )
                    )
                    continue

                if book.exchange_id != target.exchange_id:
                    raise RuntimeError(
                        "exchange orderbook response did not match requested exchange: "
                        f"requested={target.exchange_id} returned={book.exchange_id}"
                    )

                request_id = self.store.record_collection_request(
                    CollectionRequest(
                        observed_at=received_at,
                        tournament_id=tournament_id,
                        market_id=target.market_id,
                        exchange_id=target.exchange_id,
                        request_latency_ms=latency_ms,
                        success=True,
                        http_status=200,
                    )
                )
                metric = self.telemetry.observe(
                    book,
                    request_id=request_id,
                    tournament_id=tournament_id,
                    market_id=target.market_id,
                )
                self.store.record_orderbook(book)
                self.store.record_collection_metric(metric)

                snapshots += 1
                null_asof += int(metric.asof_null)
                sequence_regressions += int(metric.sequence_regression)

                if self.on_progress is not None and (
                    snapshots >= next_progress or snapshots >= self.config.target_snapshots
                ):
                    self.on_progress(
                        CollectionProgress(
                            snapshots=snapshots,
                            target_snapshots=self.config.target_snapshots,
                            reads=self._reads,
                            request_failures=request_failures,
                            elapsed_seconds=time.monotonic() - started,
                        )
                    )
                    while next_progress <= snapshots:
                        next_progress += self.config.progress_every

            if snapshots == before_round:
                no_progress_rounds += 1
                if no_progress_rounds >= self.config.max_no_progress_rounds:
                    raise RuntimeError(
                        "collector made no snapshot progress for "
                        f"{no_progress_rounds} consecutive rounds"
                    )
            else:
                no_progress_rounds = 0

        return CollectionSummary(
            tournament_id=tournament_id,
            selected_markets=selected_markets,
            selected_exchanges=len(targets),
            snapshots=snapshots,
            reads=self._reads,
            request_failures=request_failures,
            schema_failures=schema_failures,
            null_asof=null_asof,
            sequence_regressions=sequence_regressions,
            elapsed_seconds=time.monotonic() - started,
        )

    async def _paced(self, awaitable: Awaitable[T]) -> T:
        await self.limiter.wait()
        self._reads += 1
        return await awaitable


def _best(levels: tuple[BookLevel, ...]) -> BookLevel | None:
    return levels[0] if levels else None


def _select_exchange_targets(payload: Any, market_limit: int) -> list[ExchangeTarget]:
    if not isinstance(payload, dict):
        raise TypeError("markets response must be a JSON object")
    rows = payload.get("data")
    if not isinstance(rows, list):
        raise KeyError("markets response is missing data")

    out: list[ExchangeTarget] = []
    seen: set[str] = set()
    eligible_markets = 0

    for row in rows:
        if not isinstance(row, dict):
            continue
        exchanges = row.get("exchanges")
        if not isinstance(exchanges, list) or not exchanges:
            continue
        market_id = str(row.get("id") or "")
        if not market_id:
            continue

        added_for_market = False
        for exchange in exchanges:
            if not isinstance(exchange, dict):
                continue
            exchange_id = str(exchange.get("id") or "")
            if not exchange_id or exchange_id in seen:
                continue
            seen.add(exchange_id)
            out.append(ExchangeTarget(market_id=market_id, exchange_id=exchange_id))
            added_for_market = True

        if added_for_market:
            eligible_markets += 1
            if eligible_markets >= market_limit:
                break

    return out
