# Predictions Cup API integration status

This document supersedes the earlier placeholder-assumptions note. The official Super Market OpenAPI 3.1.0 contract was extracted and audited on 2026-10-01. The implementation is now bound to documented production paths, authentication, order payloads, idempotency semantics, exchange order books, tournament context, relationships, and realtime-token behavior.

See `API_BINDING.md` for the exact machine-critical contract and `READ_ONLY_GATE.md` for the production validation sequence.

## Still deliberately unclaimed

Offline contract validation does **not** prove the user's production account state or live venue behavior. These remain gated on authenticated read-only validation:

- API-key validity and scopes
- exact Predictions Cup tournament slug/UUID for the account
- live market/exchange payload samples
- tournament membership/enrolment state
- observed latency, rate-limit, and 5xx behavior
- realtime delivery/recovery behavior
- real order submit/fill/cancel/reconciliation
- strategy profitability

Live trading remains fail-closed by default.
