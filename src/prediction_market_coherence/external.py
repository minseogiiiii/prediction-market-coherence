from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Protocol


@dataclass(frozen=True, slots=True)
class ExternalQuote:
    source: str
    canonical_event_id: str
    probability: Decimal
    observed_at: datetime
    settlement_fingerprint: str

    def __post_init__(self) -> None:
        if not Decimal(0) <= self.probability <= Decimal(1):
            raise ValueError("probability must be in [0,1]")
        if self.observed_at.tzinfo is None:
            raise ValueError("observed_at must be timezone-aware")
        if not self.settlement_fingerprint:
            raise ValueError("settlement_fingerprint is required")


class ExternalSignalSource(Protocol):
    def fetch(self) -> tuple[ExternalQuote, ...]: ...


def settlement_compatible(a: ExternalQuote, b: ExternalQuote) -> bool:
    """Cross-venue comparison is allowed only for explicitly matching rules."""
    return (
        a.canonical_event_id == b.canonical_event_id
        and a.settlement_fingerprint == b.settlement_fingerprint
    )
