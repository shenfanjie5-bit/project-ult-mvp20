# System inventory and frontend response audit - 2026-06-17

Updated with additional file and disk inventory evidence on 2026-06-18.

This note records the current evidence from the ongoing full project
re-audit. It does not claim that every file on the repo and DOCKCASE disk has
already been reviewed end to end. It captures the parts that have current
command output, runtime checks, and browser evidence.

## Executive status

- Locked module set: 14 modules in `locks/modules.lock.yaml`.
- Vendored source snapshots in this repo: 7 packages under `upstream/`
  (`contracts`, `audit-eval`, `data-platform`, `entity-registry`,
  `graph-engine`, `main-core`, `reasoner-runtime`).
- Local BFF and frontend shell are operational for the audited project-ult
  flows.
- Updated strict locked-module service count: 0 running production-normal
  upstream services, 0 proven normal-but-disabled upstream services, 13 locked
  modules not usable as full services in this checkout, plus `contracts` as a
  normal importable dependency rather than a service.
- Skeleton adapter surfaces return clean envelopes, but most upstream services
  are not running as full production services in this repo.
- Frontend first-visible route timing is now below 1 second on the audited warm
  local path.
- The data/overlay structure validates, but data quality is not complete:
  `validate-overlays` reports 0 errors and 164,297 Unknown/conditional warning
  rows.

## Current validation evidence

Commands run from `/Users/fanjie/Desktop/Cowork/project-ult-mvp20`:

| Check | Result |
|---|---|
| `.venv/bin/mvp20 verify-lock --lock locks/modules.lock.yaml` | `ok: True`, `module_count: 14` |
| `.venv/bin/mvp20 validate-manifest --manifest config/mvp20.universe.yaml` | `ok: True`, 13 industries, 1853 constituents, `SPACE_ECONOMY` missing constituents, `live_evidence_blocked: True` |
| `.venv/bin/mvp20 validate-graphs` | `ok: True`, 12 strict graphs, `SPACE_ECONOMY` pending stub |
| `.venv/bin/mvp20 validate-providers` | `ok: True`, 6 providers, active providers: akshare/fmp/futu/tushare/yfinance, FRED planned |
| `.venv/bin/mvp20 validate-overlays` | `ok: True`, 1878 stock overlays, 13 industry overlays, 0 errors, 164,297 warnings; 35.91 s after C safe YAML loader |
| Targeted backend pytest | 7 passed |
| Audit-critical pytest subset | 276 passed |
| `npm run check` in `FrontEnd/` | passed |
| `npm run build` in `FrontEnd/` | passed; Vite built in 268 ms |
| Full `.venv/bin/python -m pytest -q --durations=20` | exit code 0, collected 77 files / 1341 tests, 2 third-party deprecation warnings |
| `.venv/bin/python scripts/audit_inventory.py --output docs/audit/file_inventory_2026-06-18.json` | metadata-only scan completed in 6.752 s; repo operational files 7,519; DockCase pruned `database_all` files 167,023; `market_data` files 15,154; all scanned roots reported `error_count=0` |
| `.venv/bin/python scripts/audit_code_index.py --output docs/audit/code_inventory_2026-06-18.json` | static source scan completed in 1.008 s; 1,172 code files, 277,098 lines, 12,345 static definitions, 7,343 imports, 0 Python parse errors |
| `.venv/bin/python scripts/audit_repo_content.py` | bounded repo text-body scan completed in 3.008 s; 7,519 files seen during the scan, 5,518 text file bodies read and SHA-256 fingerprinted, 550,514,168 bytes / 18,906,258 lines read, 1,983 binary files and 18 oversized text candidates skipped, 0 read errors |
| `.venv/bin/python scripts/audit_data_catalog.py --output docs/audit/data_catalog_2026-06-18.json --csv-row-sample-limit 1` | schema/first-row sample scan completed in 64.530 s; DOCKCASE `database_all` 160,561 CSV headers read with 0 header errors, 160,556 first data rows sampled, 5 header-only/no-data-row CSVs, and 0 sampled row-width mismatches; 6 DockCase SQLite schemas sampled; `market_data` HTML/PDF samples captured |
| `.venv/bin/python scripts/audit_dockcase_csv_semantics.py --as-of-date 2026-06-18` | signature-stratified semantic CSV scan completed in 40.921 s using head/tail samples; all 160,561 DOCKCASE warehouse CSV headers regrouped into 188 signatures; 184 signatures sampled across 329 CSV files / 25,205 real rows; 0 header read errors and 0 sampled row-width mismatches; review signals include 230 sparse columns, 3 high-empty signatures, 121 invalid sampled dates, 30 invalid sampled numerics, 317 nonstandard sampled `ts_code` values, 70 stale market-date signatures, 4 future-date signatures, 326 same-file duplicate sampled grain keys, 900 index by-symbol bundle mismatches, 2 zero-OHLC no-trade carry-forward rows, and 3 sampled OHLC ordering violations |
| `.venv/bin/python scripts/audit_a_share_data_semantics.py` | bounded semantic row scan completed for A-share core sources; 14 representative files loaded, 40,007 real rows read, 6 datasets checked, 2 clean, 4 review-class with 6 P2 issues and no sampled invalid dates/numerics/`ts_code` mismatches |
| `.venv/bin/python scripts/audit_market_documents.py` | bounded market document extractability/entity-event signal scan completed in 1.6 s; 14,956 news HTML files and 198 announcement PDFs counted; 60 HTML samples and 20 PDF samples parsed; CLS news and sampled PDFs extractable; entity/date/event signal evidence is now recorded for bounded samples: 58 / 80 entity-signal samples, 80 / 80 date-signal samples, 77 / 80 event-keyword samples, and 77 / 80 citation-preview samples; Eastmoney Guba / THS samples still show missing-title, short-text, and placeholder/boilerplate issues |
| Playwright MCP browser QA, recorded in `docs/audit/frontend_browser_qa_2026-06-18.json` | machine-readable browser route timing artifact generated; audited warm-path visible states stayed under 1 second: market overview median 101 ms / max 117 ms, stock detail `300750.SZ` median 148 ms / max 276 ms; 0 console errors or warnings |
| `.venv/bin/python scripts/audit_goal_coverage.py` | objective coverage matrix generated; 10/10 requirement dimensions have current evidence, overall status remains `not_complete` because several dimensions are bounded evidence rather than full semantic completion |
| `.venv/bin/python scripts/audit_bff_latency.py --start-server --port 8799 --output docs/audit/bff_latency_2026-06-18.json --repeats 3 --warmups 1` | temporary local BFF latency scan completed in 3.981 s; 19 sampled endpoints all HTTP 200 and under 1 second; max observed latency 422.959 ms |
| `.venv/bin/python scripts/audit_module_status.py --output docs/audit/module_status_2026-06-18.json` | locked module classifier completed in 0.002 s; 14 locked modules, 0 production-normal running upstream services, 0 proven normal-but-disabled, 13 not usable as full services, 1 normal dependency |
| Follow-up Playwright MCP route QA after frontend adapter fixes | previously blank/crashing Project ULT direct routes now render page identity: `/alerts`, `/admin/health`, `/project-ult/cycles`, `/project-ult/graph`, and `/project-ult/evidence`; latest `docs/audit/frontend_browser_qa_2026-06-18.json` includes `latest_project_ult_route_recheck`; audited warm navigation-commit-to-`h1` samples are under 1 second with Vite cold-transform caveat |

Targeted backend pytest command:

```bash
.venv/bin/python -m pytest -q \
  tests/test_server.py::test_profiles_filter_by_ts_code \
  tests/test_server.py::test_profiles_returns_universe_constituents \
  tests/test_server.py::test_health_envelope \
  tests/test_server.py::test_backtest_routes_serve_pnl_loop \
  tests/test_pnl_loop.py::test_server_handler_empty_db_is_honest \
  tests/test_pnl_loop.py::test_server_handler_serves_eval
```

Full-suite pytest status: an earlier full run looked stalled because the
overlay corpus tests were spending minutes in Python YAML parsing. Follow-up
isolation found the main slow point in `tests/test_overlays.py`:
`test_validate_overlay_set_accepts_generated_corpus` initially took 276.71 s
with the default Python YAML loader and took 40.61 s in the latest full-suite
run after switching the `mvp20.overlays` read path to the C safe YAML loader.
After that change,
`.venv/bin/python -m pytest -q --durations=20` completed with exit code 0 over
the collected 77 files / 1341 tests. The compile fixture remains the slowest
test at about 100 s because it compiles all overlays into a temporary SQLite
database; the full generated overlay corpus validation took 40.61 s on the
latest run.

Audit-critical pytest subset command:

