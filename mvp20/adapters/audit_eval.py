"""Skeleton adapter for upstream audit-eval."""
from __future__ import annotations

from typing import Any

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


def handle_audit(cfg, query: dict) -> tuple[int, dict]:
    if not _AVAILABLE:
        return _unavailable("audit-eval")
    from mvp20.server import _ok_envelope
    return 200, _ok_envelope(_fixture({"audit_records": [], "snapshot_id": None}))


def handle_backtest(cfg, query: dict) -> tuple[int, dict]:
    if not _AVAILABLE:
        return _unavailable("audit-eval")
    from mvp20.server import _ok_envelope
    return 200, _ok_envelope(_fixture({"backtests": [], "total": 0}))
