# MVP Docs

- [Runbook](RUNBOOK.md)
- [Data source coverage audit](data_sources/coverage_audit.md)
- [LLM-derived overlay slots](data_sources/llm_derived_nodes.md)

This documentation is intentionally scoped to the 13-industry MVP orchestration
shell. It records how to validate a bounded industry-driven universe, lock
upstream module commits, plan bounded data work, and prove fixture-level
end-to-end behavior.

Current storage split:

- YAML under `config/industry_overlays/` and `config/stock_overlays/<industry_id>/`
  is the auditable graph-overlay source.
- SQLite `runtime/hot.sqlite` stores compiled graph snapshots, overlay alerts,
  freshness metadata, and the current minute-level value per `(ts_code, dp_id)`.
- Parquet under `runtime/history/` stores minute-level history for replay and
  analysis when collector history is enabled.
