# Runbook: External smoke — Tushare corpus

This is the **external smoke lane** for the local Tushare corpus
mounted at `<external-corpus-root>`. It's Phase C of
`TUSHARE_TEST_FIXTURE_PLAN.md`.

Unlike the git-tracked fixture lanes (audit-eval shared cases +
data-platform local raw fixtures under `tests/dbt/fixtures/raw/tushare/`),
this smoke verifies the **upstream corpus itself** and the
**fixture-to-corpus traceability** chain. It is deliberately NOT a
pytest test — the corpus lives outside git on a mounted volume, so
running this under CI produces false failures.

## When to run

1. **Scheduled sanity** (recommended cron / launchd cadence: daily or
   weekly on the developer machine that has the drive mounted). A
   green run means "the corpus snapshot the Phase B fixtures were cut
   from still looks like it did on 2026-04-20".
2. **Right before cutting a new fixture** — proves the dataset paths
   you're about to rely on are still in `未见明显遗漏` territory per
   the audit CSV.
3. **Regression investigation** — when a shared case suddenly fails
   on a consumer, the first question to answer is "did the upstream
   corpus shape change?" This script answers that in ~10 seconds.

## How to run

```bash
cd <workspace>/data-platform
./scripts/external_smoke_tushare_corpus.sh
```

Or bypass the shell wrapper and invoke Python directly:

```bash
PYTHONPATH=src .venv/bin/python scripts/external_smoke_tushare_corpus.py
```

## Environment variables

| Name | Default | Effect |
|---|---|---|
| `DP_EXTERNAL_CORPUS_ROOT` | `<external-corpus-root>` | Override the corpus root. The target **must be a structural mirror of the default mount**: same dataset paths relative to the root + same audit CSV at `_workspace/_meta/analysis/api_download_completeness_audit_20260420.csv`. The `fixture_traceability` check remaps declared absolute paths into the override root before resolving, so override targets that structurally mirror the default pass cleanly; it fails only if the remapped target doesn't resolve (genuine corpus defect), not on the root string itself differing. |
| `DP_EXTERNAL_SMOKE_STRICT` | unset | When `1` / `true` / `yes`, treats "drive unmounted" as a hard failure (exit 1). Default is skip-on-unmount (exit 0) so scheduled runs don't alert when the drive is unplugged. |

**Override caveat**: The script does NOT support an override pointing
at a corpus with a *different* internal structure (flattened layout,
renamed subdirectories, partial mirror with missing datasets, etc.).
Those cases surface as failures in check 3 (`dataset_presence`) and
check 6 (`fixture_traceability`) as they should — copying or
reorganizing a corpus mirror is outside this smoke's concern.

## Exit codes

| Code | Meaning |
|---|---|
| 0 | All checks passed; OR drive unmounted and strict mode off (a normal skip). |
| 1 | At least one check failed. |
| 2 | Usage / prerequisite error (e.g. Python import path misconfigured). |

## What the 6 checks verify

1. **mount** — `DP_EXTERNAL_CORPUS_ROOT` path exists + readable.
2. **audit_csv_gate** — every Phase B dataset has
   `access_status == "available"` and `completeness_status == "未见明显遗漏"`
   in `_workspace/_meta/analysis/api_download_completeness_audit_20260420.csv`.
3. **dataset_presence** — each dataset's `dataset_path` (from the
   audit CSV) physically exists on disk.
4. **ts_code_presence** — every `ts_code` Phase B fixtures reference
   (600519.SH, 300209.SZ, 000063.SZ, 000039.SZ, 000002.SZ) still has
   data in its owning corpus dataset. by-symbol datasets match
   `<ts_code>+*.csv`; all_csv datasets scan `ts_code,` as a line
   prefix.
