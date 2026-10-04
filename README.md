# Prediction Market Coherence and Execution Research

A quantitative-market research system for detecting logical inconsistencies in prediction markets, translating them into executable order-book candidates, and validating the difference between a mathematical opportunity and a production-ready trade.

The project began as a threshold-coherence detector and now includes relationship truth tables, payoff verification, depth/VWAP execution analysis, risk controls, paper execution, fail-closed live adapters, Super Market API bindings, and read-only collection/telemetry tooling.

**Current status:** research/paper-ready prototype. **Not production certified. No profitability claim.**

## Key Verified Results

Freshly reproduced on the `vlab-audit-prep` branch:

- **94/94 automated tests passed**
- **84% total Python coverage**: 2,022 statements, 333 missed
- **5 canonical relationship truth tables** verified
- **10,000 randomized order-book invariant cases** passed
- `ruff check .`: passed
- `pyright`: 0 errors, 0 warnings
- source compilation: passed
- local validation environment: macOS, Python 3.14.5
- CI is configured to target Python 3.11, but this audit does not treat that CI target as a reproduced result

Selected coverage on critical modules:

| Module | Coverage |
| --- | ---: |
| `relationships.py` | 91% |
| `detector.py` | 87% |
| `execution.py` | 93% |
| `risk.py` | 95% |
| `paper.py` | 91% |
| `backtest.py` | 93% |
| `live.py` | 84% |
| `susq_schema.py` | 84% |
| `susq_collection.py` | 82% |
| `susq_client.py` | 71% |

Coverage is not treated as proof by itself. The validation emphasis is on relationship correctness, payoff invariants, executable depth, timestamps, fail-closed execution behavior, and malformed/partial external responses.

## Why Coherence Matters

For nested outcomes, probability ordering must respect logical implication.

For example, if

```text
X > 120  implies  X > 110
```

then

```text
P(X > 110) >= P(X > 120)
```

A midpoint violation is only a **logical pricing inconsistency**. It is not automatically a trade.

The system separates four increasingly demanding layers:

1. **Logical inconsistency** — probabilities violate a proved relationship.
2. **Quoted/executable inconsistency** — available asks imply a positive structural edge.
3. **Depth-aware candidate** — visible order-book depth and VWAP support a size.
4. **Paper/live execution state** — execution machinery determines whether the opportunity can actually be acted on.

Authenticated live fills and realized profitability remain outside the validated claims.

## System Architecture

```text
market / relationship metadata
        ↓
normalization + relationship construction
        ↓
truth-table / payoff verification
        ↓
order-book normalization
        ↓
depth + VWAP executable sizing
        ↓
risk gates
        ↓
paper execution
        ↓
fail-closed live execution adapters
        ↓
read-only telemetry / reconciliation infrastructure
```

Two relationship paths exist:

- **Legacy Kalshi threshold research**: conservative threshold-family grouping plus monotonicity checks.
- **Super Market path**: canonical venue-provided relationships are authoritative; only simple relationship types are translated locally when their truth semantics can be proved without interpretation.

The legacy threshold grouper explicitly separates different semantic subjects inside the same event to avoid cross-player/event-family contamination.

## Validation Layers

| Capability | Unit / Property Tested | Deterministic Fixture | Paper Tested | Authenticated Live Tested |
| --- | :---: | :---: | :---: | :---: |
| Relationship truth tables | Yes | Yes | n/a | No |
| Legacy threshold monotonicity | Yes | Yes | n/a | No |
| Event-family contamination regression | Yes | Yes | n/a | No |
| Payoff minimum / hedge correctness | Yes | Yes | n/a | No |
| Depth / VWAP sizing | Yes | Yes | n/a | No |
| Risk limits / stale-book rejection | Yes | Yes | n/a | No |
| Paper broker atomic precheck | Yes | Yes | Yes | No |
| No-lookahead primitive | Yes | Yes | n/a | No |
| Super Market order-book schema | Yes | Yes | n/a | No |
| Super Market order payload / idempotency schema | Yes | Yes | n/a | No |
| Live execution state machine | Yes | Yes | n/a | No |
| Read-only production collector | Yes | Yes | n/a | **Not yet certified against an authenticated production account** |

"Live execution state machine tested" means mocked/fixture behavior is tested. It does **not** mean real-money or tournament orders were submitted.

## Deterministic Demo

Run the original threshold research idea without credentials:

```bash
python -m prediction_market_coherence.cli   kalshi-scan   --fixture tests/fixtures/markets.json
```

The fixture includes a deliberate BTC threshold inconsistency. The scanner should report one monotonicity violation between the 110k and 120k thresholds, including midpoint gap and gross ask-based nested edge.

This demo is deterministic and does not require network access.

