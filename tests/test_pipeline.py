from datetime import UTC, datetime
from decimal import Decimal

from prediction_market_coherence.config import RuntimeConfig
from prediction_market_coherence.models import BookLevel, OrderBook, PortfolioSnapshot
from prediction_market_coherence.pipeline import scan_relationships
from prediction_market_coherence.relationships import mutually_exclusive

D=Decimal; NOW=datetime.now(UTC)


def test_end_to_end_structural_pipeline():
    rel=mutually_exclusive('r','A','B',evidence='audited rules')
    books={
      'A':OrderBook('A',NOW,no_asks=(BookLevel(D('.45'),D('100')),)),
      'B':OrderBook('B',NOW,no_asks=(BookLevel(D('.50'),D('100')),)),
    }
    cfg=RuntimeConfig(min_edge=D('.01'),max_order_size=D('25'),max_market_exposure=D('1000'),max_total_exposure=D('5000'),min_cash_buffer=D('100'))
    out=scan_relationships([rel],books,PortfolioSnapshot(D('10000'),{}),cfg)
    assert len(out)==1
    assert out[0].candidate.max_profitable_quantity==D('25')
    assert out[0].candidate.expected_profit==D('1.25')
    assert out[0].risk.approved
