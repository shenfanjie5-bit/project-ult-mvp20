"""Skeleton adapter for upstream main-core."""
from __future__ import annotations

from typing import Any

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
    if not _AVAILABLE:
        return _unavailable()
    from mvp20.server import _ok_envelope
    return 200, _ok_envelope(_fixture({"cycle": None, "manifest_ref": None}))


def handle_stocks(cfg, query: dict) -> tuple[int, dict]:
    if not _AVAILABLE:
        return _unavailable()
    from mvp20.server import _ok_envelope
    return 200, _ok_envelope(_fixture({"stock": None, "alpha_result": None}))


def handle_pool(cfg, query: dict) -> tuple[int, dict]:
    if not _AVAILABLE:
        return _unavailable()
    from mvp20.server import _ok_envelope
    return 200, _ok_envelope(_fixture({"pool": [], "snapshot": None}))


def handle_world_state(cfg, query: dict) -> tuple[int, dict]:
    if not _AVAILABLE:
        return _unavailable()
    from mvp20.server import _ok_envelope
    return 200, _ok_envelope(_fixture({"world_state": None, "snapshot_at": None}))
