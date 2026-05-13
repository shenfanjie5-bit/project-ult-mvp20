"""Static package boundary checks for the main-core package skeleton."""

from __future__ import annotations

import ast
import importlib
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest

from main_core.common import schemas
from main_core.common.schemas import (
    LAYER_SCHEMA_IMPORT_POLICY,
    SCHEMA_COMMON_EXPORTS,
    SCHEMA_COMMON_MODULES,
    SCHEMA_CONTRACT_LAYER,
    SCHEMA_MODULE_LAYER,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXIT_SUCCESS = 0
SCHEMA_PACKAGE = "main_core.common.schemas"
COMMON_PACKAGE = "main_core.common"

LAYER_PACKAGES = (
    "l1_l2_basis",
    "l3_features",
    "l4_world_state",
    "l5_universe",
    "l6_alpha",
    "l7_recommendation",
    "l8_publish",
)


@dataclass(frozen=True)
class SchemaImportViolation:
    path: Path
    line_number: int
    layer: str
    imported_name: str
    reason: str

    def format(self) -> str:
        return (
            f"{self.path}:{self.line_number}: {self.layer} imports "
            f"{self.imported_name}: {self.reason}"
        )


def _format_process_output(result: subprocess.CompletedProcess[str]) -> str:
    return f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"


def _run_lint_imports(cwd: Path) -> subprocess.CompletedProcess[str]:
    lint_imports = shutil.which("lint-imports")
    if lint_imports is None:
        pytest.skip("import-linter CLI is not installed; run `pip install -e .[dev]`")

    env = os.environ.copy()
    package_root = cwd / "src" if (cwd / "src").exists() else cwd
    python_path = [str(package_root)]
    if existing_python_path := env.get("PYTHONPATH"):
        python_path.append(existing_python_path)
    env["PYTHONPATH"] = os.pathsep.join(python_path)

    return subprocess.run(
        [lint_imports, "--config", ".importlinter"],
        cwd=cwd,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )


def _schema_import_violations(package_root: Path) -> list[SchemaImportViolation]:
    violations: list[SchemaImportViolation] = []
    for layer in LAYER_PACKAGES:
        layer_root = package_root / layer
        if not layer_root.exists():
            continue
        for path in sorted(layer_root.rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    violations.extend(_check_schema_import_node(path, layer, node))
                elif isinstance(node, ast.ImportFrom):
                    importing_package = _importing_package_name(package_root, path)
                    violations.extend(
                        _check_schema_import_from_node(
                            path,
                            layer,
                            node,
                            importing_package,
                        )
                    )
    return violations


def _check_schema_import_node(
    path: Path,
    layer: str,
    node: ast.Import,
) -> list[SchemaImportViolation]:
    violations: list[SchemaImportViolation] = []
    for alias in node.names:
        if alias.name == SCHEMA_PACKAGE:
            violations.append(
                _violation(
                    path,
                    node.lineno,
                    layer,
                    alias.name,
                    "package namespace import exposes every schema contract",
                )
            )
            continue
        if alias.name.startswith(f"{SCHEMA_PACKAGE}."):
            module_name = alias.name.removeprefix(f"{SCHEMA_PACKAGE}.").split(".", 1)[0]
            violation = _check_schema_module(path, node.lineno, layer, module_name)
            if violation is not None:
                violations.append(violation)
    return violations


def _check_schema_import_from_node(  # noqa: PLR0912
    path: Path,
    layer: str,
    node: ast.ImportFrom,
    importing_package: str,
) -> list[SchemaImportViolation]:
    module = _absolute_import_from_module(node, importing_package)
    if module is None:
        return []

    violations: list[SchemaImportViolation] = []
    if module == COMMON_PACKAGE:
        for alias in node.names:
            if alias.name == "schemas":
                violations.append(
                    _violation(
                        path,
                        node.lineno,
                        layer,
                        f"{module}.{alias.name}",
                        "package namespace import exposes every schema contract",
                    )
                )
        return violations

    if module == SCHEMA_PACKAGE:
        for alias in node.names:
            if alias.name == "*":
                violations.append(
                    _violation(
                        path,
                        node.lineno,
                        layer,
                        f"{module}.*",
                        "wildcard import exposes every schema contract",
                    )
                )
                continue
            if alias.name in SCHEMA_COMMON_MODULES or alias.name in SCHEMA_MODULE_LAYER:
                violation = _check_schema_module(path, node.lineno, layer, alias.name)
            else:
                violation = _check_schema_export(path, node.lineno, layer, alias.name)
            if violation is not None:
                violations.append(violation)
        return violations

    if module.startswith(f"{SCHEMA_PACKAGE}."):
        module_name = module.removeprefix(f"{SCHEMA_PACKAGE}.").split(".", 1)[0]
        for alias in node.names:
            if alias.name in SCHEMA_CONTRACT_LAYER or alias.name in SCHEMA_COMMON_EXPORTS:
                violation = _check_schema_export(path, node.lineno, layer, alias.name)
            else:
                violation = _check_schema_module(path, node.lineno, layer, module_name)
            if violation is not None:
                violations.append(violation)
    return violations


def _importing_package_name(package_root: Path, path: Path) -> str:
    relative_path = path.relative_to(package_root)
    package_parts = relative_path.parent.parts
    return ".".join((package_root.name, *package_parts))


def _absolute_import_from_module(
    node: ast.ImportFrom,
    importing_package: str,
) -> str | None:
    if node.level == 0:
        return node.module

    package_parts = importing_package.split(".")
    if node.level > len(package_parts):
        return None

    absolute_package = ".".join(package_parts[: len(package_parts) - node.level + 1])
    if node.module is None:
        return absolute_package
    return f"{absolute_package}.{node.module}"


def _check_schema_export(
    path: Path,
    line_number: int,
    layer: str,
    schema_name: str,
) -> SchemaImportViolation | None:
    if schema_name not in SCHEMA_COMMON_EXPORTS and schema_name not in SCHEMA_CONTRACT_LAYER:
        return _violation(
            path,
            line_number,
            layer,
            schema_name,
            "schema export is missing explicit layer ownership",
        )
    if schema_name in LAYER_SCHEMA_IMPORT_POLICY[layer]:
        return None
    return _violation(
        path,
        line_number,
        layer,
        schema_name,
        f"owned by downstream layer {SCHEMA_CONTRACT_LAYER[schema_name]}",
    )


def _check_schema_module(
    path: Path,
    line_number: int,
    layer: str,
    module_name: str,
) -> SchemaImportViolation | None:
    if module_name in SCHEMA_COMMON_MODULES:
        return None
    if module_name not in SCHEMA_MODULE_LAYER:
        return _violation(
            path,
            line_number,
            layer,
            module_name,
            "schema module is missing explicit layer ownership",
        )

    owner_layer = SCHEMA_MODULE_LAYER[module_name]
    if any(
        schema_name in LAYER_SCHEMA_IMPORT_POLICY[layer]
        for schema_name, schema_owner in SCHEMA_CONTRACT_LAYER.items()
        if schema_owner == owner_layer
    ):
        return None
    return _violation(
        path,
        line_number,
        layer,
        module_name,
        f"module is owned by downstream layer {owner_layer}",
    )


def _violation(
    path: Path,
    line_number: int,
    layer: str,
    imported_name: str,
    reason: str,
) -> SchemaImportViolation:
    return SchemaImportViolation(
        path=path,
        line_number=line_number,
        layer=layer,
        imported_name=imported_name,
        reason=reason,
    )


def test_all_layers_importable() -> None:
    for package in LAYER_PACKAGES:
        importlib.import_module(f"main_core.{package}")


def test_importlinter_contracts_pass() -> None:
    result = _run_lint_imports(PROJECT_ROOT)

    assert result.returncode == EXIT_SUCCESS, _format_process_output(result)


def test_forbidden_contract_triggers_on_synthetic_violation(tmp_path: Path) -> None:
    synthetic_root = tmp_path / "main_core"
    synthetic_root.mkdir()
    (synthetic_root / "__init__.py").write_text('"""Synthetic main-core package."""\n')

    for package in LAYER_PACKAGES:
        package_dir = synthetic_root / package
        package_dir.mkdir()
        package_body = '"""Synthetic layer package."""\n'
        if package == "l3_features":
            package_body += "from main_core.l6_alpha import *\n"
        (package_dir / "__init__.py").write_text(package_body)

    shutil.copyfile(PROJECT_ROOT / ".importlinter", tmp_path / ".importlinter")

    result = _run_lint_imports(tmp_path)

    assert result.returncode != EXIT_SUCCESS, _format_process_output(result)


def test_layer_schema_import_policy_passes() -> None:
    violations = _schema_import_violations(PROJECT_ROOT / "src" / "main_core")

    assert not violations, "\n".join(violation.format() for violation in violations)


def test_schema_exports_are_declared_in_boundary_policy() -> None:
    metadata_exports = {
        "LAYER_SCHEMA_IMPORT_POLICY",
        "SCHEMA_COMMON_EXPORTS",
        "SCHEMA_COMMON_MODULES",
        "SCHEMA_CONTRACT_LAYER",
        "SCHEMA_MODULE_LAYER",
    }
    declared_exports = (
        set(SCHEMA_COMMON_EXPORTS)
        | set(SCHEMA_CONTRACT_LAYER)
        | metadata_exports
    )

    assert set(schemas.__all__) <= declared_exports


def test_schema_policy_triggers_on_synthetic_downstream_import(tmp_path: Path) -> None:
    synthetic_root = tmp_path / "main_core"
    synthetic_layer = synthetic_root / "l3_features"
    synthetic_layer.mkdir(parents=True)
    (synthetic_layer / "__init__.py").write_text(
        "import main_core.common.schemas as schemas\n"
        "from main_core.common.schemas import RecommendationSnapshot\n"
        "from main_core.common.schemas.publish import PublishBundle\n",
        encoding="utf-8",
    )

    violations = _schema_import_violations(synthetic_root)

    assert [violation.imported_name for violation in violations] == [
        "main_core.common.schemas",
        "RecommendationSnapshot",
        "PublishBundle",
    ]


def test_schema_policy_triggers_on_synthetic_relative_downstream_import(
    tmp_path: Path,
) -> None:
    synthetic_root = tmp_path / "main_core"
    synthetic_layer = synthetic_root / "l3_features"
    synthetic_layer.mkdir(parents=True)
    (synthetic_layer / "__init__.py").write_text(
        "from ..common.schemas import RecommendationSnapshot\n"
        "from ..common.schemas.publish import PublishBundle\n",
        encoding="utf-8",
    )

    violations = _schema_import_violations(synthetic_root)

    assert [violation.imported_name for violation in violations] == [
        "RecommendationSnapshot",
        "PublishBundle",
    ]
