"""Unit tests for the audit_eval_fixtures importable package.

These guard:
- All 4 public APIs (``fixture_root``, ``iter_cases``, ``load_case``,
  ``fixture_version``) are exposed and behave deterministically
- Each bundled case has the 5 required files
- Metadata follows the §6 contract (required keys present)
- Invalid lookups raise ``FixtureError`` (not generic ``KeyError``)

Acts as the contract guard for downstream consumers — if these break, every
project consuming ``audit_eval_fixtures`` will silently regress.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from audit_eval_fixtures import (
    Case,
    CaseRef,
    FixtureError,
    fixture_root,
    fixture_version,
    iter_cases,
    list_packs,
    load_case,
)

REQUIRED_PACKS = {"minimal_cycle", "event_cases", "historical_replay_pack"}
REQUIRED_METADATA_KEYS = {
    "fixture_id",
    "source_module",
    "contract_version",
    "fixture_kind",
    "golden_updated_at",
}


class TestPackageAPI:
    def test_all_four_public_apis_importable(self) -> None:
        # Smoke-checks that the package's __all__ exposure is intact.
        from audit_eval_fixtures import (
            fixture_root,
            fixture_version,
            iter_cases,
            load_case,
        )

        assert callable(fixture_root)
        assert callable(iter_cases)
        assert callable(load_case)
        assert callable(fixture_version)

    def test_fixture_version_matches_audit_eval_version(self) -> None:
        from audit_eval import __version__

        assert fixture_version() == __version__


class TestPackDiscovery:
    def test_three_required_packs_present(self) -> None:
        assert REQUIRED_PACKS.issubset(set(list_packs()))

    @pytest.mark.parametrize("pack", sorted(REQUIRED_PACKS))
    def test_each_pack_has_at_least_one_case(self, pack: str) -> None:
        cases = list(iter_cases(pack))
        assert cases, f"pack {pack!r} has no cases"

    def test_unknown_pack_raises_fixture_error(self) -> None:
        with pytest.raises(FixtureError):
            fixture_root("__definitely_not_a_real_pack__")

    def test_iter_cases_returns_caseref(self) -> None:
        for pack in sorted(REQUIRED_PACKS):
            for ref in iter_cases(pack):
                assert isinstance(ref, CaseRef)
                assert ref.pack_name == pack
                assert ref.case_id  # non-empty
                assert ref.case_dir.is_dir()


class TestCaseLoading:
    @pytest.mark.parametrize("pack", sorted(REQUIRED_PACKS))
    def test_every_case_loads_with_5_files(self, pack: str) -> None:
        for ref in iter_cases(pack):
            case = load_case(ref.pack_name, ref.case_id)
            assert isinstance(case, Case)
            assert isinstance(case.input, dict)
            assert isinstance(case.context, dict)
            assert isinstance(case.expected, dict)
            assert isinstance(case.manifest_refs, dict)
            assert isinstance(case.metadata, dict)

    @pytest.mark.parametrize("pack", sorted(REQUIRED_PACKS))
    def test_every_case_metadata_has_required_keys(self, pack: str) -> None:
        for ref in iter_cases(pack):
            case = load_case(ref.pack_name, ref.case_id)
            missing = REQUIRED_METADATA_KEYS - set(case.metadata.keys())
            assert not missing, (
                f"case {pack}/{ref.case_id} missing metadata keys: {missing}"
            )

    @pytest.mark.parametrize("pack", sorted(REQUIRED_PACKS))
    def test_metadata_contract_version_starts_with_v(self, pack: str) -> None:
        for ref in iter_cases(pack):
            case = load_case(ref.pack_name, ref.case_id)
            cv = case.metadata["contract_version"]
            assert cv.startswith("v"), f"{pack}/{ref.case_id}: {cv!r}"

    def test_unknown_case_raises_fixture_error(self) -> None:
        with pytest.raises(FixtureError):
            load_case("minimal_cycle", "__not_a_real_case__")

    def test_iter_cases_is_deterministic(self) -> None:
        # Two iterations must yield the same case_id sequence.
        for pack in sorted(REQUIRED_PACKS):
            ids_1 = [r.case_id for r in iter_cases(pack)]
            ids_2 = [r.case_id for r in iter_cases(pack)]
            assert ids_1 == ids_2
            assert ids_1 == sorted(ids_1)  # sorted lexicographically


class TestCaseFilesAreValidJSON:
    """The five required files must all be JSON-parseable.

    This catches a hand-edited fixture from drifting into invalid JSON before
    the consumer-side regression test even runs.
    """

    @pytest.mark.parametrize("pack", sorted(REQUIRED_PACKS))
    def test_all_files_parse_as_json(self, pack: str) -> None:
        for ref in iter_cases(pack):
            for path in (
                ref.input_path,
                ref.context_path,
                ref.expected_path,
                ref.manifest_refs_path,
                ref.metadata_path,
            ):
                # raises if invalid JSON
                json.loads(Path(path).read_text(encoding="utf-8"))


class TestNoForbiddenWritesInFixtures:
    """No fixture must contain ``feature_weight_multiplier``.

    Mirrors audit-eval's package-level boundary guard. Drift here would
    poison every downstream regression that rolls fixture data into a
    payload subjected to ``assert_no_forbidden_write``.
    """

    @pytest.mark.parametrize("pack", sorted(REQUIRED_PACKS))
    def test_no_forbidden_field_anywhere(self, pack: str) -> None:
        from audit_eval._boundary import assert_no_forbidden_write

        for ref in iter_cases(pack):
            case = load_case(ref.pack_name, ref.case_id)
            for blob_name, blob in (
                ("input", case.input),
                ("context", case.context),
                ("expected", case.expected),
                ("manifest_refs", case.manifest_refs),
                ("metadata", case.metadata),
            ):
                # raises BoundaryViolationError on any forbidden field
                assert_no_forbidden_write(blob)
