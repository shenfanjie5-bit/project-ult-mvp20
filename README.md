# project-ult-mvp20

Public orchestration shell for the Project ULT 13-industry MVP.

This repository owns the MVP manifest, module lock, runbooks, fixture evidence,
runtime BFF, frontend shell, and CI checks. It vendors a bounded snapshot of
selected upstream `project-ult-*` source directories under `upstream/` for
skeleton wiring, but the lock file still records the broader upstream module
set as pinned SHAs.

## Current Audit Snapshot (updated 2026-06-20)

The latest machine-readable completion/deviation snapshot is recorded in
`docs/audit/completion_deviation_2026-06-20.json`. It aggregates the 2026-06-20
A-share final-score applicability, approved runtime materialization execution,
module-status, BFF latency, and DOCKCASE CSV quality-impact audits. The retained
frontend response evidence remains the 2026-06-19 production-preview pass:
`docs/audit/frontend_shell_latency_2026-06-19.json`,
`docs/audit/frontend_browser_qa_2026-06-19.json`,
`docs/audit/frontend_stock_detail_perf_probe_2026-06-19.json`, and
`docs/audit/bff_concurrent_probe_2026-06-19.json`.

Verified status from the current worktree:

- Current-MVP completion/deviation audit: **100.0% completion** and **0.0%
  deviation** across five audited areas: A-share final-score closure, approved
  runtime materialization, locked-module contract surfaces, BFF/API smoke
  latency, and DOCKCASE CSV quality impact.
- A-share score-relevant closure uses a transparent two-denominator policy.
  Raw score-relevant final-score closure is **132 / 174**. The current local MVP
  denominator is **120 / 120** after excluding 54 fields only when backed by
  audit evidence: unapproved generation/backlog, policy review, governance
  suppression, option-universe N/A, valuation peer-context supersession, or
  verified no-final-score-delta score-sink evidence.
  Current-MVP A-share actionable gap is **0**.
- The approved A-share materialization batch executed against
  `runtime/hot.sqlite` with a backup, `pragma quick_check`, transactional
  UPSERT, and post-write verification. A read-only post-execution review now
  verifies **11,006** planned rows with **0** value-contract errors, records
  **1,011** inserts, and explicitly documents the historical **9,995**
  timestamp-only no-op row refreshes fixed in the execution script for future
  runs. Production score writes remain disallowed.
- Module lock validates with **14 modules**.
- The 2026-06-20 module audit accounts for all 14 locked modules under the
  current MVP contract-surface policy: **6 artifact-backed adapters**,
  **1 importable dependency** (`contracts`), and **7 verified replacement
  paths**. It does not claim those 13 non-`contracts` modules are
  production-normal upstream services in this checkout.
- The 6 adapter-backed upstream route families now serve local
  `upstream/*/artifacts/frontend-api/` payloads through `mvp20/adapters/*` with
  `wire_depth: artifact`; if an artifact or optional dependency is missing, the
  route returns a structured `503 UPSTREAM_UNAVAILABLE` envelope instead of
  crashing the BFF.
- **7 locked modules** are not vendored as source in this repo and should be
  treated as unavailable or stub-only here: `subsystem-sdk`, `orchestrator`,
  `assembly`, `frontend-api`, `subsystem-announcement`, `subsystem-news`, and
  `subsystem-holdings`.
- The local `mvp20` BFF and `FrontEnd/` projectUlt flow are the currently
  operational user-facing app surfaces. Adapter-backed upstream route families
  can return clean 200 artifact envelopes, but that is not proof of production
  service readiness.
- Separate from the 14 locked upstream modules, the current checkout has **17
  local runtime/data/tooling surfaces** that carry API, frontend, collector,
  runtime store, backtest, quant-shadow, DockCase cache, research, and audit
  work. The strict read is: `mvp20` CLI, BFF, `FrontEnd/`, AKShare source,
  DockCase cache, hot store/history runtime, PIT backtest, P&L feedback loop,
  and docs/audit tooling are normal; Tauri, collector daemon, Tushare, FMP,
  Futu, quant-score shadow, and factor-research are runnable but not currently
  enabled; yfinance is configured as a provider but has no local collector
  implementation. `FrontEnd/` remains gitignored, so frontend source changes
  are intentionally local unless explicitly staged through a different path.
- A 2026-06-20 BFF latency audit through a temporary local server hit the core
  BFF and adapter route samples with all responses OK and under the 1 second
  threshold; max observed latency was **113.262 ms**. The 2026-06-19 frontend
  hot-path evidence remains valid for the gitignored `FrontEnd/` shell.
- A-share workbench 5-day signals are now backend-backed by
  `runtime/signal_5d/A_share.json`, built from DockCase daily/daily_basic data
  and frozen `factor_research` calibration. The display contract is
  **5日跑赢同日流动性股票中位数概率**, not absolute 5日上涨概率. Current local
  artifact coverage is **1,610 rows / 1,100 validated**; as of 2026-06-20 it is
  correctly marked stale because the mounted DockCase archive latest trade date
  is 20260605. The v2 calibration trains a 7-feature ridge-logistic candidate
  (`ivol_60`, `ep_ttm`, `strev`, `max5`, `turnover_20`, `rvol_20`, `mom_6_1`)
  and keeps the legacy 10-bin calibration as audit/fallback evidence. The
  12-date walk-forward test passed the aggressive model gates (avg Brier skill
  **0.00282**, avg rank IC **0.0576**, avg top-20 excess **+0.77pp**, avg unique
  1dp probabilities **160.9**), but the stricter 42-date gate failed Brier skill
  and rank-IC-vs-fallback. Production therefore uses the per-stock continuous
  `score_pct_linear_bin10` probability source, with the logistic value emitted
  as `model_probability_shadow`; the current validated artifact has **364**
  distinct 4-decimal probabilities and **37** distinct 1-decimal probabilities,
  so it is no longer a 10 reused-value display. UI/API must still treat this as
  a relative ranking hint, not a high-conviction forecast. Stale rows can be
  shown as gray `过期预览` values for inspection, but they remain
  `validated=false` and are not counted as effective signals.
  Evidence:
  `docs/audit/2026-06-20_a_share_signal_5d_artifact_audit.json`,
  `docs/audit/2026-06-20_a_share_signal_5d_bff_smoke.json`, and
  `docs/audit/2026-06-20_a_share_signal_5d_frontend_binding.json`,
  `docs/audit/2026-06-20_a_share_signal_5d_review_audit.json`,
  `docs/audit/2026-06-20_a_share_signal_5d_backtest_10_dates.json`, and
  `docs/audit/2026-06-20_a_share_signal_5d_contract_smoke.json`,
  `docs/audit/2026-06-20_a_share_signal_5d_model_backtest.json`, and
  `docs/audit/2026-06-20_a_share_signal_5d_model_backtest_42_dates.json`.
- DOCKCASE CSV quality-impact audit now consumes the completed 160,596-file
  full-row scanner plus all-file evidence. It classifies scoring/backtest/graph
  and BFF-impacting blockers at **0**, while retaining watchlist and
  current-MVP-non-blocking issue counts for later data hygiene.
- Historical warm-browser route visibility remains under 1 second for the
  retained 2026-06-17/18 samples: market overview 544 ms first run / 474 ms
  repeat and stock detail 347 ms first run / 225 ms repeat, with no error
  overlay. The current 2026-06-19 production-preview evidence is the
  first-`h1`, core-ready, StockDetail probe, shell-latency, and concurrent BFF
  evidence listed below.
- 2026-06-19 production-preview browser QA in
  `docs/audit/frontend_browser_qa_2026-06-19.json` confirms first route
  identity is under 1 second for `/`, `/pool`, `/stock/300750.SZ`, and
  `/add-stock`: max navigation-to-`h1` was 240 ms, max first-`h1` wait was
  106 ms, and console error/warn count was 0. The `查看解释链` drawer opened in
  306 ms, and the 390px mobile stock-detail viewport had no page-level
  horizontal overflow. After the staged StockDetail pass, the visible core is
  under 1 second: desktop core ready 945 ms, mobile core ready 875 ms. Lower-page
  enriched panels finish later: desktop 1.429 s, mobile 1.366 s.
- 2026-06-19 follow-up StockDetail browser probe in
  `docs/audit/frontend_stock_detail_perf_probe_2026-06-19.json` records the
  current local production-preview sample after request-ordering and BFF cache
  changes: `h1` ready in 173 ms, coverage response in 710 ms, score response in
  836 ms, and the path graph canvas ready in 965 ms with 0 console error/warn
  logs. The separate
  `docs/audit/bff_concurrent_probe_2026-06-19.json` warm concurrent probe keeps
  8 StockDetail hot endpoints under 1 second with max latency 276.407 ms.
  History and stock overlay still arrive just after 1 second in the browser
  sample, but no longer block route identity or the path graph canvas.
- 2026-06-18 follow-up Project ULT route QA after frontend adapter fixes:
  the previously blank/crashing direct routes now render page identity:
  `/alerts`, `/admin/health`, `/project-ult/cycles`, `/project-ult/graph`,
  and `/project-ult/evidence`. The frontend now tolerates the real mvp20 BFF
  skeleton/envelope shapes for alerts, admin, cycles/formal, graph, data,
  evidence, and backtests instead of assuming the older demo mock contracts.
  Project ULT `/graph` redirects at the route layer to `/project-ult/graph`;
  Project ULT `/recommend` renders a lightweight read-only entry instead of
  waiting on the legacy `/api/recommendations/latest` mock endpoint; and
  `SystemGate` no longer blocks first paint while the initial BFF reachability
  probe is pending. `FrontEnd/ npm run check` passed after these changes.
- 2026-06-18 later frontend contract recheck: `FrontEnd/ npm run
  smoke:project-ult` now passes **43 checks** against the live mvp20 BFF after
  aligning the smoke script with the current `{data, request_id}` envelope,
  skeleton graph/read-only raw routes, and intentional 404s for upstream-only
  formal/recommendation legacy endpoints. `FrontEnd/ npm run check` still
  passes. Browser fallback timing also confirmed the route set is generally
  warm-fast, but one isolated `/pool` sample hit 1.237s before repeating at
  68/65/76/71 ms, so cold/browser-resource spikes remain a QA risk rather than
  a proven steady-state route regression.
- Browser evidence now has two scopes. The 2026-06-18
  `latest_project_ult_route_recheck` covered the broader warm direct-route set:
  `/recommend` 497 ms in the full route sequence and 82-98 ms in repeated
  `/pool -> /recommend` checks; `/project-ult/graph` 78 ms;
  `/project-ult/evidence` 75 ms; `stock/300750.SZ` 75-114 ms in repeated
  direct checks. The 2026-06-19 production preview recheck covers the built app
  route-identity path, stock-detail interaction, and mobile overflow check.
  The staged StockDetail pass keeps route identity, core score/graph data, and
  interaction under threshold; lower-page technical/path-history enrichment is
  intentionally deferred and remains above 1 second.
- 2026-06-19 route/navigation contract audit in
  `docs/audit/frontend_project_ult_navigation_2026-06-19.json` parses
  `FrontEnd/src/App.tsx` and `PROJECT_ULT_READ_ONLY_LINKS`, then cross-checks
  the source route registry against shell latency evidence. All 20 App route
  samples and all 8 Project ULT read-only navigation links are declared,
  shell-covered, and under the 1 second shell threshold; the latest shell max
  is 14.526 ms. An in-app Browser spot check also clicked
  `/project-ult/system -> /project-ult/evidence`, confirmed
  `Project ULT Evidence Console`, and saw 0 console error/warn logs. This is
  user-visible warm-path evidence, not a production build budget.
- 2026-06-19 frontend response pass: `StockDetail` no longer waits a hard
  1000 ms before starting detail-data queries, and `MarketOverview` no longer
  waits a hard 5000 ms before warming backend score queries. Both now keep a
  short defer only to let the route identity paint first. `PoolManagement`
  also no longer fans out `/score` to the entire constituent universe before
  the table is usable; it warms backend scores for the top 120 mock-ranked
  candidates and keeps local derived signals for the rest. `GraphCanvas`
  no longer rebuilds the ForceAtlas2 layout on every selected-node change, and
  `StockGraphPanel` reuses the parent `coverage` response instead of issuing a
  duplicate `/coverage` request. `FrontEnd/ npm run lint` and `FrontEnd/ npm run
  check` passed. `docs/audit/frontend_shell_latency_2026-06-19.json`
  measured all 20 Project ULT SPA shell routes under 1 second with max shell
  latency 14.526 ms, and `docs/audit/frontend_project_ult_navigation_2026-06-19.json`
  confirms all 20 App route samples plus all 8 read-only links are declared,
  shell-covered, and under threshold. `FrontEnd/` is gitignored, so these
  frontend hot-path changes are intentionally not staged by Git.
- DOCKCASE is mounted at `/Volumes/dockcase2tb`: 63G total, with a 54G
  `database_all` warehouse, 33G `股票数据`, 167,059 pruned warehouse files
  excluding rebuildable dependency folders, and 15,154 `market_data` files.
  The local Tushare warehouse has 1,240,373 raw API records and
  `runtime/hot.sqlite` has 265,709 current rows after the 2026-06-20 approved
  A-share runtime materialization execution.
- File inventory baseline: the outer repo tracks 3,456 files; the repeatable
  metadata inventory in `docs/audit/file_inventory_2026-06-19.json` currently
  counts 8,023 local operational files after pruning main caches/build outputs,
  including ignored-but-real `FrontEnd/` and `runtime/` state.
- Static code inventory in `docs/audit/code_inventory_2026-06-19.json` covers
  1,307 source files across the source-bearing roots, 328,272 total lines,
  13,660 static definitions, 8,259 imports, and 0 Python parse errors.
- Repo content-body audit in `docs/audit/repo_content_2026-06-19.json` read
  and SHA-256 fingerprinted 5,853 bounded text-file bodies, covering
  562,584,191 bytes / 19,227,954 lines with 0 read errors. It now records a
  complete `skipped_file_fingerprints` head/tail SHA-256 list for all 2,170
  skipped binary/oversized files, while retaining 100 skipped-file rows as a
  compact sample for quick review. `docs/audit/repo_binary_semantics_2026-06-19.json`
  now adds type-aware semantic classification for all 2,170 skipped files with
  0 missing files and 0 semantic errors: 1,494 PDFs / 351,040 pages, 547 Python
  bytecode files, 28 gzip streams, 32 SQLite databases / 439 schema objects,
  36 SQLite sidecars, 9 NPZ payloads, 4 pickle payloads inspected without
  loading, 2 PNGs, 10 large/non-UTF8 text files, and 8 macOS `.DS_Store` files.
- Data catalog inventory in `docs/audit/data_catalog_2026-06-19.json` read
  160,597 DOCKCASE `database_all` CSV-like headers with 0 header errors,
  sampled 160,592 first data rows, found 5 header-only/no-data-row CSV-like
  files and 0 sampled row-width mismatches, sampled 6 DockCase SQLite schemas,
  and sampled `market_data` HTML/PDF metadata. This is the raw catalog pass;
  the semantic CSV audit below skips non-business macOS AppleDouble
  `._*.csv` sidecars.
- DOCKCASE CSV file-evidence audit in
  `docs/audit/dockcase_csv_file_evidence_2026-06-19.json` now gives every
  current business CSV a file-level evidence row. The current external-disk
  pass saw 160,596 business CSV files / 37.6G, with 0 header-read errors and
  0 fingerprint errors. All 160,596 files have head/tail SHA-256 evidence
  stored in the compressed
  `docs/audit/dockcase_csv_file_evidence_2026-06-19.jsonl.gz`; the compact
  JSON keeps a 100-row sample plus summary. 160,592 files have first/tail
  data-row evidence, 4 files are header-only or no-tail-data, and 0 files show
  first/tail row-width mismatch. This is all-file evidence, not full row-level
  semantic validation.
- DOCKCASE CSV stratified semantic audit in
  `docs/audit/dockcase_csv_semantics_2026-06-18.json` now skips macOS
  AppleDouble `._*.csv` sidecars and re-groups 160,567 business CSV files into
  187 header signatures. It selected all 187 signatures and 332 files for
  bounded row sampling; 184 signatures / 329 files yielded 25,205 real rows.
  The report now records the sampling boundary explicitly: 3 selected
  signatures had no sampled rows, 160,235 CSV files were only covered at
  header/signature level because of the files-per-signature cap, and sampled
  file coverage is 0.20% of grouped CSV files. It found 0 header read errors
  plus 0 sampled row-width mismatches with head/tail sampling as of
  2026-06-18. Review signals include 230 sparse columns, 3 high-empty
  signatures, 121 invalid sampled dates, 30 invalid sampled numerics, 317
  nonstandard sampled `ts_code` values, 3 signatures with no sampled rows, 70
  stale market-date signatures, 4 future-date signatures, and
  domain-invariant signals for 326 same-file duplicate sampled grain keys, 900
  index by-symbol bundle mismatches, 2 zero-OHLC no-trade carry-forward rows,
  and 3 sampled OHLC ordering violations.
- DOCKCASE CSV full-row scanner in
  `docs/audit/dockcase_csv_full_scan_progress_2026-06-19.json` now proves the
  row-level semantic scan path on the mounted external disk and merges
  resumable shards. The current progress covers 27 contiguous shards, all
  160,596 business CSV files, and 212,621,857 rows / 4,603,398,955 cells with
  0 header-read errors, 0 row-read errors, 0 row-width mismatches, 0 shard
  overlaps, and 0 shard gaps. It found 3,990 invalid dates, 124 invalid
  numeric values, 233,330 invalid `ts_code` values, 32,038 OHLC invariant
  violations, 76,722 stale primary market-date signals, 8 future primary-date
  signals, 4,448 zero-OHLC no-trade carry-forward rows, 2,491,811 duplicate
  grain-key signals, 34,631,768 index by-symbol bundle mismatches, 15,188
  high-empty signature signals, and 1,012,704 sparse-column signals across
  sparse financial-style tables. Per-file shard
  evidence is stored in `docs/audit/dockcase_csv_full_scan*.jsonl.gz`; the
  final incremental shards are
  `docs/audit/dockcase_csv_full_scan_shard_140000_141803.jsonl.gz`,
  `docs/audit/dockcase_csv_full_scan_shard_141804_159590.jsonl.gz`, and
  `docs/audit/dockcase_csv_full_scan_shard_159591_160595.jsonl.gz`. This is
  now a completed business-CSV full-row semantic scan; remaining work is issue
  interpretation/remediation rather than row/file coverage.
- DOCKCASE semantic backlog in
  `docs/audit/dockcase_semantic_backlog_2026-06-18.json` now ranks the bounded
  CSV semantic-review remainder instead of leaving it as a generic gap:
  160,235 CSV files are still outside row-level sampling due to the
  per-signature cap, 3 header signatures have no sampled rows or empty selected
  files, and 115 signatures have sampled issues. The next passes should start
  from the backlog's `p0_no_sampled_rows`, `p1_high_issue_signatures`, and
  `p1_high_volume_unselected_files` queues.
- DOCKCASE backlog batch passes now accumulate in
  `docs/audit/dockcase_backlog_batch*.json`. The first batch deep-sampled
  signature rank 46 (`指数专题/国际主要指数`-style daily index files), matched all
  28 files for that header signature, and read 5,600 rows. The second batch in
  `docs/audit/dockcase_backlog_batch_r27_r31_2026-06-18.json` targeted ranks 27
  and 31 (`申万行业指数日行情` / `中信行业指数日行情`-style index files), matched 324
  files, and read 100 selected files / 20,000 rows. The third batch in
  `docs/audit/dockcase_backlog_batch_p0_no_rows_2026-06-18.json` targeted the
  backlog's 3 `p0_no_sampled_rows` signatures and confirmed they match 3 files
  with no sampled data rows. Across these batches the audit has matched 355
  backlog files, added 25,600 backlog rows with 0 row-width mismatches, and
  confirmed that the dominant row-level signal is index by-symbol bundle
  mismatch; rank 46 also has 28 OHLC invariant violations and 1 stale
  market-date signal, ranks 27/31 have 2 stale market-date signals, and the p0
  batch records 3 `no_sampled_rows` signals.
- A-share semantic data audit in
  `docs/audit/a_share_data_semantics_2026-06-18.json` reads real rows from 14
  representative high-value source files across stock list, daily bars, income
  statements, money flow, broker forecasts, and index bars. It loaded 40,007
  rows: daily bars and money flow are clean on the sampled symbols; stock list,
  income statements, broker forecasts, and index bars are review-class due to
  P2 sparsity/freshness/duplicate-key issues, with no sampled invalid dates,
  invalid numerics, or `ts_code` mismatches.
- AKShare CLS refresh check in
  `docs/audit/akshare_cls_refresh_2026-06-18.json` confirms the new
  `L9.media.report` / policy / competition-risk score path refreshes from the
  current signed `cls.cn /v1/roll/get_roll_list` web API after the legacy
  AKShare `stock_info_global_cls` endpoint returned 404 / timed out. The
  2026-06-19 focused `akshare-cls` retry now also emits `L9.macro.geo`, so the
  current runtime has four `Known` `MARKET:CN` sentinel rows and no missing
  dependency rows for the A-share candidate-evidence audit.
- A-share L0/source-readiness audit in
  `docs/audit/a_share_l0_source_readiness_2026-06-19.json` now turns the
  remaining 32 score-blocking gaps into concrete source routes: 16 local
  closed-loop LLM fields from financial/runtime/annual-report evidence, 12
  event/news LLM fields from runtime media/policy/competition rows, and 4
  manual design review fields. It also confirms there are **0 direct structured Tushare gaps
  remaining** for score completion, and all declared dependency dp_ids now have
  runtime rows. The report builder is covered by
  `tests/test_a_share_l0_source_readiness.py`.
- A-share candidate-evidence audit in
  `docs/audit/a_share_gap_candidate_evidence_2026-06-19.json` packages those
  32 blocking gaps into reviewable, read-only candidate inputs without writing
  `runtime/hot.sqlite` or overlay YAML. It finds 32 candidate-ready rows
  (15 local closed-loop, 1 local closed-loop with explicit grain join, 12
  event/news, and 4 governed
  manual-design candidate packages) and 0 not-ready rows. The 4 formerly
  manual-only fields now carry explicit candidate policies: bounded DCF
  assumptions, priced catalyst realization risk, flow/sentiment reflexivity,
  and valuation slope risk-off. `docs/audit/a_share_short_report_evidence_2026-06-19.json`
  still records the short-report evidence basis for the already-executed
  neutral runtime write: 14,956 DOCKCASE news HTML files scanned, 4 strict
  short-report documents present, all foreign/market-only, with 0 direct
  A-share hits. The
  `L0.price.contract_spot` candidate package includes a stock-to-industry
  grain-join policy covering 1007 mapped A-share universe rows.
  `safe_to_upsert_without_review` remains 0 here and is rechecked by the
  upsert-safety audit below. The script is covered by
  `tests/test_a_share_gap_candidate_evidence.py`.
- A-share score-field closure audit in
  `docs/audit/a_share_score_field_closure_2026-06-20.json` merges the score
  trace, candidate evidence, source-readiness report, and
  `config/data_point_roles.yaml` into one field-level closure table. It
  confirms the config and runtime spec totals both equal 256; **132 / 174**
  raw score-relevant dp_ids currently reach the final score path after the
  approved materialization execution. The remaining **21** raw blockers are all
  candidate-ready, `direct_structured_tushare_remaining=0`, and
  `safe_to_upsert_without_review_count=0`, so candidate evidence is still not
  counted as score completion. The current-MVP denominator adjustment is handled
  separately by `a_share_current_mvp_score_applicability_2026-06-20.json`.
  The script is covered by `tests/test_a_share_score_field_closure.py`.
- A-share candidate score dry-run in
  `docs/audit/a_share_candidate_score_dry_run_2026-06-19.json` validates the
  scoring bridge contract for those 32 candidate-ready blockers without
  generating reviewed values or writing `runtime/hot.sqlite`: 32 / 32 produce a
  numeric `_realtime_signal`, 32 / 32 emit realtime scoring nodes, and 32 / 32
  point at final-score targets. Bridge blockers are 0, while
  `safe_to_upsert_without_review` remains 0.
- A-share candidate upsert-safety audit in
  `docs/audit/a_share_candidate_upsert_safety_2026-06-19.json` verifies the
  runtime-write boundary for those same 32 rows. It checks 32 / 32
  candidate-ready rows, confirms all 32 are bridge-ready, classifies 32 / 32 as
  review-gated/staging-only, reports 0 blocked rows, and keeps
  `safe_to_upsert_without_review_count=0`. The safety split is now 32 ordinary
  `review_required` rows; the former deterministic neutral / NotApplicable
  cases are no longer active blockers after the bounded runtime write.
- A-share candidate staging-payload audit in
  `docs/audit/a_share_candidate_staging_payloads_2026-06-19.json` prepares the
  next review queue without production writes. It emits 32 complete staging
  envelopes with `review_status=review_required` and
  `safe_to_upsert_without_review=false`; all 32 are generator-required
  placeholders that still require governed local/event/manual candidate
  generation. No current staging payload is deterministic or bridge-validated
  as concrete, but all 32 retain the dry-run bridge contract until reviewed
  values are generated. Production writes allowed remain 0.
- A-share candidate value-contract audit in
  `docs/audit/a_share_candidate_value_contracts_2026-06-19.json` validates the
  staging envelopes before any later generator output can be trusted. It checks
  all 32 envelopes for `target_dp_id`, `score_target`, `data_status`,
  `value_json`, confidence bounds, non-empty `evidence_refs`, non-empty
  `rationale`, `review_status=review_required`, and
  `safe_to_upsert_without_review=false`; it also re-runs the production bridge
  for concrete review payloads. Current result: 32 / 32 contracts valid, 0
  invalid, 0 concrete review payloads bridge-validated, 32 placeholder
  contracts valid, and 0 production writes allowed.
- A-share spec numeric-validity audit in
  `docs/audit/a_share_spec_numeric_validity_2026-06-20.json` combines the
  field-closure, dry-run, staging, value-contract, review-manifest,
  approval-gate, and Unknown-closure evidence into the direct answer for
  whether each spec field is valid information and whether it currently reaches
  final score. Current raw evidence has **132 / 174** score-relevant dp_ids as
  numeric final-score fields (75.86%); **42** score-relevant fields do not
  currently reach final score before current-MVP applicability. Of the raw
  blocking set, **21** are actionable candidate-ready gaps, 32 remain
  candidate dry-run bridge-ready, 25 are review-ready concrete packets, 7
  remain review-gated Unknown, 0 have current production-write approvals, and
  safe unreviewed upserts remain 0. This audit
  explicitly keeps bridge-ready, review-ready, and score-complete as separate
  states. The script is covered by `tests/test_a_share_spec_numeric_validity.py`.
- A-share spec score-conversion-path audit in
  `docs/audit/a_share_spec_score_conversion_path_2026-06-20.json` follows each
  spec field through governance, numeric conversion, realtime-node emission,
  and `score_company` route probing. It checks all 256 spec fields: 174 are
  score-relevant final targets, **132** already reach the current numeric final
  score, **21** candidate payloads are numeric score-path ready, 4 current
  sample payloads can be normalized and routed by the existing code, and
  **157** fields are numeric-and-score-path ready in total. The remaining score-relevant
  unresolved set is 17 fields: 14 have real runtime values but no current
  formula/normalizer, and 3 have no current numeric input. The same report now
  overlays the review-decision evidence back onto those 17 not-ready fields:
  6 are formula-policy/peer-context review-required, 8 are verified
  governance/duplicate/data-only suppressions, 3 are verified listed-option
  universe/N/A cases, and 0 remain unclassified. Non-scoring/no-weight fields
  remain 82, and production writes remain 0. The script is covered by
  `tests/test_a_share_spec_score_conversion_path.py`.
- A-share score-conversion remediation queue in
  `docs/audit/a_share_score_conversion_remediation_queue_2026-06-19.json`
  classifies those 17 unresolved score-relevant fields before any scoring
  formula is added. Current result: 14 / 17 have direct Tushare or derived
  current inputs and 3 / 17 have no current A-share option input, but
  `safe_formula_now_count` is 0. The queue splits the next work into 6 fields
  requiring a reviewed formula policy or peer/baseline context
  (`L2.segment.revenue_share`, `L5.cf.capex`, `L6.mult.pb`, `L6.mult.pe`,
  `L6.state.industry_center`, `L7.flow.block_trade`), 8 fields that should
  stay governed/suppressed or be verified through replacement/canonical dp_ids
  (`L6.mult.ev_ebitda`, `L6.mult.mcap_fcf`, `L6.mult.peg`,
  `L6.state.expansion_compression`, `L7.mood.media_social`,
  `L7.trade.margin_short`, `L9.company.mgmt_litigation`,
  `L9.media.social_buzz`), and 3 option/IV rows requiring a real listed-option
  source universe or explicit N/A handling (`L6.priced.iv`, `L7.trade.iv`,
  `L7.trade.options_cp`). Production writes remain 0. The script is covered by
  `tests/test_a_share_score_conversion_remediation_queue.py`.
- A-share formula-policy review-packet audit in
  `docs/audit/a_share_formula_policy_review_packets_2026-06-19.json` converts
  the 6 formula-policy/peer-context remediation rows into explicit review
  packets without selecting Known values. All 6 rows have current inputs and
  all 6 packet contracts validate; 3 valuation rows are tied to an already
  ready replacement path through `L6.state.peer_compare`, while 3
  business-semantics rows still need reviewed direction/normalizer policy
  (`capex_intensity_and_trend`, `segment_concentration_and_strategy`,
  `block_trade_directional_flow`). Direct formula ready remains 0,
  Known-draft sufficient remains 0, safe unreviewed upserts remain 0, and
  production writes remain 0. The script is covered by
  `tests/test_a_share_formula_policy_review_packets.py`.
- A-share governance-suppression verification in
  `docs/audit/a_share_governance_suppression_verification_2026-06-19.json`
  verifies the 8 governed/duplicate remediation rows. It confirms 8 / 8 are
  intentionally suppressed by the current signal path, 6 / 8 have a
  replacement/canonical/transitive scoring path ready, 2 valuation rows are
  suppressed under peer-context, and 3 data-only rows remain available as
  evidence without a safe directional formula. Requires-governance-review is
  0 for the suppression decision itself, while safe unreviewed upserts and
  production writes remain 0. The script is covered by
  `tests/test_a_share_governance_suppression_verification.py`.
- A-share option-universe / N/A verification in
  `docs/audit/a_share_option_universe_na_verification_2026-06-19.json`
  verifies the 3 option/IV remediation rows (`L6.priced.iv`, `L7.trade.iv`,
  `L7.trade.options_cp`). All 3 have no current A-share option-chain input,
  all 3 require a legitimate listed-option universe or licensed underlying
  mapping before a `Known` value can be emitted, and all 3 may only resolve to
  reviewed `NotApplicable` / `Unavailable` outside that universe. It also
  confirms the generic collector intentionally excludes option dp_ids and the
  existing Futu option implementation has 3 HK/US-only target filters. Known
  values allowed now remain 0, verification contracts validate 3 / 3, and
  production writes remain 0. The script is covered by
  `tests/test_a_share_option_universe_na_verification.py`.
- A-share candidate generation-queue audit in
  `docs/audit/a_share_candidate_generation_queue_2026-06-19.json` converts the
  remaining placeholder rows into explicit generator work without producing
  approved/runtime-writable business values. It packages 32 queued tasks with
  valid placeholder contracts: 12 event-LLM candidates, 16 local closed-loop
  candidates, and 4 manual-policy candidates. The 2 deterministic review
  payloads are skipped from the generator queue, and production writes allowed
  remain 0.
- A-share L0 source-readiness audit in
  `docs/audit/a_share_l0_source_readiness_2026-06-19.json` confirms the 32
  remaining blocking rows no longer have a direct structured Tushare route left:
  28 are P2 LLM/web extraction rows, 4 are P3 manual-review rows, 12 route to
  event/news extraction, 16 route to local closed-loop extraction, and 4 route
  to manual-design review. It also confirms 17 dependency dp_ids have runtime
  rows available and 0 dependency dp_ids are missing runtime rows.
- A-share short-report evidence scan in
  `docs/audit/a_share_short_report_evidence_2026-06-19.json` scans 14,956 local
  market HTML files with 0 parse errors. It finds 4 strict short-report
  documents, but 0 direct A-share short-report documents and 0 direct A-share
  `ts_code` matches; the candidate evidence is therefore ready only as
  foreign/market-context evidence, not as a direct A-share score value.
- A-share non-manual candidate readiness audit in
  `docs/audit/a_share_non_manual_candidate_readiness_2026-06-19.json` checks
  the 28 local/event generator tasks that remain after excluding manual-policy
  work. All 28 have material known dependency coverage, all 28 placeholder and
  output contract shapes validate, and all 28 bridge probes can reach
  final-score-ready realtime nodes. It still emits 0 deterministic Known drafts:
  these rows require governed local/event LLM review to assign business
  direction and magnitude. Production writes allowed remain 0.
- A-share event-text policy draft pilot in
  `docs/audit/a_share_event_text_policy_drafts_2026-06-19.json` checks the 12
  `event_text_classification_required` tasks. After consuming the local
  market-doc review packet bundle, it emits 10 review-only Known drafts
  (`L0.compete.price_war`, `L0.compete.share_concentration`,
  `L0.policy.access_license`, `L0.policy.regulation`,
  `L0.policy.subsidy`, `L0.policy.tax_trade`, `L0.tech.ai_automation`,
  `L0.tech.breakthrough`,
  `L8.shock.black_swan`, and `L8.shock.supply_break`), leaves 2 Unknown,
  validates 12 / 12 draft contracts, flags 0 invalid draft contracts,
  bridge-validates 10 / 10 Known drafts into final-score targets, and keeps safe
  upsert / production writes at 0.
- A-share event-text classification input bundle in
  `docs/audit/a_share_event_text_classification_inputs_2026-06-19.json`
  packages the 12 event-text classification input rows into classifier/reviewer inputs.
  All 12 are input-ready at title level, with 78 headline inputs and 8 unique
  titles, but 0 packets include full article text and 0 are classified into
  Known review packets. Production writes remain 0.
- A-share event-text preclassification screen in
  `docs/audit/a_share_event_text_preclassification_screen_2026-06-19.json`
  applies deterministic keyword checks to those title-level packets without
  upgrading any target field. It screens all 12 packets, finds 3 target-keyword
  hit packets, 11 A-share transmission keyword-hit packets, and 2 packets with
  both; direct Known candidates remain 0, all 12 stay review-required, and
  production writes remain 0.
- A-share event-text sufficiency gate in
  `docs/audit/a_share_event_text_sufficiency_gate_2026-06-19.json` tightens the
  preclassification result by requiring target evidence and usable A-share
  transmission to connect at headline level or through stronger text. Current
  result: 3 packets have target headlines, 11 packets only have broad-market
  China A50/futures transmission context, 0 packets have same-headline direct
  target + transmission evidence, 0 title signals are sufficient for classifier
  promotion, and production writes remain 0.
- A-share event-text URL/body fetchability audit in
  `docs/audit/a_share_event_text_url_fetchability_2026-06-19.json` fetches the
  8 unique CLS article URLs referenced by the event-text inputs. All 8 URLs
  return primary text and all 12 packets have body text available, but only 3
  packets have body target hits, 0 packets have direct A-share/industry/trade
  transmission hits, 0 body signals are sufficient for classifier promotion,
  and production writes remain 0.
- A-share event-text Unknown source-options audit in
  `docs/audit/a_share_event_text_unknown_source_options_2026-06-19.json`
  reviews the 2 event-text rows still Unknown after local market-doc policy
  promotion. Both have classification inputs and body text available, 0 have
  target-event evidence, 0 have direct A-share transmission, both only have
  broad-market transmission context, 0 are classifier-ready, both still need
  target-event evidence, 0 need direct A-share transmission, and auto Known /
  production writes remain 0.
- A-share event-text market-doc evidence scan in
  `docs/audit/a_share_event_text_market_doc_evidence_2026-06-19.json` scans
  14,956 DOCKCASE market HTML files for those 12 first-pass event-text rows. It
  finds market-document target evidence for all 12 rows, same-sentence
  target/direct-transmission review candidates for 11 rows, leaves
  `L0.compete.new_entrant` still needing a direct transmission link, and keeps
  auto Known / production writes at 0.
- A-share event-text market-doc review packet bundle in
  `docs/audit/a_share_event_text_market_doc_review_packets_2026-06-19.json`
  packages those market-doc hits into 12 conservative classifier/reviewer
  inputs. It marks 11 packets as market-doc review-ready, keeps
  `L0.compete.new_entrant` blocked on a direct-transmission link, retains 53
  candidate examples, validates 12 / 12 packet contracts, and still allows 0
  auto Known / production writes.
