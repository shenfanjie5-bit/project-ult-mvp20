"""Skeleton adapter for upstream entity-registry."""
from __future__ import annotations

from typing import Any
from urllib.parse import unquote

from mvp20.adapters._artifacts import artifact_envelope, load_frontend_artifact

try:
    import entity_registry as _vendor  # noqa: F401
    _AVAILABLE = True
    _VERSION = getattr(_vendor, "__version__", "unknown")
    _IMPORT_ERR: str | None = None
except Exception as e:  # noqa: BLE001
    _AVAILABLE = False
    _VERSION = None
    _IMPORT_ERR = f"{type(e).__name__}: {e}"


def _fixture(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "module": "entity-registry",
        "version": _VERSION,
        "fixture": True,
        "wire_depth": "skeleton",
        **payload,
    }


def _path(query: dict) -> str:
    return str((query.get("_path") or [""])[0] or "")


def _source_descriptor(artifact_path: str) -> dict[str, Any]:
    return {
        "kind": "entity-registry",
        "path": artifact_path,
        "exists": True,
        "message": "artifact-backed frontend-api payload",
    }


def _search_response(payload: dict[str, Any], artifact_path: str, query: dict) -> dict[str, Any]:
    items = payload.get("items") if isinstance(payload.get("items"), list) else []
    q = str((query.get("q") or [""])[0] or "").strip().lower()
    if q:
        def matches(item: dict[str, Any]) -> bool:
            haystack = " ".join([
                str(item.get("entity_id") or ""),
                str(item.get("display_name") or ""),
                " ".join(str(alias) for alias in item.get("aliases") or []),
            ]).lower()
            return q in haystack
        items = [item for item in items if isinstance(item, dict) and matches(item)]

    try:
        limit = max(1, min(500, int((query.get("limit") or ["20"])[0])))
    except ValueError:
        limit = 20

    return {
        "source_status": "available",
        "source": _source_descriptor(artifact_path),
        "items": items[:limit],
        "total": len(items),
        "next_cursor": None,
        "metadata": payload.get("metadata") or {},
    }


def _detail_response(payload: dict[str, Any], artifact_path: str, entity_id: str) -> dict[str, Any] | None:
    items = payload.get("items") if isinstance(payload.get("items"), list) else []
    for item in items:
        if not isinstance(item, dict):
            continue
        if str(item.get("entity_id") or "") == entity_id:
            return {
                "source_status": "available",
                "source": _source_descriptor(artifact_path),
                "entity_id": entity_id,
                "profile": item.get("profile") or {},
                "metadata": item.get("metadata") or payload.get("metadata") or {},
            }
    return None


def handle_entities(cfg, query: dict) -> tuple[int, dict]:
    payload, artifact_path = load_frontend_artifact("entity-registry", "entities.json")
    if payload is not None and artifact_path is not None:
        from mvp20.server import _ok_envelope

        path = _path(query)
        marker = "/api/project-ult/entities/"
        if marker in path and not path.endswith("/search"):
            entity_id = unquote(path.split(marker, 1)[1].strip("/"))
            data = _detail_response(payload, artifact_path, entity_id)
            if data is None:
                from mvp20.server import _error_envelope
                return 404, _error_envelope(
                    "ENTITY_NOT_FOUND",
                    f"entity {entity_id!r} not found in frontend-api entity artifact",
                    status=404,
                    details={"entity_id": entity_id},
                )
            return 200, _ok_envelope(
                artifact_envelope(
                    module="entity-registry",
                    version=_VERSION,
                    artifact_path=artifact_path,
                    payload=data,
                    import_error=_IMPORT_ERR,
                )
            )

        return 200, _ok_envelope(
            artifact_envelope(
                module="entity-registry",
                version=_VERSION,
                artifact_path=artifact_path,
                payload=_search_response(payload, artifact_path, query),
                import_error=_IMPORT_ERR,
            )
        )
    if not _AVAILABLE:
        from mvp20.server import _error_envelope
        return 503, _error_envelope(
            "UPSTREAM_UNAVAILABLE",
            f"entity-registry adapter unavailable: {_IMPORT_ERR}",
            status=503,
            details={"upstream_module": "entity-registry", "import_error": _IMPORT_ERR},
        )
    from mvp20.server import _ok_envelope
    return 200, _ok_envelope(_fixture({
        "source_status": "unavailable",
        "source": {
            "kind": "entity-registry",
            "exists": False,
            "message": "entity-registry frontend-api artifact not found",
        },
        "items": [],
        "total": 0,
        "next_cursor": None,
    }))
