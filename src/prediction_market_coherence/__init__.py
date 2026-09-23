"""Prediction Market Coherence detector."""

from .detector import Violation, detect_monotonicity_violations
from .models import ThresholdMarket

__all__ = ["ThresholdMarket", "Violation", "detect_monotonicity_violations"]
