# MVP Docs

- [Runbook](RUNBOOK.md)
- [Data source coverage audit](data_sources/coverage_audit.md)
- [LLM-derived overlay slots](data_sources/llm_derived_nodes.md)
- [Current-MVP completion/deviation audit](audit/completion_deviation_2026-06-20.md)
- [A-share current-MVP score applicability](audit/a_share_current_mvp_score_applicability_2026-06-20.md)
- [DOCKCASE CSV quality impact](audit/dockcase_csv_quality_impact_2026-06-20.md)

This documentation is intentionally scoped to the 13-industry MVP orchestration
shell. It records how to validate a bounded industry-driven universe, lock
upstream module commits, plan bounded data work, and prove fixture-level
end-to-end behavior.

Current 2026-06-20 evidence reports 100.0% current-MVP completion, 0.0%
deviation, A-share actionable gap 0, BFF/API smoke under 1s, and DOCKCASE
current-MVP data-quality actionable gap 0. The upstream locked-module status is
contract-surface complete for this local MVP through artifact-backed adapters,
an importable `contracts` dependency, and explicit replacement/missing-source
paths; it is not a claim that every locked upstream module runs locally as a
production-normal service.

Current storage split:

- YAML under `config/industry_overlays/` and `config/stock_overlays/<industry_id>/`
  is the auditable graph-overlay source.
- SQLite `runtime/hot.sqlite` stores compiled graph snapshots, overlay alerts,
  freshness metadata, and the current minute-level value per `(ts_code, dp_id)`.
- Parquet under `runtime/history/` stores minute-level history for replay and
  analysis when collector history is enabled.
