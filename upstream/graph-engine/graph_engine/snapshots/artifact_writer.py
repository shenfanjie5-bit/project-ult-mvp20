"""Formal-readable graph snapshot artifact persistence."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from graph_engine.models import GraphImpactSnapshot, GraphSnapshot


class FormalArtifactSnapshotWriter:
    """Persist graph snapshots as Layer A/formal-readable JSON artifacts.

    The file shape is intentionally accepted by ``ArtifactCanonicalReader``:
    a top-level ``graph_snapshot`` payload plus ``graph_generation_id`` is
    enough to derive a cold-reload plan from the persisted artifact.
    """

    def __init__(
        self,
        artifact_root: str | Path,
        *,
        namespace: str = "formal",
        artifact_kind: str = "graph_snapshot",
    ) -> None:
        self.artifact_root = Path(artifact_root)
        self.namespace = namespace
        self.artifact_kind = artifact_kind
        self.last_artifact_ref: str | None = None

    def write_snapshots(
        self,
        graph_snapshot: GraphSnapshot,
        impact_snapshot: GraphImpactSnapshot,
    ) -> None:
        artifact_path = self.artifact_path_for_graph_snapshot(graph_snapshot)
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        payload = self.artifact_payload(graph_snapshot, impact_snapshot)
        _atomic_write_json(artifact_path, payload)
        self.last_artifact_ref = str(artifact_path)

    def artifact_path_for_graph_snapshot(self, graph_snapshot: GraphSnapshot) -> Path:
        return (
            self.artifact_root
            / self.namespace
            / self.artifact_kind
            / graph_snapshot.cycle_id
            / f"{graph_snapshot.graph_snapshot_id}.json"
        )

    def artifact_ref_for_graph_snapshot(self, graph_snapshot: GraphSnapshot) -> str:
        return str(self.artifact_path_for_graph_snapshot(graph_snapshot))

    def artifact_payload(
        self,
        graph_snapshot: GraphSnapshot,
        impact_snapshot: GraphImpactSnapshot,
    ) -> dict[str, Any]:
        graph_generation_id = _generation_id_from_snapshot_id(
            graph_snapshot.graph_snapshot_id,
        )
        payload: dict[str, Any] = {
            "artifact_type": self.artifact_kind,
            "layer": "Layer A",
            "namespace": self.namespace,
            "cycle_id": graph_snapshot.cycle_id,
            "graph_snapshot": graph_snapshot.model_dump(mode="json"),
            "impact_snapshot": impact_snapshot.model_dump(mode="json"),
        }
        if graph_generation_id is not None:
            payload["graph_generation_id"] = graph_generation_id
        return payload


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    tmp_path = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp_path.write_text(encoded, encoding="utf-8")
    tmp_path.replace(path)


def _generation_id_from_snapshot_id(snapshot_id: str) -> int | None:
    parts = snapshot_id.split("-")
    if len(parts) < 4 or parts[0:2] != ["graph", "snapshot"]:
        return None
    generation_part = parts[-2]
    if generation_part.isdecimal():
        return int(generation_part)
    return None
