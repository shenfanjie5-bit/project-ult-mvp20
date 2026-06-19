"""Skeleton adapter for upstream data-platform."""
from __future__ import annotations

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


def handle_canonical(cfg, query: dict) -> tuple[int, dict]:
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
                payload={"source": "canonical", **payload},
                import_error=_IMPORT_ERR,
            )
        )
    if not _AVAILABLE:
        return _unavailable()
    from mvp20.server import _ok_envelope
    return 200, _ok_envelope(_fixture({"source": "canonical", "rows": [], "total": 0}))


def handle_raw(cfg, query: dict) -> tuple[int, dict]:
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
                payload={"source": "raw", **payload},
                import_error=_IMPORT_ERR,
            )
        )
    if not _AVAILABLE:
        return _unavailable()
    from mvp20.server import _ok_envelope
    return 200, _ok_envelope(_fixture({"source": "raw", "rows": [], "total": 0}))
