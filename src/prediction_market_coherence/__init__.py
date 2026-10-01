"""Execution-aware prediction-market coherence research toolkit."""

from .detector import Violation, detect_monotonicity_violations
from .execution import build_two_leg_candidate, consume_asks
from .models import (
    BookLevel,
    ExecutionCandidate,
    MarketContract,
    OrderBook,
    Relationship,
    RelationType,
    Side,
    ThresholdMarket,
)

__all__ = [
    "BookLevel",
    "ExecutionCandidate",
    "MarketContract",
    "OrderBook",
    "RelationType",
    "Relationship",
    "Side",
    "ThresholdMarket",
    "Violation",
    "build_two_leg_candidate",
    "consume_asks",
    "detect_monotonicity_violations",
]
