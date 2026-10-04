# Read-only production gate

This document describes **future production validation steps**. Passing unit tests or contract fixtures does not mean this gate has passed.

Do not enable live trading before the read-only and paper gates are completed.

## 1. Create a read-only API key

In Super Market Settings -> API Keys, create a key with the `read` scope only. Keep the key local; never commit or paste it into repository files.

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

## 2. Export the local environment

```bash
set -a
source .env
set +a
```

## 3. Run the zero-write smoke test

```bash
python scripts/susq_smoke.py --tournament-slug "$SUSQ_TOURNAMENT_SLUG"
```

Require explicit tournament context, successful read paths, and `WRITE REQUESTS 0`.

## 4. Collection path

Repeated sampling uses the tradable Exchange order book directly:

```text
GET /exchanges/{exchangeId}/orderbook?tournamentId=...&depth=...
```

The collector keeps request telemetry, uses an explicit request-start budget, honors `Retry-After` when available, and exposes an HTTP timeout. These are implementation properties; production latency/rate-limit behavior must still be measured from an authenticated account.

## 5. 100-snapshot characterization run

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

Do not proceed if there are unexplained schema failures or sequence regressions. Inspect transport failures, 429/503 responses, null-`asOf` frequency, spread/depth and latency tails.

## 6. 1,000-snapshot gate

Only after the 100-snapshot run is understood:

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

The SQLite database stores normalized snapshots plus:

- `collection_requests`: request latency/status/error telemetry;
- `collection_metrics`: sequence, spread/depth, displayed quantity and quote-lifetime telemetry.

The run must end with `WRITE REQUESTS 0`. Snapshot count alone is not sufficient: analyze failures, null `asOf`, sequence behavior, depth/spread, latency and quote lifetime before connecting paper execution.
