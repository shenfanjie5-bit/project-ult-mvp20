"""Static checks for L4 world-state dependency boundaries."""

from __future__ import annotations

import ast
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
L4_ROOT = PROJECT_ROOT / "src" / "main_core" / "l4_world_state"
FORBIDDEN_IMPORT_PREFIXES = (
    "main_core.l3_features",
    "main_core.l5_universe",
    "main_core.l6_alpha",
    "main_core.l7_recommendation",
    "main_core.l8_publish",
    "openai",
    "anthropic",
)


def test_l4_world_state_does_not_import_downstream_or_provider_sdks() -> None:
    violations: list[str] = []

    for path in sorted(L4_ROOT.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            imported_modules = _imported_modules(node)
            for module_name in imported_modules:
                if module_name.startswith(FORBIDDEN_IMPORT_PREFIXES):
                    relative_path = path.relative_to(PROJECT_ROOT)
                    violations.append(f"{relative_path}:{node.lineno}: {module_name}")

    assert not violations, "\n".join(violations)


def _imported_modules(node: ast.AST) -> list[str]:
    if isinstance(node, ast.Import):
        return [alias.name for alias in node.names]
    if isinstance(node, ast.ImportFrom) and node.module is not None:
        return [node.module]
    return []
