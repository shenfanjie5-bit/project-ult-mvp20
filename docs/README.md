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
  unvalidated rows must remain explicit in API/UI evidence. Historical evidence
  is in `audit/2026-06-20_a_share_signal_5d_backtest_10_dates.json`: 12
  walk-forward dates, no future calibration bins, avg rank IC 0.0245, avg Brier
  skill 0.00034, and avg top-20 excess -0.24pp.
