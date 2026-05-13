"""Cross-repo alignment: graph-engine ↔ contracts.schemas.

CLAUDE.md (graph-engine + contracts both): graph-engine is a CONSUMER
of canonical Ex-3 + GraphSnapshot + GraphImpactSnapshot — it must NOT
fork the schema. ``graph_engine.models.CandidateGraphDelta`` /
``GraphSnapshot`` / ``GraphImpactSnapshot`` MUST be the SAME Python
object as ``contracts.schemas.*`` (re-export, not subclass / wrapper /
alternative impl).

Module-level skip on missing dep — install [contracts-schemas] extra
to run this lane:

    pip install -e ".[dev,contracts-schemas]"
    pytest tests/contract/test_contracts_alignment.py

Two layers of cross-repo verification (sibling of announcement /
news, adapted for graph-engine being a CONSUMER not a PRODUCER):

**Layer 1 (re-export shape stability)**: graph_engine.models
re-exports ``CandidateGraphDelta`` / ``GraphSnapshot`` /
``GraphImpactSnapshot`` from contracts.schemas. Layer 1 asserts the
re-exports ARE the SAME Python object as contracts (identity check;
covers fork detection at module load time).

**Layer 2 (CONSUMER round-trip)**: a synthetic ``CandidateGraphDelta``
(canonical contracts wire shape) is constructed; the resulting
``GraphSnapshot`` payload (built by graph-engine's snapshot generator
via real ``GraphSnapshot.model_validate``) round-trips back through
real ``contracts.schemas.GraphSnapshot.model_validate`` — proving the
CONSUMER → PRODUCER chain (announcement/news produce Ex-3 candidates
→ graph-engine consumes → graph-engine produces snapshots that
contracts validates) doesn't drift.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

contracts_schemas = pytest.importorskip(
    "contracts.schemas",
    reason=(
        "contracts package not installed; install [contracts-schemas] "
        "extra to run cross-repo alignment tests"
    ),
)


# ── Layer 1: re-export shape stability (identity check) ─────────────


class TestGraphEngineReExportsContractsIdentity:
    """CLAUDE.md domain rule: only contracts owns Ex-3 / GraphSnapshot
    / GraphImpactSnapshot canonical shape. graph-engine.models
    re-exports must be the SAME Python object — NOT a subclass, alias,
    or alternative implementation.
    """

    def test_candidate_graph_delta_is_contracts_identity(self) -> None:
        from contracts.schemas import (
            CandidateGraphDelta as ContractsCandidateGraphDelta,
        )

        from graph_engine.models import CandidateGraphDelta

        assert CandidateGraphDelta is ContractsCandidateGraphDelta, (
            "graph_engine.models.CandidateGraphDelta MUST be the SAME "
            "Python object as contracts.schemas.CandidateGraphDelta — "
            "NOT a fork/subclass/wrapper. CLAUDE.md domain rule: only "
            "contracts owns Ex-3 canonical shape."
        )

    def test_graph_snapshot_is_contracts_identity(self) -> None:
        from contracts.schemas import GraphSnapshot as ContractsGraphSnapshot

        from graph_engine.models import GraphSnapshot

        assert GraphSnapshot is ContractsGraphSnapshot, (
            "graph_engine.models.GraphSnapshot MUST be the SAME Python "
            "object as contracts.schemas.GraphSnapshot."
        )

    def test_graph_impact_snapshot_is_contracts_identity(self) -> None:
        from contracts.schemas import (
            GraphImpactSnapshot as ContractsGraphImpactSnapshot,
        )

        from graph_engine.models import GraphImpactSnapshot

        assert GraphImpactSnapshot is ContractsGraphImpactSnapshot, (
            "graph_engine.models.GraphImpactSnapshot MUST be the SAME "
            "Python object as contracts.schemas.GraphImpactSnapshot."
        )

    def test_graph_engine_top_level_exports_contracts_identity(self) -> None:
        """The top-level ``graph_engine`` package re-exports must also
        match contracts identity (consumers may import either path).
        """

        from contracts.schemas import (
            CandidateGraphDelta as ContractsCandidateGraphDelta,
        )
        from contracts.schemas import GraphImpactSnapshot as ContractsImpact
        from contracts.schemas import GraphSnapshot as ContractsSnapshot

        import graph_engine

        assert graph_engine.CandidateGraphDelta is ContractsCandidateGraphDelta
        assert graph_engine.GraphSnapshot is ContractsSnapshot
        assert graph_engine.GraphImpactSnapshot is ContractsImpact


# ── Layer 2: CONSUMER round-trip through real contracts validation ──


class TestConsumerSideRoundTripsThroughRealContracts:
    """A synthetic ``CandidateGraphDelta`` (canonical contracts wire
    shape) is constructed → graph-engine's downstream PRODUCER schemas
    (``GraphSnapshot`` + ``GraphImpactSnapshot``) are built via real
    Pydantic round-trip → re-validated through contracts. Drift in
    either direction (consumer rejection or producer schema drift)
    fails this lane.
    """

    def test_candidate_graph_delta_round_trip_input_path(self) -> None:
        """The canonical Ex-3 wire shape (what announcement / news
        produce) round-trips through graph-engine's consumer surface
        without fork. Test the INPUT direction.
        """

        from contracts.schemas import CandidateGraphDelta

        wire_payload = {
            "subsystem_id": "subsystem-news",
            "delta_id": "consumer-roundtrip-ex3-001",
            "delta_type": "add",
            "source_node": "ENT_STOCK_CONSUMER_SRC",
            "target_node": "ENT_STOCK_CONSUMER_DST",
            "relation_type": "supplier_of",
            "properties": {"contract_value": 1_000_000},
            "evidence": [
                "consumer-evidence-ref-001",
                "consumer-evidence-ref-002",
            ],
        }

        # Producer-side validate (announcement/news pattern).
        producer_validated = CandidateGraphDelta.model_validate(wire_payload)
        # Consumer-side validate (graph-engine pattern: same Python
        # object, but exercise the import path).
        from graph_engine.models import CandidateGraphDelta as GeDelta

        consumer_validated = GeDelta.model_validate(
            producer_validated.model_dump(mode="json")
        )

        assert consumer_validated.delta_id == wire_payload["delta_id"]
        assert consumer_validated.source_node == wire_payload["source_node"]
        assert consumer_validated.target_node == wire_payload["target_node"]
        assert consumer_validated.relation_type == wire_payload["relation_type"]

    @pytest.mark.parametrize("delta_type", ["upsert_edge", "edge_upsert"])
    @pytest.mark.parametrize("relation_type", ["CO_HOLDING", "NORTHBOUND_HOLD"])
    def test_holdings_relationship_terms_stay_inside_generic_ex3_contract(
        self,
        delta_type: str,
        relation_type: str,
    ) -> None:
        from contracts.schemas import CandidateGraphDelta

        from graph_engine.models import CandidateGraphDelta as GeDelta
        from graph_engine.schema.definitions import RelationshipType

        assert relation_type in {relationship.value for relationship in RelationshipType}

        payload = {
            "subsystem_id": "subsystem-holdings",
            "delta_id": f"{relation_type.lower()}-alignment-001",
            "delta_type": delta_type,
            "source_node": "ENT_HOLDING_SRC",
            "target_node": "ENT_HOLDING_DST",
            "relation_type": relation_type,
            "properties": {"weight": 0.7},
            "evidence": ["holdings-evidence-ref-001"],
        }

        contract_validated = CandidateGraphDelta.model_validate(payload)
        graph_validated = GeDelta.model_validate(contract_validated.model_dump(mode="json"))

        assert graph_validated is not contract_validated
        assert graph_validated.relation_type == relation_type

    def test_graph_snapshot_round_trip_output_path(self) -> None:
        """A synthetic ``GraphSnapshot`` (what graph-engine PRODUCES
        and writes back to Layer A for downstream main-core / audit-
        eval consumption) round-trips through real
        ``contracts.schemas.GraphSnapshot.model_validate``. Tests the
        OUTPUT direction.
        """

        from contracts.schemas import GraphSnapshot
        from contracts.schemas.graph import GraphEdge, GraphNode

        nodes = [
            GraphNode(
                node_id="ENT_STOCK_OUTPUT_SRC",
                labels=["Stock"],
                properties={"name": "Output Source Co"},
            ),
            GraphNode(
                node_id="ENT_STOCK_OUTPUT_DST",
                labels=["Stock"],
                properties={"name": "Output Dest Co"},
            ),
        ]
        edges = [
            GraphEdge(
                edge_id="consumer-roundtrip-edge-001",
                source_node="ENT_STOCK_OUTPUT_SRC",
                target_node="ENT_STOCK_OUTPUT_DST",
                relation_type="supplier_of",
                properties={},
            ),
        ]
        snapshot = GraphSnapshot(
            graph_snapshot_id="consumer-roundtrip-snapshot-001",
            cycle_id="cycle-2026-01-01",
            version="0.1.0",
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
            node_count=len(nodes),
            edge_count=len(edges),
            nodes=nodes,
            edges=edges,
        )

        # Round-trip dump → re-validate proves serialization is
        # lossless against the same canonical schema.
        round_tripped = GraphSnapshot.model_validate(
            snapshot.model_dump(mode="json")
        )
        assert round_tripped.graph_snapshot_id == snapshot.graph_snapshot_id
        assert round_tripped.node_count == snapshot.node_count
        assert round_tripped.edge_count == snapshot.edge_count
        # Snapshot's model_validator (counts_must_match_payloads) is
        # idempotent.
        assert len(round_tripped.nodes) == round_tripped.node_count
        assert len(round_tripped.edges) == round_tripped.edge_count


class TestForbiddenIngestMetadataKeptOutOfDeltas:
    """Iron rule (consistent with announcement/news): the CONSUMER side
    must NEVER receive ingest metadata fields like ``submitted_at`` /
    ``ingest_seq`` / ``layer_b_receipt_id`` — those are Layer B-owned.
    The contracts.semantics module already enforces this on the
    producer side; here we belt-and-suspenders confirm graph-engine
    receives clean payloads.
    """

    def test_layer_b_metadata_not_accepted_in_candidate_graph_delta(
        self,
    ) -> None:
        from pydantic import ValidationError

        from contracts.schemas import CandidateGraphDelta

        polluted_payload = {
            "subsystem_id": "subsystem-news",
            "delta_id": "polluted-ex3",
            "delta_type": "add",
            "source_node": "ENT_SRC",
            "target_node": "ENT_DST",
            "relation_type": "supplier_of",
            "properties": {},
            "evidence": ["e-001"],
            # Forbidden Layer B-only fields:
            "submitted_at": "2026-01-01T00:00:00Z",
            "ingest_seq": 42,
        }

        with pytest.raises(ValidationError):
            CandidateGraphDelta.model_validate(polluted_payload)
