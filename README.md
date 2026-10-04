# Prediction Market Coherence and Execution Research

[![CI](https://github.com/minseogiiiii/prediction-market-coherence/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/minseogiiiii/prediction-market-coherence/actions/workflows/ci.yml)

A quantitative-market research system for testing whether logically related prediction contracts are priced coherently, then separating a **mathematical inconsistency** from a **quoted opportunity**, a **depth/VWAP-supported execution candidate**, and an **actually validated trade outcome**.

> **Core principle:** detecting a quantitative signal is only the beginning. It must survive logical, market-data, execution, risk, and systems validation.

**Current status:** tested research/paper-execution prototype with production-oriented controls. **Not production certified. No profitability claim.**

## Verified evidence

Validation snapshot: **2026-10-04, `main`**.

- **94/94 automated tests passed**
- **84% Python test coverage** — 2,022 statements / 333 missed
- **5 canonical relationship truth tables** verified
- **10,000 randomized order-book invariant cases** passed
- **Ruff passed**
- **Pyright: 0 errors / 0 warnings**
- Python source compilation passed
- deterministic fixture demo reproduced the expected single threshold violation
- GitHub Actions runs the release gate on **Python 3.11**
- the same test/coverage suite was also reproduced locally on **Python 3.14.5**

See [VALIDATION_REPORT.md](VALIDATION_REPORT.md) for the exact claim boundaries and detailed audit notes.

## The quantitative idea

For nested events, logical implication imposes a probability ordering. If

```text
X > 120  implies  X > 110
```

then coherence requires

```text
P(X > 120) <= P(X > 110)
```

A violation of that inequality is a **logical pricing inconsistency**. It is not automatically an arbitrage that can be filled.

For a nested threshold pair, the structural hedge is:

```text
buy YES(lower threshold) + buy NO(higher threshold)
```

The code then asks progressively harder questions: are there executable asks, is enough visible depth available, what is the VWAP, is the book fresh, do risk limits pass, and what execution state is actually known?

## Validation ladder

| Layer | Meaning | Current evidence |
| --- | --- | --- |
| **1. Logical** | Relationship/probability constraint is violated | Truth-table and deterministic tests |
| **2. Quoted** | Current top-of-book quotes imply a positive structural edge | Fixture/unit tested |
| **3. Depth/VWAP executable candidate** | Visible depth supports a quantity at positive **pre-fee** structural edge | Unit/property tested |
| **4. Paper execution** | All legs pass a preflight and the local ledger is updated atomically | Tested |
| **5. Mocked live state machine** | Partial/resting/unknown states and live gates behave correctly against mocked venue responses | Tested |
| **6. Authenticated production behavior** | Real venue authentication, fills, cancels, races, reconciliation, realized P&L | **Not certified** |

**Transaction-fee boundary:** venue transaction fees are not a first-class term in the structural candidate calculation. A positive candidate edge must therefore **not** be described as net arbitrage profit.

## System architecture

```mermaid
flowchart LR
    A[Related contracts] --> B[Relationship / truth table]
    B --> C[Coherence check]
    C --> D[Order-book normalization]
    D --> E[Depth + VWAP sizing]
    E --> F[Risk / freshness gates]
    F --> G[Paper execution]
    G --> H[Mocked live-state logic]
```

The central research path is **logical relationships → execution-aware evaluation → risk/failure boundaries**. Production-oriented API and telemetry modules are secondary infrastructure rather than evidence of live profitability.

## Deterministic recruiter demo

No credentials or network access are required:

```bash
python -m prediction_market_coherence.cli \
  kalshi-scan \
  --fixture tests/fixtures/markets.json
```

Expected output:

```text
Greater-than markets: 5
Threshold families:   2
Pairs scanned:        4
Violations:           1
TESTBTC: K=110000 mid=51.00¢ -> K=120000 mid=55.00¢ | gap=4.00¢ | gross executable edge=2.00¢
```

The final 2.00¢ figure is a **fixture-based gross pre-fee structural edge**, not realized profit.

## Mathematical correctness

The venue-independent relationship layer supports explicit truth-state definitions for:

- implication;
- mutually exclusive outcomes;
- exhaustive outcomes;
- complements;
- equivalent outcomes.

Payoffs are mechanically evaluated across every allowed truth state. The legacy threshold scanner sorts strikes in the correct subset direction and includes a regression test preventing different named subjects inside the same event from being cross-compared. That legacy title-based family grouping remains a heuristic; the Super Market path instead treats venue-provided canonical relationships as authoritative.

The Super Market order-book adapter also normalizes binary YES/NO sides mechanically:

```text
NO ask = 1 - YES bid
NO bid = 1 - YES ask
```

with quantity preserved at the corresponding price level.

## No-lookahead / time integrity

The repository implements and tests **no-lookahead/time-integrity guards**:

- `TimedFeature.available_at` and `TimedDecision.decision_at`;
- rejection of features unavailable at decision time;
- timezone-aware timestamp requirements;
- venue `asOf.sequence` / `asOf.at` preservation when supplied;
- stale-book rejection;
- theoretical-only marking for official books that lack authoritative sequence/context metadata.

This is **not** a claim that every possible historical workflow has been proven free of look-ahead bias end to end.

## Execution and risk boundaries

The execution/risk path:

- consumes visible asks rather than midpoint prices;
- computes notional, VWAP and worst fill price;
- searches visible depth breakpoints;
- verifies the minimum payout from the relationship truth table;
- rejects missing or insufficient depth;
- rejects mixed tournament contexts;
- rejects or marks unsafe unversioned/stale data;
- enforces cash, per-market and total-exposure limits;
- paper-executes only after every leg passes the depth precheck;
- keeps live trading disabled unless an explicit runtime acknowledgement is supplied.

Mocked live tests cover state classification such as full fill, partial/resting residuals and known request failures. They do **not** constitute authenticated live trading evidence.

## Failure modes made explicit

The code or tests handle/reject examples including:

- malformed or missing API fields;
- naive timestamps;
- invalid order quantities or price ticks;
- one-sided/missing liquidity;
- insufficient visible depth;
- stale books;
- mixed market contexts;
- unversioned official books;
- partial/resting multi-leg outcomes;
- unknown order-submission outcomes;
- duplicate exchanges in an atomic bundle;
- retryable read failures;
- reconciliation mismatches;
- excessive API-error/stale-book/open-order conditions.

## Super Market integration

Lower-level infrastructure includes:

- schema-validated REST client/adapters;
- exchange-level order books;
- explicit tournament context;
- idempotent single- and multi-leg order payloads;
- canonical relationship/constraint parsing;
- read-only collection telemetry;
- fail-closed write/error state handling;
- SQLite research storage.

The API binding was built against an extracted Super Market OpenAPI contract. The raw local audit artifact is not committed to this public repository; [docs/API_BINDING.md](docs/API_BINDING.md) records the machine-critical assumptions and the contract verifier can be rerun against a refreshed local extract.

## What this project does **not** claim

- profitable strategy performance;
- net profitability after real venue fees;
- authenticated live order submission/fill/cancel validation;
- real partial-fill or cancel-race validation;
- production reconciliation under real orders;
- long-duration shadow-trading reliability;
- production WebSocket gap recovery;
- complete end-to-end no-lookahead proof for every future backtest.

These are promotion gates, not implied capabilities.

## Reproduce the release gate

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev,research]'

ruff check .
pyright
python -m pytest -q \
  --cov=prediction_market_coherence \
  --cov-report=term-missing
python scripts/verify_invariants.py
python -m compileall -q src
python -m prediction_market_coherence.cli \
  kalshi-scan \
  --fixture tests/fixtures/markets.json
```

## Repository map

```text
src/prediction_market_coherence/
  relationships.py        truth-table relationships + legacy threshold grouping
  payoff.py               exhaustive state-payoff verification
  detector.py             threshold coherence detector
  execution.py            visible-depth / VWAP candidate construction
  risk.py                 cash, exposure and staleness gates
  paper.py                all-legs paper precheck/execution
  backtest.py             time-integrity and execution-edge primitives
  live.py                 fail-closed execution state machines
  susq_schema.py          market/order schema normalization
  susq_client.py          REST client and retry/error semantics
  susq_collection.py      read-only collection telemetry
  storage.py              SQLite research journal

tests/                    deterministic, regression and property tests
scripts/                  validation, smoke-test and collection utilities
docs/                     API and promotion-gate documentation
```

## Bottom line

This repository is best described as a **validated quantitative-market research and paper-execution prototype**. Its strongest result is not a profitability number; it is the explicit separation between a quantitative idea, an execution-aware candidate, a tested implementation, and behavior that still requires production evidence.
