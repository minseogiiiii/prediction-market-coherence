import asyncio
from decimal import Decimal
from typing import Any, cast

import httpx
import pytest

from prediction_market_coherence.client import KalshiClient
from prediction_market_coherence.config import RuntimeConfig
from prediction_market_coherence.susq_client import (
    AuthConfig,
    EndpointMap,
    SusqApiError,
    SusqClient,
)


class FakeResponse:
    def __init__(self,payload): self.payload=payload
    def raise_for_status(self): pass
    def json(self): return self.payload


class FakeSession:
    def __init__(self):
        self.headers={}; self.calls=[]
        self.responses=[FakeResponse({'markets':[{'ticker':'A'}],'cursor':'n'}),FakeResponse({'markets':[{'ticker':'B'}],'cursor':''})]
    def get(self,url,params,timeout):
        self.calls.append((url,dict(params),timeout)); return self.responses.pop(0)


def test_kalshi_client_pagination_and_event_filter():
    c=KalshiClient(); f=FakeSession(); c.session=cast(Any, f)
    out=list(c.iter_markets(event_ticker='E'))
    assert [x['ticker'] for x in out]==['A','B']
    assert f.calls[0][1]['event_ticker']=='E' and f.calls[1][1]['cursor']=='n'


def test_kalshi_max_pages_stops():
    c=KalshiClient(); f=FakeSession(); c.session=cast(Any, f)
    out=list(c.iter_markets(max_pages=1))
    assert [x['ticker'] for x in out]==['A']


def test_runtime_config_env(monkeypatch):
    monkeypatch.setenv('PMC_ALLOW_LIVE_TRADING','1')
    monkeypatch.setenv('PMC_LIVE_ACK','ok')
    monkeypatch.setenv('PMC_MIN_EDGE','0.03')
    c=RuntimeConfig.from_env()
    assert c.allow_live_trading and c.acknowledgement=='ok' and c.min_edge==Decimal('0.03')
    assert c.live_enabled('ok') and not c.live_enabled('bad')


def test_endpoint_map_requires_all_env(monkeypatch):
    for name in ['SUSQ_PATH_MARKETS','SUSQ_PATH_MARKET','SUSQ_PATH_ORDERBOOK','SUSQ_PATH_POSITIONS','SUSQ_PATH_ORDERS','SUSQ_PATH_ORDER','SUSQ_PATH_CANCEL_ORDER']:
        monkeypatch.delenv(name,raising=False)
    with pytest.raises(ValueError,match='Missing official'):
        EndpointMap.from_env()


def test_endpoint_map_and_auth_from_env(monkeypatch):
    values={
      'SUSQ_PATH_MARKETS':'/m','SUSQ_PATH_MARKET':'/m/{market_id}','SUSQ_PATH_ORDERBOOK':'/m/{market_id}/b',
      'SUSQ_PATH_POSITIONS':'/p','SUSQ_PATH_ORDERS':'/o','SUSQ_PATH_ORDER':'/o/{order_id}','SUSQ_PATH_CANCEL_ORDER':'/o/{order_id}',
    }
    for k,v in values.items(): monkeypatch.setenv(k,v)
    monkeypatch.setenv('SUSQ_API_KEY','k'); monkeypatch.setenv('SUSQ_AUTH_HEADER','Authorization'); monkeypatch.setenv('SUSQ_AUTH_PREFIX','Bearer ')
    assert EndpointMap.from_env().markets=='/m'
    assert AuthConfig.from_env().header_value=='Bearer k'


def test_auth_requires_key(monkeypatch):
    monkeypatch.delenv('SUSQ_API_KEY',raising=False); monkeypatch.delenv('SUSQ_AUTH_HEADER',raising=False)
    with pytest.raises(ValueError): AuthConfig.from_env()


def test_susq_format_missing_placeholder():
    with pytest.raises(ValueError): SusqClient._format('/x/{missing}',market_id='m')


def test_susq_http_error_has_payload():
    ep=EndpointMap('/m','/m/{market_id}','/b/{market_id}','/p','/o','/o/{order_id}','/o/{order_id}')
    async def h(req): return httpx.Response(401,json={'code':'NO'})
    async def scenario():
        async with SusqClient(endpoints=ep,auth=AuthConfig('X','k'),base_url='https://x',transport=httpx.MockTransport(h),max_read_retries=0) as c:
            with pytest.raises(SusqApiError) as e: await c.list_markets()
            assert e.value.status_code==401 and e.value.payload=={'code':'NO'}
    asyncio.run(scenario())


def test_balance_requires_endpoint():
    ep=EndpointMap('/m','/m/{market_id}','/b/{market_id}','/p','/o','/o/{order_id}','/o/{order_id}')
    async def h(req): return httpx.Response(200,json={})
    async def scenario():
        async with SusqClient(endpoints=ep,auth=AuthConfig('X','k'),base_url='https://x',transport=httpx.MockTransport(h)) as c:
            with pytest.raises(ValueError): await c.get_balance()
    asyncio.run(scenario())