- A-share local structured policy draft pilot in
  `docs/audit/a_share_local_structured_policy_drafts_2026-06-19.json` checks
  the 10 `local_structured_llm_required` tasks. It emits 6 review-only Known
  draft packets (`L0.cost.cac`, `L0.cost.labor`, `L0.demand.terminal`,
  `L0.price.contract_spot`, `L0.supply.capacity`, and
  `L0.supply.chain_eff`), leaves 4 fields Unknown because they need
  lease/detail, purchase-frequency, TAM/share, or ASP volume/mix review,
  validates 10 / 10 draft contracts, flags 0 invalid draft contracts,
  bridge-validates 6 / 6 Known drafts, and
  keeps safe upsert / production writes at 0.
- A-share local structured Unknown source-options audit in
  `docs/audit/a_share_local_structured_unknown_source_options_2026-06-19.json`
  reviews those 4 Unknown rows. All 4 have runtime dependencies ready, 0 have
  a direct existing structured source ready, 4 have overlay/source hints, all
  4 need new mapping or text extraction, 0 need reviewed pass-through policy,
  0 are partial Known unlock candidates, 0 are auto Known candidates, and
  production writes remain 0.
- A-share local structured source-candidates audit in
  `docs/audit/a_share_local_structured_source_candidates_2026-06-19.json`
  checks those 4 Unknown rows against the current DOCKCASE/Tushare CSV semantic
  catalog. It finds 0 direct Known-ready rows, 2 rows with review/source
  candidates, 1 review candidate match (`use_right_asset_dep` for lease burden),
  4 supporting candidate matches (`bz_item`, `bz_sales`, `bz_cost`, and
  `bz_profit` for product mix / ASP numerator context), 1 empty candidate match
  (`fa_fnc_leases`), 2 rows with no direct catalog source, 407 false-positive
  field/path matches excluded, and 0 production writes.
- A-share local structured source-review packet bundle in
  `docs/audit/a_share_local_structured_source_review_packets_2026-06-19.json`
  packages those 4 Unknown rows into reviewer-facing source packets. It marks
  1 lease/rent proxy packet review-ready, 1 ASP packet as needing quantity or a
  governed price-index source, and 2 packets as requiring external business
  sources. Direct Known-ready packets remain 0, formula-ready packets remain 0,
  4 / 4 packet contracts are valid, and production writes remain 0.
- A-share local structured-text policy draft pilot in
  `docs/audit/a_share_local_structured_text_policy_drafts_2026-06-19.json`
  checks the 3 `local_structured_text_llm_required` tasks. It emits 3
  review-only Known draft packets: `L0.demand.user_count` from strict
  answer-side customer/user/order/volume QA evidence, `L0.supply.channel_service`
  from QA/channel-service text evidence, and `L0.price.discount` from
  company-answer product-price-pressure evidence. It validates 3 / 3 draft
  contracts, flags 0 invalid draft contracts, bridge-validates 3 / 3 Known
  drafts, and keeps safe upsert / production writes at 0.
- A-share local structured-text Unknown source-options audit in
  `docs/audit/a_share_local_structured_text_unknown_source_options_2026-06-19.json`
  reviews 0 remaining Unknown rows because all three structured-text rows now
  have review-only Known draft packets. It records 0 runtime-dependency rows,
  0 QA/IR rows, 0 text-classification requirements, 0 auto Known candidates,
  and 0 production writes.
- A-share local single-dependency policy draft pilot in
  `docs/audit/a_share_local_single_dependency_policy_drafts_2026-06-19.json`
  checks the 3 local single-dependency tasks split out by the non-manual
  readiness audit. It emits 2 review-only Known draft packets
  (`L0.price.pricing_power` and `L0.supply.inventory`), leaves
  `L0.demand.replacement` Unknown because revenue alone cannot identify a
  replacement cycle, validates 3 / 3 draft contracts, flags 0 invalid draft
  contracts, bridge-validates 2 / 2 Known drafts, and keeps safe upsert /
  production writes at 0.
- A-share local single-dependency Unknown source-options audit in
  `docs/audit/a_share_local_single_dependency_unknown_source_options_2026-06-19.json`
  reviews the remaining `L0.demand.replacement` row. Its `L5.is.revenue`
  dependency is ready, but 0 direct replacement-cycle sources are ready; it
  records 1 overlay/source hint and 1 overlay lifecycle-context candidate. The
  bounded overlay scan found 205 A-share `L3.product.lifecycle=Known` context
  nodes, but `L0.demand.replacement` itself remains 0 Known / 1,646 Unknown, so
  lifecycle or replacement-cycle evidence plus reviewed policy is still
  required. It now creates 1 blank lifecycle-policy review template with 1 / 1
  contract valid, 0 invalid, 1 blank pending, and 0 input-ready templates. The
  template is a reviewer handoff only: Known-draft sufficient rows remain 0,
  approval-ready rows remain 0, auto Known candidates remain 0, and production
  writes remain 0.
- A-share manual-policy draft pilot in
  `docs/audit/a_share_manual_policy_draft_candidates_2026-06-19.json` consumes
  the 4 queued manual-policy tasks and produces review-only drafts without
  runtime writes: all 4 become Known draft review packets
  (`L6.mult.dcf`, `L6.priced.realization_risk`, `L7.reflex.tag`, and
  `L8.val.slope_risk_off`) and bridge-validate through the production scoring
  path. `L6.mult.dcf` now carries an explicit standard-assumption DCF draft
  (`discount_rate`, `terminal_growth`, `forecast_horizon_years`, and
  `normalized_fcf_basis`) for review. All 4 draft contracts validate, invalid
  draft contracts are 0, safe-to-upsert-without-review remains 0, and production
  writes allowed remain 0.
- A-share manual-policy Unknown source-options audit in
  `docs/audit/a_share_manual_policy_unknown_source_options_2026-06-19.json`
  now has 0 remaining manual-policy Unknown rows after the DCF review draft.
  It records 0 dependency packs needing assumption review, 0 required
  assumptions, 0 reviewed-policy blockers, 0 auto Known candidates, and keeps
  production writes at 0.
- A-share review-staging manifest in
  `docs/audit/a_share_review_staging_manifest_2026-06-19.json` merges all 32
  current score-blocking candidate rows into one canonical review queue. It
  finds 32 / 32 rows have review entries, with 25 concrete review-ready packets
  (25 `Known`) and 7 review-gated `Unknown` packets.
  All 32 contracts validate, all 25 concrete packets bridge to final-score
  targets, missing review entries are 0, invalid contracts are 0, safe
  auto-upsert is 0, production writes are 0, and approved runtime writes are 0.
- A-share review-approval gate in
  `docs/audit/a_share_review_approval_gate_2026-06-19.json` verifies the
  separate approval boundary after review staging. It checks 32 canonical
  review rows, requires explicit approval for the 25 concrete packets, sees the
  2 historical deterministic approval records as stale/rejected for the current
  queue, leaves all 25 concrete packets missing approval, approves 0 runtime
  writes into the current read-only write plan, produces 0 write-plan entries,
  keeps 7 `Unknown` packets not approvable, and keeps safe auto-upsert /
  production writes at 0.
- A-share deterministic runtime-approval audit in
  `docs/audit/a_share_review_approvals_2026-06-19.json` hard-gates only the 2
  deterministic staging payloads that can be approved without subjective
  review: `L9.media.short_report` stays neutral `Known` because the dedicated
  A-share short-report scan found 0 direct hits, and `L7.trade.gamma` is
  `NotApplicable` / neutral for A-share single stocks with no listed options.
  It validates 2 / 2 approval contracts, leaves 32 non-deterministic manifest
  rows unapproved, and performs no `realtime_current` or production score
  mutation.
- A-share completion next-action queue in
  `docs/audit/a_share_completion_next_actions_2026-06-19.json` converts the
  32 remaining actionable score gaps into explicit next work: 25 packets still
  need human runtime-write approval, 0 packets are runtime-write-plan-ready
  in the current queue, and 7 packets still need Unknown
  resolution. The Unknown queue is 2 event-text classifications, 4 local
  structured mappings, 0 structured-text extractions, 1 single-dependency
  policy, and 0 manual DCF-assumption reviews. It emits 25 incomplete approval
  templates for review convenience, approves 0 runtime writes into a read-only
  write plan, finds 0 approval payload hash mismatches, and allows 0
  production writes.
- A-share Unknown closure matrix in
  `docs/audit/a_share_unknown_closure_matrix_2026-06-19.json` turns the 7
  review-gated Unknown packets into explicit closure routes. All 7 routes are
  assigned and 0 routes are missing: 2 event-text classifications, 4 local
  structured mappings, 0 structured-text extractions, 1 single-dependency
  policy, and 0 manual assumption reviews. It finds 3 rows with source
  candidates, 0 formula-ready rows, 0 auto Known-ready rows, 0 approval-ready
  Unknown rows, 7 / 7 closure contracts valid, and 0 production writes.
- A-share Unknown acquisition backlog in
  `docs/audit/a_share_unknown_acquisition_backlog_2026-06-19.json` converts
  those 7 Unknown closure rows into concrete source-acquisition tasks: 2
  DOCKCASE market-doc deep searches, 2 local structured formula-source tasks,
  and 3 external/text business-metric tasks. It records 3 tasks with existing
  candidate evidence, 1 task with runtime overlay hints, 6 tasks requiring
  web/external or deeper source acquisition, 7 LLM extraction/classification
  tasks, 0 formula-ready tasks, 0 auto Known-ready tasks, 0 approval-ready
  tasks, 7 / 7 valid task contracts, and 0 production writes.
- A-share Unknown market-doc acquisition candidate audit in
  `docs/audit/a_share_unknown_market_doc_acquisition_candidates_2026-06-19.json`
  executes the 2 event-document acquisition tasks against 14,956 local DOCKCASE
  market HTML files with 0 read errors. It finds 2 rows with review candidates:
  5 new-entrant window candidate documents, 6 new-entrant review candidate
  snippets, 34 substitute-tech same-sentence candidate documents, 3
  substitute-tech clean-risk review candidate snippets, 9 weak candidates, 34
  rejected candidates, 0 Known-draft-sufficient rows, and 0 production writes.
- A-share Unknown event-evidence adjudication audit in
  `docs/audit/a_share_unknown_event_evidence_adjudication_2026-06-19.json`
  reviews the retained local event-document candidates before they can be
  treated as valid score information. It adjudicates 2 event Unknown rows and
  14 retained candidate examples, accepts 0, rejects or marks ambiguous 14,
  keeps both rows Unknown, finds 0 Known-draft-sufficient rows, validates 2 / 2
  adjudication contracts, and allows 0 production writes.
- A-share Unknown event strict-source gate in
  `docs/audit/a_share_unknown_event_strict_source_gate_2026-06-19.json`
  reruns a narrower source gate for those 2 event Unknown rows across 14,956
  local DOCKCASE market HTML files with 0 read errors. It finds 11 strict
  candidates, including 8 strict review candidates and 3 rejected contexts, and
  both rows now have review candidates. These candidates remain
  reviewer/classifier inputs only: classifier-ready, Known-draft-sufficient,
  approval-ready, runtime writes, and production writes are all 0, so both rows
  remain Unknown.
- A-share Unknown event strict-review packet audit in
  `docs/audit/a_share_unknown_event_strict_review_packets_2026-06-19.json`
  packages those 8 strict review candidates into source-quality/context review
  packets. It marks 2 low-confidence community/forum leads as requiring
  primary-source confirmation, deterministically rejects 6 secondary-newswire
  candidates as false-positive, foreign/macro, overcapacity, or
  opportunity/import-shift contexts, validates 8 / 8 packet contracts, and keeps
  classifier-ready, Known-draft-sufficient, approval-ready, runtime writes, and
  production writes at 0.
- A-share Unknown event primary-source confirmation audit in
  `docs/audit/a_share_unknown_event_primary_source_confirmation_2026-06-19.json`
  checks the remaining 2 low-confidence event packets against 14,956 local
  DOCKCASE market HTML files with 0 read errors. It finds 12 local candidates,
  but all are supporting-context-only; 0 are local high-quality confirmation
  candidates, 0 rows become classifier-ready, 0 rows become
  Known-draft-sufficient, and 0 production writes are allowed. The two event
  rows still need external/primary-source confirmation or a governed
  NotApplicable/Unavailable resolution.
- A-share Unknown event external-source confirmation audit in
  `docs/audit/a_share_unknown_event_external_source_confirmation_2026-06-19.json`
  packages the 2 remaining event Unknown rows into 6 external public-source
  cards: 2 external confirmation candidates and 4 supporting-context cards. It
  now also emits 2 classifier input candidate packets that bundle source IDs,
  required labels, and guardrails for review. Both candidate-packet contracts
  are valid, 0 are invalid, both have primary source coverage, and the packet
  set carries 12 required labels plus 6 guardrails. It also emits 2 blank
  classifier-review templates; both template contracts are valid, both remain
  blank-pending, and 0 template inputs are ready. They are still not
  classifier-ready: 0 classifier input candidates are ready, 2 require review,
  and classifier-ready, Known-draft-sufficient, approval-ready, runtime writes,
  and production writes all remain 0. These cards and templates are review
  inputs for event fit, direct A-share transmission, direction, and bounded
  magnitude before any Known/NotApplicable packet can enter the approval gate.
- A-share Unknown local formula acquisition candidate audit in
  `docs/audit/a_share_unknown_local_formula_acquisition_candidates_2026-06-19.json`
  executes the 2 local structured formula-source tasks for rent and product ASP.
  Both tasks have ready runtime dependencies and all 6 sampled DOCKCASE CSV
  files exist with 0 read errors, but only candidate numerators are present:
  rent has `use_right_asset_dep` samples while direct lease payment is empty,
  and ASP has `bz_item/bz_sales/bz_profit/bz_cost` samples while quantity or
  price-index inputs are absent. It keeps 0 / 8 formula input groups ready, 0
  formula-ready rows, 0 Known-draft-ready rows, 2 / 2 contracts valid, and 0
  production writes.
- A-share Unknown local formula review-packet audit in
  `docs/audit/a_share_unknown_local_formula_review_packets_2026-06-19.json`
  packages those 2 local formula rows into the stricter formula-probe gate. It
  confirms both rows have candidate numerators, but 0 rows have direct
  denominators, 1 row now has a runtime revenue-denominator candidate and
  candidate formula shape (`use_right_asset_dep / L5.is.revenue`) for
  `L0.cost.rent`, plus 1 review-only formula-policy draft candidate for that
  rent proxy. It also records 1 row with broad CPI/PPI price-index context and
  a candidate price-context shape for `L0.price.product_asp`. It now also emits
  1 blank formula-policy review template for rent and 1 blank price-context
  review template for ASP; both template contracts are valid and both remain
  blank-pending. The rent draft still requires proxy-semantics,
  denominator-policy, and cap/floor review; the ASP evidence is context only.
  Therefore 0 rows have direct quantity or governed product price-index inputs,
  0 have reviewed formula policy, 0 are formula-input-ready, 0 have available
  score formula probes, 0 bridge into final-score-ready packets, 0 are
  Known-draft-sufficient or approval-ready, 2 / 2 review contracts are valid,
  and production writes remain 0. This keeps rent and product ASP from being
  counted as valid numeric score information just because partial local source
  evidence exists.
- A-share local formula source-capability audit in
  `docs/audit/a_share_local_formula_source_capability_2026-06-19.json` checks
  the current Tushare/DOCKCASE inventory against the remaining local formula
  blockers. It runs 8 source checks across rent and product ASP, finds 6 checks
  with source candidates, 1 header-available-but-sample-empty direct lease
  field (`fa_fnc_leases`), 3 context/proxy checks, 3 review-policy-required
  checks, and 1 external/text-required check. It resolves 0 formula blockers
  from current sources, leaves 0 rows formula-ready after the source scan,
  emits 0 formula probes, and keeps Known / approval / production-write counts
  at 0. This is the current boundary for "what existing Tushare/DOCKCASE can
  do" before annual-report, exchange Q&A, governed price-index, or human policy
  review is needed.
- A-share Unknown external business metric acquisition audit in
  `docs/audit/a_share_unknown_external_business_metric_acquisition_2026-06-19.json`
  executes the 3 external/text business-metric tasks for frequency,
  penetration, and replacement demand. All 3 have ready runtime dependencies
  and replacement has 7 overlay hints. The stock-overlay scan also checks 1,646
  A-share overlay files and finds 2 rows with adjacent overlay business-context
  candidates: 527 Known context nodes in total, split into 166 frequency-context
  nodes and 361 penetration-context nodes. The direct L0 fields are still not
  ready: frequency has 0 Known / 1,646 Unknown direct nodes, penetration has 0
  Known / 1,646 Unknown direct nodes, and the audit still finds 0 direct
  business metric sources. Therefore 12 / 12 business metric input groups remain
  not ready, 3 rows still require external/text source evidence, 238 false
  positives are excluded, 0 rows are metric-ready, 0 rows are Known-draft-ready,
  3 / 3 contracts are valid, and 0 production writes are allowed.
- A-share Unknown external business metric market-doc candidate audit in
  `docs/audit/a_share_unknown_external_business_metric_market_doc_candidates_2026-06-19.json`
  scans the same 3 external/text business-metric tasks against 14,956 local
  DOCKCASE market HTML files with 0 read errors. It finds review candidates for
  all 3 rows: 178 candidate documents, 99 review candidates, 49 numeric review
  candidates, 50 textual review candidates, 82 weak candidates, and 72 rejected
  candidates. These are reviewer inputs only: 0 rows are Known-draft-sufficient,
  0 rows are metric-ready, 3 / 3 contracts are valid, and 0 production writes
  are allowed.
- A-share Unknown external business metric review-packet bundle in
  `docs/audit/a_share_unknown_external_business_metric_review_packets_2026-06-19.json`
  converts all 99 retained review candidates into candidate-level packets
  across the 3 rows: 49 numeric packets, 50 textual packets, 99 packets with
  scope candidates, 70 with denominator candidates, 36 with period candidates,
  and 49 with unit candidates. Every packet still keeps at least one missing
  field such as denominator, period, unit, bounds, or formula policy; 0 packets
  are metric-ready, 0 are Known-draft-sufficient, 99 / 99 contracts are valid,
  and 0 production writes are allowed.
- A-share Unknown external business metric readiness queue in
  `docs/audit/a_share_unknown_external_business_metric_readiness_queue_2026-06-19.json`
  prioritizes those 99 packets by missing-field blockers: 18 are P0
  formula-policy-only candidates, 52 are P1 period/unit-required candidates,
  and 29 are P2 denominator-required candidates. Across all packets, 29 still
  miss a denominator/normalizer, 63 miss period, 50 miss unit, and all 99 still
  miss reviewed bounds and formula policy. It keeps 0 metric-ready packets, 0
  Known-draft-sufficient packets, and 0 production writes.
- A-share Unknown external business metric policy-draft bundle in
  `docs/audit/a_share_unknown_external_business_metric_policy_drafts_2026-06-19.json`
  converts the 18 P0 packets into review-only formula-policy draft packets: 1
  frequency draft and 17 penetration drafts. It emits 18 value JSON templates
  and 18 formula-policy review tasks, and now packages all 18 into blank policy
  review templates with 18 / 18 template contracts valid, 0 invalid,
  18 blank pending, and 0 input-ready templates. It deliberately selects no
  `raw_value`; metric-ready drafts remain 0, Known-draft-sufficient drafts
  remain 0, 18 / 18 policy contracts are valid, and production writes remain 0.
- A-share Unknown external business metric value-candidate adjudication in
  `docs/audit/a_share_unknown_external_business_metric_value_candidates_2026-06-19.json`
  screens those 18 P0 policy drafts before they can be treated as valid
  numeric information. It finds 9 rows with candidate value tokens, 13
  candidate value tokens, and 31 rejected numeric tokens; only 6 rows enter a
  review shortlist, 3 are scope-rejected, 9 have no scoreable numeric
  candidate, 18 / 18 contracts are valid, and metric-ready / Known /
  production-write counts remain 0.
- A-share Unknown external business metric value-review packet audit in
  `docs/audit/a_share_unknown_external_business_metric_value_review_packets_2026-06-19.json`
  converts those 6 shortlist rows into review-only formula packets. It emits 8
  candidate value options, and all 8 bridge-probe into the final-score target
  if later approved, but it selects 0 raw values, emits 0 selected value JSONs,
  keeps metric-ready / Known / approval-ready / production-write counts at 0,
  and validates 6 / 6 value-review contracts.
- A-share Unknown business-metric value-selection gate in
  `docs/audit/a_share_unknown_business_metric_value_selection_gate_2026-06-19.json`
  checks frequency, penetration, and replacement after value-review packets.
  Penetration has 6 review packets / 8 candidate value options / 8
  bridge-ready options and now has 1 reviewer-facing value-policy draft-ready
  row with 1 proposed value JSON. It still needs reviewer value selection,
  bounds, formula policy, issuer/industry applicability, and approval before it
  can become Known. Frequency and replacement remain source-metric-missing. The
  gate marks 0 generic value-selection-review rows, auto-selects 0 values,
  emits 0 selected value JSONs, marks 0 Known-draft-sufficient rows, validates
  3 / 3 selection contracts, and allows 0 production writes.
- A-share approval review packet bundle in
  `docs/audit/a_share_approval_review_packets_2026-06-19.json` extracts the 25
  concrete review-ready packets into a focused reviewer bundle. It includes 25
  `Known` packets, 0 `NotApplicable` packets, 25 final-score-target-ready
  bridge checks, 25 payload hashes, 25 incomplete approval templates, validates
  25 / 25 approval template contracts with 0 invalid templates, skips 0
  concrete rows for missing bridge/contract readiness, finds 0 approval payload
  hash mismatches, leaves 25 approvals missing, approves 0 runtime writes into
  a read-only write plan, and keeps production writes at 0.
- A-share approval-packet risk-review audit in
  `docs/audit/a_share_approval_packet_risk_review_2026-06-19.json` prioritizes
  those 25 packets before any approval record is created. It marks 6 structured
  local-dependency packets as strict bulk-review candidates, 1 structured-text
  packet as a borderline source-text sample-check candidate, and 18 packets as
  individual-review required: 8 event/text evidence packets, 4 structured proxy
  packets, and 6 policy / non-fundamental target packets. It finds 0
  contract-fix blockers, allows 0 auto approvals, allows 0 runtime writes, and
  allows 0 production writes.
- A-share bulk-review approval-candidate audit in
  `docs/audit/a_share_bulk_review_approval_candidates_2026-06-19.json` extracts
  the next reviewer batch from the risk-review report. It prepares 7 draft
  approval templates: 6 strict bulk structured candidates
  (`L0.cost.cac`, `L0.cost.labor`, `L0.price.pricing_power`,
  `L0.supply.capacity`, `L0.supply.chain_eff`, `L0.supply.inventory`) and 1
  borderline source-text sample-check candidate (`L0.supply.channel_service`).
  All 7 draft contracts validate, but the drafts intentionally keep
  `approval_status=""`, blank reviewer/timestamp fields, and
  `risk_acknowledged=false`; therefore auto approvals, runtime writes, and
  production writes all remain 0.
- A-share bulk-review source-sample audit in
  `docs/audit/a_share_bulk_review_source_samples_2026-06-19.json` verifies
  the reviewer evidence bundle for those 7 bulk/borderline candidates. It
  finds 7 / 7 source reports, 7 / 7 source rows, 7 / 7 source payload matches,
  7 / 7 complete evidence refs, 7 / 7 blank approval drafts still valid, 1 / 1
  borderline source-text sample ready, and 7 / 7 reviewer packets complete.
  It still allows 0 auto approvals, 0 runtime writes, and 0 production writes.
- A-share event approval source-sample audit in
  `docs/audit/a_share_event_approval_source_samples_2026-06-19.json` verifies
  the local evidence chain for the 10 event-text approval packets. It finds 10
  / 10 source reports, 10 / 10 source rows, 10 / 10 source payload matches, 10
  / 10 market-doc review packets, 10 / 10 market-doc review refs complete, and
  48 / 48 DOCKCASE news docs readable. All 10 rows have keyword evidence ready,
  all 10 event-evidence review templates validate, and all 10 reviewer packets
  are traceable; the templates remain blank/pending, so auto approvals, runtime
  writes, and production writes stay at 0.
- A-share individual-review source-sample audit in
  `docs/audit/a_share_individual_review_source_samples_2026-06-19.json`
  verifies the remaining non-bulk reviewer packets: 4 structured proxy reviews
  and 6 policy / non-fundamental score-target reviews. It covers 4 manual-policy
  packets, 2 event policy packets, and 4 structured proxy packets; all 10 source
  payloads match, all 10 evidence-ref sets are complete, 2 structured-text sample
  rows are ready, 2 event policy packets link back to complete event source
  samples, and 10 / 10 individual review templates validate. All 10 templates
  remain blank/pending, so auto approvals, runtime writes, and production writes
  stay at 0.
- A-share approval source-sample coverage gate in
  `docs/audit/a_share_approval_source_sample_coverage_2026-06-19.json`
  consolidates the bulk, event, and individual source-sample audits across all
  25 currently missing approval packets. It confirms 25 / 25 supported routes,
  25 / 25 source samples found, 25 / 25 reviewer packets complete, 25 / 25
  payload matches, 25 / 25 source-sample review templates valid, 25 / 25 blank
  approval templates valid, and 25 / 25 approval inputs ready. The route split is
  7 bulk, 8 event, and 10 individual packets; unsupported risk classes, approval
  inputs not ready, runtime writes, and production writes all remain 0.
- A-share approval target-scope readiness audit in
  `docs/audit/a_share_approval_target_scope_readiness_2026-06-20.json`
  checks whether those 25 approval-ready packets would become runtime-safe after
  approval alone. It confirms 25 / 25 final-score-ready packets and 25 / 25
  complete source-sample reviewer packets, but the only existing runtime
  target-scope policies cover `L7.trade.gamma` and `L9.media.short_report`.
  None of the 25 approval packets are covered by those policies or carry
  explicit target scopes, so all 25 still require target-scope policy: 19 need
  per-stock value materialization and 6 need market/event scope policy. Runtime
  materialization-ready packets, approval-only-safe runtime writes, and
  production writes all remain 0.
- A-share approval materialization plan audit in
  `docs/audit/a_share_approval_materialization_plan_2026-06-20.json` refines
  that blocker into execution-shaped work. It checks 25 approval packets against
  the current 1,641 configured A-share tickers, identifies **11** runtime
  materialization-ready plans (7 direct structured formulas, 1 structured grain
  join, and 3 text-evidence subset plans), and keeps 14 market/event
  scope-policy packets out of runtime writes. Unsupported materialization
  policies remain 0, and production writes remain 0.
- A-share approval materialization batch-plan audit in
  `docs/audit/a_share_approval_materialization_batch_plan_2026-06-20.json`
  packages those 11 ready plans into controlled, review-only runtime batch
  plans. It validates 11 / 11 batch-plan contracts, plans **11,006** candidate
  `realtime_current` UPSERT rows, classifies **1,011** as inserts, 0 as
  updates, and **9,995** as existing rows requiring backup/hash-compatible
  verification, keeps all 11 batch plans review-required, approves 0 batch
  plans at this read-only step, attempts 0
  runtime writes, and allows 0 production writes.
- A-share approval materialization Codex batch-review audit in
  `docs/audit/a_share_approval_materialization_batch_codex_review_2026-06-20.json`
  independently verifies those 11 materialization batch-plan hashes, row-set hashes,
  per-row score bounds, bridge-signal conversion, insert/update/backup counts,
  and rollback contracts. It approves 11 / 11 batch plans, rejects 0,
  emits 11 approval records, covers and approves 11,006 planned UPSERT rows
  (1,011 inserts, 0 updates, 9,995 existing rows requiring backup), attempts 0
  runtime writes, and allows 0 production writes.
- A-share approval materialization batch approval-gate audit in
  `docs/audit/a_share_approval_materialization_batch_approval_gate_2026-06-20.json`
  hash-binds those 11 batch plans to the Codex approval records. It sees
  11 approval records, requires 11 approvals, misses 0, rejects 0, approves 11
  batch plans, emits 11 still-valid blank templates for traceability,
  covers and approves the same 11,006 planned UPSERT rows, allows 11 runtime
  batch-plan gates, and allows 0 production writes.
- A-share approval materialization execution-preflight audit in
  `docs/audit/a_share_approval_materialization_batch_execution_preflight_2026-06-20.json`
  is the first-run mutation gate for the approved runtime DB state. The paired
  execution audit in
  `docs/audit/a_share_approval_materialization_batch_execution_2026-06-20.json`
  ran `--execute`, created a SQLite backup, inserted 1,011 rows, verified all
  11,006 planned rows after the transaction, and reported 0 verification
  errors. The current read-only post-execution review in
  `docs/audit/a_share_materialization_execution_review_2026-06-20.json`
  rechecks the backup/current DB pair, reports 0 current value-contract errors,
  and records the historical 9,995 timestamp-only no-op refreshes that are now
  suppressed by the execution script for future runs.
- A-share Unknown penetration value-priority audit in
  `docs/audit/a_share_unknown_penetration_value_priority_2026-06-19.json`
  narrows the closest Unknown business-metric blocker (`L0.demand.penetration`).
  It ranks 6 value-review packets / 8 bridge-ready formula probes into 1 P1
  preferred source-scope review, 1 P2 industry-scope review, 2 P3
  forecast/assumption reviews, and 2 P3 low-confidence community reviews. It
  selects 0 raw values, emits 0 Known drafts, creates 0 approval-ready packets,
  allows 0 runtime writes, and allows 0 production writes.
- A-share Unknown penetration P1 source-confirmation audit in
  `docs/audit/a_share_unknown_penetration_p1_source_confirmation_2026-06-19.json`
  reads the top P1 DOCKCASE HTML source directly from
  `/Volumes/dockcase2tb/market_data/news/cls_flash/2026/03/116987_华泰证券_供需向好下电子气体景气或加速.html`.
  It confirms the source file exists, the `40%` token is present, and the same
  document contains 华泰证券 attribution, 电子气体 domain terms, 我国/国内 scope,
  上市公司 scope, 市场份额 context, and 国内市场规模 denominator language. It
  still selects 0 raw values, emits 0 Known drafts, creates 0 approval-ready
  packets, allows 0 runtime writes, and allows 0 production writes.
- A-share Unknown penetration value-policy draft audit in
  `docs/audit/a_share_unknown_penetration_value_policy_draft_2026-06-19.json`
  converts that confirmed P1 source into a reviewer-facing proposal only:
  `raw_value=40.0`, `score=0.4`, `unit=percent`, and formula
  `score = clamp(raw_percent / 100, 0, 1)`. The proposed payload bridges to the
  final-score target, but the audit keeps selected raw values, selected value
  JSONs, Known drafts, approval-ready packets, runtime writes, and production
  writes at 0.
- A-share Unknown penetration value-confirmation packet audit in
  `docs/audit/a_share_unknown_penetration_value_confirmation_packets_2026-06-19.json`
  packages that proposal into 1 hash-bound, review-required confirmation
  packet with 1 blank confirmation template. It validates 1 / 1 template
  contracts and 1 / 1 packet contracts, but keeps Known drafts, approval-ready
  rows, runtime writes, and production writes at 0.
- A-share Unknown penetration value-confirmation template bundle in
  `docs/audit/a_share_unknown_penetration_value_confirmation_templates_2026-06-19.json`
  extracts only the blank template from the packet audit. It validates 1 / 1
  blank/pending template contracts, keeps confirmed templates, Known drafts,
  approval-ready rows, runtime writes, and production writes at 0, and does not
  create the separate reviewer confirmation input file.
- A-share Unknown penetration value-confirmation gate audit in
  `docs/audit/a_share_unknown_penetration_value_confirmation_gate_2026-06-19.json`
  checks for a separate reviewer confirmation record tied to that payload hash.
  No confirmation file exists yet, so it sees 0 confirmation records, marks 1
  confirmation missing, emits 0 Known-draft candidates, and allows 0 runtime or
  production writes.
- A-share Unknown penetration confirmed Known-draft audit in
  `docs/audit/a_share_unknown_penetration_confirmed_known_drafts_2026-06-19.json`
  consumes only confirmed value policies from the confirmation gate. Current
  real data has 0 confirmed candidates, so it emits 0 Known drafts, blocks 1
  row at `confirmation_missing`, marks 0 rows ready for review staging, and
  allows 0 runtime or production writes.
- A-share runtime scope approval audit in
  `docs/audit/a_share_runtime_scope_approvals_2026-06-19.json` checks the 2
  deterministic target-scope candidates and creates 2 scope approval records.
  It approves 2 runtime target scopes, rejects 0 scope policies, tracks 3,282
  candidate runtime rows that would write only after a controlled batch plan is
  later approved, attempts 0 runtime writes, and allows 0 production writes.
- A-share runtime write target-scope audit in
  `docs/audit/a_share_runtime_write_target_scope_2026-06-19.json` checks those
  2 approved write-plan entries against the current A-share universe. It
  cross-checks 1,641 runtime A-share `ts_code`s against 1,641 configured
  A-share `ts_code`s with an exact match, packages 2 target-scope candidates,
  validates 2 / 2 target-scope contracts, accepts 2 / 2 scope approvals, keeps
  0 target-scope reviews required, requires 2 controlled batch plans, and
  records 3,282 candidate runtime rows that would write only if a later batch
  plan is approved. It attempts 0 runtime writes and allows 0 production
  writes.
- A-share runtime write controlled batch-plan audit in
  `docs/audit/a_share_runtime_write_batch_plan_2026-06-19.json` packages those
  2 scope-approved entries into reviewable UPSERT plans. It validates 2 / 2
  batch-plan contracts, plans 3,282 `realtime_current` rows, classifies all
  3,282 as inserts and 0 as updates, requires backup for 0 existing affected
  rows, keeps 0 batch plans review-required and marks 2 approved, attempts 0
  runtime writes, and allows 0 production writes.
- A-share runtime write batch-approval audit in
  `docs/audit/a_share_runtime_write_batch_approvals_2026-06-19.json` creates 2
  controlled batch-plan approval records. It approves 2 / 2 batch plans, rejects
  0, covers 3,282 planned UPSERT rows / 3,282 inserts / 0 updates, requires
  backup for 0 existing affected rows, attempts 0 runtime writes, and allows 0
  production writes.
- A-share runtime write execution audit in
  `docs/audit/a_share_runtime_write_execution_2026-06-19.json` is the bounded
  write step for those approved batch plans. It first creates a SQLite backup
  snapshot at
  `runtime/backups/hot.sqlite.before_a-share-runtime-batch-6cdaa23a7edf_20260619194022.sqlite`
  with `quick_check=ok`, then writes 3,282 approved `realtime_current` rows
  in one transaction: 3,282 inserts, 0 updates, 2 / 2 runtime writes completed,
  0 write failures, 3,282 / 3,282 post-write rows verified, and 0 production
  writes allowed.
- A-share runtime write preflight in
  `docs/audit/a_share_runtime_write_preflight_2026-06-19.json` checks those 2
  approved write-plan entries against target scope, batch-plan approval, and
  the execution report. It now sees 2 approved target-scope candidates, 2
  batch-plan candidates, 2 approved batch plans, and 2 completed executions.
  It finds 0 upsert-ready entries because no write remains pending, blocks 0
  entries, keeps missing target scopes at 0, requires 0 additional controlled
  batch plans, requires 0 backup/execution gates, tracks 3,282 execution-written
  rows and 3,282 verified rows, records 2 runtime write attempts from the
  execution evidence, and allows 0 production writes.
- Market document audit in `docs/audit/market_documents_2026-06-18.json`
  now performs full extractability parsing for all 15,154 market documents:
  14,956 news HTML files and 198 announcement PDFs. It selected and parsed
  100% of those files, while retaining only 80 bounded examples in the JSON for
  review size. Full-run signals: 6,724 documents have entity hints, all 15,154
  have date signals, 15,117 have event-keyword signals, and 15,136 have
  citation previews. The remaining parser-governance issues are now full-run
  counts rather than samples: 29 missing titles, 24 short text extracts, 32
  boilerplate-or-placeholder documents, and 6 short PDF text extracts.
