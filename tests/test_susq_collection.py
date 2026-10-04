import asyncio
import sqlite3
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from prediction_market_coherence.models import BookLevel, OrderBook
from prediction_market_coherence.storage import ResearchStore
from prediction_market_coherence.susq_collection import (
    BookTelemetryTracker,
    CollectionConfig,
    ProductionBookCollector,
    ReadRateLimiter,
)

D = Decimal
NOW = datetime(2026, 10, 1, 18, 0, tzinfo=UTC)


def book(
    exchange_id: str,
    *,
    sequence: int | None,
    observed_at: datetime = NOW,
    bid: str = "0.4",
    ask: str = "0.6",
) -> OrderBook:
    return OrderBook(
        market_id=exchange_id,
        observed_at=observed_at,
        yes_bids=(BookLevel(D(bid), D("2")),),
        yes_asks=(BookLevel(D(ask), D("3")),),
        source_sequence=sequence,
        received_at=observed_at,
        context_id="T",
    )


def test_read_rate_limiter_reserves_even_spacing():
    limiter = ReadRateLimiter(60)
    assert limiter.reserve_delay(100.0) == 0
    assert limiter.reserve_delay(100.5) == 0.5
    assert limiter.reserve_delay(102.0) == 0


def test_book_telemetry_flags_regression_and_quote_age():
    tracker = BookTelemetryTracker()

    first = tracker.observe(
        book("E", sequence=10),
        request_id=1,
        tournament_id="T",
        market_id="M",
    )
    second = tracker.observe(
        book("E", sequence=9, observed_at=NOW + timedelta(seconds=3)),
        request_id=2,
        tournament_id="T",
        market_id="M",
    )

    assert first.quote_changed is True
    assert first.yes_spread == D("0.2")
    assert second.sequence_delta == -1
    assert second.sequence_regression is True
    assert second.quote_changed is False
    assert second.quote_age_seconds == 3.0


class NoWaitLimiter:
    async def wait(self) -> None:
        return None


class FakeClient:
    def __init__(self):
        self.exchange_calls: list[str] = []

    async def get_tournament(self, slug: str):
        assert slug == "midterm-elections"
        return {"id": "T"}

    async def list_markets(self, **params):
        assert params["tournamentId"] == "T"
        return {
            "data": [
                {"id": 388, "exchanges": [{"id": 1077}, {"id": 1078}]},
                {"id": 387, "exchanges": [{"id": 1076}]},
            ]
        }

    async def get_exchange_orderbook(
        self,
        exchange_id: str,
        *,
        tournament_id: str | None = None,
        depth: int = 200,
    ):
        assert tournament_id == "T"
        assert depth == 200
        self.exchange_calls.append(exchange_id)
        sequence = 100 + len(self.exchange_calls)
        return {
            "exchangeId": exchange_id,
            "asOf": {"sequence": sequence, "at": "2026-10-01T18:00:00Z"},
            "bids": [{"price": 0.4, "quantity": 2}],
            "asks": [{"price": 0.6, "quantity": 3}],
        }


def test_production_collector_uses_exchange_endpoint_and_persists_exact_target(tmp_path):
    db = tmp_path / "collector.db"
    config = CollectionConfig(
        target_snapshots=2,
        market_limit=1,
        depth=200,
        reads_per_minute=100,
        progress_every=1,
    )
    client = FakeClient()
    progress = []

    with ResearchStore(db) as store:
        collector = ProductionBookCollector(
            client,
            store,
            tournament_slug="midterm-elections",
            config=config,
            limiter=NoWaitLimiter(),
            on_progress=progress.append,
        )
        summary = asyncio.run(collector.run())

    assert client.exchange_calls == ["1077", "1078"]
    assert summary.snapshots == 2
    assert summary.reads == 4
    assert summary.selected_markets == 1
    assert summary.selected_exchanges == 2
    assert summary.request_failures == 0
    assert summary.schema_failures == 0
    assert summary.sequence_regressions == 0
    assert [item.snapshots for item in progress] == [1, 2]

    conn = sqlite3.connect(db)
    snapshots = conn.execute("SELECT COUNT(*) FROM orderbook_snapshots").fetchone()[0]
    requests = conn.execute("SELECT COUNT(*) FROM collection_requests").fetchone()[0]
    metrics = conn.execute("SELECT COUNT(*) FROM collection_metrics").fetchone()[0]
    contexts = conn.execute(
        "SELECT DISTINCT tournament_id FROM collection_metrics"
    ).fetchall()
    requested_exchanges = conn.execute(
        "SELECT exchange_id FROM collection_requests ORDER BY id"
    ).fetchall()
    linked = conn.execute(
        """
        SELECT COUNT(*)
        FROM collection_metrics m
        JOIN collection_requests r ON r.id = m.request_id
        """
    ).fetchone()[0]
    conn.close()

    assert snapshots == 2
    assert requests == 2
    assert metrics == 2
    assert contexts == [("T",)]
    assert requested_exchanges == [("1077",), ("1078",)]
    assert linked == 2
