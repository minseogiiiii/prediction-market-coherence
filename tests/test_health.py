from decimal import Decimal

from prediction_market_coherence.health import HealthSnapshot, KillSwitchConfig, evaluate_health


def test_healthy_system_allows_trading():
    d=evaluate_health(HealthSnapshot(100,1,0,0,5,1,100))
    assert d.trading_allowed


def test_any_economic_unknown_halts():
    d=evaluate_health(HealthSnapshot(100,0,1,0,0))
    assert not d.trading_allowed and any('unknown' in r for r in d.reasons)


def test_error_stale_open_order_and_reconcile_limits_halt():
    s=HealthSnapshot(10,5,0,1,101,8,10)
    d=evaluate_health(s,KillSwitchConfig(max_api_error_rate=Decimal('.2'),max_open_orders=100,max_stale_rate=Decimal('.5')))
    assert not d.trading_allowed and len(d.reasons)==4


def test_zero_denominators_are_safe():
    s=HealthSnapshot(0,0,0,0,0)
    assert s.api_error_rate==0 and s.stale_rate==0
