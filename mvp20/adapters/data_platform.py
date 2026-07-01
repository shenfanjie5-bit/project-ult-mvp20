"""Skeleton adapter for upstream data-platform."""
from __future__ import annotations

import re
from typing import Any

from mvp20.adapters._artifacts import artifact_envelope, load_frontend_artifact

try:
    import data_platform as _vendor  # noqa: F401
    _AVAILABLE = True
    _VERSION = getattr(_vendor, "__version__", "unknown")
    _IMPORT_ERR: str | None = None
except Exception as e:  # noqa: BLE001
    _AVAILABLE = False
    _VERSION = None
    _IMPORT_ERR = f"{type(e).__name__}: {e}"


def _fixture(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "module": "data-platform",
        "version": _VERSION,
        "fixture": True,
        "wire_depth": "skeleton",
        **payload,
    }


def _unavailable() -> tuple[int, dict]:
    from mvp20.server import _error_envelope
    return 503, _error_envelope(
        "UPSTREAM_UNAVAILABLE",
        f"data-platform adapter unavailable: {_IMPORT_ERR}",
        status=503,
        details={"upstream_module": "data-platform", "import_error": _IMPORT_ERR},
    )


def _path(query: dict) -> str:
    return str((query.get("_path") or [""])[0] or "")


def _source_descriptor(artifact_path: str, *, kind: str) -> dict[str, Any]:
    return {
        "kind": kind,
        "path": artifact_path,
        "exists": True,
        "message": "artifact-backed frontend-api payload",
    }


def _missing_source(artifact_path: str, *, kind: str) -> dict[str, Any]:
    return {
        "kind": kind,
        "path": artifact_path,
        "exists": False,
        "message": "artifact not found under upstream/data-platform/artifacts/frontend-api",
    }


def _single_query_value(query: dict, name: str, default: str = "") -> str:
    return str((query.get(name) or [default])[0] or default)


def _table_from_path(path: str, prefix: str) -> str | None:
    if prefix not in path:
        return None
    tail = path.split(prefix, 1)[1].strip("/")
    return tail or None


def _normalize_tabular_payload(
    *,
    source_name: str,
    table: str | None,
    payload: dict[str, Any],
    artifact_path: str,
) -> dict[str, Any]:
    items = payload.get("items")
    if not isinstance(items, list):
        items = payload.get("rows") if isinstance(payload.get("rows"), list) else []
    columns = payload.get("columns")
    if not isinstance(columns, list):
        columns = list(items[0].keys()) if items and isinstance(items[0], dict) else []
    return {
        "source_status": "available",
        "source": _source_descriptor(artifact_path, kind=f"data-platform:{source_name}"),
        "table": table,
        "source_name": source_name,
        "columns": columns,
        "items": items,
        "total": int(payload.get("total") or len(items)),
        "next_cursor": payload.get("next_cursor"),
        "metadata": payload.get("metadata") or {},
    }


def handle_manifest_latest(cfg, query: dict) -> tuple[int, dict]:
    payload, artifact_path = load_frontend_artifact(
        "data-platform", "manifests", "latest.json"
    )
    if payload is not None and artifact_path is not None:
        from mvp20.server import _ok_envelope

        data = {
            "source_status": "available",
            "source": _source_descriptor(artifact_path, kind="data-platform:manifest"),
            "cycle_id": payload.get("published_cycle_id") or payload.get("cycle_id"),
            "manifest_ref": payload.get("manifest_ref"),
            "published_at": payload.get("published_at"),
            "formal_table_snapshots": payload.get("formal_table_snapshots") or {},
            "metadata": payload.get("metadata") or {},
            "payload": payload,
        }
        return 200, _ok_envelope(
            artifact_envelope(
                module="data-platform",
                version=_VERSION,
                artifact_path=artifact_path,
                payload=data,
                import_error=_IMPORT_ERR,
            )
        )
    if not _AVAILABLE:
        return _unavailable()
    from mvp20.server import _ok_envelope
    return 200, _ok_envelope(_fixture({
        "source_status": "unavailable",
        "source": _missing_source(
            artifact_path or "upstream/data-platform/artifacts/frontend-api/manifests/latest.json",
            kind="data-platform:manifest",
        ),
        "cycle_id": None,
        "manifest_ref": None,
        "published_at": None,
        "formal_table_snapshots": {},
        "payload": None,
    }))


_FORMAL_OBJECT_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_-]{0,80}$")


