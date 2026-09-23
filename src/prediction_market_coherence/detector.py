from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from itertools import combinations
from collections.abc import Iterable

from .models import ThresholdMarket


@dataclass(frozen=True, slots=True)
class Violation:
    event_ticker: str
    lower: ThresholdMarket
    higher: ThresholdMarket
    lower_mid: Decimal
    higher_mid: Decimal
    midpoint_gap: Decimal
    gross_executable_edge: Decimal | None

    @property
    def midpoint_gap_cents(self) -> Decimal:
        return self.midpoint_gap * Decimal("100")


def executable_nested_edge(
    lower: ThresholdMarket,
    higher: ThresholdMarket,
) -> Decimal | None:
    """
    Gross guaranteed edge for nested events H ⊂ L:
      buy YES(lower strike) + buy NO(higher strike).
    Each winning contract pays $1, so guaranteed payout is at least $1.
    Fees/slippage are intentionally excluded from the MVP.
    """
    if lower.yes_ask is None or higher.no_ask is None:
        return None
    if lower.yes_ask <= 0 or higher.no_ask <= 0:
        return None
    return Decimal("1") - lower.yes_ask - higher.no_ask


def detect_monotonicity_violations(
    family: Iterable[ThresholdMarket],
    *,
    adjacent_only: bool = False,
) -> list[Violation]:
    """
    For greater-than thresholds K_low < K_high, coherence requires
        P(X > K_low) >= P(X > K_high).
    Detect violations using two-sided YES midpoints.
    """
    ordered = sorted(family, key=lambda m: m.strike)
    pairs: Iterable[tuple[ThresholdMarket, ThresholdMarket]]
    if adjacent_only:
        pairs = zip(ordered, ordered[1:])
    else:
        pairs = combinations(ordered, 2)

    violations: list[Violation] = []
    for lower, higher in pairs:
        if not lower.strike < higher.strike:
            continue

        lower_mid = lower.midpoint
        higher_mid = higher.midpoint
        if lower_mid is None or higher_mid is None:
            continue

        gap = higher_mid - lower_mid
        if gap > 0:
            violations.append(
                Violation(
                    event_ticker=lower.event_ticker,
                    lower=lower,
                    higher=higher,
                    lower_mid=lower_mid,
                    higher_mid=higher_mid,
                    midpoint_gap=gap,
                    gross_executable_edge=executable_nested_edge(lower, higher),
                )
            )

    return sorted(violations, key=lambda v: v.midpoint_gap, reverse=True)
