from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class TimedFeature:
    available_at: datetime
    value: Decimal
    source: str


@dataclass(frozen=True, slots=True)
class TimedDecision:
    decision_at: datetime
    feature_sources: tuple[str, ...]


def assert_no_lookahead(decision: TimedDecision, features: Iterable[TimedFeature]) -> None:
    """Raise if any feature was unavailable when the decision was made."""
    if decision.decision_at.tzinfo is None:
        raise ValueError("decision timestamp must be timezone-aware")
    for feature in features:
        if feature.available_at.tzinfo is None:
            raise ValueError(f"feature {feature.source} timestamp must be timezone-aware")
        if feature.available_at > decision.decision_at:
            raise ValueError(
                f"look-ahead: feature {feature.source} available {feature.available_at.isoformat()} "
                f"after decision {decision.decision_at.isoformat()}"
            )


def execution_adjusted_edge(model_probability: Decimal, ask_price: Decimal, *, uncertainty_buffer: Decimal, execution_buffer: Decimal) -> Decimal:
    if not Decimal(0) <= model_probability <= Decimal(1):
        raise ValueError("model_probability must be in [0,1]")
    if not Decimal(0) < ask_price < Decimal(1):
        raise ValueError("ask_price must be in (0,1)")
    return model_probability - ask_price - uncertainty_buffer - execution_buffer
