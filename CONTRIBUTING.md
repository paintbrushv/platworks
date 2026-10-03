# Contributing to platworks

## Ground rules

- **Strict TDD.** Every behavior lands as a failing test first (assertion-level
  RED where possible), then the smallest implementation that passes, then a full
  suite run. A green total without the new tests is not acceptance.
- **One source of truth.** The catalog (`src/platworks/catalog.py`) is the only
  place component facts live. Docs, the landing page, and MCP tools must derive
  from it — never restate catalog facts by hand; the drift-gate tests will fail.
- **No unverified claims.** Public repository URLs and descriptions must be
  verified against the GitHub API before entering the catalog. Private
  components carry no repo URL and no description — `null`, never a guess.
- **Synthetic data only.** No real deal, tenant, owner, or portfolio data in
  code, tests, docs, or fixtures. See [SECURITY.md](SECURITY.md).

## Workflow

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest -m "not slow"     # fast suite
pytest                    # full suite including stdio end-to-end tests
```

Style: ruff (`line-length = 100`, `target-version = py311`); imports sorted.

## Adding a component to the catalog

1. Verify the repository is public and fetch its exact GitHub description and license
   (`https://api.github.com/repos/paintbrushv/<name>`).
2. Add the entry to `_REGISTRY` in `catalog.py` — public entries get the
   verified URL, license, and verbatim description; private entries get `repo: None`
   and `description: None`.
3. Record the verified public metadata in `docs/catalog-evidence.json`. When
   refreshing the snapshot, recheck all public entries and update both its
   `verified_on` date and `catalog.VERIFIED_ON`.
4. Extend `tests/test_catalog.py` with the new component's expectations, then
   regenerate the committed page with `platworks landing docs/index.html --force`.
5. Run `python scripts/verify_catalog.py` and the full test suite: catalog,
   CLI, landing, demo, and docs drift gates must stay green. Run
   `python scripts/verify_catalog.py --live` before release to detect changes
   since the recorded snapshot.
