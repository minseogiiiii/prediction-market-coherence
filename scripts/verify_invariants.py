from __future__ import annotations

import random
from datetime import UTC, datetime
from decimal import Decimal

from prediction_market_coherence.execution import build_two_leg_candidate, consume_asks
from prediction_market_coherence.models import BookLevel, OrderBook, TradeLeg
from prediction_market_coherence.payoff import analyze_payoff, canonical_hedge_sides
from prediction_market_coherence.relationships import (
    complement,
    equivalent,
    exhaustive,
    implication,
    mutually_exclusive,
)

D=Decimal
NOW=datetime.now(UTC)


def check_truth_tables() -> int:
    rels=[
        implication('i','A','B',evidence='test'),
        mutually_exclusive('m','A','B',evidence='test'),
        exhaustive('x','A','B',evidence='test'),
        complement('c','A','B',evidence='test'),
        equivalent('e','A','B',evidence='test'),
    ]
    for rel in rels:
        sides=canonical_hedge_sides(rel)
        legs=tuple(TradeLeg(mid,side,D('1'),D('.5')) for mid,side in zip(rel.market_ids,sides))
        analysis=analyze_payoff(rel,legs)
        assert analysis.minimum_payout >= D('1')
    return len(rels)


def check_random_books(iterations: int=10000) -> int:
    rng=random.Random(20261001)
    rel=mutually_exclusive('mx','A','B',evidence='test')
    checked=0
    for _ in range(iterations):
        def levels():
            prices=sorted({D(str(round(rng.uniform(.05,.95),2))) for _ in range(rng.randint(1,5))})
            return tuple(BookLevel(p,D(str(rng.randint(1,100)))) for p in prices)
        la,lb=levels(),levels()
        ba=OrderBook('A',NOW,no_asks=la)
        bb=OrderBook('B',NOW,no_asks=lb)
        c=build_two_leg_candidate(rel,{'A':ba,'B':bb},min_edge=D('0'))
        if c is not None:
            assert c.expected_profit >= 0
            assert c.executable_edge_per_bundle >= 0
            assert c.guaranteed_payout_per_bundle >= c.cost_per_bundle
            for leg in c.legs:
                book=ba if leg.market_id=='A' else bb
                fill=consume_asks(book.no_asks,c.max_profitable_quantity)
                assert fill.complete
                assert fill.worst_price is not None and fill.worst_price <= leg.max_price
        checked+=1
    return checked


if __name__=='__main__':
    n_rel=check_truth_tables()
    n_books=check_random_books()
    print(f'truth_tables={n_rel} random_books={n_books} status=OK')