```bash
.venv/bin/python -m pytest -q \
  tests/test_docs.py tests/test_server.py tests/test_pnl_loop.py \
  tests/test_lock.py tests/test_manifest.py tests/test_graph.py \
  tests/test_overlays.py tests/test_providers.py tests/test_scoring.py \
  tests/test_coverage.py tests/test_coverage_combined.py \
  tests/test_a_share_spec_completion.py tests/test_field_governance.py \
  tests/test_market_adapter.py tests/test_missing_balance.py --durations=8
```

## Repository file inventory

This repository has three different file classes that must not be conflated:

- Git-tracked source/config/docs under the outer mvp20 repo.
- Ignored but operational local files, especially `FrontEnd/` and `runtime/`.
- Rebuildable cache/build/session artifacts such as `.venv/`, `node_modules/`,
  `FrontEnd/src-tauri/target`, and `.claude/worktrees`.

Repeatable inventory artifact:

| Artifact | Evidence |
|---|---|
| Script | `scripts/audit_inventory.py` |
| Output | `docs/audit/file_inventory_2026-06-18.json` |
| Scan mode | metadata/stat only; no file body reads |
| Runtime | 10.695 s |
| Roots scanned | repo operational tree, `/Volumes/dockcase2tb`, pruned `database_all`, and `market_data` |
| Error count | 0 across all scanned roots |

Current tracked-file inventory:

| Scope | Count / size evidence |
|---|---:|
| `git ls-files` total | 3,456 files |
| Tracked top-level `config` | 1,920 files |
| Tracked top-level `upstream` | 1,051 files |
| Tracked top-level `factor_research` | 243 files |
| Tracked top-level `tests` | 72 files |
| Tracked top-level `docs` | 66 files |
| Tracked top-level `mvp20` | 44 files |
| Tracked top-level `scripts` | 40 files |
| Tracked top-level `pit_backtest` | 14 files |

Current local operational-file inventory, excluding `.git`, `.venv`,
`FrontEnd/node_modules`, `FrontEnd/dist`, `FrontEnd/src-tauri/target`, and
`factor_research/.venv_research`:

| Top-level path | File count |
|---|---:|
| Total after pruning rebuildable/cache roots | 7,519 |
| `config` | 1,922 |
| `.claude` | 1,621 |
| `runtime` | 1,557 |
| `upstream` | 1,297 |
| `factor_research` | 333 |
| `FrontEnd` | 254 |
| `tests` | 237 |
| `mvp20` | 96 |
| `docs` | 87 |
| `scripts` | 77 |
| `pit_backtest` | 29 |

Pruned operational-file extension mix:

| Extension | Count |
|---|---:|
| `.yaml` | 2,321 |
| `.py` | 1,694 |
| `.pdf` | 1,494 |
| `.json` | 533 |
| `.pyc` | 406 |
| `.md` | 319 |
| `.sql` | 186 |
| `.tsx` | 76 |
| `.yml` | 64 |
| `.log` | 55 |
| `.ts` | 65 |
| `.txt` | 35 |
| `.sh` | 35 |
| no extension | 86 |
| `.sqlite` | 22 |
| `.toml` | 20 |
| `.sqlite-wal` | 18 |
| `.sqlite-shm` | 18 |
| `.csv` | 15 |

Largest files in the pruned operational tree are runtime/data artifacts, not
application source: `runtime/hot.sqlite` is 2.1G; ten local
`runtime/hot.sqlite.bak*` files are about 366-367M each; the largest non-SQLite
artifact is `factor_research/04_event_study/adv/full_panel.npz` at 105M; the
largest annual-report PDFs are 79M and 74M.

Tracked extension mix:

| Extension | Count |
|---|---:|
| `.yaml` | 1,923 |
| `.py` | 892 |
| `.json` | 272 |
| `.md` | 192 |
| `.sql` | 93 |
| `.sh` | 20 |
| `.yml` | 9 |
| `.toml` | 9 |
| `.csv` | 8 |

Source line counts from the current tree:

| Scope | Lines |
|---|---:|
| All tracked Python files | 239,115 |
| `mvp20` Python | 38,279 |
| `tests` Python | 29,934 |
| `FrontEnd/src` TypeScript/TSX/CSS | 25,428 |
| `scripts` Python | 12,524 |
| `pit_backtest` Python | 2,621 |

Repeatable static code index:

| Artifact | Evidence |
|---|---|
| Script | `scripts/audit_code_index.py` |
| Output | `docs/audit/code_inventory_2026-06-18.json` |
| Scan mode | static source text scan; no project imports |
| Runtime | 1.008 s |
| Source files | 1,172 |
| Total lines / nonblank lines | 277,098 / 236,803 |
| Static imports / definitions | 7,343 / 12,345 |
| Python parse errors | 0 |
| Files with risk markers | 103 |

Repeatable repo content-body audit:

| Artifact | Evidence |
|---|---|
| Script | `scripts/audit_repo_content.py` |
| Output | `docs/audit/repo_content_2026-06-18.json` |
| Scan mode | full body read for bounded text files; binary and oversized files counted by skip reason |
| Runtime | 3.008 s |
| Files seen | 7,519 |
| Text files fully read | 5,518 |
| Text bytes / lines read | 550,514,168 bytes / 18,906,258 lines |
| Binary files skipped | 1,983 |
| Oversized text candidates skipped | 18 |
| Read errors | 0 |

Top repo content risk-marker counts from the body audit:

| Pattern | Count |
|---|---:|
| `mock` | 3,208 |
| `fixture` | 2,670 |
| `stub` | 301 |
| `placeholder` | 225 |
| `skeleton` | 177 |
| `TODO` | 66 |
| `NotImplemented` | 47 |
| `UPSTREAM_UNAVAILABLE` | 34 |
| `raise NotImplemented` | 21 |
| `FIXME` | 4 |

Ignored but operational local file inventory:

| Scope | Evidence |
|---|---|
| Operational files after pruning `.git`, `.venv`, `.playwright-mcp`, `.pytest_cache`, `.ruff_cache`, `project_ult_mvp20.egg-info`, `FrontEnd/node_modules`, `FrontEnd/dist`, `FrontEnd/src-tauri/target`, and `factor_research/.venv_research` | 7,519 files |
| `FrontEnd/src` | 145 source files: 76 `.tsx`, 64 `.ts`, 2 `.svg`, 2 `.css`, 1 `.png` |
| `FrontEnd/src` + `FrontEnd/scripts` + `FrontEnd/src-tauri/src` | 148 files |
| `FrontEnd/src-tauri/target` | 2.4G, 6,999 files; rebuildable Rust/Tauri build output |
| `.claude/worktrees` | 87M local session worktrees; not portable project state |
| `factor_research` | 606M total; includes ignored PIT snapshots / binary panels plus tracked research code and reports |

Directory sizes from the current workspace:

| Path | Size | Notes |
|---|---:|---|
| `runtime` | 10G | local data/state, ignored |
| `FrontEnd` | 2.7G | mostly `src-tauri/target`, `node_modules`, and build artifacts |
| `config` | 418M | mostly tracked overlays and config YAML |
| `factor_research` | 606M | code plus ignored research artifacts |
| `upstream` | 10M | vendored source snapshots |
| `mvp20` | 3.2M | local BFF/scoring/collector package |
| `tests` | 8.9M | tracked tests plus local caches |
| `docs` | 2.3M | docs and audit reports |

Core code map:

Code root file counts from the current source-bearing paths:

| Root | Code files | Lines | Static definitions | Risk hits |
|---|---:|---:|---:|---:|
| `upstream` | 783 | 153,908 | 8,325 | 99 |
| `mvp20` | 44 | 38,279 | 795 | 76 |
| `tests` | 79 | 29,934 | 1,820 | 70 |
| `FrontEnd/src` | 142 | 25,428 | 500 | 34 |
| `factor_research` | 55 | 11,225 | 331 | 0 |
| `scripts` | 45 | 12,524 | 334 | 29 |
| `pit_backtest` | 13 | 2,621 | 102 | 0 |
| `FrontEnd/scripts` | 1 | 789 | 52 | 0 |
| `FrontEnd/src-tauri` | 2 | 225 | 13 | 0 |

Frontend source/script/Rust-source file mix:

| Extension | Count |
|---|---:|
| `.tsx` | 76 |
| `.ts` | 64 |
| `.svg` | 2 |
| `.rs` | 2 |
| `.css` | 2 |
| `.png` | 1 |
| `.mjs` | 1 |

