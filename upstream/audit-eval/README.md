# audit-eval

`audit-eval` is the project-ult audit, replay, retrospective evaluation,
drift, backtest, and shared fixture module. It is no longer scaffold-only.

Source of truth:

- `docs/audit-eval.project-doc.md`
- `docs/PROGRESS.md`

Current workspace state:

- `audit_eval.audit` contains durable audit/replay storage adapters, write
  entrypoints, manifest-bound replay query support, and Lite/local storage.
- `audit_eval.retro` contains retrospective schemas, T+1 and multi-horizon
  computation helpers, summaries, cumulative alert logic, backfill support, and
  the retrospective hook path.
- `audit_eval.drift` contains drift report schemas, rule classification,
  runner interfaces, storage adapters, and JSON report writing boundaries.
- `audit_eval.backtest` contains point-in-time checking, backtest job/result
  schemas, Alphalens adapter boundaries, runners, and result persistence.
- `audit_eval_fixtures` publishes shared minimal-cycle, event-case, and
  historical replay fixture packs for downstream regression tests.
- `audit_eval.public` exposes the assembly public entrypoints used by module
  registry compatibility checks.

What is still out of scope here:

- Do not treat this as proof that the production daily audit -> replay ->
  retrospective -> drift/backtest loop is fully wired end to end.
- Dagster scheduling, production AssetChecks, downstream module adoption, and
  dependency/version pin rollout are orchestrator follow-up work, not work to
  complete inside `audit-eval`.
- Replay bundle generation remains owned by the calling runtime; this module
  persists and reconstructs replay records from historical data.
- Contract changes must happen only through an explicit contracts task.

Execution rule:

1. read the project doc and progress tracker first
2. keep work inside this module unless the issue explicitly targets shared
   contracts
3. preserve `read_history` replay semantics; replay must reconstruct from
   persisted history and manifest-bound refs, not re-run the current model
