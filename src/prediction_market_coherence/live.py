from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Any, Protocol

from .config import RuntimeConfig
from .models import ExecutionCandidate
from .risk import RiskDecision

LIVE_ACK = "I_UNDERSTAND_PREDICTIONS_CUP_BOT_ORDERS_ARE_FINAL"


class ExecutionState(str, Enum):
    DETECTED = "DETECTED"
    RISK_APPROVED = "RISK_APPROVED"
    SUBMITTED = "SUBMITTED"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    PARTIAL = "PARTIAL"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    UNKNOWN = "UNKNOWN"
    RECONCILED = "RECONCILED"
    HALTED = "HALTED"


@dataclass(frozen=True, slots=True)
class OrderRequest:
    market_id: str
    side: str
    quantity: Decimal
    limit_price: Decimal
    client_order_id: str


class TradingVenue(Protocol):
    async def place_order(self, order: OrderRequest) -> dict[str, Any]: ...
    async def get_order(self, order_id: str) -> dict[str, Any]: ...
    async def cancel_order(self, order_id: str) -> dict[str, Any]: ...


@dataclass(slots=True)
class ExecutionRecord:
    candidate_id: str
    state: ExecutionState
    order_ids: list[str]
    messages: list[str]


class LiveExecutor:
    """Fail-closed sequential live executor.

    This class deliberately does not claim atomicity across multiple legs. After
    every accepted leg, callers must reconcile and revalidate the remaining leg.
    It is usable only when the explicit live acknowledgement is present.
    """

    def __init__(self, venue: TradingVenue, config: RuntimeConfig) -> None:
        self.venue = venue
        self.config = config

    async def execute(self, candidate: ExecutionCandidate, decision: RiskDecision) -> ExecutionRecord:
        record = ExecutionRecord(candidate.candidate_id, ExecutionState.DETECTED, [], [])
        if not self.config.live_enabled(LIVE_ACK):
            record.state = ExecutionState.HALTED
            record.messages.append("live trading gate is disabled")
            return record
        if not decision.approved:
            record.state = ExecutionState.HALTED
            record.messages.extend(decision.reasons)
            return record
        record.state = ExecutionState.RISK_APPROVED

        q = decision.approved_quantity
        for i, leg in enumerate(candidate.legs):
            request = OrderRequest(
                market_id=leg.market_id,
                side=leg.side.value,
                quantity=q,
                limit_price=leg.max_price,
                client_order_id=f"{candidate.candidate_id}-{i}",
            )
            try:
                ack = await self.venue.place_order(request)
            except Exception as exc:  # noqa: BLE001 -- outcome unknown; do not blind-retry
                record.state = ExecutionState.UNKNOWN
                record.messages.append(f"leg {i} submit outcome unknown: {exc}")
                return record
            order_id = str(ack.get("order_id") or ack.get("id") or "")
            if not order_id:
                record.state = ExecutionState.UNKNOWN
                record.messages.append(f"leg {i} had no explicit order id confirmation")
                return record
            record.order_ids.append(order_id)
            record.state = ExecutionState.ACKNOWLEDGED
            status = str(ack.get("status", "")).upper()
            if status in {"FILLED", "EXECUTED", "COMPLETE"}:
                record.state = ExecutionState.FILLED
                continue
            # Resting/partial first legs create leg risk. Stop and require caller
            # reconciliation rather than assuming the hedge exists.
            record.state = ExecutionState.PARTIAL
            record.messages.append(f"leg {i} not fully filled; reconcile before continuing")
            return record
        record.state = ExecutionState.RECONCILED
        return record
