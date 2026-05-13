from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import pytest

from graph_engine.models import Neo4jGraphStatus, PropagationContext
from graph_engine.propagation import (
    HoldingsAlgorithmConfig,
    run_co_holding_crowding,
    run_holdings_algorithms,
    run_northbound_anomaly,
)
from graph_engine.status import GraphStatusManager
from tests.fakes import InMemoryStatusStore

NOW = datetime(2026, 5, 7, 1, 2, 3, tzinfo=timezone.utc)


class FakeHoldingsClient:
    def __init__(
        self,
        *,
        co_holding_rows: list[dict[str, Any]] | None = None,
        northbound_rows: list[dict[str, Any]] | None = None,
    ) -> None:
        self.co_holding_rows = co_holding_rows or []
        self.northbound_rows = northbound_rows or []
        self.read_calls: list[tuple[str, dict[str, Any]]] = []
        self.write_calls: list[tuple[str, dict[str, Any]]] = []

    def execute_read(
        self,
        query: str,
        parameters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        params = parameters or {}
        self.read_calls.append((query, params))
        if "CO_HOLDING" in query:
            return self.co_holding_rows[: int(params.get("scan_limit", len(self.co_holding_rows)))]
        if "NORTHBOUND_HOLD" in query:
            return self.northbound_rows[: int(params.get("scan_limit", len(self.northbound_rows)))]
        return []

    def execute_write(
        self,
        query: str,
        parameters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        self.write_calls.append((query, parameters or {}))
        raise AssertionError("holdings algorithms must not execute writes")


@pytest.mark.parametrize("graph_status", ["rebuilding", "failed"])
def test_co_holding_crowding_blocks_non_ready_before_neo4j_reads(
    graph_status: str,
) -> None:
    client = FakeHoldingsClient(co_holding_rows=[_co_row()])

    with pytest.raises(PermissionError, match="ready"):
        run_co_holding_crowding(
            _context(enabled_channels=["reflexive"]),
            client,  # type: ignore[arg-type]
            status_manager=_status_manager(graph_status=graph_status),
        )

    assert client.read_calls == []
    assert client.write_calls == []


def test_co_holding_crowding_blocks_active_writer_lock_before_neo4j_reads() -> None:
    client = FakeHoldingsClient(co_holding_rows=[_co_row()])

    with pytest.raises(PermissionError, match="writer lock"):
        run_co_holding_crowding(
            _context(enabled_channels=["reflexive"]),
            client,  # type: ignore[arg-type]
            status_manager=_status_manager(writer_lock_token="incremental-sync"),
        )

    assert client.read_calls == []
    assert client.write_calls == []


def test_co_holding_crowding_blocks_generation_mismatch_before_neo4j_reads() -> None:
    client = FakeHoldingsClient(co_holding_rows=[_co_row()])

    with pytest.raises(ValueError, match="graph_generation_id"):
        run_co_holding_crowding(
            _context(enabled_channels=["reflexive"]),
            client,  # type: ignore[arg-type]
            status_manager=_status_manager(graph_generation_id=2),
        )

    assert client.read_calls == []
    assert client.write_calls == []


def test_co_holding_crowding_requires_reflexive_channel_before_neo4j_reads() -> None:
    client = FakeHoldingsClient(co_holding_rows=[_co_row()])

    with pytest.raises(PermissionError, match="reflexive channel"):
        run_co_holding_crowding(
            _context(enabled_channels=["event"]),
            client,  # type: ignore[arg-type]
            status_manager=_status_manager(),
        )

    assert client.read_calls == []
    assert client.write_calls == []


def test_co_holding_crowding_scores_thresholds_and_records_diagnostics() -> None:
    client = FakeHoldingsClient(
        co_holding_rows=[
            _co_row(
                edge_id="edge-a",
                source_node_id="security-a",
                target_node_id="security-crowded",
                co_holding_fund_count=4,
                jaccard_score=1.0,
                evidence_refs=["mart-co-a"],
            ),
            _co_row(
                edge_id="edge-b",
                source_node_id="security-b",
                target_node_id="security-crowded",
                co_holding_fund_count=3,
                jaccard_score=1.0,
                evidence_refs=["mart-co-b"],
            ),
            _co_row(
                edge_id="edge-low-holder",
                target_node_id="security-skipped",
                co_holding_fund_count=1,
                evidence_refs=["mart-low-holder"],
            ),
            _co_row(
                edge_id="edge-no-evidence",
                target_node_id="security-skipped",
                evidence_refs=[],
            ),
            _co_row(
                edge_id="edge-below-score",
                target_node_id="security-below-score",
                co_holding_fund_count=3,
                jaccard_score=0.1,
                evidence_refs=["mart-below-score"],
            ),
        ]
    )

    result = run_co_holding_crowding(
        _context(enabled_channels=["reflexive"]),
        client,  # type: ignore[arg-type]
        status_manager=_status_manager(),
        config=HoldingsAlgorithmConfig(crowding_threshold=0.4),
        result_limit=10,
    )

    assert [path["edge_id"] for path in result.activated_paths] == ["edge-a", "edge-b"]
    assert all(path["channel"] == "reflexive" for path in result.activated_paths)
    assert result.activated_paths[0]["algorithm"] == "co_holding_crowding"
    assert result.activated_paths[0]["crowding_score"] == pytest.approx(0.4)
    assert result.activated_paths[0]["target_holder_count"] == 7
    assert result.activated_paths[0]["evidence_refs"] == ["mart-co-a"]
    assert result.activated_paths[0]["lineage"] == {
        "source_mart": "mart_deriv_fund_co_holding"
    }

    assert len(result.impacted_entities) == 1
    assert result.impacted_entities[0]["node_id"] == "security-crowded"
    assert result.impacted_entities[0]["score"] == pytest.approx(0.4)
    assert result.impacted_entities[0]["holder_count"] == 7

    breakdown = result.channel_breakdown["reflexive"]["co_holding_crowding"]
    assert breakdown["scanned_edge_count"] == 5
    assert breakdown["valid_edge_count"] == 3
    assert breakdown["diagnostics"] == {
        "crowding_score_below_threshold": 1,
        "holder_count_below_minimum": 1,
        "missing_evidence_refs": 1,
    }

    assert client.write_calls == []
    assert _all_queries_read_only(client.read_calls)
    assert "CREATE" not in client.read_calls[0][0]
    assert "MERGE" not in client.read_calls[0][0]


def test_co_holding_crowding_prefers_jaccard_over_default_weight() -> None:
    client = FakeHoldingsClient(
        co_holding_rows=[
            _co_row(
                edge_id="edge-low-jaccard",
                weight=1.0,
                jaccard_score=0.2,
                evidence_refs=["mart-low-jaccard"],
            ),
        ]
    )

    result = run_co_holding_crowding(
        _context(enabled_channels=["reflexive"]),
        client,  # type: ignore[arg-type]
        status_manager=_status_manager(),
        config=HoldingsAlgorithmConfig(crowding_threshold=0.0),
    )

    assert len(result.activated_paths) == 1
    path = result.activated_paths[0]
    assert path["edge_id"] == "edge-low-jaccard"
    assert path["score"] == pytest.approx(0.2)
    assert path["explanation"]["relation_weight"] == pytest.approx(0.2)
    assert path["crowding_score"] == pytest.approx(0.04)


def test_co_holding_crowding_skips_default_weight_when_jaccard_missing() -> None:
    client = FakeHoldingsClient(
        co_holding_rows=[
            _co_row(
                edge_id="edge-default-weight",
                weight=1.0,
                jaccard_score=None,
                evidence_refs=["mart-default-weight"],
            ),
        ]
    )

    result = run_co_holding_crowding(
        _context(enabled_channels=["reflexive"]),
        client,  # type: ignore[arg-type]
        status_manager=_status_manager(),
        config=HoldingsAlgorithmConfig(crowding_threshold=0.0),
    )

    assert result.activated_paths == []
    breakdown = result.channel_breakdown["reflexive"]["co_holding_crowding"]
    assert breakdown["diagnostics"] == {
        "invalid_scoring_field": 1,
        "missing_explicit_weight": 1,
    }


def test_co_holding_crowding_falls_back_to_explicit_properties_weight() -> None:
    client = FakeHoldingsClient(
        co_holding_rows=[
            _co_row(
                edge_id="edge-weight-only",
                weight=1.0,
                jaccard_score=None,
                properties_weight=0.7,
                include_properties_weight=True,
                evidence_refs=["mart-weight-only"],
            ),
        ]
    )

    result = run_co_holding_crowding(
        _context(enabled_channels=["reflexive"]),
        client,  # type: ignore[arg-type]
        status_manager=_status_manager(),
        config=HoldingsAlgorithmConfig(crowding_threshold=0.0),
    )

    assert len(result.activated_paths) == 1
    path = result.activated_paths[0]
    assert path["edge_id"] == "edge-weight-only"
    assert path["score"] == pytest.approx(0.7)
    assert path["explanation"]["relation_weight"] == pytest.approx(0.7)


def test_co_holding_crowding_skips_invalid_explicit_properties_weight() -> None:
    client = FakeHoldingsClient(
        co_holding_rows=[
            _co_row(
                edge_id="edge-invalid-explicit-weight",
                weight=1.0,
                jaccard_score=None,
                properties_weight="not-a-number",
                include_properties_weight=True,
                evidence_refs=["mart-invalid-explicit-weight"],
            ),
        ]
    )

    result = run_co_holding_crowding(
        _context(enabled_channels=["reflexive"]),
        client,  # type: ignore[arg-type]
        status_manager=_status_manager(),
        config=HoldingsAlgorithmConfig(crowding_threshold=0.0),
    )

    assert result.activated_paths == []
    breakdown = result.channel_breakdown["reflexive"]["co_holding_crowding"]
    assert breakdown["diagnostics"] == {
        "invalid_explicit_weight": 1,
        "invalid_scoring_field": 1,
    }


def test_co_holding_crowding_skips_invalid_jaccard_without_fallback() -> None:
    client = FakeHoldingsClient(
        co_holding_rows=[
            _co_row(
                edge_id="edge-invalid-jaccard",
                weight=1.0,
                jaccard_score="not-a-number",
                evidence_refs=["mart-invalid-jaccard"],
            ),
        ]
    )

    result = run_co_holding_crowding(
        _context(enabled_channels=["reflexive"]),
        client,  # type: ignore[arg-type]
        status_manager=_status_manager(),
        config=HoldingsAlgorithmConfig(crowding_threshold=0.0),
    )

    assert result.activated_paths == []
    breakdown = result.channel_breakdown["reflexive"]["co_holding_crowding"]
    assert breakdown["diagnostics"] == {
        "invalid_jaccard_score": 1,
        "invalid_scoring_field": 1,
    }


def test_northbound_anomaly_blocks_generation_mismatch_before_neo4j_reads() -> None:
    client = FakeHoldingsClient(northbound_rows=[_northbound_row()])

    with pytest.raises(ValueError, match="graph_generation_id"):
        run_northbound_anomaly(
            _context(enabled_channels=["event"]),
            client,  # type: ignore[arg-type]
            status_manager=_status_manager(graph_generation_id=2),
        )

    assert client.read_calls == []
    assert client.write_calls == []


def test_northbound_anomaly_scores_direction_and_skips_invalid_rows() -> None:
    client = FakeHoldingsClient(
        northbound_rows=[
            _northbound_row(
                edge_id="edge-inflow",
                target_node_id="security-a",
                metric_z_score=2.4,
                evidence_refs=["mart-nb-inflow"],
            ),
            _northbound_row(
                edge_id="edge-outflow",
                target_node_id="security-b",
                metric_z_score=-2.1,
                evidence_refs=["mart-nb-outflow"],
            ),
            _northbound_row(
                edge_id="edge-low",
                metric_z_score=1.9,
                evidence_refs=["mart-nb-low"],
            ),
            _northbound_row(
                edge_id="edge-missing-z",
                metric_z_score=None,
                northbound_z_score=None,
                z_score=None,
                evidence_refs=["mart-nb-missing-z"],
            ),
            _northbound_row(edge_id="edge-no-evidence", evidence_refs=[]),
        ]
    )

    result = run_northbound_anomaly(
        _context(enabled_channels=["event"]),
        client,  # type: ignore[arg-type]
        status_manager=_status_manager(),
        result_limit=10,
    )

    assert [path["edge_id"] for path in result.activated_paths] == [
        "edge-inflow",
        "edge-outflow",
    ]
    assert result.activated_paths[0]["channel"] == "event"
    assert result.activated_paths[0]["algorithm"] == "northbound_anomaly"
    assert result.activated_paths[0]["direction"] == "inflow"
    assert result.activated_paths[1]["direction"] == "outflow"
    assert result.activated_paths[0]["score"] == pytest.approx(2.4)
    assert result.activated_paths[0]["lookback_observations"] == 8
    assert result.activated_paths[0]["lineage"] == {
        "source_mart": "mart_deriv_northbound_holding_z_score"
    }
    assert [entity["node_id"] for entity in result.impacted_entities] == [
        "security-a",
        "security-b",
    ]

    breakdown = result.channel_breakdown["event"]["northbound_anomaly"]
    assert breakdown["diagnostics"] == {
        "missing_evidence_refs": 1,
        "missing_z_score": 1,
        "z_score_below_threshold": 1,
    }
    assert breakdown["northbound_z_threshold"] == pytest.approx(2.0)
    assert client.write_calls == []
    assert _all_queries_read_only(client.read_calls)


def test_northbound_anomaly_accepts_fallback_z_score_fields() -> None:
    client = FakeHoldingsClient(
        northbound_rows=[
            _northbound_row(
                edge_id="edge-northbound-z",
                metric_z_score=None,
                northbound_z_score=2.2,
                z_score=None,
                evidence_refs=["mart-nb-fallback-1"],
            ),
            _northbound_row(
                edge_id="edge-z-score",
                metric_z_score=None,
                northbound_z_score=None,
                z_score=-2.3,
                evidence_refs=["mart-nb-fallback-2"],
            ),
        ]
    )

    result = run_northbound_anomaly(
        _context(enabled_channels=["event"]),
        client,  # type: ignore[arg-type]
        status_manager=_status_manager(),
        result_limit=10,
    )

    assert [path["z_score"] for path in result.activated_paths] == [-2.3, 2.2]
    assert [path["direction"] for path in result.activated_paths] == ["outflow", "inflow"]


def test_run_holdings_algorithms_merges_explicit_event_and_reflexive_results() -> None:
    client = FakeHoldingsClient(
        co_holding_rows=[
            _co_row(
                edge_id="edge-co-a",
                target_node_id="security-shared",
                jaccard_score=1.0,
                evidence_refs=["mart-co-a"],
            ),
            _co_row(
                edge_id="edge-co-b",
                source_node_id="security-b",
                target_node_id="security-shared",
                jaccard_score=1.0,
                evidence_refs=["mart-co-b"],
            ),
        ],
        northbound_rows=[
            _northbound_row(
                edge_id="edge-nb",
                target_node_id="security-nb",
                metric_z_score=2.5,
                evidence_refs=["mart-nb"],
            ),
        ],
    )

    result = run_holdings_algorithms(
        _context(enabled_channels=["event", "reflexive"]),
        client,  # type: ignore[arg-type]
        status_manager=_status_manager(),
        result_limit=10,
    )

    assert result.channel_breakdown["merged"]["enabled_channels"] == ["event", "reflexive"]
    assert {path["algorithm"] for path in result.activated_paths} == {
        "co_holding_crowding",
        "northbound_anomaly",
    }
    assert {path["relationship_type"] for path in result.activated_paths} == {
        "CO_HOLDING",
        "NORTHBOUND_HOLD",
    }
    assert client.write_calls == []


def test_run_holdings_algorithms_is_not_wired_into_full_propagation() -> None:
    import graph_engine.propagation.pipeline as propagation_pipeline

    assert "run_holdings_algorithms" not in propagation_pipeline.__dict__


def _context(*, enabled_channels: list[str]) -> PropagationContext:
    return PropagationContext(
        cycle_id="cycle-1",
        world_state_ref="world-state-1",
        graph_generation_id=1,
        enabled_channels=enabled_channels,  # type: ignore[arg-type]
        channel_multipliers={channel: 1.0 for channel in enabled_channels},
        regime_multipliers={channel: 1.0 for channel in enabled_channels},
        decay_policy={},
        regime_context={},
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
                node_count=3,
                edge_count=2,
                key_label_counts={"Entity": 3},
                checksum="abc123" if graph_status == "ready" else graph_status,
                last_verified_at=NOW if graph_status == "ready" else None,
                last_reload_at=None,
                writer_lock_token=writer_lock_token,
            ),
        ),
    )


