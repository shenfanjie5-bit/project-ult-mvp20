# MVP20 Runbook

## Scope

The MVP uses a fixed 20-stock decision universe with a 120-month history window
and a two-hop graph context. Related listed companies are included in graph and
risk summaries as `context_only`; they are not decision targets.

## Operator Gates

1. Fill `config/mvp20.universe.yaml` with exactly 20 real A-share `ts_code`
   values.
2. Run `mvp20 validate-manifest`.
3. Run `mvp20 verify-lock` and confirm every dependency is pinned to a full
   commit SHA, not `main`.
4. Run `mvp20 plan-backfill` and review provider gaps.
5. Run fixture and live evidence only through explicit gates.

## Evidence Hygiene

Do not commit raw provider payloads, DSNs, tokens, local runtime paths, parquet
files, generated manifests, stdout/stderr captures, or exitcode files.

## Not Claimed

- Default/full propagation enabled.
- Broad production rollout complete.
- M4.7/financial-doc complete.
- Contracts subtype changes.
- New relation types.
