# Release Gate

No live release unless:
- unit/property/state-machine tests pass;
- exact official API paths/schema have been captured as fixtures;
- read-only integration works;
- at least 1,000 live book snapshots have been collected;
- paper/shadow execution shows no ledger mismatch;
- unknown order/cancel outcomes reconcile correctly;
- live gate remains off until the user explicitly enables it locally.

A green test suite is necessary but not sufficient for live readiness.