def _co_row(
    *,
    edge_id: str = "edge-co",
    source_node_id: str = "security-a",
    source_entity_id: str = "entity-security-a",
    target_node_id: str = "security-b",
    target_entity_id: str = "entity-security-b",
    co_holding_fund_count: int | None = 3,
    security_left_fund_count: int = 10,
    security_right_fund_count: int = 9,
    weight: float | None = None,
    jaccard_score: Any = 1.0,
    properties_weight: Any = None,
    include_properties_weight: bool = False,
    evidence_refs: list[str] | None = None,
) -> dict[str, Any]:
    properties: dict[str, Any] = {
        "lineage": {"source_mart": "mart_deriv_fund_co_holding"},
    }
    if include_properties_weight:
        properties["weight"] = properties_weight

    return {
        "source_node_id": source_node_id,
        "source_entity_id": source_entity_id,
        "source_labels": ["Entity"],
        "target_node_id": target_node_id,
        "target_entity_id": target_entity_id,
        "target_labels": ["Entity"],
        "edge_id": edge_id,
        "relationship_type": "CO_HOLDING",
        "evidence_refs": [f"fact-{edge_id}"] if evidence_refs is None else evidence_refs,
        "evidence_ref": None,
        "properties_json": json.dumps(properties, sort_keys=True),
        "weight": weight,
        "evidence_confidence": 1.0,
        "recency_decay": 1.0,
        "co_holding_fund_count": co_holding_fund_count,
        "security_left_fund_count": security_left_fund_count,
        "security_right_fund_count": security_right_fund_count,
        "jaccard_score": jaccard_score,
        "report_date": "2026-03-31",
        "latest_announced_date": "2026-04-30",
        "source_canonical_id_rule_version": "entity-registry/v1",
        "target_canonical_id_rule_version": "entity-registry/v1",
    }


