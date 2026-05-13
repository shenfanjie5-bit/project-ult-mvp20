"""Opt-in live graph canary runner and cold-reload replay evidence."""

from __future__ import annotations

import json
import os
import re
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from contracts.schemas import CandidateGraphDelta

from graph_engine.models import (
    ColdReloadPlan,
    Neo4jGraphStatus,
    PropagationContext,
    PropagationResult,
    PromotionPlan,
)
from graph_engine.promotion.interfaces import EntityAnchorReader
from graph_engine.promotion.service import promote_graph_deltas
from graph_engine.propagation.holdings import (
    HoldingsAlgorithmConfig,
    run_co_holding_crowding,
    run_northbound_anomaly,
)
from graph_engine.reload.interfaces import CanonicalReader
from graph_engine.rollout.evidence import (
    EvidenceWriter,
    redact_evidence_payload,
    safe_reload_ref_label,
)
from graph_engine.rollout.guard import (
    LiveGraphRolloutConfig,
    validate_candidate_relationship_allowlist,
    validate_client_database_matches_config,
    validate_promotion_plan_relationship_allowlist,
    validate_rollout_config,
)
from graph_engine.status import GraphStatusManager

_SAFE_FILE_COMPONENT_PATTERN = re.compile(r"[^A-Za-z0-9_.-]+")


@dataclass(frozen=True)
class LoadedCandidateDeltaReader:
    """CandidateDeltaReader for preselected rollout candidates."""

    deltas: Sequence[CandidateGraphDelta]
    allowed_relationship_types: set[str]

    def read_candidate_graph_deltas(
        self,
        cycle_id: str,
        selection_ref: str,
    ) -> list[CandidateGraphDelta]:
        del cycle_id, selection_ref
        validate_candidate_relationship_allowlist(
            self.deltas,
            self.allowed_relationship_types,
        )
        return list(self.deltas)


@dataclass(frozen=True)
class LayerAArtifactSummary:
    """Summary of the Layer A artifact created before Neo4j sync."""

    manifest_ref: str
    records_ref: str
    cycle_id: str
    selection_ref: str
    delta_count: int
    node_count: int
    edge_count: int
    assertion_count: int
    relation_counts: dict[str, int]


@dataclass(frozen=True)
class EdgeReadbackSummary:
    """Read-only verification summary for canary edges."""

    expected_edge_count: int
    edge_count: int
    relation_counts: dict[str, int]
    missing_edge_ids: list[str]
    disallowed_relation_types: list[str]


@dataclass(frozen=True)
class HoldingsAlgorithmCanarySummary:
    """Summary from explicit holdings algorithms used by the canary."""

    cycle_id: str
    graph_generation_id: int
    co_holding_path_count: int
    northbound_path_count: int
    total_path_count: int
    impacted_entity_count: int
    co_holding_diagnostics: dict[str, int]
    northbound_diagnostics: dict[str, int]


@dataclass(frozen=True)
class LiveGraphCanarySummary:
    """Canary runner result with evidence manifest location."""

    namespace: str
    mode: str
    neo4j_database: str
    cycle_id: str
    selection_ref: str
    layer_a_artifact: LayerAArtifactSummary
    edge_readback: EdgeReadbackSummary
    algorithm_summary: HoldingsAlgorithmCanarySummary
    evidence_manifest_path: Path


class LayerAArtifactCanonicalWriter:
    """CanonicalWriter that persists a compact Layer A artifact for canary evidence."""

    def __init__(self, artifact_root: str | Path, *, namespace: str) -> None:
        self.artifact_root = Path(artifact_root).expanduser().resolve(strict=False)
        self.namespace = _safe_file_component(namespace)
        self.last_summary: LayerAArtifactSummary | None = None

    def write_canonical_records(self, plan: PromotionPlan) -> None:
        artifact_dir = (
            self.artifact_root
            / self.namespace
            / "layer_a"
            / _safe_file_component(plan.cycle_id)
            / _safe_file_component(plan.selection_ref)
        )
        artifact_dir.mkdir(parents=True, exist_ok=True)
        records_path = artifact_dir / "canonical_records.jsonl"
        manifest_path = artifact_dir / "manifest.json"

        relation_counts = _relation_counts(plan)
        _atomic_write_text(
            records_path,
            "\n".join(_canonical_record_lines(plan)) + "\n",
        )
        _atomic_write_json(
            manifest_path,
            {
                "artifact_type": "live_graph_rollout_layer_a",
                "layer": "Layer A",
                "namespace": self.namespace,
                "cycle_id": plan.cycle_id,
                "selection_ref": plan.selection_ref,
                "records_ref": "canonical_records.jsonl",
                "delta_count": len(plan.delta_ids),
                "node_count": len(plan.node_records),
                "edge_count": len(plan.edge_records),
                "assertion_count": len(plan.assertion_records),
                "relation_counts": relation_counts,
                "relation_types": sorted(relation_counts),
                "delta_ids": sorted(plan.delta_ids),
                "created_at": plan.created_at,
            },
        )
        self.last_summary = LayerAArtifactSummary(
            manifest_ref=_relative_ref(manifest_path, self.artifact_root),
            records_ref=_relative_ref(records_path, self.artifact_root),
            cycle_id=plan.cycle_id,
            selection_ref=plan.selection_ref,
            delta_count=len(plan.delta_ids),
            node_count=len(plan.node_records),
            edge_count=len(plan.edge_records),
            assertion_count=len(plan.assertion_records),
            relation_counts=relation_counts,
        )


