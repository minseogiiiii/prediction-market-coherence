# Prediction Market Coherence — Predictions Cup System

Execution-aware prediction-market research system derived from the original Kalshi threshold-coherence MVP and now bound to the official Super Market `/api/v1` contract.

## Current status

Version `0.3.0` has two layers:

1. **Venue-independent research core** — logical relationship truth tables, executable depth/VWAP, payoff verification, paper execution, risk limits, backtest guards, storage and monitoring.
2. **Super Market binding** — official bearer auth, concrete endpoints, exchange-orderbook normalization, idempotent order payloads, atomic multi-leg admission, tournament context, canonical ALL relationships and a read-only production smoke test.

Live trading remains fail-closed by default.

## Critical model distinction

Super Market uses:

```text
Market   = container
Exchange = tradable contract
```

Orders and order books use `exchangeId`. The original generic model retains the legacy `market_id` field name for replay compatibility; the Super Market adapter stores the `exchangeId` there and exposes an `exchange_id` alias.

## Install

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev,research]'
```

## Release gate

```bash
pytest -q
python scripts/verify_invariants.py
python -m compileall -q src
ruff check .
pyright
```

If you have a fresh extracted API audit:

```bash
PYTHONPATH=src python scripts/verify_api_contract.py tmp/api-discovery/core-api-audit.json
```

## Read-only Super Market gate

Keep `PMC_ALLOW_LIVE_TRADING=0`, create a **read-scope** API key, set `SUSQ_TOURNAMENT_SLUG`, then:

```bash
set -a
source .env
set +a
python scripts/susq_smoke.py --tournament-slug "$SUSQ_TOURNAMENT_SLUG"
```

The smoke test sends **zero write requests**. See `docs/READ_ONLY_GATE.md`.

## Atomic execution

The official API exposes `POST /orders/multi-leg`, which atomically admits 1–10 legs. The `AtomicLiveExecutor` uses that route for multi-leg candidates. Atomic admission does not imply complete fills; any resting/partial leg remains a reconciliation/cancel problem and is not marked reconciled automatically.

## Main modules

```text
client.py                 legacy Kalshi public data client
models.py                 normalized books/contracts/candidates
relationships.py          local proved truth-table relationships
payoff.py                 exhaustive state payoff analysis
execution.py              depth/VWAP executable sizing
risk.py                   exposure/cash/staleness limits
paper.py                  atomic paper broker
live.py                   sequential + atomic fail-closed live state machines
susq_client.py            official Super Market /api/v1 client
susq_schema.py            official book/order schema adapters
susq_relationships.py     canonical ALL relationship/constraint parsers
collector.py              concurrent data collection
storage.py                SQLite research journal
signals.py                fair-value/calibration primitives
backtest.py               look-ahead and execution-edge guards
maker.py                  market-making primitives
health.py                 kill-switch evaluation
```

## Next gate

Do not move directly from unit tests to autonomous live orders. The next sequence is:

```text
read-only authenticated smoke test
→ explicit tournament-context verification
→ 1,000+ live order-book snapshots
→ paper/replay validation
→ controlled order plumbing
→ limited live execution
```