def _northbound_row(
    *,
    edge_id: str = "edge-nb",
    source_node_id: str = "northbound-holder",
    source_entity_id: str = "entity-northbound-holder",
    target_node_id: str = "security-a",
    target_entity_id: str = "entity-security-a",
    metric_z_score: float | None = 2.4,
    northbound_z_score: float | None = None,
    z_score: float | None = None,
    evidence_refs: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "source_node_id": source_node_id,
        "source_entity_id": source_entity_id,
        "source_labels": ["Entity"],
        "target_node_id": target_node_id,
        "target_entity_id": target_entity_id,
        "target_labels": ["Entity"],
        "edge_id": edge_id,
        "relationship_type": "NORTHBOUND_HOLD",
        "evidence_refs": [f"fact-{edge_id}"] if evidence_refs is None else evidence_refs,
        "evidence_ref": None,
        "properties_json": json.dumps(
            {"lineage": {"source_mart": "mart_deriv_northbound_holding_z_score"}},
            sort_keys=True,
        ),
        "weight": None,
        "evidence_confidence": 1.0,
        "recency_decay": 1.0,
        "metric_z_score": metric_z_score,
        "northbound_z_score": northbound_z_score,
        "z_score": z_score,
        "z_score_metric": "holding_ratio",
        "lookback_observations": 8,
        "window_start_date": "2025-12-31",
        "window_end_date": "2026-03-31",
        "observation_count": 63,
        "metric_value": 0.018,
        "metric_mean": 0.011,
        "metric_stddev": 0.0029,
        "report_date": "2026-03-31",
        "source_canonical_id_rule_version": "entity-registry/v1",
        "target_canonical_id_rule_version": "entity-registry/v1",
    }


def _all_queries_read_only(read_calls: list[tuple[str, dict[str, Any]]]) -> bool:
    forbidden_tokens = ("CREATE", "MERGE", " SET ", "DELETE")
    return all(
        not any(token in query for token in forbidden_tokens)
        for query, _ in read_calls
    )