| Area | Largest / important files |
|---|---|
| `mvp20` BFF and scoring | `sources/tushare_source.py` 8,654 lines; `sources/fmp_source.py` 3,906; `derive.py` 3,055; `aggregator.py` 2,258; `scoring.py` 1,984; `server.py` 1,875; `overlays.py` 1,681 |
| `scripts` operations | `codex_prompt_gen.py` 1,782; `verify_overlay_closed_loop.py` 1,161; `check_a_share_spec_completion.py` 701; `script_fill.py` 597; `collector.py` 464 |
| `pit_backtest` | `collector.py` 1,124; `metrics.py` 259; `report.py` 218; `calendar.py` 154; `score.py` 152 |
| `FrontEnd/src` pages | `AuditReplay` 1,081; `Admin` 992; `EvidenceConsole` 977; `MarketOverview` 705; `StockDetail/index` 448 plus large detail panels |
| `FrontEnd/src` API | `projectUlt/contracts.ts` 385; `projectUlt/hooks.ts` 374; `client.ts` 173; stock score/overlay/technicals hooks 169-187 |

Function/class concentration scan:

| Area | Highest-count files |
|---|---|
| Static code index | `mvp20/sources/tushare_source.py` 153 definitions; `upstream/data-platform/src/data_platform/adapters/tushare/adapter.py` 107; `tests/test_realtime_bridge.py` 104; `tests/test_tushare_derive.py` 90; `upstream/entity-registry/src/entity_registry/storage.py` 90 |
| `mvp20` / scripts / PIT | `mvp20/sources/tushare_source.py` 153 defs/classes; `mvp20/sources/fmp_source.py` 57; `mvp20/derive.py` 57; `mvp20/server.py` 45; `mvp20/sources/akshare_source.py` 40; `pit_backtest/collector.py` 38; `mvp20/overlays.py` 34 |
| `FrontEnd/src` | `mocks/data/mockData.ts` 95 export/function-like entries; `StockGraphPanel.tsx` 87; `EvidenceConsole/index.tsx` 75; `api/projectUlt/hooks.ts` 67; `MarketOverview/index.tsx` 61 |

Import smoke from the current environment:

| Import surface | Result |
|---|---|
| Local packages | `mvp20` and `pit_backtest` import successfully |
| Vendored package roots | `contracts`, `audit_eval`, `audit_eval_fixtures`, `data_platform`, `entity_registry`, `main_core`, `graph_engine`, and `reasoner_runtime` import successfully when their source paths are on `sys.path` |
| Vendored public entrypoints | `contracts.public`, `audit_eval.public`, `data_platform.public`, `entity_registry.public`, `main_core.public`, `graph_engine.public`, and `reasoner_runtime.public` import successfully |
| Local adapter modules | `mvp20.adapters.graph_engine`, `data_platform`, `entity_registry`, `main_core`, `audit_eval`, and `reasoner_runtime` import successfully |
| CLI | `mvp20.cli` imports, and `.venv/bin/mvp20 --help` lists the expected orchestration commands |

Vendored upstream code scale:

| Vendored package | Source/docs/config files | Python lines | Test files |
|---|---:|---:|---:|
| `upstream/audit-eval` | 97 | 16,952 | 36 |
| `upstream/contracts` | 70 | 9,503 | 36 |
| `upstream/data-platform` | 256 | 44,497 | 74 |
| `upstream/entity-registry` | 69 | 16,476 | 40 |
| `upstream/graph-engine` | 127 | 32,581 | 57 |
| `upstream/main-core` | 158 | 14,693 | 75 |
| `upstream/reasoner-runtime` | 94 | 13,943 | 45 |

## Runtime data snapshot

Current `runtime/hot.sqlite` table counts:

| Table | Rows | Tickers | Other current evidence |
|---|---:|---:|---|
| `realtime_current` | 249,761 | 1,867 | 183 distinct `dp_id`, 141 distinct `source` |
| `company_graph_snapshot` | 1,878 | 1,853 | 12 distinct industries |
| `overlay_manifest` | 1,878 | 1,853 | compiled overlay index |
| `company_node_instance` | 217,848 | 1,853 | 116 distinct `dp_id`, 12 industries |
| `company_edge_instance` | 24,414 | 1,853 | 12 industries |

The manifest has 1853 constituents, while compiled overlay tables have 1878
stock-overlay memberships because some constituents have multiple
company-industry overlay views.

`runtime/hot.sqlite` schema inventory:

- `alert_state`
- `company_edge_instance`
- `company_graph_snapshot`
- `company_node_instance`
- `freshness_meta`
- `onboard_jobs`
- `overlay_alert`
- `overlay_manifest`
- `realtime_current`

Core runtime schema samples:

| Table | Key columns / shape |
|---|---|
| `realtime_current` | primary key `ts_code, dp_id`; `value_json`, `data_status`, `confidence`, `source`, `updated_at` |
| `company_graph_snapshot` | primary key `ts_code, industry_id`; `payload_json`, `graph_version`, `data_version`, `updated_at` |
| `overlay_manifest` | primary key `ts_code, industry_id`; `overlay_path`, `period`, `primary_industry`, `overlay_status`, `updated_at` |

Current `realtime_current` row-level date range is
`2026-05-11 15:09:19` to `2026-06-17 23:53:55` local time, with 1,867
tickers and 183 distinct `dp_id`.

Local annual-report and PIT/backtest inventory:

| Asset | Evidence |
|---|---|
| `runtime/annual_reports` | 1,495 files under 1,494 ticker directories; 4.5G |
| `runtime/backtest/20260116/pit.sqlite` | `realtime_current=151,212`, 1,641 tickers, 95 dp_ids, 49 sources; graph snapshot/overlay tables empty |
| `runtime/backtest/20260309/pit.sqlite` | `realtime_current=150,444`, 1,641 tickers, 95 dp_ids, 49 sources; graph snapshot/overlay tables empty |
| `runtime/backtest/20260421/pit.sqlite` | `realtime_current=151,231`, 1,641 tickers, 95 dp_ids, 49 sources; graph snapshot/overlay tables empty |
| `runtime/backtest/backtest.sqlite` | `scores=4,923`, `returns=9,846`, `manifest=6` |
| `runtime/backtest/pnl.sqlite` | `scores=3,704`, `scores_v2=3,704`, `returns=0`, `eval_metrics=0`, `manifest=1` |
| `factor_research/pit_extra/realbase.sqlite` | 480K, `scores=3,500`, `manifest=0` |
| `factor_research/pit_extra` | 14 dated PIT directories plus logs and realbase artifacts |

## DOCKCASE data inventory

Current external disk path: `/Volumes/dockcase2tb`.

Current recheck on 2026-06-18:

- `/Volumes/dockcase2tb` is mounted and is 63G on disk.
- `/Volumes/dockcase2tb/database_all` is 54G.
- `database_all`, excluding rebuildable `_workspace/.venv` /
  `_workspace/node_modules`, has 167,023 files.
- `database_all` has 160,561 `.csv` files under that same pruned scan.
- `/Volumes/dockcase2tb/market_data` has 15,154 files: 14,956 `.html` news
  files and 198 `.pdf` announcement files.

Confirmed sizes:

| Path | Size | Notes |
|---|---:|---|
| `/Volumes/dockcase2tb` | 63G | mounted external disk |
| `/Volumes/dockcase2tb/database_all` | 54G | primary warehouse root |
| `/Volumes/dockcase2tb/database_all/股票数据` | 33G | A-share/HK/stock warehouse source tree |
| `/Volumes/dockcase2tb/database_all/指数专题` | 13G | index data |
| `/Volumes/dockcase2tb/database_all/_workspace` | 4.5G | sync workspaces and metadata |
| `/Volumes/dockcase2tb/market_data/news` | 1.8G | news archive |
| `/Volumes/dockcase2tb/market_data/announcements` | 262M | announcement archive |

Important correction from earlier notes: `_workspace` is currently under
`database_all/_workspace`, not directly under `/Volumes/dockcase2tb`.

`database_all` full file-count scan by top-level data area:

| Area | File count | Size |
|---|---:|---:|
| `股票数据` | 120,109 | 33G |
| `指数专题` | 21,489 | 13G |
| `公募基金` | 17,791 | 2.3G |
| `_workspace` | 6,578 | 4.5G |
| `债券专题` | 599 | 327M |
| `港股数据` | 279 | 37M |
| `美股数据` | 78 | 13M |
| `ETF专题` | 47 | 8.4M |
| `期货数据` | 23 | 14M |
| `宏观经济` | 17 | 5.6M |
| `大模型语料专题数据` | 4 | 11M |
| `_meta` | 4 | 19M |
| `现货数据` | 2 | 1.5M |
| `外汇数据` | 2 | 2.8M |
| `期权数据` | 1 | 38M |

Separate `market_data` full file-count scan:

| Area | File count |
|---|---:|
| `news` | 14,956 |
| `announcements` | 198 |

