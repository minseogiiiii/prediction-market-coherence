# Prediction Market Coherence — Predictions Cup System

Execution-aware research/trading framework evolved from the original Kalshi threshold-coherence MVP. The project now separates **logical validity**, **executable liquidity**, **risk**, and **order execution** instead of treating a displayed probability mismatch as a trade.

## Core design

```text
market/rule data -> approved relationship graph -> truth-table payoff verifier
order books       -> depth/VWAP engine        -> executable candidate
candidate         -> risk manager             -> paper/live state machine
external signals  -> fair-value research      -> calibrated directional feature
```

Live trading is **fail-closed**. The code does not guess Predictions Cup API paths or auth details. Copy the exact values from the official Scalar API reference into `.env`/your environment, validate read-only fixtures, and pass the gates in `docs/VALIDATION.md` before enabling live orders.

## What is reused

The original Kalshi public client, threshold normalizer/grouping, monotonicity detector, fixture and CLI behavior are preserved. New modules add Predictions Cup-specific execution research without discarding that work.

## Quick validation

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
pytest -q
python -m compileall -q src tests
python -m prediction_market_coherence.cli --fixture tests/fixtures/markets.json
```

## Important modules

```text
client.py        Kalshi research client
susq_client.py   fail-closed configurable Predictions Cup HTTP client
models.py        binary markets, order books, relationships, portfolios
payoff.py        truth-table payoff verification
execution.py     depth, VWAP, max profitable size
risk.py          edge, freshness, cash/exposure gates
ledger.py        local position/cash accounting + reconciliation
paper.py         atomic-precheck paper executor
live.py          gated live order state machine
storage.py       durable SQLite research log
collector.py     concurrent collection + adaptive cadence
signals.py       weighted fair value, shrinkage, Kelly, calibration
backtest.py      timestamp/no-lookahead guards
external.py      settlement-compatible cross-venue signals
news.py          news/entity mapping only (never direct orders)
maker.py         inventory-aware maker quote core
tournament.py    bounded score/time risk adjustment
```

See `docs/API_ASSUMPTIONS.md`, `docs/VALIDATION.md`, and `docs/ROADMAP.md`.
