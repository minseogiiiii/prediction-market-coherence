# Validation report — v0.3.0

## Completed in build environment

- `90` pytest tests passed.
- `5` canonical relationship truth tables verified.
- `10,000` randomized order-book invariants verified.
- Python source compilation passed.
- Extracted OpenAPI contract regression passed against `core-api-audit.json`:
  - OpenAPI `3.1.0`
  - production base `https://www.thesuper.market/api/v1`
  - bearer authentication
  - 27 audited core operations
  - official order/idempotency fields
  - official exchange orderbook `price`/`quantity` fields
  - documented multi-leg atomicity guarantee present

## New contract-bound tests

The v0.3 suite validates:

- official bearer auth defaults
- official endpoint paths and tournament query context
- read retry behavior for transient 503s
- no blind retry of ambiguous write transport failures
- `ORDER_STATUS_UNKNOWN` classification
- cancellation retry behavior
- YES-normalized exchange-book parsing
- mathematically exact NO-side complement reconstruction
- `asOf.sequence` and timestamp handling
- exact 0.005 order-price tick enforcement
- integer quantity enforcement
- single-order idempotency payloads
- multi-leg shared idempotency + duplicate-exchange rejection
- single and multi-leg response normalization
- atomic executor partial/resting detection
- official simple ALL relationship translation
- official constraint parsing

## Not yet claimed as validated

The following require the user's authenticated account and live venue data and therefore cannot be certified offline:

- API-key authentication against production
- exact Predictions Cup tournament slug/UUID
- live market/exchange response samples
- account/tournament membership state
- REST latency and observed rate-limit behavior
- realtime WebSocket delivery and revision-gap recovery
- actual submit/fill/cancel/reconciliation behavior
- strategy profitability

Live trading remains disabled by default until those gates are completed.

## Local release gate still required after sync

Run on the user's Mac after applying v0.3:

```bash
pytest -q
python scripts/verify_invariants.py
python -m compileall -q src
ruff check .
pyright
```

The build environment had no network access to install Ruff/Pyright, so those two static checks must be re-run locally before the v0.3 commit is pushed.