`database_all` extension mix excluding `_workspace/.venv`:

| Extension | Count |
|---|---:|
| `.csv` | 160,561 |
| `.json` | 6,344 |
| `.py` | 30 |
| `.md` | 28 |
| `.pyc` | 26 |
| `.sqlite3` | 6 |
| `.jsonl` | 4 |
| `.zip` | 3 |
| `.toml` | 3 |
| `.sh` | 3 |
| `.log` | 3 |
| `.yaml` | 2 |
| `.part` | 2 |

`_workspace/.venv` itself is 879M and is treated as a rebuildable dependency
environment, not market data. The heavy useful workspace state is
`database_all/_workspace/_meta` at 3.7G; `tushare_sync` source/config is 4.1M.
`market_data` extension mix is simple: 14,956 `.html` news files and 198 `.pdf`
announcement files.

DockCase read/write boundary in current code:

- `mvp20/sources/dockcase_cache.py` reads single-`ts_code` by-symbol CSV files
  for the mapped Tushare endpoints and falls through to live Tushare for
  cross-sectional/date-range calls.
- `DOCKCASE_CACHE=0` disables the external-drive cache.
- Existing files are not modified on the normal read path.
- If `DOCKCASE_WRITEBACK` is enabled, cache misses can create a new by-symbol
  CSV file and `refresh_existing` can append strictly newer rows to an existing
  file. That path is guarded and append/create-only, but it is still a write
  path and should stay explicit in operations.

Repeatable data schema/catalog artifact:

| Artifact | Evidence |
|---|---|
| Script | `scripts/audit_data_catalog.py` |
| Output | `docs/audit/data_catalog_2026-06-18.json` |
| Scan mode | CSV first-line headers plus bounded first non-empty data row samples, SQLite schema, JSON/HTML/PDF samples; no full dataset reads |
| Runtime | 64.530 s |
| Local roots | `config`, `runtime`, `factor_research`, `docs/audit` |
| External roots | `/Volumes/dockcase2tb/database_all`, `/Volumes/dockcase2tb/market_data` |

Data catalog summary:

| Root | Data files | CSV files | CSV headers read | First rows sampled | Header-only/no-row CSVs | Header signatures | Row-width mismatches | SQLite files | Errors |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `config` | 1,920 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| `runtime` | 1,509 | 1 | 1 | 1 | 0 | 1 | 0 | 7 | 0 |
| `factor_research` | 159 | 1 | 1 | 1 | 0 | 1 | 0 | 15 | 0 |
| `docs/audit` | 12 | 3 | 3 | 3 | 0 | 2 | 0 | 0 | 0 |
| `/Volumes/dockcase2tb/database_all` | 166,918 | 160,561 | 160,561 | 160,556 | 5 | 188 | 0 | 6 | 0 |
| `/Volumes/dockcase2tb/market_data` | 15,154 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |

Important schema signals from the data catalog:

- DOCKCASE `database_all` CSV header/data-row sample scan read every one of the
  160,561 CSV first lines, sampled 160,556 first non-empty data rows, found 188
  distinct header signatures, 5 header-only/no-data-row CSVs, 0 header-read
  errors, and 0 sampled row-width mismatches.
- Top DOCKCASE header groups include fund scale rows, Shenwan/Changjiang
  industry constituents, A-share weekly/daily OHLCV, and daily indicator
  datasets.
- DOCKCASE SQLite schema sampling covered 6 `.sqlite3` files, including
  `tushare_state.sqlite3` and `tushare_warehouse.sqlite3`.
- `market_data` schema sampling confirms CLS-style HTML titles and PDF 1.7
  announcement files; this is event/document extraction material, not yet
  structured scoring data.

Repeatable DOCKCASE CSV stratified semantic artifact:

| Artifact | Evidence |
|---|---|
| Script | `scripts/audit_dockcase_csv_semantics.py` |
| JSON output | `docs/audit/dockcase_csv_semantics_2026-06-18.json` |
| Markdown output | `docs/audit/dockcase_csv_semantics_2026-06-18.md` |
| Scan mode | header-signature stratified bounded head/tail real-row samples |
| Runtime | 41.2 s |
| CSV headers regrouped | 160,561 |
| Header signatures | 188 |
| Sampled signatures | 184 |
| Sampled files / rows | 329 / 25,205 |
| Header errors / row-width mismatches | 0 / 0 |
| As-of date | 2026-06-18 |

Stratified semantic signals from the DOCKCASE CSV audit:

- The audit re-opened all 160,561 warehouse CSV files to regroup headers into
  188 signatures, then sampled up to 3 example files and 100 head/tail real rows
  per signature.
- 184 signatures had sampled rows; 4 signatures had no sampled rows.
- No header read errors or sampled row-width mismatches were detected.
- Review-class signals are now explicit rather than inferred from schema:
  230 sparse columns below 5% non-empty in their sampled stratum, 3 high-empty
  signatures, 121 invalid sampled dates, 30 invalid sampled numeric values,
  317 nonstandard sampled `ts_code` values, 70 stale market-date signatures,
  and 4 future-date signatures.
- Domain-invariant signals are now separated from parse/sparsity checks:
  326 same-file duplicate sampled grain keys, 900 index by-symbol bundle
  mismatches, 2 zero-OHLC no-trade carry-forward rows, and 3 sampled OHLC
  ordering violations. Duplicate grain checks are now
  constrained within each sampled file, so duplicated delivery/export copies do
  not inflate this issue class. The 900 bundle mismatches are concentrated in
  `指数专题/*/by_symbol` files where the filename is a bundle/container code
  but sampled rows carry component or vendor index codes. These are review
  signals, not proof that every represented full table row is invalid, because
  some sampled index and historical/delisted files use nonstandard vendor
  coding.
- This strengthens the external-disk evidence beyond first-row cataloging, but
  remains a bounded sample and is not an exhaustive read of every CSV row.

Bounded A-share semantic row audit:

| Artifact | Evidence |
|---|---|
| Script | `scripts/audit_a_share_data_semantics.py` |
| JSON output | `docs/audit/a_share_data_semantics_2026-06-18.json` |
| Markdown output | `docs/audit/a_share_data_semantics_2026-06-18.md` |
| Scan mode | selected high-value A-share CSV files; full rows for the bounded symbol/index sample |
| Symbols | `000001.SZ`, `300750.SZ`, `600519.SH` |
| Files loaded | 14 |
| Rows read | 40,007 |
| Dataset status | 2 clean, 4 review-class |
| Issue severity | 6 P2 issues; no P0/P1 issues in the sampled rows |

Semantic audit by source:

| Dataset | Files | Rows | Status | Evidence |
|---|---:|---:|---|---|
| A-share stock list | 1 | 5,499 | review | all required columns present; 2 rows have required-value gaps |
| A-share historical daily OHLCV | 3 | 16,185 | ok | no missing required values, invalid dates/numerics, duplicate keys, or symbol/file mismatches; latest sampled trade date `2026-06-05` |
| A-share income statement | 3 | 217 | review | no invalid dates/numerics; 34 required-value gaps, 36 duplicate sampled key rows, latest sampled announcement `2026-04-25` |
| A-share individual money flow | 3 | 6,936 | ok | no missing required values, invalid dates/numerics, duplicate keys, or symbol/file mismatches; latest sampled trade date `2026-06-05` |
| Sell-side broker forecast | 3 | 2,585 | review | no invalid dates/numerics; required-value completeness is 843 / 2,585 because target price / earnings / rating fields are sparse |
| Index daily OHLCV | 1 | 8,585 | review | no missing required values, invalid dates/numerics, or duplicate keys; sampled index file is stale at `2026-02-13` |

Bounded market document extractability and entity/event signal audit:

| Artifact | Evidence |
|---|---|
| Script | `scripts/audit_market_documents.py` |
| JSON output | `docs/audit/market_documents_2026-06-18.json` |
| Markdown output | `docs/audit/market_documents_2026-06-18.md` |
| Scan mode | count all `market_data` HTML/PDF files; parse bounded per-group samples; record entity/date/event/citation signal hints |
| News HTML files | 14,956 total, 60 sampled |
| Announcement PDFs | 198 total, 20 sampled |
| Issue counts | 6 missing titles, 7 short text extracts, 7 boilerplate-or-placeholder samples |
| Signal counts | 58 / 80 entity-signal samples, 80 / 80 date-signal samples, 77 / 80 event-keyword samples, 77 / 80 citation-preview samples |

Document audit by source:

