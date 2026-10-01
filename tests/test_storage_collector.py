import asyncio
import sqlite3
from datetime import UTC, datetime
from decimal import Decimal

from prediction_market_coherence.collector import AdaptiveCadence, collect_orderbooks_once
from prediction_market_coherence.models import BookLevel, OrderBook
from prediction_market_coherence.storage import ResearchStore

NOW=datetime.now(UTC)
D=Decimal


def sample(mid):
    return OrderBook(mid,NOW,yes_asks=(BookLevel(D('.5'),D('10')),))


def test_research_store_roundtrip(tmp_path):
    path=tmp_path/'r.db'
    with ResearchStore(path) as s: s.record_orderbook(sample('M'))
    conn=sqlite3.connect(path)
    row=conn.execute('select market_id, payload_json from orderbook_snapshots').fetchone()
    assert row[0]=='M' and 'yes_asks' in row[1]
    conn.close()


def test_collector_isolates_one_market_failure(tmp_path):
    async def fetch(mid):
        if mid=='bad': raise RuntimeError('boom')
        return sample(mid)
    with ResearchStore(tmp_path/'c.db') as s:
        r=asyncio.run(collect_orderbooks_once(['a','bad','b'],fetch,s,concurrency=2))
    assert r.requested==3 and r.succeeded==2 and r.failed==1


def test_adaptive_cadence_prioritizes_active_and_near_edge():
    c=AdaptiveCadence(cold_seconds=10,warm_seconds=2,hot_seconds=.5)
    assert c.interval(active_order=True,edge_distance=None)==.5
    assert c.interval(active_order=False,edge_distance=.004)==.5
    assert c.interval(active_order=False,edge_distance=.01)==2
    assert c.interval(active_order=False,edge_distance=.2)==10
