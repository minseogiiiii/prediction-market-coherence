# Trading Chaos Tester

Before live promotion, inject:
- HTTP 429, 500, 502, 503, 504;
- timeout before and after server acceptance;
- connection reset;
- malformed JSON;
- empty/one-sided/stale books;
- partial fill;
- fill during cancel;
- duplicate confirmation;
- position/balance mismatch.

The invariant is not "the request returned"; it is "economic state is known and reconciled". Any unknown state halts new orders until reconciled.
