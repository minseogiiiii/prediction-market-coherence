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

Target:

```text
ACCOUNT            PASS
TOURNAMENTS        PASS
TOURNAMENT         PASS
MARKETS            PASS
EXCHANGE_BOOK      PASS
RELATIONSHIPS      PASS
CONSTRAINTS        PASS
POSITIONS          PASS or SKIP before enrolment
WRITE REQUESTS      0
```

A FAIL must be investigated before continuing. Do not switch to a trade-scoped key to work around a read failure.

## 4. Data-collection gate

After the smoke test passes, collect at least 1,000 versioned order-book snapshots in the explicit tournament context. Required metrics:

- REST latency
- 429/5xx rate
- `asOf.sequence` monotonicity
- null-`asOf` rate
- spread/depth distribution
- quote lifetime
- schema failures

Only then connect the paper execution/scanner to the live books.
