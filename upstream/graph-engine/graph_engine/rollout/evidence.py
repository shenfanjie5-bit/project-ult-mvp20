"""Sanitized evidence manifests for guarded rollout paths."""

from __future__ import annotations

import json
import os
import re
from collections.abc import Mapping
from datetime import date, datetime
from pathlib import Path
from typing import Any

_SAFE_FILE_COMPONENT_PATTERN = re.compile(r"[^A-Za-z0-9_.-]+")
_SENSITIVE_KEY_PATTERN = re.compile(
    r"(token|secret|password|passwd|pwd|dsn|database_url|private_key|"
    r"raw[_-]?(payload|response|provider)?|provider[_-]?payload|"
    r"local[_-]?path|runtime[_-]?path)",
    re.IGNORECASE,
)
_SENSITIVE_VALUE_PATTERNS = (
    re.compile(r"\b(?:postgres(?:ql)?|mysql|redis|mongodb)://\S+", re.IGNORECASE),
    re.compile(r"\bbolt(?:\+s|\+ssc)?://\S+", re.IGNORECASE),
    re.compile(r"\b(?:ghp|gho|github_pat)_[A-Za-z0-9_]+\b"),
    re.compile(r"\b[A-Za-z0-9_]*token[A-Za-z0-9_]*=[^\s,;]+", re.IGNORECASE),
    re.compile(r"/Users/[^,\s\"']+"),
    re.compile(r"/private/var/[^,\s\"']+"),
    re.compile(r"/tmp/[^,\s\"']+"),
)
_REDACTED_VALUE = "<redacted>"


class EvidenceWriter:
    """Write sanitized rollout evidence JSON under an artifact namespace."""

    def __init__(self, artifact_root: str | Path, *, namespace: str) -> None:
        self.artifact_root = Path(artifact_root).expanduser().resolve(strict=False)
        self.namespace = _safe_file_component(namespace)

    def write_manifest(self, name: str, payload: Mapping[str, Any]) -> Path:
        evidence_dir = self.artifact_root / self.namespace / "evidence"
        evidence_dir.mkdir(parents=True, exist_ok=True)
        manifest_path = evidence_dir / f"{_safe_file_component(name)}.json"
        sanitized = redact_evidence_payload(payload)
        _atomic_write_json(manifest_path, sanitized)
        return manifest_path


def redact_evidence_payload(value: Any, *, key: str | None = None) -> Any:
    """Return a JSON-safe payload with secrets, local paths, and raw bodies redacted."""

    if key is not None and _SENSITIVE_KEY_PATTERN.search(key):
        return _REDACTED_VALUE
    if isinstance(value, Mapping):
        return {
            str(item_key): redact_evidence_payload(item_value, key=str(item_key))
            for item_key, item_value in value.items()
        }
    if isinstance(value, list):
        return [redact_evidence_payload(item) for item in value]
    if isinstance(value, tuple):
        return [redact_evidence_payload(item) for item in value]
    if isinstance(value, set | frozenset):
        return sorted(redact_evidence_payload(item) for item in value)
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, Path):
        return _REDACTED_VALUE
    if isinstance(value, str):
        return _redact_sensitive_string(value)
    return value


def safe_reload_ref_label(snapshot_ref: str) -> str:
    """Record a reload ref label without leaking local filesystem paths."""

    value = str(snapshot_ref or "").strip()
    if not value:
        raise ValueError("snapshot_ref must not be empty")
    if value.startswith(("artifact://", "s3://", "gs://")):
        return _redact_sensitive_string(value)
    path = Path(value)
    if path.is_absolute() or "/" in value or "\\" in value:
        return path.name or _REDACTED_VALUE
    return _redact_sensitive_string(value)


def _redact_sensitive_string(value: str) -> str:
    redacted = value
    for pattern in _SENSITIVE_VALUE_PATTERNS:
        redacted = pattern.sub(_REDACTED_VALUE, redacted)
    if _looks_like_raw_payload_string(redacted):
        return _REDACTED_VALUE
    return redacted


def _looks_like_raw_payload_string(value: str) -> bool:
    stripped = value.strip()
    if not (
        (stripped.startswith("{") and stripped.endswith("}"))
        or (stripped.startswith("[") and stripped.endswith("]"))
    ):
        return False
    lowered = stripped.lower()
    return any(
        marker in lowered
        for marker in (
            '"password"',
            '"private_key"',
            '"raw_payload"',
            '"raw_response"',
            '"secret"',
            '"token"',
        )
    )


def _safe_file_component(value: str) -> str:
    sanitized = _SAFE_FILE_COMPONENT_PATTERN.sub("-", value.strip()).strip(".-")
    if not sanitized:
        raise ValueError("file component must not be empty after sanitization")
    return sanitized[:120]


def _atomic_write_json(path: Path, payload: Any) -> None:
    tmp_path = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp_path.write_text(
        json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    tmp_path.replace(path)
