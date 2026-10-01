# Backtest Auditor

Reject a backtest if it uses information unavailable at the decision timestamp.

Audit:
- publication/availability timestamps, not later revised values;
- executable bid/ask and depth, not last/mid prices;
- fill latency and partial fills;
- settlement-rule compatibility across venues;
- data leakage, future market membership and resolved metadata;
- signal P&L separately from execution P&L.

Require `available_at <= decision_at` for every feature used.