| Source | Files | Sampled | Months | Extractability / signal result |
|---|---:|---:|---|---|
| `news/cls_flash` | 14,300 | 20 | `2026-02` to `2026-03` | ok; extracted text median 1,485.5 chars; no sampled issues; 8 entity, 20 date, 20 event-keyword, 20 citation-preview samples |
| `news/eastmoney_guba` | 584 | 20 | `2026-02` | review; extracted text median 818 chars, but 3 samples miss title and look like site boilerplate; 20 entity, 20 date, 20 event-keyword, 20 citation-preview samples |
| `news/ths_news` | 72 | 20 | `2026-02` to `2026-03` | review; median 1,041.5 chars but 3 missing-title samples, 7 short extracts, and 4 placeholder/boilerplate samples; 10 entity, 20 date, 17 event-keyword, 17 citation-preview samples |
| `announcements/688256` | 198 | 20 | `2025-02` to `2026-03` | ok; PDF page-count median 7.5 and first-two-page text median 1,089 chars; no sampled issues; 20 entity, 20 date, 20 event-keyword, 20 citation-preview samples |

Representative DOCKCASE schema samples:

| Data source | Representative file / table | Schema signal | Project fit |
|---|---|---|---|
| A-share stock list | `股票数据/基础数据/股票列表/all.csv` | `ts_code,symbol,name,area,industry,cnspell,market,list_date,act_name,act_ent_type` | Directly joinable to universe/profile onboarding via `ts_code` |
| A-share daily OHLCV | `股票数据/行情数据/历史日线/by_symbol/000001.SZ+平安银行.csv` | `ts_code,trade_date,open,high,low,close,pre_close,change,pct_chg,vol,amount` | Directly usable for price/history/technical factors |
| A-share income statement | `股票数据/财务数据/利润表/by_symbol/000001.SZ+平安银行.csv` | `ts_code,ann_date,f_ann_date,end_date,report_type,...,total_revenue,revenue,operate_profit,n_income,rd_exp,...` | Directly usable for financial spec/factor filling; needs unit and period policy |
| A-share money flow | `股票数据/资金流向数据/个股资金流向/by_symbol/000001.SZ+平安银行.csv` | `ts_code,trade_date,buy_sm_amount,...,buy_elg_amount,sell_elg_amount,net_mf_amount` | Directly usable for flow/funding signals |
| Sell-side forecasts | `股票数据/特色数据/券商盈利预测数据/by_symbol/000001.SZ+平安银行.csv` | `ts_code,name,report_date,report_title,org_name,author_name,quarter,tp,np,eps,pe,rating,...` | Useful for expectation/revision features; requires dedupe and broker weighting |
| Index metadata | `指数专题/指数基本信息/all.csv` | `ts_code,name,market,publisher,category,base_date,base_point,list_date` | Directly usable for benchmark/index mapping |
| Index daily OHLCV | `指数专题/指数日线行情/by_symbol/000001.SH+上证指数.csv` | `ts_code,trade_date,close,open,high,low,pre_close,change,pct_chg,vol,amount` | Directly usable for market regime and benchmark returns |
| News archive | `market_data/news/cls_flash/...html` | UTF-8 HTML with metadata and article body | Useful for event extraction; needs parser and ticker/entity linking |
| Announcement archive | `market_data/announcements/688256/...pdf` | PDF 1.7, sampled file has 3 pages | Useful for LLM/document extraction; needs PDF text extraction and citation tracking |

Tushare warehouse schema samples:

| Table | Key columns / shape | Current range / breadth |
|---|---|---|
| `fact_cn_stock_daily` | `ts_code, trade_date`, OHLCV, turnover, valuation, share float, money-flow, limits | `20260304` to `20260415`, 5,502 tickers |
| `fact_cn_stock_financial` | `ts_code, end_date`, announcement dates, income/balance/cashflow/indicator/audit fields plus raw JSON payloads | `20211231` to `20260331`, 6,138 tickers |
| `raw_api_records` | primary key `api, scope, partition_key, record_key`; `dataset_path`, `payload_json`, `fetched_at` | `2026-03-09T04:52:35` to `2026-04-20T03:08:12`, 39 APIs |

Detailed stock-data sizes:

| Path under `database_all/股票数据` | Size |
|---|---:|
| `特色数据` | 17G |
| `财务数据` | 6.7G |
| `行情数据` | 5.9G |
| `资金流向数据` | 2.6G |
| `参考数据` | 685M |
| `基础数据` | 60M |
| `打板专题数据` | 76M |
| `两融及转融通` | 22M |

The stock-data tree includes these major A-share-relevant groups:

- 基础数据: stock list, trading calendar, ST/risk-warning lists, company basics,
  management, IPO, historical stock list.
- 行情数据: historical daily, realtime daily/minute, weekly/monthly, adjusted
  prices, adjustment factors, daily indicators, limit-up/down, suspensions,
  northbound/southbound turnover.
- 财务数据: income statement, balance sheet, cash flow, forecast/flash reports,
  dividends, financial indicators, audit opinions, main business composition,
  disclosure calendar.
- 参考数据: top shareholders, pledge, buyback, share unlock, block trade, holder
  count, shareholder changes.
- 特色数据: sell-side forecasts, chip distribution, CSDC holdings, stock connect
  holdings, auction, magic nine-turn, AH premium, institutional research, broker
  monthly golden stocks.
- 资金流向数据: individual flows, THS/DC flows, sector/industry flows,
  northbound/southbound flows.
- 打板专题数据: dragon-tiger, limit-up board, THS/EM concepts, KPL/topic data,
  hot-money roster and rankings.

Tushare sync evidence from
`/Volumes/dockcase2tb/database_all/_workspace/tushare_sync/README.md`:

- About 227 Tushare APIs are cataloged.
- Current account snapshot: 15,000 points, no independent permissions.
- 203 APIs available, 24 unavailable, 0 unknown.
- 38 APIs are configured and scheduler-active.
- 165 available APIs are not yet enabled: 51 `ready_now`, 83 `needs_modeling`,
  31 `keep_independent`.

Tushare warehouse SQLite evidence:

| Store | Evidence |
|---|---|
| `/Volumes/dockcase2tb/database_all/_workspace/_meta/runtime/tushare_warehouse.sqlite3` | 1.6G, mtime 2026-04-20 11:08 |
| `/Volumes/dockcase2tb/database_all/_workspace/_meta/runtime/tushare_state.sqlite3` | 45M, mtime 2026-04-20 11:08 |
| `raw_api_records` | 1,240,373 rows |
| `fact_market_bar` | 164,852 rows |
| `fact_cn_stock_daily` | 164,492 rows |
| `dim_trading_calendar` | 72,609 rows |
| `dim_theme_membership` | 33,000 rows |
| `fact_cn_stock_financial` | 31,408 rows |
| `doc_finance_corpus` | 17,737 rows |
| `fact_overseas_financial_indicator` | 16,852 rows |
| `bridge_cross_listing` | 15,716 rows |
| `fact_index_constituent_weight` | 14,969 rows |
| `fact_macro_series` | 8,511 rows |
| `dim_cn_stock_security` | 6,313 rows |
| `dim_us_security` | 5,924 rows |
| `dim_hk_security` | 3,479 rows |
| `dim_index_security` | 1,041 rows |
| `fact_index_daily` | 360 rows |

Tushare state/control DB:

| Table / status | Evidence |
|---|---|
| Tables | `api_runtime_health`, `api_watch_health`, `job_log`, `run_log`, `sync_state`, `sqlite_sequence` |
| `sync_state` | 41,035 rows |
| Watch health status | `available_empty=139`, `available_nonempty=60`, `param_error=12`, `permission_denied=10`, `rate_limited=3`, `api_error=2`, `transport_unsupported=1` |
| Runtime health status | `success=39`, `failed=1` |
| Runtime problem counters | `permission_denied=3`, `param_error=81`, `rate_limited=0`, `fetch_error=44` |
| Latest runtime success/failure | success `2026-04-20T03:08:12`, failure `2026-04-04T12:54:23` |

External file counts:

| External data path | File count |
|---|---:|
| `/Volumes/dockcase2tb/database_all/股票数据` | 120,109 |
| `股票数据/财务数据` | 54,779 |
| `股票数据/行情数据` | 23,500 |
| `股票数据/特色数据` | 19,661 |
| `股票数据/资金流向数据` | 16,633 |
| `股票数据/参考数据` | 5,425 |
| `股票数据/两融及转融通` | 83 |
| `股票数据/打板专题数据` | 17 |
| `股票数据/基础数据` | 11 |
| `/Volumes/dockcase2tb/market_data/news` | 14,956 |
| `/Volumes/dockcase2tb/market_data/announcements` | 198 |

Local runtime side evidence:

- `runtime/backtest`: 148M.
- `runtime/quant_score`: 364K.
- `runtime/hot.sqlite`: 2.1G.
- `runtime/hot.sqlite.bak*`: 10 local backup files at roughly 366-367M each,
  about 3.6G total; useful for recovery but not on the frontend hot path.
