from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
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
    """Generic limit-order request.

    `market_id` is the legacy name for the contract identifier. The official
    Super Market adapter maps it to `exchangeId`.
    """

    market_id: str
    side: str
    quantity: Decimal
    limit_price: Decimal
    client_order_id: str
    action: str = "buy"
    tournament_id: str | None = None
    expiration_date: datetime | None = None

    @property
    def exchange_id(self) -> str:
        return self.market_id


class TradingVenue(Protocol):
    async def place_order(self, order: OrderRequest) -> dict[str, Any]: ...
    async def get_order(self, order_id: str) -> dict[str, Any]: ...
    async def cancel_order(self, order_id: str) -> dict[str, Any]: ...


class AtomicTradingVenue(Protocol):
    async def place_multi_leg(
        self,
        orders: tuple[OrderRequest, ...],
        *,
        idempotency_key: str,
        relationship_constraint: str | None = None,
    ) -> dict[str, Any]: ...


@dataclass(slots=True)
class ExecutionRecord:
    candidate_id: str
    state: ExecutionState
    order_ids: list[str]
    messages: list[str]


class LiveExecutor:
    """Fail-closed sequential executor retained as a fallback.

    Structural multi-leg opportunities should prefer `AtomicLiveExecutor` on
    Super Market because `/orders/multi-leg` atomically admits all legs.
    """

    def __init__(self, venue: TradingVenue, config: RuntimeConfig) -> None:
        self.venue = venue
        self.config = config

    async def execute(
        self,
        candidate: ExecutionCandidate,
        decision: RiskDecision,
        *,
        tournament_id: str | None = None,
    ) -> ExecutionRecord:
        record = _preflight(candidate, decision, self.config)
        if record.state is ExecutionState.HALTED:
            return record

        q = decision.approved_quantity
        for i, leg in enumerate(candidate.legs):
            request = OrderRequest(
                market_id=leg.market_id,
                side=leg.side.value,
                quantity=q,
                limit_price=leg.max_price,
                client_order_id=f"{candidate.candidate_id}-{i}",
                tournament_id=tournament_id,
            )
            try:
                record.state = ExecutionState.SUBMITTED
                ack = await self.venue.place_order(request)
            except Exception as exc:  # noqa: BLE001 - execution boundary must fail closed
                record.state = _exception_state(exc)
                record.messages.append(f"leg {i} submit failed: {exc}")
                return record

            status = str(ack.get("status", "")).upper()
            order_id = str(ack.get("order_id") or "")
            if order_id:
                record.order_ids.append(order_id)
            record.state = ExecutionState.ACKNOWLEDGED

            if status == "FILLED":
                record.state = ExecutionState.FILLED
                continue
            if status in {"RESTING", "PARTIAL"}:
                record.state = ExecutionState.PARTIAL
                record.messages.append(f"leg {i} not fully filled; reconcile before continuing")
                return record

            record.state = ExecutionState.UNKNOWN
            record.messages.append(f"leg {i} returned unrecognized terminal status {status!r}")
            return record

        record.state = ExecutionState.FILLED
        record.messages.append("all legs reported filled; authoritative REST reconciliation still required")
        return record


class AtomicLiveExecutor:
    """Super Market multi-leg executor using atomic order admission.

    Atomic admission means all legs are persisted or none are. It does *not*
    imply that every marketable limit leg will fill completely. The returned
    state is therefore FILLED only when every leg reports a full fill; otherwise
    the caller must reconcile/cancel residual resting quantities.
    """

    def __init__(self, venue: AtomicTradingVenue, config: RuntimeConfig) -> None:
        self.venue = venue
        self.config = config

    async def execute(
        self,
        candidate: ExecutionCandidate,
        decision: RiskDecision,
        *,
        tournament_id: str | None,
        relationship_constraint: str | None = None,
    ) -> ExecutionRecord:
        record = _preflight(candidate, decision, self.config)
        if record.state is ExecutionState.HALTED:
            return record

        q = decision.approved_quantity
        orders = tuple(
            OrderRequest(
                market_id=leg.market_id,
                side=leg.side.value,
                quantity=q,
                limit_price=leg.max_price,
                client_order_id=f"{candidate.candidate_id}-{i}",
                tournament_id=tournament_id,
            )
            for i, leg in enumerate(candidate.legs)
        )

        try:
            record.state = ExecutionState.SUBMITTED
            response = await self.venue.place_multi_leg(
                orders,
                idempotency_key=f"{candidate.candidate_id}-atomic",
                relationship_constraint=relationship_constraint,
            )
        except Exception as exc:  # noqa: BLE001 - execution boundary must fail closed
            record.state = _exception_state(exc)
            record.messages.append(f"atomic submit failed: {exc}")
            return record

        results = response.get("results")
        if not isinstance(results, list) or len(results) != len(orders):
            record.state = ExecutionState.UNKNOWN
            record.messages.append("multi-leg response did not confirm every requested leg")
            return record

        statuses: list[str] = []
        for item in results:
            if not isinstance(item, dict):
                record.state = ExecutionState.UNKNOWN
                record.messages.append("malformed multi-leg result")
                return record
            order_id = str(item.get("order_id") or "")
            if order_id:
                record.order_ids.append(order_id)
            statuses.append(str(item.get("status", "")).upper())

        record.state = ExecutionState.ACKNOWLEDGED
        if all(status == "FILLED" for status in statuses):
            record.state = ExecutionState.FILLED
            record.messages.append(
                "all atomic legs reported filled; authoritative REST reconciliation still required"
            )
            return record
        if all(status in {"FILLED", "RESTING", "PARTIAL"} for status in statuses):
            record.state = ExecutionState.PARTIAL
            record.messages.append(
                "atomic admission succeeded but at least one leg remains unfilled; reconcile/cancel residuals"
            )
            return record

        record.state = ExecutionState.UNKNOWN
        record.messages.append(f"unexpected multi-leg statuses: {statuses}")
        return record


def _preflight(
    candidate: ExecutionCandidate,
    decision: RiskDecision,
    config: RuntimeConfig,
) -> ExecutionRecord:
    record = ExecutionRecord(candidate.candidate_id, ExecutionState.DETECTED, [], [])
    if not config.live_enabled(LIVE_ACK):
        record.state = ExecutionState.HALTED
        record.messages.append("live trading gate is disabled")
        return record
    if not decision.approved:
        record.state = ExecutionState.HALTED
        record.messages.extend(decision.reasons)
        return record
    record.state = ExecutionState.RISK_APPROVED
    return record


def _exception_state(exc: Exception) -> ExecutionState:
    if bool(getattr(exc, "outcome_unknown", False)):
        return ExecutionState.UNKNOWN
    status = getattr(exc, "status_code", None)
    if isinstance(status, int) and 400 <= status < 500:
        return ExecutionState.HALTED
    return ExecutionState.UNKNOWN