## No-Lookahead and Time Integrity

The repository includes explicit time-integrity primitives:

- every `TimedFeature` has an `available_at` timestamp;
- every `TimedDecision` has a `decision_at` timestamp;
- `assert_no_lookahead` rejects any feature available after the decision;
- timestamps must be timezone-aware;
- official order books preserve venue `asOf.sequence` / `asOf.at` when available;
- books lacking authoritative version metadata are marked theoretical-only before structural execution can pass the risk layer;
- stale books are rejected by the risk manager.

These guards are validated as primitives. The repository does **not** claim that every possible historical-data workflow has been audited end-to-end.

## Executability and Risk Controls

The structural execution engine:

- consumes visible asks;
- computes fill quantity, notional, VWAP and worst price;
- searches visible depth breakpoints;
- verifies minimum payout from the underlying relationship truth table;
- rejects missing/insufficient depth;
- rejects cross-tournament-context book combinations;
- marks unversioned official books theoretical-only;
- applies cash, market-exposure, total-exposure, stale-book and minimum-edge gates;
- paper-executes only after all legs pass a preflight depth check;
- keeps live trading disabled unless an explicit runtime gate and acknowledgement are both present.

Important limitation: the structural candidate calculation does **not** currently model a venue transaction-fee schedule as a first-class cost term. Therefore "positive executable edge" in this repository must not be described as net profit after fees.

## Super Market Integration

The Super Market adapter is bound to the documented `/api/v1` contract and includes:

- bearer authentication configuration;
- exchange-level order books;
- tournament context;
- order and multi-leg payload schemas;
- idempotency keys;
- response normalization;
- relationship/constraint parsing;
- read-only collection telemetry;
- retry handling for documented transient read failures;
- fail-closed handling for ambiguous write outcomes.

The code deliberately distinguishes **contract/fixture validation** from **authenticated production validation**.

## Failure Modes Explicitly Handled

Examples include:

- malformed or missing API fields;
- invalid/tick-misaligned prices;
- invalid order quantities;
- stale books;
- insufficient visible depth;
- mismatched tournament context;
- unversioned official books;
- partial/resting multi-leg outcomes;
- unknown order submission outcomes;
- duplicate exchanges inside one atomic bundle;
- API retryable read failures;
- reconciliation mismatches;
- excessive API-error/stale-book/open-order conditions through health gates.

Unexpected software defects are not silently reclassified as market-data failures in the production collector path; known API and schema failures are handled separately.

## What Is NOT Yet Validated

The repository does **not** currently claim:

- profitable strategy performance;
- net profitability after real venue fees;
- authenticated live order submission/fill/cancel behavior;
- real partial-fill and cancel-race behavior;
- end-to-end production reconciliation under real orders;
- long-duration shadow-trading reliability;
- realtime/WebSocket gap recovery in production;
- complete end-to-end no-lookahead proof for every future historical pipeline.

These are explicit promotion gates, not implied capabilities.

## Testing and Reproduction

Install:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev,research]'
```

Run the current local audit gate:

```bash
python -m pytest -q

python -m pytest   --cov=prediction_market_coherence   --cov-report=term-missing

python -m compileall -q src
ruff check .
pyright
python scripts/verify_invariants.py
```

The invariant script currently verifies 5 canonical relationship truth tables and 10,000 randomized order-book cases.

If an extracted API audit artifact is available locally:

```bash
PYTHONPATH=src python scripts/verify_api_contract.py tmp/api-discovery/core-api-audit.json
```

## Repository Structure

```text
src/prediction_market_coherence/
  relationships.py        local proved relationship constructors + legacy threshold grouping
  detector.py             legacy monotonicity detector
  payoff.py               exhaustive state-payoff verification
  execution.py            depth/VWAP executable candidate construction
  risk.py                 cash/exposure/staleness gates
  paper.py                atomic paper precheck/execution
  live.py                 fail-closed sequential + atomic execution state machines
  backtest.py             no-lookahead and execution-adjusted-edge primitives
  health.py               operational kill-switch evaluation
  storage.py              SQLite research journal / collection telemetry
  susq_client.py          Super Market API client
  susq_schema.py          order-book and order schema adapters
  susq_relationships.py   canonical relationship/constraint parsers
  susq_collection.py      rate-budgeted read-only production collector

tests/
  deterministic, regression, integration-style and property tests

scripts/
  verify_invariants.py
  verify_api_contract.py
  susq_smoke.py
  susq_collect.py
  susq_analyze_collection.py
```

## Current Research Position

The repository is best described as a **tested quantitative-market research and paper-execution prototype with production-oriented controls**.

It is intentionally not described as a profitable trading bot or production-certified live trading system.
