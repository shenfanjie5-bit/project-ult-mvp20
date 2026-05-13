"""Regression tests consuming the shared ``audit_eval_fixtures`` package.

Per SUBPROJECT_TESTING_STANDARD.md §10 ``contracts`` heavy-uses
``event_cases`` as the schema-drift baseline. This module:

1. Walks every ``event_cases`` case and asserts metadata is contract-shaped
   (drift in metadata format → fail here, not in 11 downstream regression
   suites).
2. Confirms the audit_eval_fixtures package is actually installed and the
   import path is correct — without this, every other module's "wire
   shared fixtures" issue would silently no-op.

**Hard-import on purpose** (codex review #1, lesson recorded in plan stage 2.1
followups): per SUBPROJECT_TESTING_STANDARD.md §2.2 + §13.6 the regression
tier must not depend on the network at runtime AND must really consume the
fixture corpus. Module-level skip on missing ``audit_eval_fixtures`` would
let CI report green without ever exercising the corpus. Instead we let
ImportError bubble so `make regression` / the regression CI lane fail loud.

Install path: ``pip install -e ".[dev,shared-fixtures]"`` or
``make install-shared``. The default ``dev`` extra deliberately omits
audit-eval to keep the test-fast / smoke lanes offline-first.
"""

from __future__ import annotations

# Hard import — fail collection if shared-fixtures extra is not installed.
# See module docstring for rationale (codex review finding #1).
from audit_eval_fixtures import (  # noqa: F401
    Case,
    CaseRef,
    iter_cases,
    list_packs,
    load_case,
)


class TestSharedFixturesAreReachable:
    def test_three_required_packs_present(self) -> None:
        packs = set(list_packs())
        assert {
            "minimal_cycle",
            "event_cases",
            "historical_replay_pack",
        }.issubset(packs)

    def test_event_cases_pack_has_at_least_one_case(self) -> None:
        cases = list(iter_cases("event_cases"))
        assert cases, "event_cases pack is empty"


class TestEventCasesMetadataIsContractCompatible:
    """Every event_cases case's metadata must be parseable as a structured
    payload — guards against ``audit_eval_fixtures`` silently shipping a
    case whose metadata schema drifted.
    """

    REQUIRED_METADATA_KEYS = {
        "fixture_id",
        "source_module",
        "contract_version",
        "fixture_kind",
        "golden_updated_at",
    }

    def test_every_event_case_metadata_has_required_keys(self) -> None:
        for ref in iter_cases("event_cases"):
            case = load_case(ref.pack_name, ref.case_id)
            missing = self.REQUIRED_METADATA_KEYS - set(case.metadata.keys())
            assert not missing, (
                f"{ref.pack_name}/{ref.case_id} missing metadata keys: {missing}"
            )

    def test_every_event_case_contract_version_starts_with_v(self) -> None:
        for ref in iter_cases("event_cases"):
            case = load_case(ref.pack_name, ref.case_id)
            cv = case.metadata["contract_version"]
            assert cv.startswith("v"), f"{ref.case_id}: {cv!r}"


class TestEventCaseInputIsContractCompatible:
    """Spot-check that the ``case_fuzzy_alias_simple`` case's expected
    payload uses ``ENT_*`` canonical_entity_id format — that's the ID
    rule contracts owns (per project-ult v5.0.1 §6 + entity-registry
    CLAUDE.md). Drift here means contracts and audit_eval_fixtures fell
    out of sync.
    """

    def test_fuzzy_alias_resolves_to_ent_prefixed_id(self) -> None:
        case = load_case("event_cases", "case_fuzzy_alias_simple")

        resolved = case.expected.get("resolved_entity_id")
        assert isinstance(resolved, str), case.expected
        assert resolved.startswith("ENT_"), (
            f"resolved_entity_id must use ENT_* canonical id rule; got {resolved!r}"
        )
