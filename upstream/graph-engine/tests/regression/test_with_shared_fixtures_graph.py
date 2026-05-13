"""Stage 2.10 regression tier — fixture-backed regression via
audit_eval_fixtures (sibling of subsystem-announcement Stage 2.8
follow-up #3 + subsystem-news Stage 2.9 regressions).

CLAUDE.md (graph-engine):
- §10 #1 Truth Before Mirror: Iceberg is canonical; Neo4j is hot
  mirror only.
- §10 #5 No Raw Text: graph-engine accepts only contracted
  ``CandidateGraphDelta``.
- §10 #7 Status Guard: live graph reads check ``graph_status='ready'``.

Iron rule #1: hard-import ``audit_eval_fixtures`` (no module-level
skip). Iron rule #5 + main-core sub-rule: real runtime + fixture-
derived business expectation.

Codex review #1 P2 fix (stage 2.10 follow-up #1): the previous
version of this regression only called
``CandidateGraphDelta.model_validate(...)``, which is the contracts
schema graph-engine RE-EXPORTS — calling it doesn't exercise any
graph-engine code at all. A bug in graph-engine's ``promote_graph_deltas``
or ``freeze_contract_deltas`` would have stayed green.

This rewrite drives the **real graph-engine consumer service**:
``promote_graph_deltas(..., sync_to_live_graph=False)`` against
fixture-derived ``CandidateGraphDelta`` input, with stub reader /
entity reader / canonical writer that capture call ordering. The
fixture's ``case_ex3_negative`` is upstream-rejected by announcement /
news producer guards (so its weak-evidence form never reaches
graph-engine in production); we use the case's STRENGTHENED variant
(canonical resolved entities + multiple evidence refs — what the
producer guards would emit if the scenario had been well-evidenced)
to drive the consumer side.

Fixture: ``audit_eval_fixtures.event_cases.case_ex3_negative``
(audit-eval v0.2.2 release). Same case used by announcement Stage
2.8 follow-up #3 + news Stage 2.9 regression.
"""

from __future__ import annotations

# Iron rule #1: hard import. Missing audit_eval_fixtures must fail
# collection — NOT module-level skip.
from audit_eval_fixtures import load_case  # noqa: F401  (load_case below proves use)

import pytest


class TestCaseEx3NegativeFixtureMetadataDeclaresGraphConsumerScenario:
    """Cross-check fixture metadata: the case is the canonical "Ex-3
    high-threshold negative" baseline used across announcement / news
    / graph-engine. If a future audit-eval bump changes the
    ``fixture_kind`` or business expectation, this regression should
    be revisited.
    """

    def test_case_ex3_negative_metadata_describes_high_threshold_kind(
        self,
    ) -> None:
        case = load_case("event_cases", "case_ex3_negative")
        metadata = case.metadata
        assert metadata.get("fixture_kind") == "ex3_high_threshold_negative", (
            f"fixture kind drift: expected "
            f"'ex3_high_threshold_negative', got "
            f"{metadata.get('fixture_kind')!r}"
        )

    def test_case_ex3_negative_business_expectation_zero_ex3(self) -> None:
        case = load_case("event_cases", "case_ex3_negative")
        expected = case.expected
        assert expected["ex3_candidates_emitted"] == 0
        assert expected["ex3_high_threshold_guard_triggered"] is True


