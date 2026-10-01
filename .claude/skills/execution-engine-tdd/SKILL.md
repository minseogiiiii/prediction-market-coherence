# Execution Engine TDD

For order, cancel, fill, ledger, reconciliation or risk code:

1. Write a failing regression test first.
2. Cover normal fill, partial fill, timeout, malformed response, 429/503, cancel race and unknown submit outcome.
3. Never blindly retry an order submission after a timeout unless the official API guarantees idempotency for that exact request.
4. Require explicit platform confirmation/order id before treating an order as accepted.
5. Reconcile positions after uncertain outcomes.
6. Keep live trading fail-closed by default.
7. Run the full suite before claiming completion.
