from __future__ import annotations

import argparse
import sqlite3
import statistics
from collections import Counter
from pathlib import Path


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Analyze Super Market read-only collection telemetry")
    p.add_argument("db", type=Path)
    return p


def percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = int((len(ordered) - 1) * q)
    return ordered[index]


def fmt(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.2f}"


def main() -> int:
    args = parser().parse_args()
    if not args.db.exists():
        raise SystemExit(f"database not found: {args.db}")

    con = sqlite3.connect(args.db)
    con.row_factory = sqlite3.Row

    requests = list(con.execute("SELECT * FROM collection_requests ORDER BY id"))
    metrics = list(con.execute("SELECT * FROM collection_metrics ORDER BY id"))

    successful = [row for row in requests if row["success"]]
    failures = [row for row in requests if not row["success"]]
    latencies = [float(row["request_latency_ms"]) for row in successful]
    failure_counts = Counter((row["http_status"], row["error_code"]) for row in failures)

    print("COLLECTION ANALYSIS")
    print("=" * 72)
    print(f"database            {args.db}")
    print(f"requests            {len(requests)}")
    print(f"successful requests {len(successful)}")
    print(f"failed requests     {len(failures)}")
    print(f"snapshots/metrics   {len(metrics)}")
    print(f"distinct markets    {len({row['market_id'] for row in metrics})}")
    print(f"distinct exchanges  {len({row['exchange_id'] for row in metrics})}")

    print("\nSUCCESS LATENCY (ms)")
    print("-" * 72)
    print(f"avg                 {fmt(statistics.mean(latencies) if latencies else None)}")
    print(f"median              {fmt(statistics.median(latencies) if latencies else None)}")
    print(f"p90                 {fmt(percentile(latencies, 0.90))}")
    print(f"p95                 {fmt(percentile(latencies, 0.95))}")
    print(f"max                 {fmt(max(latencies) if latencies else None)}")

    print("\nFAILURES")
    print("-" * 72)
    if not failure_counts:
        print("none")
    else:
        for (status, code), count in failure_counts.most_common():
            print(f"HTTP={status} code={code} count={count}")

    integrity = con.execute(
        """
        SELECT
          COUNT(*) AS rows,
          COALESCE(SUM(asof_null), 0) AS null_asof,
          COALESCE(SUM(sequence_regression), 0) AS sequence_regressions,
          COALESCE(SUM(quote_changed), 0) AS quote_changes
        FROM collection_metrics
        """
    ).fetchone()
    schema_failures = con.execute(
        """
        SELECT COUNT(*)
        FROM collection_requests
        WHERE error_code LIKE 'SCHEMA_%'
        """
    ).fetchone()[0]

    print("\nINTEGRITY")
    print("-" * 72)
    print(f"schema failures     {schema_failures}")
    print(f"null asOf           {integrity['null_asof']}")
    print(f"seq regressions     {integrity['sequence_regressions']}")
    print(f"quote changes       {integrity['quote_changes']}")

    lifetimes = [
        float(row["previous_quote_lifetime_seconds"])
        for row in metrics
        if row["previous_quote_lifetime_seconds"] is not None
    ]
    spreads = [
        float(row["yes_spread"])
        for row in metrics
        if row["yes_spread"] is not None
    ]

    print("\nMARKET MICROSTRUCTURE")
    print("-" * 72)
    print(f"spread observations {len(spreads)}")
    print(f"median spread       {fmt(statistics.median(spreads) if spreads else None)}")
    print(f"max spread          {fmt(max(spreads) if spreads else None)}")
    print(f"quote lifetimes     {len(lifetimes)}")
    print(f"median lifetime sec {fmt(statistics.median(lifetimes) if lifetimes else None)}")
    print(f"max lifetime sec    {fmt(max(lifetimes) if lifetimes else None)}")

    print("\nPER EXCHANGE")
    print("-" * 72)
    for row in con.execute(
        """
        SELECT
          exchange_id,
          market_id,
          COUNT(*) AS snapshots,
          ROUND(AVG(bid_levels), 2) AS avg_bid_levels,
          ROUND(AVG(ask_levels), 2) AS avg_ask_levels,
          ROUND(AVG(CAST(yes_spread AS REAL)), 6) AS avg_spread,
          COALESCE(SUM(sequence_regression), 0) AS regressions,
          COALESCE(SUM(asof_null), 0) AS null_asof
        FROM collection_metrics
        GROUP BY exchange_id, market_id
        ORDER BY snapshots DESC, exchange_id
        """
    ):
        print(dict(row))

    print("=" * 72)
    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