def run_live_graph_canary(
    *,
    cycle_id: str,
    selection_ref: str,
    candidate_deltas: Sequence[CandidateGraphDelta],
    entity_reader: EntityAnchorReader,
    client: Any,
    status_manager: GraphStatusManager,
    config: LiveGraphRolloutConfig,
    env: Mapping[str, str | None] | None = None,
    algorithm_config: HoldingsAlgorithmConfig | None = None,
    result_limit: int = 100,
    readback_hook: Callable[[Any, PromotionPlan, set[str]], EdgeReadbackSummary] | None = None,
    evidence_writer: EvidenceWriter | None = None,
) -> LiveGraphCanarySummary:
    """Run the guarded holdings canary; this is not part of the default pipeline."""

    guarded_config = validate_rollout_config(config, env=env)
    if guarded_config.mode != "canary":
        raise PermissionError("live graph canary runner requires mode='canary'")
    validate_client_database_matches_config(client, guarded_config)
    validate_candidate_relationship_allowlist(
        candidate_deltas,
        guarded_config.allowed_relationship_types,
    )
    pre_status = status_manager.require_ready()

    canonical_writer = LayerAArtifactCanonicalWriter(
        guarded_config.artifact_root,
        namespace=guarded_config.namespace,
    )
    plan = promote_graph_deltas(
        cycle_id,
        selection_ref,
        candidate_reader=LoadedCandidateDeltaReader(
            candidate_deltas,
            guarded_config.allowed_relationship_types,
        ),
        entity_reader=entity_reader,
        canonical_writer=canonical_writer,
        client=client,
        status_manager=status_manager,
        sync_to_live_graph=True,
        allowed_relationship_types=guarded_config.allowed_relationship_types,
    )
    validate_promotion_plan_relationship_allowlist(
        plan,
        guarded_config.allowed_relationship_types,
    )
    if canonical_writer.last_summary is None:
        raise RuntimeError("Layer A artifact writer did not record a summary")

    edge_readback = (
        readback_hook(client, plan, guarded_config.allowed_relationship_types)
        if readback_hook is not None
        else readback_canary_edges(
            client,
            plan=plan,
            allowed_relationship_types=guarded_config.allowed_relationship_types,
        )
    )
    post_status = status_manager.require_ready()
    algorithm_summary = run_holdings_canary_algorithms(
        build_holdings_canary_context(
            cycle_id=cycle_id,
            graph_generation_id=post_status.graph_generation_id,
            namespace=guarded_config.namespace,
        ),
        client,
        status_manager=status_manager,
        config=algorithm_config,
        result_limit=result_limit,
    )

    writer = evidence_writer or EvidenceWriter(
        guarded_config.artifact_root,
        namespace=guarded_config.namespace,
    )
    manifest_path = writer.write_manifest(
        "live_graph_canary_evidence",
        {
            "artifact_type": "live_graph_canary_evidence",
            "namespace": guarded_config.namespace,
            "mode": guarded_config.mode,
            "neo4j_database_label": guarded_config.neo4j_database,
            "allowed_relationship_types": guarded_config.allowed_relationship_types,
            "cycle_id": cycle_id,
            "selection_ref": selection_ref,
            "relation_counts": canonical_writer.last_summary.relation_counts,
            "pre_status": _status_summary(pre_status),
            "post_status": _status_summary(post_status),
            "reload_ref": None,
            "layer_a_artifact": canonical_writer.last_summary.__dict__,
            "edge_readback": edge_readback.__dict__,
            "holdings_algorithms": algorithm_summary.__dict__,
        },
    )

    return LiveGraphCanarySummary(
        namespace=guarded_config.namespace,
        mode=guarded_config.mode,
        neo4j_database=guarded_config.neo4j_database,
        cycle_id=cycle_id,
        selection_ref=selection_ref,
        layer_a_artifact=canonical_writer.last_summary,
        edge_readback=edge_readback,
        algorithm_summary=algorithm_summary,
        evidence_manifest_path=manifest_path,
    )


