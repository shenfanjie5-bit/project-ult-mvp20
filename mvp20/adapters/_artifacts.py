"""Helpers for artifact-backed upstream adapters."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
UPSTREAM_ROOT = REPO_ROOT / "upstream"


def load_frontend_artifact(module_slug: str, *parts: str) -> tuple[dict[str, Any] | None, str | None]:
    path = UPSTREAM_ROOT / module_slug / "artifacts" / "frontend-api"
    for part in parts:
        path /= part
    if not path.exists():
        return None, str(path.relative_to(REPO_ROOT))
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        payload = {"items": payload}
    return payload, str(path.relative_to(REPO_ROOT))


def artifact_envelope(
    *,
    module: str,
    version: str | None,
    artifact_path: str,
    payload: dict[str, Any],
    import_error: str | None,
) -> dict[str, Any]:
    return {
        "module": module,
        "version": version,
        "fixture": True,
        "wire_depth": "artifact",
        "artifact_path": artifact_path,
        "vendor_import_error": import_error,
        **payload,
    }
