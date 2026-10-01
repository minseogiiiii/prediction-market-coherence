from datetime import UTC, datetime
from decimal import Decimal

import pytest

from prediction_market_coherence.backtest import TimedDecision, TimedFeature, assert_no_lookahead
from prediction_market_coherence.config import RuntimeConfig
from prediction_market_coherence.models import (
    ExecutionCandidate,
    PortfolioSnapshot,
    Side,
    TradeLeg,
)
from prediction_market_coherence.risk import RiskManager
from prediction_market_coherence.signals import (
    ProbabilitySignal,
    brier_score,
    kelly_fraction,
    shrink_probability,
    weighted_probability,
)
from prediction_market_coherence.storage import ResearchStore

D=Decimal; NOW=datetime.now(UTC)


def mk_candidate():
    return ExecutionCandidate('c','r',(TradeLeg('A',Side.NO,D('10'),D('.5')),TradeLeg('B',Side.NO,D('10'),D('.5'))),D('1'),D('.9'),D('.1'),D('10'),D('1'),D('0'))


def test_risk_rejects_edge_cash_market_and_total_limits():
    c=mk_candidate()
    cfg=RuntimeConfig(min_edge=D('.2'),max_order_size=D('10'),max_market_exposure=D('1'),max_total_exposure=D('2'),min_cash_buffer=D('1000'),max_book_age_seconds=D('2'))
    d=RiskManager(cfg).assess(c,PortfolioSnapshot(D('5'),{'A':D('1')}))
    assert not d.approved
    text=' '.join(d.reasons)
    assert 'edge below' in text and 'cash buffer' in text and 'market exposure' in text and 'total exposure' in text


def test_risk_rejects_theoretical_only():
    c=mk_candidate()
    c=ExecutionCandidate(c.candidate_id,c.relationship_id,c.legs,c.guaranteed_payout_per_bundle,c.cost_per_bundle,c.executable_edge_per_bundle,c.max_profitable_quantity,c.expected_profit,c.book_age_seconds,True)
    assert not RiskManager(RuntimeConfig(min_cash_buffer=D('0'))).assess(c,PortfolioSnapshot(D('10000'),{})).approved


def test_signal_validation_branches():
    with pytest.raises(ValueError): ProbabilitySignal('x',D('1.1'),D('1'))
    with pytest.raises(ValueError): ProbabilitySignal('x',D('.5'),D('-1'))
    with pytest.raises(ValueError): weighted_probability([])
    with pytest.raises(ValueError): weighted_probability([ProbabilitySignal('x',D('.5'),D('1'))],half_life_seconds=D('0'))
    with pytest.raises(ValueError): shrink_probability(D('.5'),D('2'))
    with pytest.raises(ValueError): kelly_fraction(D('.5'),D('0'))
    with pytest.raises(ValueError): kelly_fraction(D('.6'),D('.5'),fraction=D('2'))
    with pytest.raises(ValueError): brier_score([])
    with pytest.raises(ValueError): brier_score([(D('2'),True)])


def test_backtest_timezone_guards():
    naive=datetime(2026,1,1)  # noqa: DTZ001 -- deliberately naive for guard test
    with pytest.raises(ValueError): assert_no_lookahead(TimedDecision(naive,()),[])
    with pytest.raises(ValueError): assert_no_lookahead(TimedDecision(NOW,()),[TimedFeature(naive,D('1'),'x')])


def test_store_candidate_and_event(tmp_path):
    with ResearchStore(tmp_path/'x.db') as s:
        s.record_candidate(mk_candidate(),created_at=NOW)
        s.record_event('TEST',{'a':D('1.2')},created_at=NOW,candidate_id='c')
        assert s.conn.execute('select count(*) from signals').fetchone()[0]==1
        assert s.conn.execute('select count(*) from execution_events').fetchone()[0]==1
