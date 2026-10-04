# Validation protocol

These are **promotion criteria**, not claims that every gate has already passed.

## Gate A — deterministic correctness

- All automated tests pass.
- Truth tables for every approved relationship are explicit and non-empty.
- Every structural bundle has a mechanically verified minimum payoff.
- Executable analysis uses asks and visible depth rather than midpoint alone.
- No-lookahead guards reject features published after the decision timestamp.

## Gate B — API contract / read-only integration

- Exact endpoint paths/auth are checked against the current official contract.
- Authenticated read-only market/order-book/position/balance calls are captured or characterized locally.
- Parsers are checked against current response shapes.
- Rate-limit and timestamp semantics are documented from evidence rather than assumed.

## Gate C — paper / shadow

- At least 1,000 order-book snapshots are characterized.
- No invalid relationship alerts remain unexplained.
- No structural trade has a negative mechanically verified minimum payout.
- Stale-book, insufficient-depth and partial/unknown-state handling are exercised.
- Shadow records include expected price, executable size, book age and post-signal movement.

## Gate D — limited live

- Explicit live environment gate is enabled only after prior gates.
- Size remains deliberately small.
- Every order receives an authoritative platform identifier/state.
- Unknown submission outcomes are reconciled rather than blindly retried.
- Position and balance reconciliation shows zero unexplained differences.
- Any reconciliation failure halts new orders.

## Gate E — strategy promotion

- Signal P&L and execution P&L are separated.
- Directional/fair-value models report calibration metrics where applicable.
- Market-making is promoted only after spread, fill, quote-lifetime, post-fill move and inventory-duration analysis.
- Tournament/leaderboard logic never overrides hard portfolio-risk limits.
