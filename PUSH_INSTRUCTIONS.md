# GitHub handoff

The connected GitHub integration could read `minseogiiiii/prediction-market-coherence` but returned HTTP 403 when asked to create a branch, so this build was not pushed automatically.

From the directory containing this repository:

```bash
git checkout -b predictions-cup-system
git add .
git commit -m "Build execution-aware Predictions Cup trading system"
git push -u origin predictions-cup-system
```

Then open a pull request into `main` and let `.github/workflows/ci.yml` run.
