from __future__ import annotations

import json
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest

import graph_engine.promotion.service as promotion_service
import graph_engine.rollout.canary as canary_module
from graph_engine.models import (
    CandidateGraphDelta,
    ColdReloadPlan,
    GraphEdgeRecord,
    GraphMetricsSnapshot,
    GraphNodeRecord,
    Neo4jGraphStatus,
    PropagationResult,
    PromotionPlan,
)
from graph_engine.promotion.service import promote_graph_deltas
from graph_engine.rollout import (
    EdgeReadbackSummary,
    EvidenceWriter,
    HoldingsAlgorithmCanarySummary,
    LiveGraphRolloutConfig,
    build_holdings_canary_context,
    redact_evidence_payload,
    run_holdings_canary_algorithms,
    run_live_graph_canary,
    validate_client_database_matches_config,
    validate_rollout_config,
    write_cold_reload_replay_evidence,
)
from graph_engine.status import GraphStatusManager
from tests.fakes import InMemoryStatusStore

NOW = datetime(2026, 5, 7, 12, 0, tzinfo=timezone.utc)
ENV = {"GRAPH_ENGINE_LIVE_GRAPH_ROLLOUT_CONFIRM": "1"}
ALLOW_HOLDINGS = {"CO_HOLDING", "NORTHBOUND_HOLD"}


