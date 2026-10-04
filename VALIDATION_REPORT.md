# Validation Report — Current `main`

**Validation date:** 2026-10-04  
**Branch:** `main`

This report records only claims supported by the current repository and reproduced validation runs. Historical resume numbers are not carried forward unless they match the current suite.

## Fresh validation snapshot

Current reproduced metrics:

- **94 tests collected**
- **94 passed**
- **0 failed**
- **84% Python test coverage**
- **2,022 statements / 333 missed**
- **5 canonical relationship truth tables verified**
- **10,000 randomized order-book invariant cases passed**
- `ruff check .`: passed
- `pyright`: 0 errors, 0 warnings
- `python -m compileall -q src`: passed
- deterministic fixture demo: 5 greater-than markets, 2 families, 4 pairs, 1 expected violation
- local reproduction: macOS / Python 3.14.5
- clean CI reproduction: Ubuntu / Python 3.11 — **94/94 tests passed**, **84% coverage**, Ruff passed, Pyright reported 0 errors / 0 warnings, invariants passed, compilation passed, and the deterministic demo passed

The CI workflow installs the package from the repository from scratch and runs linting, type checking, pytest+coverage, invariant stress validation, source compilation, and the deterministic fixture demo.

## Coverage snapshot

Selected modules from the reproduced pytest coverage run:

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

Overall coverage is evidence of exercised code, not proof of financial correctness. The audit places more weight on explicit mathematical invariants, failure cases, timestamp discipline, depth/VWAP logic and state transitions.

The CLI itself is not materially covered by pytest; it is instead run as a deterministic release-gate demo. The underlying detector and relationship logic are separately tested.

## Mathematical correctness audit

### Supported binary relationships

The truth-state definitions and canonical hedge directions are internally consistent:

- **Implication** `A -> B`: allowed states `00, 01, 11`; hedge `NO(A) + YES(B)`.
- **Mutual exclusion**: `00, 01, 10`; hedge `NO(A) + NO(B)`.
- **Exhaustive**: `01, 10, 11`; hedge `YES(A) + YES(B)`.
- **Complement**: `01, 10`; `YES(A) + YES(B)` pays exactly one unit.
- **Equivalent**: `00, 11`; `NO(A) + YES(B)` pays exactly one unit.

The payoff engine enumerates every allowed relationship state and computes minimum/maximum payout mechanically.

### Threshold ordering

For lower strike `K1 < K2`:

```text
{X > K2} subset {X > K1}
P(X > K2) <= P(X > K1)
```

The legacy detector sorts thresholds by strike and flags `higher_mid - lower_mid > 0`, which is the correct monotonicity direction.

Its gross nested structural hedge uses:

```text
YES(lower) + NO(higher)
gross edge = 1 - ask(YES lower) - ask(NO higher)
```

### Cross-subject contamination

The prior event-only grouping bug remains fixed. A regression test verifies that named subjects such as Dak Prescott and Derrick Henry inside the same event are not cross-compared.

The legacy family grouper is still title-derived and therefore intentionally treated as a heuristic. Canonical Super Market relationships do not rely on that heuristic.

### YES/NO normalization

For a YES-normalized binary order book:

```text
NO ask = 1 - YES bid
NO bid = 1 - YES ask
```

Tests verify both the complemented prices and preserved quantities.

## Executability boundary audit

The repository now documents six distinct evidence layers:

1. **Logical inconsistency**
2. **Quoted-price structural edge**
3. **Visible-depth / VWAP execution candidate**
4. **Paper execution**
5. **Mocked live state-machine behavior**
6. **Authenticated production behavior**

Current evidence reaches Layer 5 only in mocked/state-machine form. It does **not** certify Layer 6.

The structural candidate engine consumes asks through visible depth and computes VWAP/worst price. It does **not** currently subtract a venue fee schedule as a first-class cost term. Therefore a positive candidate is a **pre-fee structural edge**, not demonstrated net arbitrage profit.

## No-lookahead / time-integrity audit

Verified primitives:

- timezone-aware decision and feature timestamps;
- rejection when `available_at > decision_at`;
- venue receive/source timestamps;
- `asOf.sequence` preservation when present;
- stale-book rejection;
- theoretical-only marking when authoritative version/context metadata is missing.

Safe wording is:

> **implemented and tested no-lookahead/time-integrity guards**

Unsafe wording is:

> **proved the entire system has no lookahead bias**

because no single end-to-end historical strategy pipeline is proven to invoke every guard correctly under every data transformation.

## Failure-boundary audit

Tested or explicitly handled examples include:

- malformed schema fields;
- naive timestamps;
- invalid tick sizes and quantities;
- missing books;
- insufficient depth;
- stale data;
- cross-context books;
- unversioned official books;
- partial/resting atomic outcomes;
- unknown/failed submissions;
- duplicate exchange IDs in multi-leg payloads;
- retryable read failures;
- local/remote position mismatches;
- API-error/stale/open-order health gates.

## Public-repository hygiene

The recruiter-facing root was cleaned so that the first impression is the research system rather than the development tooling.

Removed from the public project surface:

- obsolete `PUSH_INSTRUCTIONS.md`;
- project-specific `.claude/skills` development scaffolding.

Kept intentionally:

- `.env.example` with empty placeholders;
- API binding/gate documentation;
- deterministic fixtures and tests;
- `VALIDATION_REPORT.md`.

The current `main` tree contains no committed real API key or `.env` file. The earlier reachable `main` MVP tree likewise contained no credential file. This repository-level inspection is not a substitute for provider-side secret scanning, but no credential artifact was found in the reviewed public tree/history.

## API contract evidence

The Super Market adapter was developed against an extracted 2026-10-01 OpenAPI contract. The raw local extraction is intentionally not committed. `scripts/verify_api_contract.py` can regression-check a refreshed local extract.

That is **contract validation**, not authenticated production validation.

## What is verified

- relationship truth-table construction;
- state-payoff analysis;
- threshold monotonicity example;
- cross-subject regression protection;
- order-book normalization;
- visible-depth / VWAP calculation;
- executable-size search;
- context and version-data guards;
- cash/exposure/staleness risk limits;
- paper execution precheck;
- ledger settlement/reconciliation diagnostics;
- no-lookahead/time-integrity primitives;
- order payload/tick/idempotency rules;
- mocked partial/resting/error execution states;
- read-only collector/storage logic;
- operational health gates.

## What remains unvalidated

- profitability;
- venue-fee-adjusted net arbitrage;
- authenticated live execution;
- real partial fills/cancel races;
- production account reconciliation;
- long-running shadow reliability;
- production realtime/WebSocket recovery;
- end-to-end no-lookahead proof for every historical experiment.

## Reproduction

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

## Portfolio classification

**READY as a quantitative-market research / validation portfolio project.**

It is not represented as a profitable strategy or production-certified trading system.
