# Super Market API binding

The implementation was developed against a **2026-10-01 extracted Super Market OpenAPI 3.1.0 contract**. The raw local extraction is intentionally not committed to this public repository; `scripts/verify_api_contract.py` can check a refreshed local extract for machine-critical drift.

Contract validation is not authenticated production validation.

## Production and authentication

- Production base: `https://www.thesuper.market/api/v1`
- Preferred auth: `Authorization: Bearer <key>`
- Alternate auth: `X-API-Key: <key>`
- The extracted contract documented standard request budgets for reads/writes.
- Realtime behavior is documented separately from authoritative REST state.

The client defaults to the production base and bearer authentication.

## Correct data model

A `Market` is a container. An `Exchange` is the tradable contract. Orders, positions, books and trades reference `exchangeId`.

The venue-independent model retains the legacy field name `market_id` in `OrderBook` and `TradeLeg`. Under the Super Market adapter that field contains the **exchange ID** and exposes an `exchange_id` alias.

## Order books

`GET /exchanges/{id}/orderbook` is parsed as a YES-normalized book.

The adapter derives the side-relative NO book mechanically:

```text
NO ask = 1 - YES bid
NO bid = 1 - YES ask
```

Quantities are preserved at the corresponding rung. `asOf.sequence` and `asOf.at` are stored when supplied. If `asOf` is null, local receive time is retained and `source_sequence` remains null; such missing authoritative version metadata is treated conservatively downstream.

## Orders

A single-order payload has the contract shape:

```json
{
  "idempotencyKey": "...",
  "exchangeId": "36",
  "side": "yes",
  "action": "buy",
  "quantity": 100,
  "price": 0.42,
  "tournamentId": "..."
}
```

Local validation enforces integer quantity and the documented `0.005` price tick within `0.005..0.995`.

The extracted contract describes `POST /orders/multi-leg` as atomic admission of 1–10 legs: all legs are persisted or none are. **Atomic admission is not a fill guarantee.** The state machine therefore treats resting/partial legs as unresolved execution state requiring reconciliation/cancel handling.

When a canonical relationship UUID is available, it can be passed as `relationshipConstraint`. Relationship validation is not treated as a guarantee against later concurrent state changes.

## Idempotency and retries

Every placement carries a client-supplied idempotency key.

The client distinguishes documented transient/retryable states from ambiguous write transport failures. It does not invent a fresh logical order after an uncertain write outcome. Unknown economic state must be reconciled.

## Tournament context

The adapter resolves explicit tournament context and carries the tournament ID through discovery, book reads, relationship evaluation and order payloads rather than relying on an implicit mutable default.

## Relationships

Canonical relationships are treated as authoritative. The local translator intentionally supports only simple relationship forms it can prove without interpretation: implication/monotonic, complementary, and two-member mutually-exclusive relationships. Complex boolean expressions remain authoritative-only.

## Realtime boundary

Realtime is not treated as the authoritative state source in the current validated path. Reconnect/token/revision-gap behavior would require dedicated production validation before promotion.

## Contract regression

With a refreshed local audit artifact:

```bash
PYTHONPATH=src python scripts/verify_api_contract.py tmp/api-discovery/core-api-audit.json
```

The verifier fails closed when machine-critical endpoint/auth/orderbook/order assumptions drift.