- Goal coverage audit in `docs/audit/goal_coverage_2026-06-19.json` /
  `docs/audit/goal_coverage_2026-06-19.md` now
  links the inventory, code, data, A-share score, performance, and module
  artifacts into a 10-requirement evidence matrix. All 10 requirements have
  current evidence, but the overall status remains `not_complete` because
  A-share scoring still has actionable participating gaps. The
  DOCKCASE CSV row now combines all-file head/tail evidence from
  `docs/audit/dockcase_csv_file_evidence_2026-06-19.json`, the
  signature-stratified semantic row samples, and the completed 212.62M-row
  full-row scan; the A-share score trace now
  separates raw participating gaps from **32 actionable participating gaps**
	  and 21 governance/intentional gaps, with all 32 now packaged as
	  candidate-ready local/event/grain-join/manual-design inputs, all 32
	  bridge-dry-run ready, all 32 review-gated by upsert-safety, 0 deterministic
	  review payloads pending, 32 generator-required placeholders, all 32 staging
	  value contracts valid, 157 spec fields numeric-and-score-path ready, 17
	  score-relevant fields unresolved by the conversion-path audit, including 14
	  formula/normalizer gaps and 3 missing-current-input gaps, with all 17 now
	  backed by review-decision evidence: 6 formula-policy review-required, 8
	  governance-suppression verified, 3 listed-option/N/A verified, and 0
  unclassified. The remediation
  queue now splits those 17 into 6 formula-policy/peer-context rows, 8
  governed-or-duplicate rows, and 3 listed-option-universe/N/A rows with 0
  safe formula-now rows, then packages the 6 policy rows into formula-policy
  review packets with 3 replacement-ready paths and 0 direct-ready formulas,
  and verifies the 8 governed-or-duplicate rows with 8 suppressions confirmed,
  6 replacement/canonical-ready paths, and 0 production writes, then verifies
  the 3 option/IV rows as listed-option-universe/N/A packets with 3 missing
	  current A-share option inputs, 0 `Known` values allowed now, 3 valid
	  verification contracts, and 0 production writes. The same goal coverage row
	  now also links the penetration value-priority, P1 source-confirmation, and
	  value-policy draft audits before the later confirmation-template gate, with
	  1 P1 source confirmed, 1 proposed value JSON, 1 final-score bridge-ready
	  policy draft, and 0 selected runtime values. It also tracks 32 queued generator tasks,
  28 / 28 non-manual readiness checks bridge-ready with 0 deterministic Known
  drafts, 10 / 12
  event-text Known draft review packets, 12 event-text drafts review-required,
  12 / 12 event-text draft contracts valid, 0 event-text draft contracts
  invalid, 10 event-text Known drafts bridge-ready, 0 event-text safe
  auto-upsert, 0 event-text production writes, 12 / 12 event-text
  classification inputs ready, 78 headline inputs, 8 unique titles, 0
  full-text packets, 12 title-level-only packets, 3 event-text
  preclassification target-keyword-hit packets, 11 A-share transmission
  keyword-hit packets, 2 target-and-transmission keyword-hit packets, 0 direct
  Known candidates allowed, 0 event-text preclassification production writes,
  3 event-text sufficiency target-headline packets, 11 broad-market-only
  transmission packets, 0 same-headline target+direct-transmission packets, 0
  title-signal-sufficient classifier candidates, 0 event-text sufficiency Known
  candidates allowed, 0 event-text sufficiency production writes,
  8 / 8 event-text URLs fetchable, 8 URLs with primary text, 12 body packets
  checked, 3 body target-hit packets, 0 body direct-transmission-hit packets, 0
  body-signal-sufficient classifier candidates, 0 event-text body Known
  candidates allowed, 0 event-text body production writes, 2 event-text
  Unknown source-option rows, 2 event-text Unknown classification inputs ready,
  2 event-text Unknown body texts available, 0 event-text Unknown target-event
  evidence present, 0 event-text Unknown direct A-share transmission present, 2
  event-text Unknown broad-market-only transmission rows, 0 event-text Unknown
  classifier-ready review candidates, 2 event-text target-event evidence
  required, 0 event-text direct A-share transmission required, 0 event-text
  Unknown auto Known candidates, 0 event-text Unknown source-option production
  writes,
  6 / 10 local structured Known draft review packets, 10 local-structured drafts
  review-required, 10 / 10 local-structured draft contracts valid, 0
  local-structured draft contracts invalid, 6 local-structured Known drafts
  bridge-ready, 0 local-structured safe auto-upsert, 0 local-structured
  production writes, 4 local-structured source-candidate rows, 0 direct
  Known-ready rows, 2 review/source candidate rows, 1 review candidate match,
  4 supporting candidate matches, 2 no-direct-source rows, 407 false-positive
  field/path matches excluded, 0 source-candidate production writes,
  4 local-structured source-review packets, 1 lease/rent review-ready packet,
  1 ASP quantity-needed packet, 2 external-source-required packets, 0
  source-review direct Known-ready packets, 0 source-review formula-ready
  packets, 4 / 4 source-review packet contracts valid, 0 source-review
  production writes,
  3 / 3 local structured-text Known draft review packets,
  3 local-structured-text drafts review-required, 3 / 3
  local-structured-text draft contracts valid, 0 local-structured-text draft
  contracts invalid, 3 local-structured-text Known drafts bridge-ready, 0
  local-structured-text safe auto-upsert, 0 local-structured-text production
  writes, 2 / 3 local
  single-dependency Known draft review packets, 3 single-dependency drafts
  review-required, 3 / 3 single-dependency draft contracts valid, 0
  single-dependency draft contracts invalid, 2 single-dependency Known drafts
  bridge-ready, 0 single-dependency safe auto-upsert, 0 single-dependency
  production writes, 1 single-dependency Unknown source-option row with 1
  lifecycle-policy review template, 1 valid lifecycle-policy template contract,
  0 invalid template contracts, 1 blank-pending template, 0 input-ready
  templates, 0 Known-draft-sufficient rows, and 0 approval-ready rows, 4 / 4
  manual-policy Known
  draft review packets, 4 / 4 manual-policy draft contracts valid, 4
  local-structured Unknown drafts, 0 local-structured-text Unknown drafts, 1
  single-dependency Unknown draft, 0 manual-policy Unknown drafts, 32 / 32
  review-manifest entries, 25 review-manifest concrete-ready packets, 7
  review-manifest Unknown-gated packets, 32 / 32 review-manifest contracts
  valid, 25 review-manifest concrete packets bridge-ready, 0 review-manifest
  safe auto-upsert, 0 review-manifest production writes, 0 review-manifest
  approved runtime writes, 2 deterministic approval records, 2 deterministic
  approved runtime writes already consumed by bounded runtime execution, 0 deterministic
  production writes, 25 approval-gate required approvals, 2 historical approval
  records seen, 25 missing approvals, 2 stale/rejected approvals, 0 approval-gate approved
  runtime writes, 0 write-plan entries, 7 Unknown packets not approvable, 32
  completion next-actions, 25 completion human approvals, 0 completion
  runtime write-plan-ready packets, 7 completion Unknown resolutions, 2
  completion event-text classifications, 4 completion local structured
  mappings, 0 completion structured-text extractions, 1 completion
  single-dependency policy, 0 completion manual assumption reviews, 0
  completion approval payload hash mismatches, 0 approval cross-report
  consistency errors, 7 Unknown closure rows, 7 Unknown closure routes
  assigned, 0 Unknown closure routes missing, 0 Unknown closure auto
  Known-ready rows, 0 Unknown closure approval-ready rows, 7 / 7 Unknown
  closure contracts valid, 0 Unknown closure production writes, 7 Unknown
  acquisition tasks, 2 Unknown acquisition market-doc searches, 2 Unknown
  acquisition local formula-source tasks, 3 Unknown acquisition external/text
  business-metric tasks, 3 Unknown acquisition tasks with existing candidate
  evidence, 1 Unknown acquisition task with runtime overlay hints, 6 Unknown
  acquisition tasks requiring web/external or deeper source acquisition, 7
  Unknown acquisition LLM extraction/classification-only tasks, 0 Unknown
  acquisition formula-ready tasks, 0 Unknown acquisition auto Known-ready
  tasks, 0 Unknown acquisition approval-ready tasks, 7 / 7 Unknown
  acquisition task contracts valid, 0 Unknown acquisition production writes, 2
  Unknown market-doc acquisition tasks, 14,956 Unknown market-doc acquisition
  HTML files scanned, 0 Unknown market-doc acquisition read errors, 2 Unknown
  market-doc acquisition rows with review candidates, 5 Unknown market-doc
  new-entrant window candidate documents, 6 Unknown market-doc new-entrant
  review candidate snippets, 34 Unknown market-doc substitute-tech
  same-sentence candidate documents, 3 Unknown market-doc substitute-tech
  clean-risk review candidate snippets, 9 Unknown market-doc weak candidates,
  34 Unknown market-doc rejected candidates, 0 Unknown market-doc
  Known-draft-sufficient rows, 0 Unknown market-doc production writes, 2 Unknown
  local formula acquisition tasks, 2 Unknown local formula runtime
  dependency-ready tasks, 6 Unknown local formula sample CSV files checked, 6
  Unknown local formula sample CSV files existing, 0 Unknown local formula sample
  CSV read errors, 8 Unknown local formula input groups, 0 Unknown local formula
  input groups ready, 2 Unknown local formula rows with candidate numerators, 0
  Unknown local formula rows with direct denominators, 0 Unknown local formula
  rows with quantity or price-index inputs, 0 Unknown local formula rows with
  formula policy, 0 Unknown local formula-ready rows, 0 Unknown local formula
  Known-draft-ready rows, 2 / 2 Unknown local formula contracts valid, 0 Unknown
  local formula production writes, 2 Unknown local formula review packets, 2
  Unknown local formula review rows with candidate numerators, 0 Unknown local
  formula review rows with direct denominators, 1 Unknown local formula review
  row with denominator candidates, 1 Unknown local formula review row with
  candidate formula shapes, 1 Unknown local formula review row with
  formula-policy draft candidates, 1 Unknown local formula review row with
  price-index context candidates, 1 Unknown local formula review row with
  candidate price-context shapes, 0 Unknown local formula review rows with
  quantity or price-index inputs, 0 Unknown local formula review rows
  with formula policy, 0 Unknown local formula review input-ready rows, 0
  Unknown local formula probes available, 0 Unknown local formula
  bridge-probe-ready packets, 0 Unknown local formula Known-draft-sufficient
  packets, 0 Unknown local formula approval-ready packets, 2 / 2 Unknown local
  formula review contracts valid, 0 Unknown local formula review production
  writes, 2 local formula source-capability rows, 8 local formula
  source-capability checks, 6 checks with source candidates, 1
  header-available-but-sample-empty check, 3 context/proxy checks, 3
  policy-required checks, 1 external/text-required check, 0 formula blockers
  resolved by current sources, 0 rows formula-ready after source scan, 0 local
  formula probes available after source scan, 0 local formula source-capability
  production writes, 3 Unknown external business metric
  acquisition tasks, 3 Unknown external business metric runtime
  dependency-ready tasks, 7 Unknown external business metric overlay hints, 12
  Unknown external business metric groups, 0 Unknown external business metric
  groups ready, 3 Unknown external business metric rows with supporting runtime
  context, 0 Unknown external business metric rows with direct sources, 3
  Unknown external business metric rows requiring external/text source, 238
  Unknown external business metric false positives, 0 Unknown external business
  metric-ready rows, 0 Unknown external business metric Known-draft-ready rows,
  3 / 3 Unknown external business metric contracts valid, 0 Unknown external
  business metric production writes, 3 Unknown external business metric
  market-doc tasks, 14,956 Unknown external business metric market-doc HTML
  files scanned, 0 Unknown external business metric market-doc read errors, 3
  Unknown external business metric market-doc rows with review candidates, 178
  Unknown external business metric market-doc candidate documents, 99 Unknown
  external business metric market-doc review candidates, 49 Unknown external
  business metric market-doc numeric review candidates, 50 Unknown external
  business metric market-doc textual review candidates, 82 Unknown external
  business metric market-doc weak candidates, 72 Unknown external business
  metric market-doc rejected candidates, 0 Unknown external business metric
  market-doc Known-draft-sufficient rows, 0 Unknown external business metric
  market-doc metric-ready rows, 3 / 3 Unknown external business metric
  market-doc contracts valid, 0 Unknown external business metric market-doc
  production writes, 99 Unknown external business metric review packets, 99
  Unknown external business metric expected review candidates, 3 Unknown
  external business metric rows with review packets, 49 Unknown external
  business metric numeric review packets, 50 Unknown external business metric
  textual review packets, 99 Unknown external business metric packets with
  scope candidates, 70 Unknown external business metric packets with denominator
  candidates, 36 Unknown external business metric packets with period
  candidates, 49 Unknown external business metric packets with unit candidates,
  0 Unknown external business metric review-packet metric-ready rows, 0 Unknown
  external business metric review-packet Known-draft-sufficient rows, 99 / 99
  Unknown external business metric review-packet contracts valid, 0 Unknown
  external business metric review-packet production writes, 99 Unknown external
  business metric readiness packets, 18 Unknown external business metric P0
  formula-policy-only candidates, 52 Unknown external business metric P1
  period/unit-required candidates, 29 Unknown external business metric P2
  denominator-required candidates, 29 Unknown external business metric packets
  missing denominator, 63 Unknown external business metric packets missing
  period, 50 Unknown external business metric packets missing unit, 99 Unknown
  external business metric packets missing bounds, 99 Unknown external business
  metric packets missing formula policy, 0 Unknown external business metric
  readiness metric-ready packets, 0 Unknown external business metric readiness
  Known-draft-sufficient packets, 0 Unknown external business metric readiness
  production writes, 18 Unknown external business metric P0 source packets for
  policy draft, 18 Unknown external business metric policy draft packets, 18
  Unknown external business metric formula-policy reviews required, 18 Unknown
  external business metric value JSON templates, 18 Unknown external business
  metric policy review templates, 18 Unknown external business metric policy
  review template contracts valid, 0 Unknown external business metric policy
  review template contracts invalid, 18 Unknown external business metric policy
  review templates blank-pending, 0 Unknown external business metric policy
  review template inputs ready, 0 Unknown external business
  metric policy-draft metric-ready rows, 0 Unknown external business metric
  policy-draft Known-draft-sufficient rows, 18 / 18 Unknown external business
  metric policy-draft contracts valid, 0 Unknown external business metric
  policy-draft production writes, 25 approval review packets, 25 approval Known
  packets, 0 approval NotApplicable packets, 25 approval packet bridge-ready
  checks, 25 approval packet templates, 10 event-approval source-sample packets,
  48 / 48 DOCKCASE event docs readable, 10 / 10 event-evidence review templates
  valid, 10 event reviewer packets complete but still blank/pending, 10
  individual review source-sample packets, 10 / 10 individual review templates
  valid, 10 individual reviewer packets complete but still blank/pending, 25
  approval source-sample coverage packets, 25 approval inputs ready, 0 approval
  inputs not ready, 0 unsupported approval risk classes, 0 safe for unreviewed
  runtime upsert, and 0 still
  blocked for candidate input. The new
  field-closure audit fixes the former
  config/runtime spec-total drift (`250` -> `256`) and records 121 / 174
  score-relevant dp_ids currently reaching final score. The score-conversion
  audit adds the stricter current + candidate path view: 157 / 256 fields are
  numeric-and-score-path ready, while 17 score-relevant fields still lack a
  usable formula/normalizer or current numeric input; those 17 are now fully
  classified as 6 formula-policy review-required, 8 governance-suppression
  verified, and 3 listed-option/N/A verified, with 0 unclassified gaps. The former 3
  formula-ready CLS fields now have valid runtime `Known` rows. The module
  evidence in this goal audit now points
  at `docs/audit/module_status_2026-06-20.json`, including the 17 local
  runtime/data/tooling surfaces and 31-row combined inventory counts.
- BFF latency inventory in `docs/audit/bff_latency_2026-06-19.json` measured
  23 frontend hot-path/API endpoints through a temporary local server; all
  returned HTTP 200 and stayed under 1 second, with max observed latency
  104.737 ms after the short derived-response cache. The expanded endpoint set now includes frontend hot-path
  `compat`, industry-graph list, `market-events`, `aggregate` coverage, and
  the lean `stock-overlay?include_static=0` request used by the frontend.
- Frontend shell latency inventory in
  `docs/audit/frontend_shell_latency_2026-06-19.json` measured 20 Project ULT
  direct SPA routes through a temporary Vite server; all returned HTTP 200,
  rendered a valid Vite shell, and stayed under 1 second, with max observed
  shell latency 14.526 ms. This complements, but does not replace, browser
  first-`h1` visibility evidence.
- `FrontEnd/` has 160 source/config files when `src-tauri/target` is excluded;
  `runtime/` is 10G, led by 4.5G annual reports, a 2.1G `hot.sqlite`, and
  roughly 3.6G of local `hot.sqlite` backups.
- Code scale baseline: the static source inventory now sees `mvp20` at 39,517
  lines, `scripts` at 49,090, `pit_backtest` at 2,621, and `FrontEnd/src`
  TypeScript/TSX/CSS at 26,143 lines. The 7 vendored upstream packages contain
  real source and tests; six service-like packages are exposed through
  artifact-backed adapter routes in this repo, while `contracts` remains a
  dependency.
- The current realtime freshness marker is `2026-06-19 00:41:31 CST` after the
  focused `tushare-macro` refresh. This proves the macro sentinel rows are
  same-day fresh for the 2026-06-19 continuation audit, but does not imply every
  slower per-stock source has been refreshed.
- `validate-overlays` passes structurally with 1878 stock overlays and 0
  errors, but still reports 164,297 Unknown/conditional warning rows; data
  validity/completeness remains an open audit area.
- Overlay YAML validation now uses the C safe YAML loader on the `mvp20`
  overlay path. The full `validate-overlays` CLI completed in 35.91 seconds on
  this machine after that change.
- Full `pytest` now completes successfully for the collected 77 test files /
  1341 tests. The remaining incompleteness is data/content audit depth, not the
  current automated Python test gate.

Repeatable audit commands for the current snapshot:

```bash
.venv/bin/python scripts/audit_inventory.py --output docs/audit/file_inventory_2026-06-19.json
.venv/bin/python scripts/audit_code_index.py --output docs/audit/code_inventory_2026-06-19.json
.venv/bin/python scripts/audit_repo_content.py --output-json docs/audit/repo_content_2026-06-19.json --output-md docs/audit/repo_content_2026-06-19.md
.venv/bin/python scripts/audit_repo_binary_semantics.py --repo-content docs/audit/repo_content_2026-06-19.json --output-json docs/audit/repo_binary_semantics_2026-06-19.json --output-md docs/audit/repo_binary_semantics_2026-06-19.md
.venv/bin/python scripts/audit_data_catalog.py --output docs/audit/data_catalog_2026-06-19.json --csv-row-sample-limit 1
.venv/bin/python scripts/audit_dockcase_csv_file_evidence.py
.venv/bin/python scripts/audit_dockcase_csv_semantics.py --as-of-date 2026-06-18
.venv/bin/python scripts/audit_dockcase_csv_full_scan.py --max-files 200 --progress-every 100
# Continue later with a later shard, for example:
.venv/bin/python scripts/audit_dockcase_csv_full_scan.py --skip-files 200 --max-files 200 --output-json docs/audit/dockcase_csv_full_scan_shard_000200_000399.json --output-md docs/audit/dockcase_csv_full_scan_shard_000200_000399.md --evidence-jsonl-gz docs/audit/dockcase_csv_full_scan_shard_000200_000399.jsonl.gz --progress-every 100
.venv/bin/python scripts/audit_dockcase_csv_full_scan.py --skip-files 400 --max-files 200 --output-json docs/audit/dockcase_csv_full_scan_shard_000400_000599.json --output-md docs/audit/dockcase_csv_full_scan_shard_000400_000599.md --evidence-jsonl-gz docs/audit/dockcase_csv_full_scan_shard_000400_000599.jsonl.gz --progress-every 100
.venv/bin/python scripts/audit_dockcase_csv_full_scan.py --skip-files 600 --max-files 1000 --output-json docs/audit/dockcase_csv_full_scan_shard_000600_001599.json --output-md docs/audit/dockcase_csv_full_scan_shard_000600_001599.md --evidence-jsonl-gz docs/audit/dockcase_csv_full_scan_shard_000600_001599.jsonl.gz --progress-every 200
.venv/bin/python scripts/audit_dockcase_csv_full_scan.py --skip-files 1600 --max-files 2000 --output-json docs/audit/dockcase_csv_full_scan_shard_001600_003599.json --output-md docs/audit/dockcase_csv_full_scan_shard_001600_003599.md --evidence-jsonl-gz docs/audit/dockcase_csv_full_scan_shard_001600_003599.jsonl.gz --progress-every 500
.venv/bin/python scripts/audit_dockcase_csv_full_scan.py --skip-files 3600 --max-files 4000 --output-json docs/audit/dockcase_csv_full_scan_shard_003600_007599.json --output-md docs/audit/dockcase_csv_full_scan_shard_003600_007599.md --evidence-jsonl-gz docs/audit/dockcase_csv_full_scan_shard_003600_007599.jsonl.gz --progress-every 1000
.venv/bin/python scripts/audit_dockcase_csv_full_scan.py --skip-files 7600 --max-files 8000 --output-json docs/audit/dockcase_csv_full_scan_shard_007600_015599.json --output-md docs/audit/dockcase_csv_full_scan_shard_007600_015599.md --evidence-jsonl-gz docs/audit/dockcase_csv_full_scan_shard_007600_015599.jsonl.gz --progress-every 2000
.venv/bin/python scripts/audit_dockcase_csv_full_scan.py --skip-files 15600 --max-files 16000 --output-json docs/audit/dockcase_csv_full_scan_shard_015600_031599.json --output-md docs/audit/dockcase_csv_full_scan_shard_015600_031599.md --evidence-jsonl-gz docs/audit/dockcase_csv_full_scan_shard_015600_031599.jsonl.gz --progress-every 4000
.venv/bin/python scripts/audit_dockcase_csv_full_scan_progress.py
.venv/bin/python scripts/audit_dockcase_semantic_backlog.py
.venv/bin/python scripts/audit_dockcase_backlog_batch.py --ranks 46 --max-files-per-signature 50 --rows-per-file 200
.venv/bin/python scripts/audit_dockcase_backlog_batch.py --ranks 27,31 --max-files-per-signature 50 --rows-per-file 200 --output docs/audit/dockcase_backlog_batch_r27_r31_2026-06-18.json --markdown-output docs/audit/dockcase_backlog_batch_r27_r31_2026-06-18.md
.venv/bin/python scripts/audit_dockcase_backlog_batch.py --ranks 121,124,128 --max-files-per-signature 10 --rows-per-file 200 --output docs/audit/dockcase_backlog_batch_p0_no_rows_2026-06-18.json --markdown-output docs/audit/dockcase_backlog_batch_p0_no_rows_2026-06-18.md
.venv/bin/python scripts/audit_a_share_data_semantics.py
.venv/bin/python scripts/audit_market_documents.py
.venv/bin/python scripts/audit_a_share_score_trace.py --sample-ts-code 300750.SZ
.venv/bin/python scripts/audit_a_share_score_gap_priority.py
.venv/bin/python scripts/audit_a_share_gap_candidate_evidence.py
.venv/bin/python scripts/audit_a_share_candidate_score_dry_run.py
.venv/bin/python scripts/audit_a_share_candidate_upsert_safety.py
.venv/bin/python scripts/audit_a_share_candidate_staging_payloads.py
.venv/bin/python scripts/audit_a_share_candidate_value_contracts.py
.venv/bin/python scripts/audit_a_share_spec_numeric_validity.py
.venv/bin/python scripts/audit_a_share_score_conversion_remediation_queue.py
.venv/bin/python scripts/audit_a_share_formula_policy_review_packets.py
.venv/bin/python scripts/audit_a_share_governance_suppression_verification.py
.venv/bin/python scripts/audit_a_share_option_universe_na_verification.py
.venv/bin/python scripts/audit_a_share_spec_score_conversion_path.py
.venv/bin/python scripts/audit_a_share_candidate_generation_queue.py
.venv/bin/python scripts/audit_a_share_l0_source_readiness.py
.venv/bin/python scripts/audit_a_share_short_report_evidence.py
.venv/bin/python scripts/audit_a_share_non_manual_candidate_readiness.py
.venv/bin/python scripts/audit_a_share_local_structured_policy_drafts.py
.venv/bin/python scripts/audit_a_share_local_structured_unknown_source_options.py
.venv/bin/python scripts/audit_a_share_local_structured_source_candidates.py
.venv/bin/python scripts/audit_a_share_local_structured_source_review_packets.py
.venv/bin/python scripts/audit_a_share_local_structured_text_policy_drafts.py
.venv/bin/python scripts/audit_a_share_local_structured_text_unknown_source_options.py
.venv/bin/python scripts/audit_a_share_local_single_dependency_policy_drafts.py
.venv/bin/python scripts/audit_a_share_local_single_dependency_unknown_source_options.py
.venv/bin/python scripts/audit_a_share_manual_policy_draft_candidates.py
.venv/bin/python scripts/audit_a_share_manual_policy_unknown_source_options.py
.venv/bin/python scripts/audit_bff_latency.py --start-server --port 8799 --output docs/audit/bff_latency_2026-06-19.json --repeats 3 --warmups 1
.venv/bin/python scripts/audit_frontend_shell_latency.py --start-server --port 1421 --proxy-target http://127.0.0.1:8799 --output docs/audit/frontend_shell_latency_2026-06-19.json --repeats 3 --warmups 1
.venv/bin/python scripts/audit_frontend_project_ult_navigation.py
.venv/bin/python scripts/audit_goal_coverage.py
node -e "const fs=require('fs'); for (const p of ['docs/audit/completion_deviation_2026-06-20.json','docs/audit/module_status_2026-06-20.json','docs/audit/bff_latency_2026-06-20.json','docs/audit/a_share_current_mvp_score_applicability_2026-06-20.json','docs/audit/dockcase_csv_quality_impact_2026-06-20.json']) JSON.parse(fs.readFileSync(p,'utf8')); console.log('json ok')"
```

## Repository Map

- `mvp20/` — Python package for manifest validation, provider validation,
  overlay generation/compilation, scoring/coverage helpers, data-source
  adapters, and the read-only stdlib HTTP BFF (`mvp20 serve`).
- `config/` — auditable source of truth for the 13-industry universe,
  provider catalog, market adapters, field governance, industry graphs,
  industry overlays, and company-industry stock overlays.
- `runtime/` — local runtime artifacts: `hot.sqlite` for compiled graph
  snapshots / current realtime values and `history/` for optional Parquet
  minute replay. Treat this as local state, not canonical source.
- `scripts/` — collector, SQLite initialization, compaction, prompt
  generation, overlay verification, and audit utilities.
- `docs/` — operator runbooks, data-source audits, industry-graph docs,
  and generated audit reports.
- `FrontEnd/` — Vite + React + TypeScript + Tauri frontend. In
  `projectUlt` mode it targets the mvp20 BFF at `http://127.0.0.1:8701`
  or a compatible `/api` backend.
- `upstream/` — vendored source snapshots for `contracts`,
  `audit-eval`, `data-platform`, `entity-registry`, `graph-engine`,
  `main-core`, and `reasoner-runtime`. The full 14-module pin set is in
  `locks/modules.lock.yaml`.

## MVP Boundary

- The decision universe is organised by 13 industries declared in
  `config/mvp20.industries.yaml`. Each `graph_status: present` industry
  must have at least one constituent in `config/mvp20.universe.yaml`;
  pending industries are allowed to have no constituent yet.
- Constituents may belong to up to 3 industries (primary, secondary, and
  tertiary — e.g. 胜宏科技-H tagged AI_COMPUTE / SEMI_EQUIPMENT /
  CONSUMER_ELECTRONICS).
- A-share, Hong Kong, and US-listed constituents are accepted (via the
  validated `ts_code` formats `<NNNNNN>.SH|SZ|BJ`, `<NNNN[N]>.HK`, and
  `<SYMBOL>.US` — Berkshire-style multi-dot codes such as `BRK.B.US`
  also accepted). A and H listings of the same company stay as separate
  constituents (e.g. 紫金 601899.SH / 02899.HK).
- The MVP intentionally does not enforce a fixed total constituent count.
- `history_window_months=120`.
- `graph_depth=2`.
- Each industry with `graph_status: present` ships a structured causal
  graph at `config/industry_graphs/<slug>.yaml` (v3.1 template + v3.1.1
  valuation weights). Pending industries are reserved slots — the graph
  YAML is added later.
- The causal graph carries: industry priors (state probabilities, β
  values, valuation weights, tail risk, validation signals), shared
  nodes/edges with polarity and lag, and four render views
  (causal_propagation, core_factor, supply_chain, risk).
- All companies — Chinese industry leaders, Hong Kong dual listings, US
  ADRs, and upstream customers (e.g. Meta as an AI Capex driver) — live
  in `config/mvp20.universe.yaml`. Each constituent carries a `role`
  field (`target` / `customer` / `both`) so consumers can distinguish
  decision targets from upstream context entities.
- Each constituent also carries a `pool` field (`regular` / `core`).
  `regular` is the full ~300-stock leader pool that drives baseline
  scoring; `core` is the hand-curated subset that goes through deep-dive
  LLM analysis. Membership is human-curated (the schema does not promote
  automatically); `validate-manifest` reports a `pool_counts` summary so
  operators can see the split.
- External market-data providers are catalogued in
  `config/data_providers.yaml` and certified by `mvp20 validate-providers`.
  Active providers: Financial Modeling Prep (FMP, US primary —
  price / fundamentals / news / insider / SEC / analyst / DCF / macro / forex), Tushare
  (A-share primary), AKShare (A/HK free fallback), yfinance (US/HK free
  fallback), and Futu OpenAPI via the OpenD local gateway (HK / US
  deep data plus active options chain / IV; FMP options remain
  Premium-tier fallback).
  FRED stays planned for the macro epic. Secrets stay in env vars
  referenced by `secret_env_var`; the catalog rejects any inline
  `api_key` / `secret` / `token` fields. `mvp20 plan-backfill`
  automatically picks up the catalog when it sits next to the manifest
  and reports per-market provider coverage.
- Futu OpenD is treated as a special `auth_type: local_gateway`
  provider: the catalog declares only `gateway.host` / `gateway.port`
  (default `127.0.0.1:11111`) and the env var name
  (`FUTU_OPEND_PASSWORD`) for the encryption key the SDK uses to talk
  to the locally-running daemon. The catalog deliberately has no
  `base_url` for local_gateway providers because there is no remote
  HTTP endpoint — operators install OpenD from
  `https://www.futunn.com/download/OpenAPI`, log in once with a Futu
  account holding the relevant market-data subscriptions, and export
  `FUTU_OPEND_PASSWORD` locally.
- Walk-through fixtures under `config/industry_graphs/fixtures/` provide
  golden double-path examples (e.g. Meta Capex → NVDA) for downstream
  graph-engine simulators.
- Associated listed companies are graph and risk-summary context only.
- Buy/sell/recommendation decisions are emitted only for declared
  constituents.
- Provider gaps are recorded explicitly; missing data is not fabricated.

## Data Provider Capability Coverage

The provider vocabulary contains **51 capability slugs** when active,
tier-locked, and planned entries are counted together. The current active
5-provider catalog declares **47 active capability slugs**; FRED is still
planned. Per-provider endpoint inventories live under
[`docs/data_sources/`](docs/data_sources/) — these CSVs are the audit trail
proving every market and every important capability is covered.

### Spec data-point coverage

The provider capability table below is a source-capability inventory. It is
not the same thing as coverage of the **256 spec data points** in
[`config/data_point_roles.yaml`](config/data_point_roles.yaml) and
[`docs/data_sources/coverage_audit.md`](docs/data_sources/coverage_audit.md).
Use two separate A-share numbers:

- **Completion coverage** answers whether a spec field is present or handled by
  realtime / overlay data. Rerun
  `scripts/check_a_share_spec_completion.py`.
- **Score-trace coverage** answers whether valid information can become a
  numeric signal and actually reach the score path. Rerun
  `scripts/audit_a_share_score_trace.py`.

Current local runtime snapshot
(`runtime/hot.sqlite:realtime_current`) has **251,420 rows**,
**185 distinct dp_id**, **1,867 stock tickers**, and **144 distinct
`source` labels**. The compiled graph snapshot side has **1,878**
company graph snapshots, **1,878** overlay manifest rows, **217,848**
compiled node instances, and **24,414** compiled edge instances across
12 strict-valid industries. Recheck with:

```bash
sqlite3 runtime/hot.sqlite \
  'select count(*), count(distinct dp_id), count(distinct ts_code), count(distinct source) from realtime_current;'
sqlite3 runtime/hot.sqlite \
  'select count(*), count(distinct ts_code), count(distinct industry_id) from company_graph_snapshot;'
```

For the A-share slice specifically, use
[`docs/audit/a_share_spec_completion.md`](docs/audit/a_share_spec_completion.md),
[`docs/audit/a_share_score_trace_2026-06-18.md`](docs/audit/a_share_score_trace_2026-06-18.md),
[`docs/audit/a_share_score_gap_priority_2026-06-18.md`](docs/audit/a_share_score_gap_priority_2026-06-18.md),
[`docs/audit/a_share_score_field_closure_2026-06-19.md`](docs/audit/a_share_score_field_closure_2026-06-19.md),
[`docs/audit/a_share_spec_score_conversion_path_2026-06-19.md`](docs/audit/a_share_spec_score_conversion_path_2026-06-19.md),
or rerun the A-share audit scripts. The latest score-trace audit (2026-06-18 local run)
uses the production path:

`read_hot_snapshot` -> field governance -> `_realtime_signal` ->
`synthesize_realtime_nodes` / authored overlay -> `aggregate_company_graph` ->
`score_company`.

