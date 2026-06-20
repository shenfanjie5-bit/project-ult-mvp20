# MVP Docs

- [Runbook](RUNBOOK.md)
- [Data source coverage audit](data_sources/coverage_audit.md)
- [LLM-derived overlay slots](data_sources/llm_derived_nodes.md)
- [Current-MVP completion/deviation audit](audit/completion_deviation_2026-06-20.md)
- [A-share current-MVP score applicability](audit/a_share_current_mvp_score_applicability_2026-06-20.md)
- [DOCKCASE CSV quality impact](audit/dockcase_csv_quality_impact_2026-06-20.md)
- [A-share 5d signal artifact audit](audit/2026-06-20_a_share_signal_5d_artifact_audit.json)
- [A-share 5d signal BFF smoke](audit/2026-06-20_a_share_signal_5d_bff_smoke.json)
- [A-share 5d signal frontend binding](audit/2026-06-20_a_share_signal_5d_frontend_binding.json)
- [A-share 5d signal review audit](audit/2026-06-20_a_share_signal_5d_review_audit.json)
- [A-share 5d signal 12-date backtest](audit/2026-06-20_a_share_signal_5d_backtest_10_dates.json)
- [A-share 5d signal contract smoke](audit/2026-06-20_a_share_signal_5d_contract_smoke.json)
- [A-share 5d model 12-date backtest](audit/2026-06-20_a_share_signal_5d_model_backtest.json)
- [A-share 5d model 42-date backtest](audit/2026-06-20_a_share_signal_5d_model_backtest_42_dates.json)
- [A-share absolute up-5d artifact audit](audit/2026-06-21_a_share_signal_up_5d_artifact_audit.json)
- [A-share absolute up-5d 12-date backtest](audit/2026-06-21_a_share_signal_up_5d_model_backtest_12_dates.json)
- [A-share absolute up-5d 42-date backtest](audit/2026-06-21_a_share_signal_up_5d_model_backtest_42_dates.json)
- [A-share absolute up-5d BFF smoke](audit/2026-06-21_a_share_signal_up_5d_bff_smoke.json)
- [A-share absolute up-5d frontend binding](audit/2026-06-21_a_share_signal_up_5d_frontend_binding.json)
- [A-share relative 5d utility review](audit/2026-06-21_a_share_signal_5d_utility_review.json)

This documentation is intentionally scoped to the 13-industry MVP orchestration
shell. It records how to validate a bounded industry-driven universe, lock
upstream module commits, plan bounded data work, and prove fixture-level
end-to-end behavior.

Current 2026-06-20 evidence reports 100.0% current-MVP completion, 0.0%
deviation, A-share actionable gap 0, BFF/API smoke under 1s, and DOCKCASE
current-MVP data-quality actionable gap 0. The upstream locked-module status is
contract-surface complete for this local MVP through artifact-backed adapters,
an importable `contracts` dependency, and verified replacement paths; it is not
a claim that every locked upstream module runs locally as a
production-normal service.

Current storage split:

- YAML under `config/industry_overlays/` and `config/stock_overlays/<industry_id>/`
  is the auditable graph-overlay source.
- SQLite `runtime/hot.sqlite` stores compiled graph snapshots, overlay alerts,
  freshness metadata, and the current minute-level value per `(ts_code, dp_id)`.
- Parquet under `runtime/history/` stores minute-level history for replay and
  analysis when collector history is enabled.
- `runtime/signal_5d/A_share.json` stores the backend A-share 5-day relative
  signal artifact used by the workbench. Its target is 5d probability of
  beating the same-day liquid-universe median, not absolute P(up); stale and
  unvalidated rows must remain explicit in API/UI evidence. The v2 calibration
  exports a 7-feature ridge-logistic candidate and a legacy-bin fallback. The
  12-date model evidence passes the aggressive gate, but the required 42-date
  evidence fails Brier-skill and rank-IC-vs-fallback, so the current production
  `probability_source` is `score_pct_linear_bin10` and the logistic output is
  retained as `model_probability_shadow`. Current artifact evidence shows 1,610
  rows, 1,100 validated rows, and 37 distinct 1-decimal validated
  probabilities. Stale rows may show gray `过期预览` values for inspection, but
  they remain invalid for signal counts.
- `runtime/signal_up_5d/A_share.json` stores the parallel absolute A-share
  5-day upside artifact. Its target is `P(5d return > 0)` with
  `target_kind=absolute_up_5d`; it is not the relative win-rate signal and does
  not reuse `final_score.base_score` as a probability. The 2026-06-21 12-date
  run passed the fast gate, but the 42-date stability gate failed. Current rows
  therefore expose shadow/fallback probabilities with `validated=false`; stock
  detail may show them as an over-date preview, while workbench sorting should
  remain based on `signal_5d`.