5. **schema_alignment** — sampled CSV headers for `stock_basic` /
   `daily` / `daily_basic` / `weekly` / `monthly` contain every column
   `data_platform.adapters.tushare.assets.TUSHARE_*_SCHEMA` declares.
   (Exact type checking is the fixture tests' job via
   `tests/dbt/test_tushare_local_fixtures.py`; this check is a column-
   presence-only upstream guard.)
6. **fixture_traceability** — every committed fixture's traceability
   block (audit-eval case `metadata.tushare_source`, entity-registry
   `*.source.json`, data-platform `_source.json`) declares a
   `dataset_path` that still resolves under the current corpus root
   AND a `datasets: [...]` list whose entries are all present in the
   audit CSV.

Checks 2–6 are independent and always run in full even when one
fails — the final summary reports all failures at once so you don't
have to re-run to see the second one.

## Expected output (green mount + green corpus)

```
external smoke — Tushare corpus @ <external-corpus-root>
────────────────────────────────────────────────────────────────────────
  ✓ mount: mounted + readable at <external-corpus-root>
  ✓ audit_csv_gate: all 12 required datasets are access=available + completeness=未见明显遗漏
  ✓ dataset_presence: all 12 dataset_paths present on disk
  ✓ ts_code_presence: all 6 Phase-B ts_codes resolve in their datasets
  ✓ schema_alignment: all 5 schema-checked datasets carry TUSHARE_*_SCHEMA required columns
  ✓ fixture_traceability: all 7 Phase-B fixtures' tushare_source blocks trace to the live corpus
────────────────────────────────────────────────────────────────────────
  6/6 checks passed
```

## Expected output (drive unmounted)

```
external smoke — Tushare corpus @ <external-corpus-root>
────────────────────────────────────────────────────────────────────────
  ✗ mount: corpus root <external-corpus-root> does not exist (drive not mounted)
      This is the expected state in CI and on dev machines where the external drive
      hasn't been plugged in; the caller usually treats this as a skip, not a failure.
────────────────────────────────────────────────────────────────────────
  0/1 checks passed
  NOTE: a failing 'mount' check is normal when the external drive is not plugged in;
  use DP_EXTERNAL_SMOKE_STRICT=1 to make that a hard failure.
```

Exit code is **0** by default so a cron / launchd job won't alert.

## Why this is NOT a pytest test

1. `<external-corpus-root>` is a developer-local mount;
   CI containers don't have it and shouldn't pretend they do.
2. Phase B's fixture assertions already ensure the in-repo fixture
   content is internally consistent. This smoke's job is the
   complementary "is the *upstream* corpus still what the fixtures
   say it was" — a different question with a different cadence.
3. Cron exit codes + stdout are simpler to monitor than a
   `pytest.skip` path that splits "not run" from "ran and passed".

## Scheduling recommendation

On the developer machine with the drive mounted, add a daily launchd
job (macOS) or cron entry:

```bash
# crontab -e (daily 09:00)
0 9 * * * cd <workspace>/data-platform \
            && ./scripts/external_smoke_tushare_corpus.sh \
            > <proof-workspace>/dp-external-smoke-$(date +\%Y\%m\%d).log 2>&1 \
            || osascript -e 'display notification "Tushare corpus smoke FAILED" with title "data-platform"'
```

The `|| osascript` tail only fires on non-zero exit, so drive-unmounted
days (exit 0) do not trigger a notification.

## Modifying the required set

If you add a Phase D / Phase E fixture that consumes a new dataset
or ts_code, update the top of
`scripts/external_smoke_tushare_corpus.py`:

- `REQUIRED_DATASETS` — tuple of doc_api names from the audit CSV
- `REQUIRED_TS_CODE_PRESENCE` — tuple of `(ts_code, dataset, reason)`
- `FIXTURE_TRACEABILITY_PATHS` — tuple of `(relpath, json_pointer)`

The helper functions auto-adapt; no per-dataset code change is needed
unless a dataset's on-disk layout is neither `split_by_symbol=True`
(by-symbol CSVs) nor `all_csv` (single `all.csv`).