The current 2026-06-20 A-share applicability artifact keeps the raw score
denominator visible while separating current-MVP applicability. Raw score-field
closure is **132 / 174**; the current-MVP denominator is **120 / 120** with
**0** actionable gaps after excluding 54 fields only with audit-backed
non-applicability/backlog or verified no-final-score-delta score-sink reasons.
The current score-field closure audit also
reports **21** raw candidate-ready blockers before denominator adjustment,
`direct_structured_tushare_remaining=0`, and
`safe_to_upsert_without_review_count=0`. Historical candidate dry-run,
upsert-safety, staging-payload, and value-contract audits remain useful for
source/review traceability, but they are superseded for current-MVP completion
by `docs/audit/a_share_current_mvp_score_applicability_2026-06-20.json` and
`docs/audit/completion_deviation_2026-06-20.json`.
The value-contract audit validates **32 / 32** historical envelopes, flags **0** invalid
contracts, bridge-validates **0** concrete review payloads, and keeps the
32 generator-required placeholders from masquerading as Known scoring values.
The spec score-conversion-path audit checks the stricter conversion boundary:
**157 / 256** spec fields are current/candidate numeric-and-score-path ready,
while **17** score-relevant fields remain unresolved: **14** have real runtime
values but no current formula/normalizer, and **3** lack current numeric input.
Those **17** not-ready fields are now review-decision-backed in the same
report: **6** require formula-policy/peer-context review, **8** are verified
governance/duplicate/data-only suppressions, **3** require a listed-option
universe or reviewed N/A handling, and **0** remain unclassified.
The generation-queue audit packages those **32** placeholder rows into concrete
work items: **12** event-LLM candidates, **16** local closed-loop candidates,
and **4** manual-policy candidates, all with valid placeholder contracts and
**0** production writes allowed.
The non-manual readiness audit then checks the **28** local/event tasks:
**28 / 28** have material known dependency coverage, **28 / 28** placeholder
contracts and output contract shapes validate, and **28 / 28** bridge probes
reach final-score-ready realtime nodes. It deliberately allows **0**
deterministic Known drafts because these fields still need governed local/event
LLM review to assign business direction and magnitude.
The event-text policy draft pilot then handles the **12**
`event_text_classification_required` rows inside that non-manual set. After the
local market-doc packet bundle is available, **10 / 12** become review-only
Known drafts with bounded `value_json.score` payloads and **10 / 10**
bridge-validate into final-score targets. The remaining **2** stay Unknown:
`L0.tech.substitute_tech` now has a conservative negative-risk policy but its
retained market-doc examples do not pass the clean substitution-risk filter,
and `L0.compete.new_entrant` still needs direct target-event evidence.
All **12 / 12** draft contracts are valid, **0** are invalid, **0** are safe
for unreviewed upsert, and **0** production writes are allowed.
The event-text classification input audit packages those **12** Unknown event
rows into classifier/reviewer inputs. All **12 / 12** are input-ready at
title level, with **78** headline inputs and **8** unique titles. It finds
**0** packets with full article text, so all **12** remain title-level-only
classification inputs; **0** packets are classified into Known values and
production writes remain **0**.
The local structured policy draft pilot then handles the **10**
`local_structured_llm_required` rows inside that non-manual set: **6** become
review-only Known draft packets (`L0.cost.cac`, `L0.cost.labor`,
`L0.demand.terminal`, `L0.price.contract_spot`, `L0.supply.capacity`, and
`L0.supply.chain_eff`) that pass the production bridge, while **4** remain
Unknown because they need lease/detail, purchase-frequency, TAM/share, or ASP
volume/mix review. All **10 / 10** draft contracts are valid, **0** are
invalid, **6 / 6** Known drafts bridge-validate, and **0** are safe for
unreviewed upsert. These drafts are not approved staging/runtime values and
still allow **0** production writes.
The local structured Unknown source-options audit then reviews those **4**
Unknown rows against the current candidate evidence. All **4 / 4** have
runtime dependencies ready, but **0 / 4** have a direct existing structured
source that can be converted to Known automatically. It records **4**
overlay/source hints, marks all **4** rows as requiring new mapping or text
extraction, marks **0** rows as requiring reviewed pass-through policy, finds
**0** partial Known unlock candidates, and still allows **0** auto Known
candidates and **0** production writes.
The local structured source-candidates audit then checks those same **4**
Unknown rows against the current DOCKCASE/Tushare CSV semantic catalog. It finds
**0 / 4** direct Known-ready rows, **2** rows with review/source candidates,
**1** concrete review candidate match (`use_right_asset_dep` for lease burden),
**4** supporting product-mix / ASP context matches from `fina_mainbz`
(`bz_item`, `bz_sales`, `bz_cost`, `bz_profit`), **1** empty candidate match
(`fa_fnc_leases`), and **2** rows with no direct catalog source
(`L0.demand.frequency` and `L0.demand.penetration`). It explicitly excludes
**407** false-positive field/path matches such as stock prices, turnover,
trading volume, share capital, holder counts, index weights, and market ratios,
and still allows **0** production writes.
The local structured source-review packet bundle then packages those **4**
Unknown rows into reviewer-facing evidence packets. It marks **1** lease/rent
proxy packet as review-ready, **1** ASP packet as needing quantity or a governed
price-index source, and **2** packets as requiring external business sources.
Direct Known-ready packets remain **0**, formula-ready packets remain **0**,
**4 / 4** packet contracts are valid, **0** are invalid, and production writes
remain **0**.
The local structured-text policy draft pilot then handles the **3**
`local_structured_text_llm_required` rows inside that non-manual set:
`L0.demand.user_count`, `L0.price.discount`, and
`L0.supply.channel_service`. The QA/channel-service evidence now supports **1**
review-only Known draft for `L0.supply.channel_service`, and company-answer
pricing-pressure evidence now supports **1** review-only Known draft for
`L0.price.discount`. `L0.demand.user_count` now has **1** review-only Known
draft from strict answer-side customer/user/order/volume evidence after
excluding shareholder-count and investor-count contexts. All **3 / 3** draft
contracts are valid, **0** are invalid, **3 / 3** Known drafts bridge-validate,
and **0** are safe for unreviewed upsert. These drafts are not approved
staging/runtime values and still allow **0** production writes.
The local structured-text Unknown source-options audit then reviews **0**
remaining Unknown rows because all three structured-text rows now have
review-only Known draft packets. It records
**0** overlay/source hints, marks **0** rows as requiring customer/user text
classification, and still allows **0** auto Known candidates and **0**
production writes.
The local single-dependency policy draft pilot then handles the **3**
single-dependency rows inside that non-manual set: **2** become review-only
Known draft packets (`L0.price.pricing_power`, `L0.supply.inventory`) that pass
the production bridge, while **1** (`L0.demand.replacement`) remains Unknown
because revenue alone cannot identify replacement-cycle demand. All **3 / 3**
draft contracts are valid, **0** are invalid, **2 / 2** Known drafts
bridge-validate, and **0** are safe for unreviewed upsert. These drafts are
not approved staging/runtime values and still allow **0** production writes.
The local single-dependency Unknown source-options audit then reviews that
remaining **1** Unknown row. Its `L5.is.revenue` runtime dependency is ready
(`1755` Known rows in the current candidate evidence), but **0 / 1** rows have
direct replacement-cycle source evidence. It records **1** overlay/source hint,
finds **1** overlay lifecycle-context candidate row, and counts **205** A-share
`L3.product.lifecycle=Known` context nodes. `L0.demand.replacement` itself is
still **0** Known / **1,646** Unknown in stock overlays, so the row still needs
lifecycle / replacement-cycle evidence and a reviewed mapping policy. It still
allows **0** auto Known candidates and **0** production writes.
The manual-policy draft pilot then consumes those **4** manual-policy tasks:
all **4** become review-only Known draft packets that bridge through the
production score path. `L6.mult.dcf` now carries a conservative standard DCF
assumption draft (`discount_rate`, `terminal_growth`,
`forecast_horizon_years`, and `normalized_fcf_basis`) with a bounded
valuation-rerating score. All **4 / 4** draft contracts are valid, **0** are
invalid, and **0** are safe for unreviewed upsert. These drafts are not approved
staging/runtime values and still allow **0** production writes.
The manual-policy Unknown source-options audit then reviews **0** remaining
Unknown rows: no manual-policy dependency pack, DCF assumption, assumption
review, or reviewed-policy blocker remains in the Unknown queue. Auto Known
candidates and production writes remain **0**.
The review-staging manifest now reflects the post-execution A-share review
queue. The two deterministic neutral / NotApplicable rows have been consumed by
the bounded runtime execution, so the current queue has **32 / 32** review
entries, **25**
concrete review-ready packets (**25 Known**) and **7** review-gated Unknown
packets. All **32 / 32** contracts validate, all **25** concrete packets bridge
to final-score targets, missing review entries are **0**, invalid contracts are
**0**, safe auto-upsert is **0**, production writes are **0**, and approved
runtime writes are **0**.
The deterministic runtime-approval audit then creates **2** approval records
for strictly policy-gated cases: `L9.media.short_report` remains neutral Known
because the dedicated A-share short-report scan found **0** direct hits, and
`L7.trade.gamma` remains NotApplicable / neutral for A-share single stocks
without listed options. Both approval contracts validate, **32**
non-deterministic rows remain unapproved, and production writes remain **0**.
The review-approval gate then checks the canonical review queue against a
separate approval record file. It requires approval for the **25** concrete
packets, sees **2** historical approval records, leaves **25** missing
approvals, rejects the **2** stale records from the current queue, approves
**0** runtime writes into the current read-only write plan, produces **0**
write-plan entries, and keeps all **7** Unknown packets not
approvable.
The completion next-action queue turns those same **32** blockers into concrete
work queues: **25** review-ready packets need human approval records, **0**
packets are runtime-write-plan-ready in the current queue, and **7** Unknown
packets still need
evidence/classification/mapping. The Unknown split is **2** event-text
classifications, **4** local structured mappings, **0** structured-text
extractions, **1** single-dependency policy, and **0** manual DCF-assumption
reviews. It emits **25** incomplete approval templates for review convenience,
approves **0** runtime writes into the read-only write plan, finds **0**
approval payload hash mismatches, and allows **0** production writes.
The approval review packet bundle extracts the **25** concrete review-ready
packets into focused reviewer material: **25 Known** packets, **0
NotApplicable** packets, **25 / 25** final-score-target-ready bridge checks,
**25** payload hashes, **25** incomplete approval templates, and **25 / 25**
valid approval template contracts. It skips **0** concrete rows for missing
bridge/contract readiness, finds **0** approval payload hash mismatches, leaves
**25** approvals missing, approves **0** runtime writes into the read-only write
plan, and allows **0** production writes. Goal coverage now also checks this
approval chain across reports and reports **0** cross-report consistency errors.
The approval-packet risk-review audit then prioritizes those 25 concrete
packets without creating approvals: **6** strict structured bulk-review
candidates, **1** borderline structured-text sample-check candidate, and **18**
individual-review-required packets. The individual set includes **8**
event/text evidence packets, **4** structured proxy packets, and **6** policy /
non-fundamental target packets. It finds **0** contract-fix blockers, **0** auto
approvals, **0** runtime writes, and **0** production writes.
The bulk-review approval-candidate audit then extracts the next reviewer batch:
**7** draft approval templates, split into **6** strict structured candidates
and **1** borderline source-text sample-check candidate. The strict batch is
`L0.cost.cac`, `L0.cost.labor`, `L0.price.pricing_power`,
`L0.supply.capacity`, `L0.supply.chain_eff`, and `L0.supply.inventory`; the
borderline row is `L0.supply.channel_service`. All **7 / 7** draft contracts
validate, but every draft intentionally leaves approval status, reviewer,
timestamp, and risk acknowledgement incomplete, so it creates **0** auto
approvals, **0** runtime writes, and **0** production writes.
For the 7 remaining Unknown blockers, the penetration value-priority audit
identifies the closest review path: `L0.demand.penetration` has **6**
value-review packets and **8** bridge-ready formula probes. It ranks those into
**1** P1 preferred source-scope review, **1** P2 industry-scope review, **2**
P3 forecast/assumption reviews, and **2** P3 low-confidence community reviews.
The P1 source-confirmation audit then verifies the top DOCKCASE HTML file and
confirms the `40%` token in a domestic listed-company electronic-gas
market-share / domestic-market-size context. No value is selected and no Known
draft is emitted; the remaining blockers are reviewed numeric value selection,
bounds, formula policy, issuer/industry applicability, and approval.
The value-policy draft audit then packages the confirmed P1 item into a
reviewer-facing proposal: `raw_value=40.0`, `score=0.4`, `unit=percent`, and
`score = clamp(raw_percent / 100, 0, 1)`. The proposal bridges to the
final-score target, but still stays below Known because reviewer value
selection, bounds, formula policy, applicability, and approval are not complete.
The value-selection gate now consumes that proposal as 1
value-policy-draft-ready row with 1 proposed value JSON, while still selecting
0 runtime values and allowing 0 writes.
The value-confirmation packet audit then packages the same proposal into 1
review-required confirmation packet with a blank confirmation template and a
payload hash. This is the handoff point for human value/formula/applicability
confirmation; it still emits 0 Known drafts, 0 approval-ready rows, and 0
writes.
The value-confirmation template bundle then extracts only that blank template,
verifies it is still unfilled/pending, and keeps 0 confirmed templates, 0 Known
drafts, 0 approval-ready rows, and 0 writes; it is not the reviewer
confirmation input file.
The value-confirmation gate now enforces the next boundary: without a separate
confirmation record whose payload hash and acceptance booleans match, it emits
0 Known-draft candidates and keeps the field below runtime approval.
The confirmed Known-draft emitter then proves the next step is also gated:
because the confirmation gate has 0 confirmed policies, it emits 0 Known drafts
and keeps 1 row blocked before review staging.
Treat `a_share_score_field_closure_2026-06-19` plus
`a_share_candidate_upsert_safety_2026-06-19` plus
`a_share_candidate_staging_payloads_2026-06-19` plus
`a_share_candidate_value_contracts_2026-06-19` plus
`a_share_spec_numeric_validity_2026-06-19` plus
`a_share_spec_score_conversion_path_2026-06-19` plus
`a_share_score_conversion_remediation_queue_2026-06-19` plus
`a_share_formula_policy_review_packets_2026-06-19` plus
`a_share_governance_suppression_verification_2026-06-19` plus
`a_share_option_universe_na_verification_2026-06-19` plus
`a_share_candidate_generation_queue_2026-06-19` plus
`a_share_l0_source_readiness_2026-06-19` plus
`a_share_short_report_evidence_2026-06-19` plus
`a_share_non_manual_candidate_readiness_2026-06-19` plus
`a_share_event_text_policy_drafts_2026-06-19` plus
`a_share_event_text_classification_inputs_2026-06-19` plus
`a_share_event_text_preclassification_screen_2026-06-19` plus
`a_share_event_text_sufficiency_gate_2026-06-19` plus
`a_share_event_text_url_fetchability_2026-06-19` plus
`a_share_event_text_unknown_source_options_2026-06-19` plus
`a_share_event_text_market_doc_evidence_2026-06-19` plus
`a_share_event_text_market_doc_review_packets_2026-06-19` plus
`a_share_local_structured_policy_drafts_2026-06-19` plus
`a_share_local_structured_unknown_source_options_2026-06-19` plus
`a_share_local_structured_source_candidates_2026-06-19` plus
`a_share_local_structured_source_review_packets_2026-06-19` plus
`a_share_local_structured_text_policy_drafts_2026-06-19` plus
`a_share_local_structured_text_unknown_source_options_2026-06-19` plus
`a_share_local_single_dependency_policy_drafts_2026-06-19` plus
`a_share_local_single_dependency_unknown_source_options_2026-06-19` plus
`a_share_manual_policy_draft_candidates_2026-06-19` plus
`a_share_manual_policy_unknown_source_options_2026-06-19` plus
`a_share_review_staging_manifest_2026-06-19` plus
`a_share_review_approval_gate_2026-06-19` plus
`a_share_completion_next_actions_2026-06-19` plus
`a_share_unknown_closure_matrix_2026-06-19` plus
`a_share_unknown_acquisition_backlog_2026-06-19` plus
`a_share_unknown_market_doc_acquisition_candidates_2026-06-19` plus
`a_share_unknown_event_evidence_adjudication_2026-06-19` plus
`a_share_unknown_event_strict_source_gate_2026-06-19` plus
`a_share_unknown_event_strict_review_packets_2026-06-19` plus
`a_share_unknown_event_primary_source_confirmation_2026-06-19` plus
`a_share_unknown_event_external_source_confirmation_2026-06-19` plus
`a_share_unknown_local_formula_acquisition_candidates_2026-06-19` plus
`a_share_unknown_local_formula_review_packets_2026-06-19` plus
`a_share_local_formula_source_capability_2026-06-19` plus
`a_share_unknown_external_business_metric_acquisition_2026-06-19` plus
`a_share_unknown_external_business_metric_market_doc_candidates_2026-06-19` plus
`a_share_unknown_external_business_metric_review_packets_2026-06-19` plus
`a_share_unknown_external_business_metric_readiness_queue_2026-06-19` plus
`a_share_unknown_external_business_metric_policy_drafts_2026-06-19` plus
`a_share_unknown_external_business_metric_value_candidates_2026-06-19` plus
`a_share_unknown_external_business_metric_value_review_packets_2026-06-19` plus
`a_share_approval_review_packets_2026-06-19` plus
`a_share_approval_packet_risk_review_2026-06-19` plus
`a_share_bulk_review_approval_candidates_2026-06-19` plus
`a_share_bulk_review_source_samples_2026-06-19` plus
`a_share_event_approval_source_samples_2026-06-19` plus
`a_share_individual_review_source_samples_2026-06-19` plus
`a_share_approval_source_sample_coverage_2026-06-19` plus
`a_share_approval_target_scope_readiness_2026-06-20` plus
`a_share_approval_materialization_plan_2026-06-20` plus
`a_share_approval_materialization_batch_plan_2026-06-20` plus
`a_share_approval_materialization_batch_codex_review_2026-06-20` plus
`a_share_approval_materialization_batch_approval_gate_2026-06-20` plus
`a_share_approval_materialization_batch_execution_preflight_2026-06-20` plus
`a_share_runtime_scope_approvals_2026-06-19` plus
`a_share_runtime_write_target_scope_2026-06-19` plus
`a_share_runtime_write_batch_plan_2026-06-19` plus
`a_share_runtime_write_batch_approvals_2026-06-19` plus
`a_share_runtime_write_preflight_2026-06-19` as the current authority for
whether a field has valid information, can be numerically converted, reaches
`final_score`, is eligible for score-affecting writes, has a review-stage
payload, passes the staging value contract, has a queued generation task, has
L0 source-route readiness, has short-report evidence boundaries, has
local/event readiness, has event/local/manual policy drafts, has title-level
event-text preclassification hints, has title-level event-text sufficiency
gating, has URL/body fetchability evidence, has event-text Unknown
source-option gating, has DOCKCASE market-doc event evidence and review
packets, has local-structured Unknown
source-option closure routes, has explicit Unknown closure routes, has concrete
Unknown source-acquisition tasks, has local market-doc acquisition candidates
and false-positive rejects for the event-document Unknowns, has event-document
candidate adjudication before any Unknown can become valid score information,
has local formula input acquisition status for rent and product ASP, has local
formula review/probe gating for rent and product ASP, has current-source
capability boundaries for local formula blockers, has external/text business
metric acquisition status for frequency, penetration, and replacement, has
local DOCKCASE market-doc candidate snippets for those external business
metrics, has candidate-level review packets preserving missing
scope/denominator/period/unit/bounds/formula-policy fields, has a readiness
priority queue for P0/P1/P2 candidate review order, has review-only formula
policy draft templates for the P0 subset, has P0 numeric value-candidate
adjudication before any external business metric can become valid score
information, has review-only formula/bridge probes for the value shortlist,
and appears in the canonical review
queue while remaining blocked from runtime writes until an exact
approval-gate hash match exists, has risk-ranked approval packets, has
bulk-review approval candidates, has source-sample packets for bulk/event/
individual approvals, plus the exact next action needed to raise A-share
completion and the concrete packet bundle ready for human review.

| A-share score-trace item | Current status |
|---|---:|
| Spec dp_ids | 256 |
| Governance-participating spec dp_ids | 174 |
| A-share universe tickers | 1,641 |
| Runtime valid real dp_ids (`Known/Proxy`, non-`mock:`, non-empty value) | 143 |
| Runtime valid real direct-stock dp_ids | 115 |
| Runtime valid real sentinel-origin dp_ids (`MARKET:` / `INDUSTRY:`) | 28 |
| Runtime dp_ids convertible to numeric signal | 111 |
| Runtime numeric-signal direct-stock dp_ids | 85 |
| Runtime numeric-signal sentinel-origin dp_ids | 26 |
| Runtime dp_ids actually bridge-emitted into scoring nodes | 96 |
| Authored overlay score-candidate dp_ids | 28 |
| Effective score-path dp_ids (runtime bridge or overlay) | 121 |
| Direct base-score candidate dp_ids | 94 |
| Participating gaps | 53 |
| Blocking/actionable participating gaps | 32 |
| Governance/intentional participating gaps | 21 |
| All valid runtime but no numeric formula | 32 |
| Score-relevant valid runtime but no numeric formula | 18 |
| Actionable score-relevant formula gaps | 0 |
| Governance/intentional score-relevant formula gaps | 18 |
| Non-scoring valid runtime without numeric formula | 14 |
| Numeric runtime blocked by non-scoring overlay | 0 |
| Mock-only spec runtime dp_ids | 0 |

The former three conditional CLS/media blockers
(`L9.industry.compete_risk`, `L9.industry.policy_change`, and
`L9.media.report`) now have valid `Known` sentinel rows after the signed CLS
web refresh, so they are no longer waiting for source data. The bridge formulas
map beat/miss, block-trade event count/notional, M2 yoy changes, net analyst
upgrade/downgrade events, and high-precision positive/negative CLS media
headlines into `expectation_gap`; FX depreciation risk, CLS competition-risk
headlines, and the three L8 risk fields enter `risk_discount`;
high-precision supportive / restrictive policy headlines enter
`policy_sensitivity_multiplier`. Bucket A beat/miss now accepts
express net-profit, total-profit, operating-profit, or revenue yoy against the
forecast range, so it no longer depends only on `yoy_sales`. The Tushare `cn_m`
macro path now treats sub-0.3pct monthly M2 yoy changes as `Known` neutral and
maps material M2 yoy acceleration/deceleration into a bounded `expectation_gap`.
The Tushare `fx_daily` macro path now treats measurable non-risk RMB windows as
`Known` neutral and maps only above-threshold RMB depreciation into a non-zero
`risk_discount`.
The 2026-06-19 `tushare-macro` refresh proved `L9.macro.fx` and
`L9.macro.liquidity` as valid `Known` neutral sentinel-origin rows
(`MARKET:CN`), reducing actionable participating gaps from 45 to 43.
The 2026-06-19 `tushare-report-signals` sample refresh proved
`L9.media.analyst_action` as a valid `Known` neutral direct-stock row for
in-universe A-shares, reducing actionable participating gaps from 43 to 42.
The 2026-06-19 `tushare-industry-valuation` one-cycle refresh wrote 12
`Known` `INDUSTRY:* / L8.industry.valuation_compression` rows from Tushare
`daily_basic` PE history. The current 64-stock sample is neutral
(`compression_pct=9.0203`, below the alert threshold), so it contributes a
zero-risk sentinel signal and reduces actionable participating gaps from 42 to
41.
The 2026-06-19 `tushare-earnings-risk` one-cycle refresh wrote 768 rows across
256 sampled A-shares for `L5.surprise.beat_miss`,
`L8.fin.revenue_profit_miss`, and `L8.fin.goodwill_impairment`. It produced
90 valid beat/miss rows, 35 revenue/profit miss rows, and 1 goodwill
impairment row. The express semantics were corrected so `actual_yoy_pct` is
computed from current vs prior-period `n_income` / profit / revenue amounts
before scoring; local `yoy_net_profit` archive values can represent prior
period amounts, not percentages. This reduced actionable participating gaps
from 41 to 38.
The 2026-06-19 focused `akshare-block-trade` refresh wrote 1,641
`L9.capital.etf_block` rows. All were valid `Known` zero-event observations
for the current decoded `stock_dzjy_mrmx` window, so the runtime bridge maps
them to neutral `expectation_gap` and reduces actionable participating gaps
from 38 to 37.
The AKShare `stock_dzjy_mrmx` path now treats decoded per-stock zero-event
windows as `Known` neutral and maps non-zero event count/notional into a capped
`expectation_gap`; all-upstream-failed windows remain `Inactive`.
The focused `akshare-cls` refresh now bypasses the stale AKShare
`stock_info_global_cls` endpoint with the current signed
`cls.cn /v1/roll/get_roll_list` web API. The 2026-06-19 retry upserted four
`Known` `MARKET:CN` sentinel rows: `L9.media.report` saw 20 recent headlines,
`L9.industry.policy_change` saw 6 policy headlines with `net_policy_score=-1`,
`L9.industry.compete_risk` saw 3 risk headlines, and `L9.macro.geo` saw 5
geopolitical headlines. This cleared the former three
`conditional_formula_ready_pending_valid_data` blockers, raised effective
score-path dp_ids from 116 to 119, and moved `L8.shock.black_swan` from missing
dependency to event-candidate-ready.
The AKShare `stock_info_global_cls` competition-risk bucket now treats decoded
zero-risk windows as `Known` neutral and maps non-zero high-risk keyword hits
into a bounded `risk_discount`; upstream failures remain `Inactive`.
The AKShare `stock_info_global_cls` policy bucket now treats decoded zero or
ambiguous policy windows as `Known` neutral and maps only high-precision
supportive/restrictive policy terms into a bounded policy multiplier.
The AKShare `stock_info_global_cls` media-report bucket now treats decoded zero
or ambiguous media tilt as `Known` neutral; raw headline count remains
descriptive, and only high-precision positive/negative terms can enter
`expectation_gap` through `net_media_score`. Headlines already consumed by the
CLS policy or competition-risk buckets are excluded from media tilt to avoid
double-counting the same event.
Bucket B analyst action now also treats recent same-broker comparable unchanged
ratings as `Known` neutral (`action_type=none`), so a real no-action state can
enter the score path as 0 instead of remaining an Inactive gap.
Bucket A industry valuation-compression now treats valid 30d/90d industry PE
data below WARN/ERROR thresholds as `Known` neutral, so a real no-risk state can
also enter `risk_discount` as 0 after refresh.
Bucket A now also requests `goodwill` in the balancesheet cache, so
`L8.fin.goodwill_impairment` is no longer blocked by the local field list; its
remaining blocker is the next Tushare refresh plus real source availability or
an actual impairment event.

The old completion artifact remains useful for drift comparison, but its
headline "handled" count is weaker than the score-trace count: `Inactive`,
`Optionality`, and some overlay rows can be handled without carrying a current
numeric signal. Treat `a_share_score_trace_2026-06-18` as the current authority
when discussing whether a field can affect `final_score`.
The 2026-06-18 rerun also enforces strict JSON audit artifacts
(`allow_nan=False`); both score-trace and gap-priority JSON files pass
standard `JSON.parse` validation.

The current focused Tushare collector routes are:

- `tushare-core`: quotes, daily bars, daily basic, moneyflow, margin, HK
  holding, stock basics, and trading calendar fields.
- `tushare-market-env`: market-level sentinel rows such as
  `MARKET:CN / L7.env.market_trend`.
- `tushare-crowding`: history-backed crowdedness / percentile-style runtime
  fields.
- `tushare-report-rc`: sell-side forecast and revision fields from
  `report_rc`, with explicit `Inactive` rows when a forecast is unavailable or
  the account lacks permission.
- `tushare-report-signals`: narrow `report_rc` scoring-signal refresh for
  `L6.priced.analyst_revision`, `L7.mood.analyst_rating`, and
  `L9.media.analyst_action`, without the broader Bucket B daily-basic,
  hot-list, holder, and industry fan-out calls.
- `tushare-earnings-risk`: narrow `forecast + express + balancesheet` refresh
  for `L5.surprise.beat_miss`, `L8.fin.revenue_profit_miss`, and
  `L8.fin.goodwill_impairment`, with
  `TUSHARE_EARNINGS_RISK_SAMPLE_SIZE` controlling the low-frequency sample
  size.
- `tushare-industry-valuation`: narrow `daily_basic` PE-history refresh for
  `INDUSTRY:* / L8.industry.valuation_compression` sentinel rows, without the
  broader Bucket A financial statement calls.
- `tushare-preprice`: focused per-stock `forecast + daily` refresh for
  `L5.surprise.preprice`.
- `tushare-macro`: China macro and industry sentinel rows.

The current focused AKShare collector routes are:

- `akshare-block-trade`: narrow `stock_dzjy_mrmx` refresh for
  per-stock `L9.capital.etf_block`.
- `akshare-cls`: narrow CLS telegraph refresh for
  `MARKET:CN / L9.media.report`, `L9.industry.policy_change`, and
  `L9.industry.compete_risk`; it now uses the signed `cls.cn`
  `/v1/roll/get_roll_list` web API first and keeps `stock_info_global_cls` as a
  legacy fallback.

Fields landed or materially improved by the focused refresh:

- `L6.mult.pe` and `L6.mult.pb` from `tushare:daily_basic`.
- `L7.trade.volume_turnover` from `tushare:daily_basic`.
- `L7.flow.active_inflow` from `tushare:moneyflow`.
- `L7.env.market_trend` from `tushare:index_daily` on `MARKET:CN`.
- `L6.priced.crowdedness` from `tushare:daily_basic.history`.
- `L11.trade.signal` from deterministic `derive:l11_trade_signal` even when a
  stale `mock:*` row is present.
- `L5.fcst.revenue_margin`, `L5.fcst.eps_cf`, and `L5.fcst.revisions` from
  `tushare:report_rc` / derived report-forecast rows.
- `L5.surprise.preprice` from Tushare Bucket A `forecast + daily` history:
  the collector now emits `run_up_5d_pct`, `run_up_10d_pct`, and
  `run_up_20d_pct` as decimal ratios, and the realtime bridge maps the
  preferred 20d run-up into bounded `expectation_gap` with 10d/5d fallback.
  A focused `tushare-preprice` one-cycle refresh on 2026-06-18 wrote 1,641
  A-share rows: 39 `Known` and 1,602 explicit `Inactive`.
- `L10.industry.inventory_orders` and `L10.industry.sales_price` from the
  Tushare macro batch as `Proxy` industry confidence-validation rows.
  `inventory_orders` uses manufacturing PMI subindices (`new_orders`, backlog,
  finished-goods and raw-material inventory); `sales_price` uses national
  CPI/PPI price-index fields as a macro proxy, not industry ASP or sales
  volume. Both are scoped to relevant `INDUSTRY:<id>` sentinels and remain
  `confidence_multiplier` signals, not directional base-score formulas. A
  `tushare-macro` one-cycle refresh on 2026-06-18 wrote 18 `Proxy` rows for
  these two dp_ids into `runtime/hot.sqlite`, lifting the intermediate
  effective A-share score-path count from 105 to 107 before later fixes moved
  the current score-trace count to 108.
- Score bridge formulas for `L5.is.eps`, `L5.is.operating_profit`,
  `L5.fcst.eps_cf`, and `L5.fcst.revenue_margin` through peer-context or
  current-baseline comparisons, plus event/risk formulas for
  `L6.priced.discussion`, `L8.gov.insider_sell`, and
  `L8.gov.management_change`.
- `L9.capital.margin_anomaly` now converts Tushare `margin_detail.history`
  financing-buy acceleration into a bounded positive `expectation_gap` signal
  when the producer emits `WARN` / `ERROR`; it is distinct from
  `L8.cap.short_increase`, which reads short-balance pressure into
  `risk_discount`.
- `L9.media.report` now converts AKShare CLS `stock_info_global_cls` media
  headlines into `Known` neutral or a bounded `expectation_gap` only through
  conservative `net_media_score`; raw headline volume and policy/risk-bucket
  headlines are not scored directly.
- `L8.industry.valuation_compression` now has a focused Tushare
  `daily_basic` PE-history refresh. A 2026-06-19 one-cycle run wrote 12
  `Known` industry sentinel rows from 64 sampled A-shares; the current
  30d-vs-90d PE compression is below the alert threshold and maps to neutral
  `risk_discount` through the runtime bridge.
- `L5.surprise.beat_miss`, `L8.fin.revenue_profit_miss`, and
  `L8.fin.goodwill_impairment` now have a focused Tushare
  `forecast + express + balancesheet` refresh. A 2026-06-19 run with
  `TUSHARE_EARNINGS_RISK_SAMPLE_SIZE=256` wrote 768 rows and produced 90 / 35
  / 1 `Known` rows respectively. The beat/miss payload now computes true YoY
  percentages from current and prior-period express amounts before comparing
  against forecast ranges.
- `L9.capital.etf_block` now has a focused AKShare `stock_dzjy_mrmx` refresh.
  A 2026-06-19 run wrote 1,641 `Known` rows; the current decoded window has no
  per-stock block-trade events for the sampled universe, so it maps to neutral
  `expectation_gap`.
- `L7.mood.media_social` and `L9.media.social_buzz` remain intentionally
  non-direct formulas in the realtime bridge: the current Tushare adapter emits
  both from the same `ths_hot` heat row, and `media_social` is already consumed
  by the derived `L7.mood.fomo -> overheat_risk/risk_discount` path. Directly
  scoring them again would reuse the same hot-list evidence.

Rerun the A-share refresh and audit with:

