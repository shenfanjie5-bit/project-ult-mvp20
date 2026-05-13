# M4.8 Focused Resolution Proof Evidence

Date: 2026-05-07

## Scope

M4.8 adds a focused proof harness around the existing entity-registry resolution
chain. The harness uses in-memory repositories, `resolve_mention_with_repositories`,
runtime `ResolutionCase` records, `get_resolution_audit_payload`, and contracts
projection helpers.

Covered proof cases:

- deterministic exact alias hit
- deterministic code alias hit
- deterministic rule hit from suffixed stock code
- ambiguous injected fuzzy candidates that remain unresolved and require review
- no-candidate unresolved path that fails closed

## Non-goals

- No contracts package changes.
- No holdings subtype.
- No new core resolver capability.
- No claim that the placeholder fuzzy adapter is production-ready.

## Verification

Primary commands:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:../contracts/src python -m pytest -q -p no:cacheprovider \
  tests/test_resolution_deterministic.py \
  tests/test_resolution_fuzzy.py \
  tests/test_resolution_resolve_mention.py \
  tests/test_resolution_llm.py \
  tests/test_references.py \
  tests/test_contracts_alignment.py \
  tests/boundary \
  tests/proof/test_m4_8_focused_resolution_proof.py
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:../contracts/src python scripts/m4_8_focused_resolution_proof.py
python -m py_compile scripts/m4_8_focused_resolution_proof.py
git diff --check origin/main...HEAD
git diff --check
```
