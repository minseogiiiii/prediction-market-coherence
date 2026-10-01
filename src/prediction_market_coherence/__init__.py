"""Execution-aware prediction-market coherence research toolkit."""

from .detector import Violation, detect_monotonicity_violations
from .execution import build_two_leg_candidate, consume_asks
from .live import AtomicLiveExecutor, LiveExecutor
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
from .susq_client import AuthConfig, EndpointMap, SusqClient
from .susq_schema import ExchangeOrderBookSchema, SusqVenueAdapter

__all__ = [
    "AtomicLiveExecutor",
    "AuthConfig",
    "BookLevel",
    "EndpointMap",
    "ExchangeOrderBookSchema",
    "ExecutionCandidate",
    "LiveExecutor",
    "MarketContract",
    "OrderBook",
    "RelationType",
    "Relationship",
    "Side",
    "SusqClient",
    "SusqVenueAdapter",
    "ThresholdMarket",
    "Violation",
    "build_two_leg_candidate",
    "consume_asks",
    "detect_monotonicity_violations",
]
