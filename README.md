# Prediction Market Coherence

Research MVP for detecting logical pricing inconsistencies in threshold prediction markets, starting with Kalshi greater-than contracts.

## Research question

For the same event, greater-than contracts must obey monotonicity. If `K1 < K2`, then:

```text
P(X > K1) >= P(X > K2)
```

The detector flags timestamps where two-sided YES midpoints violate that relationship. It separately computes a **gross executable nested edge** using asks:

```text
buy YES(lower strike) + buy NO(higher strike)
gross_edge = 1 - yes_ask(lower) - no_ask(higher)
```

Fees, slippage, fill risk, and settlement-rule equivalence are deliberately not treated as solved in this MVP.

## Why this implementation is conservative

- Only `strike_type="greater"` markets with `floor_strike` are included.
- Markets are matched inside the same `event_ticker`.
- Midpoint tests require a valid two-sided YES book.
- Executable edge uses asks, not midpoint prices.
- Non-threshold contracts are ignored rather than inferred from titles.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Run against the included deterministic fixture

```bash
python -m prediction_market_coherence.cli --fixture tests/fixtures/markets.json
```

Expected key result:

```text
TESTBTC: K=110000 ... -> K=120000 ... | gap=4.00¢ | gross executable edge=2.00¢
```

## Run against live Kalshi public market data

```bash
python -m prediction_market_coherence.cli --live
```

Or restrict the scan to one event:

```bash
python -m prediction_market_coherence.cli --live --event <EVENT_TICKER>
```

Kalshi public market endpoint used by the client:

```text
GET https://external-api.kalshi.com/trade-api/v2/markets
```

## Tests

```bash
pytest -q
```

## Current scope

MVP 1 focuses only on static monotonicity detection. Planned research extensions:

1. Historical 1-minute violation frequency/magnitude/duration.
2. Quote-executable vs fee-adjusted arbitrage.
3. Liquidity and lead-lag price discovery.
4. Live WebSocket L2 book reconstruction and order-flow features.
5. Execution-aware backtesting and robustness checks.

## Project structure

```text
src/prediction_market_coherence/
  client.py          # public Kalshi REST client
  models.py          # normalized threshold market
  relationships.py   # grouping and strike ordering
  detector.py        # monotonicity + gross executable edge
  cli.py             # command-line scanner

tests/
  fixtures/
  test_models.py
  test_detector.py
```
