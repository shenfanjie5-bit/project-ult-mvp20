"""Skeleton adapter for upstream main-core."""
from __future__ import annotations

from typing import Any

from mvp20.adapters._artifacts import artifact_envelope, load_frontend_artifact

try:
    import main_core as _vendor  # noqa: F401
    _AVAILABLE = True
    _VERSION = getattr(_vendor, "__version__", "unknown")
    _IMPORT_ERR: str | None = None
except Exception as e:  # noqa: BLE001
    _AVAILABLE = False
    _VERSION = None
    _IMPORT_ERR = f"{type(e).__name__}: {e}"


def _fixture(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "module": "main-core",
        "version": _VERSION,
        "fixture": True,
        "wire_depth": "skeleton",
        **payload,
    }


def _unavailable() -> tuple[int, dict]:
    from mvp20.server import _error_envelope
    return 503, _error_envelope(
        "UPSTREAM_UNAVAILABLE",
        f"main-core adapter unavailable: {_IMPORT_ERR}",
        status=503,
        details={"upstream_module": "main-core", "import_error": _IMPORT_ERR},
    )


def handle_cycle_detail(cfg, query: dict) -> tuple[int, dict]:
    payload, artifact_path = load_frontend_artifact("data-platform", "cycles.json")
    if payload is not None and artifact_path is not None:
        from mvp20.server import _ok_envelope
        return 200, _ok_envelope(
            artifact_envelope(
                module="main-core",
                version=_VERSION,
                artifact_path=artifact_path,
                payload=payload,
                import_error=_IMPORT_ERR,
            )
        )
    if not _AVAILABLE:
        return _unavailable()
    from mvp20.server import _ok_envelope
    return 200, _ok_envelope(_fixture({"cycle": None, "manifest_ref": None}))


def handle_stocks(cfg, query: dict) -> tuple[int, dict]:
    payload, artifact_path = load_frontend_artifact(
        "data-platform", "formal", "recommendation_snapshot", "latest.json"
    )
    if payload is not None and artifact_path is not None:
        from mvp20.server import _ok_envelope
        return 200, _ok_envelope(
            artifact_envelope(
                module="main-core",
                version=_VERSION,
                artifact_path=artifact_path,
                payload={"stock": None, "alpha_result": payload},
                import_error=_IMPORT_ERR,
            )
        )
    if not _AVAILABLE:
        return _unavailable()
    from mvp20.server import _ok_envelope
    return 200, _ok_envelope(_fixture({"stock": None, "alpha_result": None}))


def handle_pool(cfg, query: dict) -> tuple[int, dict]:
    payload, artifact_path = load_frontend_artifact(
        "data-platform", "formal", "official_alpha_pool", "latest.json"
    )
    if payload is not None and artifact_path is not None:
        from mvp20.server import _ok_envelope
        return 200, _ok_envelope(
            artifact_envelope(
                module="main-core",
                version=_VERSION,
                artifact_path=artifact_path,
                payload={"pool": payload.get("items", []), "snapshot": payload},
                import_error=_IMPORT_ERR,
            )
        )
    if not _AVAILABLE:
        return _unavailable()
    from mvp20.server import _ok_envelope
    return 200, _ok_envelope(_fixture({"pool": [], "snapshot": None}))


def handle_world_state(cfg, query: dict) -> tuple[int, dict]:
    payload, artifact_path = load_frontend_artifact(
        "data-platform", "formal", "world_state_snapshot", "latest.json"
    )
    if payload is not None and artifact_path is not None:
        from mvp20.server import _ok_envelope
        return 200, _ok_envelope(
            artifact_envelope(
                module="main-core",
                version=_VERSION,
                artifact_path=artifact_path,
                payload={"world_state": payload, "snapshot_at": payload.get("as_of")},
                import_error=_IMPORT_ERR,
            )
        )
    if not _AVAILABLE:
        return _unavailable()
    from mvp20.server import _ok_envelope
    return 200, _ok_envelope(_fixture({"world_state": None, "snapshot_at": None}))