def handle_formal_object(cfg, query: dict) -> tuple[int, dict]:
    path = _path(query)
    marker = "/api/project-ult/formal/"
    if marker not in path:
        from mvp20.server import _error_envelope
        return 400, _error_envelope(
            "BAD_FORMAL_PATH",
            "formal object path must be /api/project-ult/formal/{object_type}[/{cycle_id}]",
            status=400,
            details={"path": path},
        )
    parts = path.split(marker, 1)[1].strip("/").split("/")
    object_type = parts[0] if parts else ""
    cycle_id = parts[1] if len(parts) > 1 else ""
    if not _FORMAL_OBJECT_RE.match(object_type):
        from mvp20.server import _error_envelope
        return 400, _error_envelope(
            "BAD_FORMAL_OBJECT_TYPE",
            "formal object_type contains unsupported characters",
            status=400,
            details={"object_type": object_type},
        )

    artifact_file = "latest.json" if not cycle_id or cycle_id == "latest" else f"{cycle_id}.json"
    payload, artifact_path = load_frontend_artifact(
        "data-platform", "formal", object_type, artifact_file
    )
    if payload is not None and artifact_path is not None:
        from mvp20.server import _ok_envelope

        data = {
            "source_status": "available",
            "source": _source_descriptor(artifact_path, kind="data-platform:formal"),
            "object_type": payload.get("object_type") or object_type,
            "cycle_id": payload.get("cycle_id") or (cycle_id or None),
            "snapshot_id": payload.get("snapshot_id"),
            "metadata": payload.get("metadata") or {},
            "payload": payload.get("payload"),
        }
        return 200, _ok_envelope(
            artifact_envelope(
                module="data-platform",
                version=_VERSION,
                artifact_path=artifact_path,
                payload=data,
                import_error=_IMPORT_ERR,
            )
        )

    if not _AVAILABLE:
        return _unavailable()
    from mvp20.server import _ok_envelope
    return 200, _ok_envelope(_fixture({
        "source_status": "unavailable",
        "source": _missing_source(
            artifact_path or f"upstream/data-platform/artifacts/frontend-api/formal/{object_type}/{artifact_file}",
            kind="data-platform:formal",
        ),
        "object_type": object_type,
        "cycle_id": cycle_id or None,
        "snapshot_id": None,
        "metadata": {},
        "payload": None,
    }))


def handle_canonical(cfg, query: dict) -> tuple[int, dict]:
    table = _table_from_path(_path(query), "/api/project-ult/data/canonical/")
    payload, artifact_path = load_frontend_artifact(
        "data-platform", "data", "canonical", "stock_basic.json"
    )
    if payload is not None and artifact_path is not None:
        from mvp20.server import _ok_envelope
        return 200, _ok_envelope(
            artifact_envelope(
                module="data-platform",
                version=_VERSION,
                artifact_path=artifact_path,
                payload=_normalize_tabular_payload(
                    source_name="canonical",
                    table=table,
                    payload=payload,
                    artifact_path=artifact_path,
                ),
                import_error=_IMPORT_ERR,
            )
        )
    if not _AVAILABLE:
        return _unavailable()
    from mvp20.server import _ok_envelope
    return 200, _ok_envelope(_fixture({
        "source_status": "unavailable",
        "source": _missing_source(
            "upstream/data-platform/artifacts/frontend-api/data/canonical/stock_basic.json",
            kind="data-platform:canonical",
        ),
        "table": table,
        "source_name": "canonical",
        "columns": [],
        "items": [],
        "total": 0,
        "next_cursor": None,
    }))


def handle_raw(cfg, query: dict) -> tuple[int, dict]:
    table = _table_from_path(_path(query), "/api/project-ult/data/raw/")
    payload, artifact_path = load_frontend_artifact(
        "data-platform", "data", "raw", "tushare_stock_basic.json"
    )
    if payload is not None and artifact_path is not None:
        from mvp20.server import _ok_envelope
        return 200, _ok_envelope(
            artifact_envelope(
                module="data-platform",
                version=_VERSION,
                artifact_path=artifact_path,
                payload=_normalize_tabular_payload(
                    source_name="raw",
                    table=table,
                    payload=payload,
                    artifact_path=artifact_path,
                ),
                import_error=_IMPORT_ERR,
            )
        )
    if not _AVAILABLE:
        return _unavailable()
    from mvp20.server import _ok_envelope
    return 200, _ok_envelope(_fixture({
        "source_status": "unavailable",
        "source": _missing_source(
            "upstream/data-platform/artifacts/frontend-api/data/raw/tushare_stock_basic.json",
            kind="data-platform:raw",
        ),
        "table": table,
        "source_name": "raw",
        "columns": [],
        "items": [],
        "total": 0,
        "next_cursor": None,
    }))
