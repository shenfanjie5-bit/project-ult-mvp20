# project-ult-mvp20

Public orchestration shell for the Project ULT 20-stock MVP.

This repository owns the MVP manifest, module lock, runbooks, fixture evidence,
and CI checks. It does not copy module implementation code and does not replace
the existing `project-ult-*` repositories.

## MVP Boundary

- Exactly 20 decision target stocks, supplied by `config/mvp20.universe.yaml`.
- `history_window_months=120`.
- `graph_depth=2`.
- Associated listed companies are graph and risk-summary context only.
- Buy/sell/recommendation decisions are emitted only for the 20 decision
  targets.
- Provider gaps are recorded explicitly; missing data is not fabricated.

## Not Claimed

- Default/full propagation enabled.
- Broad production rollout complete.
- M4.7/financial-doc complete.
- Contracts subtype changes.
- New relation types.

## Local Checks

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e ".[dev]"
.venv/bin/mvp20 validate-manifest --manifest config/mvp20.universe.yaml
.venv/bin/mvp20 verify-lock --lock locks/modules.lock.yaml
.venv/bin/mvp20 plan-backfill --manifest config/mvp20.universe.yaml
.venv/bin/mvp20 run-fixture-e2e
.venv/bin/python -m pytest
git diff --check
```

The checked-in manifest is a slot manifest. It intentionally blocks live MVP
evidence until the real 20 `ts_code` values are filled.