- `runtime/history` is absent, so minute-history replay routes do not have the
  expected local history directory.
- `runtime/hot.sqlite:freshness_meta` reports realtime freshness
  `2026-06-17 23:53:55 CST`; this is near-current but still not same-day fresh
  relative to this 2026-06-18 audit.

## Frontend response and BFF hot path

Hot BFF timings with the current running server on port 8701:

| Endpoint | Status | Time | Size |
|---|---:|---:|---:|
| `/api/project-ult/profiles?ts_code=300750.SZ` | 200 | 0.001130 s | 218 B |
| `/api/project-ult/profiles` | 200 | 0.004927 s | 231,230 B |
| `/api/project-ult/industry-graphs` | 200 | 0.001022 s | 1,169 B |
| `/api/project-ult/industry-graphs?industry_id=STORAGE_GRID` | 200 | 0.000920 s | 28,196 B |

Repeatable BFF latency artifact:

| Artifact | Evidence |
|---|---|
| Script | `scripts/audit_bff_latency.py` |
| Output | `docs/audit/bff_latency_2026-06-18.json` |
| Mode | starts a temporary local BFF on `127.0.0.1:8799`, warms routes once, measures each endpoint 3 times |
| Endpoints sampled | 19 |
| Result | all HTTP 200 and all under 1 second |
| Max observed latency | 422.959 ms |

Slowest measured endpoints in the repeatable BFF latency scan:

| Endpoint | Median | Max | Size |
|---|---:|---:|---:|
| `/api/project-ult/score?ts_code=300750.SZ` | 422.906 ms | 422.959 ms | 6,867 B |
| `/api/project-ult/coverage?ts_code=300750.SZ` | 395.944 ms | 396.177 ms | 5,780 B |
| `/api/project-ult/stock-overlay?ts_code=300750.SZ` | 30.092 ms | 30.255 ms | 941,532 B |
| `/api/project-ult/health` | 1.394 ms | 1.425 ms | 127 B |
| `/api/project-ult/technicals?ts_code=300750.SZ` | 1.009 ms | 1.068 ms | 1,361 B |

Browser route timing evidence from the in-app browser after BFF YAML cache and
frontend query/defer changes:

| Route | First run visible | Repeat visible | Error overlay |
|---|---:|---:|---|
| `/?data_mode=projectUlt` | 544 ms | 474 ms | no |
| `/stock/300750.SZ?data_mode=projectUlt` | 347 ms | 225 ms | no |

Current in-app browser QA pass on 2026-06-18:

| Check | `/?data_mode=projectUlt` | `/stock/300750.SZ?data_mode=projectUlt` |
|---|---:|---:|
| Meaningful visible state | 566 ms | 197 ms |
| Page title | `AI 投研操作系统` | `AI 投研操作系统` |
| Not blank | yes, 4,075 chars / 51 buttons | yes, 3,195 chars / 27 buttons |
| Framework error overlay | no | no |
| Console `error` / `warn` | none | none |
| Screenshot evidence | captured in Browser tool output | captured in Browser tool output |

Interaction proof: on the 300750.SZ detail route, `查看解释链` resolved to one
button. Clicking it opened the explanation-chain drawer for 宁德时代 in 309 ms;
the DOM then contained explanation-chain / main-driver content, URL stayed
stable, and console `error` / `warn` remained empty.

Responsive QA recheck on a 390x844 mobile viewport:

| Route | Meaningful visible state | Page-level horizontal overflow | Console `error` / `warn` |
|---|---:|---:|---:|
| `/stock/300750.SZ?data_mode=projectUlt` | 245 ms | no (`scrollWidth=390`, `clientWidth=390`) | none |

The mobile check initially exposed a fixed-width shell: `html/body/#root`
had `min-width:1280px`, and `.app-shell` lacked an explicit grid column so
the implicit grid column expanded to about 644 px. The local frontend fix
removes the global 1280px minimum, gives `.app-shell` a
`minmax(0, 1fr)` column, constrains shell children to `min-width:0`, and
adds responsive wrapping / long-token breaks to the stock header, common
cards, factor list, and status bar. The final mobile scan has no page-level
horizontal scroll; the status bar keeps its dense controls inside an internal
scroll area on narrow screens.

Changes that enabled this:

- BFF now caches YAML loads by file mtime for manifest, module, provider,
  profile, and industry graph handlers.
- `/api/project-ult/profiles` supports `ts_code`, so stock detail can request
  one profile instead of the full universe.
- BFF suppresses client-cancel `BrokenPipeError` / `ConnectionResetError`
  tracebacks caused by React Query or browser navigation cancellation.
- Frontend propagates `AbortSignal` into project-ult GET requests.
- Market overview prefetches the StockDetail chunk, prehydrates the clicked
  stock profile into React Query, and delays expensive background score fanout.
- Stock detail defers heavy overlay/realtime/history/technical/aggregate calls
  until the profile screen is visible.
- Frontend shell and stock-detail cards now keep mobile width responsive:
  no global 1280px minimum, no implicit grid-column expansion, and long
  data-quality/source-id tokens wrap instead of forcing page overflow.

`FrontEnd/` is gitignored in this repository, so these frontend source changes
are on disk but do not appear in `git diff`.

## BFF route smoke - 2026-06-18

Temporary server command:

```bash
.venv/bin/mvp20 serve --host 127.0.0.1 --port 8799
```

The local sandbox blocks `urllib` loopback calls unless the command is run
outside the sandbox, so the HTTP smoke was run with local-network approval.
The temporary server was stopped after the smoke.

Cold-ish route smoke over 20 endpoints: all returned HTTP 200. This proves the
local BFF route families are callable; it does not upgrade skeleton/fixture
routes into production services.

| Route family | Endpoints sampled | Status | Timing evidence |
|---|---:|---|---:|
| Health/module/profile/graph core | 5 | 200 | 1.69-212.79 ms |
| Stock detail data core | 4 | 200 | 65.72-468.61 ms |
| P&L/backtest API | 1 | 200 | 67.36 ms |
| Vendored upstream adapter families | 7 | 200 skeleton fixture | 0.32-0.61 ms |
| Local BFF stubs | 3 | 200 empty fixture | 0.25-0.46 ms |

Warm-cache core route timing, same temporary server:

| Endpoint | Status | Time | Size |
|---|---:|---:|---:|
| `/api/project-ult/profiles?ts_code=300750.SZ` | 200 | 9.78 ms | 218 B |
| `/api/project-ult/industry-graphs?industry_id=STORAGE_GRID` | 200 | 0.81 ms | 28,196 B |
| `/api/project-ult/stock-overlay?ts_code=300750.SZ` | 200 | 38.09 ms | 941,532 B |
| `/api/project-ult/coverage?ts_code=300750.SZ` | 200 | 404.99 ms | 5,780 B |
| `/api/project-ult/score?ts_code=300750.SZ` | 200 | 433.62 ms | 6,786 B |
| `/api/project-ult/modules` | 200 | 0.59 ms | 2,201 B |

Adapter body samples explicitly report `fixture: true` and
`wire_depth: skeleton` for `graph-engine`, `data-platform`, and
`reasoner-runtime`. The orchestrator route reports `module: mvp20-bff`,
`fixture: true`, and an empty `runs` list.

## Module status

Repeatable module-status artifact:

| Artifact | Evidence |
|---|---|
| Script | `scripts/audit_module_status.py` |
| Output | `docs/audit/module_status_2026-06-18.json` |
| Runtime | 0.002 s |
| Locked module count | 14 |
| Normally running locked upstream services | 0 |
| Proven normal-but-not-enabled locked upstream services | 0 |
| Locked modules not usable as full services here | 13 |
| Normal dependency, not a service | 1 (`contracts`) |

Counting rules:

- **Locked modules** are the 14 entries in `locks/modules.lock.yaml`; this
  excludes the local `mvp20` package and `FrontEnd/` application.
- **Callable** means the current repo can import the package or return a 200
  route envelope.
- **Production-normal** means the module returns real behavior without a
  `fixture: true` / `wire_depth: skeleton` envelope and without requiring an
  unconfigured external service.

Locked-module classification:

