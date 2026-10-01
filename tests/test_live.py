import asyncio
from decimal import Decimal

from prediction_market_coherence.config import RuntimeConfig
from prediction_market_coherence.live import (
    LIVE_ACK,
    AtomicLiveExecutor,
    ExecutionState,
    LiveExecutor,
)
from prediction_market_coherence.models import ExecutionCandidate, Side, TradeLeg
from prediction_market_coherence.risk import RiskDecision

D = Decimal


def candidate():
    return ExecutionCandidate(
        "c",
        "r",
        (
            TradeLeg("A", Side.NO, D("10"), D(".45")),
            TradeLeg("B", Side.NO, D("10"), D(".5")),
        ),
        D("1"),
        D(".95"),
        D(".05"),
        D("10"),
        D(".5"),
        D("0"),
    )


class Venue:
    def __init__(self, statuses):
        self.statuses = list(statuses)
        self.calls = 0

    async def place_order(self, order):
        self.calls += 1
        status = self.statuses.pop(0)
        return {"order_id": f"o{self.calls}", "status": status}

    async def get_order(self, order_id):
        return {}

    async def cancel_order(self, order_id):
        return {}


class AtomicVenue:
    def __init__(self, statuses):
        self.statuses = list(statuses)
        self.calls = 0
        self.relationship_constraint = None

    async def place_multi_leg(self, orders, *, idempotency_key, relationship_constraint=None):
        self.calls += 1
        self.relationship_constraint = relationship_constraint
        return {
            "results": [
                {"index": i, "order_id": f"o{i}", "status": status}
                for i, status in enumerate(self.statuses)
            ]
        }


def test_live_gate_defaults_off():
    venue = Venue(["FILLED", "FILLED"])
    executor = LiveExecutor(venue, RuntimeConfig())
    result = asyncio.run(executor.execute(candidate(), RiskDecision(True, (), D("10"))))
    assert result.state is ExecutionState.HALTED
    assert venue.calls == 0


def test_live_stops_on_partial_first_leg():
    cfg = RuntimeConfig(allow_live_trading=True, acknowledgement=LIVE_ACK)
    venue = Venue(["PARTIAL", "FILLED"])
    result = asyncio.run(
        LiveExecutor(venue, cfg).execute(candidate(), RiskDecision(True, (), D("10")))
    )
    assert result.state is ExecutionState.PARTIAL
    assert venue.calls == 1


def test_sequential_full_fills_are_not_called_reconciled_automatically():
    cfg = RuntimeConfig(allow_live_trading=True, acknowledgement=LIVE_ACK)
    venue = Venue(["FILLED", "FILLED"])
    result = asyncio.run(
        LiveExecutor(venue, cfg).execute(candidate(), RiskDecision(True, (), D("10")))
    )
    assert result.state is ExecutionState.FILLED
    assert len(result.order_ids) == 2
    assert "reconciliation" in result.messages[-1]


def test_atomic_executor_submits_once_and_passes_relationship_constraint():
    cfg = RuntimeConfig(allow_live_trading=True, acknowledgement=LIVE_ACK)
    venue = AtomicVenue(["FILLED", "FILLED"])
    result = asyncio.run(
        AtomicLiveExecutor(venue, cfg).execute(
            candidate(),
            RiskDecision(True, (), D("10")),
            tournament_id="tid",
            relationship_constraint="rel-id",
        )
    )
    assert result.state is ExecutionState.FILLED
    assert venue.calls == 1
    assert venue.relationship_constraint == "rel-id"
    assert len(result.order_ids) == 2


def test_atomic_executor_detects_resting_residual():
    cfg = RuntimeConfig(allow_live_trading=True, acknowledgement=LIVE_ACK)
    venue = AtomicVenue(["FILLED", "RESTING"])
    result = asyncio.run(
        AtomicLiveExecutor(venue, cfg).execute(
            candidate(), RiskDecision(True, (), D("10")), tournament_id="tid"
        )
    )
    assert result.state is ExecutionState.PARTIAL


def test_atomic_known_4xx_failure_halts_not_unknown():
    class Error(Exception):
        status_code = 422
        outcome_unknown = False

    class BadAtomic:
        async def place_multi_leg(self, orders, *, idempotency_key, relationship_constraint=None):
            raise Error("relationship violation")

    cfg = RuntimeConfig(allow_live_trading=True, acknowledgement=LIVE_ACK)
    result = asyncio.run(
        AtomicLiveExecutor(BadAtomic(), cfg).execute(
            candidate(), RiskDecision(True, (), D("10")), tournament_id="tid"
        )
    )
    assert result.state is ExecutionState.HALTED
