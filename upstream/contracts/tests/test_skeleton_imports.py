from __future__ import annotations

import ast
import importlib
import pathlib
import subprocess
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from importlib import metadata

import pytest


PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
CONTRACTS_DIR = SRC_DIR / "contracts"
EXPECTED_RUNTIME_SOURCE_FILES = {
    "src/contracts/__init__.py",
    "src/contracts/compat/__init__.py",
    "src/contracts/compat/__main__.py",
    "src/contracts/core/__init__.py",
    "src/contracts/core/base.py",
    "src/contracts/core/types.py",
    "src/contracts/core/version.py",
    "src/contracts/errors.py",
    "src/contracts/export/__init__.py",
    "src/contracts/export/__main__.py",
    "src/contracts/protocols/__init__.py",
    "src/contracts/protocols/alpha_analyzer.py",
    "src/contracts/protocols/data_source_adapter.py",
    "src/contracts/schemas/__init__.py",
    "src/contracts/schemas/alpha.py",
    "src/contracts/schemas/cycle.py",
    "src/contracts/schemas/ex_payloads.py",
    "src/contracts/schemas/formal_objects.py",
}
BUSINESS_IMPORT_ROOTS = {
    "data_platform",
    "main_core",
    "graph_engine",
    "entity_registry",
    "reasoner_runtime",
    "orchestrator",
}


@contextmanager
def prepend_src_path() -> Iterator[None]:
    sys.path.insert(0, str(SRC_DIR))
    try:
        yield
    finally:
        sys.path.remove(str(SRC_DIR))


def test_milestone_source_tree_contains_real_python_sources() -> None:
    source_paths = {
        str(path.relative_to(PROJECT_ROOT))
        for path in CONTRACTS_DIR.rglob("*.py")
    }
    test_paths = {
        str(path.relative_to(PROJECT_ROOT))
        for path in (PROJECT_ROOT / "tests").glob("test_*.py")
    }

    assert EXPECTED_RUNTIME_SOURCE_FILES <= source_paths
    assert test_paths


def test_no_tracked_python_bytecode_artifacts() -> None:
    if not (PROJECT_ROOT / ".git").exists():
        pytest.skip("git metadata is required to inspect tracked artifacts")

    result = subprocess.run(
        ["git", "ls-files"],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr

    tracked_artifacts = [
        path
        for path in result.stdout.splitlines()
        if "__pycache__/" in path or path.endswith((".pyc", ".pyo"))
    ]
    assert not tracked_artifacts


def test_package_imports() -> None:
    module_names = [
        "contracts",
        "contracts.core",
        "contracts.protocols",
        "contracts.schemas",
        "contracts.export",
        "contracts.compat",
    ]

    with prepend_src_path():
        imported_modules = [
            importlib.import_module(module_name) for module_name in module_names
        ]

    assert [module.__name__ for module in imported_modules] == module_names


def test_version_constant() -> None:
    with prepend_src_path():
        contracts = importlib.import_module("contracts")
        core = importlib.import_module("contracts.core")

    assert contracts.__version__ == "0.1.3"
    assert contracts.__version__ == core.CURRENT_VERSION_ENTRY.version


def test_cli_entrypoints_registered() -> None:
    expected_entry_points = {
        "contracts-export": "contracts.export.__main__:main",
        "contracts-compat": "contracts.compat.__main__:main",
    }
    expected_names = set(expected_entry_points)

    try:
        console_scripts = metadata.entry_points(group="console_scripts")
    except Exception as exc:
        with prepend_src_path():
            importlib.import_module("contracts.export.__main__")
            importlib.import_module("contracts.compat.__main__")
        pytest.skip(f"console script entry point lookup unavailable: {exc!r}")

    registered = {
        entry_point.name: entry_point
        for entry_point in console_scripts
        if entry_point.name in expected_names
    }
    missing_names = expected_names.difference(registered)

    if missing_names:
        with prepend_src_path():
            importlib.import_module("contracts.export.__main__")
            importlib.import_module("contracts.compat.__main__")
        missing = ", ".join(sorted(missing_names))
        pytest.skip(
            f"console script entry points not installed: {missing}; "
            "run `pip install -e .[dev]`"
        )

    assert set(registered) == expected_names
    for entry_point in registered.values():
        assert entry_point.group == "console_scripts"
        assert entry_point.value == expected_entry_points[entry_point.name]
        assert callable(entry_point.load())


def test_no_business_deps() -> None:
    violations: list[str] = []

    for source_path in sorted(CONTRACTS_DIR.rglob("*.py")):
        tree = ast.parse(
            source_path.read_text(encoding="utf-8"),
            filename=str(source_path),
        )

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imported_root = alias.name.split(".", maxsplit=1)[0]
                    if imported_root in BUSINESS_IMPORT_ROOTS:
                        violations.append(
                            f"{source_path.relative_to(PROJECT_ROOT)}:{node.lineno} "
                            f"imports {alias.name}"
                        )

            if isinstance(node, ast.ImportFrom):
                module_root = (node.module or "").split(".", maxsplit=1)[0]
                imported_roots = {
                    alias.name.split(".", maxsplit=1)[0] for alias in node.names
                }
                forbidden_roots = {module_root, *imported_roots}.intersection(
                    BUSINESS_IMPORT_ROOTS
                )
                if forbidden_roots:
                    imported_name = node.module or ", ".join(
                        alias.name for alias in node.names
                    )
                    violations.append(
                        f"{source_path.relative_to(PROJECT_ROOT)}:{node.lineno} "
                        f"imports {imported_name}"
                    )

    assert not violations, (
        "business module imports are forbidden in src/contracts:\n"
        + "\n".join(violations)
    )
