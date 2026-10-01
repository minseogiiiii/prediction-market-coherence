# Validation protocol

A strategy is not considered live-ready because unit tests pass. Promotion gates are:

## Gate A — deterministic correctness

- All unit tests pass.
- Truth tables for every approved relationship are explicit and non-empty.
- Every proposed structural bundle has a mechanically verified minimum payoff.
- Executable edge uses order-book asks and visible depth, never midpoint alone.
- No-lookahead checks reject features published after the decision timestamp.

## Gate B — API contract

- Exact endpoint paths/auth copied from the official API reference.
- Read-only market, order-book, position, order, and balance calls captured as fixtures.
- Parser tests use those real fixtures.
- Rate-limit and timestamp semantics documented.

## Gate C — paper/shadow

- At least 1,000 order-book snapshots.
- No invalid relationship alerts.
- No negative guaranteed-payoff structural trade.
- Partial-fill, stale-book, insufficient-depth, and cancel-race tests pass.
- Shadow orders record expected price, executable size, book age, and post-signal price movement.

## Gate D — limited live

- Explicit live environment gate enabled only after B/C.
- Small size limits.
- Every order gets an explicit platform order id/confirmation.
- Unknown submission outcomes are reconciled; they are never blind-retried.
- Position and balance reconciliation shows zero unexplained differences.
- Any reconciliation failure halts new orders.

## Gate E — strategy promotion

- Expected P&L is separated into signal P&L and execution P&L.
- Directional/fair-value models report Brier score/log loss and calibration.
- Market-making is promoted only after measuring spread, fill probability, quote lifetime, post-fill move, and inventory duration.
- Leaderboard-aware sizing remains bounded by ordinary portfolio risk limits.
