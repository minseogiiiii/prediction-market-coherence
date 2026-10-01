import asyncio
from datetime import UTC
from decimal import Decimal

import pytest

from prediction_market_coherence.live import OrderRequest
from prediction_market_coherence.susq_schema import (
    OrderBookSchema,
    OrderPayloadSchema,
    SusqVenueAdapter,
    get_path,
    parse_timestamp,
)

D=Decimal


def test_get_path_and_missing():
    assert get_path({'a':{'b':3}},'a.b')==3
    with pytest.raises(KeyError): get_path({'a':{}},'a.b')


def test_configurable_book_schema_parses_and_sorts():
    payload={'data':{'id':'m','ts':'2026-10-01T16:00:00Z','yb':[[.4,2],[.5,3]],'ya':[[.6,2],[.55,1]],'nb':[[.3,1]],'na':[[.46,5]]}}
    s=OrderBookSchema('data.id','data.ts','data.yb','data.ya','data.nb','data.na')
    b=s.parse(payload)
    assert b.market_id=='m'
    assert [x.price for x in b.yes_bids]==[D('.5'),D('.4')]
    assert [x.price for x in b.yes_asks]==[D('.55'),D('.6')]
    assert b.observed_at.tzinfo == UTC


def test_timestamp_rejects_naive():
    with pytest.raises(ValueError): parse_timestamp('2026-10-01T12:00:00')


def test_order_payload_schema_uses_configured_field_names():
    s=OrderPayloadSchema('market','outcome','qty','limit','type','limit','client_id')
    p=s.build(OrderRequest('M','YES',D('10'),D('.42'),'abc'))
    assert p=={'market':'M','outcome':'YES','qty':10,'limit':.42,'type':'limit','client_id':'abc'}


def test_venue_adapter_bridges_without_hidden_retry():
    class Client:
        async def submit_order(self,payload,idempotency_key=None): return {'order_id':'1','status':'FILLED','payload':payload,'key':idempotency_key}
        async def get_order(self,oid): return {'order_id':oid}
        async def cancel_order(self,oid): return {'order_id':oid,'status':'CANCELLED'}
    async def run():
        a=SusqVenueAdapter(Client(),OrderPayloadSchema('market','side','qty','price'))
        r=await a.place_order(OrderRequest('M','YES',D('2'),D('.4'),'c1'))
        assert r['key']=='c1' and r['payload']['qty']==2
        assert (await a.get_order('1'))['order_id']=='1'
        assert (await a.cancel_order('1'))['status']=='CANCELLED'
    asyncio.run(run())
