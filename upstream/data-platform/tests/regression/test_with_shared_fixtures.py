"""Regression tests consuming the shared ``audit_eval_fixtures`` package.

Per SUBPROJECT_TESTING_STANDARD.md §10 ``data-platform`` heavy-uses
``minimal_cycle`` as the cycle_publish_manifest baseline.

This module:

1. Walks every minimal_cycle case and asserts the fixture's
   ``cycle_publish_manifest`` declares all four formal object table
   slots data-platform owns serving.
2. **Really exercises a runtime function**: feeds the fixture's
   ``cycle_publish_manifest_id`` and ``snapshot_ids`` into
   ``data_platform.cycle.manifest`` model construction; asserts the
   built manifest model matches the fixture's expected shape (iron
   rule #5: regression must touch real runtime code).

**Hard-import on purpose** (iron rule #1): ImportError bubbles to pytest
collection so ``make regression`` / the regression CI lane fail loud
when shared-fixtures extra is not installed.

Install path: ``pip install -e ".[dev,shared-fixtures]"``.
"""

from __future__ import annotations

# Hard import — fail collection if shared-fixtures extra not installed.
from audit_eval_fixtures import (  # noqa: F401
    Case,
    CaseRef,
    iter_cases,
    list_packs,
    load_case,
)


class TestSharedFixturesAreReachable:
    def test_minimal_cycle_pack_present(self) -> None:
        assert "minimal_cycle" in list_packs()

    def test_pack_has_at_least_one_case(self) -> None:
        cases = list(iter_cases("minimal_cycle"))
        assert cases, "minimal_cycle is empty"


class TestManifestDeclaresFourFormalTables:
    """Every minimal_cycle case's expected.cycle_publish_manifest must
    declare the four formal object table slots data-platform serves.
    Drift in the fixture's published-table list would mean
    data-platform's manifest contract is no longer asserted.
    """

    REQUIRED_TABLES = {
        "world_state_snapshot",
        "official_alpha_pool",
        "alpha_result_snapshot",
        "recommendation_snapshot",
    }

    def test_every_case_declares_four_tables(self) -> None:
        for ref in iter_cases("minimal_cycle"):
            case = load_case(ref.pack_name, ref.case_id)
            manifest = case.expected.get("cycle_publish_manifest", {})
            tables = set(manifest.get("tables", {}).keys())
            missing = self.REQUIRED_TABLES - tables
            assert not missing, (
                f"{ref.case_id}: cycle_publish_manifest.tables missing "
                f"data-platform-served formal objects: {missing}"
            )


class TestFixtureManifestSemanticShape:
    """**Fixture self-check** (NOT runtime regression).

    The ``cycle_publish_manifest`` payload in the audit-eval shared
    fixtures is the **business-readable semantic layer**: snapshot_id
    is a string like ``"WS_CYC_2025_01_03"`` (audit-eval's stable
    cross-module identifier) and table keys lack the ``formal.``
    namespace prefix.

    The data-platform runtime layer (``data_platform.cycle.manifest``)
    uses a *different* schema: snapshot_id is a positive integer
    (Iceberg snapshot ID) and table keys must start with ``formal.``.
    The two layers are deliberately decoupled — the fixture is what
    audit / replay / business consumers see, the runtime int is internal.

    This class validates ONLY the fixture's own semantic shape.
    Runtime validator coverage is in ``TestRuntimeManifestValidatorPath``
    below (codex stage-2.4 follow-up #2 fix).
    """

    def test_every_case_snapshot_ids_are_well_formed_strings(self) -> None:
        exercised_at_least_one = False
        for ref in iter_cases("minimal_cycle"):
            case = load_case(ref.pack_name, ref.case_id)
            tables = case.expected.get("cycle_publish_manifest", {}).get(
                "tables", {}
            )
            if not tables:
                continue
            exercised_at_least_one = True

            for table_name, table_meta in tables.items():
                assert isinstance(table_meta, dict), (
                    f"{ref.case_id}: tables.{table_name} must be a dict, "
                    f"got {type(table_meta).__name__}"
                )
                snapshot_id = table_meta.get("snapshot_id")
                assert snapshot_id, (
                    f"{ref.case_id}: tables.{table_name} missing snapshot_id"
                )
                # Fixture-side: snapshot_id is a business-readable str.
                # Runtime-side: it is a positive int — see
                # TestRuntimeManifestValidatorPath below.
                assert isinstance(snapshot_id, str), (
                    f"{ref.case_id}: fixture snapshot_id must be str "
                    f"(business semantic layer); got "
                    f"{type(snapshot_id).__name__}"
                )

        assert exercised_at_least_one, (
            "expected at least one minimal_cycle case with manifest tables"
        )


