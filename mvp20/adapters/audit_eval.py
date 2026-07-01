"""Skeleton adapter for upstream audit-eval."""
from __future__ import annotations

from typing import Any
from urllib.parse import unquote

from mvp20.adapters._artifacts import artifact_envelope, load_frontend_artifact

try:
    import audit_eval as _vendor  # noqa: F401
    _AVAILABLE = True
    _VERSION = getattr(_vendor, "__version__", "unknown")
    _IMPORT_ERR: str | None = None
except Exception as e:  # noqa: BLE001
    _AVAILABLE = False
    _VERSION = None
    _IMPORT_ERR = f"{type(e).__name__}: {e}"


def _fixture(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "module": "audit-eval",
        "version": _VERSION,
        "fixture": True,
        "wire_depth": "skeleton",
        **payload,
    }


def _unavailable(module_label: str) -> tuple[int, dict]:
    from mvp20.server import _error_envelope
    return 503, _error_envelope(
        "UPSTREAM_UNAVAILABLE",
        f"{module_label} adapter unavailable: {_IMPORT_ERR}",
        status=503,
        details={"upstream_module": "audit-eval", "import_error": _IMPORT_ERR},
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


def _detail_payload(
    *,
    kind: str,
    payload: dict[str, Any],
    artifact_path: str,
    message: str | None = None,
) -> dict[str, Any]:
    return {
        "source_status": "available",
        "source": _source_descriptor(artifact_path, kind=kind),
        "payload": payload,
        "metadata": payload.get("metadata") or {},
        "message": message,
    }


def _tail_id(path: str, marker: str) -> str:
    if marker not in path:
        return ""
    return unquote(path.split(marker, 1)[1].strip("/"))


def handle_audit(cfg, query: dict) -> tuple[int, dict]:
    cycle_id = _tail_id(_path(query), "/api/project-ult/audit/") or "CYCLE_20260424"
    payload, artifact_path = load_frontend_artifact(
        "audit-eval", "audit", f"{cycle_id}.json"
    )
    if payload is None:
        # Keep legacy smoke routes artifact-backed even when the caller uses
        # a synthetic cycle id (tests and old demo links rely on this).
        payload, artifact_path = load_frontend_artifact(
            "audit-eval", "audit", "CYCLE_20260424.json"
        )
    if payload is not None and artifact_path is not None:
        from mvp20.server import _ok_envelope
        return 200, _ok_envelope(
            artifact_envelope(
                module="audit-eval",
                version=_VERSION,
                artifact_path=artifact_path,
                payload={
                    **payload,
                    "source_status": "available",
                    "source": _source_descriptor(artifact_path, kind="audit-eval:audit"),
                    "payload": payload,
                    "metadata": payload.get("metadata") or {},
                },
                import_error=_IMPORT_ERR,
            )
        )
    if not _AVAILABLE:
        return _unavailable("audit-eval")
    from mvp20.server import _ok_envelope
    return 200, _ok_envelope(_fixture({"audit_records": [], "snapshot_id": None}))


def handle_replay(cfg, query: dict) -> tuple[int, dict]:
    cycle_id = _tail_id(_path(query), "/api/project-ult/replay/") or "CYCLE_20260424"
    payload, artifact_path = load_frontend_artifact(
        "audit-eval", "replay", f"{cycle_id}.json"
    )
    if payload is not None and artifact_path is not None:
        from mvp20.server import _ok_envelope
        return 200, _ok_envelope(
            artifact_envelope(
                module="audit-eval",
                version=_VERSION,
                artifact_path=artifact_path,
                payload=_detail_payload(
                    kind="audit-eval:replay",
                    payload=payload,
                    artifact_path=artifact_path,
                ),
                import_error=_IMPORT_ERR,
            )
        )
    if not _AVAILABLE:
        return _unavailable("audit-eval")
    from mvp20.server import _error_envelope
    return 404, _error_envelope(
        "REPLAY_NOT_FOUND",
        f"replay artifact for cycle {cycle_id!r} was not found",
        status=404,
        details={"cycle_id": cycle_id},
    )


def handle_backtest_detail(cfg, query: dict) -> tuple[int, dict]:
    backtest_id = _tail_id(_path(query), "/api/project-ult/backtests/")
    payload, artifact_path = load_frontend_artifact(
        "audit-eval", "backtests", f"{backtest_id}.json"
    )
    if payload is not None and artifact_path is not None:
        from mvp20.server import _ok_envelope
        return 200, _ok_envelope(
            artifact_envelope(
                module="audit-eval",
                version=_VERSION,
                artifact_path=artifact_path,
                payload=_detail_payload(
                    kind="audit-eval:backtest",
                    payload=payload,
                    artifact_path=artifact_path,
                ),
                import_error=_IMPORT_ERR,
            )
        )
    if not _AVAILABLE:
        return _unavailable("audit-eval")
    from mvp20.server import _error_envelope
    return 404, _error_envelope(
        "BACKTEST_NOT_FOUND",
        f"backtest artifact {backtest_id!r} was not found",
        status=404,
        details={"backtest_id": backtest_id},
    )


def handle_backtest(cfg, query: dict) -> tuple[int, dict]:
    payload, artifact_path = load_frontend_artifact("audit-eval", "backtests.json")
    if payload is not None and artifact_path is not None:
        from mvp20.server import _ok_envelope
        return 200, _ok_envelope(
            artifact_envelope(
                module="audit-eval",
                version=_VERSION,
                artifact_path=artifact_path,
                payload={
                    "source_status": "available",
                    "source": _source_descriptor(artifact_path, kind="audit-eval:backtests"),
                    "backtests": payload.get("items", []),
                    "items": payload.get("items", []),
                    "total": len(payload.get("items", []) or []),
                    "next_cursor": None,
                    **payload,
                },
                import_error=_IMPORT_ERR,
            )
        )
    if not _AVAILABLE:
        return _unavailable("audit-eval")
    from mvp20.server import _ok_envelope
    return 200, _ok_envelope(_fixture({"backtests": [], "total": 0}))
