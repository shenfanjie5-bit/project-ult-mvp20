"""Skeleton adapter for upstream graph-engine."""
from __future__ import annotations

from typing import Any

from mvp20.adapters._artifacts import (
    ArtifactPathError,
    artifact_envelope,
    load_frontend_artifact,
)

try:
    import graph_engine as _vendor  # noqa: F401
    _AVAILABLE = True
    _VERSION = getattr(_vendor, "__version__", "unknown")
    _IMPORT_ERR: str | None = None
except Exception as e:  # noqa: BLE001
    _AVAILABLE = False
    _VERSION = None
    _IMPORT_ERR = f"{type(e).__name__}: {e}"


def _fixture(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "module": "graph-engine",
        "version": _VERSION,
        "fixture": True,
        "wire_depth": "skeleton",
        **payload,
    }


GRAPH_ARTIFACT_ALLOWLIST = {"subgraph.json", "paths.json", "impact.json"}


def _path(query: dict) -> str:
    return str((query.get("_path") or [""])[0] or "")


def _query_dict(query: dict) -> dict[str, Any]:
    return {
        key: values[0] if isinstance(values, list) and values else values
        for key, values in query.items()
        if not key.startswith("_")
    }


def _source_descriptor(artifact_path: str) -> dict[str, Any]:
    return {
        "kind": "graph-engine",
        "path": artifact_path,
        "exists": True,
        "message": "artifact-backed frontend-api payload",
    }


def _artifact_for_path(path: str) -> str:
    if path.endswith("/paths"):
        return "paths.json"
    if path.endswith("/impact"):
        return "impact.json"
    return "subgraph.json"


def _normalize_payload(
    *,
    artifact: str,
    payload: dict[str, Any],
    artifact_path: str,
    query: dict,
) -> dict[str, Any]:
    common = {
        "source_status": "available",
        "source": _source_descriptor(artifact_path),
        "query": _query_dict(query),
        "metadata": payload.get("metadata") or {},
    }
    if artifact == "paths.json":
        paths = payload.get("paths") if isinstance(payload.get("paths"), list) else []
        return {
            **common,
            "paths": paths,
            "total": int(payload.get("total") or len(paths)),
            "truncated": bool(payload.get("truncated", False)),
        }
    if artifact == "impact.json":
        items = payload.get("items") if isinstance(payload.get("items"), list) else []
        return {
            **common,
            "items": items,
            "impacted_entities": payload.get("impacted_entities") if isinstance(payload.get("impacted_entities"), list) else items,
            "total": int(payload.get("total") or len(items)),
            "snapshot_id": payload.get("snapshot_id"),
            "cycle_id": payload.get("cycle_id"),
            "entity_id": payload.get("entity_id"),
        }
    nodes = payload.get("nodes") if isinstance(payload.get("nodes"), list) else []
    edges = payload.get("edges") if isinstance(payload.get("edges"), list) else []
    return {
        **common,
        "nodes": nodes,
        "edges": edges,
        "total_nodes": int(payload.get("total_nodes") or len(nodes)),
        "total_edges": int(payload.get("total_edges") or len(edges)),
        "truncated": bool(payload.get("truncated", False)),
    }


def handle_graph_query(cfg, query: dict) -> tuple[int, dict]:
    artifact = str(query.get("artifact", [_artifact_for_path(_path(query))])[0] or "subgraph.json")
    if artifact not in GRAPH_ARTIFACT_ALLOWLIST:
        from mvp20.server import _error_envelope
        return 400, _error_envelope(
            "BAD_ARTIFACT_PARAM",
            "graph-engine artifact must be one of the declared frontend-api graph artifacts",
            status=400,
            details={
                "artifact": artifact,
                "allowed_artifacts": sorted(GRAPH_ARTIFACT_ALLOWLIST),
            },
        )
    try:
        payload, artifact_path = load_frontend_artifact("graph-engine", artifact)
    except (ArtifactPathError, ValueError) as e:
        from mvp20.server import _error_envelope
        return 400, _error_envelope(
            "BAD_ARTIFACT_PARAM",
            "graph-engine artifact path is not allowed",
            status=400,
            details={"artifact": artifact, "reason": str(e)},
        )
    if payload is not None and artifact_path is not None:
        from mvp20.server import _ok_envelope
        return 200, _ok_envelope(
            artifact_envelope(
                module="graph-engine",
                version=_VERSION,
                artifact_path=artifact_path,
                payload=_normalize_payload(
                    artifact=artifact,
                    payload=payload,
                    artifact_path=artifact_path,
                    query=query,
                ),
                import_error=_IMPORT_ERR,
            )
        )
    if not _AVAILABLE:
        from mvp20.server import _error_envelope
        return 503, _error_envelope(
            "UPSTREAM_UNAVAILABLE",
            f"graph-engine adapter unavailable: {_IMPORT_ERR}",
            status=503,
            details={"upstream_module": "graph-engine", "import_error": _IMPORT_ERR},
        )
    from mvp20.server import _ok_envelope
    return 200, _ok_envelope(_fixture({
        "source_status": "unavailable",
        "source": {
            "kind": "graph-engine",
            "exists": False,
            "message": "graph-engine frontend-api artifact not found",
        },
        "query": _query_dict(query),
        "nodes": [],
        "edges": [],
        "total_nodes": 0,
        "total_edges": 0,
        "truncated": False,
    }))