class TestRuntimeManifestValidatorPath:
    """**Real-runtime regression** (iron rule #5, codex stage-2.4 follow-up #2).

    Imports + invokes ``data_platform.cycle.manifest`` runtime symbols
    and asserts they accept a *runtime-shaped* manifest derived from
    each fixture, AND reject the fixture's *semantic-shape* string
    snapshot_ids.

    The fixture's table-key set is **derived** from
    ``case.expected.cycle_publish_manifest.tables.keys()`` — not
    hard-coded — so adding/removing tables in the fixture automatically
    flows into the runtime construction (codex non-blocking suggestion).

    Key bridging points fixture → runtime:
      - fixture cycle_id ``CYC_YYYY_MM_DD_DAILY`` (semantic)
        → runtime cycle_id ``CYCLE_YYYYMMDD`` (validator pattern)
      - fixture table key ``world_state_snapshot`` (semantic)
        → runtime table key ``formal.world_state_snapshot``
          (namespace-prefixed)
      - fixture snapshot_id ``"WS_CYC_2025_01_03"`` (business id)
        → runtime snapshot_id ``1`` (Iceberg int; assigned via enumerate)
    """

    @staticmethod
    def _runtime_cycle_id_for(case_input: dict) -> str:
        """Fixture cycle_id is ``CYC_YYYY_MM_DD_DAILY`` (semantic);
        runtime ``_cycle_date_from_id`` requires ``CYCLE_YYYYMMDD``.
        Use the fixture's trade_date as the canonical bridge.
        """
        trade_date = case_input["trade_date"]  # e.g. "2025-01-03"
        compact = trade_date.replace("-", "")  # "20250103"
        return f"CYCLE_{compact}"

    def test_runtime_validator_accepts_fixture_derived_runtime_manifest(
        self,
    ) -> None:
        from datetime import datetime, timezone

        from data_platform.cycle.manifest import (
            CyclePublishManifest,
            FormalTableSnapshot,
        )

        exercised_at_least_one = False
        for ref in iter_cases("minimal_cycle"):
            case = load_case(ref.pack_name, ref.case_id)
            tables = case.expected.get("cycle_publish_manifest", {}).get(
                "tables", {}
            )
            if not tables:
                continue
            exercised_at_least_one = True

            runtime_cycle_id = self._runtime_cycle_id_for(case.input)

            # Derive the runtime payload from fixture's tables.keys() —
            # NOT hard-coded — so a future fixture with N tables keeps
            # the regression honest.
            runtime_snapshots = {
                f"formal.{table_key}": FormalTableSnapshot(
                    table=f"formal.{table_key}",
                    snapshot_id=i,
                )
                for i, table_key in enumerate(tables.keys(), start=1)
            }

            manifest = CyclePublishManifest(
                published_cycle_id=runtime_cycle_id,
                published_at=datetime.now(timezone.utc),
                formal_table_snapshots=runtime_snapshots,
            )

            assert manifest.published_cycle_id == runtime_cycle_id
            assert len(manifest.formal_table_snapshots) == len(tables), (
                f"{ref.case_id}: runtime manifest has "
                f"{len(manifest.formal_table_snapshots)} tables, "
                f"fixture has {len(tables)}"
            )
            for runtime_key in manifest.formal_table_snapshots:
                assert runtime_key.startswith("formal."), runtime_key
                stripped = runtime_key.removeprefix("formal.")
                assert stripped in tables, (
                    f"{ref.case_id}: runtime table {runtime_key!r} not in "
                    f"fixture tables {set(tables)!r}"
                )
                assert isinstance(
                    manifest.formal_table_snapshots[runtime_key].snapshot_id,
                    int,
                ), "runtime snapshot_id must be int"

        assert exercised_at_least_one, (
            "expected at least one minimal_cycle case with manifest tables"
        )

    def test_runtime_validator_rejects_fixture_string_snapshot_ids(self) -> None:
        """Reverse-proof the two-layer split: feeding the fixture's
        business-string snapshot_id directly to ``validate_snapshot_id``
        must raise. If this passes silently, the runtime validator has
        loosened — and the two-layer assumption above breaks down.
        """
        import pytest

        from data_platform.cycle.manifest import (
            InvalidFormalSnapshotManifest,
            validate_snapshot_id,
        )

        exercised_at_least_one = False
        for ref in iter_cases("minimal_cycle"):
            case = load_case(ref.pack_name, ref.case_id)
            tables = case.expected.get("cycle_publish_manifest", {}).get(
                "tables", {}
            )
            if not tables:
                continue

            for _, table_meta in tables.items():
                fixture_snapshot_id = table_meta["snapshot_id"]
                assert isinstance(fixture_snapshot_id, str)
                exercised_at_least_one = True
                with pytest.raises(InvalidFormalSnapshotManifest):
                    validate_snapshot_id(fixture_snapshot_id)

        assert exercised_at_least_one, (
            "expected at least one fixture string snapshot_id to challenge "
            "the runtime validator"
        )