def readback_canary_edges(
    client: Any,
    *,
    plan: PromotionPlan,
    allowed_relationship_types: set[str],
    strict: bool = True,
) -> EdgeReadbackSummary:
    """Verify synced canary edges through a read-only query."""

    expected_edge_ids = sorted({edge.edge_id for edge in plan.edge_records})
    if not expected_edge_ids:
        raise ValueError("canary readback requires at least one edge")

    rows = client.execute_read(
        """
MATCH ()-[relationship]->()
WHERE relationship.edge_id IN $edge_ids
RETURN relationship.edge_id AS edge_id,
       type(relationship) AS relationship_type
ORDER BY edge_id ASC
""",
        {"edge_ids": expected_edge_ids},
    )
    seen_edge_ids = sorted(
        str(row.get("edge_id")) for row in rows if row.get("edge_id") is not None
    )
    relation_counts = dict(
        sorted(Counter(str(row.get("relationship_type")) for row in rows).items())
    )
    missing_edge_ids = sorted(set(expected_edge_ids) - set(seen_edge_ids))
    disallowed_relation_types = sorted(
        relation_type
        for relation_type in relation_counts
        if relation_type not in allowed_relationship_types
    )
    summary = EdgeReadbackSummary(
        expected_edge_count=len(expected_edge_ids),
        edge_count=len(seen_edge_ids),
        relation_counts=relation_counts,
        missing_edge_ids=missing_edge_ids,
        disallowed_relation_types=disallowed_relation_types,
    )
    if strict:
        if missing_edge_ids:
            raise ValueError(f"missing synced canary edges: {missing_edge_ids}")
        if disallowed_relation_types:
            raise ValueError(
                "unexpected canary relationship types: "
                + ", ".join(disallowed_relation_types),
            )
    return summary


def build_holdings_canary_context(
    *,
    cycle_id: str,
    graph_generation_id: int,
    namespace: str,
    world_state_ref: str | None = None,
) -> PropagationContext:
    """Build the context for explicit holdings algorithms in the canary."""

    safe_namespace = _safe_file_component(namespace)
    return PropagationContext(
        cycle_id=cycle_id,
        world_state_ref=world_state_ref or f"live-graph-canary:{safe_namespace}",
        graph_generation_id=graph_generation_id,
        enabled_channels=["event", "reflexive"],
        channel_multipliers={"event": 1.0, "reflexive": 1.0},
        regime_multipliers={"event": 1.0, "reflexive": 1.0},
        decay_policy={},
        regime_context={"rollout_namespace": safe_namespace},
    )


def run_holdings_canary_algorithms(
    context: PropagationContext,
    client: Any,
    *,
    status_manager: GraphStatusManager,
    config: HoldingsAlgorithmConfig | None = None,
    result_limit: int = 100,
) -> HoldingsAlgorithmCanarySummary:
    """Run only explicit holdings algorithms; no full propagation pipeline."""

    if "event" not in context.enabled_channels or "reflexive" not in context.enabled_channels:
        raise PermissionError("holdings canary requires event and reflexive channels")
    co_holding = run_co_holding_crowding(
        context,
        client,
        status_manager=status_manager,
        config=config,
        result_limit=result_limit,
    )
    northbound = run_northbound_anomaly(
        context,
        client,
        status_manager=status_manager,
        config=config,
        result_limit=result_limit,
    )
    return HoldingsAlgorithmCanarySummary(
        cycle_id=context.cycle_id,
        graph_generation_id=context.graph_generation_id,
        co_holding_path_count=len(co_holding.activated_paths),
        northbound_path_count=len(northbound.activated_paths),
        total_path_count=len(co_holding.activated_paths) + len(northbound.activated_paths),
        impacted_entity_count=_merged_impacted_entity_count(co_holding, northbound),
        co_holding_diagnostics=_co_holding_diagnostics(co_holding),
        northbound_diagnostics=_northbound_diagnostics(northbound),
    )