| Locked module | Current state in this checkout | Operational classification | Evidence |
|---|---|---|---|
| `contracts` | vendored source imports successfully and exposes public contracts | normal dependency, not a standalone service | `upstream/contracts`, import smoke |
| `audit-eval` | vendored source imports; adapter route returns fixture envelope | callable skeleton, not production-normal | adapter route family + `wire_depth: skeleton` |
| `data-platform` | vendored source imports; adapter route returns fixture envelope | callable skeleton, not production-normal | adapter route family + runtime-service notes |
| `entity-registry` | vendored source imports; adapter route returns fixture envelope | callable skeleton, not production-normal | adapter route family + empty entity payload |
| `graph-engine` | vendored source imports; adapter route returns fixture envelope | callable skeleton, not production-normal | adapter route family; full service needs Neo4j |
| `main-core` | vendored source imports; adapter routes return skeleton/empty envelopes | callable skeleton, not production-normal | cycles/stocks/world-state routes |
| `reasoner-runtime` | vendored source imports; adapter route returns fixture envelope | callable skeleton, not production-normal | adapter route family; full use needs LLM runtime |
| `frontend-api` | not vendored; replaced by local mvp20 BFF in this repo | unavailable as locked module here | lock entry + README/server route table |
| `subsystem-sdk` | locked but not vendored here | unavailable as locked module here | `locks/modules.lock.yaml` only |
| `orchestrator` | locked but not vendored here; local runs route is an empty BFF stub | unavailable as locked module here | lock entry + `/orchestrator/runs` stub |
| `assembly` | locked but not vendored here | unavailable as locked module here | `locks/modules.lock.yaml` only |
| `subsystem-announcement` | locked but represented by local empty/stub routes only | unavailable as full module here | lock + BFF stub routes |
| `subsystem-news` | locked but represented by local data/archive, not a service | unavailable as full module here | lock + local data only |
| `subsystem-holdings` | locked but represented by local data/source coverage, not a service | unavailable as full module here | lock + data/source coverage only |

Local user-runnable surfaces:

| Local surface | Current state | Evidence |
|---|---|---|
| `mvp20` BFF | running/normal for audited read-only routes | pytest, route smoke, warm timings |
| `FrontEnd/` | running/normal for audited projectUlt routes | `npm run check`, `npm run build`, browser timing |

Practical count:

- Total locked modules: **14**.
- Updated objective count, locked upstream modules only:
  - **Normally running now:** **0 / 14** production-normal upstream services.
  - **Can run normally but not enabled:** **0 / 14 proven**. Importability and
    skeleton 200 responses are not strong enough evidence to claim a module can
    run normally.
  - **Not usable as a full service in this checkout:** **13 / 14** locked
    modules. This combines 6 skeleton-wired modules and 7 modules with no full
    vendored source/runtime here.
  - **Normal dependency, not a running service:** **1 / 14** (`contracts`).
- Local user-runnable surfaces, outside the 14-module lock count: **2 normally
  running** (`mvp20` BFF and `FrontEnd/` projectUlt flow).
- Locked modules that are importable/route-callable only through skeleton or
  fixture wiring: **6** (`graph-engine`, `data-platform`, `entity-registry`,
  `reasoner-runtime`, `main-core`, `audit-eval`).
- Locked modules unavailable as complete modules in this repo: **7**
  (`subsystem-sdk`, `orchestrator`, `assembly`, `frontend-api`,
  `subsystem-announcement`, `subsystem-news`, `subsystem-holdings`).
- Directly operational app surfaces in this repo: **2** (`mvp20` BFF and
  `FrontEnd/`). These are not part of the 14-module lock count, but they are
  the surfaces a user can currently run locally.
- Modules with deeper-than-skeleton runtime needs before they can be counted
  as production-normal: `graph-engine`, `data-platform`, `reasoner-runtime`,
  and `audit-eval`.

Readiness keyword scan:

- `rg -l "TODO|FIXME|NotImplemented|skeleton|fixture: true|stub|placeholder|UPSTREAM_UNAVAILABLE" mvp20 upstream FrontEnd/src scripts pit_backtest factor_research`
  previously found 92 files in the core paths.
- A broader scan over the current repository, excluding heavy caches/build
  outputs and `runtime/`, currently finds 102 files with
  `TODO|FIXME|NotImplemented|raise NotImplemented|stub|skeleton|placeholder|UPSTREAM_UNAVAILABLE`.
  Distribution by top-level path: `upstream` 46, `tests` 19, `mvp20` 18,
  `docs` 6, `factor_research` 5, `scripts` 4, `config` 3, `README.md` 1.
- Local source match-line distribution for the same risk family, scoped to
  `mvp20`, `pit_backtest`, `scripts`, `FrontEnd/src`, `FrontEnd/scripts`, and
  `FrontEnd/src-tauri/src`: `mvp20` 70, `FrontEnd` 33, `scripts` 6.
- The local BFF adapter files explicitly return `wire_depth: skeleton` for
  graph-engine, data-platform, entity-registry, audit-eval, main-core, and
  reasoner-runtime adapter families.
- `upstream/main-core/docs/PROGRESS.md` still lists milestones 1-5 and
  ISSUE-004 through ISSUE-014 as `blocked`; that supports treating main-core
  as skeleton-wired in this repo rather than fully production-normal.
- `scripts/check_spec_drift.py`, `mvp20/derive.py`, `mvp20/scoring.py`, and
  `mvp20/sources/tushare_source.py` contain explicit TODO or placeholder notes
  around spec drift inference, HK/US weekly/monthly coverage, Tier 1.5 derives,
  adaptive scoring calibration, and industry mapping gaps.

## Code changes in this pass

Tracked backend/package/test files currently changed:

- `mvp20/server.py`
  - YAML mtime cache.
  - `profiles?ts_code=` filter and validation.
  - client-cancel exception handling.
- `mvp20/overlays.py`
  - uses `yaml.CSafeLoader` when available for overlay YAML reads; this reduces
    full overlay corpus validation from 276.71 s before the change to 40.61 s
    in the latest full-suite run, and makes `validate-overlays` complete in
    35.91 s locally.
- `mvp20/pnl_loop.py`
  - adds repo root to `sys.path` so the console entry point can import local
    `pit_backtest`.
- `pyproject.toml`
  - includes `pit_backtest*` in setuptools package discovery.
- `tests/test_server.py`
  - adds coverage for `profiles?ts_code=300750.SZ`.
- `scripts/audit_inventory.py`
  - adds repeatable metadata-only inventory for the repo and DockCase roots.
- `scripts/audit_code_index.py`
  - adds repeatable static source-code inventory for Python / TypeScript /
    TSX / Rust / shell / SQL / CSS code roots without importing project code.
- `scripts/audit_repo_content.py`
  - adds repeatable repo text-body audit for bounded text files, including
    SHA-256 fingerprints, risk markers, and explicit binary/oversized skip
    reasons.
- `scripts/audit_data_catalog.py`
  - adds repeatable lightweight data schema/catalog audit for CSV headers,
    bounded first-row samples, sampled row-width mismatches, SQLite schemas,
    and JSON/HTML/PDF samples.
- `scripts/audit_dockcase_csv_semantics.py`
  - adds repeatable DOCKCASE CSV header-signature stratified semantic sampling
    across head/tail real rows, with date, numeric, `ts_code`, sparsity,
    freshness, by-symbol code consistency, grain-duplicate, OHLC invariant,
    read-error, and row-width review signals.
- `scripts/audit_a_share_data_semantics.py`
  - adds repeatable bounded semantic-row audit for high-value A-share DockCase
    sources, checking required fields, dates, numeric values, duplicate keys,
    symbol/file consistency, and freshness for selected symbols.
- `scripts/audit_market_documents.py`
  - adds repeatable bounded extractability audit for DockCase `market_data`
    news HTML and announcement PDFs, checking titles, extracted text length,
    boilerplate/placeholder samples, PDF headers, page-count estimates, and
    optional PDF text extraction, plus bounded entity/date/event keyword and
    citation-preview signal counts for sampled documents.
- `scripts/audit_goal_coverage.py`
  - adds a conservative requirement-by-requirement coverage matrix across the
    inventory, code, data, score, latency, browser-evidence, and module-status
    audit artifacts.
- `scripts/audit_bff_latency.py`
  - adds repeatable local BFF endpoint latency audit with optional temporary
    server startup.
- `scripts/audit_module_status.py`
  - adds repeatable locked-module classification from module lock, vendored
    source, skeleton adapter markers, and BFF latency evidence.
- `tests/test_audit_inventory.py`
  - covers inventory extension counting and nested relative prune behavior.
- `tests/test_audit_code_index.py`
  - covers Python AST counting, TypeScript counting, and node_modules pruning.
- `tests/test_repo_content.py`
  - covers bounded text-body reads, digest/risk marker capture, and
    binary/oversized skip reasons.
- `tests/test_audit_data_catalog.py`
  - covers CSV header aggregation/pruning, first-row sample capture,
    header-only CSV counting, sampled row-width mismatch detection, and SQLite
    schema extraction.
