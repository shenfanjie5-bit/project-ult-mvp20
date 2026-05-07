"""Module lock validation for the MVP20 orchestration shell."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

SHA_RE = re.compile(r"^[0-9a-f]{40}$")
EXPECTED_MODULES = frozenset(
    {
        "contracts",
        "data-platform",
        "entity-registry",
        "reasoner-runtime",
        "graph-engine",
        "main-core",
        "audit-eval",
        "subsystem-sdk",
        "orchestrator",
        "assembly",
        "frontend-api",
        "subsystem-announcement",
        "subsystem-news",
        "subsystem-holdings",
    }
)


@dataclass(frozen=True)
class LockValidationResult:
    ok: bool
    module_count: int
    errors: tuple[str, ...]


def load_lock(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("lock must be a YAML object")
    return payload


def validate_lock(path: Path) -> LockValidationResult:
    payload = load_lock(path)
    errors: list[str] = []
    modules = payload.get("modules")
    if not isinstance(modules, dict):
        return LockValidationResult(
            ok=False,
            module_count=0,
            errors=("modules must be a mapping",),
        )

    module_names = set(modules)
    missing = sorted(EXPECTED_MODULES - module_names)
    extra = sorted(module_names - EXPECTED_MODULES)
    if missing:
        errors.append("missing modules: " + ", ".join(missing))
    if extra:
        errors.append("unexpected modules: " + ", ".join(extra))

    for module_name, spec in sorted(modules.items()):
        if not isinstance(spec, dict):
            errors.append(f"{module_name}: module spec must be an object")
            continue
        repo = str(spec.get("repo", "")).strip()
        commit = str(spec.get("commit", "")).strip()
        if not repo.startswith("https://github.com/shenfanjie5-bit/project-ult-"):
            errors.append(f"{module_name}: repo must be a project-ult GitHub URL")
        if not SHA_RE.fullmatch(commit):
            errors.append(f"{module_name}: commit must be a full 40-char SHA")
        if repo.endswith("@main") or commit == "main":
            errors.append(f"{module_name}: main branch dependency is not allowed")

    return LockValidationResult(
        ok=not errors,
        module_count=len(modules),
        errors=tuple(errors),
    )
