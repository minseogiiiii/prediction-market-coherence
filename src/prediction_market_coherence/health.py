from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class HealthSnapshot:
    api_requests: int
    api_errors: int
    unknown_order_outcomes: int
    reconciliation_mismatches: int
    open_orders: int
    stale_books: int = 0
    observed_books: int = 0

    @property
    def api_error_rate(self) -> Decimal:
        if self.api_requests <= 0:
            return Decimal(0)
        return Decimal(self.api_errors) / Decimal(self.api_requests)

    @property
    def stale_rate(self) -> Decimal:
        if self.observed_books <= 0:
            return Decimal(0)
        return Decimal(self.stale_books) / Decimal(self.observed_books)


@dataclass(frozen=True, slots=True)
class KillSwitchConfig:
    max_api_error_rate: Decimal = Decimal("0.20")
    max_unknown_orders: int = 0
    max_reconciliation_mismatches: int = 0
    max_open_orders: int = 100
    max_stale_rate: Decimal = Decimal("0.50")


@dataclass(frozen=True, slots=True)
class HealthDecision:
    trading_allowed: bool
    reasons: tuple[str, ...]


def evaluate_health(
    snapshot: HealthSnapshot,
    config: KillSwitchConfig | None = None,
) -> HealthDecision:
    config = config or KillSwitchConfig()
    reasons: list[str] = []
    if snapshot.api_error_rate > config.max_api_error_rate:
        reasons.append(f"api error rate {snapshot.api_error_rate} exceeds {config.max_api_error_rate}")
    if snapshot.unknown_order_outcomes > config.max_unknown_orders:
        reasons.append("unknown order outcome requires reconciliation")
    if snapshot.reconciliation_mismatches > config.max_reconciliation_mismatches:
        reasons.append("position/balance reconciliation mismatch")
    if snapshot.open_orders > config.max_open_orders:
        reasons.append("too many open orders")
    if snapshot.observed_books > 0 and snapshot.stale_rate > config.max_stale_rate:
        reasons.append("stale market-data rate too high")
    return HealthDecision(not reasons, tuple(reasons))
