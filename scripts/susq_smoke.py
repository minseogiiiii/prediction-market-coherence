from __future__ import annotations

import argparse
import asyncio
import os
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from prediction_market_coherence.susq_client import AuthConfig, SusqApiError, SusqClient
from prediction_market_coherence.susq_schema import ExchangeOrderBookSchema


@dataclass(slots=True)
class Check:
    name: str
    status: str
    detail: str = ""


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Read-only Super Market API integration smoke test")
    p.add_argument(
        "--tournament-slug",
        default=os.getenv("SUSQ_TOURNAMENT_SLUG"),
        help="Explicit tournament slug; defaults to SUSQ_TOURNAMENT_SLUG",
    )
    p.add_argument("--depth", type=int, default=20)
    return p


async def main_async() -> int:
    args = parser().parse_args()
    auth = AuthConfig.from_env()
    checks: list[Check] = []

    async with SusqClient(auth=auth) as client:
        account = await _run(checks, "ACCOUNT", client.get_account)
        if isinstance(account, dict):
            balance = account.get("balance")
            checks[-1].detail = f"profile={account.get('id')} balance={balance}"

        tournaments = await _run(
            checks,
            "TOURNAMENTS",
            lambda: client.list_tournaments(status="active", limit=100),
        )
        available = []
        if isinstance(tournaments, dict) and isinstance(tournaments.get("data"), list):
            available = [
                (str(row.get("slug")), str(row.get("name")))
                for row in tournaments["data"]
                if isinstance(row, dict)
            ]
            checks[-1].detail = f"active={len(available)}"

        tournament_id: str | None = None
        slug = args.tournament_slug
        if slug:
            tournament = await _run(
                checks,
                "TOURNAMENT",
                lambda: client.get_tournament(slug),
            )
            if isinstance(tournament, dict):
                tournament_id = str(tournament.get("id") or "") or None
                checks[-1].detail = (
                    f"slug={slug} id={tournament_id} balance={tournament.get('myBalance')} "
                    f"pending={tournament.get('isPendingEnrolment')}"
                )
        else:
            checks.append(
                Check(
                    "TOURNAMENT",
                    "SKIP",
                    "set SUSQ_TOURNAMENT_SLUG to lock all reads to one competition context; "
                    + ", ".join(f"{s} ({n})" for s, n in available[:8]),
                )
            )

        market_params: dict[str, Any] = {"status": "open", "limit": 20}
        if tournament_id:
            market_params["tournamentId"] = tournament_id
        markets = await _run(
            checks,
            "MARKETS",
            lambda: client.list_markets(**market_params),
        )

        market_id: str | None = None
        exchange_id: str | None = None
        if isinstance(markets, dict) and isinstance(markets.get("data"), list):
            rows = [row for row in markets["data"] if isinstance(row, dict)]
            checks[-1].detail = f"rows={len(rows)}"
            if rows:
                market_id = str(rows[0].get("id") or "") or None
                exchanges = rows[0].get("exchanges")
                if isinstance(exchanges, list) and exchanges and isinstance(exchanges[0], dict):
                    exchange_id = str(exchanges[0].get("id") or "") or None

        if exchange_id:
            book_payload = await _run(
                checks,
                "EXCHANGE_BOOK",
                lambda: client.get_exchange_orderbook(
                    exchange_id,
                    tournament_id=tournament_id,
                    depth=args.depth,
                ),
            )
            if isinstance(book_payload, dict):
                book = ExchangeOrderBookSchema().parse(
                    book_payload,
                    tournament_id=tournament_id,
                )
                checks[-1].detail = (
                    f"exchange={book.exchange_id} yes_bids={len(book.yes_bids)} "
                    f"yes_asks={len(book.yes_asks)} seq={book.source_sequence}"
                )
        else:
            checks.append(Check("EXCHANGE_BOOK", "SKIP", "no open exchange discovered"))

        if market_id:
            rels = await _run(
                checks,
                "RELATIONSHIPS",
                lambda: client.get_relationships(
                    marketId=market_id,
                    tournamentId=tournament_id,
                    limit=100,
                ),
            )
            if isinstance(rels, dict) and isinstance(rels.get("data"), list):
                checks[-1].detail = f"relationships={len(rels['data'])}"

            constraints = await _run(
                checks,
                "CONSTRAINTS",
                lambda: client.get_relationship_constraints(
                    marketId=market_id,
                    tournamentId=tournament_id,
                    violationsOnly="false",
                    minViolation=0,
                ),
            )
            if isinstance(constraints, dict):
                checks[-1].detail = (
                    f"evaluations={len(constraints.get('data') or [])} "
                    f"violations={constraints.get('violationsCount')}"
                )
        else:
            checks.append(Check("RELATIONSHIPS", "SKIP", "no open market discovered"))
            checks.append(Check("CONSTRAINTS", "SKIP", "no open market discovered"))

        if slug and tournament_id:
            positions = await _run(
                checks,
                "POSITIONS",
                lambda: client.get_tournament_positions(slug),
                allow_forbidden=True,
            )
            if isinstance(positions, dict) and isinstance(positions.get("positions"), list):
                checks[-1].detail = f"open_positions={len(positions['positions'])}"
        else:
            checks.append(Check("POSITIONS", "SKIP", "explicit tournament context not selected"))

    print("\nREAD-ONLY SUPER MARKET SMOKE TEST")
    print("=" * 72)
    for check in checks:
        suffix = f" | {check.detail}" if check.detail else ""
        print(f"{check.name:18} {check.status:6}{suffix}")
    print("=" * 72)
    print("WRITE REQUESTS      0")

    failed = [c for c in checks if c.status == "FAIL"]
    return 1 if failed else 0


async def _run(
    checks: list[Check],
    name: str,
    call: Callable[[], Awaitable[Any]],
    *,
    allow_forbidden: bool = False,
) -> Any:
    try:
        result = await call()
    except SusqApiError as exc:
        if allow_forbidden and exc.status_code == 403:
            checks.append(Check(name, "SKIP", f"HTTP 403 {exc.code or ''}".strip()))
            return None
        checks.append(
            Check(
                name,
                "FAIL",
                f"HTTP={exc.status_code} code={exc.code} retryable={exc.retryable}",
            )
        )
        return None
    except Exception as exc:  # noqa: BLE001 - smoke harness records every failure
        checks.append(Check(name, "FAIL", f"{type(exc).__name__}: {exc}"))
        return None
    checks.append(Check(name, "PASS"))
    return result


def main() -> int:
    return asyncio.run(main_async())


if __name__ == "__main__":
    raise SystemExit(main())
