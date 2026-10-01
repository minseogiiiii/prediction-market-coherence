from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from prediction_market_coherence.backtest import (
    TimedDecision,
    TimedFeature,
    assert_no_lookahead,
    execution_adjusted_edge,
)
from prediction_market_coherence.external import ExternalQuote, settlement_compatible
from prediction_market_coherence.maker import MakerConfig, adverse_selection_cost, make_quote
from prediction_market_coherence.news import NewsEvent, map_event_to_markets
from prediction_market_coherence.signals import (
    ProbabilitySignal,
    brier_score,
    kelly_fraction,
    shrink_probability,
    weighted_probability,
)
from prediction_market_coherence.tournament import TournamentState, tournament_risk_multiplier

D=Decimal
NOW=datetime(2026,10,1,16,0,tzinfo=UTC)


def test_weighted_probability():
    p=weighted_probability([ProbabilitySignal('a',D('.6'),D('2')),ProbabilitySignal('b',D('.4'),D('1'))])
    assert p == D('0.5333333333333333333333333333')


def test_weighted_probability_time_decay():
    p=weighted_probability([ProbabilitySignal('fresh',D('.8'),D('1'),D('0')),ProbabilitySignal('old',D('.2'),D('1'),D('100'))],half_life_seconds=D('100'))
    assert p == D('0.6')


def test_shrink_and_fractional_kelly():
    assert shrink_probability(D('.7'),D('.5')) == D('.6')
    assert kelly_fraction(D('.60'),D('.55'),fraction=D('.5')) == D('0.05555555555555555555555555555')
    assert kelly_fraction(D('.50'),D('.55')) == 0


def test_brier_score():
    assert brier_score([(D('.8'),True),(D('.2'),False)]) == D('.04')


def test_no_lookahead_guard():
    decision=TimedDecision(NOW,('x',))
    assert_no_lookahead(decision,[TimedFeature(NOW-timedelta(seconds=1),D('1'),'x')])
    with pytest.raises(ValueError): assert_no_lookahead(decision,[TimedFeature(NOW+timedelta(seconds=1),D('1'),'future')])


def test_execution_adjusted_edge_requires_buffers():
    assert execution_adjusted_edge(D('.60'),D('.55'),uncertainty_buffer=D('.02'),execution_buffer=D('.01')) == D('.02')


def test_settlement_compatibility_is_strict():
    a=ExternalQuote('x','event',D('.5'),NOW,'rules-v1')
    b=ExternalQuote('y','event',D('.6'),NOW,'rules-v1')
    c=ExternalQuote('y','event',D('.6'),NOW,'rules-v2')
    assert settlement_compatible(a,b)
    assert not settlement_compatible(a,c)


def test_market_maker_inventory_skews_reservation_down_when_long_yes():
    cfg=MakerConfig(half_spread=D('.02'),inventory_skew=D('.001'),max_inventory=D('100'))
    q=make_quote(D('.60'),D('10'),cfg)
    assert q.enabled and q.reservation_price == D('.590') and q.bid==D('.570') and q.ask==D('.610')


def test_market_maker_halts_at_inventory_limit():
    assert not make_quote(D('.5'),D('500'),MakerConfig(max_inventory=D('500'))).enabled


def test_adverse_selection_cost_sign():
    assert adverse_selection_cost(D('.5'),D('.45'),bought=True) == D('.05')
    assert adverse_selection_cost(D('.5'),D('.55'),bought=False) == D('.05')


def test_news_mapper_only_maps_and_does_not_trade():
    event=NewsEvent('wire',NOW,'headline',('Alpha','Beta'),D('.9'))
    r=map_event_to_markets(event,{'m1':{'Alpha','Beta'},'m2':{'Gamma'}},threshold=D('.8'))
    assert len(r)==1 and r[0].market_id=='m1'


def test_tournament_multiplier_bounded():
    for hours in [D('1000'),D('100'),D('10')]:
        for bal in [D('80000'),D('100000'),D('120000')]:
            x=tournament_risk_multiplier(TournamentState(bal,D('100000'),hours)).risk_multiplier
            assert D('.5') <= x <= D('1.25')
