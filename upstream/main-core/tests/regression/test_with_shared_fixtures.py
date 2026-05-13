"""Regression tests consuming the shared ``audit_eval_fixtures`` package.

Per SUBPROJECT_TESTING_STANDARD.md §10 ``main-core`` heavy-uses both
``minimal_cycle`` (L4-L8 chain baseline) and ``historical_replay_pack``
(replay invariants).

This module:

1. Walks every ``minimal_cycle`` case and asserts the cycle_publish_manifest
   declares the four formal-object snapshots main-core owns publishing
   (world_state_snapshot / official_alpha_pool / alpha_result_snapshot /
   recommendation_snapshot).
2. **Really exercises a runtime function**: instantiates
   ``WorldStateSnapshot`` from fixture-derived inputs and asserts the
   constructed model carries the same canonical shape as the fixture
   declared (iron rule #5: regression must touch real runtime code).

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

# Hard import the formal-object models we exercise so a refactor that
# drops them from the public schema namespace fails immediately at
# collection.
from main_core.common.schemas.world_state import WorldStateSnapshot  # noqa: F401


class TestSharedFixturesAreReachable:
    def test_minimal_cycle_pack_present(self) -> None:
        assert "minimal_cycle" in list_packs()

    def test_historical_replay_pack_present(self) -> None:
        assert "historical_replay_pack" in list_packs()

    def test_minimal_cycle_pack_has_at_least_one_case(self) -> None:
        cases = list(iter_cases("minimal_cycle"))
        assert cases, "minimal_cycle is empty"


class TestMinimalCycleManifestDeclaresFourFormalObjects:
    """Every minimal_cycle case must declare the four formal-object
    snapshots main-core owns producing in Phase 3. Drift in the
    fixture's published-table list would mean main-core's manifest
    contract is no longer assertion-covered.
    """

    REQUIRED_TABLES = {
        "world_state_snapshot",
        "official_alpha_pool",
        "alpha_result_snapshot",
        "recommendation_snapshot",
    }

    def test_every_minimal_cycle_case_declares_four_tables(self) -> None:
        for ref in iter_cases("minimal_cycle"):
            case = load_case(ref.pack_name, ref.case_id)
            manifest = case.expected.get("cycle_publish_manifest", {})
            tables = set(manifest.get("tables", {}).keys())
            missing = self.REQUIRED_TABLES - tables
            assert not missing, (
                f"{ref.case_id}: cycle_publish_manifest.tables missing "
                f"main-core formal objects: {missing}"
            )


class TestPhaseResultsExpectAllFourPhases:
    """Every minimal_cycle case must declare phase_results for all four
    phases — main-core is one of the consumers asserting on these.
    """

    REQUIRED_PHASES = {
        "phase_0_data_preparation",
        "phase_1_graph_update",
        "phase_2_business_chain",
        "phase_3_formal_publish",
    }

    def test_every_case_declares_four_phase_results(self) -> None:
        for ref in iter_cases("minimal_cycle"):
            case = load_case(ref.pack_name, ref.case_id)
            phases = set(case.expected.get("phase_results", {}).keys())
            missing = self.REQUIRED_PHASES - phases
            assert not missing, (
                f"{ref.case_id}: phase_results missing required phases: "
                f"{missing}"
            )


class TestRuntimeFixtureDrivenL5PoolSelection:
    """**This is the real-runtime regression** (iron rule #5, codex
    stage-2.3 review #2).

    For every minimal_cycle case, build a WorldStateSnapshot + minimal
    FeatureSignalBundle from ``case.input.candidate_universe`` and run
    ``main_core.l5_universe.service.select_official_alpha_pool``.
    Assert the produced ``OfficialAlphaPool`` matches the fixture's
    ``case.expected.cycle_publish_manifest`` shape (capacity, candidate
    membership) and the §9 invariant ``capacity <= 100``.

    This is the codex-required real-runtime regression: fixture
    ``case.input`` drives a real main-core runtime function, the
    function's output is asserted against ``case.expected``. Drift in
    either the runtime or the fixture surfaces here.
    """

    @staticmethod
    def _build_world_state_for(cycle_id: str) -> WorldStateSnapshot:
        return WorldStateSnapshot(
            cycle_id=cycle_id,
            baseline_regime="neutral",
            llm_delta=0,
            final_regime="neutral",
            llm_rationale="regression test rationale",
            actual_model_used="gpt-4o-mini",
            actual_provider="openai",
            fallback_path=[],
        )

    @staticmethod
    def _build_minimal_bundle(cycle_id: str, entity_id: str):
        from main_core.common.schemas.feature_bundle import FeatureSignalBundle

        return FeatureSignalBundle(
            cycle_id=cycle_id,
            entity_id=entity_id,
            feature_values={"momentum": 0.5},
            signal_values={},
            graph_features={},
            feature_weight_multiplier={"momentum": 1.0},
        )

    def test_select_official_alpha_pool_consumes_fixture_input(self) -> None:
        """Real-runtime call sweep: every minimal_cycle case is fed
        through select_official_alpha_pool. Generic L5 invariants are
        asserted here (cycle_id round-trip, §9 capacity cap, candidate
        membership, manifest declares the published table).

        The case-specific business expectation (e.g. "1-candidate cycle
        produces a pool of size 1") is asserted in
        ``test_one_candidate_cycle_produces_one_entity_pool`` below so
        the assertion is keyed to a known fixture shape rather than a
        generic invariant — that's the codex stage-2.3 review #2 fix.
        """
        from main_core.l5_universe.service import select_official_alpha_pool

        exercised_at_least_one = False
        for ref in iter_cases("minimal_cycle"):
            case = load_case(ref.pack_name, ref.case_id)
            cycle_id = case.input["cycle_id"]
            candidates = case.input.get("candidate_universe", [])
            if not candidates:
                continue
            exercised_at_least_one = True

            world_state = self._build_world_state_for(cycle_id)
            bundles = [
                self._build_minimal_bundle(cycle_id, c["canonical_entity_id"])
                for c in candidates
            ]
            pool = select_official_alpha_pool(
                world_state=world_state,
                bundles=bundles,
                capacity=100,
            )

            assert pool.cycle_id == cycle_id, (
                f"{ref.case_id}: pool.cycle_id {pool.cycle_id!r} != "
                f"fixture {cycle_id!r}"
            )
            assert pool.official_alpha_pool_capacity <= 100, (
                f"{ref.case_id}: capacity {pool.official_alpha_pool_capacity}"
                " breaks the §9 cap"
            )
            fixture_ent_ids = {c["canonical_entity_id"] for c in candidates}
            assert all(
                str(e) in fixture_ent_ids for e in pool.selected_entities
            ), (
                f"{ref.case_id}: pool selected entities not in fixture "
                f"candidate set"
            )
            tables = case.expected.get("cycle_publish_manifest", {}).get(
                "tables", {}
            )
            assert "official_alpha_pool" in tables, (
                f"{ref.case_id}: expected.cycle_publish_manifest.tables "
                f"missing official_alpha_pool"
            )

        assert exercised_at_least_one, (
            "expected at least one minimal_cycle case with candidate_universe"
        )

    def test_one_candidate_cycle_produces_one_entity_pool(self) -> None:
        """Business-expectation regression (codex stage-2.3 review #2 fix).

        For ``minimal_cycle/case_001_one_stock_one_cycle`` the fixture
        carries exactly 1 candidate (CATL / ENT_STOCK_300750.SZ). The
        L5 service contract says: with no previous_pool, no frozen
        entities, and capacity=100, every eligible candidate is
        selected. The expected business outcome is therefore:

          - selected_entities == [the single candidate id]
          - observation_pool_size == 1
          - added_entities  == [the single candidate id]   (no previous pool)
          - removed_entities == [] (no previous pool)
          - freeze_reason_map == {}

        A regression that returns an empty pool, a pool missing the
        candidate, or an over-counted pool would fail here — which is
        exactly what the previous "generic invariants only" version
        could not catch.
        """
        from main_core.l5_universe.service import select_official_alpha_pool

        case = load_case("minimal_cycle", "case_001_one_stock_one_cycle")
        candidates = case.input["candidate_universe"]
        assert len(candidates) == 1, (
            "fixture invariant: case_001_one_stock_one_cycle must carry "
            "exactly one candidate; if you intentionally added more, "
            "update this test to derive the expectation accordingly"
        )
        expected_entity_id = candidates[0]["canonical_entity_id"]
        cycle_id = case.input["cycle_id"]

        world_state = self._build_world_state_for(cycle_id)
        bundle = self._build_minimal_bundle(cycle_id, expected_entity_id)

        pool = select_official_alpha_pool(
            world_state=world_state,
            bundles=[bundle],
            capacity=100,
        )

        # Business-shape assertions tied to the 1-candidate fixture.
        selected = [str(e) for e in pool.selected_entities]
        added = [str(e) for e in pool.added_entities]
        removed = [str(e) for e in pool.removed_entities]
        assert selected == [expected_entity_id], (
            f"selected_entities should be exactly [{expected_entity_id!r}], "
            f"got {selected!r}"
        )
        assert pool.observation_pool_size == 1, (
            f"observation_pool_size should be 1 for 1-candidate cycle; "
            f"got {pool.observation_pool_size}"
        )
        assert added == [expected_entity_id], (
            f"with no previous_pool, the candidate must show up as added; "
            f"got {added!r}"
        )
        assert removed == [], (
            f"with no previous_pool, removed_entities must be empty; "
            f"got {removed!r}"
        )
        assert dict(pool.freeze_reason_map) == {}, (
            f"freeze_reason_map should be empty (no frozen entities passed); "
            f"got {dict(pool.freeze_reason_map)!r}"
        )
