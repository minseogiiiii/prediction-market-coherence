# Super Market API binding (OpenAPI 1.0.0)

Validated against the 2026-10-01 extracted `Super Market API` OpenAPI 3.1.0 contract.

## Production and authentication

- Production base: `https://www.thesuper.market/api/v1`
- Preferred auth: `Authorization: Bearer <key>`
- Alternate auth: `X-API-Key: <key>`
- Standard key budget documented by the API: 100 reads/minute, 30 writes/minute.
- Realtime messages do not count against REST request budgets.

The client defaults to the production base and bearer authentication. No endpoint-path environment variables are needed in v0.3.

## Correct data model

A `Market` is a container. An `Exchange` is the tradable contract. Orders, positions, books and trades reference `exchangeId`.

The original research code retained the generic field name `market_id` inside `OrderBook` and `TradeLeg`. Under the Super Market adapter that field **must contain the exchange ID**, never the market container ID. The models expose `exchange_id` aliases to make that explicit while retaining replay compatibility.

## Order books

`GET /exchanges/{id}/orderbook` returns one YES-normalized book with `bids`, `asks`, and `asOf`.

The adapter derives the side-relative NO book exactly:

```text
NO ask = 1 - YES bid
NO bid = 1 - YES ask
```

Quantities are preserved at the corresponding price rung. `asOf.sequence` and `asOf.at` are stored on the normalized book. If `asOf` is null, the local receive time is used and `source_sequence` stays null.

## Orders

Single order body:

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

Fresh limit orders must use integer quantity and a `0.005` price tick within `0.005..0.995`.

`POST /orders/multi-leg` admits 1-10 legs atomically: all legs are persisted or none are. This removes sequential placement risk but **does not guarantee complete fills**. A successful request can still leave one or more legs resting. Live code therefore reports `PARTIAL` until all legs are filled and authoritative REST reconciliation is complete.

When an official ALL relationship is used, pass its UUID as `relationshipConstraint`. The engine validates the relationship immediately before dispatch, but the OpenAPI reference explicitly says that concurrent fills/graph changes can create a later violation, so relationship preflight is not treated as a risk-free execution guarantee.

## Idempotency and retries

Every placement carries a client-supplied `idempotencyKey` in the JSON body.

The client classifies these as retryable with the same logical payload/key:

- `429 RATE_LIMITED`
- `409 REQUEST_IN_FLIGHT`
- `502 ORDER_STATUS_UNKNOWN`
- `503 TX_CONFLICT`
- `503 SERVICE_UNAVAILABLE`

It does not automatically invent a new key or blindly repeat a write after a transport failure. A transport failure is marked outcome-unknown and must be reconciled or retried with the identical idempotency key.

## Tournament context

Use `GET /tournaments/{slug}` to resolve the tournament UUID. Then carry that UUID as `tournamentId` through market discovery, exchange price/book reads, relationship evaluation and order placement.

This avoids accidental dependence on the organization's mutable default tournament.

## Relationships

Canonical ALL relationships are authoritative through:

- `GET /relationships`
- `GET /relationships/graph`
- `GET /relationships/constraints`

The local truth-table translator intentionally supports only simple relationships it can prove without interpretation: implication/monotonic, complementary, and two-member mutually-exclusive. Complex boolean expressions remain authoritative-only until a dedicated AST verifier is implemented.

## Realtime

`POST /realtime/token` returns a short-lived token, `supabaseUrl`, `anonKey` and a user channel. Realtime is best-effort and is **not** the authoritative state source. Initial state, reconnects, token refreshes, revision gaps and `resyncRequired` must trigger REST resynchronization.

The first integration gate deliberately stays REST read-only. Realtime is the next optimization after schema and tournament-context validation.

## Contract regression

Run the extracted-contract verifier whenever the OpenAPI reference is refreshed:

```bash
PYTHONPATH=src python scripts/verify_api_contract.py tmp/api-discovery/core-api-audit.json
```

It fails closed if machine-critical endpoint/auth/orderbook/order assumptions drift.