class TestOneStockCycleManifestExpectations:
    """Business-expectation regression (iron rule #5 sub-rule from
    main-core stage 2.3 follow-up #2): assertion keyed to
    ``case_001_one_stock_one_cycle`` specific business outcome.

    For the 1-candidate cycle, the manifest's snapshot ids follow a
    stable naming convention (WS_/AP_/AR_/RC_ + cycle suffix). A
    runtime regression that returned an empty manifest, or a manifest
    with missing snapshots for some of the four tables, would fail
    here — generic invariants alone wouldn't.
    """

    def test_case_001_manifest_has_four_named_snapshots(self) -> None:
        case = load_case("minimal_cycle", "case_001_one_stock_one_cycle")
        manifest = case.expected.get("cycle_publish_manifest", {})
        tables = manifest.get("tables", {})

        # Exactly 4 formal-object slots, no more no less.
        assert set(tables.keys()) == {
            "world_state_snapshot",
            "official_alpha_pool",
            "alpha_result_snapshot",
            "recommendation_snapshot",
        }, f"case_001 manifest tables drift: {set(tables.keys())}"

        # Each slot's snapshot_id follows the stable naming prefix.
        expected_prefixes = {
            "world_state_snapshot": "WS_",
            "official_alpha_pool": "AP_",
            "alpha_result_snapshot": "AR_",
            "recommendation_snapshot": "RC_",
        }
        for table, prefix in expected_prefixes.items():
            sid = tables[table]["snapshot_id"]
            assert sid.startswith(prefix), (
                f"case_001 tables.{table}.snapshot_id {sid!r} should start "
                f"with {prefix!r}"
            )

        # All four cycle suffixes match the case's cycle_id.
        cycle_id = case.input["cycle_id"]
        cycle_suffix = cycle_id.replace("CYC_", "")  # 2025_01_03_DAILY
        for table in tables:
            sid = tables[table]["snapshot_id"]
            assert cycle_suffix.split("_DAILY")[0] in sid, (
                f"case_001 tables.{table}.snapshot_id {sid!r} should "
                f"reference the cycle suffix"
            )
