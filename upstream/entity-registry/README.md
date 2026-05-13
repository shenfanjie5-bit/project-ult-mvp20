# entity-registry

Canonical entity ID and alias resolution for project-ult. The package now has
runtime implementation for ENT_* canonical entities, alias storage, deterministic
mention resolution, fuzzy candidate injection, LLM-assisted disambiguation
boundaries, reference audit records, resolution cases, batch workflows, and
manual-review audit payloads.

Source of truth:

- `docs/entity-registry.project-doc.md`
- shared schemas from `contracts`

Current workspace state:

- `src/entity_registry/` contains the implementation.
- `tests/` covers deterministic resolution, fuzzy candidate behavior, LLM
  boundaries, references, contracts alignment, and red-line boundary checks.
- `scripts/m4_8_focused_resolution_proof.py` is a focused proof harness for the
  existing resolution chain.

## M4.8 Focused Resolution Proof

The M4.8 proof harness verifies the existing `resolve_mention_with_repositories`
path with in-memory repositories. It covers deterministic exact/code/rule hits,
ambiguous injected fuzzy candidates that are not auto-selected, unresolved
fail-closed behavior, runtime `ResolutionCase` records, review audit payloads,
and contracts projection.

Run it with:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:../contracts/src python scripts/m4_8_focused_resolution_proof.py
```

This is focused evidence, not productionization of the fuzzy backend. The proof
injects a fake fuzzy matcher and does not add core resolver capability.

Execution rule:

1. read the project doc first
2. keep work inside this module unless the issue explicitly targets shared contracts
3. do not change shared contracts from this repository
