import asyncio
from decimal import Decimal

from prediction_market_coherence.config import RuntimeConfig
from prediction_market_coherence.live import LIVE_ACK, ExecutionState, LiveExecutor
from prediction_market_coherence.models import ExecutionCandidate, Side, TradeLeg
from prediction_market_coherence.risk import RiskDecision

D=Decimal


def candidate():
    return ExecutionCandidate('c','r',(TradeLeg('A',Side.NO,D('10'),D('.45')),TradeLeg('B',Side.NO,D('10'),D('.5'))),D('1'),D('.95'),D('.05'),D('10'),D('.5'),D('0'))


class Venue:
    def __init__(self,statuses): self.statuses=list(statuses); self.calls=0
    async def place_order(self,order):
        self.calls+=1; status=self.statuses.pop(0); return {'order_id':f'o{self.calls}','status':status}
    async def get_order(self,order_id): return {}
    async def cancel_order(self,order_id): return {}


def test_live_gate_defaults_off():
    v=Venue(['FILLED','FILLED']); e=LiveExecutor(v,RuntimeConfig())
    r=asyncio.run(e.execute(candidate(),RiskDecision(True,(),D('10'))))
    assert r.state is ExecutionState.HALTED and v.calls==0


def test_live_requires_exact_ack_and_stops_on_partial_first_leg():
    cfg=RuntimeConfig(allow_live_trading=True,acknowledgement=LIVE_ACK)
    v=Venue(['PARTIAL','FILLED']); e=LiveExecutor(v,cfg)
    r=asyncio.run(e.execute(candidate(),RiskDecision(True,(),D('10'))))
    assert r.state is ExecutionState.PARTIAL and v.calls==1


def test_live_two_explicit_fills_reaches_reconciled():
    cfg=RuntimeConfig(allow_live_trading=True,acknowledgement=LIVE_ACK)
    v=Venue(['FILLED','FILLED']); e=LiveExecutor(v,cfg)
    r=asyncio.run(e.execute(candidate(),RiskDecision(True,(),D('10'))))
    assert r.state is ExecutionState.RECONCILED and len(r.order_ids)==2


def test_missing_order_id_is_unknown_not_success():
    class Bad(Venue):
        async def place_order(self,order): return {'status':'FILLED'}
    cfg=RuntimeConfig(allow_live_trading=True,acknowledgement=LIVE_ACK)
    r=asyncio.run(LiveExecutor(Bad([]),cfg).execute(candidate(),RiskDecision(True,(),D('10'))))
    assert r.state is ExecutionState.UNKNOWN
