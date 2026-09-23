from __future__ import annotations

import argparse
import json
from decimal import Decimal
from pathlib import Path

from .client import KalshiClient
from .detector import detect_monotonicity_violations
from .relationships import group_threshold_families, normalize_greater_markets


def _money(value: Decimal | None) -> str:
    if value is None:
        return "n/a"
    return f"{value * Decimal('100'):.2f}¢"


def _load_fixture(path: Path) -> list[dict]:
    payload = json.loads(path.read_text())
    if isinstance(payload, list):
        return payload
    return payload.get("markets", [])


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Detect monotonicity violations in Kalshi greater-than threshold markets."
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--live", action="store_true", help="Fetch open markets from Kalshi")
    source.add_argument("--fixture", type=Path, help="Read a Kalshi-style JSON fixture")
    parser.add_argument("--event", help="Optional Kalshi event ticker filter for --live")
    parser.add_argument("--adjacent-only", action="store_true")
    parser.add_argument("--max-pages", type=int, default=None)
    return parser


def main() -> int:
    args = build_parser().parse_args()

    if args.live:
        raw = list(
            KalshiClient().iter_markets(
                status="open",
                event_ticker=args.event,
                max_pages=args.max_pages,
            )
        )
    else:
        raw = _load_fixture(args.fixture)

    markets = normalize_greater_markets(raw)
    families = group_threshold_families(markets)

    scanned_pairs = 0
    violations = []
    for family in families.values():
        n = len(family)
        scanned_pairs += (n - 1) if args.adjacent_only else n * (n - 1) // 2
        violations.extend(
            detect_monotonicity_violations(family, adjacent_only=args.adjacent_only)
        )

    violations.sort(key=lambda v: v.midpoint_gap, reverse=True)

    print(f"Greater-than markets: {len(markets)}")
    print(f"Threshold families:   {len(families)}")
    print(f"Pairs scanned:        {scanned_pairs}")
    print(f"Violations:           {len(violations)}")

    if not violations:
        print("\nNo monotonicity violations found.")
        return 0

    print("\nVIOLATIONS")
    print("-" * 96)
    for v in violations:
        executable = (
            "n/a"
            if v.gross_executable_edge is None
            else _money(v.gross_executable_edge)
        )
        print(
            f"{v.event_ticker}: "
            f"K={v.lower.strike} mid={_money(v.lower_mid)}  ->  "
            f"K={v.higher.strike} mid={_money(v.higher_mid)}  | "
            f"gap={_money(v.midpoint_gap)}  | gross executable edge={executable}"
        )
        print(f"  lower:  {v.lower.ticker} | {v.lower.title}")
        print(f"  higher: {v.higher.ticker} | {v.higher.title}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
