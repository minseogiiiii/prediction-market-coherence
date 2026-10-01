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
    return f"{value * Decimal(100):.2f}¢"


def _load_fixture(path: Path) -> list[dict]:
    payload = json.loads(path.read_text())
    if isinstance(payload, list):
        return payload
    return payload.get("markets", [])


def _kalshi_scan(args: argparse.Namespace) -> int:
    if args.live:
        raw = list(
            KalshiClient().iter_markets(
                status="open", event_ticker=args.event, max_pages=args.max_pages
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
        violations.extend(detect_monotonicity_violations(family, adjacent_only=args.adjacent_only))
    violations.sort(key=lambda v: v.midpoint_gap, reverse=True)
    print(f"Greater-than markets: {len(markets)}")
    print(f"Threshold families:   {len(families)}")
    print(f"Pairs scanned:        {scanned_pairs}")
    print(f"Violations:           {len(violations)}")
    for v in violations:
        executable = "n/a" if v.gross_executable_edge is None else _money(v.gross_executable_edge)
        print(
            f"{v.event_ticker}: K={v.lower.strike} mid={_money(v.lower_mid)} -> "
            f"K={v.higher.strike} mid={_money(v.higher_mid)} | gap={_money(v.midpoint_gap)} | "
            f"gross executable edge={executable}"
        )
    if not violations:
        print("No monotonicity violations found.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Prediction-market coherence research toolkit")
    sub = parser.add_subparsers(dest="command")

    scan = sub.add_parser("kalshi-scan", help="run the legacy Kalshi threshold scanner")
    source = scan.add_mutually_exclusive_group(required=True)
    source.add_argument("--live", action="store_true")
    source.add_argument("--fixture", type=Path)
    scan.add_argument("--event")
    scan.add_argument("--adjacent-only", action="store_true")
    scan.add_argument("--max-pages", type=int, default=None)

    # Backward-compatible arguments used by the original project.
    parser.add_argument("--live", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--fixture", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--event", help=argparse.SUPPRESS)
    parser.add_argument("--adjacent-only", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--max-pages", type=int, default=None, help=argparse.SUPPRESS)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.command == "kalshi-scan":
        return _kalshi_scan(args)
    if args.live or args.fixture:
        return _kalshi_scan(args)
    build_parser().print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
