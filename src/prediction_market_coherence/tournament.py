from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class TournamentState:
    balance: Decimal
    reference_top3_balance: Decimal | None
    hours_remaining: Decimal


@dataclass(frozen=True, slots=True)
class TournamentRisk:
    risk_multiplier: Decimal
    rationale: str


def tournament_risk_multiplier(state: TournamentState) -> TournamentRisk:
    """Conservative bounded heuristic, not an election-outcome forecast.

    It never recommends a political direction; it only adjusts position sizing
    based on score gap and time left. The multiplier is intentionally bounded to
    [0.5, 1.25] so leaderboard chasing cannot override core risk limits.
    """
    if state.reference_top3_balance is None or state.reference_top3_balance <= 0:
        return TournamentRisk(Decimal("1.0"), "no reliable leaderboard reference")
    gap = (state.reference_top3_balance - state.balance) / state.reference_top3_balance
    if state.hours_remaining > Decimal(168):
        return TournamentRisk(Decimal("1.0"), "early competition")
    if gap <= Decimal(0):
        return TournamentRisk(Decimal("0.75"), "protecting a top-three-level score")
    if state.hours_remaining <= Decimal(24) and gap >= Decimal("0.10"):
        return TournamentRisk(Decimal("1.25"), "late and materially behind reference")
    if gap >= Decimal("0.05"):
        return TournamentRisk(Decimal("1.10"), "behind reference with limited time")
    return TournamentRisk(Decimal("1.0"), "neutral")
