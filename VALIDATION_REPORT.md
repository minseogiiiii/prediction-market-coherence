# Validation Report — 2026-10-01

## Automated results

- Unit/integration tests: **75 passed**.
- Invariant stress test: **5 relationship truth tables + 10,000 randomized order books: OK**.
- Python bytecode compilation: **PASS** for `src`, `tests`, and `scripts`.
- Editable package install using the local build environment: **PASS**.
- Credential scan for committed `SUSQ_API_KEY=...`: **PASS**.
- Deterministic legacy fixture smoke test: **PASS**.

## Deterministic fixture smoke test

```text
Greater-than markets: 5
Threshold families:   2
Pairs scanned:        4
Violations:           1
TESTBTC: K=110000 mid=51.00¢ -> K=120000 mid=55.00¢ | gap=4.00¢ | gross executable edge=2.00¢
```

## Coverage

Overall measured Python coverage: **86%** across 1,290 statements. Critical execution/risk modules are higher: execution 92%, risk 95%, live state machine 91%, ledger 93%, paper broker 91%, health/kill switch 100%, configurable schema adapter 93%.

## What this validates

The suite covers the original Kalshi detector; logical truth tables; depth/VWAP; max-profitable-size selection; paper execution; ledger pairing and settlement; stale-book/cash/exposure gates; unknown-order handling; cancellation retry behavior; fail-closed API configuration; timestamp/no-lookahead checks; fair-value weighting, shrinkage, Kelly and calibration math; market-maker inventory skew; bounded tournament sizing; durable storage; adaptive collection; schema adapters; and kill-switch conditions.

## What is not yet truthfully validated

1. The exact Predictions Cup endpoint paths, auth header, order payload and order-book JSON schema. The official Scalar API reference is dynamic and its endpoint table was not retrievable from this build environment, so the code intentionally requires those values instead of guessing them.
2. Authenticated live API calls using the user's account/API key.
3. 1,000+ live order-book snapshots and multi-hour shadow execution.
4. Real partial fills, cancel races and position/balance reconciliation on the platform.
5. Live market-making performance and directional-model calibration, which require elapsed market data.

The repository is therefore **paper/research ready, not certified live-ready** until Gates B–D in `docs/VALIDATION.md` are completed.
