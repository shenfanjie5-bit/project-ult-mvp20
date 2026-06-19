"""Helpers for artifact-backed upstream adapters."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
UPSTREAM_ROOT = REPO_ROOT / "upstream"


class ArtifactPathError(ValueError):
    """Raised when an adapter artifact path would leave its frontend-api root."""


def _safe_artifact_path(module_slug: str, parts: tuple[str, ...]) -> Path:
    base = (UPSTREAM_ROOT / module_slug / "artifacts" / "frontend-api").resolve()
    path = base
    for part in parts:
        piece = Path(str(part))
        if piece.is_absolute() or ".." in piece.parts:
            raise ArtifactPathError(f"unsafe artifact path segment: {part!r}")
        path /= piece
    resolved = path.resolve()
    if base != resolved and base not in resolved.parents:
        raise ArtifactPathError("artifact path escapes frontend-api root")
    return resolved


def load_frontend_artifact(module_slug: str, *parts: str) -> tuple[dict[str, Any] | None, str | None]:
    path = _safe_artifact_path(module_slug, parts)
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
