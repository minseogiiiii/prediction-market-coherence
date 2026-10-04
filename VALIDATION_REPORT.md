# Validation Report — V-Lab Audit Branch

Branch: `vlab-audit-prep`

This report records only results that were freshly reproduced during the current audit. Historical counts from earlier versions are not carried forward unless re-run.

## Freshly Reproduced Local Gate

Environment:

- macOS
- Python 3.14.5

Results:

- **94 tests collected**
- **94 passed**
- **0 failed**
- **84% total Python coverage**
- **2,022 statements / 333 missed**
- **5 canonical relationship truth tables verified**
- **10,000 randomized order-book invariant cases passed**
- `python -m compileall -q src`: passed
- `ruff check .`: passed
- `pyright`: 0 errors, 0 warnings, 0 informations

The repository CI configuration targets Python 3.11, but this report does not treat that configured target as a freshly reproduced result.

## Coverage Review

Selected critical modules:

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

The overall percentage is not used as a substitute for behavioral validation. The audit prioritizes relationship correctness, payoff invariants, order-book depth, timestamps, malformed external inputs, risk limits, and execution-state transitions.

`cli.py` is currently uncovered by the pytest suite. That is a documentation/demo entrypoint gap rather than evidence that the underlying detector/execution primitives are untested; the underlying detector and relationship modules are covered separately.

## Correctness Fix Added During Audit

The legacy threshold-family grouper previously grouped only by `event_ticker`, which could allow unrelated subjects inside the same event to be compared.

The audit changed the legacy grouping key to:

```text
event_ticker + normalized non-numeric proposition text
```

and added a regression test proving that two different player subjects inside the same event are not cross-compared.

This heuristic applies only to the legacy Kalshi research path. Super Market relationships use the venue's canonical relationship API as the authoritative source.

## Verified Capability Classes

### Unit / property tested

- relationship truth-table construction
- minimum-payoff analysis
- order-book level normalization
- visible-depth consumption
- VWAP / worst-price calculation
- executable candidate sizing
- cross-context rejection
- theoretical-only marking for unversioned official books
- cash/exposure/staleness risk limits
- paper broker all-legs precheck
- ledger settlement / reconciliation mismatch reporting
- no-lookahead timestamp guard
- Super Market auth/path/payload schema handling
- idempotency payload requirements
- partial/resting/unknown live execution states
- read-only collector telemetry logic
- health / kill-switch decisions

### Deterministic / fixture tested

- legacy threshold monotonicity example
- official exchange-book YES/NO normalization
- canonical simple relationship translation
- order payload and multi-leg payload construction
- malformed schema handling
- transient API behavior through mocked HTTP transports

### Paper tested

- atomic paper precheck and ledger mutation only after every leg has sufficient visible depth

### Contract tested

- Super Market API binding is coded against the extracted OpenAPI contract used by the repository's contract verifier.

### Not authenticated-live certified

The audit has **not** established authenticated production behavior for:

- API key scopes/account state
- real order submit/fill/cancel behavior
- real partial fills
- cancel races
- real-money/tournament reconciliation
- realtime/WebSocket recovery
- long-duration shadow operation

## No-Lookahead Status

Verified:

- explicit timezone-aware feature and decision timestamps;
- guard rejects features available after the decision;
- stale-book rejection exists;
- official book sequence/timestamps are preserved when supplied.

Not yet established:

- an end-to-end proof that every future historical evaluation path invokes these primitives correctly.

Therefore the resume should say **"implemented and tested no-lookahead/time-integrity guards"**, not **"proved the full backtest has no lookahead"** unless a specific end-to-end backtest is later audited.

## Executability Status

The repository distinguishes:

1. logical inconsistency;
2. ask/depth-based executable candidate;
3. paper execution;
4. live execution state-machine support;
5. authenticated production execution.

Important limitation: the structural candidate engine does not currently subtract a venue transaction-fee schedule as a first-class execution cost. It must not be described as demonstrated net arbitrage profit.

## Unsupported Resume Claims

Do not claim any of the following from the current evidence:

- profitable trading strategy;
- realized live arbitrage profit;
- authenticated live execution;
- net edge after all venue fees;
- production-certified trading bot;
- zero-lookahead guarantee for every possible historical workflow;
- real cancel-race or partial-fill validation;
- validated realtime/WebSocket recovery.

## Reproduction Commands

```bash
python -m pytest -q

python -m pytest   --cov=prediction_market_coherence   --cov-report=term-missing

python -m compileall -q src
ruff check .
pyright
python scripts/verify_invariants.py
```

Deterministic recruiter-facing demo:

```bash
python -m prediction_market_coherence.cli   kalshi-scan   --fixture tests/fixtures/markets.json
```

## Current Classification

**Research/paper-ready prototype with production-oriented controls; not production certified.**
