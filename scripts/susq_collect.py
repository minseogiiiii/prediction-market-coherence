from __future__ import annotations

import argparse
import asyncio
import os
from pathlib import Path

from prediction_market_coherence.storage import ResearchStore
from prediction_market_coherence.susq_client import AuthConfig, SusqClient
from prediction_market_coherence.susq_collection import (
    CollectionConfig,
    CollectionProgress,
    ProductionBookCollector,
)


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Read-only, rate-budgeted Super Market exchange-book collector"
    )
    p.add_argument(
        "--tournament-slug",
        default=os.getenv("SUSQ_TOURNAMENT_SLUG"),
        help="Explicit tournament slug; defaults to SUSQ_TOURNAMENT_SLUG",
    )
    p.add_argument("--db", type=Path, default=Path("data/susq_readonly.sqlite3"))
    p.add_argument("--target-snapshots", type=int, default=1_000)
    p.add_argument("--markets", type=int, default=10)
    p.add_argument("--depth", type=int, default=200)
    p.add_argument("--timeout-seconds", type=float, default=15.0)
    p.add_argument("--progress-every", type=int, default=25)
    p.add_argument(
        "--reads-per-minute",
        type=float,
        default=80.0,
        help="Client-side request-start cap; keep <= documented per-key read limit.",
    )
    return p


async def main_async() -> int:
    args = parser().parse_args()
    if not args.tournament_slug:
        raise SystemExit(
            "SUSQ_TOURNAMENT_SLUG is required; run the read-only smoke gate first"
        )
    if args.timeout_seconds <= 0:
        raise SystemExit("--timeout-seconds must be positive")

    auth = AuthConfig.from_env()
    config = CollectionConfig(
        target_snapshots=args.target_snapshots,
        market_limit=args.markets,
        depth=args.depth,
        reads_per_minute=args.reads_per_minute,
        progress_every=args.progress_every,
    )

    args.db.parent.mkdir(parents=True, exist_ok=True)

    print("READ-ONLY PRODUCTION COLLECTION")
    print("=" * 72)
    print(f"tournament          {args.tournament_slug}")
    print(f"database            {args.db}")
    print("endpoint            /exchanges/{id}/orderbook")
    print(f"target snapshots    {config.target_snapshots}")
    print(f"market cap          {config.market_limit}")
    print(f"book depth          {config.depth}")
    print(f"read budget/min     {config.reads_per_minute:g}")
    print(f"HTTP timeout sec    {args.timeout_seconds:g}")
    print("=" * 72)

    def progress(p: CollectionProgress) -> None:
        print(
            f"progress {p.snapshots:>5}/{p.target_snapshots:<5} "
            f"reads={p.reads:<5} failures={p.request_failures:<4} "
            f"elapsed={p.elapsed_seconds:.1f}s",
            flush=True,
        )

    with ResearchStore(args.db) as store:
        # Hidden GET retries stay disabled so every wire attempt is observable in
        # collection_requests. The collector itself handles pacing and Retry-After.
        async with SusqClient(
            auth=auth,
            timeout=args.timeout_seconds,
            max_read_retries=0,
        ) as client:
            summary = await ProductionBookCollector(
                client,
                store,
                tournament_slug=args.tournament_slug,
                config=config,
                on_progress=progress,
            ).run()

    print("\nCOLLECTION SUMMARY")
    print("=" * 72)
    print(f"tournament id       {summary.tournament_id}")
    print(f"selected markets    {summary.selected_markets}")
    print(f"selected exchanges  {summary.selected_exchanges}")
    print(f"snapshots           {summary.snapshots}")
    print(f"GET reads           {summary.reads}")
    print(f"request failures    {summary.request_failures}")
    print(f"schema failures     {summary.schema_failures}")
    print(f"null asOf           {summary.null_asof}")
    print(f"seq regressions     {summary.sequence_regressions}")
    print(f"elapsed seconds     {summary.elapsed_seconds:.1f}")
    print("WRITE REQUESTS      0")
    print("=" * 72)

    return 0 if summary.snapshots >= config.target_snapshots else 1


def main() -> int:
    return asyncio.run(main_async())


if __name__ == "__main__":
    raise SystemExit(main())