class TestPromoteGraphDeltasConsumerSideViaRealRuntime:
    """Real runtime touch (iron rule #5 + main-core sub-rule):
    ``promote_graph_deltas(..., sync_to_live_graph=False)`` is invoked
    against fixture-derived ``CandidateGraphDelta`` input. The
    promotion plan output is asserted against fixture-anchored
    business expectations (cycle id, frozen delta count, source/target
    nodes preserved). Stub reader / entity reader / canonical writer
    capture the call ordering invariant (Layer A canonical write
    happens — CLAUDE.md §10 #1 truth-before-mirror).
    """

    def test_promote_graph_deltas_consumes_fixture_derived_candidate(
        self,
    ) -> None:
        from contracts.schemas import CandidateGraphDelta

        from graph_engine import promote_graph_deltas

        case = load_case("event_cases", "case_ex3_negative")
        attempt = case.input["candidate_graph_delta_attempt"]

        # Build a STRENGTHENED CandidateGraphDelta from the fixture's
        # attempt shape: same source_node + relation_type, but
        # promote target_node from "unresolved counterparty" to a
        # canonical entity id, and use multiple evidence refs (the
        # fixture's "single weak evidence" guard reason is upstream-
        # producer's responsibility; once the producer guard would
        # accept, this is what graph-engine sees).
        strengthened_delta = CandidateGraphDelta(
            subsystem_id="subsystem-news",
            delta_id=f"graph-engine-regression-{attempt['delta_id']}",
            # graph-engine internal mapper accepts only
            # ``upsert_edge`` / ``upsert_relation``; the canonical Ex-3
            # wire shape (announcement/news produce this).
            delta_type="upsert_edge",
            source_node=str(attempt["source_node"]),
            target_node="ENT_RESOLVED_DOWNSTREAM_FROM_FIXTURE",
            # Must be a graph-engine RelationshipType enum value (see
            # ``schema/definitions.py``).
            relation_type="SUPPLY_CHAIN",
            properties=dict(attempt.get("properties", {})),
            evidence=[
                "evidence-strong-fixture-ref-001",
                "evidence-strong-fixture-ref-002",
            ],
        )

        cycle_id = "regression-cycle-from-fixture-001"
        selection_ref = f"regression-selection-{strengthened_delta.delta_id}"

        # Stub reader / entity reader / canonical writer with call
        # logging so we can assert the Layer-A-first ordering.
        call_log: list[str] = []

        class _FixtureReader:
            def read_candidate_graph_deltas(
                self, cid: str, sref: str
            ) -> list[CandidateGraphDelta]:
                call_log.append("reader.read")
                assert cid == cycle_id
                assert sref == selection_ref
                return [strengthened_delta]

        class _FixtureEntityReader:
            def canonical_entity_ids_for_node_ids(
                self, node_ids: set[str]
            ) -> dict[str, str]:
                call_log.append("entity_reader.canonical_ids")
                # Resolve every node id to itself (fixture's source +
                # the strengthened target both already canonical).
                return {nid: nid for nid in node_ids}

            def existing_entity_ids(
                self, entity_ids: set[str]
            ) -> set[str]:
                call_log.append("entity_reader.existing")
                # Fixture-derived entities are all canonical (the
                # strengthened scenario assumes entity-registry
                # resolved them upstream).
                return set(entity_ids)

        class _RecordingCanonicalWriter:
            def __init__(self) -> None:
                self.written_plans: list = []

            def write_canonical_records(self, plan) -> None:
                call_log.append("canonical_writer.write")
                self.written_plans.append(plan)

        canonical_writer = _RecordingCanonicalWriter()

        plan = promote_graph_deltas(
            cycle_id=cycle_id,
            selection_ref=selection_ref,
            candidate_reader=_FixtureReader(),
            entity_reader=_FixtureEntityReader(),
            canonical_writer=canonical_writer,
            sync_to_live_graph=False,  # no Neo4j needed for regression
        )

        # Iron rule #5: real runtime returned a real PromotionPlan
        # (not just a Pydantic re-validation echo).
        assert plan is not None, (
            "promote_graph_deltas must return a PromotionPlan"
        )

        # CLAUDE.md §10 #1 (truth-before-mirror): canonical writer was
        # invoked exactly once (Layer A write is the source of truth).
        assert call_log.count("canonical_writer.write") == 1, (
            f"Layer A canonical write must run exactly once per "
            f"promotion; call log: {call_log}"
        )
        assert canonical_writer.written_plans == [plan], (
            "canonical_writer received exactly the PromotionPlan that "
            "promote_graph_deltas returned"
        )

        # Fixture-derived business expectation (main-core sub-rule):
        # the promotion plan's cycle / selection / delta_ids carry the
        # fixture-anchored identity all the way through the consumer
        # chain. PromotionPlan shape (see ``models.py``):
        #   {cycle_id, selection_ref, delta_ids, node_records,
        #    edge_records, assertion_records, created_at}
        assert plan.cycle_id == cycle_id
        assert plan.selection_ref == selection_ref
        assert strengthened_delta.delta_id in plan.delta_ids, (
            f"fixture-derived delta_id "
            f"{strengthened_delta.delta_id!r} missing from "
            f"PromotionPlan.delta_ids={plan.delta_ids}"
        )

        # CLAUDE.md §10 #6 (No Raw Text): graph-engine emitted real
        # GraphEdgeRecord(s) (Layer A canonical edge), proving the
        # consumer pipeline freeze + plan-build went all the way through.
        assert plan.edge_records, (
            "promotion plan must contain at least one GraphEdgeRecord "
            "for an upsert_edge candidate; got empty edge_records"
        )
        edge_sources = {edge.source_node_id for edge in plan.edge_records}
        edge_targets = {edge.target_node_id for edge in plan.edge_records}
        # Both source AND target carry forward — fixture's source +
        # the strengthened target are both in the canonical Layer A
        # edge record (no silent rename / drop).
        assert str(attempt["source_node"]) in edge_sources, (
            f"fixture-derived source_node "
            f"{str(attempt['source_node'])!r} missing from "
            f"PromotionPlan.edge_records sources={edge_sources}"
        )
        assert "ENT_RESOLVED_DOWNSTREAM_FROM_FIXTURE" in edge_targets, (
            f"strengthened target_node missing from "
            f"PromotionPlan.edge_records targets={edge_targets}"
        )