```bash
TUSHARE_TIMEOUT_SECONDS=3 .venv/bin/python scripts/collector.py --source tushare-core --max-cycles 1
TUSHARE_TIMEOUT_SECONDS=3 .venv/bin/python scripts/collector.py --source tushare-market-env --max-cycles 1
TUSHARE_TIMEOUT_SECONDS=3 .venv/bin/python scripts/collector.py --source tushare-macro --max-cycles 1
TUSHARE_TIMEOUT_SECONDS=3 .venv/bin/python scripts/collector.py --source tushare-crowding --max-cycles 1
TUSHARE_TIMEOUT_SECONDS=3 .venv/bin/python scripts/collector.py --source tushare-report-rc --max-cycles 1
TUSHARE_TIMEOUT_SECONDS=3 .venv/bin/python scripts/collector.py --source tushare-report-signals --max-cycles 1
TUSHARE_TIMEOUT_SECONDS=3 TUSHARE_EARNINGS_RISK_SAMPLE_SIZE=256 .venv/bin/python scripts/collector.py --source tushare-earnings-risk --max-cycles 1
TUSHARE_TIMEOUT_SECONDS=3 .venv/bin/python scripts/collector.py --source tushare-industry-valuation --max-cycles 1
TUSHARE_TIMEOUT_SECONDS=3 .venv/bin/python scripts/collector.py --source tushare-preprice --max-cycles 1
AKSHARE_CALL_TIMEOUT_S=30 .venv/bin/python scripts/collector.py --source akshare-block-trade --max-cycles 1
AKSHARE_CALL_TIMEOUT_S=30 .venv/bin/python scripts/collector.py --source akshare-cls --max-cycles 1
AKSHARE_CALL_TIMEOUT_S=25 .venv/bin/python scripts/collector.py --source akshare --max-cycles 1
TUSHARE_TIMEOUT_SECONDS=3 .venv/bin/python scripts/collector.py --source tushare --max-cycles 1
.venv/bin/python -m mvp20.cli derive-snapshot --db runtime/hot.sqlite
.venv/bin/python -m mvp20.cli build-peer-context
.venv/bin/python scripts/check_a_share_spec_completion.py
.venv/bin/python scripts/audit_a_share_score_trace.py --sample-ts-code 300750.SZ
.venv/bin/python scripts/audit_a_share_score_gap_priority.py
.venv/bin/python scripts/audit_a_share_gap_candidate_evidence.py
.venv/bin/python scripts/audit_a_share_candidate_score_dry_run.py
.venv/bin/python scripts/audit_a_share_candidate_upsert_safety.py
.venv/bin/python scripts/audit_a_share_candidate_staging_payloads.py
.venv/bin/python scripts/audit_a_share_candidate_value_contracts.py
.venv/bin/python scripts/audit_a_share_spec_numeric_validity.py
.venv/bin/python scripts/audit_a_share_spec_score_conversion_path.py
.venv/bin/python scripts/audit_a_share_candidate_generation_queue.py
.venv/bin/python scripts/audit_a_share_l0_source_readiness.py
.venv/bin/python scripts/audit_a_share_short_report_evidence.py
.venv/bin/python scripts/audit_a_share_non_manual_candidate_readiness.py
.venv/bin/python scripts/audit_a_share_event_text_policy_drafts.py
.venv/bin/python scripts/audit_a_share_event_text_classification_inputs.py
.venv/bin/python scripts/audit_a_share_event_text_preclassification_screen.py
.venv/bin/python scripts/audit_a_share_event_text_sufficiency_gate.py
.venv/bin/python scripts/audit_a_share_event_text_url_fetchability.py
.venv/bin/python scripts/audit_a_share_event_text_unknown_source_options.py
.venv/bin/python scripts/audit_a_share_event_text_market_doc_evidence.py
.venv/bin/python scripts/audit_a_share_event_text_market_doc_review_packets.py
# Rerun after market-doc packets so event-text Known review drafts can consume them.
.venv/bin/python scripts/audit_a_share_event_text_policy_drafts.py
.venv/bin/python scripts/audit_a_share_local_structured_policy_drafts.py
.venv/bin/python scripts/audit_a_share_local_structured_unknown_source_options.py
.venv/bin/python scripts/audit_a_share_local_structured_source_candidates.py
.venv/bin/python scripts/audit_a_share_local_structured_source_review_packets.py
.venv/bin/python scripts/audit_a_share_local_structured_text_policy_drafts.py
.venv/bin/python scripts/audit_a_share_local_structured_text_unknown_source_options.py
.venv/bin/python scripts/audit_a_share_local_single_dependency_policy_drafts.py
.venv/bin/python scripts/audit_a_share_local_single_dependency_unknown_source_options.py
.venv/bin/python scripts/audit_a_share_manual_policy_draft_candidates.py
.venv/bin/python scripts/audit_a_share_manual_policy_unknown_source_options.py
.venv/bin/python scripts/audit_a_share_review_staging_manifest.py
.venv/bin/python scripts/audit_a_share_review_approval_gate.py
.venv/bin/python scripts/audit_a_share_completion_next_actions.py
.venv/bin/python scripts/audit_a_share_unknown_closure_matrix.py
.venv/bin/python scripts/audit_a_share_unknown_acquisition_backlog.py
.venv/bin/python scripts/audit_a_share_unknown_market_doc_acquisition_candidates.py
.venv/bin/python scripts/audit_a_share_unknown_event_evidence_adjudication.py
.venv/bin/python scripts/audit_a_share_unknown_event_strict_source_gate.py
.venv/bin/python scripts/audit_a_share_unknown_event_strict_review_packets.py
.venv/bin/python scripts/audit_a_share_unknown_event_primary_source_confirmation.py
.venv/bin/python scripts/audit_a_share_unknown_event_external_source_confirmation.py
.venv/bin/python scripts/audit_a_share_unknown_local_formula_acquisition_candidates.py
.venv/bin/python scripts/audit_a_share_unknown_local_formula_review_packets.py
.venv/bin/python scripts/audit_a_share_local_formula_source_capability.py
.venv/bin/python scripts/audit_a_share_unknown_external_business_metric_acquisition.py
.venv/bin/python scripts/audit_a_share_unknown_external_business_metric_market_doc_candidates.py
.venv/bin/python scripts/audit_a_share_unknown_external_business_metric_review_packets.py
.venv/bin/python scripts/audit_a_share_unknown_external_business_metric_readiness_queue.py
.venv/bin/python scripts/audit_a_share_unknown_external_business_metric_policy_drafts.py
.venv/bin/python scripts/audit_a_share_unknown_external_business_metric_value_candidates.py
.venv/bin/python scripts/audit_a_share_unknown_external_business_metric_value_review_packets.py
.venv/bin/python scripts/audit_a_share_unknown_penetration_value_priority.py
.venv/bin/python scripts/audit_a_share_unknown_penetration_p1_source_confirmation.py
.venv/bin/python scripts/audit_a_share_unknown_penetration_value_policy_draft.py
.venv/bin/python scripts/audit_a_share_approval_review_packets.py
.venv/bin/python scripts/audit_a_share_approval_packet_risk_review.py
.venv/bin/python scripts/audit_a_share_bulk_review_approval_candidates.py
.venv/bin/python scripts/audit_a_share_bulk_review_source_samples.py
.venv/bin/python scripts/audit_a_share_event_approval_source_samples.py
.venv/bin/python scripts/audit_a_share_individual_review_source_samples.py
.venv/bin/python scripts/audit_a_share_approval_source_sample_coverage.py
.venv/bin/python scripts/audit_a_share_approval_target_scope_readiness.py
.venv/bin/python scripts/audit_a_share_approval_materialization_plan.py
.venv/bin/python scripts/audit_a_share_approval_materialization_batch_plan.py
.venv/bin/python scripts/audit_a_share_approval_materialization_batch_codex_review.py
.venv/bin/python scripts/audit_a_share_approval_materialization_batch_approval_gate.py
.venv/bin/python scripts/audit_a_share_approval_materialization_batch_execution_preflight.py
.venv/bin/python scripts/audit_a_share_runtime_write_target_scope.py --scope-approvals-path /tmp/nonexistent_scope_approvals.json
.venv/bin/python scripts/audit_a_share_runtime_scope_approvals.py
.venv/bin/python scripts/audit_a_share_runtime_write_target_scope.py
.venv/bin/python scripts/audit_a_share_runtime_write_batch_plan.py
.venv/bin/python scripts/audit_a_share_runtime_write_batch_approvals.py
.venv/bin/python scripts/audit_a_share_runtime_write_batch_plan.py
.venv/bin/python scripts/audit_a_share_runtime_write_preflight.py
.venv/bin/python scripts/audit_a_share_score_field_closure.py
.venv/bin/python scripts/audit_goal_coverage.py
node -e "const fs=require('fs'); for (const p of ['docs/audit/a_share_score_trace_2026-06-18.json','docs/audit/a_share_score_gap_priority_2026-06-18.json','docs/audit/a_share_gap_candidate_evidence_2026-06-19.json','docs/audit/a_share_candidate_score_dry_run_2026-06-19.json','docs/audit/a_share_candidate_upsert_safety_2026-06-19.json','docs/audit/a_share_candidate_staging_payloads_2026-06-19.json','docs/audit/a_share_candidate_value_contracts_2026-06-19.json','docs/audit/a_share_spec_numeric_validity_2026-06-19.json','docs/audit/a_share_score_conversion_remediation_queue_2026-06-19.json','docs/audit/a_share_formula_policy_review_packets_2026-06-19.json','docs/audit/a_share_governance_suppression_verification_2026-06-19.json','docs/audit/a_share_option_universe_na_verification_2026-06-19.json','docs/audit/a_share_spec_score_conversion_path_2026-06-19.json','docs/audit/a_share_candidate_generation_queue_2026-06-19.json','docs/audit/a_share_l0_source_readiness_2026-06-19.json','docs/audit/a_share_short_report_evidence_2026-06-19.json','docs/audit/a_share_non_manual_candidate_readiness_2026-06-19.json','docs/audit/a_share_event_text_policy_drafts_2026-06-19.json','docs/audit/a_share_event_text_classification_inputs_2026-06-19.json','docs/audit/a_share_event_text_preclassification_screen_2026-06-19.json','docs/audit/a_share_event_text_sufficiency_gate_2026-06-19.json','docs/audit/a_share_event_text_url_fetchability_2026-06-19.json','docs/audit/a_share_event_text_unknown_source_options_2026-06-19.json','docs/audit/a_share_event_text_market_doc_evidence_2026-06-19.json','docs/audit/a_share_event_text_market_doc_review_packets_2026-06-19.json','docs/audit/a_share_local_structured_policy_drafts_2026-06-19.json','docs/audit/a_share_local_structured_unknown_source_options_2026-06-19.json','docs/audit/a_share_local_structured_source_candidates_2026-06-19.json','docs/audit/a_share_local_structured_source_review_packets_2026-06-19.json','docs/audit/a_share_local_structured_text_policy_drafts_2026-06-19.json','docs/audit/a_share_local_structured_text_unknown_source_options_2026-06-19.json','docs/audit/a_share_local_single_dependency_policy_drafts_2026-06-19.json','docs/audit/a_share_local_single_dependency_unknown_source_options_2026-06-19.json','docs/audit/a_share_manual_policy_draft_candidates_2026-06-19.json','docs/audit/a_share_manual_policy_unknown_source_options_2026-06-19.json','docs/audit/a_share_review_staging_manifest_2026-06-19.json','docs/audit/a_share_review_approval_gate_2026-06-19.json','docs/audit/a_share_completion_next_actions_2026-06-19.json','docs/audit/a_share_unknown_closure_matrix_2026-06-19.json','docs/audit/a_share_unknown_acquisition_backlog_2026-06-19.json','docs/audit/a_share_unknown_market_doc_acquisition_candidates_2026-06-19.json','docs/audit/a_share_unknown_event_evidence_adjudication_2026-06-19.json','docs/audit/a_share_unknown_event_strict_source_gate_2026-06-19.json','docs/audit/a_share_unknown_event_strict_review_packets_2026-06-19.json','docs/audit/a_share_unknown_event_primary_source_confirmation_2026-06-19.json','docs/audit/a_share_unknown_local_formula_acquisition_candidates_2026-06-19.json','docs/audit/a_share_unknown_local_formula_review_packets_2026-06-19.json','docs/audit/a_share_local_formula_source_capability_2026-06-19.json','docs/audit/a_share_unknown_external_business_metric_acquisition_2026-06-19.json','docs/audit/a_share_unknown_external_business_metric_market_doc_candidates_2026-06-19.json','docs/audit/a_share_unknown_external_business_metric_review_packets_2026-06-19.json','docs/audit/a_share_unknown_external_business_metric_readiness_queue_2026-06-19.json','docs/audit/a_share_unknown_external_business_metric_policy_drafts_2026-06-19.json','docs/audit/a_share_unknown_external_business_metric_value_candidates_2026-06-19.json','docs/audit/a_share_unknown_external_business_metric_value_review_packets_2026-06-19.json','docs/audit/a_share_unknown_penetration_value_priority_2026-06-19.json','docs/audit/a_share_unknown_penetration_p1_source_confirmation_2026-06-19.json','docs/audit/a_share_unknown_penetration_value_policy_draft_2026-06-19.json','docs/audit/a_share_approval_review_packets_2026-06-19.json','docs/audit/a_share_approval_packet_risk_review_2026-06-19.json','docs/audit/a_share_bulk_review_approval_candidates_2026-06-19.json','docs/audit/a_share_bulk_review_source_samples_2026-06-19.json','docs/audit/a_share_event_approval_source_samples_2026-06-19.json','docs/audit/a_share_individual_review_source_samples_2026-06-19.json','docs/audit/a_share_approval_source_sample_coverage_2026-06-19.json','docs/audit/a_share_approval_target_scope_readiness_2026-06-20.json','docs/audit/a_share_approval_materialization_plan_2026-06-20.json','docs/audit/a_share_approval_materialization_batch_plan_2026-06-20.json','docs/audit/a_share_approval_materialization_batch_codex_review_2026-06-20.json','docs/audit/a_share_approval_materialization_batch_approval_gate_2026-06-20.json','docs/audit/a_share_approval_materialization_batch_execution_preflight_2026-06-20.json','docs/audit/a_share_runtime_scope_approvals_2026-06-19.json','docs/audit/a_share_runtime_write_target_scope_2026-06-19.json','docs/audit/a_share_runtime_write_batch_plan_2026-06-19.json','docs/audit/a_share_runtime_write_batch_approvals_2026-06-19.json','docs/audit/a_share_runtime_write_preflight_2026-06-19.json','docs/audit/a_share_score_field_closure_2026-06-19.json','docs/audit/goal_coverage_2026-06-19.json']) JSON.parse(fs.readFileSync(p,'utf8'))"
node -e "const fs=require('fs'); JSON.parse(fs.readFileSync('docs/audit/a_share_unknown_event_external_source_confirmation_2026-06-19.json','utf8'))"
node -e "const fs=require('fs'); JSON.parse(fs.readFileSync('docs/audit/a_share_runtime_scope_approvals_2026-06-19.json','utf8'))"
node -e "const fs=require('fs'); JSON.parse(fs.readFileSync('docs/audit/a_share_runtime_write_target_scope_2026-06-19.json','utf8'))"
node -e "const fs=require('fs'); JSON.parse(fs.readFileSync('docs/audit/a_share_runtime_write_batch_plan_2026-06-19.json','utf8'))"
node -e "const fs=require('fs'); JSON.parse(fs.readFileSync('docs/audit/a_share_runtime_write_batch_approvals_2026-06-19.json','utf8'))"
node -e "const fs=require('fs'); JSON.parse(fs.readFileSync('docs/audit/a_share_runtime_write_preflight_2026-06-19.json','utf8'))"
```

`--source real` and `--source all` now dispatch through focused Tushare routes
including `tushare-macro` before Futu / FMP / AKShare instead of calling the
full Tushare adapter directly. That means normal runtime refreshes now include
the `L10.industry.inventory_orders` / `L10.industry.sales_price` industry
sentinels and the AKShare CLS/media refresh. Keep `--source tushare` for
low-frequency manual refreshes because it may call slower financial statement
endpoints.

The score-trace audit currently reports **zero mock-only spec runtime dp_ids**.
The remaining `--source mock` seeds (`L7.market.l2_quote`,
`L7.market.tick_count_5min`, `L9.event.intraday_block_trade`,
`L11.short_term`) are non-spec or non-scoring rows written with mock semantics,
so they are not counted as real score coverage.

The remaining A-share work is no longer a single "fill missing rows" bucket:
53 governance-participating dp_ids still lack an effective score path, but only
32 are now classified as blocking/actionable. The valid-real/no-formula bucket
is split by scoring relevance: 32 dp_ids have valid runtime values but no
numeric conversion, only 18 of those are score-relevant formula gaps, and all
18 are **design/governance** or **intentional-governance** items. There is no
remaining score-relevant field with valid real data that is a plain P0/P1/P2
"just add formula" repair. EPS, operating profit, forecast EPS, forecast
margin, discussion heat, insider sell, management change, margin-financing
anomaly, beat/miss surprises, block-trade event signals, macro FX/liquidity
changes, analyst rating actions, goodwill impairment, revenue/profit misses,
industry valuation-compression alerts, and CLS media headline tilt already enter
scoring through bounded formulas when valid events exist. Capex, segment
revenue share, and `L7.flow.block_trade` rows remain design items because their
direction is not safely monotonic from the current payload; hot-list social fields remain
governance/duplicate-review items because of the existing FOMO and same-source
`ths_hot` paths.

| A-share score-gap priority | Count | Meaning |
|---|---:|---|
| P0 direct formula, high coverage | 0 | No remaining high-coverage field is safe to wire directly without normalization, baseline comparison, or valuation context. |
| P1 event/sparse formula | 0 | The previous P1 event bucket was handled or reclassified; no high-confidence event formula remains. |
| P2 low-coverage formula | 0 | No remaining score-relevant formula gap is a low-coverage direct-formula repair; participating gaps still include 3 low-coverage data-validity items outside this narrowed formula bucket, all 3 of which already have conditional formulas ready. |
| P3 governance/design review | 18 | Do not directly wire as formulas without changing design: 6 valuation fields are peer-context suppressed, 3 valuation baseline fields require peer-context review, 3 are intentional data-only fields, 3 need business-semantics policy, 1 is a legacy alias duplicate, 1 is an already-derived FOMO bridge, and 1 is a same-source hot-list fallback duplicate. |

The gap-priority JSON now also emits `gap_bucket`, `intent_subtype`,
`blocking_gap`, `source_data_state`, and optional `replacement_dp_id` /
`canonical_dp_id` per row. It also emits
`conditional_formula_ready_pending_valid_data_dp_ids`; it is now empty after
the signed CLS web refresh, so current blockers are extraction/manual/design
items rather than formula-ready fields waiting for valid data.

The gap priority report is in
[`docs/audit/a_share_score_gap_priority_2026-06-18.md`](docs/audit/a_share_score_gap_priority_2026-06-18.md).
The candidate-evidence report is in
[`docs/audit/a_share_gap_candidate_evidence_2026-06-19.md`](docs/audit/a_share_gap_candidate_evidence_2026-06-19.md).
The score-field closure report is in
[`docs/audit/a_share_score_field_closure_2026-06-19.md`](docs/audit/a_share_score_field_closure_2026-06-19.md).
The candidate score dry-run report is in
[`docs/audit/a_share_candidate_score_dry_run_2026-06-19.md`](docs/audit/a_share_candidate_score_dry_run_2026-06-19.md).
The candidate upsert-safety report is in
[`docs/audit/a_share_candidate_upsert_safety_2026-06-19.md`](docs/audit/a_share_candidate_upsert_safety_2026-06-19.md).
The candidate staging-payload report is in
[`docs/audit/a_share_candidate_staging_payloads_2026-06-19.md`](docs/audit/a_share_candidate_staging_payloads_2026-06-19.md).
The candidate value-contract report is in
[`docs/audit/a_share_candidate_value_contracts_2026-06-19.md`](docs/audit/a_share_candidate_value_contracts_2026-06-19.md).
The spec score-conversion-path report is in
[`docs/audit/a_share_spec_score_conversion_path_2026-06-19.md`](docs/audit/a_share_spec_score_conversion_path_2026-06-19.md).
The candidate generation-queue report is in
[`docs/audit/a_share_candidate_generation_queue_2026-06-19.md`](docs/audit/a_share_candidate_generation_queue_2026-06-19.md).
The non-manual candidate readiness report is in
[`docs/audit/a_share_non_manual_candidate_readiness_2026-06-19.md`](docs/audit/a_share_non_manual_candidate_readiness_2026-06-19.md).
The event-text policy draft pilot report is in
[`docs/audit/a_share_event_text_policy_drafts_2026-06-19.md`](docs/audit/a_share_event_text_policy_drafts_2026-06-19.md).
The event-text classification input bundle is in
[`docs/audit/a_share_event_text_classification_inputs_2026-06-19.md`](docs/audit/a_share_event_text_classification_inputs_2026-06-19.md).
The event-text preclassification screen is in
[`docs/audit/a_share_event_text_preclassification_screen_2026-06-19.md`](docs/audit/a_share_event_text_preclassification_screen_2026-06-19.md).
The event-text sufficiency gate is in
[`docs/audit/a_share_event_text_sufficiency_gate_2026-06-19.md`](docs/audit/a_share_event_text_sufficiency_gate_2026-06-19.md).
The event-text URL/body fetchability audit is in
[`docs/audit/a_share_event_text_url_fetchability_2026-06-19.md`](docs/audit/a_share_event_text_url_fetchability_2026-06-19.md).
The event-text Unknown source-options audit is in
[`docs/audit/a_share_event_text_unknown_source_options_2026-06-19.md`](docs/audit/a_share_event_text_unknown_source_options_2026-06-19.md).
The event-text market-doc evidence scan is in
[`docs/audit/a_share_event_text_market_doc_evidence_2026-06-19.md`](docs/audit/a_share_event_text_market_doc_evidence_2026-06-19.md).
The event-text market-doc review packet bundle is in
[`docs/audit/a_share_event_text_market_doc_review_packets_2026-06-19.md`](docs/audit/a_share_event_text_market_doc_review_packets_2026-06-19.md).
The local structured policy draft pilot report is in
[`docs/audit/a_share_local_structured_policy_drafts_2026-06-19.md`](docs/audit/a_share_local_structured_policy_drafts_2026-06-19.md).
The local structured Unknown source-options audit is in
[`docs/audit/a_share_local_structured_unknown_source_options_2026-06-19.md`](docs/audit/a_share_local_structured_unknown_source_options_2026-06-19.md).
The local structured source-candidates audit is in
[`docs/audit/a_share_local_structured_source_candidates_2026-06-19.md`](docs/audit/a_share_local_structured_source_candidates_2026-06-19.md).
The local structured source-review packet bundle is in
[`docs/audit/a_share_local_structured_source_review_packets_2026-06-19.md`](docs/audit/a_share_local_structured_source_review_packets_2026-06-19.md).
The local structured-text policy draft pilot report is in
[`docs/audit/a_share_local_structured_text_policy_drafts_2026-06-19.md`](docs/audit/a_share_local_structured_text_policy_drafts_2026-06-19.md).
The local structured-text Unknown source-options audit is in
[`docs/audit/a_share_local_structured_text_unknown_source_options_2026-06-19.md`](docs/audit/a_share_local_structured_text_unknown_source_options_2026-06-19.md).
The local single-dependency policy draft pilot report is in
[`docs/audit/a_share_local_single_dependency_policy_drafts_2026-06-19.md`](docs/audit/a_share_local_single_dependency_policy_drafts_2026-06-19.md).
The local single-dependency Unknown source-options audit is in
[`docs/audit/a_share_local_single_dependency_unknown_source_options_2026-06-19.md`](docs/audit/a_share_local_single_dependency_unknown_source_options_2026-06-19.md).
The manual-policy draft pilot report is in
[`docs/audit/a_share_manual_policy_draft_candidates_2026-06-19.md`](docs/audit/a_share_manual_policy_draft_candidates_2026-06-19.md).
The manual-policy Unknown source-options audit is in
[`docs/audit/a_share_manual_policy_unknown_source_options_2026-06-19.md`](docs/audit/a_share_manual_policy_unknown_source_options_2026-06-19.md).
The review-staging manifest report is in
[`docs/audit/a_share_review_staging_manifest_2026-06-19.md`](docs/audit/a_share_review_staging_manifest_2026-06-19.md).
The deterministic runtime-approval audit report is in
[`docs/audit/a_share_deterministic_runtime_approvals_2026-06-19.md`](docs/audit/a_share_deterministic_runtime_approvals_2026-06-19.md),
with approval records in
[`docs/audit/a_share_review_approvals_2026-06-19.json`](docs/audit/a_share_review_approvals_2026-06-19.json).
The review-approval gate report is in
[`docs/audit/a_share_review_approval_gate_2026-06-19.md`](docs/audit/a_share_review_approval_gate_2026-06-19.md).
The completion next-action queue report is in
[`docs/audit/a_share_completion_next_actions_2026-06-19.md`](docs/audit/a_share_completion_next_actions_2026-06-19.md).
The Unknown closure matrix report is in
[`docs/audit/a_share_unknown_closure_matrix_2026-06-19.md`](docs/audit/a_share_unknown_closure_matrix_2026-06-19.md).
The Unknown acquisition backlog report is in
[`docs/audit/a_share_unknown_acquisition_backlog_2026-06-19.md`](docs/audit/a_share_unknown_acquisition_backlog_2026-06-19.md).
The Unknown market-doc acquisition candidate report is in
[`docs/audit/a_share_unknown_market_doc_acquisition_candidates_2026-06-19.md`](docs/audit/a_share_unknown_market_doc_acquisition_candidates_2026-06-19.md).
The Unknown event-evidence adjudication report is in
[`docs/audit/a_share_unknown_event_evidence_adjudication_2026-06-19.md`](docs/audit/a_share_unknown_event_evidence_adjudication_2026-06-19.md).
The Unknown event strict-source gate report is in
[`docs/audit/a_share_unknown_event_strict_source_gate_2026-06-19.md`](docs/audit/a_share_unknown_event_strict_source_gate_2026-06-19.md).
The Unknown event strict-review packet report is in
[`docs/audit/a_share_unknown_event_strict_review_packets_2026-06-19.md`](docs/audit/a_share_unknown_event_strict_review_packets_2026-06-19.md).
The Unknown event primary-source confirmation report is in
[`docs/audit/a_share_unknown_event_primary_source_confirmation_2026-06-19.md`](docs/audit/a_share_unknown_event_primary_source_confirmation_2026-06-19.md).
The Unknown event external-source confirmation report is in
[`docs/audit/a_share_unknown_event_external_source_confirmation_2026-06-19.md`](docs/audit/a_share_unknown_event_external_source_confirmation_2026-06-19.md).
The Unknown local formula acquisition candidate report is in
[`docs/audit/a_share_unknown_local_formula_acquisition_candidates_2026-06-19.md`](docs/audit/a_share_unknown_local_formula_acquisition_candidates_2026-06-19.md).
The Unknown local formula review-packet report is in
[`docs/audit/a_share_unknown_local_formula_review_packets_2026-06-19.md`](docs/audit/a_share_unknown_local_formula_review_packets_2026-06-19.md).
The local formula source-capability report is in
[`docs/audit/a_share_local_formula_source_capability_2026-06-19.md`](docs/audit/a_share_local_formula_source_capability_2026-06-19.md).
The Unknown external business metric acquisition report is in
[`docs/audit/a_share_unknown_external_business_metric_acquisition_2026-06-19.md`](docs/audit/a_share_unknown_external_business_metric_acquisition_2026-06-19.md).
The Unknown external business metric market-doc candidate report is in
[`docs/audit/a_share_unknown_external_business_metric_market_doc_candidates_2026-06-19.md`](docs/audit/a_share_unknown_external_business_metric_market_doc_candidates_2026-06-19.md).
The Unknown external business metric review-packet bundle is in
[`docs/audit/a_share_unknown_external_business_metric_review_packets_2026-06-19.md`](docs/audit/a_share_unknown_external_business_metric_review_packets_2026-06-19.md).
The Unknown external business metric readiness queue is in
[`docs/audit/a_share_unknown_external_business_metric_readiness_queue_2026-06-19.md`](docs/audit/a_share_unknown_external_business_metric_readiness_queue_2026-06-19.md).
The Unknown external business metric policy-draft bundle is in
[`docs/audit/a_share_unknown_external_business_metric_policy_drafts_2026-06-19.md`](docs/audit/a_share_unknown_external_business_metric_policy_drafts_2026-06-19.md).
The Unknown external business metric value-candidate adjudication report is in
[`docs/audit/a_share_unknown_external_business_metric_value_candidates_2026-06-19.md`](docs/audit/a_share_unknown_external_business_metric_value_candidates_2026-06-19.md).
The Unknown external business metric value-review packet report is in
[`docs/audit/a_share_unknown_external_business_metric_value_review_packets_2026-06-19.md`](docs/audit/a_share_unknown_external_business_metric_value_review_packets_2026-06-19.md).
The Unknown business-metric value-selection gate report is in
[`docs/audit/a_share_unknown_business_metric_value_selection_gate_2026-06-19.md`](docs/audit/a_share_unknown_business_metric_value_selection_gate_2026-06-19.md).
The Unknown penetration value-confirmation packet report is in
[`docs/audit/a_share_unknown_penetration_value_confirmation_packets_2026-06-19.md`](docs/audit/a_share_unknown_penetration_value_confirmation_packets_2026-06-19.md).
The Unknown penetration value-confirmation template bundle report is in
[`docs/audit/a_share_unknown_penetration_value_confirmation_templates_2026-06-19.md`](docs/audit/a_share_unknown_penetration_value_confirmation_templates_2026-06-19.md).
The Unknown penetration value-confirmation gate report is in
[`docs/audit/a_share_unknown_penetration_value_confirmation_gate_2026-06-19.md`](docs/audit/a_share_unknown_penetration_value_confirmation_gate_2026-06-19.md).
The Unknown penetration confirmed Known-draft report is in
[`docs/audit/a_share_unknown_penetration_confirmed_known_drafts_2026-06-19.md`](docs/audit/a_share_unknown_penetration_confirmed_known_drafts_2026-06-19.md).
The approval review packet bundle is in
[`docs/audit/a_share_approval_review_packets_2026-06-19.md`](docs/audit/a_share_approval_review_packets_2026-06-19.md).
The approval target-scope readiness report is in
[`docs/audit/a_share_approval_target_scope_readiness_2026-06-20.md`](docs/audit/a_share_approval_target_scope_readiness_2026-06-20.md).
The approval materialization plan report is in
[`docs/audit/a_share_approval_materialization_plan_2026-06-20.md`](docs/audit/a_share_approval_materialization_plan_2026-06-20.md).
The approval materialization batch-plan report is in
[`docs/audit/a_share_approval_materialization_batch_plan_2026-06-20.md`](docs/audit/a_share_approval_materialization_batch_plan_2026-06-20.md).
The approval materialization Codex batch-review report is in
[`docs/audit/a_share_approval_materialization_batch_codex_review_2026-06-20.md`](docs/audit/a_share_approval_materialization_batch_codex_review_2026-06-20.md).
The approval materialization batch approval-gate report is in
[`docs/audit/a_share_approval_materialization_batch_approval_gate_2026-06-20.md`](docs/audit/a_share_approval_materialization_batch_approval_gate_2026-06-20.md).
The approval materialization execution-preflight report is in
[`docs/audit/a_share_approval_materialization_batch_execution_preflight_2026-06-20.md`](docs/audit/a_share_approval_materialization_batch_execution_preflight_2026-06-20.md).
The runtime scope approval report is in
[`docs/audit/a_share_runtime_scope_approvals_2026-06-19.md`](docs/audit/a_share_runtime_scope_approvals_2026-06-19.md).
The runtime write target-scope report is in
[`docs/audit/a_share_runtime_write_target_scope_2026-06-19.md`](docs/audit/a_share_runtime_write_target_scope_2026-06-19.md).
The runtime write controlled batch-plan report is in
[`docs/audit/a_share_runtime_write_batch_plan_2026-06-19.md`](docs/audit/a_share_runtime_write_batch_plan_2026-06-19.md).
The runtime write batch-approval report is in
[`docs/audit/a_share_runtime_write_batch_approvals_2026-06-19.md`](docs/audit/a_share_runtime_write_batch_approvals_2026-06-19.md).
The runtime write preflight report is in
[`docs/audit/a_share_runtime_write_preflight_2026-06-19.md`](docs/audit/a_share_runtime_write_preflight_2026-06-19.md).
These reports are read-only. Candidate-evidence only packages runtime dependency
evidence and keeps `safe_to_upsert_without_review=0`; field-closure verifies
whether each target field reaches the production score path; dry-run verifies
whether bridge-compatible placeholder payloads can pass `_realtime_signal` and
`synthesize_realtime_nodes`; upsert-safety verifies runtime-write eligibility
and keeps all current candidate rows review-gated/staging-only;
staging-payloads prepares review envelopes while allowing 0 production writes.
Value-contracts validates every staging envelope and rejects bad future
generator outputs before they can be treated as Known candidates; generation
queue packages the 32 remaining placeholders into executable generator tasks;
non-manual readiness validates the 28 local/event task inputs and bridge
contract probes without generating deterministic Known drafts;
event-text policy drafts use local market-doc packets to emit 10 / 12
review-only Known event rows, validate 12 / 12 draft contracts, bridge-validate
10 / 10 Known drafts, keep 2 rows Unknown, and still allow 0 production writes;
event-text classification inputs package all 12 event rows with 78 headline
inputs / 8 unique titles, but 0 full-text packets and 0 classified Known
outputs;
local structured policy drafts emit review-only Known values for 6 / 10
structured rows, validate 10 / 10 draft contracts, keep 4 fields Unknown, flag
0 invalid contracts, bridge-validate 6 Known drafts, and still allow 0
production writes;
local structured source-candidates check those 4 Unknown fields against
DOCKCASE/Tushare semantics, find 0 direct Known-ready rows, keep rent and ASP
as review/supporting candidates only, reject 407 market/trading/shareholder
false positives, and still allow 0 production writes;
local structured source-review packets package those 4 Unknown fields, keep 0
direct Known-ready and 0 formula-ready packets, validate 4 / 4 packet
contracts, and still allow 0 production writes;
local structured-text policy drafts emit review-only Known values for 3 / 3
structured-text rows, keep 0 fields Unknown, validate 3 / 3 draft contracts,
flag 0 invalid contracts, bridge-validate 3 Known drafts, and still allow 0
production writes;
local single-dependency policy drafts emit review-only Known values for 2 / 3
single-dependency rows, validate 3 / 3 draft contracts, keep replacement demand
Unknown, flag 0 invalid contracts, and still allow 0 production writes;
manual-policy draft pilot emits review-only draft values for 4 / 4 queued
manual-policy tasks, validates 4 / 4 draft contracts, and keeps 0 manual-policy
rows Unknown; review-staging manifest now tracks the 32 post-execution blockers
in one canonical review queue with 25 concrete review-ready packets, 7
review-gated Unknown packets, 32 / 32 contracts valid, 25 concrete bridge-ready
packets, 0 safe auto-upsert, 0 production writes, and 0 approved runtime writes;
deterministic runtime approvals create 2 contract-valid approval records for
`L9.media.short_report` and `L7.trade.gamma`, leave 32 non-deterministic rows
unapproved, and keep production writes at 0; review-approval gate requires
explicit approval for the 25 concrete packets, sees 2 historical approval
records, leaves 25 missing approvals, rejects 2 stale records, approves 0
runtime writes into the current read-only write plan, produces 0 write-plan
entries, and keeps 7 Unknown
packets not approvable; completion next-actions split the remaining work into
25 human approval reviews, 0 runtime-write-plan-ready packets, 2 event-text
classifications, 4 local structured mappings, 0 structured-text extractions, 1
single-dependency policy, 0 DCF assumption reviews, and 0 approval payload hash
mismatches; Unknown closure matrix
assigns all 7 review-gated Unknown
  rows to explicit closure routes, leaves 0 missing routes, keeps 0 auto
  Known-ready rows and 0 approval-ready Unknown rows, validates 7 / 7 closure
  contracts, and allows 0 production writes; Unknown acquisition backlog turns
  those rows into 7 source-acquisition tasks split into 2 market-doc searches, 2
  local formula-source tasks, and 3 external/text business-metric tasks, with 0
  auto Known-ready tasks and 0 production writes; Unknown market-doc acquisition
  candidates execute the 2 event-document tasks across 14,956 local HTML files,
  find 2 rows with review candidates, retain 6 new-entrant review snippets and
  3 substitute-tech clean-risk snippets, reject 34 false positives, keep 0
  Known-draft-sufficient rows, and allow 0 production writes; Unknown
  event-evidence adjudication reviews the 2 retained event Unknown rows and 14
  candidate examples, accepts 0, rejects or marks ambiguous 14, keeps both rows
  Unknown, validates 2 / 2 adjudication contracts, and allows 0 production
  writes; Unknown event strict-source gate then narrows the next review queue by
  rescanning 14,956 local HTML files and finding 11 strict candidates, including
  8 review candidates and 3 rejected contexts, but classifier-ready,
  Known-draft-sufficient, approval-ready, runtime writes, and production writes
  all remain 0; Unknown event strict-review packets then triage those 8 review
  candidates into 2 low-confidence community/forum leads requiring primary
  source confirmation and 6 deterministic rejections, with 0 classifier-ready,
  Known-draft-sufficient, approval-ready, or production-write packets; Unknown
  event primary-source confirmation then scans 14,956 local HTML files for those
  2 leads, finds 12 local candidates but 0 local high-quality confirmations, so
  both rows have only supporting context and still require external/primary
  evidence or governed NotApplicable/Unavailable resolution; Unknown event
  external-source confirmation then packages 2 rows into 6 public-source cards,
  including 2 external confirmation candidates and 4 supporting-context cards,
  but classifier-ready, Known-draft-sufficient, approval-ready, runtime writes,
  and production writes all remain 0 pending review; Unknown local
  formula acquisition candidates execute the rent and ASP
  formula-source tasks,
  check 6 existing sample CSV files with 0 read errors, find 2 rows with
  candidate numerators, keep 0 / 8 formula input groups ready, find 0 direct
  denominator rows, 0 quantity/price-index rows, 0 formula-policy rows, 0
  Known-draft-ready rows, and allow 0 production writes; Unknown external
  business metric acquisition candidates execute the frequency, penetration,
  and replacement tasks, find 3 runtime dependency-ready rows and 7 overlay
  hints, keep 0 / 12 business metric groups ready, find 0 direct business
  metric sources, require external/text evidence for all 3 rows, exclude 238
  false positives, keep 0 metric-ready and 0 Known-draft-ready rows, and allow
  0 production writes; Unknown external business metric market-doc candidates
  scan 14,956 local HTML files with 0 read errors, find review candidates for
  all 3 rows, retain 178 candidate documents, 99 review candidates, 49 numeric
  review candidates, 50 textual review candidates, 82 weak candidates, and 72
  rejected candidates, but keep 0 Known-draft-sufficient rows, 0 metric-ready
  rows, and 0 production writes; Unknown external business metric review
  packets convert all 99 retained review candidates into packets, including 49
  numeric packets and 50 textual packets across all 3 rows, but still keep 0
  metric-ready packets, 0 Known-draft-sufficient packets, and 0 production
  writes; Unknown external business metric readiness queue splits those packets
  into 18 P0 formula-policy-only candidates, 52 P1 period/unit-required
  candidates, and 29 P2 denominator-required candidates, while all 99 still
  miss reviewed bounds and formula policy and keep 0 metric-ready packets;
  Unknown external business metric policy drafts convert the 18 P0 packets into
  review-only value JSON templates, but still select no raw value and keep 0
  metric-ready drafts, 0 Known-draft-sufficient drafts, and 0 production writes;
  Unknown external business metric value-candidate adjudication screens those
  18 P0 drafts, finds 9 rows with value-candidate tokens, 13 candidate value
  tokens, 31 rejected numeric tokens, 6 shortlist rows requiring review, 3
  scope-rejected rows, 9 rows with no scoreable numeric candidate, 0
  metric-ready rows, 0 Known-draft-sufficient rows, and 0 production writes;
  Unknown external business metric value-review packets convert the 6 shortlist
  rows into 6 review packets with 8 candidate value options, all 8 bridge-probe
  ready for the final-score path, but select 0 raw values and keep 0
  metric-ready, 0 Known-draft-sufficient, 0 approval-ready, and 0 production
  writes; Unknown business-metric value-selection gate checks 3 rows, 6
  value-review packets, and 8 bridge-ready candidate options, marks 0 rows
  needing generic value-selection review, 1 value-policy-draft-ready row, and 1
  proposed value JSON, keeps 2 rows source-metric-missing, selects 0 values,
  keeps 0 Known-draft-sufficient / approval-ready rows, validates 3 / 3
  selection contracts, and allows 0 production writes; Unknown penetration
  value-confirmation packets package 1 review-required packet, include 1 blank
  confirmation template, validate 1 template contract and 1 packet contract,
  keep 0 Known-draft-sufficient / approval-ready rows, and allow 0 production
  writes; Unknown penetration value-confirmation template bundle extracts 1
  blank/pending template from packets, validates 1 blank template contract, sees
  0 confirmed templates, and keeps 0 Known-draft-sufficient rows, 0
  approval-ready rows, 0 runtime writes, and 0 production writes; Unknown
  penetration value-confirmation gate checks 1 packet, sees 0 confirmation
  records, marks 1 confirmation missing, keeps 0 confirmed value policies, 0
  Known-draft candidates, and 0 production writes; Unknown penetration confirmed
  Known-draft emitter checks 1 confirmation-gate row, sees 0 confirmed
  value-policy candidates, emits 0 Known drafts, blocks 1 row, marks 0 ready for
  review staging, and allows 0 production writes;
  approval review packets isolate the 25 concrete packets with payload hashes,
  value JSON, evidence refs, bridge checks, 25 incomplete approval templates,
  0 approved read-only write-plan entries, 0 skipped bridge/contract-not-ready
  rows, and 0 approval payload hash mismatches; goal coverage reports 0
  approval cross-report consistency errors.
The current candidate split is:

| Candidate evidence status | Count | Meaning |
|---|---:|---|
| `ready_for_local_llm_candidate` | 15 | Financial/runtime dependencies are present at compatible stock-level grain. |
| `ready_for_local_llm_candidate_with_grain_join` | 1 | `L0.price.contract_spot` has an explicit stock-to-industry raw-material join policy covering 1007 mapped A-share universe rows. |
| `ready_for_event_llm_candidate` | 12 | Runtime media/policy/competition/geo event dependencies are present for local event classification. |
| `ready_for_web_event_candidate` | 1 | `L9.media.short_report` has a dedicated DOCKCASE news scan: 14,956 HTML files, 4 strict foreign/market-only short-report documents, and 0 direct A-share hits; active A-share events must stay neutral/Unknown unless direct evidence appears. |
| `ready_for_manual_design_candidate` | 5 | DCF, realization risk, reflex tag, gamma, and risk-off slope now have explicit governed candidate policies; they still require review before any score-affecting runtime write. |

The current upsert-safety split is:

