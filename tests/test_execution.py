import random
from datetime import UTC, datetime
from decimal import Decimal

from prediction_market_coherence.execution import build_two_leg_candidate, consume_asks
from prediction_market_coherence.models import BookLevel, OrderBook, Side
from prediction_market_coherence.relationships import implication, mutually_exclusive

D=Decimal
NOW=datetime.now(UTC)


def book(mid, yes_asks=(), no_asks=()):
    return OrderBook(mid, NOW, yes_asks=tuple(BookLevel(D(p),D(s)) for p,s in yes_asks), no_asks=tuple(BookLevel(D(p),D(s)) for p,s in no_asks))


def test_consume_asks_vwap():
    f=consume_asks((BookLevel(D("0.4"),D("10")),BookLevel(D("0.5"),D("10"))),D("15"))
    assert f.complete
    assert f.notional == D("6.5")
    assert f.average_price == D("0.4333333333333333333333333333")
    assert f.worst_price == D("0.5")


def test_consume_asks_insufficient_depth():
    f=consume_asks((BookLevel(D("0.4"),D("2")),),D("3"))
    assert not f.complete and f.filled == D("2")


def test_mutual_exclusion_candidate_uses_no_asks_and_depth():
    rel=mutually_exclusive("r","A","B",evidence="rules")
    books={"A":book("A",no_asks=(("0.45","100"),("0.49","100"))),"B":book("B",no_asks=(("0.51","50"),("0.54","150")))}
    c=build_two_leg_candidate(rel,books,min_edge=D("0.01"))
    assert c is not None
    # q=50 cost=.96 edge=.04 profit=2; q=100 cost=.975 edge=.025 profit=2.5, so q=100 wins.
    assert c.max_profitable_quantity == D("100")
    assert c.executable_edge_per_bundle == D("0.025")
    assert c.expected_profit == D("2.500")


def test_candidate_rejects_display_only_mispricing_without_executable_edge():
    rel=mutually_exclusive("r","A","B",evidence="rules")
    books={"A":book("A",no_asks=(("0.52","100"),)),"B":book("B",no_asks=(("0.50","100"),))}
    assert build_two_leg_candidate(rel,books,min_edge=D("0.001")) is None


def test_implication_candidate_uses_no_a_yes_b():
    rel=implication("r","A","B",evidence="rules")
    books={"A":book("A",no_asks=(("0.40","20"),)),"B":book("B",yes_asks=(("0.55","20"),))}
    c=build_two_leg_candidate(rel,books,min_edge=D("0.01"))
    assert c is not None and c.executable_edge_per_bundle == D("0.05")
    assert [leg.side for leg in c.legs] == [Side.NO,Side.YES]


def test_property_random_vwap_never_below_best_or_above_worst():
    rng=random.Random(7)
    for _ in range(500):
        prices=sorted({D(str(round(rng.uniform(.05,.95),2))) for _ in range(5)})
        levels=tuple(BookLevel(p,D(str(rng.randint(1,20)))) for p in prices)
        total=sum((x.size for x in levels),D("0"))
        q=D(str(rng.randint(1,int(total))))
        f=consume_asks(levels,q)
        assert f.complete
        assert f.average_price is not None
        assert f.worst_price is not None
        assert levels[0].price <= f.average_price <= f.worst_price <= levels[-1].price
