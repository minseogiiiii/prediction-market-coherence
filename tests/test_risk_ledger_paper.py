from datetime import UTC, datetime, timedelta
from decimal import Decimal

from prediction_market_coherence.config import RuntimeConfig
from prediction_market_coherence.execution import build_two_leg_candidate
from prediction_market_coherence.ledger import Ledger
from prediction_market_coherence.models import BookLevel, OrderBook, PortfolioSnapshot, Side
from prediction_market_coherence.paper import PaperBroker
from prediction_market_coherence.relationships import mutually_exclusive
from prediction_market_coherence.risk import RiskManager

D=Decimal
NOW=datetime.now(UTC)


def book(mid, observed=NOW, no_asks=()):
    return OrderBook(mid, observed, no_asks=tuple(BookLevel(D(p),D(s)) for p,s in no_asks))


def candidate(observed=NOW):
    rel=mutually_exclusive('r','A','B',evidence='rules')
    books={'A':book('A',observed,no_asks=(("0.45","100"),)), 'B':book('B',observed,no_asks=(("0.50","100"),))}
    return build_two_leg_candidate(rel,books,min_edge=D("0.01")),books


def test_risk_approves_small_fresh_edge():
    c,_=candidate()
    assert c is not None
    cfg=RuntimeConfig(min_edge=D("0.01"),max_order_size=D("20"),max_market_exposure=D("1000"),max_total_exposure=D("5000"),min_cash_buffer=D("100"),max_book_age_seconds=D("3"))
    d=RiskManager(cfg).assess(c,PortfolioSnapshot(cash=D("10000"),market_exposure={}))
    assert d.approved and d.approved_quantity == D("20")


def test_risk_rejects_stale_book():
    c,_=candidate(NOW-timedelta(seconds=10))
    assert c is not None
    cfg=RuntimeConfig(max_book_age_seconds=D("2"),min_cash_buffer=D("0"))
    d=RiskManager(cfg).assess(c,PortfolioSnapshot(cash=D("10000"),market_exposure={}))
    assert not d.approved and any('stale' in r for r in d.reasons)


def test_ledger_opposite_share_pairing_returns_one_per_pair():
    l=Ledger(D("100"))
    l.apply_buy('M',Side.YES,D("10"),D("0.4"))
    assert l.cash == D("96.0")
    l.apply_buy('M',Side.NO,D("5"),D("0.5"))
    # spend 2.5 then receive 5 from cancelled YES/NO pairs
    assert l.cash == D("98.5")
    assert l.positions[("M",Side.YES)] == D("5")
    assert ("M",Side.NO) not in l.positions


def test_ledger_settlement():
    l=Ledger(D("100")); l.apply_buy('M',Side.YES,D("10"),D("0.4"))
    payout=l.settle('M',Side.YES)
    assert payout == D("10") and l.cash == D("106.0") and l.positions == {}


def test_paper_broker_atomic_precheck():
    c,books=candidate(); assert c is not None
    l=Ledger(D("1000"))
    result=PaperBroker().execute(c,books,l,quantity=D("10"))
    assert result.success and len(result.fills)==2
    # 10*(.45+.50)
    assert l.cash == D("990.50")


def test_paper_broker_does_not_modify_ledger_on_missing_second_leg_depth():
    c,books=candidate(); assert c is not None
    bad=dict(books); bad['B']=book('B',no_asks=(("0.50","2"),))
    l=Ledger(D("1000")); before=l.cash
    r=PaperBroker().execute(c,bad,l,quantity=D("10"))
    assert not r.success and l.cash==before and l.positions=={}


def test_reconciliation_reports_mismatch():
    l=Ledger(D("100")); l.apply_buy('M',Side.YES,D("2"),D("0.4"))
    mismatches=l.reconcile_positions({('M',Side.YES):D("1")})
    assert len(mismatches)==1 and 'local=2' in mismatches[0]