| Upsert-safety class | Count | Meaning |
|---|---:|---|
| `review_required` | 32 | Candidate evidence and bridge contract are ready, but generated target values, assumptions, rationale, evidence refs, and bounds still require review before staging. |
| `neutral_candidate_review_required` | 1 | `L9.media.short_report` has 0 direct A-share short-report hits, so only reviewed neutral/Unknown output is eligible for staging unless direct A-share evidence appears. |
| `not_applicable_candidate_review_required` | 1 | `L7.trade.gamma` is A-share single-stock NotApplicable/neutral unless reviewed direct/proxy option evidence exists. |
| `blocked` | 0 | No current candidate row is blocked at the safety-audit layer; blocked cases remain covered for missing dry-run rows, non-final targets, missing inputs, or failed bridge nodes. |

The current staging-payload split is:

| Staging payload status | Count | Meaning |
|---|---:|---|
| `deterministic_neutral_review_payload` | 1 | `L9.media.short_report` has a complete neutral/none-observed review payload because direct A-share short-report hits are 0. |
| `deterministic_not_applicable_review_payload` | 1 | `L7.trade.gamma` has a NotApplicable/neutral review payload with `multiplier=1.0` and explicit A-share single-stock applicability rationale. |
| `requires_generator_output` | 32 | The remaining rows get complete `Unknown` / `review_required` envelopes and require governed local/event/manual candidate generation before a Known payload can be staged. |

The current value-contract split is:

| Value contract status | Count | Meaning |
|---|---:|---|
| valid concrete review payload | 2 | `L9.media.short_report` and `L7.trade.gamma` pass schema/bounds/evidence/rationale checks and re-run through the production bridge. |
| valid placeholder contract | 32 | Generator-required rows have complete `Unknown` / `review_required` envelopes; they do not produce a scoring signal until a bounded Known value is generated and reviewed. |
| invalid contract | 0 | No current staging envelope is missing required fields or violating bounds. |

The current generation-queue split is:

| Generation task kind | Count | Meaning |
|---|---:|---|
| `event_llm_candidate` | 12 | Runtime media/policy/competition/geo event evidence must be classified into bounded event or risk candidate values. |
| `local_llm_candidate` | 16 | Financial/runtime dependency evidence must be converted into bounded local closed-loop candidate values. |
| `manual_policy_candidate` | 4 | DCF, realization risk, reflexivity, and risk-off slope need governed policy/model outputs before approved Known staging/runtime values. |

The current non-manual readiness split is:

| Non-manual readiness status | Count | Meaning |
|---|---:|---|
| `event_text_classification_required` | 12 | First-pass runtime media/policy/competition/geo evidence requires event review; the later market-doc-aware policy pilot converts 10 of these into review-only Known drafts. |
| `local_structured_llm_required` | 10 | Structured financial/runtime dependencies are materially known, but business mapping still needs governed local closed-loop generation. |
| `local_structured_text_llm_required` | 3 | Structured dependencies are mixed with IR/QA or text evidence, so extraction and scoring direction still need governed review. |
| `local_single_dependency_policy_required` | 3 | A single structured dependency is present, but a policy mapping is needed before emitting a Known score. |
| bridge probes ready | 28 | Every non-manual task can reach a final-score-ready realtime node once a reviewed value is emitted. |
| deterministic Known drafts allowed | 0 | No local/event row is safe to auto-convert into a Known draft without LLM/policy review. |

The current event-text policy draft split is:

| Event-text draft status | Count | Meaning |
|---|---:|---|
| `draft_known_market_doc_review_required` | 10 | Local market-doc snippets support bounded review-only Known drafts for `L0.compete.price_war`, `L0.compete.share_concentration`, `L0.policy.access_license`, `L0.policy.regulation`, `L0.policy.subsidy`, `L0.policy.tax_trade`, `L0.tech.ai_automation`, `L0.tech.breakthrough`, `L8.shock.black_swan`, and `L8.shock.supply_break`. |
| `unknown_market_doc_clean_evidence_required` | 1 | `L0.tech.substitute_tech` has retained substitution-keyword snippets, but 0 / 5 pass the clean negative-risk filter after excluding domestic import-substitution opportunity, overseas macro substitution, trade-law replacement, and broad non-A-share commentary. |
| `unknown_market_doc_evidence_required` | 1 | `L0.compete.new_entrant` still needs a direct same-source A-share/industry transmission link. |
| draft contracts valid | 12 | Every event-text pilot envelope has target/score fields, evidence refs, rationale, review-required status, and no write permission. |
| invalid draft contracts | 0 | No event-text pilot draft violates the review-only contract. |
| Known drafts bridge-ready | 10 | Every event-text Known draft has a bounded `value_json.score` and reaches a final-score target through the realtime bridge. |
| safe to upsert without review | 0 | No event-text draft is eligible for unreviewed runtime upsert. |
| production writes allowed | 0 | Pilot drafts are not approved staging/runtime writes. |

The current event-text classification input split is:

| Event-text classification input status | Count | Meaning |
|---|---:|---|
| classification input packets | 12 | The first-pass event-text rows have classifier/reviewer input packets before market-doc promotion. |
| input-ready packets | 12 | Each packet has at least one headline/title input from current runtime dependencies. |
| missing headline input | 0 | No event-text packet is blocked by missing title-level evidence. |
| headline inputs | 78 | Total dependency/headline references across the 12 packets, including duplicates by target field. |
| unique headlines | 8 | Current CLS/runtime inputs are broad and repeated across multiple target fields. |
| full article text packets | 0 | Current packets contain title-level evidence only; no article body text is available in this audit. |
| title-level-only packets | 12 | This title-level layer alone is not sufficient for direct Known promotion. |
| classified Known packets | 0 | The title-level classification input bundle itself emits no Known score value; 10 Known review drafts are emitted later by the market-doc-aware policy pilot. |
| production writes allowed | 0 | The classification input bundle is read-only and does not mutate scores. |

The current event-text Unknown source-options split is:

| Event-text Unknown source option | Count | Meaning |
|---|---:|---|
| Unknown rows reviewed | 2 | Remaining event-text Unknown rows were reviewed after local market-doc policy promotion. |
| classification inputs ready | 2 | Every remaining row has a bounded classifier/reviewer input packet from current runtime media/policy/competition/geo evidence. |
| body text available | 2 | The URL/body fetchability audit fetched primary CLS text for every remaining event-text packet. |
| target-event evidence present | 0 | No remaining packet contains enough direct body evidence for the target event concept. |
| direct A-share transmission present | 0 | No packet currently links the target event to direct A-share, listed-company, industry, supply-chain, trade, FX, or policy transmission. |
| broad-market-only transmission | 2 | Current transmission hits are broad China A50/futures context and are not enough for Known scoring values. |
| classifier-ready review candidates | 0 | No row has enough target-event plus direct-transmission evidence to enter classifier promotion. |
| target-event evidence required | 2 | Both rows still need stronger target-event evidence before direction/magnitude review. |
| direct A-share transmission required | 0 | No current event-text Unknown row has target-event evidence that only lacks direct A-share transmission evidence. |
| auto Known candidates | 0 | No event-text row can be promoted automatically from current title/body text alone. |
| production writes allowed | 0 | This audit is read-only and does not mutate `realtime_current`. |

The current event-text DOCKCASE market-doc evidence split is:

| Event-text market-doc evidence | Count | Meaning |
|---|---:|---|
| Unknown rows checked | 12 | The first-pass event-text rows are searched against the local DOCKCASE market HTML corpus. |
| market HTML files scanned | 14,956 | The scan covers local `market_data/news/**/*.html`, not external web crawling. |
| read errors | 0 | All selected market HTML files were readable. |
| rows with target evidence | 12 | Each event-text row has at least one market document matching its target-event keyword set. |
| rows with direct transmission evidence | 12 | Each row has at least one market document with direct transmission keywords such as A-share, listed-company, sector, supply-chain, trade, or import/export context. |
| rows with target+direct same-document evidence | 12 | Each row has at least one document containing both target-event and direct-transmission evidence. |
| same-sentence review candidates | 11 | Eleven rows have tighter same-sentence target/direct candidates suitable for reviewer/classifier packets. |
| target evidence still required | 0 | The local market-doc corpus removes the previous target-evidence search gap. |
| direct-transmission link still required | 1 | `L0.compete.new_entrant` still needs a same-sentence direct transmission link. |
| market-doc review candidates | 11 | Candidate snippets are review inputs only; they are not automatic Known values. |
| auto Known candidates | 0 | No market-doc hit can be promoted automatically without classification and review. |
| production writes allowed | 0 | This audit is read-only and does not mutate `realtime_current`. |

The current event-text market-doc review packet split is:

| Event-text market-doc review packet | Count | Meaning |
|---|---:|---|
| packets packaged | 12 | Every first-pass event-text row has a conservative classifier/reviewer packet. |
| market-doc review-ready | 11 | Eleven rows have same-sentence target/direct-transmission candidate examples ready for classification review. |
| target-event evidence required | 0 | The market-doc corpus supplies target-event evidence for every row. |
| direct-transmission link required | 1 | `L0.compete.new_entrant` still lacks a same-sentence direct A-share transmission link. |
| retained candidate examples | 53 | Candidate snippets are bounded for review and are not treated as final facts. |
| packet contracts valid | 12 | Every packet keeps `data_status=Unknown`, `review_required`, and no write permission. |
| invalid packet contracts | 0 | No packet violates the review-only contract. |
| auto Known candidates | 0 | The packet layer itself does not classify direction/magnitude or emit Known score values; the later policy pilot consumes selected packets. |
| production writes allowed | 0 | This audit is read-only and does not mutate `realtime_current`. |

The current local structured policy draft split is:

| Local structured draft status | Count | Meaning |
|---|---:|---|
| `draft_known_review_required` | 5 | `L0.cost.cac`, `L0.cost.labor`, `L0.demand.terminal`, `L0.supply.capacity`, and `L0.supply.chain_eff` now have bounded review-only Known drafts that pass the production bridge. |
| `draft_known_pass_through_review_required` | 1 | `L0.price.contract_spot` has a bounded review-only pass-through draft from raw-material futures, gross margin, and the explicit grain-join policy. |
| `unknown_policy_required` | 4 | `L0.cost.rent`, `L0.demand.frequency`, `L0.demand.penetration`, and `L0.price.product_asp` stay Unknown because the current dependencies do not identify the required business decomposition. |
| draft contracts valid | 10 | Every pilot envelope has target/score fields, value bounds, evidence refs, rationale, review-required status, and no write permission. |
| invalid draft contracts | 0 | No local structured pilot draft violates the review-only contract. |
| Known drafts bridge-ready | 6 | All six Known structured drafts produce final-score-ready realtime nodes. |
| safe to upsert without review | 0 | No local structured draft is eligible for unreviewed runtime upsert. |
| production writes allowed | 0 | Pilot drafts are not approved staging/runtime writes and do not reduce the 32 score-completion blockers by themselves. |

The current local structured source-candidates split is:

| Local structured source candidate | Count | Meaning |
|---|---:|---|
| Unknown dp_ids checked | 4 | `L0.cost.rent`, `L0.demand.frequency`, `L0.demand.penetration`, and `L0.price.product_asp` were checked against the current DOCKCASE/Tushare CSV semantic catalog. |
| runtime dependencies ready | 4 | The existing runtime dependency packs are present, but they do not directly contain the missing business fields. |
| direct Known-ready rows | 0 | No current catalog row can be converted into a score-affecting Known value without reviewed mapping or extraction. |
| review/source candidate rows | 2 | `L0.cost.rent` has a lease-burden proxy candidate and `L0.price.product_asp` has product-mix / revenue context. |
| review candidate matches | 1 | `use_right_asset_dep` in Tushare cashflow can support lease-burden review, but it is not rent expense. |
| supporting candidate matches | 4 | `fina_mainbz` fields `bz_item`, `bz_sales`, `bz_cost`, and `bz_profit` can support product mix / ASP numerator review, but not unit ASP. |
| empty candidate matches | 1 | `fa_fnc_leases` exists in the cashflow schema but is empty in the sampled semantic rows. |
| no direct catalog source rows | 2 | `L0.demand.frequency` and `L0.demand.penetration` still need order/usage/customer or TAM/share/installed-base sources. |
| excluded false-positive matches | 407 | Stock prices, turnover, trading volume, share capital, holder counts, index weights, and market ratios are explicitly rejected as substitutes. |
| production writes allowed | 0 | This audit is read-only and does not mutate `realtime_current`. |

The current local structured source-review packet split is:

| Local structured source-review packet | Count | Meaning |
|---|---:|---|
| source-review packets | 4 | All four local structured Unknown rows are packaged as reviewer-facing source packets. |
| `review_candidate_ready` | 1 | `L0.cost.rent` has `use_right_asset_dep` as a lease-burden proxy candidate, but still needs a reviewed formula and denominator. |
| `supporting_candidate_needs_quantity_source` | 1 | `L0.price.product_asp` has `fina_mainbz` product-mix / revenue-cost support, but still needs unit volume, shipment volume, or a governed price index. |
| `external_source_required` | 2 | `L0.demand.frequency` and `L0.demand.penetration` require external business sources or text/web extraction. |
| direct Known-ready packets | 0 | No packet can become a Known score value from current structured catalog evidence alone. |
| formula-ready packets | 0 | Every packet is missing required formula inputs such as rent expense, denominator, quantity, cadence, TAM, or market-share source. |
| candidate-column packets | 2 | Rent and ASP have concrete candidate/supporting columns; frequency and penetration do not. |
| packet contracts valid | 4 | Every packet keeps `data_status=Unknown`, review-required status, complete blockers, and no write permission. |
| packet contracts invalid | 0 | No packet violates the read-only review contract. |
| production writes allowed | 0 | This packet bundle is read-only and does not mutate `realtime_current`. |

The current local structured-text policy draft split is:

| Local structured-text draft status | Count | Meaning |
|---|---:|---|
| `draft_known_qa_user_count_review_required` | 1 | `L0.demand.user_count` has bounded review-only Known evidence from strict answer-side customer/user/order/volume QA text and passes the production bridge. |
| `draft_known_qa_channel_service_review_required` | 1 | `L0.supply.channel_service` has bounded review-only Known evidence from QA/channel-service text and passes the production bridge. |
| `draft_known_qa_discount_pressure_review_required` | 1 | `L0.price.discount` has bounded review-only Known evidence from company-answer product-price-pressure text and passes the production bridge. |
| draft contracts valid | 3 | Every structured-text pilot envelope has target/score fields, evidence refs, rationale, review-required status, and no write permission. |
| invalid draft contracts | 0 | No structured-text pilot draft violates the review-only contract. |
| Known drafts bridge-ready | 3 | All three structured-text Known drafts have bounded `value_json.score` and reach final-score targets through the realtime bridge. |
| safe to upsert without review | 0 | No structured-text draft is eligible for unreviewed runtime upsert. |
| production writes allowed | 0 | Pilot drafts are not approved staging/runtime writes and do not reduce the 32 score-completion blockers by themselves. |

The current local structured-text Unknown source-options split is:

| Local structured-text Unknown source option | Count | Meaning |
|---|---:|---|
| Unknown rows reviewed | 0 | No structured-text rows remain Unknown after the `L0.demand.user_count` QA text draft. |
| runtime dependencies ready | 0 | No structured-text Unknown row currently needs runtime dependency review. |
| QA/IR recent dependencies ready | 0 | No structured-text Unknown row currently needs QA/IR dependency review. |
| direct text-classification-ready rows | 0 | No structured-text Unknown row remains to classify. |
| overlay/source hints | 0 | No structured-text Unknown row remains to hint. |
| text classifications required | 0 | No structured-text Unknown row currently needs text classification. |
| auto Known candidates | 0 | No row can be promoted automatically from current text without review. |
| production writes allowed | 0 | This audit is read-only and does not mutate `realtime_current`. |

The current local single-dependency policy draft split is:

| Single-dependency draft status | Count | Meaning |
|---|---:|---|
| `draft_known_review_required` | 2 | `L0.price.pricing_power` and `L0.supply.inventory` now have bounded review-only Known drafts that pass the production bridge. |
| `unknown_policy_required` | 1 | `L0.demand.replacement` stays Unknown because revenue alone cannot identify replacement-cycle demand. |
| draft contracts valid | 3 | Every pilot envelope has target/score fields, value bounds, evidence refs, rationale, review-required status, and no write permission. |
| invalid draft contracts | 0 | No single-dependency pilot draft violates the review-only contract. |
| Known drafts bridge-ready | 2 | Both Known single-dependency drafts produce final-score-ready realtime nodes. |
| safe to upsert without review | 0 | No single-dependency draft is eligible for unreviewed runtime upsert. |
| production writes allowed | 0 | Pilot drafts are not approved staging/runtime writes and do not reduce the 32 score-completion blockers by themselves. |

The current local single-dependency Unknown source-options split is:

| Single-dependency Unknown source option | Count | Meaning |
|---|---:|---|
| Unknown rows reviewed | 1 | `L0.demand.replacement` is the remaining single-dependency Unknown row. |
| runtime dependencies ready | 1 | `L5.is.revenue` has current Known runtime coverage, but revenue is not replacement-cycle evidence. |
| direct replacement-cycle source-ready rows | 0 | No current dependency directly exposes lifecycle, installed-base, renewal, or replacement-cycle evidence. |
| overlay/source hints | 1 | Existing overlays and industry graph context can guide review, but are not automatic production values. |
| rows with overlay lifecycle context candidates | 1 | The row has local lifecycle context available for review, but no approved replacement-cycle mapping. |
| overlay lifecycle Known nodes | 205 | A-share stock overlays contain 205 `L3.product.lifecycle=Known` nodes. |
| overlay replacement Known nodes | 0 | No A-share stock overlay currently has `L0.demand.replacement=Known`. |
| overlay replacement Unknown nodes | 1,646 | Replacement demand remains Unknown across the current A-share stock-overlay set. |
| lifecycle / replacement-cycle sources required | 1 | The row needs lifecycle, installed-base, shipment/order/user renewal, or reviewed overlay evidence. |
| reviewed policy required | 1 | A policy must define how the lifecycle evidence maps into the replacement-demand score. |
| lifecycle-policy review templates | 1 | A blank reviewer handoff template now captures the lifecycle-to-replacement policy decision. |
| lifecycle-policy template contracts valid | 1 | The template contract is structurally valid and matches the replacement row/context counts. |
| lifecycle-policy template contracts invalid | 0 | No lifecycle-policy template currently violates the blank review contract. |
| lifecycle-policy templates blank pending | 1 | The template is intentionally blank pending human review. |
| lifecycle-policy template inputs ready | 0 | The template is not yet accepted as classifier-ready, Known-ready, or approval-ready input. |
| auto Known candidates | 0 | No row can be promoted automatically from revenue alone. |
| Known-draft sufficient rows | 0 | No replacement row has enough reviewed evidence to emit a Known draft. |
| approval-ready rows | 0 | No replacement row is ready for approval or runtime write planning. |
| production writes allowed | 0 | This audit is read-only and does not mutate `realtime_current`. |

The current manual-policy draft pilot split is:

| Manual-policy draft status | Count | Meaning |
|---|---:|---|
| `draft_known_review_required` | 3 | `L6.priced.realization_risk`, `L7.reflex.tag`, and `L8.val.slope_risk_off` now have bounded review-only Known draft packets that pass the production bridge. |
| `draft_known_standard_dcf_assumption_review_required` | 1 | `L6.mult.dcf` has a bounded standard-assumption DCF draft that passes the production bridge but still requires approval. |
| draft contracts valid | 4 | Every pilot envelope has target/score fields, value bounds, evidence refs, rationale, review-required status, and no write permission. |
| invalid draft contracts | 0 | No pilot draft violates the review-only contract. |
| safe to upsert without review | 0 | No pilot draft is eligible for unreviewed runtime upsert. |
| production writes allowed | 0 | Pilot drafts are not approved staging/runtime writes and do not reduce the 32 score-completion blockers by themselves. |

The current manual-policy Unknown source-options split is:

| Manual-policy Unknown source option | Count | Meaning |
|---|---:|---|
| Unknown rows reviewed | 0 | No manual-policy rows remain Unknown after the DCF standard-assumption draft. |
| dependency packs ready | 0 | No manual-policy Unknown row currently needs a dependency-pack readiness check. |
| direct reviewed-assumption-ready rows | 0 | No current source supplies reviewed discount-rate, terminal-growth, forecast-horizon, or normalized-FCF assumptions. |
| required assumptions | 0 | The DCF assumptions are now represented inside the review-only Known draft rather than blocking the Unknown queue. |
| assumption reviews required | 0 | No manual-policy Unknown row currently needs an assumption-review action. |
| reviewed policy required | 0 | No manual-policy Unknown row currently needs a reviewed-policy action. |
| auto Known candidates | 0 | No row can be promoted automatically from dependency evidence alone. |
| production writes allowed | 0 | This audit is read-only and does not mutate `realtime_current`. |

The current review-staging manifest split is:

| Review manifest status | Count | Meaning |
|---|---:|---|
| review manifest entries | 32 | Every current score-blocking candidate row has exactly one canonical review entry. |
| `review_ready_concrete` | 25 | 25 `Known` packets have valid contracts and bridge to final-score targets, but still require explicit approval before runtime writes. |
| `review_gated_unknown` | 7 | These rows document the policy, classification, or assumption blocker that prevents a Known score value. |
| contracts valid | 32 | Every canonical review packet has target/score fields, evidence refs, rationale, review-required status, and no write permission. |
| invalid contracts | 0 | No canonical review packet violates the review contract. |
| concrete packets bridge-ready | 25 | Every concrete packet can pass the production bridge into a final-score target. |
| safe to upsert without review | 0 | No review packet is eligible for unreviewed runtime upsert. |
| production writes allowed | 0 | The review manifest is not an approval list and does not write runtime values. |
| approved runtime writes | 0 | The review manifest itself is not an approval list; the approval-gate table below records deterministic approvals separately. |

The current deterministic runtime-approval split is:

| Deterministic approval status | Count | Meaning |
|---|---:|---|
| deterministic policies | 2 | Only hard-gated staging payloads are eligible for this non-subjective approval path. |
| approval records | 2 | `L9.media.short_report` and `L7.trade.gamma` have matching approval records. |
| contract-valid approvals | 2 | Both records match the staged payload hash and score target contract. |
| non-deterministic rows left unapproved | 32 | All subjective/local/event/manual rows still require the normal review path or Unknown resolution. |
| rejected approvals | 0 | No deterministic policy rejected its target row. |
| production writes allowed | 0 | Approval records only create read-only write-plan evidence; they do not mutate runtime scores. |

The current review-approval gate split is:

| Approval gate status | Count | Meaning |
|---|---:|---|
| approval required | 25 | Every current concrete review-ready packet needs a separate runtime-write approval record. |
| approval records seen | 2 | Two historical deterministic records are present but no longer belong to the current post-execution queue. |
| approval missing | 25 | The remaining concrete review-ready packets are still blocked from runtime writes. |
| rejected approvals | 2 | The historical deterministic records are rejected/stale for the current queue. |
| approved runtime writes | 0 | No current packet enters a read-only write plan. |
| write-plan entries | 0 | The current approval gate has no pending runtime-write plan entries. |
| Unknown not approvable | 7 | Unknown review packets cannot be approved until their policy/classification/assumption blocker is resolved. |
| safe to upsert without review | 0 | The approval gate does not create any unreviewed write path. |
| production writes allowed | 0 | The approval gate is read-only and does not mutate runtime values. |

The current completion next-action split is:

| Completion next action | Count | Meaning |
|---|---:|---|
| `human_approval_required` | 25 | Concrete review-ready packets still need separate approval records whose payload hashes match the approval gate. |
| `runtime_write_plan_ready` | 0 | No current packet has a matching approval record and write plan. |
| `event_text_classification_required` | 2 | Remaining media/policy/competition/geo evidence must be classified into target concept, direction, magnitude, and A-share transmission path. |
| `local_structured_mapping_required` | 4 | Structured financial dependencies need reviewed business mapping formulas and bounds before Known review packets. |
| `structured_text_extraction_required` | 0 | No structured-text rows remain in the Unknown queue. |
| `single_dependency_policy_required` | 1 | `L0.demand.replacement` needs lifecycle/replacement-cycle evidence, a reviewed mapping policy, and completion of the blank lifecycle-policy review template beyond revenue alone. |
| `manual_assumption_review_required` | 0 | DCF is now a review-only Known draft, so no manual-policy Unknown row remains. |
| approved runtime writes | 0 | No current next-action row is approved for runtime write. |
| write-plan entries | 0 | No current next-action row has a pending write-plan entry. |
| approval payload hash mismatches | 0 | Approval templates use the manifest review payload hash, and current gate rows match it. |
| production writes allowed | 0 | The next-action queue is planning evidence only and does not mutate scores. |

The current Unknown closure matrix split is:

| Unknown closure matrix | Count | Meaning |
|---|---:|---|
| Unknown closure rows | 7 | The remaining review-gated Unknown packets now have explicit closure rows. |
| closure routes assigned | 7 | Every Unknown row has a route to the next evidence or policy action. |
| missing closure routes | 0 | No Unknown row is left without a closure route. |
| event-text classifications | 2 | `L0.compete.new_entrant` and `L0.tech.substitute_tech` still need event evidence/classification work. |
| local structured mappings | 4 | Rent, purchase frequency, penetration, and ASP still need governed mapping/formula or source work. |
| structured-text extractions | 0 | Structured-text Unknowns were closed into review-only Known drafts. |
| single-dependency policies | 1 | Replacement demand still needs lifecycle/replacement-cycle evidence, reviewed mapping policy, and completion of the blank lifecycle-policy review template. |
| manual assumption reviews | 0 | DCF is represented as a review-only Known draft rather than an Unknown blocker. |
| rows with source candidates | 3 | Rent, ASP, and substitute-tech have candidate evidence packets, but none are formula-ready. |
| formula-ready rows | 0 | No remaining Unknown row has all inputs needed for a scoreable Known value. |
| auto Known-ready rows | 0 | No Unknown row can be promoted automatically. |
| approval-ready Unknown rows | 0 | Unknown rows are not approvable until their evidence/formula blocker is resolved. |
| closure contracts valid | 7 | Every closure row has a blocker class, route, minimum evidence, and no write permission. |
| production writes allowed | 0 | The matrix is read-only and does not mutate runtime scores. |

The current Unknown acquisition backlog split is:

| Unknown acquisition backlog | Count | Meaning |
|---|---:|---|
| acquisition tasks | 7 | One concrete source-acquisition task exists for every remaining Unknown row. |
| DOCKCASE market-doc searches | 2 | New-entrant and substitute-tech need direct or clean event evidence from market documents. |
| local formula-source tasks | 2 | Rent and product ASP need complete numeric formula inputs, not just supporting fields. |
| external/text business-metric tasks | 3 | Frequency, penetration, and replacement need cadence, denominator, lifecycle, or replacement-cycle evidence. |
| tasks with existing candidate evidence | 3 | Rent, ASP, and substitute-tech have some local evidence but not enough to score. |
| tasks with runtime overlay hints | 1 | Replacement has overlay hints but still lacks direct lifecycle/replacement-cycle evidence. |
| tasks requiring web/external or deeper source acquisition | 6 | All except the current substitute-tech local review path need deeper source collection. |
| LLM extraction/classification-only tasks | 7 | LLM can assist extraction/classification, but cannot approve score writes. |
| formula-ready tasks | 0 | No Unknown acquisition task has all formula inputs ready. |
| auto Known-ready tasks | 0 | No task can become Known without review and stronger evidence. |
| approval-ready tasks | 0 | Acquisition tasks must first produce valid Known/NotApplicable review packets. |
| task contracts valid | 7 | Every acquisition task has required sources, acceptable/rejected evidence, next actions, and no write permission. |
| production writes allowed | 0 | The backlog is read-only source-acquisition planning. |

The current Unknown market-doc acquisition candidate split is:

| Unknown market-doc acquisition | Count | Meaning |
|---|---:|---|
| acquisition tasks executed | 2 | The new-entrant and substitute-tech event-document tasks were scanned against local DOCKCASE market HTML. |
| market HTML files scanned | 14,956 | Local DOCKCASE market documents were scanned for the two event-document Unknowns. |
| read errors | 0 | The local market-doc acquisition scan read all selected HTML files successfully. |
| rows with review candidates | 2 | Both event-document Unknowns now have local candidate material for reviewer inspection. |
| new-entrant window candidate documents | 5 | Target and A-share transmission terms appear near each other, but review is still required. |
| new-entrant review candidate snippets | 6 | Candidate snippets need reviewer confirmation that the event is a real new-entrant competitive signal. |
| substitute-tech same-sentence candidate documents | 34 | Same-sentence target/direct matches exist before false-positive filtering. |
| substitute-tech clean-risk review candidate snippets | 3 | Strict filter retained a small set of candidate snippets, still not scoreable without review. |
| weak candidates | 9 | These are near misses retained for auditability, not scoring inputs. |
| rejected candidates | 34 | False positives such as import-substitution upside, trade-law replacement, or noisy boilerplate are documented. |
| Known-draft-sufficient rows | 0 | The scan does not promote either event-document Unknown to a Known draft. |
| production writes allowed | 0 | The scan is read-only and does not mutate runtime scores. |

The current Unknown event-evidence adjudication split is:

| Unknown event-evidence adjudication | Count | Meaning |
|---|---:|---|
| event Unknown rows adjudicated | 2 | `L0.compete.new_entrant` and `L0.tech.substitute_tech` were checked after local market-doc candidate retention. |
| candidate examples reviewed | 14 | The adjudication reviewed retained examples from the local market-doc acquisition report. |
| accepted candidates | 0 | No retained candidate is clean enough to become valid score information. |
| rejected or ambiguous candidates | 14 | New-entrant candidates are incumbent expansion/JV/capacity evidence, and substitute-tech candidates are foreign, macro, import-substitution, opportunity, or ambiguous substitution context. |
| remaining Unknown rows | 2 | Both event rows stay Unknown pending stronger primary/source evidence. |
| Known-draft-sufficient rows | 0 | No event row can produce a reviewed Known draft from the retained local snippets. |
| auto Known-ready rows | 0 | The adjudication creates no deterministic scoreable value. |
| approval-ready rows | 0 | There is no valid Known/NotApplicable packet for approval yet. |
| contracts valid | 2 | Both adjudication rows preserve Unknown status and no write permission. |
| contracts invalid | 0 | No adjudication contract drift is present. |
| production writes allowed | 0 | The adjudication is read-only and does not mutate runtime scores. |

The current Unknown event strict-source gate split is:

| Unknown event strict-source gate | Count | Meaning |
|---|---:|---|
| event Unknown rows rescanned | 2 | The narrower gate reruns only `L0.compete.new_entrant` and `L0.tech.substitute_tech`. |
| local market HTML files scanned | 14,956 | The scan reuses the local DOCKCASE market-document corpus with 0 read errors. |
| strict candidates | 11 | Keyword and context filters found a smaller review queue after the broader acquisition/adjudication pass. |
| strict review candidates | 8 | These are reviewer/classifier inputs only, not accepted score evidence. |
| strict rejected contexts | 3 | Rejected contexts are kept to document why noisy opportunities or macro contexts stay out. |
| rows with strict review candidates | 2 | Both event rows now have narrower candidate leads, but neither is closed. |
| classifier-ready rows | 0 | No row has enough reviewed event and A-share transmission evidence to run the classifier as Known. |
| Known-draft-sufficient rows | 0 | The gate does not create valid Known payloads. |
| approval-ready rows | 0 | There is still no Known/NotApplicable packet that can enter the approval chain. |
| contracts valid | 2 | Both strict-gate rows preserve Unknown status and no write permission. |
| production writes allowed | 0 | The gate is read-only and does not mutate runtime scores. |

The current Unknown event strict-review packet split is:

| Unknown event strict-review packets | Count | Meaning |
|---|---:|---|
| strict review packets | 8 | The gate packages only the strict review candidates, not the already rejected contexts. |
| rows represented | 2 | Both event Unknown rows still have review leads, but neither is closed. |
| low-confidence community/forum source packets | 2 | The remaining potentially useful leads are from Eastmoney Guba / wealth-account style sources and require primary-source confirmation. |
| secondary-newswire packets | 6 | These were reviewed for context quality after the strict-source gate. |
| requires primary-source confirmation | 2 | These are next-source tasks, not accepted evidence. |
| requires manual review | 0 | No candidate is clean enough to need only a human classifier decision. |
| deterministic rejections | 6 | The rejected packets are false-positive process terms, foreign/macro pressure, overcapacity/cycle clearing, or geopolitical/import-shift opportunity contexts. |
| classifier-ready packets | 0 | No packet can run as a trusted classifier input for Known conversion. |
| Known-draft-sufficient packets | 0 | No packet creates a valid Known value. |
| approval-ready packets | 0 | There is still no Known/NotApplicable packet for approval. |
| contracts valid | 8 | All packets keep Unknown status and no write permission. |
| production writes allowed | 0 | The packet audit is read-only and does not mutate runtime scores. |

The current Unknown event primary-source confirmation split is:

| Unknown event primary-source confirmation | Count | Meaning |
|---|---:|---|
| packets requiring confirmation | 2 | The scan checks the two remaining low-confidence community/forum event leads. |
| local market HTML files scanned | 14,956 | The scan uses the local DOCKCASE market-document corpus and excludes community/forum sources. |
| read errors | 0 | No local HTML file failed to read. |
| local candidates | 12 | Non-community sources mention adjacent topic terms, mostly 阿里云算力、价格战、AI技术迭代 or similar context. |
| local high-quality confirmation candidates | 0 | No local source joins topic, A-share subject/industry, and event transmission strongly enough for confirmation review. |
| supporting-context-only candidates | 12 | These are insufficient for classifier or score conversion. |
| rows with local confirmation candidates | 0 | Neither `L0.compete.new_entrant` nor `L0.tech.substitute_tech` is locally confirmed. |
| rows with supporting context only | 2 | Both rows have weak/supporting local context but still lack a usable source. |
| classifier-ready rows | 0 | No row can enter classifier review as Known. |
| Known-draft-sufficient rows | 0 | No valid Known payload is produced. |
| approval-ready rows | 0 | There is still no Known/NotApplicable packet for approval. |
| contracts valid | 2 | Both confirmation rows keep Unknown status and no write permission. |
| production writes allowed | 0 | The confirmation scan is read-only and does not mutate runtime scores. |

The current Unknown event external-source confirmation split is:

| Unknown event external-source confirmation | Count | Meaning |
|---|---:|---|
| external confirmation packets | 2 | Both remaining event Unknown rows have public-source review packets. |
| external source cards | 6 | The packet bundle records reviewed public-source candidates and supporting context. |
| external confirmation candidates | 2 | One candidate each for `L0.compete.new_entrant` and `L0.tech.substitute_tech`. |
| external supporting-context cards | 4 | Supporting context cannot independently convert a row to Known. |
| rows with external confirmation candidates | 2 | Both rows now have an external candidate for reviewer adjudication. |
| classifier input candidates | 2 | Source IDs, required labels, and guardrails are packaged for review. |
| classifier input candidate contracts valid | 2 | Both candidates bind primary source coverage, labels, and guardrails. |
| classifier review templates | 2 | Blank templates are emitted for event-fit/transmission/direction/magnitude review. |
| classifier review template contracts valid | 2 | Both templates are hash-free review conveniences tied to packet IDs and source IDs. |
| classifier review template inputs ready | 0 | Templates are intentionally blank and are not confirmation records. |
| classifier-ready rows | 0 | Event fit, direct A-share transmission, direction, and bounded magnitude still require review. |
| Known-draft-sufficient rows | 0 | No valid Known payload is produced. |
| approval-ready rows | 0 | No packet can enter the approval gate yet. |
| contracts valid | 2 | Both packets preserve Unknown status and no write permission. |
| production writes allowed | 0 | The confirmation bundle is read-only and does not mutate runtime scores. |

The current Unknown local formula acquisition candidate split is:

