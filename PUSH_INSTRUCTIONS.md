# Sync v0.3 onto the existing `predictions-cup-system` branch

From the cloned repository on the Mac, copy the v0.3 files into the repo, then run the release gate before committing.

```bash
source .venv/bin/activate
pip install -e '.[dev,research]'
pytest -q
python scripts/verify_invariants.py
python -m compileall -q src
ruff check .
pyright
```

Expected functional checks in this build: `90 passed` and `truth_tables=5 random_books=10000 status=OK`.

Then:

```bash
git add .
git status
git commit -m "Bind Predictions Cup system to official Super Market API"
git push
```

Do not commit `.env` or any API key. Do not enable `PMC_ALLOW_LIVE_TRADING` yet.
