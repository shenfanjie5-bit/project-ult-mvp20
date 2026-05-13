# Entity Registry Production Readiness Gate Evidence - 2026-05-07

## Scope

This evidence covers the first production-readiness gate for entity-registry
runtime wiring. It proves fail-fast behavior around resolution audit writes and
adds a local JSON evidence runner.

## What The Gate Checks

- `profile=production` rejects `InMemory*` repositories unless a local/test
  profile explicitly allows them.
- Public resolution requires both `reference_repo` and `case_repo`.
- The reference audit repository must expose
  `save_resolution(reference, case)`.
- The reference audit repository must expose
  `owns_resolution_case_repository(case_repo)` and return true for the
  configured case repository.
- Split reference/case audit repositories fail before mutation.
- Deterministic audit write failure fails closed and does not return a
  successful resolution result.
- Unresolved resolution writes both reference and case audit records without
  minting a synthetic canonical entity ID.

## Evidence Runner

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:../contracts/src .venv/bin/python scripts/entity_registry_readiness_probe.py --profile production --json
```

The runner emits JSON with:

- top-level `metrics.runner_local` counters and duration
- per-check `latency_ms`, `status`, `error_type`, and `non_goals`
- explicit non-goals:
  - `splink_backend=not_proven`
  - `reasoner_runtime=injected_or_not_configured`
  - `durable_backend=adapter_contract_only`

## Non-Goals

This PR does not implement or prove a real PostgreSQL adapter, Iceberg adapter,
Splink production backend, Prometheus/OTEL export, or production LLM runtime.
The strict adapter used by the probe is a runner-local fake that validates the
repository protocol boundary only.

## Verification Commands

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:../contracts/src .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_readiness.py
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:../contracts/src .venv/bin/python scripts/entity_registry_readiness_probe.py --profile production --json
```