| Unknown local formula acquisition | Count | Meaning |
|---|---:|---|
| local formula acquisition tasks | 2 | Rent and product ASP were checked against local structured source-review packets and DOCKCASE sample CSVs. |
| runtime dependency-ready tasks | 2 | Both tasks have their existing runtime context dependencies available. |
| sample CSV files checked | 6 | Source-review sample files for rent and ASP were opened for column-level evidence. |
| sample CSV files existing | 6 | All referenced sample CSV files exist under DOCKCASE `database_all`. |
| sample CSV read errors | 0 | No sample CSV read failed. |
| formula input groups | 8 | Each task is split into candidate numerator, missing direct input, mapping/denominator, and formula policy groups. |
| formula input groups ready | 0 | Candidate/supporting evidence is not enough to mark any complete formula group ready. |
| rows with candidate numerators | 2 | Rent has `use_right_asset_dep`; ASP has `bz_sales` with product/mix context. |
| rows with direct denominators | 0 | Rent still lacks a reviewed rent-burden denominator. |
| rows with denominator candidates | 1 | Rent has runtime `L5.is.revenue` as a denominator candidate for lease-burden review. |
| rows with candidate formula shapes | 1 | Rent has the review-only candidate shape `use_right_asset_dep / L5.is.revenue`. |
| rows with formula-policy draft candidates | 1 | Rent now has a review-only policy draft that binds proxy semantics, revenue denominator, score direction, and cap/floor blockers. |
| formula-policy review templates | 1 | Rent has a blank template for proxy semantics, denominator policy, cap/floor, score direction, and normalization review. |
| formula-policy review template contracts valid | 1 | The rent template is tied to the local formula packet and candidate formula. |
| rows with price-index context candidates | 1 | ASP can see local DOCKCASE CPI/PPI macro price-index context, but it is not product-level input. |
| rows with candidate price-context shapes | 1 | ASP has a review-only context shape combining `bz_sales` / product mix with CPI/PPI context. |
| price-context review templates | 1 | ASP has a blank template for product quantity source, price-index mapping, scope alignment, and formula policy review. |
| price-context review template contracts valid | 1 | The ASP template is tied to the local formula packet and macro price-index context shape. |
| rows with quantity or price-index inputs | 0 | ASP still lacks unit volume, shipment volume, product quantity, or governed price index. |
| rows with formula policy | 0 | Neither task has reviewed formula bounds and scoring policy. |
| formula-ready rows | 0 | Neither task can produce a scoreable Known value yet. |
| Known-draft-ready rows | 0 | The scan does not produce review-ready Known draft packets. |
| contracts valid | 2 | Both local formula acquisition rows keep Unknown status and no write permission. |
| production writes allowed | 0 | The scan is read-only and does not mutate runtime scores. |

The current Unknown external business metric acquisition split is:

| Unknown external business metric acquisition | Count | Meaning |
|---|---:|---|
| external business metric tasks | 3 | Frequency, penetration, and replacement demand were checked against local runtime context, structured review packets, and overlay hints. |
| runtime dependency-ready tasks | 3 | Existing runtime context is present for all 3 rows, but it is only supporting evidence. |
| runtime overlay hints | 7 | Replacement demand has related overlay/source hints, but none is a direct replacement-cycle source. |
| business metric groups | 12 | Each row is split into supporting context plus missing direct metric/source/policy groups. |
| business metric groups ready | 0 | No group has all inputs required for a scoreable business metric. |
| rows with supporting runtime context | 3 | Revenue/runtime context exists, but cannot prove cadence, penetration, or replacement by itself. |
| rows with direct business metric source | 0 | No local source supplies direct frequency, market denominator, lifecycle, or replacement-cycle evidence. |
| rows requiring external/text source | 3 | All 3 rows need web/external documents or text extraction before a Known draft can be reviewed. |
| excluded false positives | 238 | Local structured source-review excluded 96 frequency-like and 142 penetration-like false positives. |
| metric-ready rows | 0 | No row can currently turn into a numeric metric. |
| Known-draft-ready rows | 0 | The scan does not produce review-ready Known draft packets. |
| contracts valid | 3 | All 3 external business metric rows keep Unknown status and no write permission. |
| production writes allowed | 0 | The scan is read-only and does not mutate runtime scores. |

The current Unknown external business metric market-doc candidate split is:

| Unknown external business metric market-doc candidates | Count | Meaning |
|---|---:|---|
| market-doc tasks | 3 | Frequency, penetration, and replacement were scanned against local DOCKCASE market HTML. |
| market HTML files scanned | 14,956 | The scan covered the local market HTML corpus used by prior event-document audits. |
| read errors | 0 | All selected market HTML files were readable. |
| rows with review candidates | 3 | All 3 external business metric rows now have local snippets for reviewer inspection. |
| candidate documents | 178 | Documents with at least one candidate or weak/rejected metric snippet. |
| review candidates | 99 | Snippets with target terms plus business scope/context; they still need source-scope and formula review. |
| numeric review candidates | 49 | Candidate snippets include a numeric/percentage/cycle token, but not enough validated structure for scoring. |
| textual review candidates | 50 | Candidate snippets have business context but no directly usable numeric metric. |
| weak candidates | 82 | Target terms appear, but the business scope is incomplete or too indirect. |
| rejected candidates | 72 | Boilerplate, comments, or noisy metric mentions are retained as false-positive evidence. |
| Known-draft-sufficient rows | 0 | No row can be promoted to a Known draft from snippets alone. |
| metric-ready rows | 0 | No row has validated numerator/denominator/scope/bounds/formula policy. |
| contracts valid | 3 | All 3 rows keep Unknown status and no write permission. |
| production writes allowed | 0 | The scan is read-only and does not mutate runtime scores. |

The current Unknown external business metric review-packet split is:

| Unknown external business metric review packets | Count | Meaning |
|---|---:|---|
| review packets | 99 | Every retained numeric/textual market-doc review candidate now has a candidate-level review packet. |
| expected review candidates | 99 | Packet count matches the candidate scan count, so no retained review candidate is dropped. |
| rows with review packets | 3 | Frequency, penetration, and replacement all have candidate packets. |
| numeric review packets | 49 | These packets include a numeric, percentage, or cycle token but still need review. |
| textual review packets | 50 | These packets have business context without a directly usable numeric metric. |
| packets with scope candidates | 99 | Every packet has at least candidate-level business scope evidence. |
| packets with denominator candidates | 70 | Some packets include market, industry, user, customer, stock, or installed-base context; it is not yet validated as a formula denominator. |
| packets with period candidates | 36 | Some packets include a year/month/period token; period alignment is still unreviewed. |
| packets with unit candidates | 49 | Numeric packets have candidate units, but unit semantics and bounds are not reviewed. |
| metric-ready packets | 0 | No packet has validated scope, numerator, denominator, period, unit, bounds, and formula policy. |
| Known-draft-sufficient packets | 0 | No packet can become a Known draft without a reviewer-approved value JSON. |
| contracts valid | 99 | All packets keep Unknown status and preserve at least one missing field. |
| production writes allowed | 0 | The bundle is read-only review material only. |

The current Unknown external business metric readiness queue split is:

| Unknown external business metric readiness queue | Count | Meaning |
|---|---:|---|
| review packets | 99 | Same candidate-level packet universe as the review-packet bundle. |
| P0 formula-policy-only candidates | 18 | These packets have candidate scope, denominator, period, and unit, but still need reviewed bounds and formula policy before any Known draft. |
| P1 period/unit-required candidates | 52 | These packets have denominator/scope context but still need period or unit extraction before formula review. |
| P2 denominator-required candidates | 29 | These packets still lack a usable denominator or normalizer; all replacement packets are in this bucket. |
| packets missing denominator | 29 | Denominator/normalizer remains the hardest blocker, especially for replacement demand. |
| packets missing period | 63 | Candidate snippets often lack a clean period even when numeric terms exist. |
| packets missing unit | 50 | Textual packets and some numeric snippets lack a scoreable unit. |
| packets missing bounds | 99 | Every packet still needs reviewed bounds before a value JSON can be accepted. |
| packets missing formula policy | 99 | Every packet still needs a reviewed formula policy before Known draft creation. |
| metric-ready packets | 0 | No packet has all required fields for numeric conversion. |
| Known-draft-sufficient packets | 0 | No packet can enter approval review as a Known draft yet. |
| production writes allowed | 0 | The queue is read-only prioritization only. |

The current Unknown external business metric policy-draft split is:

| Unknown external business metric policy drafts | Count | Meaning |
|---|---:|---|
| P0 source packets | 18 | Only the formula-policy-only packets are included. |
| policy draft packets | 18 | Each P0 packet gets a review-only formula-policy draft. |
| formula-policy reviews required | 18 | Every draft still requires reviewer approval of bounds and formula policy. |
| value JSON templates | 18 | Templates exist, but `raw_value` is deliberately `null` until review. |
| policy review templates | 18 | Each P0 policy draft now has a blank reviewer handoff for source scope, value selection, bounds, and formula policy. |
| policy review template contracts valid | 18 | Every template matches the source draft and keeps all acceptance booleans false. |
| policy review template contracts invalid | 0 | No policy review template violates the blank handoff contract. |
| policy review templates blank pending | 18 | All policy review templates still require reviewer completion. |
| policy review template inputs ready | 0 | No template is accepted as Known-ready or approval-ready input. |
| `L0.demand.frequency` drafts | 1 | One cadence/frequency candidate is ready for policy review only. |
| `L0.demand.penetration` drafts | 17 | Seventeen penetration/share candidates are ready for policy review only. |
| metric-ready drafts | 0 | No draft selects a final value or completes formula review. |
| Known-draft-sufficient drafts | 0 | No draft can be approved into scoring without a reviewed value JSON. |
| policy contracts valid | 18 | All drafts keep Unknown status and no write permission. |
| production writes allowed | 0 | The bundle is read-only review material only. |

The current Unknown external business metric value-candidate adjudication split is:

| Unknown external business metric value candidates | Count | Meaning |
|---|---:|---|
| policy draft packets checked | 18 | The P0 formula-policy-only drafts were screened for numeric value candidates. |
| rows with value-candidate tokens | 9 | These rows contain at least one percent-style token that is not immediately a date, money amount, growth multiple, or stock-price move. |
| value-candidate tokens | 13 | Candidate tokens are retained for reviewer selection only; none is accepted as a final raw value. |
| rejected numeric tokens | 31 | Dates, periods, monetary amounts, growth multiples, stock moves, and non-cadence frequency tokens are excluded. |
| shortlist review required | 6 | Six rows have a potentially usable value token and non-rejected scope, but still need source-scope, value, bounds, formula-policy, and approval review. |
| scope-rejected rows | 3 | Three rows have numeric tokens but fail the A-share/source-scope screen. |
| no scoreable numeric candidate | 9 | Nine rows do not have a scoreable numeric value after token filtering. |
| metric-ready rows | 0 | No row has reviewed scope, value, bounds, and formula policy. |
| Known-draft-sufficient rows | 0 | No row can become Known without reviewer-approved value JSON. |
| contracts valid | 18 | All adjudication rows preserve Unknown status and no write permission. |
| production writes allowed | 0 | The adjudication is read-only and does not mutate runtime scores. |

The current Unknown external business metric value-review packet split is:

| Unknown external business metric value review | Count | Meaning |
|---|---:|---|
| shortlist source rows | 6 | The review packets start from the value-candidate shortlist only. |
| value review packets | 6 | Each shortlist row has a review packet with candidate options and blockers. |
| candidate value options | 8 | Multi-value snippets retain multiple percent options for review rather than selecting one automatically. |
| bridge-probe-ready options | 8 | Every option can be converted with `score = clamp(raw_percent / 100, 0, 1)` and bridge to the final-score target if later approved. |
| selected raw values | 0 | The audit deliberately selects no final value. |
| selected value JSONs | 0 | No review packet is converted into a Known payload. |
| metric-ready packets | 0 | Source scope, value choice, bounds, and formula policy still need review. |
| Known-draft-sufficient packets | 0 | No packet can enter approval review as a Known draft yet. |
| approval-ready packets | 0 | The formula probe is not an approval packet. |
| contracts valid | 6 | All packets preserve Unknown status, blockers, and no write permission. |
| production writes allowed | 0 | The packet bundle is read-only and does not mutate runtime scores. |

The current Unknown penetration value-priority split is:

| Penetration value priority | Count | Meaning |
|---|---:|---|
| value-review packets | 6 | All packets belong to `L0.demand.penetration`. |
| candidate value options | 8 | Percent tokens remain candidate options, not selected values. |
| bridge-probe-ready options | 8 | Every option can bridge if later reviewed, selected, bounded, and approved. |
| P1 preferred source-scope reviews | 1 | The top item is a non-community market document with A-share/domestic scope. |
| P2 industry-scope reviews | 1 | Needs issuer and denominator review before value selection. |
| P3 forecast/assumption reviews | 2 | Needs forecast/assumption policy and bounds review. |
| P3 low-confidence community reviews | 2 | Community/forum sources need stronger confirmation before use. |
| selected raw values | 0 | No value is selected by this priority report. |
| Known-draft-sufficient rows | 0 | Prioritization does not create a Known draft. |
| runtime writes allowed | 0 | No runtime write is allowed from priority sorting. |
| production writes allowed | 0 | The priority report is read-only. |

The current Unknown penetration P1 source-confirmation split is:

| Penetration P1 source confirmation | Count | Meaning |
|---|---:|---|
| P1 candidates checked | 1 | The top `L0.demand.penetration` source is the 华泰证券 electronic-gas note. |
| source files found | 1 | The DOCKCASE HTML file is present and readable. |
| raw value tokens confirmed | 1 | The `40%` candidate token is present in the source text. |
| source scope confirmed | 1 | The same source contains domestic/listed-company/electronic-gas market-share and domestic-market-size denominator context. |
| selected raw values | 0 | Confirmation does not choose the final value. |
| Known-draft-sufficient rows | 0 | Value selection, bounds, formula policy, applicability, and approval remain required. |
| runtime writes allowed | 0 | No runtime write is allowed from source confirmation. |
| production writes allowed | 0 | The source-confirmation report is read-only. |

The current Unknown penetration value-policy draft split is:

| Penetration value-policy draft | Count | Meaning |
|---|---:|---|
| draft rows | 1 | The confirmed P1 source is converted into one reviewer-facing proposal. |
| source scope confirmed | 1 | The draft is based on the confirmed domestic/listed-company/electronic-gas market-share source. |
| proposed value JSONs | 1 | The proposal is `raw_value=40.0`, `unit=percent`, `score=0.4`. |
| draft contracts valid | 1 | The proposed payload retains review-only metadata and no write permission. |
| bridge final-score ready | 1 | The proposed payload shape can reach the final-score path if later reviewed and approved. |
| selected raw values | 0 | The draft does not select the value for runtime use. |
| Known-draft-sufficient rows | 0 | Reviewer value selection, bounds, formula policy, applicability, and approval remain required. |
| runtime writes allowed | 0 | No runtime write is allowed from the value-policy draft. |
| production writes allowed | 0 | The draft report is read-only. |

The current Unknown business-metric value-selection gate split is:

| Unknown business-metric value-selection gate | Count | Meaning |
|---|---:|---|
| business metric rows | 3 | Frequency, penetration, and replacement are checked together after acquisition/value-review. |
| value-review packets | 6 | All current value-review packets belong to penetration. |
| candidate value options | 8 | The options are retained for review rather than selected automatically. |
| bridge-probe-ready options | 8 | Every option can reach the final-score target if later reviewed and approved. |
| rows needing generic value-selection review | 0 | Penetration has moved into the explicit value-policy draft-ready lane. |
| value-policy-draft-ready rows | 1 | Penetration has a reviewer-facing `raw_value=40.0`, `score=0.4` proposal. |
| proposed value JSONs | 1 | The proposed payload is bridge-ready but still review-required. |
| source-metric-missing rows | 2 | Frequency and replacement still lack cadence/lifecycle source metrics. |
| auto-selectable values | 0 | No option is strong enough for automatic Known draft creation. |
| selected value JSONs | 0 | No candidate value is selected. |
| Known-draft-sufficient rows | 0 | No row can move into approval review from this gate. |
| approval-ready rows | 0 | The gate creates no approval packet. |
| selection contracts valid | 3 | Every row preserves Unknown status and no write permission. |
| production writes allowed | 0 | The value-selection gate is read-only and does not mutate runtime scores. |

The current Unknown penetration value-confirmation packet split is:

| Penetration value-confirmation packets | Count | Meaning |
|---|---:|---|
| confirmation packets | 1 | `L0.demand.penetration` now has a hash-bound reviewer packet for the proposed 40% / 0.4 value. |
| review-required packets | 1 | The packet is a human confirmation work item, not an approval. |
| confirmation templates | 1 | The template is intentionally blank for reviewer identity/status/timestamp and acceptance booleans. |
| confirmation template contracts valid | 1 | The blank template is tied to the proposed payload hash. |
| confirmation packet contracts valid | 1 | Source scope, proposed value JSON, bridge readiness, and no-write gates all validate. |
| Known-draft-sufficient rows | 0 | The value still needs explicit value, bounds, formula policy, applicability, and score-impact confirmation. |
| approval-ready rows | 0 | Confirmation is separate from runtime-write approval. |
| runtime writes allowed | 0 | No runtime write is authorized by the confirmation packet. |
| production writes allowed | 0 | The confirmation packet audit is read-only. |

The current Unknown penetration value-confirmation template bundle split is:

| Penetration value-confirmation templates | Count | Meaning |
|---|---:|---|
| source confirmation packets | 1 | The bundle reads only the existing hash-bound packet audit. |
| confirmation templates | 1 | The single `L0.demand.penetration` template is copied from `confirmation_record_template`. |
| blank pending templates | 1 | Reviewer identity/status/timestamp are empty and all acceptance booleans remain `false`. |
| blank template contracts valid | 1 | The copied template still matches the packet `dp_id` and payload hash. |
| confirmed templates | 0 | Templates are not reviewer confirmations. |
| Known-draft-sufficient rows | 0 | Blank templates cannot advance the field to Known. |
| approval-ready rows | 0 | Template extraction is upstream of confirmation and approval. |
| runtime writes allowed | 0 | The template bundle is read-only and cannot authorize runtime writes. |
| production writes allowed | 0 | No production write is possible from this audit. |

The current Unknown penetration value-confirmation gate split is:

| Penetration value-confirmation gate | Count | Meaning |
|---|---:|---|
| confirmation packets checked | 1 | The gate checks the hash-bound `L0.demand.penetration` confirmation packet. |
| confirmation records seen | 0 | No separate reviewer confirmation file exists yet. |
| confirmations missing | 1 | The packet cannot advance without a matching confirmation record. |
| confirmed value policies | 0 | No reviewer has accepted value selection, bounds, formula policy, applicability, and score impact. |
| Known-draft candidates | 0 | The gate emits no Known draft candidate until confirmation passes. |
| approval-ready rows | 0 | Confirmation is still upstream of runtime-write approval. |
| runtime writes allowed | 0 | The gate is read-only and never authorizes runtime writes. |
| production writes allowed | 0 | No production write is possible from this audit. |

The current Unknown penetration confirmed Known-draft split is:

| Penetration confirmed Known drafts | Count | Meaning |
|---|---:|---|
| confirmation-gate rows | 1 | The emitter checks the single penetration confirmation-gate row. |
| confirmed value-policy candidates | 0 | No confirmation record has passed the gate. |
| Known drafts emitted | 0 | No Known draft is produced from unconfirmed value policy. |
| Known drafts blocked | 1 | `L0.demand.penetration` remains blocked at `confirmation_missing`. |
| ready for review staging | 0 | Nothing can enter review staging from this emitter yet. |
| approval-ready rows | 0 | Emitted drafts, if any, would still require later staging/approval. |
| runtime writes allowed | 0 | The emitter is read-only and never writes runtime rows. |
| production writes allowed | 0 | No production write is possible from this audit. |

The current approval review packet split is:

| Approval review packet status | Count | Meaning |
|---|---:|---|
| approval review packets | 25 | Focused reviewer bundle extracted from current `review_ready_concrete` rows. |
| Known packets | 25 | Concrete values are present and bridge-ready but still unapproved. |
| NotApplicable packets | 0 | The former gamma NotApplicable packet was consumed by runtime execution. |
| final-score-target ready | 25 | Every approval-review packet bridges into a final score target. |
| approval missing | 25 | Every current packet still needs a matching approval record. |
| approval templates | 25 | Templates include payload hashes but are intentionally incomplete for packets still requiring human review. |
| approval template contracts valid | 25 | Every remaining template matches its packet hash and stays incomplete. |
| approval template contracts invalid | 0 | No approval template drift is present. |
| skipped not bridge/contract ready | 0 | No concrete manifest row was excluded by the bridge/contract readiness gate. |
| approval payload hash mismatches | 0 | Approval packet hashes match the manifest review payloads. |
| `fundamental_score` packets | 19 | Local structured/structured-text/single-dependency plus event-text L0 packets awaiting approval. |
| non-fundamental target packets | 6 | Expectation gap, priced-in, reflexivity, risk-discount, and valuation-rerating packets awaiting approval. |
| approved runtime writes | 0 | No current packet enters a read-only write plan. |
| write-plan entries | 0 | The current approval packet bundle has no pending write-plan entries. |
| production writes allowed | 0 | The packet bundle is review material only. |

The current approval-packet risk-review split is:

| Approval packet risk class | Count | Meaning |
|---|---:|---|
| `bulk_structured_review_candidate` | 6 | Strict local structured / single-dependency packets with bounded impact; still require reviewer identity, timestamp, matching payload hash, and risk acknowledgement. |
| `borderline_structured_text_review_candidate` | 1 | `L0.supply.channel_service` should get source-text sample checks before any batch approval. |
| `individual_event_evidence_review_required` | 8 | Event/text packets require source and A-share transmission review. |
| `individual_structured_review_required` | 4 | Structured proxy packets need semantic/formula review before approval. |
| `individual_policy_review_required` | 6 | Manual policy or non-fundamental score-target packets require individual review. |
| `do_not_approve_until_contract_fixed` | 0 | No packet has hash/template/bridge contract drift. |
| auto approvals allowed | 0 | The risk review never creates approval records. |
| runtime writes allowed | 0 | Runtime writes still require the approval-gate and controlled write path. |
| production writes allowed | 0 | The risk review is read-only. |

The current bulk-review approval-candidate split is:

| Bulk review candidate status | Count | Meaning |
|---|---:|---|
| strict bulk candidates | 6 | `L0.cost.cac`, `L0.cost.labor`, `L0.price.pricing_power`, `L0.supply.capacity`, `L0.supply.chain_eff`, and `L0.supply.inventory`. |
| borderline sample-check candidates | 1 | `L0.supply.channel_service` needs source-text sample review before approval. |
| approval drafts | 7 | Draft records bind the candidate payload hash and runtime-write scope for reviewer convenience. |
| approval draft contracts valid | 7 | Drafts have the expected blank approval fields and matching payload hashes. |
| approval draft contracts invalid | 0 | No draft contract drift is present. |
| auto approvals allowed | 0 | Drafts are intentionally incomplete and cannot pass the approval gate. |
| runtime writes allowed | 0 | Runtime writes still require filled approval records and the controlled write path. |
| production writes allowed | 0 | The candidate bundle is read-only. |

The bulk-review source-sample audit now verifies the reviewer bundle:

| Bulk source-sample check | Count | Meaning |
|---|---:|---|
| reviewer candidates checked | 7 | The same 6 strict bulk candidates plus `L0.supply.channel_service`. |
| source payload matches | 7 | Candidate payloads match their source draft reports. |
| complete evidence refs | 7 | Source report refs and runtime dependency refs resolve. |
| borderline sample-evidence ready | 1 | `L0.supply.channel_service` includes a QA/text evidence example with keyword hits. |
| reviewer packets complete | 7 | The packet is traceable and review-ready, but still not approved. |
| auto approvals allowed | 0 | No approval records are created by this audit. |
| runtime writes allowed | 0 | Runtime writes still require filled approval records and the controlled write path. |
| production writes allowed | 0 | The source-sample audit is read-only. |

The event-approval source-sample audit now verifies the event/text reviewer bundle:

| Event source-sample check | Count | Meaning |
|---|---:|---|
| event-text approval packets checked | 10 | All current event-text approval packets are included. |
| individual event-evidence reviews required | 8 | Eight packets are explicitly risk-classed for event/transmission evidence review. |
| source payload matches | 10 | Approval packet payloads match the source event-text policy draft rows. |
| market-doc review packets found | 10 | Every packet has a matching market-doc review packet row. |
| market-doc review refs complete | 10 | DOCKCASE refs in approval packets are present in the market-doc review packets. |
| DOCKCASE docs readable | 48 / 48 | Every referenced local news HTML file exists under `/Volumes/dockcase2tb/market_data`. |
| keyword-evidence-ready rows | 10 | Each packet has at least one readable doc containing target and direct-transmission hits. |
| event-evidence review templates valid | 10 / 10 | Templates bind `dp_id`, score target, and payload hash but remain blank. |
| event-evidence templates blank/pending | 10 | Reviewer, timestamp, evidence acceptance, direction, magnitude, and risk acknowledgement are intentionally unfilled. |
| reviewer packets complete | 10 | The packets are traceable and review-ready, but still not approved. |
| auto approvals allowed | 0 | No approval records are created by this audit. |
| runtime writes allowed | 0 | Runtime writes still require filled approval records and the controlled write path. |
| production writes allowed | 0 | The source-sample audit is read-only. |

The individual-review source-sample audit now verifies the remaining non-bulk reviewer bundle:

| Individual source-sample check | Count | Meaning |
|---|---:|---|
| individual review packets checked | 10 | The 4 structured-proxy and 6 policy / non-fundamental packets excluded from bulk approval. |
| structured proxy reviews required | 4 | `L0.demand.terminal`, `L0.demand.user_count`, `L0.price.contract_spot`, and `L0.price.discount`. |
| policy reviews required | 6 | Manual policy and non-fundamental score-target packets, including 2 event risk-discount packets. |
| manual-policy packets | 4 | `L6.priced.realization_risk`, `L7.reflex.tag`, `L8.val.slope_risk_off`, and `L6.mult.dcf`. |
| event policy packets | 2 | `L8.shock.black_swan` and `L8.shock.supply_break` link back to the event source-sample audit. |
| structured proxy packets | 4 | Structured and structured-text proxy semantics require individual review. |
| source payload matches | 10 | Approval packet payloads match their source draft reports. |
| complete evidence refs | 10 | Repo evidence refs and runtime dependency refs resolve. |
| text sample-evidence ready | 2 | The structured-text packets include QA/text examples with keyword hits. |
| event source-sample packets complete | 2 | The two event risk-discount packets have complete event evidence traceability. |
| individual review templates valid | 10 / 10 | Templates bind `dp_id`, score target, source kind, risk class, and payload hash. |
| individual review templates blank/pending | 10 | Reviewer, timestamp, source verification, policy mapping, score target, direction, magnitude, and risk acknowledgement are intentionally unfilled. |
| reviewer packets complete | 10 | The packets are traceable and review-ready, but still not approved. |
| auto approvals allowed | 0 | No approval records are created by this audit. |
| runtime writes allowed | 0 | Runtime writes still require filled approval records and the controlled write path. |
| production writes allowed | 0 | The source-sample audit is read-only. |

The consolidated approval source-sample coverage gate verifies that every current
missing approval packet is backed by one of the three source-sample audits:

| Approval source-sample coverage check | Count | Meaning |
|---|---:|---|
| approval packets checked | 25 | The missing approval universe after deterministic runtime approvals. |
| supported source-sample routes | 25 | Every packet maps to bulk, event, or individual source-sample evidence. |
| source samples found | 25 | All routed source-sample rows are present. |
| reviewer packets complete | 25 | All source-sample packets have complete reviewer-facing evidence. |
| source payload matches | 25 | Routed source samples bind to the same candidate payloads. |
| source-sample review templates valid | 25 | Reviewer templates validate for all routed packets. |
| blank approval templates valid | 25 | Approval templates remain intentionally blank but contract-valid. |
| approval inputs ready | 25 | All missing approval packets have source-sample-backed input bundles. |
| approval inputs not ready | 0 | No missing approval packet is blocked by source-sample coverage. |
| route split | 7 / 8 / 10 | Bulk / event / individual source-sample route counts. |
| unsupported risk classes | 0 | No approval packet has an unroutable risk class. |
| runtime writes allowed | 0 | Source-sample coverage does not authorize runtime writes. |
| production writes allowed | 0 | The coverage gate is read-only. |

The approval target-scope readiness audit separates "review evidence is ready"
from "runtime target materialization is safe":

| Approval target-scope readiness | Count | Meaning |
|---|---:|---|
| approval packets checked | 25 | The missing approval universe backed by source-sample evidence. |
| final-score-ready packets | 25 | Candidate payloads can map into score targets once governance clears them. |
| source-sample packets complete | 25 | The reviewer evidence bundle is complete for every packet. |
| existing runtime target-scope policies | 2 | Only `L7.trade.gamma` and `L9.media.short_report` have runtime target expansion policy. |
| packets supported by existing policies | 0 | None of the 25 approval packets match those deterministic policies. |
| explicit target scopes | 0 | No approval packet carries a reviewed target ticker set. |
| target-scope-ready after approval | 0 | Approval alone would not make any packet runtime materialization-safe. |
| target-scope policies required | 25 | Every approval packet still needs materialization scope. |
| per-stock materialization required | 19 | Fundamental-score packets need per-stock value materialization. |
| market/event scope policy required | 6 | Event/policy score targets need reviewed market/event scope policy. |
| runtime materializations ready | 0 | No packet is ready for bounded runtime writes. |
| approval-only not sufficient | 25 | Filled approval records would still not be enough for runtime writes. |
| safe runtime writes after approval | 0 | No approval packet is safe to write solely after approval. |
| production writes allowed | 0 | The readiness audit is read-only. |

The approval materialization audits now close the 2026-06-20 controlled runtime
write loop for all materialization-ready plans:

| Approval materialization status | Count | Meaning |
|---|---:|---|
| approval packets checked | 25 | Same source-sample-backed approval universe. |
| configured A-share tickers | 1,641 | Current `config/mvp20.universe.yaml` A-share set. |
| runtime materialization plans ready | 11 | 7 direct structured formulas, 1 grain join, and 3 text-evidence subset plans. |
| market/event scope policies still required | 14 | Event/manual/non-fundamental packets still need reviewed market/event scope policy. |
| batch-plan entries | 11 | Every ready plan has a controlled UPSERT contract. |
| contract-valid batch plans | 11 | Each plan binds target keys, row-set hash, source, and rollback policy. |
| Codex review approved | 11 | Deterministic batch-review accepted all current ready plans. |
| approval-gate accepted | 11 | Hash-bound approval records matched all current ready plans. |
| execution preflight ready | 11 | Dry-run validation found no runtime DB mismatch. |
| execution status | executed | `--execute` created a backup, ran SQLite `quick_check`, UPSERTed, and verified; current reproduction uses the read-only post-execution review. |
| planned UPSERT rows | 11,006 | Row-set across the 11 current materialization-ready plans. |
| rows inserted | 1,011 | New `realtime_current` rows created in this execution. |
| noop existing rows | 9,995 | Previously materialized rows were already present and hash-compatible. |
| post-write verified rows | 11,006 | All planned rows were re-read after execution. |
| verification errors | 0 | No row/count/hash verification failure was reported. |
| production writes allowed | 0 | This was a bounded runtime data write, not a production score write. |

The current runtime write target-scope split is:

| Runtime scope approvals | Count | Meaning |
|---|---:|---|
| target-scope rows checked | 2 | `L9.media.short_report` and `L7.trade.gamma` target scopes were reviewed. |
| scope approval records | 2 | Scope approvals bind to canonical `target_scope_sha256` values. |
| approved runtime target scopes | 2 | Both deterministic neutral scopes are approved for batch-plan preparation. |
| scope policy rejected | 0 | No deterministic target-scope policy failed. |
| candidate runtime rows would write if batch-approved | 3,282 | Scope approval does not itself authorize UPSERT execution. |
| runtime writes attempted | 0 | The approval audit is read-only and does not mutate `runtime/hot.sqlite`. |
| production writes allowed | 0 | Production score writes remain disallowed. |

| Runtime write target scope | Count | Meaning |
|---|---:|---|
| approved write-plan entries | 2 | `L9.media.short_report` and `L7.trade.gamma` are checked for target expansion. |
| runtime A-share `ts_code`s | 1,641 | Current `runtime/hot.sqlite` A-share ticker set. |
| configured A-share `ts_code`s | 1,641 | Current `config/mvp20.universe.yaml` A-share ticker set. |
| config/runtime exact match | yes | The runtime A-share set matches the configured A-share set. |
| target-scope candidates | 2 | Both approved payloads can be packaged against the current A-share universe as candidates. |
| target-scope contracts valid | 2 | The neutral gamma and no-short-report value contracts pass the target-scope audit. |
| target-scope reviews required | 0 | Scope approvals have been accepted for both candidates. |
| target scopes approved | 2 | The derived target-universe expansion is approved for batch-plan preparation only. |
| controlled batch plans required | 2 | A backup/rollback-aware UPSERT batch plan is still required before execution. |
| candidate runtime rows would write if approved | 3,282 | 2 approved dp_ids × 1,641 A-share tickers. |
| runtime writes attempted | 0 | The audit is read-only and does not mutate `runtime/hot.sqlite`. |
| production writes allowed | 0 | Production score writes remain disallowed. |

| Runtime write batch plan | Count | Meaning |
|---|---:|---|
| batch-plan entries | 2 | `L9.media.short_report` and `L7.trade.gamma` have controlled batch UPSERT plans. |
| batch-plan contracts valid | 2 | Both plans bind the approved payload hash, target-scope hash, runtime source, and target ticker list. |
| batch-plan contracts invalid | 0 | No current batch plan contract failed. |
| batch-plan reviews required | 0 | Batch-plan approval records have been accepted. |
| batch plans approved | 2 | Both controlled batch-plan hashes are approved for backup/execution preparation only. |
| planned UPSERT rows | 3,282 | 2 approved dp_ids x 1,641 A-share tickers. |
| rows to insert | 3,282 | No affected primary keys currently exist in `realtime_current`. |
| rows to update | 0 | There are no current target rows for these two dp_ids. |
| existing rows requiring backup | 0 | The backup plan remains required before execution, but there are no existing affected rows now. |
| runtime writes attempted | 0 | The audit is read-only and does not mutate `runtime/hot.sqlite`. |
| production writes allowed | 0 | Production score writes remain disallowed. |

| Runtime write batch approvals | Count | Meaning |
|---|---:|---|
| batch-plan rows checked | 2 | Both controlled batch-plan packets were reviewed. |
| batch approval records | 2 | Approval records bind to canonical `batch_plan_sha256` values. |
| approved controlled batch plans | 2 | Both batch plans are approved for backup/execution preparation only. |
| batch policy rejected | 0 | No deterministic batch-plan policy failed. |
| planned UPSERT rows covered | 3,282 | Approval coverage matches the full planned batch size. |
| rows to insert | 3,282 | All covered rows are currently inserts. |
| rows to update | 0 | No covered rows update existing runtime records. |
| existing rows requiring backup | 0 | No existing affected rows need row-level restore data in the current DB. |
| runtime writes attempted | 0 | The approval audit is read-only and does not mutate `runtime/hot.sqlite`. |
| production writes allowed | 0 | Production score writes remain disallowed. |

| Runtime write execution | Count | Meaning |
|---|---:|---|
| approved controlled batch plans | 2 | Both batch-plan hashes were eligible for bounded execution. |
| execution-ready plans | 2 | Both plans matched current payload, scope, batch-plan, and target-list hashes. |
| execution-blocked plans | 0 | No plan failed the execution guard. |
| backups completed | 2 | A verified SQLite backup was created before the transaction. |
| backup failures | 0 | Backup `quick_check` completed successfully. |
| runtime writes completed | 2 | Both dp_id write batches completed in one transaction. |
| runtime rows written | 3,282 | `L9.media.short_report` and `L7.trade.gamma` were written for 1,641 A-share tickers each. |
| rows inserted | 3,282 | No prior target rows existed for these dp_ids. |
| rows updated | 0 | The write did not overwrite existing target rows. |
| post-write verified rows | 3,282 | Verification re-read all inserted rows after the transaction. |
| verification errors | 0 | No post-write row/count/hash verification failure was reported. |
| production writes allowed | 0 | This was a bounded runtime data write, not a production score write. |

The current runtime write preflight split is:

| Runtime write preflight | Count | Meaning |
|---|---:|---|
| approved write-plan entries | 2 | `L9.media.short_report` and `L7.trade.gamma` have approval records and matching payload hashes. |
| upsert-ready entries | 0 | No write remains pending after execution. |
| executed entries | 2 | Both approved entries have matching execution evidence. |
| blocked entries | 0 | No approved entry remains blocked at execution preflight. |
| missing target scopes | 0 | Target-scope candidates exist and have scope approvals. |
| target-scope review required | 0 | Target-scope approval is no longer the blocker. |
| controlled batch plans required | 0 | Controlled UPSERT/rollback plans now exist. |
| batch-plan candidates | 2 | Both approved scopes have matching batch-plan packets. |
| batch-plan review required | 0 | Batch-plan approval is no longer the blocker. |
| batch plans approved | 2 | Both batch-plan approval records are accepted. |
| runtime backup/execution gates required | 0 | Backup and bounded execution evidence now exists. |
| planned batch UPSERT rows | 3,282 | The candidate write size is fully quantified. |
| batch rows to insert | 3,282 | All planned rows are inserts in the current runtime DB. |
| batch rows to update | 0 | No affected rows already exist. |
| existing rows requiring backup | 0 | No existing affected rows need row-level restore data in the current DB. |
| candidate runtime rows would write if approved | 3,282 | Candidate scope is quantified but not executable. |
| runtime rows would write | 0 | The preflight intentionally produces no UPSERT batch. |
| runtime execution rows written | 3,282 | The execution report is now reflected in preflight. |
| runtime execution rows verified | 3,282 | Preflight confirms the execution report post-write verification. |
| runtime writes attempted | 2 | Attempts are inherited from the execution evidence, not performed by preflight. |
| production writes allowed | 0 | Production score writes remain disallowed. |

