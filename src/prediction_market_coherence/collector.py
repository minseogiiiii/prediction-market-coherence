from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from .models import OrderBook
from .storage import ResearchStore


@dataclass(frozen=True, slots=True)
class CollectionResult:
    requested: int
    succeeded: int
    failed: int
    errors: tuple[str, ...]


async def collect_orderbooks_once(
    market_ids: list[str],
    fetch: Callable[[str], Awaitable[OrderBook]],
    store: ResearchStore,
    *,
    concurrency: int = 20,
) -> CollectionResult:
    if concurrency <= 0:
        raise ValueError("concurrency must be positive")
    semaphore = asyncio.Semaphore(concurrency)
    errors: list[str] = []
    succeeded = 0

    async def one(market_id: str) -> None:
        nonlocal succeeded
        async with semaphore:
            try:
                book = await fetch(market_id)
                store.record_orderbook(book)
                succeeded += 1
            except Exception as exc:  # noqa: BLE001 -- isolate per-market collection failures
                errors.append(f"{market_id}: {type(exc).__name__}: {exc}")

    await asyncio.gather(*(one(m) for m in market_ids))
    return CollectionResult(len(market_ids), succeeded, len(errors), tuple(errors))


class AdaptiveCadence:
    """Simple request-budget prioritizer.

    Lower returned interval means higher polling priority. Active orders dominate,
    then near-threshold opportunities, then ordinary markets.
    """

    def __init__(self, *, cold_seconds: float = 10.0, warm_seconds: float = 2.0, hot_seconds: float = 0.5) -> None:
        if min(cold_seconds, warm_seconds, hot_seconds) <= 0:
            raise ValueError("cadences must be positive")
        self.cold = cold_seconds
        self.warm = warm_seconds
        self.hot = hot_seconds

    def interval(self, *, active_order: bool, edge_distance: float | None) -> float:
        if active_order:
            return self.hot
        if edge_distance is not None and edge_distance <= 0.005:
            return self.hot
        if edge_distance is not None and edge_distance <= 0.02:
            return self.warm
        return self.cold
