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


def handle_graph_query(cfg, query: dict) -> tuple[int, dict]:
    artifact = str(query.get("artifact", ["subgraph.json"])[0] or "subgraph.json")
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
                payload=payload,
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
        "nodes": [],
        "edges": [],
        "total_nodes": 0,
        "total_edges": 0,
        "truncated": False,
    }))