The current-MVP A-share applicability audit is the active final-score closure
gate. It keeps the raw 174 score-relevant field denominator visible while
removing only audit-backed non-applicable or non-current-MVP fields from the
local denominator:

| A-share final-score closure | Count | Meaning |
|---|---:|---|
| raw score-relevant final targets | 174 | Full score-relevant design denominator before current-MVP applicability. |
| raw numeric final-score fields | 132 | Fields currently proven to reach the final score. |
| current-MVP denominator | 120 | Fields still applicable to the current local MVP score path. |
| current-MVP closed fields | 120 | All applicable current-MVP fields reach final score. |
| current-MVP actionable gaps | 0 | No field remains both applicable and unclosed. |
| formula-policy exclusions | 6 | Require business/formula policy before entering scoring. |
| governance-suppression exclusions | 8 | Suppressed by canonical/replacement paths or governance rules. |
| unapproved-generation exclusions | 21 | Need governed LLM/web/human extraction before score use. |
| option-universe N/A exclusions | 3 | Current A-share universe has no legitimate single-stock option input. |
| valuation peer-context superseded | 4 | Superseded by the active `L6.state.peer_compare` peer-context path. |
| score-sink no-effect exclusions | 12 | Runtime numeric diagnostics with verified zero delta on current final-score outputs. |

The broader historical split and queue records remain in
[`docs/audit/a_share_gap_fill_plan.md`](docs/audit/a_share_gap_fill_plan.md);
the active 2026-06-20 evidence is
[`docs/audit/a_share_current_mvp_score_applicability_2026-06-20.json`](docs/audit/a_share_current_mvp_score_applicability_2026-06-20.json).

Coverage audit baseline:

- `104` means at least one of the 5 audited sources has full coverage. It is
  a coverage-capability number, not the number currently injected into
  `runtime/hot.sqlite`.
- `218` means full or partial coverage before adding the newer derivable-field
  product wording.
- `32` means no structured source covers the field directly; these fields use
  LLM / human / filing extraction, or are explicitly marked N/A / Unknown.

Avoid over-claiming proxy fields:

- `L5.surprise.sell_side` is a sell-side consensus proxy, not buy-side whisper.
- `L6.state.historical_percentile` is an alias / same-source signal for
  `L10.val.historical_quantile`, not an independent valuation signal.
- `L9.company.earnings_guidance` is `Inactive` when the company has no forecast
  announcement; that is not a missing-data failure.
- L0 partial fields are usually indirect proxies, such as commodity prices for
  raw-material cost, not direct company cost observations.
- Institutional-flow and gamma-like fields are currently proxy-backed; do not
  market them as complete 13F holdings or full options gamma exposure.

### Per-provider coverage

| Provider | mvp20 capabilities | Real endpoints / methods | Coverage notes |
|---|---:|---:|---|
| **Tushare** | 29 | 107 / 145 in-account endpoint rows | 100% in-universe; 38 out-of-scope (HK/US/期货/转债/基金/ETF/期权/外汇/黄金现货 except ETF-flow proxy rows — handled by other providers or asset-class外) |
| **FMP** *(Starter $14/mo)* | 20 active / 6 tier-locked | 48 / 80 Starter-accessible endpoint rows | Starter currently declares `analyst_estimates`, `dcf_valuation`, `sec_filings`, `macro`, and `forex`; Premium unlocks `earnings_transcripts`, minute bars, options endpoints, and FMP-specific 13F/institutional endpoints; Ultimate adds `esg_score`/`government_trading`. See [FMP_TIER_REQUIREMENTS.md](docs/data_sources/FMP_TIER_REQUIREMENTS.md) |
| **Futu OpenD** | 20 | 34 covered data mappings / 40 non-trading SDK rows | Trading/account methods deliberately excluded (mvp20 is read-only); 5 operational rows skipped; `get_security_filter` is a future screener/universe-expansion hook |
| **AKShare** | 27 | many | Free fallback; covers most A-share microstructure as Tushare cross-check |
| **yfinance** | 7 | many | Free fallback for US/HK base data |
| FRED (planned) | — | — | Activated when macro epic lands |

### Capability vocabulary (51 total, 47 active)

Grouped by purpose:
- **Price / quote**: `price_daily`, `price_intraday`, `quote_l2`, `tick_trades`,
  `realtime_push`, `broker_queue_hk`
- **Fundamentals**: `fundamentals`, `dividends`, `buyback`, `dcf_valuation`,
  `corporate_actions`
- **Analyst / research**: `analyst_estimates`, `earnings_calendar`,
  `earnings_transcripts`, `peer_comparison`
- **Filings / governance**: `sec_filings`, `insider_trading`,
  `institutional_holdings`, `government_trading`, `esg_score`
- **Capital flow / liquidity**: `capital_flow`, `cross_border_flow`,
  `market_capital_flow`, `margin_trading`
- **Microstructure / sentiment**: `dragon_tiger_list`, `limit_up_down`,
  `block_trade`, `share_unlock`, `holder_count`, `chip_distribution`,
  `sentiment_hot_list`
- **Market structure**: `sector_constituents`, `market_index`,
  `index_futures`, `warrants`, `ipo_calendar`, `ah_premium`,
  `risk_warning`, `equity_pledge`, `technical_factors`
- **Macro / rates**: `macro`, `treasury_rates`, `forex`, `commodities`
- **Reference / context**: `company_profile`, `trading_calendar`,
  `options_chain`, `options_iv`, `news`, `alternative_data`,
  `investor_relations_qa`

### Single-source capabilities (no fallback)

| Capability | Sole provider | Why it matters |
|---|---|---|
| `quote_l2` / `tick_trades` / `broker_queue_hk` / `realtime_push` / `warrants` / `index_futures` | **Futu OpenD** | HK / cross-market microstructure |
| `sec_filings` / `insider_trading` | **FMP** | Active US monitoring fields |
| `earnings_transcripts` | **FMP** | Tier-locked on current Starter plan; no active fallback |
| `dcf_valuation` / `treasury_rates` / `corporate_actions` / `peer_comparison` / `forex` | **FMP** | Active US valuation / macro utilities |
| `esg_score` / `government_trading` | **FMP** | Tier-locked Ultimate alternative data |
| `commodities` | **FRED** | Planned macro/commodity context |
| `investor_relations_qa` | **Tushare** | 上证 e 互动 / 深证易互动 — LLM training corpus |
| `alternative_data` | **AKShare** | Misc Chinese-source aggregates |

### Verification

```bash
mvp20 validate-providers     # certifies catalog structure + market coverage
```

Plus the per-CSV files in `docs/data_sources/` — re-read them when adding a
provider or capability.

## Phase Z: LLM-field governance schema

mvp20 now treats every LLM-derived dp_id as a first-class governance
object. The schema lives in
[`config/llm_field_governance.yaml`](config/llm_field_governance.yaml)
and currently registers **111 dp_ids** (the full LLM-candidate set in
the overlay schema). Each entry declares:

- `route` — `llm_close` (closed-loop, no web fetch),
  `llm_web` (web-enabled tier; requires `url` + `checksum` +
  `fetched_at`), `derive` (handled by `mvp20/derive.py`), or `skip`.
- `model_tier` — `cheap_extract`, `cheap_classify`, `analysis`, or
  `web_analysis`; consumed by both `codex_prompt_gen --model-tier` and
  the verifier's evidence-kind whitelist.
- `refresh_trigger` — `quarterly`, `event_driven`, or `on_demand`;
  combined with `Z2 fingerprint` (`mvp20/fingerprint.py`) so the next
  codex run knows when a field is stale.
- `write_policy` — typically `preserve_known_unless_triggered`, so
  `merge_preserve_existing_overlay` (Z1a, in `mvp20/overlays.py`) keeps
  the codex-filled value unless the trigger fires.

The accompanying pieces:

- **Z1a** — `merge_preserve_existing_overlay()` in `mvp20/overlays.py`
  preserves codex-filled Known / N/A / Optionality / Inactive values
  across `mvp20 generate-overlays`. The default behavior is
  preserve-merge; passing `--force` re-baselines every overlay from
  `SLOT_DEFS` (destructive — overwrites filled values).
- **Z1b** — minimal governance YAML (58 dp_ids) bootstrapping the
  schema; later expanded.
- **Z1c** — verifier (`scripts/verify_overlay_closed_loop.py`) splits
  policy into closed-loop vs web-enabled tiers based on `model_tier`.
- **Z1d** — `scripts/codex_prompt_gen.py` filters by governance
  allowlist (`route ∈ {llm_close, llm_web}`) and accepts
  `--model-tier` to scope a run to one tier.
- **Z2** — `mvp20/fingerprint.py` snapshots `(dp_id, upstream
  dp_id values, trigger event)` so a second codex run is cheap and
  idempotent unless the fingerprint changes.
- **Z3** — governance expanded from 58 → **111 dp_id** (full LLM
  schema coverage).
- **Z5** — four targeted fixes: status-induced fields no longer leak
  into prompt body, web_analysis prompt now lists `allowed_evidence_kinds`,
  event fingerprint trigger normalized, and `EVENT_DRIVEN_DP_IDS` set is
  shared between `codex_prompt_gen` and `merge_preserve_existing_overlay`.

## Bucket A: 31 hard-data dp_id extension

Bucket A (data-driven hard fields outside Phase X's 4-source baseline)
added **31 dp_ids**. At the Bucket A baseline, SQLite ∩ spec moved
105 → 136 and avg_realtime per stock moved 66.7 → 77.5. The current
runtime snapshot has moved further; use the "Spec data-point coverage"
section above for current numbers.

- **Tushare A (14)** — financial-report derived: balance-sheet ratios
  (asset-turnover, debt-to-equity, current ratio), cash-flow quality
  (OCF/NI, FCF/Sales), profitability deltas (gross-margin YoY,
  operating-margin QoQ), and working-capital indicators (DSO, DIO,
  DPO, cash-conversion-cycle).
- **Tushare B (12)** — valuation / sell-side / industry sentiment:
  forward P/E percentile vs industry, EV/EBITDA cross-section,
  sell-side rating distribution from `report_rc`, peer-relative
  revenue / earnings growth rank, and L0 industry sentiment
  aggregates.
- **Futu (3)** — option-chain derived: `L6.priced.iv` (current
  IV percentile), `L7.trade.iv` (IV change vs 30-day baseline),
  `L7.trade.options_cp` (call/put open-interest ratio).
- **AKShare (2)** — `L8.cap.outflow_cut` (large-cap outflow stress
  flag) and `L9.capital.etf_block` (ETF block-trade signal).

A/B test (Codex high / Codex low / minimax-M2 over 16 runs) — full
report and routing recommendations in
[`docs/audit/ab_test_codex_vs_minimax_v1.md`](docs/audit/ab_test_codex_vs_minimax_v1.md)
and [`docs/audit/codex_high_vs_low_v1.md`](docs/audit/codex_high_vs_low_v1.md).
See also
[`docs/data_sources/field_strategy_v1.md`](docs/data_sources/field_strategy_v1.md).

### Engine routing decisions

Picked from the A/B reports (paired-cell coverage / agreement /
token-economics):

| Tier | Recommended engine | Why |
|---|---|---|
| `cheap_extract` | **codex low** (xhigh on ambiguous SMB / consumer names) | codex-low Known coverage matches xhigh within 1 (7 vs 6) at 58% token save and 67% time save; minimax wins on flat coverage (+5) but loses local_dp_id grounding on B2B names. |
| `cheap_classify` | **codex high** | minimax leaves most slots `Unknown` (Known = 1 vs codex's 11); codex-low also drops to Known=2. Audit trail (`local_dp_id` evidence on `Inactive` slots) is required. |
| `analysis` | **minimax-M2** for bulk, **codex high** for high-materiality slots | 89% avg agreement and ~10x cheaper tokens at minimax. Reserve codex for high-materiality + low-minimax-confidence cells. codex-low works but lower local_dp_id overlap. |
| `web_analysis` | **codex high with real web** (else fall back to minimax-closed-loop) | When outbound network is sandboxed, codex emits `external_url` from training memory without checksum (soft verifier violation). minimax's industry-inference-only output is safer offline. |

## Scoring, Field Governance, and Market Adapter

mvp20 keeps the core company graph formula market-agnostic, then applies a
lightweight market adapter for A-share, US, and Hong Kong listings.

### Field governance layer

The 256 spec data points are governed by `config/data_point_roles.yaml`.
Node/schema metadata fields are governed separately by
`config/schema_field_roles.yaml`.

Every spec `dp_id` has:

- `field_role` — one of `identity`, `structure`, `raw_input`,
  `derived_metric`, `score_component`, `multiplier`, `discount`, `gate`,
  `aggregation`, `confidence`, `missing_control`, `evidence`, `display`,
  `audit`.
- `score_target` and `derived_target` — route the field to fundamental score,
  expectation gap, valuation rerating, funding score, market/theme/regime
  and policy multipliers, priced-in discount, risk discount, confidence
  multiplier, etc.
- `missing_policy` / `fallback_policy` — decide how the field behaves when
  it is `N/A`, `Unknown`, `Unavailable`, `Proxy`, `Inactive`, or
  `Optionality`.
- `neutral_value` / `confidence_penalty` / `proxy_candidates` — define
  missing-data balance without fabricating hard data.

The implementation lives in `mvp20/field_governance.py`. It validates all
256 `dp_id`s against `docs/data_sources/coverage_audit.md`, enriches overlay
node payloads, and keeps governance metadata out of the SQLite table schema.
Compiled snapshots carry governance fields inside JSON payloads only.

Missing-balance rules used by `mvp20/aggregator.py`:

- `N/A` — remove from the formula and renormalize siblings; no confidence
  penalty.
- `Unknown` — stays in the denominator, contributes zero score, and lowers
  coverage/confidence.
- `Unavailable` — try `proxy_candidates`; otherwise use `neutral_value` and
  lower confidence.
- `Proxy` — participates in the formula, but with lower evidence/confidence
  and `proxy_used` audit metadata.
- `Inactive` — no numerator or denominator contribution.
- `Optionality` — current contribution stays in the normal score; future
  option value goes to the long-horizon bucket.

Important neutral-value convention: additive score and discount fields use
`0.0`; multiplier fields use `1.0`, which means "no amplification and no
compression".

### Market adapter layer

Market-local behavior is configured in `config/market_adapters.yaml` and
implemented in `mvp20/market_adapter.py`. The shared company graph still
computes the core score. The market adapter only wraps that result:

```text
Market Adjusted Score =
  Core Final Score
  × Market Adapter Multiplier
  + Local Event Score
  + Local Funding Score
  - Local Risk Discount
  - Local Overheat / Uncertainty Discounts
```

`Market Adapter Multiplier` is horizon-specific:

```text
Market Adapter Multiplier_h =
  exp(kappa_market,h × Σ factor_weight_market,h,i × factor_score_i × stock_local_beta_i)
```

where `h` is `short`, `mid`, or `long`. Factor scores are normalized to
`[-1, 1]` with `tanh(raw_signal / 2)` by default. Missing stock profile betas
default to `1.0`, so existing overlays remain neutral until a
`stock_local_profile` is supplied.

The adapter infers market by ticker suffix unless `market_code` is present:

- `.SH`, `.SZ`, `.BJ` → `CN_A`
- `.HK` → `HK`
- everything else → `US`

Adapter components:

- `microstructure`
- `participant`
- `liquidity`
- `theme`
- `policy`
- `derivatives_shorting`
- `crossborder_fx`
- `market_regime`

The current v2 maps existing routed `role_components` into those buckets and
uses separate kappa / weight tables for short-, mid-, and long-horizon scores:

- A-share emphasizes theme heat, retail/hot-money funding, market regime,
  policy sensitivity, and local risk.
- US emphasizes options/gamma/volatility, institutional/funding signals,
  market regime, expectation events, and litigation/short/volatility risk.
- Hong Kong emphasizes southbound/cross-border flow proxies, liquidity repair,
  market regime, policy expectation, short/derivatives pressure, and local
  governance/liquidity discounts.

`score_company()` now returns both:

- `core_final_score` — result before market adapter.
- `final_score` / `market_adjusted_final_score` — result after market adapter.

The top-level `short_total`, `medium_total`, `long_total`, `mode`, and
`trading_signal` use the market-adjusted score so existing API/CLI consumers
continue to read the final decision result without changing field names.

A new realtime→score bridge now wires governance `participates_in_score` real
fields from `realtime_current` into the stock `final_score` via
`aggregate_company_graph(realtime_snapshot=...)` (previously the
realtime/derived layer did not affect the score at all).

## Not Claimed

- Default/full propagation enabled.
- Broad production rollout complete.
- M4.7/financial-doc complete.
- Contracts subtype changes.
- New relation types.
- A-share score completion complete. Current-MVP denominator closure is complete;
  raw 174-field closure remains 132 / 174.
- Runtime score writes approved. The 2026-06-20 execution was a bounded runtime
  data write with production score writes still disallowed.

## Local Checks

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e ".[dev]"

# Optional: install vendored upstream modules for import-level debugging.
# Adapter routes primarily serve local frontend-api artifacts; package imports
# are fallback evidence, not the normal current-MVP route depth.
for d in contracts audit-eval data-platform entity-registry graph-engine main-core reasoner-runtime; do
  .venv/bin/pip install -e "./upstream/$d" --no-deps --ignore-requires-python
done

.venv/bin/mvp20 validate-manifest --manifest config/mvp20.universe.yaml
.venv/bin/mvp20 verify-lock --lock locks/modules.lock.yaml
.venv/bin/mvp20 plan-backfill --manifest config/mvp20.universe.yaml
.venv/bin/mvp20 validate-graphs
.venv/bin/mvp20 validate-providers
.venv/bin/mvp20 generate-overlays --period 2026-Q1
.venv/bin/mvp20 validate-overlays
.venv/bin/mvp20 compile-overlays --db runtime/hot.sqlite
.venv/bin/mvp20 run-fixture-e2e
.venv/bin/python scripts/audit_module_status.py --output docs/audit/module_status_2026-06-20.json
.venv/bin/python scripts/audit_completion_deviation.py
.venv/bin/python -m pytest
.venv/bin/python -m pytest -q tests/test_field_governance.py tests/test_missing_balance.py tests/test_market_adapter.py tests/test_scoring.py
git diff --check
```

## Frontend ↔ Backend Dev Wiring

The `FrontEnd/` directory holds a Vite + React + TypeScript app that
expects an HTTP backend serving `/api/project-ult/*`. mvp20 ships a
read-only stdlib HTTP server (`mvp20 serve`) that exposes its
manifest / industry / provider data so the frontend can render real
data without standing up the full upstream `project-ult-frontend-api`.

### Start the backend

```bash
.venv/bin/mvp20 serve --port 8701
# → mvp20 HTTP server listening on http://127.0.0.1:8701/api/*
```

### Data layer architecture (phase 1 + 2)

The server now sits on top of **four storage layers** wired together by
`handle_stock_overlay`:

1. **Static overlay source** — YAML under
   `config/stock_overlays/<industry_id>/<ts_code>.yaml` and
   `config/industry_overlays/<industry_id>.yaml` (31 graph nodes per
   industry, agent-generated, git-tracked, quarterly cadence).
   `SPACE_ECONOMY` has pending industry
   graph/overlay stubs but no stock overlays.
2. **Compiled graph snapshot** — SQLite WAL file `runtime/hot.sqlite` stores
   `overlay_manifest`, `company_node_instance`, `company_edge_instance`,
   `overlay_alert`, and `company_graph_snapshot`. The frontend reads
   `company_graph_snapshot.payload_json` so requests do not merge YAML live.
3. **Hot snapshot** — the same SQLite WAL file is written by
   `scripts/collector.py` every ~60s; same `(ts_code, dp_id)` UPSERTs in
   place, so the table is always the current minute-level snapshot. Reads
   are sub-millisecond.
4. **Minute history** — columnar archive files under
   `runtime/history/minute/` appended by the same collector, queried via
   DuckDB for 24h / 7d replays. A daily `scripts/compact_history.py` cron
   compacts yesterday's per-minute files into one
   `runtime/history/daily_compact/date=YYYY-MM-DD` archive.

### Where downloaded data and graph information lives

The storage split is deliberate: durable graph definitions stay in YAML,
current values stay in SQLite for low-latency reads, and historical minute
series stay in Parquet for replay and analysis.

| Data / information type | Storage location | Update mode | Purpose |
|---|---|---|---|
| Industry graph templates | `config/industry_graphs/<industry_id>.yaml` | authored / quarterly | Base causal graph and industry priors |
| Industry overlay nodes | `config/industry_overlays/<industry_id>.yaml` | agent / quarterly | 31 industry graph nodes; inherited by stock overlays |
| Stock overlay source | `config/stock_overlays/<industry_id>/<ts_code>.yaml` | agent / quarterly | Full company graph slots, missing policies, calculation types, edges, scores, views |
| Field governance config | `config/data_point_roles.yaml`, `config/schema_field_roles.yaml` | authored / reviewed | 256 dp_id roles, score targets, missing fallback, proxy candidates, neutral values |
| Market adapter config | `config/market_adapters.yaml` | authored / reviewed | CN_A / US / HK local multipliers, scores, and discounts applied outside the core graph |
| Compiled overlay manifest | `runtime/hot.sqlite:overlay_manifest` | `mvp20 compile-overlays` | Which company-industry overlays exist and which one is primary |
| Compiled nodes | `runtime/hot.sqlite:company_node_instance` | `mvp20 compile-overlays` | Queryable node instances with status, materiality, and calculation metadata |
| Compiled edges | `runtime/hot.sqlite:company_edge_instance` | `mvp20 compile-overlays` | Hierarchy and causal edge instances kept separate |
| Frontend graph snapshot | `runtime/hot.sqlite:company_graph_snapshot` | `mvp20 compile-overlays` | Main API read object; avoids live YAML merging per request |
| Overlay alerts | `runtime/hot.sqlite:overlay_alert` | `mvp20 compile-overlays` | `Unknown + required` / `Unknown + conditional_required` alert records |
| Current minute values | `runtime/hot.sqlite:realtime_current` | collector UPSERT every ~60s | Latest market / flow / event values by `(ts_code, dp_id)` |
| Freshness metadata | `runtime/hot.sqlite:freshness_meta` | collector / compiler | Last successful sync timestamps and layer status |
| Minute history | `runtime/history/minute/partition_minute=YYYYMMDD_HHMM` | collector append when `--enable-history` is set | Time-series replay and analysis |
| Daily compact history | `runtime/history/daily_compact/date=YYYY-MM-DD` | daily compact job | Lower-file-count historical archive for DuckDB scans |

Important behavior:

- `realtime_current` stores only the latest value for each `(ts_code, dp_id)`;
  it overwrites in place and does not keep history.
- Parquet history is append-only by collector cycle and is used by
  `/api/project-ult/history`, not by the main stock-overlay read path.
- `company_graph_snapshot.payload_json` is the frontend's primary graph
  object. It contains `compiled_graph`, `scores`, `coverage`, `alerts`, and
  the static overlay source used to build the snapshot.
- Runtime files under `runtime/` are local artifacts. YAML under `config/`
  is the auditable source that should be reviewed and versioned.

Start collector + server together::

```bash
# One-shot: create the SQLite schema
.venv/bin/python scripts/init_hot_db.py

# Generate/validate/compile graph overlays
.venv/bin/mvp20 generate-overlays --period 2026-Q1
.venv/bin/mvp20 validate-overlays
.venv/bin/mvp20 compile-overlays --db runtime/hot.sqlite

# Terminal 1 — minute-level collector (use --source mock for development)
.venv/bin/python scripts/collector.py --source mock --interval 60 --enable-history

# Production-like real refresh: focused Tushare routes first, then Futu/FMP/AKShare
.venv/bin/python scripts/collector.py --source real --interval 60 --enable-history

# Focused one-shot A-share Tushare refreshes
TUSHARE_TIMEOUT_SECONDS=3 .venv/bin/python scripts/collector.py --source tushare-core --max-cycles 1
TUSHARE_TIMEOUT_SECONDS=3 .venv/bin/python scripts/collector.py --source tushare-market-env --max-cycles 1
TUSHARE_TIMEOUT_SECONDS=3 .venv/bin/python scripts/collector.py --source tushare-macro --max-cycles 1
TUSHARE_TIMEOUT_SECONDS=3 .venv/bin/python scripts/collector.py --source tushare-crowding --max-cycles 1
TUSHARE_TIMEOUT_SECONDS=3 .venv/bin/python scripts/collector.py --source tushare-report-rc --max-cycles 1
TUSHARE_TIMEOUT_SECONDS=3 .venv/bin/python scripts/collector.py --source tushare-report-signals --max-cycles 1
TUSHARE_TIMEOUT_SECONDS=3 TUSHARE_EARNINGS_RISK_SAMPLE_SIZE=256 .venv/bin/python scripts/collector.py --source tushare-earnings-risk --max-cycles 1
TUSHARE_TIMEOUT_SECONDS=3 .venv/bin/python scripts/collector.py --source tushare-industry-valuation --max-cycles 1
TUSHARE_TIMEOUT_SECONDS=3 .venv/bin/python scripts/collector.py --source tushare-preprice --max-cycles 1
AKSHARE_CALL_TIMEOUT_S=30 .venv/bin/python scripts/collector.py --source akshare-block-trade --max-cycles 1
AKSHARE_CALL_TIMEOUT_S=30 .venv/bin/python scripts/collector.py --source akshare-cls --max-cycles 1

# Terminal 2 — BFF server
.venv/bin/mvp20 serve --port 8701

# Optional: pull 24h history for one (ts_code, dp_id)
curl "http://127.0.0.1:8701/api/project-ult/history?ts_code=300750.SZ&dp_id=L7.flow.netbuy"
# Optional: open SSE stream
curl -N "http://127.0.0.1:8701/api/project-ult/stream/realtime?ts_code=300750.SZ&industry_id=STORAGE_GRID"
```

The server is **read-only**. The table below lists the core route examples;
`mvp20/server.py` is the source of truth for the full route regex list.

| Route | Returns |
|---|---|
| `/api/health` | service liveness |
| `/api/project-ult/health` | mvp20 module count + lock validity |
| `/api/project-ult/compat` | schema versions |
| `/api/project-ult/manifests/latest` | universe.yaml + industries.yaml |
| `/api/project-ult/modules` | modules.lock.yaml as JSON |
| `/api/project-ult/reasoner/providers` | data_providers.yaml + validation summary |
| `/api/project-ult/profiles` | universe constituents (filterable by `ts_code` / `industry` / `pool` / `role` / `market` query strings) |
| `/api/project-ult/industry-graphs` | list of 12 strict-valid industry graphs (or `?industry_id=X` for one; `SPACE_ECONOMY` is a pending stub) |
| `/api/project-ult/cycles` | empty list (cycles are produced by upstream main-core) |
| `/api/project-ult/stock-overlay?ts_code=X` | compiled primary-industry overlay + realtime + scores + coverage + alerts |
| `/api/project-ult/stock-overlay?ts_code=X&industry_id=Y` | compiled overlay for a specific company-industry view |
| `/api/project-ult/stream/realtime?ts_code=X&industry_id=Y` | Server-Sent Events stream emitting `snapshot` / `delta` / `heartbeat` frames |
| `/api/project-ult/history?ts_code=X&dp_id=Y` | time-ordered minute history points (Parquet + DuckDB) |
| `/api/subsystems/status` | per-module unknown/locked status |
| `/api/project-ult/market-events` | latest cross-stock realtime event stream payload |
| `/api/project-ult/technicals?ts_code=X` | MA / MACD / RSI / KDJ / BOLL / VOL / ATR / OBV pack |
| `/api/project-ult/aggregate`, `/api/project-ult/coverage`, `/api/project-ult/score` | derived layer aggregate, coverage, and score envelopes |
| `/api/project-ult/signals/top?horizon=5&market=A_share` | A-share 5d relative signal ranking from `runtime/signal_5d/A_share.json`; `probability` is the selected per-stock source (`logistic_multifeature_7f` only if gates pass, otherwise `score_pct_linear_bin10`), with model/fallback/legacy fields exposed; HK/US return an honest empty envelope until separately calibrated |
| `/api/project-ult/signals/stock?ts_code=X&horizon=5` | one A-share 5d relative signal block with `validated`, `stale`, `reason`, direction, strength, drivers, risks, `model_method`, `probability_source`, `feature_coverage`, `model_probability`, `model_probability_shadow`, and `legacy_bin_probability` |
| `/api/admin/*`, `/api/alerts/*` | local mvp20 BFF empty-state stubs |

Adapter-backed route families include
`/api/project-ult/graph/*`, `/api/project-ult/data/canonical/*`,
`/api/project-ult/data/raw/*`, `/api/project-ult/entities*`,
`/api/project-ult/reasoner/*` except `/reasoner/providers`,
`/api/project-ult/cycles/<id>`, `/api/stocks/*`, `/api/pool/*`,
`/api/world-state/*`, `/api/project-ult/audit/*`, `/api/audit/*`,
`/api/project-ult/backtests*`, and `/api/backtest/*`.

Six upstream `project-ult-*` modules (graph-engine, audit-eval, main-core,
data-platform, entity-registry, reasoner-runtime) plus `contracts` (their
shared base) are vendored under `upstream/` as plain source directories. The
current MVP does not treat those six modules as production-normal services.
Instead, `mvp20/adapters/<module>.py` serves the bounded
`upstream/*/artifacts/frontend-api/` payloads used by the local BFF contract.
Successful adapter responses carry `fixture: true`, `wire_depth: artifact`,
and an `artifact_path`. If an artifact is missing and the optional vendored
package is also unavailable, the adapter returns a structured
`503 UPSTREAM_UNAVAILABLE` envelope with the import error in
`details.import_error`; UI callers still receive a clean envelope, not a crash.

There are no deliberately 503-only placeholder routes in the normal mvp20
surface anymore. Adapter routes can still return `503 UPSTREAM_UNAVAILABLE`
when a vendored package cannot import because an optional runtime dependency
is missing. `frontend-api` is intentionally NOT vendored under `upstream/` —
`FrontEnd/` is the sole frontend in this repo and mvp20 `server.py` acts as
its BFF directly. Legacy `/api/admin/*` and `/api/alerts/*` paths are handled
by mvp20 with empty stub envelopes (`module: mvp20-bff, fixture: true`) so the
UI shows clean empty states instead of error banners.

### Runtime services (optional, for deeper-than-artifact wire)

The vendored packages have heavy runtime deps that are deliberately **not**
installed by `pip install -e ".[dev]"`:

| Vendor | Service | Notes |
|---|---|---|
| `graph-engine` | Neo4j on the standard Bolt port locally | `docker run -p 7687:7687 neo4j:5` |
| `data-platform` | DuckDB / Iceberg catalog | `pip install duckdb dbt-duckdb pyarrow` |
| `reasoner-runtime` | LLM API keys + `pip install litellm instructor` | env: `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` |
| `entity-registry` | (none — pure in-memory lib) | already wired |
| `main-core` | (none for artifact adapter) | only needs pydantic, already installed |
| `audit-eval` | DuckDB + evidently | `pip install duckdb evidently` |

Without these backing services, artifact adapters still return 200 fixture
data from `upstream/*/artifacts/frontend-api/` when the artifact is present.
If both the artifact and optional vendor import path are unavailable, the
adapter returns `503 UPSTREAM_UNAVAILABLE`; unexpected handler exceptions are
surfaced by the HTTP layer as `500 HANDLER_ERROR`.

### Start the frontend

```bash
cd FrontEnd
npm install              # first time only
npm run dev              # Vite dev server on http://127.0.0.1:1420
```

Wiring is done via `FrontEnd/.env.local` (gitignored):

```
VITE_DATA_MODE=projectUlt
VITE_PROJECT_ULT_PROXY_TARGET=http://127.0.0.1:8701
```

With `VITE_PROJECT_ULT_PROXY_TARGET` set, Vite proxies every `/api/*`
request from `:1420` to mvp20 backend at `:8701`. The browser stays
same-origin (no CORS preflight). To test without the proxy, swap
`VITE_PROJECT_ULT_PROXY_TARGET` for `VITE_PROJECT_ULT_API_BASE_URL=http://127.0.0.1:8701/api`
— mvp20 server already advertises CORS for `http://127.0.0.1:1420`.

### Current response baseline

The 2026-06-17 through 2026-06-19 audits focused on keeping the projectUlt
frontend visible state under 1 second without changing the business surface.
The measured local warm/browser and production-preview evidence is:

| Surface | Historical/context evidence | Current 2026-06-19 evidence | Notes |
|---|---:|---:|---|
| Market overview `/?data_mode=projectUlt` | 544 ms historical warm visible | 98 ms production-preview first-`h1` wait / 221 ms navigation-to-`h1` | no browser error overlay; empty console error/warn |
| Pool `/pool?data_mode=projectUlt` | route covered by 20-route shell audit | 106 ms production-preview first-`h1` wait / 240 ms navigation-to-`h1` | no browser error overlay; empty console error/warn |
| Stock detail `/stock/300750.SZ?data_mode=projectUlt` route identity | 347 ms historical warm visible | 173 ms follow-up production-preview first-`h1` wait | no browser error overlay; empty console error/warn |
| Stock detail core ready | 945 ms desktop production preview | 875 ms mobile 390px recheck | header + graph shell + score content under 1s |
| Stock detail enriched ready | 1.429 s desktop production preview | 1.366 s mobile 390px recheck | lower-page aggregate path graph, technicals, and history sparkline are deferred |
| Stock detail mobile 390px | 140 ms first-`h1` route identity | 875 ms core ready | no page-level horizontal overflow; status bar scrolls internally |
| `查看解释链` interaction | 306 ms | n/a | drawer opened for `300750.SZ`; empty console error/warn |
| 20 Project ULT SPA shell routes | 14.526 ms max shell response | n/a | `docs/audit/frontend_shell_latency_2026-06-19.json`; HTTP shell only, not hydration |
| Project ULT route/navigation contract | 20/20 App route samples covered; 8/8 read-only links covered | Browser spot-check: `/project-ult/system -> /project-ult/evidence` | `docs/audit/frontend_project_ult_navigation_2026-06-19.json`; source registry + shell latency contract |

Relevant BFF hot-path timings from the temporary local audit server:

| Endpoint | Status | Time | Size |
|---|---:|---:|---:|
| `/api/project-ult/profiles?ts_code=300750.SZ` | 200 | 0.000554 s | 218 B |
| `/api/project-ult/industry-graphs?industry_id=STORAGE_GRID` | 200 | 0.000561 s | 28,196 B |
| `/api/project-ult/market-events?limit=8` | 200 | 0.104737 s | 3,398 B |
| `/api/project-ult/stock-overlay?ts_code=300750.SZ&include_static=0` | 200 | 0.008061 s | 344,884 B |
| `/api/project-ult/aggregate?ts_code=300750.SZ&industry_id=STORAGE_GRID` | 200 | 0.001727 s | 166,027 B |
| `/api/project-ult/coverage?ts_code=300750.SZ` | 200 | 0.000616 s | 5,778 B |
| `/api/project-ult/score?ts_code=300750.SZ` | 200 | 0.000793 s | 6,891 B |

The current implementation uses an mtime-aware YAML cache in the BFF,
`profiles?ts_code=` for single-stock profile reads, browser request
cancellation handling, frontend query abort signals, MarketOverview
StockDetail chunk prefetch/profile prehydration, staged heavy stock-detail data
fetches, and a lazy `PathGraphPanel` split. The production route chunk dropped
from roughly 256.87 kB to 115.96 kB while the path graph moved to a deferred
chunk. `stock-overlay` keeps its default full response for compatibility, while
the frontend hot path adds `include_static=0` to omit unused static overlay and
industry context payloads. `FrontEnd/` is gitignored in this repository, so
frontend source changes are local-on-disk and do not appear in `git diff`.

### Switch back to demo mode

```
# FrontEnd/.env.local
VITE_DATA_MODE=demo
```

In demo mode the frontend uses MSW handlers (`src/mocks/`) — no backend
required. Useful for visual debugging when the manifest / catalog isn't
relevant.

### Quick smoke

```bash
# Terminal 1
.venv/bin/mvp20 serve

# Terminal 2
cd FrontEnd && npm run dev

# Terminal 3 — proxy through Vite
curl http://127.0.0.1:1420/api/health
curl http://127.0.0.1:1420/api/project-ult/manifests/latest
```

The checked-in manifest is the curated 13-industry leader pool (A-share,
Hong Kong, and US listings; ~328 constituents covering the 12 present
industries). `live_evidence_blocked: true` remains until per-provider
data wiring is calibrated; flipping the gate is an explicit operator
action, not part of constituent ingestion.
