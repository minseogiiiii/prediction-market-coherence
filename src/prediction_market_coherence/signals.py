from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal
from math import log

from .models import ONE, ZERO

EPS = Decimal("0.000001")


def clamp_probability(p: Decimal) -> Decimal:
    return min(ONE - EPS, max(EPS, p))


@dataclass(frozen=True, slots=True)
class ProbabilitySignal:
    source: str
    probability: Decimal
    weight: Decimal
    age_seconds: Decimal = ZERO
    confidence: Decimal = ONE

    def __post_init__(self) -> None:
        if not ZERO <= self.probability <= ONE:
            raise ValueError("probability must be in [0,1]")
        if self.weight < ZERO or self.confidence < ZERO:
            raise ValueError("weight/confidence cannot be negative")


def weighted_probability(signals: Iterable[ProbabilitySignal], *, half_life_seconds: Decimal | None = None) -> Decimal:
    numerator = ZERO
    denominator = ZERO
    for signal in signals:
        decay = ONE
        if half_life_seconds is not None:
            if half_life_seconds <= ZERO:
                raise ValueError("half_life_seconds must be positive")
            # Decimal exponentiation for arbitrary real powers is awkward; float is
            # acceptable here because this is model weighting, not cash accounting.
            decay = Decimal(str(0.5 ** float(signal.age_seconds / half_life_seconds)))
        effective = signal.weight * signal.confidence * decay
        numerator += signal.probability * effective
        denominator += effective
    if denominator <= ZERO:
        raise ValueError("at least one positive-weight signal is required")
    return numerator / denominator


def shrink_probability(p: Decimal, strength: Decimal) -> Decimal:
    if not ZERO <= strength <= ONE:
        raise ValueError("strength must be in [0,1]")
    return Decimal("0.5") + strength * (p - Decimal("0.5"))


def kelly_fraction(probability: Decimal, price: Decimal, *, fraction: Decimal = ONE) -> Decimal:
    p = clamp_probability(probability)
    if not ZERO < price < ONE:
        raise ValueError("price must be in (0,1)")
    if not ZERO <= fraction <= ONE:
        raise ValueError("fraction must be in [0,1]")
    if p <= price:
        return ZERO
    full = (p - price) / (ONE - price)
    return min(ONE, full * fraction)


def brier_score(predictions: Iterable[tuple[Decimal, bool]]) -> Decimal:
    pairs = list(predictions)
    if not pairs:
        raise ValueError("predictions cannot be empty")
    total = ZERO
    for p, y in pairs:
        if not ZERO <= p <= ONE:
            raise ValueError("probability must be in [0,1]")
        outcome = ONE if y else ZERO
        total += (p - outcome) ** 2
    return total / Decimal(len(pairs))


def log_loss(predictions: Iterable[tuple[Decimal, bool]]) -> float:
    pairs = list(predictions)
    if not pairs:
        raise ValueError("predictions cannot be empty")
    total = 0.0
    for p, y in pairs:
        q = float(clamp_probability(p))
        total += -(log(q) if y else log(1.0 - q))
    return total / len(pairs)
