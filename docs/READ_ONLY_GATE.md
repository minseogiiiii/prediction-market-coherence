# Read-only production gate

Do not enable live trading before this gate passes.

## 1. Create a read-only API key

In Super Market Settings -> API Keys, create a key with the `read` scope only. Keep the key local; never commit or paste it into chat.

```bash
cp .env.example .env
chmod 600 .env
```

Set only:

```text
SUSQ_API_KEY=...
SUSQ_TOURNAMENT_SLUG=...
PMC_ALLOW_LIVE_TRADING=0
```

## 2. Export local environment

```bash
set -a
source .env
set +a
```

## 3. Run the no-write smoke test

```bash
python scripts/susq_smoke.py --tournament-slug "$SUSQ_TOURNAMENT_SLUG"
```

The explicit tournament context, exchange orderbook, portfolio read, and `WRITE REQUESTS 0` must pass.

## 4. Production collection design

Latency probing on the production API showed that direct exchange books are materially more stable than combined market books. The collector therefore uses:

```text
GET /exchanges/{exchangeId}/orderbook?tournamentId=...&depth=...
```

instead of the combined market orderbook endpoint for repeated sampling.

The client-side request-start budget is capped, hidden GET retries are disabled, every wire attempt is recorded, `Retry-After` is honored when present, and the HTTP timeout is configurable. A default depth of 200 is retained because the observed direct-exchange latency difference between depth 50 and 200 was small relative to network/server variance.

## 5. 100-snapshot validation run

Run a medium validation before the 1,000-snapshot gate:

```bash
rm -f data/susq_readonly_100.sqlite3 \
      data/susq_readonly_100.sqlite3-wal \
      data/susq_readonly_100.sqlite3-shm

python scripts/susq_collect.py \
  --tournament-slug "$SUSQ_TOURNAMENT_SLUG" \
  --target-snapshots 100 \
  --markets 10 \
  --depth 200 \
  --reads-per-minute 80 \
  --timeout-seconds 15 \
  --progress-every 25 \
  --db data/susq_readonly_100.sqlite3

python scripts/susq_analyze_collection.py data/susq_readonly_100.sqlite3
```

Do not proceed if there are schema failures or sequence regressions. Investigate recurring transport failures, 429/503 responses, or a high null-`asOf` rate.

## 6. 1,000-snapshot gate

After the 100-snapshot run is clean enough to characterize the production path:

```bash
rm -f data/susq_readonly.sqlite3 \
      data/susq_readonly.sqlite3-wal \
      data/susq_readonly.sqlite3-shm

python scripts/susq_collect.py \
  --tournament-slug "$SUSQ_TOURNAMENT_SLUG" \
  --target-snapshots 1000 \
  --markets 10 \
  --depth 200 \
  --reads-per-minute 80 \
  --timeout-seconds 15 \
  --progress-every 50 \
  --db data/susq_readonly.sqlite3

python scripts/susq_analyze_collection.py data/susq_readonly.sqlite3
```

The SQLite database contains normalized snapshots plus two telemetry tables:

- `collection_requests`: one row per direct exchange-book HTTP attempt with market/exchange IDs, latency, HTTP status, and error code/text.
- `collection_metrics`: one row per normalized exchange book, linked to its request and carrying sequence, spread/depth, displayed quantity, and quote-lifetime telemetry.

The run must end with `WRITE REQUESTS 0`. Snapshot count alone is not a sufficient gate: inspect latency tails, failures, null `asOf`, sequence regressions, depth/spread, and quote lifetime before connecting paper execution.
