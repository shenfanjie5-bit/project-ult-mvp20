"""File-backed canonical artifact reader for cold reload."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from pydantic import ValidationError

from graph_engine.models import (
    ColdReloadPlan,
    GraphAssertionRecord,
    GraphEdgeRecord,
    GraphNodeRecord,
    GraphSnapshot,
)
from graph_engine.reload.service import metrics_snapshot_from_graph_snapshot

_COLD_RELOAD_PLAN_KEYS = {
    "snapshot_ref",
    "cycle_id",
    "expected_snapshot",
    "node_records",
    "edge_records",
    "assertion_records",
    "projection_name",
    "created_at",
}
_GRAPH_SNAPSHOT_KEYS = {
    "graph_snapshot_id",
    "cycle_id",
    "version",
    "created_at",
    "node_count",
    "edge_count",
    "nodes",
    "edges",
}
_RESERVED_NODE_PROPERTIES = {
    "node_id",
    "canonical_entity_id",
    "label",
    "properties_json",
    "created_at",
    "updated_at",
}
_RESERVED_EDGE_PROPERTIES = {
    "edge_id",
    "source_node_id",
    "target_node_id",
    "relationship_type",
    "weight",
    "properties_json",
    "created_at",
    "updated_at",
}
_DIRECTORY_CANDIDATES = (
    "cold_reload_plan.json",
    "graph_reload_plan.json",
    "reload_plan.json",
    "graph_snapshot.json",
    "snapshot.json",
    "latest.json",
)


class CanonicalArtifactError(ValueError):
    """Raised when a persisted canonical artifact cannot form a reload plan."""


class CanonicalArtifactNotFound(FileNotFoundError):
    """Raised when a snapshot reference does not resolve to an artifact path."""


class ArtifactCanonicalReader:
    """Read cold-reload plans from persisted Layer A/formal-readable files.

    Supported JSON shapes are:
    - a direct ``ColdReloadPlan`` payload
    - an envelope containing ``cold_reload_plan`` or ``payload``
    - a graph snapshot bundle with ``graph_snapshot`` plus optional
      ``node_records`` / ``edge_records`` / ``assertion_records``
    - a direct live-metric-shaped ``GraphSnapshot`` payload
    """

    def __init__(
        self,
        artifact_root: str | Path | None = None,
        *,
        default_projection_name: str = "graph_engine_reload",
    ) -> None:
        self.artifact_root = Path(artifact_root) if artifact_root is not None else None
        self.default_projection_name = default_projection_name

    def read_cold_reload_plan(self, snapshot_ref: str) -> ColdReloadPlan:
        artifact_path = self._resolve_artifact_path(snapshot_ref)
        payload = self._read_json_artifact(artifact_path)
        return self._plan_from_payload(
            payload,
            snapshot_ref=snapshot_ref,
            artifact_path=artifact_path,
        )

    def _resolve_artifact_path(self, snapshot_ref: str) -> Path:
        parsed = urlparse(snapshot_ref)
        if parsed.scheme == "file":
            candidate = Path(unquote(parsed.path))
        elif parsed.scheme == "artifact":
            if self.artifact_root is None:
                raise CanonicalArtifactNotFound(
                    f"artifact URI requires artifact_root: {snapshot_ref}",
                )
            candidate = self.artifact_root / parsed.netloc / unquote(parsed.path).lstrip("/")
        else:
            candidate = Path(snapshot_ref)
            if not candidate.is_absolute() and self.artifact_root is not None:
                candidate = self.artifact_root / candidate

        resolved = self._resolve_existing_path(candidate)
        if resolved is None:
            raise CanonicalArtifactNotFound(f"canonical artifact not found: {candidate}")
        return resolved

    def _resolve_existing_path(self, candidate: Path) -> Path | None:
        if candidate.is_file():
            return candidate
        if candidate.is_dir():
            for file_name in _DIRECTORY_CANDIDATES:
                nested = candidate / file_name
                if nested.is_file():
                    return nested
            json_files = sorted(path for path in candidate.iterdir() if path.suffix == ".json")
            if len(json_files) == 1:
                return json_files[0]
            return None
        if candidate.suffix == "":
            json_candidate = candidate.with_suffix(".json")
            if json_candidate.is_file():
                return json_candidate
        return None

    def _read_json_artifact(self, artifact_path: Path) -> Any:
        try:
            with artifact_path.open("r", encoding="utf-8") as artifact_file:
                return json.load(artifact_file)
        except json.JSONDecodeError as exc:
            raise CanonicalArtifactError(
                f"canonical artifact is not valid JSON: {artifact_path}",
            ) from exc
        except OSError as exc:
            raise CanonicalArtifactNotFound(
                f"canonical artifact cannot be read: {artifact_path}",
            ) from exc

    def _plan_from_payload(
        self,
        payload: Any,
        *,
        snapshot_ref: str,
        artifact_path: Path,
    ) -> ColdReloadPlan:
        normalized = _unwrap_formal_payload(payload)
        if not isinstance(normalized, Mapping):
            raise CanonicalArtifactError(
                f"canonical artifact must contain a JSON object: {artifact_path}",
            )

        plan_payload = _mapping_value(normalized, "cold_reload_plan", "reload_plan")
        if plan_payload is not None:
            return _validate_plan(plan_payload, artifact_path)

        if _COLD_RELOAD_PLAN_KEYS <= set(normalized):
            return _validate_plan(normalized, artifact_path)

        graph_snapshot_payload = _mapping_value(normalized, "graph_snapshot", "snapshot")
        graph_snapshot = (
            _validate_graph_snapshot(graph_snapshot_payload, artifact_path)
            if graph_snapshot_payload is not None
            else None
        )
        if graph_snapshot is None and _GRAPH_SNAPSHOT_KEYS <= set(normalized):
            graph_snapshot = _validate_graph_snapshot(normalized, artifact_path)

        if graph_snapshot is None:
            raise CanonicalArtifactError(
                "canonical artifact must contain cold_reload_plan or graph_snapshot: "
                f"{artifact_path}",
            )

        graph_generation_id = _graph_generation_id(normalized, graph_snapshot, artifact_path)
        try:
            expected_snapshot = metrics_snapshot_from_graph_snapshot(
                graph_snapshot,
                graph_generation_id=graph_generation_id,
            )
        except ValueError as exc:
            raise CanonicalArtifactError(
                f"graph snapshot artifact is not cold-reload readable: {artifact_path}",
            ) from exc
        node_records = _node_records(normalized, graph_snapshot, artifact_path)
        edge_records = _edge_records(normalized, graph_snapshot, artifact_path)
        assertion_records = _assertion_records(normalized, artifact_path)
        _validate_record_counts(
            expected_snapshot,
            node_records=node_records,
            edge_records=edge_records,
            assertion_records=assertion_records,
            artifact_path=artifact_path,
        )
        return ColdReloadPlan(
            snapshot_ref=snapshot_ref,
            cycle_id=str(normalized.get("cycle_id") or graph_snapshot.cycle_id),
            expected_snapshot=expected_snapshot,
            node_records=node_records,
            edge_records=edge_records,
            assertion_records=assertion_records,
            projection_name=str(normalized.get("projection_name") or self.default_projection_name),
            created_at=normalized.get("created_at") or graph_snapshot.created_at,
        )


def _unwrap_formal_payload(payload: Any) -> Any:
    if not isinstance(payload, Mapping):
        return payload
    payload_json = payload.get("payload_json")
    if isinstance(payload_json, str):
        try:
            return _unwrap_formal_payload(json.loads(payload_json))
        except json.JSONDecodeError as exc:
            raise CanonicalArtifactError("formal payload_json is not valid JSON") from exc
    nested_payload = payload.get("payload")
    if isinstance(nested_payload, Mapping):
        return _unwrap_formal_payload(nested_payload)
    return payload


def _mapping_value(payload: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in payload:
            return payload[key]
    return None


def _validate_plan(payload: Any, artifact_path: Path) -> ColdReloadPlan:
    try:
        plan = ColdReloadPlan.model_validate(payload)
    except ValidationError as exc:
        raise CanonicalArtifactError(
            f"cold reload plan artifact is invalid: {artifact_path}",
        ) from exc
    _validate_record_counts(
        plan.expected_snapshot,
        node_records=plan.node_records,
        edge_records=plan.edge_records,
        assertion_records=plan.assertion_records,
        artifact_path=artifact_path,
    )
    return plan


def _validate_graph_snapshot(payload: Any, artifact_path: Path) -> GraphSnapshot:
    try:
        return GraphSnapshot.model_validate(payload)
    except ValidationError as exc:
        raise CanonicalArtifactError(
            f"graph snapshot artifact is invalid: {artifact_path}",
        ) from exc


def _graph_generation_id(
    payload: Mapping[str, Any],
    graph_snapshot: GraphSnapshot,
    artifact_path: Path,
) -> int:
    raw_generation_id = payload.get("graph_generation_id")
    if raw_generation_id is None:
        raw_generation_id = _generation_id_from_snapshot_id(graph_snapshot.graph_snapshot_id)
    if raw_generation_id is None:
        raise CanonicalArtifactError(
            "graph snapshot artifact requires graph_generation_id when the "
            f"snapshot id does not encode it: {artifact_path}",
        )
    try:
        generation_id = int(raw_generation_id)
    except (TypeError, ValueError) as exc:
        raise CanonicalArtifactError(
            f"graph_generation_id is invalid in artifact: {artifact_path}",
        ) from exc
    if generation_id < 0:
        raise CanonicalArtifactError(
            f"graph_generation_id cannot be negative in artifact: {artifact_path}",
        )
    return generation_id


def _generation_id_from_snapshot_id(snapshot_id: str) -> int | None:
    parts = snapshot_id.split("-")
    if len(parts) < 4 or parts[0:2] != ["graph", "snapshot"]:
        return None
    generation_part = parts[-2]
    if generation_part.isdecimal():
        return int(generation_part)
    return None


def _node_records(
    payload: Mapping[str, Any],
    graph_snapshot: GraphSnapshot,
    artifact_path: Path,
) -> list[GraphNodeRecord]:
    raw_records = payload.get("node_records")
    if raw_records is not None:
        return _validate_record_list(raw_records, GraphNodeRecord, "node_records", artifact_path)

    records: list[GraphNodeRecord] = []
    for node in graph_snapshot.nodes:
        properties = dict(node.properties)
        labels = sorted(str(label) for label in node.labels)
        if len(labels) != 1:
            raise CanonicalArtifactError(
                "graph snapshot cold reload requires single-label nodes; "
                f"node {node.node_id!r} in {artifact_path} has labels {labels!r}",
            )
        canonical_entity_id = (
            node.entity.entity_id if node.entity is not None else properties.get("canonical_entity_id")
        )
        if canonical_entity_id is None or str(canonical_entity_id) == "":
            raise CanonicalArtifactError(
                "graph snapshot cold reload requires canonical_entity_id; "
                f"node {node.node_id!r} in {artifact_path} is missing one",
            )
        try:
            records.append(
                GraphNodeRecord.model_validate(
                    {
                        "node_id": node.node_id,
                        "canonical_entity_id": str(canonical_entity_id),
                        "label": labels[0],
                        "properties": _canonical_properties(
                            properties,
                            reserved_keys=_RESERVED_NODE_PROPERTIES,
                            artifact_path=artifact_path,
                        ),
                        "created_at": properties.get("created_at"),
                        "updated_at": properties.get("updated_at"),
                    },
                ),
            )
        except ValidationError as exc:
            raise CanonicalArtifactError(
                f"graph snapshot node cannot form GraphNodeRecord: {artifact_path}",
            ) from exc
    return records


def _edge_records(
    payload: Mapping[str, Any],
    graph_snapshot: GraphSnapshot,
    artifact_path: Path,
) -> list[GraphEdgeRecord]:
    raw_records = payload.get("edge_records")
    if raw_records is not None:
        return _validate_record_list(raw_records, GraphEdgeRecord, "edge_records", artifact_path)

    records: list[GraphEdgeRecord] = []
    for edge in graph_snapshot.edges:
        properties = dict(edge.properties)
        try:
            records.append(
                GraphEdgeRecord.model_validate(
                    {
                        "edge_id": edge.edge_id,
                        "source_node_id": edge.source_node,
                        "target_node_id": edge.target_node,
                        "relationship_type": edge.relation_type,
                        "properties": _canonical_properties(
                            properties,
                            reserved_keys=_RESERVED_EDGE_PROPERTIES,
                            artifact_path=artifact_path,
                        ),
                        "weight": properties.get("weight", 1.0),
                        "created_at": properties.get("created_at"),
                        "updated_at": properties.get("updated_at"),
                    },
                ),
            )
        except ValidationError as exc:
            raise CanonicalArtifactError(
                f"graph snapshot edge cannot form GraphEdgeRecord: {artifact_path}",
            ) from exc
    return records


def _assertion_records(
    payload: Mapping[str, Any],
    artifact_path: Path,
) -> list[GraphAssertionRecord]:
    raw_records = payload.get("assertion_records", [])
    return _validate_record_list(raw_records, GraphAssertionRecord, "assertion_records", artifact_path)


def _validate_record_counts(
    expected_snapshot: Any,
    *,
    node_records: list[GraphNodeRecord],
    edge_records: list[GraphEdgeRecord],
    assertion_records: list[GraphAssertionRecord],
    artifact_path: Path,
) -> None:
    reload_node_count = len(node_records) + len(assertion_records)
    if reload_node_count != expected_snapshot.node_count:
        raise CanonicalArtifactError(
            "canonical artifact record counts disagree with graph snapshot: "
            f"node_records + assertion_records={reload_node_count}, "
            f"snapshot.node_count={expected_snapshot.node_count} in {artifact_path}",
        )
    if len(edge_records) != expected_snapshot.edge_count:
        raise CanonicalArtifactError(
            "canonical artifact record counts disagree with graph snapshot: "
            f"edge_records={len(edge_records)}, "
            f"snapshot.edge_count={expected_snapshot.edge_count} in {artifact_path}",
        )


def _validate_record_list(
    raw_records: Any,
    model: type[GraphNodeRecord] | type[GraphEdgeRecord] | type[GraphAssertionRecord],
    field_name: str,
    artifact_path: Path,
) -> Any:
    if not isinstance(raw_records, list):
        raise CanonicalArtifactError(
            f"{field_name} must be a list in canonical artifact: {artifact_path}",
        )
    try:
        return [model.model_validate(record) for record in raw_records]
    except ValidationError as exc:
        raise CanonicalArtifactError(
            f"{field_name} is invalid in canonical artifact: {artifact_path}",
        ) from exc


def _canonical_properties(
    live_properties: Mapping[str, Any],
    *,
    reserved_keys: set[str],
    artifact_path: Path,
) -> dict[str, Any]:
    properties_json = live_properties.get("properties_json")
    if isinstance(properties_json, str):
        try:
            decoded = json.loads(properties_json)
        except json.JSONDecodeError as exc:
            raise CanonicalArtifactError(
                f"properties_json is invalid in canonical artifact: {artifact_path}",
            ) from exc
        if not isinstance(decoded, dict):
            raise CanonicalArtifactError(
                f"properties_json must decode to an object in artifact: {artifact_path}",
            )
        return decoded
    return {
        str(key): value
        for key, value in live_properties.items()
        if str(key) not in reserved_keys
    }
