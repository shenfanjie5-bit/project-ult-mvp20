"""Skeleton adapter for upstream entity-registry."""
from __future__ import annotations

from typing import Any

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


def handle_entities(cfg, query: dict) -> tuple[int, dict]:
    payload, artifact_path = load_frontend_artifact("entity-registry", "entities.json")
    if payload is not None and artifact_path is not None:
        from mvp20.server import _ok_envelope
        return 200, _ok_envelope(
            artifact_envelope(
                module="entity-registry",
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
            f"entity-registry adapter unavailable: {_IMPORT_ERR}",
            status=503,
            details={"upstream_module": "entity-registry", "import_error": _IMPORT_ERR},
        )
    from mvp20.server import _ok_envelope
    return 200, _ok_envelope(_fixture({"entities": [], "total": 0, "next_cursor": None}))
