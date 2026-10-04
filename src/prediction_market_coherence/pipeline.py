from __future__ import annotations

from dataclasses import dataclass

from .config import RuntimeConfig
from .execution import build_two_leg_candidate
from .models import ExecutionCandidate, OrderBook, PortfolioSnapshot, Relationship
from .risk import RiskDecision, RiskManager


@dataclass(frozen=True, slots=True)
class ScannedOpportunity:
    relationship: Relationship
    candidate: ExecutionCandidate
    risk: RiskDecision


def scan_relationships(
    relationships: list[Relationship],
    books: dict[str, OrderBook],
    portfolio: PortfolioSnapshot,
    config: RuntimeConfig,
) -> tuple[ScannedOpportunity, ...]:
    """Pure orchestration layer: logic -> execution -> risk.

    Relationships with missing/insufficient books simply produce no candidate.
    The function has no network or order side effects, making it replay-safe.
    """
    manager = RiskManager(config)
    out: list[ScannedOpportunity] = []
    for relationship in relationships:
        candidate = build_two_leg_candidate(
            relationship,
            books,
            min_edge=config.min_edge,
            max_quantity=config.max_order_size,
        )
        if candidate is None:
            continue
        out.append(ScannedOpportunity(relationship, candidate, manager.assess(candidate, portfolio)))
    return tuple(sorted(out, key=lambda x: x.candidate.expected_profit, reverse=True))
