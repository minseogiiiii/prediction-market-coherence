from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Self

from .models import ExecutionCandidate, OrderBook


def _json_default(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if hasattr(value, "value"):
        return value.value
    raise TypeError(f"not JSON serializable: {type(value).__name__}")


@dataclass(frozen=True, slots=True)
class CollectionRequest:
    """One authoritative REST order-book request."""

    observed_at: datetime
    tournament_id: str
    market_id: str
    request_latency_ms: float
    success: bool
    exchange_id: str | None = None
    http_status: int | None = None
    error_code: str | None = None
    error_text: str | None = None


@dataclass(frozen=True, slots=True)
class CollectionMetric:
    """Exchange-level telemetry derived from one successful collection request."""

    request_id: int
    observed_at: datetime
    tournament_id: str
    market_id: str
    exchange_id: str
    source_sequence: int | None = None
    sequence_delta: int | None = None
    sequence_regression: bool = False
    asof_null: bool = False
    yes_best_bid: Decimal | None = None
    yes_best_ask: Decimal | None = None
    yes_spread: Decimal | None = None
    bid_levels: int = 0
    ask_levels: int = 0
    bid_quantity: Decimal = Decimal(0)
    ask_quantity: Decimal = Decimal(0)
    quote_changed: bool = True
    quote_age_seconds: float = 0.0
    previous_quote_lifetime_seconds: float | None = None


class ResearchStore:
    """Append-oriented SQLite research store."""

    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        self.conn = sqlite3.connect(self.path)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA synchronous=NORMAL")
        self._init_schema()

    def _init_schema(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS orderbook_snapshots (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              observed_at TEXT NOT NULL,
              market_id TEXT NOT NULL,
              payload_json TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_books_market_time
              ON orderbook_snapshots(market_id, observed_at);

            CREATE TABLE IF NOT EXISTS collection_requests (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              observed_at TEXT NOT NULL,
              tournament_id TEXT NOT NULL,
              market_id TEXT NOT NULL,
              exchange_id TEXT,
              request_latency_ms REAL NOT NULL,
              success INTEGER NOT NULL,
              http_status INTEGER,
              error_code TEXT,
              error_text TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_collection_requests_market_time
              ON collection_requests(market_id, observed_at);

            CREATE TABLE IF NOT EXISTS collection_metrics (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              request_id INTEGER NOT NULL,
              observed_at TEXT NOT NULL,
              tournament_id TEXT NOT NULL,
              market_id TEXT NOT NULL,
              exchange_id TEXT NOT NULL,
              source_sequence INTEGER,
              sequence_delta INTEGER,
              sequence_regression INTEGER NOT NULL DEFAULT 0,
              asof_null INTEGER NOT NULL DEFAULT 0,
              yes_best_bid TEXT,
              yes_best_ask TEXT,
              yes_spread TEXT,
              bid_levels INTEGER NOT NULL,
              ask_levels INTEGER NOT NULL,
              bid_quantity TEXT NOT NULL,
              ask_quantity TEXT NOT NULL,
              quote_changed INTEGER NOT NULL,
              quote_age_seconds REAL NOT NULL,
              previous_quote_lifetime_seconds REAL,
              FOREIGN KEY(request_id) REFERENCES collection_requests(id)
            );
            CREATE INDEX IF NOT EXISTS idx_collection_exchange_time
              ON collection_metrics(exchange_id, observed_at);
            CREATE INDEX IF NOT EXISTS idx_collection_market_time
              ON collection_metrics(market_id, observed_at);

            CREATE TABLE IF NOT EXISTS signals (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              created_at TEXT NOT NULL,
              candidate_id TEXT NOT NULL,
              relationship_id TEXT NOT NULL,
              edge TEXT NOT NULL,
              quantity TEXT NOT NULL,
              expected_profit TEXT NOT NULL,
              payload_json TEXT NOT NULL
            );
            CREATE UNIQUE INDEX IF NOT EXISTS idx_signal_candidate
              ON signals(candidate_id, created_at);

            CREATE TABLE IF NOT EXISTS execution_events (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              created_at TEXT NOT NULL,
              candidate_id TEXT,
              event_type TEXT NOT NULL,
              payload_json TEXT NOT NULL
            );
            """
        )
        _ensure_column(self.conn, "collection_requests", "exchange_id", "TEXT")
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_collection_requests_exchange_time "
            "ON collection_requests(exchange_id, observed_at)"
        )
        self.conn.commit()

    def record_orderbook(self, book: OrderBook) -> None:
        self.record_orderbooks((book,))

    def record_orderbooks(self, books: Iterable[OrderBook]) -> None:
        rows = [
            (
                book.observed_at.isoformat(),
                book.market_id,
                json.dumps(asdict(book), default=_json_default, sort_keys=True),
            )
            for book in books
        ]
        if not rows:
            return
        self.conn.executemany(
            "INSERT INTO orderbook_snapshots(observed_at, market_id, payload_json) "
            "VALUES (?, ?, ?)",
            rows,
        )
        self.conn.commit()

    def record_collection_request(self, request: CollectionRequest) -> int:
        cursor = self.conn.execute(
            """
            INSERT INTO collection_requests(
              observed_at, tournament_id, market_id, exchange_id,
              request_latency_ms, success, http_status, error_code, error_text
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                request.observed_at.isoformat(),
                request.tournament_id,
                request.market_id,
                request.exchange_id,
                request.request_latency_ms,
                int(request.success),
                request.http_status,
                request.error_code,
                request.error_text,
            ),
        )
        self.conn.commit()
        if cursor.lastrowid is None:
            raise RuntimeError("SQLite did not return a collection request id")
        return int(cursor.lastrowid)

    def record_collection_metric(self, metric: CollectionMetric) -> None:
        self.record_collection_metrics((metric,))

    def record_collection_metrics(self, metrics: Iterable[CollectionMetric]) -> None:
        rows = [
            (
                metric.request_id,
                metric.observed_at.isoformat(),
                metric.tournament_id,
                metric.market_id,
                metric.exchange_id,
                metric.source_sequence,
                metric.sequence_delta,
                int(metric.sequence_regression),
                int(metric.asof_null),
                _decimal_text(metric.yes_best_bid),
                _decimal_text(metric.yes_best_ask),
                _decimal_text(metric.yes_spread),
                metric.bid_levels,
                metric.ask_levels,
                str(metric.bid_quantity),
                str(metric.ask_quantity),
                int(metric.quote_changed),
                metric.quote_age_seconds,
                metric.previous_quote_lifetime_seconds,
            )
            for metric in metrics
        ]
        if not rows:
            return
        self.conn.executemany(
            """
            INSERT INTO collection_metrics(
              request_id, observed_at, tournament_id, market_id, exchange_id,
              source_sequence, sequence_delta, sequence_regression, asof_null,
              yes_best_bid, yes_best_ask, yes_spread, bid_levels, ask_levels,
              bid_quantity, ask_quantity, quote_changed, quote_age_seconds,
              previous_quote_lifetime_seconds
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        self.conn.commit()

    def record_candidate(self, candidate: ExecutionCandidate, *, created_at: datetime) -> None:
        payload = json.dumps(asdict(candidate), default=_json_default, sort_keys=True)
        self.conn.execute(
            """INSERT INTO signals(created_at, candidate_id, relationship_id, edge, quantity,
               expected_profit, payload_json) VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                created_at.isoformat(),
                candidate.candidate_id,
                candidate.relationship_id,
                str(candidate.executable_edge_per_bundle),
                str(candidate.max_profitable_quantity),
                str(candidate.expected_profit),
                payload,
            ),
        )
        self.conn.commit()

    def record_event(
        self,
        event_type: str,
        payload: dict[str, Any],
        *,
        created_at: datetime,
        candidate_id: str | None = None,
    ) -> None:
        self.conn.execute(
            "INSERT INTO execution_events(created_at, candidate_id, event_type, payload_json) "
            "VALUES (?, ?, ?, ?)",
            (
                created_at.isoformat(),
                candidate_id,
                event_type,
                json.dumps(payload, default=_json_default, sort_keys=True),
            ),
        )
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


def _decimal_text(value: Decimal | None) -> str | None:
    return None if value is None else str(value)


def _ensure_column(
    conn: sqlite3.Connection,
    table: str,
    column: str,
    declaration: str,
) -> None:
    columns = {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})")}
    if column not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {declaration}")