def write_cold_reload_replay_evidence(
    *,
    snapshot_ref: str,
    canonical_reader: CanonicalReader,
    config: LiveGraphRolloutConfig,
    env: Mapping[str, str | None] | None = None,
    evidence_writer: EvidenceWriter | None = None,
) -> Path:
    """Prove the cold-reload artifact can be read without running destructive reload."""

    guarded_config = validate_rollout_config(config, env=env)
    plan = canonical_reader.read_cold_reload_plan(snapshot_ref)
    validate_promotion_plan_relationship_allowlist(
        _promotion_plan_from_reload_plan(plan),
        guarded_config.allowed_relationship_types,
    )
    writer = evidence_writer or EvidenceWriter(
        guarded_config.artifact_root,
        namespace=guarded_config.namespace,
    )
    return writer.write_manifest(
        "cold_reload_replay_evidence",
        {
            "artifact_type": "cold_reload_replay_evidence",
            "namespace": guarded_config.namespace,
            "mode": guarded_config.mode,
            "neo4j_database_label": guarded_config.neo4j_database,
            "reload_ref": safe_reload_ref_label(snapshot_ref),
            "cycle_id": plan.cycle_id,
            "projection_name": plan.projection_name,
            "node_count": len(plan.node_records),
            "edge_count": len(plan.edge_records),
            "assertion_count": len(plan.assertion_records),
            "relation_counts": dict(
                sorted(Counter(edge.relationship_type for edge in plan.edge_records).items())
            ),
            "expected_snapshot": plan.expected_snapshot.model_dump(mode="json"),
            "destructive_reload_executed": False,
        },
    )


def _promotion_plan_from_reload_plan(plan: ColdReloadPlan) -> PromotionPlan:
    return PromotionPlan(
        cycle_id=plan.cycle_id,
        selection_ref=f"cold-reload:{plan.snapshot_ref}",
        delta_ids=[],
        node_records=plan.node_records,
        edge_records=plan.edge_records,
        assertion_records=plan.assertion_records,
        created_at=plan.created_at,
    )


def _canonical_record_lines(plan: PromotionPlan) -> list[str]:
    records: list[dict[str, Any]] = []
    for node in plan.node_records:
        records.append({"record_type": "node", "record": node.model_dump(mode="json")})
    for edge in plan.edge_records:
        records.append({"record_type": "edge", "record": edge.model_dump(mode="json")})
    for assertion in plan.assertion_records:
        records.append(
            {"record_type": "assertion", "record": assertion.model_dump(mode="json")}
        )
    return [
        json.dumps(redact_evidence_payload(record), sort_keys=True, separators=(",", ":"))
        for record in records
    ]


def _relation_counts(plan: PromotionPlan) -> dict[str, int]:
    return dict(sorted(Counter(edge.relationship_type for edge in plan.edge_records).items()))


def _status_summary(status: Neo4jGraphStatus) -> dict[str, Any]:
    return {
        "graph_status": status.graph_status,
        "graph_generation_id": status.graph_generation_id,
        "node_count": status.node_count,
        "edge_count": status.edge_count,
        "key_label_counts": dict(status.key_label_counts),
        "checksum": status.checksum,
        "last_verified_at": status.last_verified_at,
        "last_reload_at": status.last_reload_at,
        "writer_lock_token": status.writer_lock_token,
    }


def _co_holding_diagnostics(result: PropagationResult) -> dict[str, int]:
    breakdown = result.channel_breakdown.get("reflexive", {}).get("co_holding_crowding", {})
    return _int_diagnostics(breakdown.get("diagnostics"))


def _northbound_diagnostics(result: PropagationResult) -> dict[str, int]:
    breakdown = result.channel_breakdown.get("event", {}).get("northbound_anomaly", {})
    return _int_diagnostics(breakdown.get("diagnostics"))


def _int_diagnostics(value: Any) -> dict[str, int]:
    if not isinstance(value, Mapping):
        return {}
    return {
        str(key): int(count)
        for key, count in value.items()
        if isinstance(count, int | float)
    }


def _merged_impacted_entity_count(*results: PropagationResult) -> int:
    entity_ids: set[str] = set()
    for result in results:
        for entity in result.impacted_entities:
            node_id = entity.get("node_id")
            if node_id is not None:
                entity_ids.add(str(node_id))
    return len(entity_ids)


def _relative_ref(path: Path, artifact_root: Path) -> str:
    try:
        return str(path.relative_to(artifact_root))
    except ValueError:
        return path.name


def _safe_file_component(value: str) -> str:
    sanitized = _SAFE_FILE_COMPONENT_PATTERN.sub("-", value.strip()).strip(".-")
    if not sanitized:
        raise ValueError("file component must not be empty after sanitization")
    return sanitized[:120]


def _atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    _atomic_write_text(
        path,
        json.dumps(
            redact_evidence_payload(payload),
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n",
    )


def _atomic_write_text(path: Path, text: str) -> None:
    tmp_path = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp_path.write_text(text, encoding="utf-8")
    tmp_path.replace(path)
