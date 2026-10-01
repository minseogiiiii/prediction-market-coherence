import asyncio

import httpx
import pytest

from prediction_market_coherence.susq_client import (
    AuthConfig,
    EndpointMap,
    SusqApiError,
    SusqClient,
)

EP=EndpointMap(markets='/markets',market='/markets/{market_id}',orderbook='/markets/{market_id}/book',positions='/positions',orders='/orders',order='/orders/{order_id}',cancel_order='/orders/{order_id}')
AUTH=AuthConfig('X-API-Key','secret')


def run(coro): return asyncio.run(coro)


def test_read_auth_and_path():
    seen={}
    async def handler(req):
        seen['path']=req.url.path; seen['auth']=req.headers.get('X-API-Key')
        return httpx.Response(200,json={'ok':True})
    async def scenario():
        async with SusqClient(endpoints=EP,auth=AUTH,base_url='https://example.test',transport=httpx.MockTransport(handler)) as c:
            assert await c.get_orderbook('abc') == {'ok':True}
    run(scenario())
    assert seen=={'path':'/markets/abc/book','auth':'secret'}


def test_read_retries_503_then_succeeds():
    calls=0
    async def handler(req):
        nonlocal calls; calls+=1
        return httpx.Response(503,json={'retry':True}) if calls<3 else httpx.Response(200,json={'ok':True})
    async def scenario():
        async with SusqClient(endpoints=EP,auth=AUTH,base_url='https://x',transport=httpx.MockTransport(handler),max_read_retries=3) as c:
            return await c.list_markets()
    assert run(scenario())=={'ok':True} and calls==3


def test_order_submission_is_not_blind_retried_after_timeout():
    calls=0
    async def handler(req):
        nonlocal calls; calls+=1
        raise httpx.ReadTimeout('timeout')
    async def scenario():
        async with SusqClient(endpoints=EP,auth=AUTH,base_url='https://x',transport=httpx.MockTransport(handler)) as c:
            with pytest.raises(SusqApiError,match='UNKNOWN'):
                await c.submit_order({'x':1})
    run(scenario()); assert calls==1


def test_cancel_retries_503():
    calls=0
    async def handler(req):
        nonlocal calls; calls+=1
        return httpx.Response(503,json={'retry':True}) if calls==1 else httpx.Response(200,json={'status':'cancelled'})
    async def scenario():
        async with SusqClient(endpoints=EP,auth=AUTH,base_url='https://x',transport=httpx.MockTransport(handler)) as c:
            return await c.cancel_order('o1')
    assert run(scenario())=={'status':'cancelled'} and calls==2
