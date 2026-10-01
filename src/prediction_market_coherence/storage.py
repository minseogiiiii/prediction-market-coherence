from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict
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


class ResearchStore:
    """Append-oriented SQLite research store.

    SQLite is a zero-dependency durable baseline. Optional Parquet/DuckDB export
    can be layered on top without making the live trading path depend on an
    analytics package.
    """

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
        self.conn.commit()

    def record_orderbook(self, book: OrderBook) -> None:
        payload = json.dumps(asdict(book), default=_json_default, sort_keys=True)
        self.conn.execute(
            "INSERT INTO orderbook_snapshots(observed_at, market_id, payload_json) VALUES (?, ?, ?)",
            (book.observed_at.isoformat(), book.market_id, payload),
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

    def record_event(self, event_type: str, payload: dict[str, Any], *, created_at: datetime, candidate_id: str | None = None) -> None:
        self.conn.execute(
            "INSERT INTO execution_events(created_at, candidate_id, event_type, payload_json) VALUES (?, ?, ?, ?)",
            (created_at.isoformat(), candidate_id, event_type, json.dumps(payload, default=_json_default, sort_keys=True)),
        )
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
