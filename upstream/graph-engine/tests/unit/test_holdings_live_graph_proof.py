from __future__ import annotations

import json
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any

import pytest
from contracts.schemas import CandidateGraphDelta

import graph_engine.proofs.holdings_live_graph as proof_module
from graph_engine.models import (
    GraphEdgeRecord,
    GraphAssertionRecord,
    GraphNodeRecord,
    Neo4jGraphStatus,
    PropagationResult,
    PromotionPlan,
)
from graph_engine.proofs import (
    HoldingsAlgorithmProofSummary,
    LayerAArtifactCanonicalWriter,
    LoadedCandidateDeltaReader,
    build_holdings_proof_context,
    run_holdings_live_graph_proof,
    run_holdings_algorithm_proof,
    validate_holdings_candidate_deltas,
    validate_holdings_live_graph_proof_env,
    verify_holdings_edges,
    write_layer_a_artifact,
)
from graph_engine.status import GraphStatusManager
from tests.fakes import InMemoryStatusStore

NOW = datetime(2026, 5, 7, 12, 0, tzinfo=timezone.utc)


class FakeReadOnlyClient:
    def __init__(
        self,
        rows: list[dict[str, Any]] | None = None,
        *,
        database: str = "projectultproof20260507",
    ) -> None:
        self.config = SimpleNamespace(database=database)
        self.rows = rows or []
        self.read_calls: list[tuple[str, dict[str, Any]]] = []
        self.write_calls: list[tuple[str, dict[str, Any]]] = []

    def execute_read(
        self,
        query: str,
        parameters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        self.read_calls.append((query, parameters or {}))
        return list(self.rows)

    def execute_write(
        self,
        query: str,
        parameters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        self.write_calls.append((query, parameters or {}))
        raise AssertionError("proof readback must not write")


def test_live_graph_proof_guard_requires_confirm(tmp_path) -> None:  # type: ignore[no-untyped-def]
    env = {
        "GRAPH_ENGINE_LIVE_PROOF_NAMESPACE": "proof-20260507-a",
        "NEO4J_DATABASE": "projectultproof20260507",
    }

    with pytest.raises(PermissionError, match="GRAPH_ENGINE_LIVE_PROOF_CONFIRM"):
        validate_holdings_live_graph_proof_env(env, artifact_root=tmp_path / "proof-artifacts")


def test_live_graph_proof_guard_rejects_default_neo4j(tmp_path) -> None:  # type: ignore[no-untyped-def]
    env = {
        "GRAPH_ENGINE_LIVE_PROOF_CONFIRM": "1",
        "GRAPH_ENGINE_LIVE_PROOF_NAMESPACE": "proof-20260507-a",
        "NEO4J_DATABASE": "neo4j",
    }

    with pytest.raises(PermissionError, match="default Neo4j database"):
        validate_holdings_live_graph_proof_env(env, artifact_root=tmp_path / "proof-artifacts")


@pytest.mark.parametrize("database", ["system", "prod", "production", "live"])
def test_live_graph_proof_guard_rejects_unsafe_non_default_db_names(
    tmp_path,
    database: str,
) -> None:  # type: ignore[no-untyped-def]
    env = {
        "GRAPH_ENGINE_LIVE_PROOF_CONFIRM": "1",
        "GRAPH_ENGINE_LIVE_PROOF_NAMESPACE": "proof-20260507-a",
        "NEO4J_DATABASE": database,
    }

    with pytest.raises(PermissionError, match="not allowed"):
        validate_holdings_live_graph_proof_env(env, artifact_root=tmp_path / "proof-artifacts")


def test_live_graph_proof_guard_requires_disposable_db_marker(tmp_path) -> None:  # type: ignore[no-untyped-def]
    env = {
        "GRAPH_ENGINE_LIVE_PROOF_CONFIRM": "1",
        "GRAPH_ENGINE_LIVE_PROOF_NAMESPACE": "proof-20260507-a",
        "NEO4J_DATABASE": "analytics",
    }

    with pytest.raises(PermissionError, match="proof, smoke, or test"):
        validate_holdings_live_graph_proof_env(env, artifact_root=tmp_path / "proof-artifacts")


def test_live_graph_proof_guard_accepts_safe_proof_db(tmp_path) -> None:  # type: ignore[no-untyped-def]
    env = {
        "GRAPH_ENGINE_LIVE_PROOF_CONFIRM": "1",
        "GRAPH_ENGINE_LIVE_PROOF_NAMESPACE": "proof-20260507-a",
        "NEO4J_DATABASE": "projectultproof20260507",
    }

    config = validate_holdings_live_graph_proof_env(
        env,
        artifact_root=tmp_path / "proof-artifacts",
    )

    assert config.neo4j_database == "projectultproof20260507"


def test_live_graph_proof_guard_requires_namespace(tmp_path) -> None:  # type: ignore[no-untyped-def]
    env = {
        "GRAPH_ENGINE_LIVE_PROOF_CONFIRM": "1",
        "NEO4J_DATABASE": "projectultproof20260507",
    }

    with pytest.raises(PermissionError, match="GRAPH_ENGINE_LIVE_PROOF_NAMESPACE"):
        validate_holdings_live_graph_proof_env(env, artifact_root=tmp_path / "proof-artifacts")


def test_live_graph_proof_guard_rejects_non_proof_artifact_root(tmp_path) -> None:  # type: ignore[no-untyped-def]
    env = {
        "GRAPH_ENGINE_LIVE_PROOF_CONFIRM": "1",
        "GRAPH_ENGINE_LIVE_PROOF_NAMESPACE": "proof-20260507-a",
        "NEO4J_DATABASE": "projectultproof20260507",
    }

    with pytest.raises(ValueError, match="proof/smoke/test workspace"):
        validate_holdings_live_graph_proof_env(env, artifact_root=tmp_path / "artifacts")


def test_layer_a_artifact_writer_sanitizes_manifest_and_records(tmp_path) -> None:  # type: ignore[no-untyped-def]
    plan = _promotion_plan()
    summary = write_layer_a_artifact(
        plan,
        artifact_root=tmp_path / "proof-workspace",
        namespace="proof-20260507-a",
    )

    manifest = json.loads(summary.manifest_path.read_text(encoding="utf-8"))
    assert manifest == {
        "artifact_type": "holdings_live_graph_layer_a",
        "assertion_count": 0,
        "created_at": NOW.isoformat(),
        "cycle_id": "cycle-1",
        "delta_count": 2,
        "delta_ids": ["delta-co", "delta-nb"],
        "edge_count": 2,
        "layer": "Layer A",
        "namespace": "proof-20260507-a",
        "node_count": 2,
        "records_ref": "canonical_records.jsonl",
        "relation_counts": {"CO_HOLDING": 1, "NORTHBOUND_HOLD": 1},
        "relation_types": ["CO_HOLDING", "NORTHBOUND_HOLD"],
        "selection_ref": "selection-1",
    }
    assert str(tmp_path) not in summary.manifest_path.read_text(encoding="utf-8")

    records = [
        json.loads(line)
        for line in summary.records_path.read_text(encoding="utf-8").splitlines()
    ]
    assert [record["record_type"] for record in records] == ["node", "node", "edge", "edge"]
    assert {record["record"]["relationship_type"] for record in records if record["record_type"] == "edge"} == {
        "CO_HOLDING",
        "NORTHBOUND_HOLD",
    }


def test_layer_a_artifact_redacts_nested_sensitive_values(tmp_path) -> None:  # type: ignore[no-untyped-def]
    plan = _sensitive_promotion_plan()

    summary = write_layer_a_artifact(
        plan,
        artifact_root=tmp_path / "proof-workspace",
        namespace="proof-20260507-a",
    )

    records_text = summary.records_path.read_text(encoding="utf-8")
    assert "postgresql://" not in records_text
    assert "ghp_secretvalue" not in records_text
    assert "/Users/fanjie/Desktop/Cowork/project-ult" not in records_text
    assert "raw_provider_payload" not in records_text
    assert "projectultproof20260507" in records_text

    records = [json.loads(line) for line in records_text.splitlines()]
    node_record = next(record["record"] for record in records if record["record_type"] == "node")
    edge_record = next(record["record"] for record in records if record["record_type"] == "edge")
    assertion_record = next(
        record["record"] for record in records if record["record_type"] == "assertion"
    )

    assert node_record["properties"]["local_path"] == "<redacted>"
    assert edge_record["properties"]["lineage"]["database_url"] == "<redacted>"
    assert edge_record["properties"]["lineage"]["nested"]["raw_payload"] == "<redacted>"
    assert edge_record["properties"]["notes"] == "<redacted>"
    assert assertion_record["evidence"]["provider_payload"] == "<redacted>"
    assert assertion_record["evidence"]["safe_summary"] == "projectultproof20260507"


def test_layer_a_canonical_writer_records_last_summary(tmp_path) -> None:  # type: ignore[no-untyped-def]
    writer = LayerAArtifactCanonicalWriter(
        tmp_path / "proof-workspace",
        namespace="proof-20260507-a",
    )

    writer.write_canonical_records(_promotion_plan())

    assert writer.last_summary is not None
    assert writer.last_summary.edge_count == 2
    assert writer.last_summary.relation_counts == {"CO_HOLDING": 1, "NORTHBOUND_HOLD": 1}


def test_relation_whitelist_rejects_non_holdings_candidate() -> None:
    with pytest.raises(ValueError, match="SUPPLY_CHAIN"):
        validate_holdings_candidate_deltas(
            [
                CandidateGraphDelta(
                    delta_id="delta-supply",
                    delta_type="edge_upsert",
                    source_node="node-a",
                    target_node="node-b",
                    relation_type="SUPPLY_CHAIN",
                    properties={"evidence_refs": ["fact-supply"]},
                    evidence=["fact-supply"],
                    subsystem_id="subsystem-news",
                )
            ]
        )


def test_loaded_candidate_reader_validates_relation_whitelist() -> None:
    reader = LoadedCandidateDeltaReader([_candidate_delta("delta-co", "CO_HOLDING")])

    assert reader.read_candidate_graph_deltas("cycle-1", "selection-1") == [
        _candidate_delta("delta-co", "CO_HOLDING")
    ]

    bad_reader = LoadedCandidateDeltaReader([_candidate_delta("delta-bad", "SUPPLY_CHAIN")])
    with pytest.raises(ValueError, match="SUPPLY_CHAIN"):
        bad_reader.read_candidate_graph_deltas("cycle-1", "selection-1")


def test_layer_a_artifact_rejects_non_holdings_plan(tmp_path) -> None:  # type: ignore[no-untyped-def]
    plan = _promotion_plan(relationship_type="SUPPLY_CHAIN")

    with pytest.raises(ValueError, match="SUPPLY_CHAIN"):
        write_layer_a_artifact(
            plan,
            artifact_root=tmp_path / "proof-workspace",
            namespace="proof-20260507-a",
        )


def test_verify_holdings_edges_rejects_missing_and_disallowed_edges() -> None:
    client = FakeReadOnlyClient(
        rows=[
            {"edge_id": "edge-co", "relationship_type": "CO_HOLDING"},
            {"edge_id": "edge-bad", "relationship_type": "SUPPLY_CHAIN"},
        ]
    )

    with pytest.raises(ValueError, match="missing synced holdings edges"):
        verify_holdings_edges(client, edge_ids=["edge-co", "edge-nb", "edge-bad"])

    summary = verify_holdings_edges(
        client,
        edge_ids=["edge-co", "edge-nb", "edge-bad"],
        strict=False,
    )
    assert summary.edge_count == 2
    assert summary.missing_edge_ids == ["edge-nb"]
    assert summary.disallowed_relation_types == ["SUPPLY_CHAIN"]
    assert summary.relation_counts == {"CO_HOLDING": 1, "SUPPLY_CHAIN": 1}
    assert client.write_calls == []
    assert "MATCH" in client.read_calls[0][0]
    assert "MERGE" not in client.read_calls[0][0]


def test_verify_holdings_edges_passes_for_whitelisted_edges() -> None:
    client = FakeReadOnlyClient(
        rows=[
            {"edge_id": "edge-co", "relationship_type": "CO_HOLDING"},
            {"edge_id": "edge-nb", "relationship_type": "NORTHBOUND_HOLD"},
        ]
    )

    summary = verify_holdings_edges(client, edge_ids=["edge-co", "edge-nb"])

    assert summary.expected_edge_count == 2
    assert summary.edge_count == 2
    assert summary.relation_counts == {"CO_HOLDING": 1, "NORTHBOUND_HOLD": 1}
    assert summary.missing_edge_ids == []
    assert summary.disallowed_relation_types == []


def test_holdings_algorithm_proof_calls_explicit_algorithms_only(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    calls: list[str] = []

    def fake_co_holding(*args: Any, **kwargs: Any) -> PropagationResult:
        calls.append("co")
        return _propagation_result("co_holding_crowding", "reflexive", "CO_HOLDING")

    def fake_northbound(*args: Any, **kwargs: Any) -> PropagationResult:
        calls.append("nb")
        return _propagation_result("northbound_anomaly", "event", "NORTHBOUND_HOLD")

    monkeypatch.setattr(proof_module, "run_co_holding_crowding", fake_co_holding)
    monkeypatch.setattr(proof_module, "run_northbound_anomaly", fake_northbound)

    summary = run_holdings_algorithm_proof(
        build_holdings_proof_context(
            cycle_id="cycle-1",
            graph_generation_id=4,
            namespace="proof-20260507-a",
        ),
        FakeReadOnlyClient(),
        status_manager=_status_manager(graph_generation_id=4),
    )

    assert calls == ["co", "nb"]
    assert summary.co_holding_path_count == 1
    assert summary.northbound_path_count == 1
    assert summary.total_path_count == 2
    assert summary.impacted_entity_count == 1
    assert not hasattr(proof_module, "run_full_propagation")


def test_holdings_algorithm_proof_requires_event_and_reflexive_channels() -> None:
    context = build_holdings_proof_context(
        cycle_id="cycle-1",
        graph_generation_id=4,
        namespace="proof-20260507-a",
    ).model_copy(update={"enabled_channels": ["event"]})

    with pytest.raises(PermissionError, match="event and reflexive"):
        run_holdings_algorithm_proof(
            context,
            FakeReadOnlyClient(),
            status_manager=_status_manager(graph_generation_id=4),
        )


def test_live_graph_proof_harness_blocks_dangerous_db_before_promotion(
    monkeypatch,
    tmp_path,
) -> None:  # type: ignore[no-untyped-def]
    called = False

    def fail_if_called(*args: Any, **kwargs: Any) -> PromotionPlan:
        nonlocal called
        called = True
        raise AssertionError("promotion must not run when guard fails")

    monkeypatch.setattr(proof_module, "promote_graph_deltas", fail_if_called)

    with pytest.raises(PermissionError, match="default Neo4j database"):
        run_holdings_live_graph_proof(
            cycle_id="cycle-1",
            selection_ref="selection-1",
            candidate_deltas=[_candidate_delta("delta-co", "CO_HOLDING")],
            entity_reader=object(),  # type: ignore[arg-type]
            client=FakeReadOnlyClient(),
            status_manager=_status_manager(graph_generation_id=4),
            env={
                "GRAPH_ENGINE_LIVE_PROOF_CONFIRM": "1",
                "GRAPH_ENGINE_LIVE_PROOF_NAMESPACE": "proof-20260507-a",
                "NEO4J_DATABASE": "neo4j",
            },
            artifact_root=tmp_path / "proof-workspace",
        )

    assert called is False


def test_live_graph_proof_harness_rejects_client_db_mismatch_before_promotion(
    monkeypatch,
    tmp_path,
) -> None:  # type: ignore[no-untyped-def]
    called = False

    def fail_if_called(*args: Any, **kwargs: Any) -> PromotionPlan:
        nonlocal called
        called = True
        raise AssertionError("promotion must not run when client database mismatches")

    monkeypatch.setattr(proof_module, "promote_graph_deltas", fail_if_called)

    with pytest.raises(PermissionError, match="client database does not match"):
        run_holdings_live_graph_proof(
            cycle_id="cycle-1",
            selection_ref="selection-1",
            candidate_deltas=[_candidate_delta("delta-co", "CO_HOLDING")],
            entity_reader=object(),  # type: ignore[arg-type]
            client=FakeReadOnlyClient(database="neo4j"),
            status_manager=_status_manager(graph_generation_id=4),
            env={
                "GRAPH_ENGINE_LIVE_PROOF_CONFIRM": "1",
                "GRAPH_ENGINE_LIVE_PROOF_NAMESPACE": "proof-20260507-a",
                "NEO4J_DATABASE": "projectultproof20260507",
            },
            artifact_root=tmp_path / "proof-workspace",
        )

    assert called is False


def test_live_graph_proof_harness_runs_promotion_readback_and_algorithm_summary(
    monkeypatch,
    tmp_path,
) -> None:  # type: ignore[no-untyped-def]
    calls: list[str] = []
    plan = _promotion_plan()
    client = FakeReadOnlyClient(
        rows=[
            {"edge_id": "edge-co", "relationship_type": "CO_HOLDING"},
            {"edge_id": "edge-nb", "relationship_type": "NORTHBOUND_HOLD"},
        ]
    )

    def fake_promote_graph_deltas(*args: Any, **kwargs: Any) -> PromotionPlan:
        calls.append("promote")
        assert kwargs["sync_to_live_graph"] is True
        kwargs["canonical_writer"].write_canonical_records(plan)
        return plan

    def fake_algorithm_proof(*args: Any, **kwargs: Any) -> HoldingsAlgorithmProofSummary:
        calls.append("algorithms")
        return HoldingsAlgorithmProofSummary(
            cycle_id="cycle-1",
            graph_generation_id=4,
            co_holding_path_count=1,
            northbound_path_count=1,
            total_path_count=2,
            impacted_entity_count=1,
            co_holding_diagnostics={},
            northbound_diagnostics={},
        )

    monkeypatch.setattr(proof_module, "promote_graph_deltas", fake_promote_graph_deltas)
    monkeypatch.setattr(proof_module, "run_holdings_algorithm_proof", fake_algorithm_proof)

    summary = run_holdings_live_graph_proof(
        cycle_id="cycle-1",
        selection_ref="selection-1",
        candidate_deltas=[
            _candidate_delta("delta-co", "CO_HOLDING"),
            _candidate_delta("delta-nb", "NORTHBOUND_HOLD"),
        ],
        entity_reader=object(),  # type: ignore[arg-type]
        client=client,
        status_manager=_status_manager(graph_generation_id=4),
        env={
            "GRAPH_ENGINE_LIVE_PROOF_CONFIRM": "1",
            "GRAPH_ENGINE_LIVE_PROOF_NAMESPACE": "proof-20260507-a",
            "NEO4J_DATABASE": "projectultproof20260507",
        },
        artifact_root=tmp_path / "proof-workspace",
    )

    assert calls == ["promote", "algorithms"]
    assert summary.namespace == "proof-20260507-a"
    assert summary.neo4j_database == "projectultproof20260507"
    assert summary.layer_a_artifact.edge_count == 2
    assert summary.edge_verification.relation_counts == {
        "CO_HOLDING": 1,
        "NORTHBOUND_HOLD": 1,
    }
    assert summary.algorithm_proof.total_path_count == 2
    assert client.write_calls == []


def _promotion_plan(*, relationship_type: str = "CO_HOLDING") -> PromotionPlan:
    return PromotionPlan(
        cycle_id="cycle-1",
        selection_ref="selection-1",
        delta_ids=["delta-co", "delta-nb"],
        node_records=[
            _node("node-a", "entity-a"),
            _node("node-b", "entity-b"),
        ],
        edge_records=[
            _edge(
                "edge-co",
                relationship_type,
                properties={
                    "evidence_refs": ["fact-co"],
                    "jaccard_score": 0.5,
                    "co_holding_fund_count": 3,
                },
            ),
            _edge(
                "edge-nb",
                "NORTHBOUND_HOLD",
                properties={
                    "evidence_refs": ["fact-nb"],
                    "metric_z_score": 2.4,
                    "z_score_metric": "holding_ratio",
                },
            ),
        ],
        assertion_records=[],
        created_at=NOW,
    )


def _sensitive_promotion_plan() -> PromotionPlan:
    return PromotionPlan(
        cycle_id="cycle-1",
        selection_ref="selection-1",
        delta_ids=["delta-sensitive"],
        node_records=[
            _node(
                "node-a",
                "entity-a",
                properties={
                    "canonical_id_rule_version": "proof/v1",
                    "local_path": "/Users/fanjie/Desktop/Cowork/project-ult/.local/proof",
                },
            )
        ],
        edge_records=[
            _edge(
                "edge-sensitive",
                "CO_HOLDING",
                properties={
                    "evidence_refs": ["fact-sensitive"],
                    "lineage": {
                        "database_url": "postgresql://dp:secret@localhost:5432/proof",
                        "nested": {
                            "raw_payload": {
                                "provider": "raw_provider_payload",
                                "token": "ghp_secretvalue",
                            }
                        },
                    },
                    "notes": '{"token":"ghp_secretvalue","raw_payload":"raw_provider_payload"}',
                    "safe_summary": "projectultproof20260507",
                },
            )
        ],
        assertion_records=[
            GraphAssertionRecord(
                assertion_id="assertion-sensitive",
                source_node_id="node-a",
                target_node_id=None,
                assertion_type="HOLDINGS_PROOF",
                evidence={
                    "provider_payload": '{"token":"ghp_secretvalue"}',
                    "safe_summary": "projectultproof20260507",
                },
                confidence=0.9,
                created_at=NOW,
            )
        ],
        created_at=NOW,
    )


def _candidate_delta(delta_id: str, relation_type: str) -> CandidateGraphDelta:
    return CandidateGraphDelta(
        delta_id=delta_id,
        delta_type="edge_upsert",
        source_node="node-a",
        target_node="node-b",
        relation_type=relation_type,
        properties={"evidence_refs": [f"fact-{delta_id}"]},
        evidence=[f"fact-{delta_id}"],
        subsystem_id="subsystem-holdings",
    )


def _node(
    node_id: str,
    canonical_entity_id: str,
    *,
    properties: dict[str, Any] | None = None,
) -> GraphNodeRecord:
    return GraphNodeRecord(
        node_id=node_id,
        canonical_entity_id=canonical_entity_id,
        label="Entity",
        properties=properties or {"canonical_id_rule_version": "proof/v1"},
        created_at=NOW,
        updated_at=NOW,
    )


def _edge(
    edge_id: str,
    relationship_type: str,
    *,
    properties: dict[str, Any],
) -> GraphEdgeRecord:
    return GraphEdgeRecord(
        edge_id=edge_id,
        source_node_id="node-a",
        target_node_id="node-b",
        relationship_type=relationship_type,
        properties=properties,
        weight=1.0,
        created_at=NOW,
        updated_at=NOW,
    )


def _status_manager(*, graph_generation_id: int) -> GraphStatusManager:
    return GraphStatusManager(
        InMemoryStatusStore(
            Neo4jGraphStatus(
                graph_status="ready",
                graph_generation_id=graph_generation_id,
                node_count=2,
                edge_count=2,
                key_label_counts={"Entity": 2},
                checksum="abc123",
                last_verified_at=NOW,
                last_reload_at=None,
            )
        )
    )


def _propagation_result(
    algorithm: str,
    channel: str,
    relationship_type: str,
) -> PropagationResult:
    breakdown = {
        "reflexive": {"co_holding_crowding": {"diagnostics": {"missing": 1}}},
    }
    if channel == "event":
        breakdown = {"event": {"northbound_anomaly": {"diagnostics": {}}}}
    return PropagationResult(
        cycle_id="cycle-1",
        graph_generation_id=4,
        activated_paths=[
            {
                "algorithm": algorithm,
                "channel": channel,
                "edge_id": f"edge-{channel}",
                "relationship_type": relationship_type,
                "target_node_id": "node-b",
                "score": 1.0,
            }
        ],
        impacted_entities=[
            {
                "channel": channel,
                "node_id": "node-b",
                "canonical_entity_id": "entity-b",
                "score": 1.0,
                "path_count": 1,
            }
        ],
        channel_breakdown=breakdown,
    )
