from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from .config import RuntimeConfig
from .models import ZERO, ExecutionCandidate, PortfolioSnapshot


@dataclass(frozen=True, slots=True)
class RiskDecision:
    approved: bool
    reasons: tuple[str, ...]
    approved_quantity: Decimal


class RiskManager:
    def __init__(self, config: RuntimeConfig) -> None:
        self.config = config

    def assess(self, candidate: ExecutionCandidate, portfolio: PortfolioSnapshot) -> RiskDecision:
        reasons: list[str] = []
        if candidate.theoretical_only:
            reasons.append("candidate is theoretical-only")
        if candidate.executable_edge_per_bundle < self.config.min_edge:
            reasons.append("edge below minimum")
        if candidate.book_age_seconds > self.config.max_book_age_seconds:
            reasons.append("order book is stale")

        quantity = min(candidate.max_profitable_quantity, self.config.max_order_size)
        if quantity <= ZERO:
            reasons.append("non-positive quantity")
            return RiskDecision(False, tuple(reasons), ZERO)

        # Worst-case capital required for the bundle uses the observed average cost.
        capital = candidate.cost_per_bundle * quantity
        if portfolio.cash - capital < self.config.min_cash_buffer:
            reasons.append("cash buffer would be breached")

        incremental_by_market: dict[str, Decimal] = {}
        for leg in candidate.legs:
            # exposure is bounded by purchase notional for long binary shares
            incremental_by_market[leg.market_id] = incremental_by_market.get(
                leg.market_id, ZERO
            ) + leg.max_price * quantity

        for market_id, inc in incremental_by_market.items():
            current = portfolio.market_exposure.get(market_id, ZERO) + portfolio.open_order_exposure.get(
                market_id, ZERO
            )
            if current + inc > self.config.max_market_exposure:
                reasons.append(f"market exposure limit: {market_id}")

        if portfolio.total_exposure + capital > self.config.max_total_exposure:
            reasons.append("total exposure limit")

        return RiskDecision(not reasons, tuple(reasons), quantity if not reasons else ZERO)
