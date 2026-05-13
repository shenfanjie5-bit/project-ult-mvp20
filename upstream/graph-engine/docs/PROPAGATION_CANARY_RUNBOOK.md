# Propagation Canary Runbook

This runbook is for the guarded holdings propagation canary only. Issue #55
is CLOSED/COMPLETED for holdings-only explicit algorithms:
`run_co_holding_crowding`, `run_northbound_anomaly`, and
`run_holdings_algorithms`. It does not restore the old financial-doc,
guarantee-chain, related-party, contracts subtype, or broad propagation scope.

## Scope

- Relationship scope is limited to `CO_HOLDING` and `NORTHBOUND_HOLD`.
- The canary is opt-in and gated. It does not enable default or full
  propagation.
- The canary evidence does not mean broad rollout is complete.
- The canary writes Layer A artifacts before the live-graph sync and then uses
  read-only checks and explicit holdings algorithms for diagnostics.
- The canary must not emit formal graph snapshots or write algorithm results
  back to Neo4j.

## Required Gates

Before any live PG or Neo4j proof path is allowed:

- Set `GRAPH_ENGINE_LIVE_GRAPH_ROLLOUT_CONFIRM=1` in the runner environment.
- Use `LiveGraphRolloutConfig.mode="canary"` for `run_live_graph_canary`.
- Use a unique namespace such as `canary-<ticket>-<date>`. Do not use
  `default`, `live`, `main`, `neo4j`, `prod`, `production`, or `system`.
- Use a disposable Neo4j database whose name contains `canary`, `proof`,
  `rollout`, `smoke`, or `test`. The default `neo4j` database and production
  database labels are forbidden.
- Verify the actual Neo4j client database matches the guarded config before
  promotion or sync.
- Set `allowed_relationship_types` to holdings relationships only. Do not add
  `SUPPLY_CHAIN`, `OWNERSHIP`, financial-doc, or subtype relationship values.
- Keep PG DSNs, Neo4j credentials, tokens, and local proof paths in the runner
  environment or secret manager only. Do not write persistent repo config.

## Execution Checklist

1. Select a small, frozen canary candidate set from the upstream queue.
2. Validate every candidate delta before promotion. The set must contain only
   `CO_HOLDING` and `NORTHBOUND_HOLD`.
3. Validate the rollout config, namespace, disposable Neo4j database label,
   artifact root, and client database match.
4. Require `Neo4jGraphStatus.graph_status == "ready"` and no active writer
   lock before promotion.
5. Run `run_live_graph_canary` with injected candidates, entity reader, Neo4j
   client, status manager, and guarded config.
6. Confirm the Layer A artifact summary exists before accepting any Neo4j sync
   result.
7. Read back synced edges with `readback_canary_edges`. This must be a
   read-only query scoped by promoted `edge_id` values.
8. Require post-sync ready status before algorithm diagnostics.
9. Run only explicit holdings diagnostics through
   `run_holdings_canary_algorithms`. Do not call or route through
   `run_full_propagation`.
10. Write only sanitized evidence under the canary namespace.

## Layer A To Sync Verification

A passing canary must show all of these in sanitized evidence:

- Layer A artifact relation counts match the candidate scope.
- Neo4j readback `missing_edge_ids` is empty.
- Neo4j readback `disallowed_relation_types` is empty.
- Readback relation counts contain only `CO_HOLDING` and `NORTHBOUND_HOLD`.
- Pre-sync and post-sync graph status are both ready.
- Algorithm diagnostics include separate co-holding and northbound summaries.

Any mismatch fails the canary. Do not broaden the allowlist to make the
readback pass.

## Rollback And Diagnostics

The canary rollback posture is fail-closed:

- Stop on guard, Layer A, sync, readback, or algorithm diagnostic failure.
- Do not run destructive reload from this canary runbook.
- If a disposable Neo4j database is contaminated, discard or recreate that
  disposable database out of band. Never repair by targeting the default DB.
- Use `write_cold_reload_replay_evidence` only to prove a reload artifact can
  be read. Its evidence must keep `destructive_reload_executed` false.
- Treat zero or unexpected algorithm counts as read-only diagnostics. They do
  not authorize default propagation, full propagation, broad rollout, or
  graph writeback.

## Evidence Hygiene

Do not commit runtime artifacts, parquet files, generated manifests, stdout,
stderr, exit-code files, local proof paths, tokens, DSNs, or raw provider
payloads. Evidence committed to the repo must be documentation or tests only,
not live run output.

## Verification Commands

```bash
git diff --check
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -p no:cacheprovider -q \
  tests/unit/test_rollout.py tests/unit/test_rollout_runbook.py \
  tests/unit/test_holdings_live_graph_proof.py
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -p no:cacheprovider -q \
  tests/unit/test_propagation_holdings.py tests/unit/test_propagation_merge.py \
  tests/unit/test_propagation_channels.py tests/unit/test_schema.py \
  tests/boundary/test_red_lines.py
```