class FakeClient:
    def __init__(
        self,
        *,
        database: str = "graph-canary-test-20260507",
        rows: list[dict[str, Any]] | None = None,
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
        return []


class FakeEntityReader:
    def canonical_entity_ids_for_node_ids(self, node_ids: set[str]) -> dict[str, str]:
        return {node_id: f"entity-{node_id}" for node_id in node_ids}

    def existing_entity_ids(self, entity_ids: set[str]) -> set[str]:
        return set(entity_ids)


class FakeCanonicalWriter:
    def __init__(self) -> None:
        self.plans: list[PromotionPlan] = []

    def write_canonical_records(self, plan: PromotionPlan) -> None:
        self.plans.append(plan)


class FakeColdReloadReader:
    def __init__(self, plan: ColdReloadPlan) -> None:
        self.plan = plan
        self.calls: list[str] = []
        self.drop_all_calls = 0

    def read_cold_reload_plan(self, snapshot_ref: str) -> ColdReloadPlan:
        self.calls.append(snapshot_ref)
        return self.plan

    def drop_all(self) -> None:
        self.drop_all_calls += 1


def test_rollout_guard_requires_confirm_default_db_namespace_and_client_match(tmp_path) -> None:  # type: ignore[no-untyped-def]
    config = _config(tmp_path)

    with pytest.raises(PermissionError, match="ROLLOUT_CONFIRM"):
        validate_rollout_config(config, env={})

    with pytest.raises(PermissionError, match="not allowed"):
        validate_rollout_config(
            _config(tmp_path, neo4j_database="neo4j"),
            env=ENV,
        )

    with pytest.raises(PermissionError, match="not allowed"):
        validate_rollout_config(
            _config(tmp_path, neo4j_database="production"),
            env=ENV,
        )

    with pytest.raises(PermissionError, match="namespace"):
        validate_rollout_config(_config(tmp_path, namespace=""), env=ENV)

    guarded = validate_rollout_config(config, env=ENV)
    with pytest.raises(PermissionError, match="client database does not match"):
        validate_client_database_matches_config(FakeClient(database="graph-canary-test-other"), guarded)


def test_rollout_guard_rejects_allowlist_outside_holdings_scope(tmp_path) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(PermissionError, match="holdings relationships"):
        validate_rollout_config(
            _config(
                tmp_path,
                allowed_relationship_types={"CO_HOLDING", "SUPPLY_CHAIN"},
            ),
            env=ENV,
        )


def test_promotion_relation_allowlist_rejects_before_canonical_writer_and_sync(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sync_live_graph = MagicMock()
    monkeypatch.setattr(promotion_service, "sync_live_graph", sync_live_graph)
    writer = FakeCanonicalWriter()

    with pytest.raises(PermissionError, match="SUPPLY_CHAIN"):
        promote_graph_deltas(
            "cycle-1",
            "selection-1",
            candidate_reader=_candidate_reader(
                [_candidate_delta("delta-supply", "SUPPLY_CHAIN")]
            ),
            entity_reader=FakeEntityReader(),
            canonical_writer=writer,
            client=FakeClient(),
            status_manager=_status_manager(),
            sync_to_live_graph=True,
            allowed_relationship_types=ALLOW_HOLDINGS,
        )

    assert writer.plans == []
    sync_live_graph.assert_not_called()


@pytest.mark.parametrize(
    ("graph_status", "writer_lock_token", "match"),
    [
        ("rebuilding", None, "graph_status='ready'"),
        ("ready", "incremental-sync", "active writer lock"),
    ],
)
def test_canary_status_guard_fails_before_promotion_and_neo4j(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
    graph_status: str,
    writer_lock_token: str | None,
    match: str,
) -> None:  # type: ignore[no-untyped-def]
    promote = MagicMock(side_effect=AssertionError("promotion must not run"))
    monkeypatch.setattr(canary_module, "promote_graph_deltas", promote)
    client = FakeClient()

    with pytest.raises(PermissionError, match=match):
        run_live_graph_canary(
            cycle_id="cycle-1",
            selection_ref="selection-1",
            candidate_deltas=[_candidate_delta("delta-co", "CO_HOLDING")],
            entity_reader=FakeEntityReader(),
            client=client,
            status_manager=_status_manager(
                graph_status=graph_status,  # type: ignore[arg-type]
                writer_lock_token=writer_lock_token,
            ),
            config=_config(tmp_path),
            env=ENV,
        )

    promote.assert_not_called()
    assert client.write_calls == []


def test_evidence_writer_redacts_secrets_paths_and_raw_payload(tmp_path) -> None:  # type: ignore[no-untyped-def]
    writer = EvidenceWriter(tmp_path, namespace="canary-20260507")

    path = writer.write_manifest(
        "redaction",
        {
            "namespace": "canary-20260507",
            "neo4j_database_label": "graph-canary-test-20260507",
            "dsn": "postgresql://user:secret@localhost/db",
            "password": "secret",
            "local_path": "/Users/fanjie/Desktop/Cowork/project-ult/private.json",
            "nested": {
                "raw_payload": {"token": "ghp_secretvalue"},
                "safe": "graph-canary-test-20260507",
                "note": '{"token":"ghp_secretvalue","raw_payload":"x"}',
            },
        },
    )

    text = path.read_text(encoding="utf-8")
    payload = json.loads(text)
    assert "postgresql://" not in text
    assert "ghp_secretvalue" not in text
    assert "/Users/fanjie" not in text
    assert payload["dsn"] == "<redacted>"
    assert payload["password"] == "<redacted>"
    assert payload["local_path"] == "<redacted>"
    assert payload["nested"]["raw_payload"] == "<redacted>"
    assert payload["nested"]["note"] == "<redacted>"
    assert payload["nested"]["safe"] == "graph-canary-test-20260507"
    assert redact_evidence_payload({"database_url": "postgresql://x"}) == {
        "database_url": "<redacted>"
    }


def test_canary_runner_writes_evidence_and_uses_explicit_holdings_algorithms(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:  # type: ignore[no-untyped-def]
    calls: list[str] = []
    plan = _promotion_plan()

    def fake_promote_graph_deltas(*args: Any, **kwargs: Any) -> PromotionPlan:
        calls.append("promote")
        assert kwargs["allowed_relationship_types"] == ALLOW_HOLDINGS
        assert kwargs["sync_to_live_graph"] is True
        kwargs["canonical_writer"].write_canonical_records(plan)
        return plan

    def fake_algorithms(*args: Any, **kwargs: Any) -> HoldingsAlgorithmCanarySummary:
        calls.append("algorithms")
        return HoldingsAlgorithmCanarySummary(
            cycle_id="cycle-1",
            graph_generation_id=4,
            co_holding_path_count=1,
            northbound_path_count=1,
            total_path_count=2,
            impacted_entity_count=1,
            co_holding_diagnostics={"candidate_pair_count": 3},
            northbound_diagnostics={"window_count": 2},
        )

    monkeypatch.setattr(canary_module, "promote_graph_deltas", fake_promote_graph_deltas)
    monkeypatch.setattr(canary_module, "run_holdings_canary_algorithms", fake_algorithms)

    summary = run_live_graph_canary(
        cycle_id="cycle-1",
        selection_ref="selection-1",
        candidate_deltas=[
            _candidate_delta("delta-co", "CO_HOLDING"),
            _candidate_delta("delta-nb", "NORTHBOUND_HOLD"),
        ],
        entity_reader=FakeEntityReader(),
        client=FakeClient(),
        status_manager=_status_manager(graph_generation_id=4),
        config=_config(tmp_path),
        env=ENV,
        readback_hook=lambda client, plan, allowed: EdgeReadbackSummary(
            expected_edge_count=2,
            edge_count=2,
            relation_counts={"CO_HOLDING": 1, "NORTHBOUND_HOLD": 1},
            missing_edge_ids=[],
            disallowed_relation_types=[],
        ),
    )

    assert calls == ["promote", "algorithms"]
    assert summary.layer_a_artifact.relation_counts == {
        "CO_HOLDING": 1,
        "NORTHBOUND_HOLD": 1,
    }
    evidence = json.loads(summary.evidence_manifest_path.read_text(encoding="utf-8"))
    assert evidence["mode"] == "canary"
    assert evidence["neo4j_database_label"] == "graph-canary-test-20260507"
    assert evidence["relation_counts"] == {"CO_HOLDING": 1, "NORTHBOUND_HOLD": 1}
    assert evidence["layer_a_artifact"]["relation_counts"] == {
        "CO_HOLDING": 1,
        "NORTHBOUND_HOLD": 1,
    }
    assert evidence["edge_readback"]["missing_edge_ids"] == []
    assert evidence["edge_readback"]["disallowed_relation_types"] == []
    assert evidence["holdings_algorithms"]["co_holding_diagnostics"] == {
        "candidate_pair_count": 3,
    }
    assert evidence["holdings_algorithms"]["northbound_diagnostics"] == {
        "window_count": 2,
    }
    assert "run_full_propagation" not in canary_module.__dict__


def test_readback_canary_edges_is_read_only_and_reports_sync_failures() -> None:
    client = FakeClient(
        rows=[
            {"edge_id": "edge-co", "relationship_type": "CO_HOLDING"},
            {"edge_id": "edge-bad", "relationship_type": "SUPPLY_CHAIN"},
        ],
    )

    with pytest.raises(ValueError, match="missing synced canary edges"):
        canary_module.readback_canary_edges(
            client,
            plan=_promotion_plan(),
            allowed_relationship_types=ALLOW_HOLDINGS,
        )

    summary = canary_module.readback_canary_edges(
        client,
        plan=_promotion_plan(),
        allowed_relationship_types=ALLOW_HOLDINGS,
        strict=False,
    )

    assert summary.missing_edge_ids == ["edge-nb"]
    assert summary.disallowed_relation_types == ["SUPPLY_CHAIN"]
    assert summary.relation_counts == {"CO_HOLDING": 1, "SUPPLY_CHAIN": 1}
    assert client.write_calls == []
    assert "MATCH" in client.read_calls[0][0]
    assert "MERGE" not in client.read_calls[0][0]


def test_holdings_canary_algorithm_summary_calls_only_explicit_algorithms(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    def fake_co_holding(*args: Any, **kwargs: Any) -> PropagationResult:
        calls.append("co")
        return _propagation_result("co_holding_crowding", "reflexive")

    def fake_northbound(*args: Any, **kwargs: Any) -> PropagationResult:
        calls.append("nb")
        return _propagation_result("northbound_anomaly", "event")

    monkeypatch.setattr(canary_module, "run_co_holding_crowding", fake_co_holding)
    monkeypatch.setattr(canary_module, "run_northbound_anomaly", fake_northbound)

    summary = run_holdings_canary_algorithms(
        build_holdings_canary_context(
            cycle_id="cycle-1",
            graph_generation_id=4,
            namespace="canary-20260507",
        ),
        FakeClient(),
        status_manager=_status_manager(graph_generation_id=4),
    )

    assert calls == ["co", "nb"]
    assert summary.total_path_count == 2
    assert "run_full_propagation" not in canary_module.__dict__


def test_cold_reload_replay_evidence_reads_artifact_plan_without_destructive_reload(
    tmp_path,
) -> None:  # type: ignore[no-untyped-def]
    reader = FakeColdReloadReader(_cold_reload_plan())

    evidence_path = write_cold_reload_replay_evidence(
        snapshot_ref="/Users/fanjie/Desktop/Cowork/project-ult/private/reload_plan.json",
        canonical_reader=reader,
        config=_config(tmp_path),
        env=ENV,
    )

    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    assert reader.calls == ["/Users/fanjie/Desktop/Cowork/project-ult/private/reload_plan.json"]
    assert reader.drop_all_calls == 0
    assert evidence["destructive_reload_executed"] is False
    assert evidence["reload_ref"] == "reload_plan.json"
    assert "/Users/fanjie" not in evidence_path.read_text(encoding="utf-8")
    assert evidence["relation_counts"] == {"CO_HOLDING": 1, "NORTHBOUND_HOLD": 1}


def _config(
    tmp_path,  # type: ignore[no-untyped-def]
    *,
    namespace: str = "canary-20260507",
    neo4j_database: str = "graph-canary-test-20260507",
    allowed_relationship_types: set[str] | None = None,
) -> LiveGraphRolloutConfig:
    return LiveGraphRolloutConfig(
        namespace=namespace,
        mode="canary",
        neo4j_database=neo4j_database,
        allowed_relationship_types=set(allowed_relationship_types or ALLOW_HOLDINGS),
        artifact_root=tmp_path,
    )


def _candidate_reader(deltas: list[CandidateGraphDelta]) -> Any:
    return SimpleNamespace(
        read_candidate_graph_deltas=lambda cycle_id, selection_ref: list(deltas)
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


def _promotion_plan() -> PromotionPlan:
    return PromotionPlan(
        cycle_id="cycle-1",
        selection_ref="selection-1",
        delta_ids=["delta-co", "delta-nb"],
        node_records=[_node("node-a", "entity-a"), _node("node-b", "entity-b")],
        edge_records=[
            _edge("edge-co", "CO_HOLDING"),
            _edge("edge-nb", "NORTHBOUND_HOLD"),
        ],
        assertion_records=[],
        created_at=NOW,
    )


def _cold_reload_plan() -> ColdReloadPlan:
    plan = _promotion_plan()
    return ColdReloadPlan(
        snapshot_ref="snapshot-1",
        cycle_id="cycle-1",
        expected_snapshot=GraphMetricsSnapshot(
            cycle_id="cycle-1",
            snapshot_id="snapshot-1",
            graph_generation_id=4,
            node_count=2,
            edge_count=2,
            key_label_counts={"Entity": 2},
            checksum="checksum",
            created_at=NOW,
        ),
        node_records=plan.node_records,
        edge_records=plan.edge_records,
        assertion_records=[],
        projection_name="graph_canary_test",
        created_at=NOW,
    )


def _node(node_id: str, canonical_entity_id: str) -> GraphNodeRecord:
    return GraphNodeRecord(
        node_id=node_id,
        canonical_entity_id=canonical_entity_id,
        label="Entity",
        properties={"canonical_id_rule_version": "test/v1"},
        created_at=NOW,
        updated_at=NOW,
    )


def _edge(edge_id: str, relationship_type: str) -> GraphEdgeRecord:
    return GraphEdgeRecord(
        edge_id=edge_id,
        source_node_id="node-a",
        target_node_id="node-b",
        relationship_type=relationship_type,
        properties={"evidence_refs": [f"fact-{edge_id}"]},
        weight=1.0,
        created_at=NOW,
        updated_at=NOW,
    )


def _status_manager(
    *,
    graph_status: str = "ready",
    graph_generation_id: int = 1,
    writer_lock_token: str | None = None,
) -> GraphStatusManager:
    return GraphStatusManager(
        InMemoryStatusStore(
            Neo4jGraphStatus(
                graph_status=graph_status,  # type: ignore[arg-type]
                graph_generation_id=graph_generation_id,
                node_count=2,
                edge_count=2,
                key_label_counts={"Entity": 2},
                checksum="checksum",
                last_verified_at=NOW if graph_status == "ready" else None,
                last_reload_at=None,
                writer_lock_token=writer_lock_token,
            )
        )
    )


def _propagation_result(algorithm: str, channel: str) -> PropagationResult:
    relationship_type = "CO_HOLDING" if channel == "reflexive" else "NORTHBOUND_HOLD"
    return PropagationResult(
        cycle_id="cycle-1",
        graph_generation_id=4,
        activated_paths=[
            {
                "source_node_id": "node-a",
                "target_node_id": "node-b",
                "relationship_type": relationship_type,
                "score": 0.5,
            }
        ],
        impacted_entities=[{"node_id": "node-b", "score": 0.5}],
        channel_breakdown={
            channel: {
                algorithm: {
                    "relationship_type": relationship_type,
                    "diagnostics": {},
                }
            }
        },
    )
