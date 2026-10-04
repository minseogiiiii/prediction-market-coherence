# Validation roadmap

The central project is the research path:

```text
logical relationship
→ coherence test
→ quoted/depth-aware executability
→ risk gates
→ paper execution
→ production evidence only after explicit gates
```

## Verified in the current repository

- [x] Legacy threshold-coherence detector with cross-subject regression protection.
- [x] Explicit binary relationship truth tables.
- [x] Exhaustive state-payoff verification.
- [x] Visible-depth / VWAP candidate sizing.
- [x] Context, timestamp and stale-book guards.
- [x] Cash, per-market and total-exposure limits.
- [x] Paper execution with all-legs precheck.
- [x] Ledger/reconciliation diagnostics.
- [x] Fail-closed live execution state machines tested with mocked responses.
- [x] Super Market schema/order payload adapters.
- [x] Durable SQLite research/collection telemetry.
- [x] Automated tests, coverage, invariant stress validation and CI.

## Required before any production claim

- [ ] Authenticate a read-only production account and capture current schema examples.
- [ ] Complete and analyze the documented 100- then 1,000-snapshot read-only gates.
- [ ] Validate real partial-fill/cancel/reconciliation behavior.
- [ ] Add an explicit venue-fee model before claiming net executable profit.
- [ ] Validate realtime recovery if realtime data becomes part of an execution path.
- [ ] Run limited live execution only after the prior gates and explicit local enablement.

None of the unchecked items is implied by a green unit-test suite.
