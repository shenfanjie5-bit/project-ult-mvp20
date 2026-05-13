from __future__ import annotations

import ast
import sys
from dataclasses import dataclass
from pathlib import Path


DEFAULT_FORBIDDEN_MODULES = {"anthropic", "openai"}
SKIPPED_DIRECTORIES = {
    ".git",
    ".pytest_cache",
    ".venv",
    "__pycache__",
    "build",
    "dist",
}


@dataclass(frozen=True)
class DirectImportViolation:
    path: Path
    line: int
    module: str


def scan_for_direct_provider_imports(
    root: Path,
    forbidden_modules: set[str] | None = None,
) -> list[DirectImportViolation]:
    forbidden = (
        DEFAULT_FORBIDDEN_MODULES if forbidden_modules is None else forbidden_modules
    )
    violations: list[DirectImportViolation] = []

    for path in _iter_python_files(root):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError:
            continue

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    module = _forbidden_module(alias.name, forbidden)
                    if module is not None:
                        violations.append(
                            DirectImportViolation(
                                path=path,
                                line=node.lineno,
                                module=module,
                            )
                        )
            elif isinstance(node, ast.ImportFrom):
                module_name = node.module or ""
                module = _forbidden_module(module_name, forbidden)
                if module is not None:
                    violations.append(
                        DirectImportViolation(
                            path=path,
                            line=node.lineno,
                            module=module,
                        )
                    )

    return violations


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    roots = [Path(arg) for arg in args] if args else [Path.cwd()]
    violations: list[DirectImportViolation] = []

    for root in roots:
        violations.extend(scan_for_direct_provider_imports(root))

    if violations:
        for violation in violations:
            print(
                f"{violation.path}:{violation.line}: "
                f"forbidden provider SDK import: {violation.module}",
                file=sys.stderr,
            )
        return 1

    return 0


def _iter_python_files(root: Path) -> list[Path]:
    if root.is_file():
        return [root] if root.suffix == ".py" else []

    paths: list[Path] = []
    for path in sorted(root.rglob("*.py")):
        if any(part in SKIPPED_DIRECTORIES for part in path.parts):
            continue
        paths.append(path)
    return paths


def _forbidden_module(
    module_name: str,
    forbidden_modules: set[str],
) -> str | None:
    top_level_module = module_name.split(".", 1)[0]
    if top_level_module in forbidden_modules:
        return top_level_module
    return None


if __name__ == "__main__":
    raise SystemExit(main())