- `tests/test_dockcase_csv_semantics.py`
  - covers header-signature stratified head/tail row sampling,
    date/numeric/`ts_code` issue detection, row-width mismatches, sparse
    columns, stock by-symbol code mismatches, index by-symbol bundle
    mismatches, duplicate grain keys, OHLC invariant violations, freshness,
    and Markdown output.
- `tests/test_a_share_data_semantics.py`
  - covers clean semantic source checks, invalid dates/numerics, missing files,
    and symbol-file mismatch detection for the A-share semantic audit.
- `tests/test_market_documents.py`
  - covers HTML text/title extraction, stock-code hints, PDF header/page
    metadata, entity/date/event signal counts, short text, and bad PDF
    detection for the market document audit.
- `tests/test_goal_coverage.py`
  - covers the conservative goal coverage matrix and verifies missing evidence
    remains incomplete rather than being promoted to done.
- `tests/test_audit_bff_latency.py`
  - covers URL joining, response-key extraction, and latency summary behavior.
- `tests/test_audit_module_status.py`
  - covers strict module classification for dependency, skeleton, and missing
    module cases.
- `docs/audit/file_inventory_2026-06-18.json`
  - generated inventory summary for the current repo / DockCase scan.
- `docs/audit/code_inventory_2026-06-18.json`
  - generated static code index summary for the current source-bearing roots.
- `docs/audit/repo_content_2026-06-18.json`
  - generated machine-readable repo text-body audit with text-file
    fingerprints and skip reasons.
- `docs/audit/repo_content_2026-06-18.md`
  - generated human-readable repo text-body audit report.
- `docs/audit/data_catalog_2026-06-18.json`
  - generated data schema/catalog summary for current local data and DockCase
    roots.
- `docs/audit/dockcase_csv_semantics_2026-06-18.json`
  - generated machine-readable DOCKCASE CSV stratified semantic-row audit.
- `docs/audit/dockcase_csv_semantics_2026-06-18.md`
  - generated human-readable DOCKCASE CSV stratified semantic-row audit.
- `docs/audit/a_share_data_semantics_2026-06-18.json`
  - generated bounded semantic-row audit summary for selected A-share DockCase
    source files.
- `docs/audit/a_share_data_semantics_2026-06-18.md`
  - generated human-readable A-share semantic data audit report.
- `docs/audit/market_documents_2026-06-18.json`
  - generated bounded extractability audit for DockCase market news HTML and
    announcement PDF samples.
- `docs/audit/market_documents_2026-06-18.md`
  - generated human-readable market document extractability audit report.
- `docs/audit/frontend_browser_qa_2026-06-18.json`
  - generated machine-readable Playwright browser QA timing artifact for the
    audited frontend warm paths.
- `docs/audit/frontend_browser_qa_2026-06-18.md`
  - generated human-readable Playwright browser QA timing report.
- `docs/audit/goal_coverage_2026-06-18.json`
  - generated machine-readable objective coverage matrix with `not_complete`
    status.
- `docs/audit/goal_coverage_2026-06-18.md`
  - generated human-readable objective coverage matrix.
- `docs/audit/bff_latency_2026-06-18.json`
  - generated BFF latency summary for 19 frontend hot-path/API endpoints.
- `docs/audit/module_status_2026-06-18.json`
  - generated locked-module status summary for the updated module-count
    objective.

Frontend files changed on disk but gitignored:

- `FrontEnd/src/api/client.ts`
- `FrontEnd/src/api/projectUlt/hooks.ts`
- `FrontEnd/src/api/hooks/useIndustryGraphs.ts`
- `FrontEnd/src/api/hooks/useStockOverlay.ts`
- `FrontEnd/src/api/hooks/useStockScore.ts`
- `FrontEnd/src/api/hooks/useStockAggregate.ts`
- `FrontEnd/src/api/hooks/useStockCoverage.ts`
- `FrontEnd/src/api/hooks/useTechnicals.ts`
- `FrontEnd/src/api/hooks/useStockHistory.ts`
- `FrontEnd/src/pages/MarketOverview/index.tsx`
- `FrontEnd/src/pages/StockDetail/index.tsx`
- `FrontEnd/src/pages/StockDetail/components/RealtimeHistoryChart.tsx`
- `FrontEnd/src/pages/StockDetail/components/StockGraphPanel.tsx`
- `FrontEnd/src/components/data/FactorWaterfall.tsx`

## Goal coverage matrix

`docs/audit/goal_coverage_2026-06-18.json` links the current audit artifacts
back to the original objective. It is intentionally conservative: every
requirement dimension has current evidence, but the overall goal is still
`not_complete`.

| Requirement dimension | Status | Evidence strength |
|---|---|---|
| Repo operational file inventory / text body audit | covered | metadata full walk plus bounded text-body reads |
| DOCKCASE file inventory | covered | metadata full walk |
| Source-code static inventory | covered | static index over selected source-bearing roots |
| DOCKCASE schema / first-row catalog | covered | all CSV headers plus bounded first-row samples |
| DOCKCASE CSV stratified semantic audit | covered | header-signature stratified bounded real-row sample |
| A-share structured semantic data | covered | bounded real-row semantic sample |
| Market document extractability | covered | all-file count plus bounded parse samples |
| A-share score-field path | covered | runtime trace plus gap-priority artifact |
| Frontend/BFF hot-path latency | covered | BFF machine artifact plus machine-readable browser QA |
| Locked-module status | covered | lockfile plus latency evidence |

Current completion blockers from the matrix:

- Repo binary/large files are not fully body-read and file semantics are not
  exhaustively reviewed.
- DOCKCASE CSV semantic review is signature-stratified and evidence-backed, but
  not exhaustive across every CSV row/file.
- Market document entity/event signal evidence is bounded to samples and is not
  full entity linking or event classification for every document.
- A-share score field trace still reports participating gaps.
- Frontend browser timing covers selected audited routes, not every interaction.

## Remaining work before declaring full goal complete

- Full repository file-by-file content audit is still not complete. Current
  evidence now covers all tracked-file counts, 7,519 pruned operational files,
  full-body reads for 5,518 bounded text files, risk-keyword distribution, key
  source/config/docs/tests/runtime DB, and DOCKCASE top-level data roots; it
  still does not prove every binary/large file body or every implementation
  path was semantically reviewed.
- External disk data has been inventoried by full top-level file count and
  size, key Tushare workspace docs, all DOCKCASE `database_all` CSV headers,
  bounded first-row samples for non-empty CSVs, SQLite schemas, stratified
  semantic samples across 184/188 CSV header signatures, and representative
  HTML/PDF samples. The selected A-share stock list, daily bar,
  income-statement, money-flow, broker-forecast, and index-bar sources now also
  have bounded semantic row checks; `market_data` news/announcement documents
  now have bounded text/PDF extractability and entity/date/event signal checks.
  This still does not mean every CSV row, every HTML/PDF body, or every
  extracted entity/link was semantically reviewed.
- Current hot data is near-current but not same-day fresh relative to
  2026-06-18; the next correctness pass needs focused Tushare refreshes or an
  explicit stale-data mode in the UI.
- `runtime/history` is missing, so history/replay UI cannot be counted as fully
  backed by local data yet.
- P&L score tables exist, but `returns` and `eval_metrics` are empty; the P&L
  loop is serviceable as an API surface but not yet populated with mature eval
  truth.
- `validate-overlays` proves structure but also shows a large warning backlog.
  The separate A-share score-trace audit now exists at
  `docs/audit/a_share_score_trace_2026-06-18.md`: 256 spec dp_ids, 174
  governance-participating dp_ids, 1,641 A-share tickers, 126 valid real
  runtime dp_ids, 95 numeric-signal dp_ids, 80 runtime bridge-emitted dp_ids,
  28 overlay score-candidate dp_ids, 105 effective score-path dp_ids, and 69
  participating gaps; 31 valid real runtime dp_ids still have no numeric
  formula under the broad data-quality count, but only 18 are score-relevant
  formula gaps and 13 are non-final raw/audit fields. The new gap-priority
  audit at `docs/audit/a_share_score_gap_priority_2026-06-18.md` further splits
  those 18 into 18 design/governance review items and 0 score-relevant
  low-coverage direct-formula repairs. EPS, operating profit, forecast EPS,
  forecast margin, discussion heat, insider sell, management change, and
  margin-financing anomaly now enter scoring through bounded formulas. The
  remaining work is governance/design review plus collector/LLM/web gap repair,
  not proving whether this audit exists.
- The automated Python test gate is now green, but that is not the same as
  proving every file and external data item has been reviewed end to end.
- Skeleton adapter modules need deeper service-level verification before being
  counted as production-normal modules.
- If strict cold-start sub-1s is required, add explicit BFF warmup for large
  YAML files and measure a fresh process, not only warm-cache local routes.
