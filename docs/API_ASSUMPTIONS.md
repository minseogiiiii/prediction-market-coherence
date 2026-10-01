# Predictions Cup API integration assumptions

## Facts verified from official public material

- Participants may use the API for market data, order submission/cancellation, positions, and automated strategies.
- Participant keys may trade but cannot use restricted administrator endpoints.
- A trade counts only after explicit platform confirmation.
- Market and limit orders exist; unmatched limit quantity may rest in the peer-to-peer order book.
- YES and NO are complements at settlement; selling YES at p is economically equivalent to buying NO at 1-p.
- Cancellation may return HTTP 503 when the trading engine is temporarily overloaded; the official changelog says retrying cancellation is safe.

Sources checked 2026-10-01:
- https://predictionscup.com/rules/
- https://sig.thesuper.market/docs/markets-and-trading
- https://sig.thesuper.market/docs/changelog
- https://sig.thesuper.market/api/v1/docs

## Deliberately *not* guessed

The dynamic Scalar API reference could be opened but its endpoint table/schema was not retrievable in the build environment. Therefore this repository does not invent endpoint paths, auth header names, order JSON fields, IOC/FOK support, rate-limit numbers, or response schemas.

`EndpointMap.from_env()` requires exact documented paths. `AuthConfig.from_env()` requires the documented auth header. The live order adapter remains gated until these are copied from the official API reference and verified with read-only requests.

This is a correctness decision: an incomplete integration is safer than a plausible but fabricated live API schema.
