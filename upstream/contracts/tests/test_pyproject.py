from __future__ import annotations

import importlib
import json
import os
import pathlib
import re
import subprocess
import sys
import sysconfig
import tomllib
from collections.abc import Callable
from importlib.metadata import EntryPoint


PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"


def venv_executable(venv_dir: pathlib.Path, executable_name: str) -> pathlib.Path:
    bin_dir = "Scripts" if os.name == "nt" else "bin"
    suffix = (
        ".exe"
        if os.name == "nt" and not executable_name.endswith(".exe")
        else ""
    )
    return venv_dir / bin_dir / f"{executable_name}{suffix}"


def load_pyproject() -> dict:
    return tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))


def load_console_script(name: str, entry_point: str) -> Callable[..., int]:
    sys.path.insert(0, str(SRC_DIR))
    try:
        function = EntryPoint(name=name, value=entry_point, group="console_scripts").load()
    finally:
        sys.path.remove(str(SRC_DIR))

    assert callable(function)
    return function


def run_subprocess(
    args: list[str],
    *,
    cwd: pathlib.Path,
    env: dict[str, str],
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=cwd,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )


def assert_success(result: subprocess.CompletedProcess[str]) -> None:
    assert result.returncode == 0, (
        f"command failed: {' '.join(result.args)}\n"
        f"stdout:\n{result.stdout}\n"
        f"stderr:\n{result.stderr}"
    )


def local_build_requirement_wheel_dirs() -> list[pathlib.Path]:
    stdlib_dir = pathlib.Path(sysconfig.get_path("stdlib"))
    base_prefix = pathlib.Path(sys.base_prefix)
    candidate_dirs = [
        stdlib_dir / "ensurepip" / "_bundled",
        stdlib_dir / "test" / "wheeldata",
    ]
    candidate_dirs.extend(
        parent / "libexec" for parent in [base_prefix, *base_prefix.parents]
    )

    package_dirs: dict[str, pathlib.Path] = {}
    for candidate_dir in candidate_dirs:
        if not candidate_dir.is_dir():
            continue
        setuptools_wheels = sorted(candidate_dir.glob("setuptools-*.whl"))
        if any(is_setuptools_69_or_newer(wheel) for wheel in setuptools_wheels):
            package_dirs.setdefault("setuptools", candidate_dir)
        if any(candidate_dir.glob("wheel-*.whl")):
            package_dirs.setdefault("wheel", candidate_dir)

    if {"setuptools", "wheel"} <= package_dirs.keys():
        return sorted(set(package_dirs.values()))
    return []


def is_setuptools_69_or_newer(wheel_path: pathlib.Path) -> bool:
    match = re.match(r"setuptools-(\d+)", wheel_path.name)
    return bool(match and int(match.group(1)) >= 69)


def test_project_runtime_dependencies_match_contract_requirements() -> None:
    project = load_pyproject()["project"]

    assert project["requires-python"] == ">=3.12"
    assert project["dependencies"] == ["pydantic>=2.5,<3"]


def test_dev_dependencies_match_contract_requirements() -> None:
    optional_dependencies = load_pyproject()["project"]["optional-dependencies"]

    # Per SUBPROJECT_TESTING_STANDARD.md §2.2 + codex review #3 of stage
    # 2.1: the `dev` extra is offline-first (pure-pip only). Any git+URL
    # dependency belongs in a separate extra so the test-fast / smoke
    # CI lanes can stay network-free.
    assert optional_dependencies["dev"] == [
        "pytest>=8",
        "pytest-cov>=4",
    ]


def test_shared_fixtures_extra_pins_audit_eval_to_git_tag() -> None:
    """The shared-fixtures extra is the ONLY place a git+URL dep lives.

    Drift in either the package name or the tag would silently invalidate
    cross-project shared regression — the dependency contract is part of
    the test rollout plan stage 2 baseline, not an internal detail.
    """
    optional_dependencies = load_pyproject()["project"]["optional-dependencies"]

    assert optional_dependencies["shared-fixtures"] == [
        (
            "project-ult-audit-eval @ "
            "git+https://github.com/shenfanjie5-bit/project-ult-audit-eval.git@v0.2.5"
        ),
    ]


def test_setuptools_uses_src_layout_package_discovery() -> None:
    setuptools_config = load_pyproject()["tool"]["setuptools"]

    assert setuptools_config["packages"] == {"find": {"where": ["src"]}}
    assert setuptools_config["package-dir"] == {"": "src"}


def test_console_scripts_point_to_export_and_compat_entrypoints() -> None:
    scripts = load_pyproject()["project"]["scripts"]

    assert scripts == {
        "contracts-export": "contracts.export.__main__:main",
        "contracts-compat": "contracts.compat.__main__:main",
    }


def test_packaging_metadata_does_not_use_scaffold_defaults() -> None:
    pyproject = load_pyproject()

    assert pyproject["project"]["requires-python"] != ">=3.11"
    assert pyproject["project"]["dependencies"]
    assert pyproject["tool"]["setuptools"].get("packages") != []
    assert set(pyproject["project"]["scripts"]) == {
        "contracts-export",
        "contracts-compat",
    }


def test_console_script_entry_points_are_importable_and_invokable(
    tmp_path: pathlib.Path,
) -> None:
    scripts = load_pyproject()["project"]["scripts"]

    for name, entry_point in scripts.items():
        main = load_console_script(name, entry_point)

        if name == "contracts-export":
            assert (
                main(
                    [
                        "--output-dir",
                        str(tmp_path / "json_schema"),
                        "--version",
                        "0.1.0",
                    ]
                )
                == 0
            )
            continue

        baseline_dir = tmp_path / "compat_baseline"
        export_main = load_console_script(
            "contracts-export",
            scripts["contracts-export"],
        )
        assert (
            export_main(
                [
                    "--output-dir",
                    str(baseline_dir),
                    "--version",
                    "0.1.0",
                ]
            )
            == 0
        )
        assert main(["--baseline", str(baseline_dir), "--current", "HEAD"]) == 0


def test_installed_distribution_imports_and_console_scripts_are_invokable(
    tmp_path: pathlib.Path,
) -> None:
    smoke_env = os.environ.copy()
    smoke_env.pop("PYTHONPATH", None)
    smoke_env.pop("VIRTUAL_ENV", None)
    smoke_env["PIP_DISABLE_PIP_VERSION_CHECK"] = "1"
    smoke_env["PIP_CACHE_DIR"] = str(tmp_path / "pip-cache")

    venv_dir = tmp_path / "installed-artifact-venv"
    create_venv = run_subprocess(
        [
            sys.executable,
            "-m",
            "venv",
            "--system-site-packages",
            str(venv_dir),
        ],
        cwd=tmp_path,
        env=smoke_env,
    )
    assert_success(create_venv)

    python_bin = venv_executable(venv_dir, "python")
    install_build_requirements_args = [
        str(python_bin),
        "-m",
        "pip",
        "install",
        *load_pyproject()["build-system"]["requires"],
    ]
    wheel_dirs = local_build_requirement_wheel_dirs()
    if wheel_dirs:
        install_build_requirements_args[4:4] = [
            "--no-index",
            *[
                item
                for wheel_dir in wheel_dirs
                for item in ("--find-links", str(wheel_dir))
            ],
        ]
    install_build_requirements = run_subprocess(
        install_build_requirements_args,
        cwd=tmp_path,
        env=smoke_env,
    )
    assert_success(install_build_requirements)

    install_project = run_subprocess(
        [
            str(python_bin),
            "-m",
            "pip",
            "install",
            "--no-deps",
            "--no-build-isolation",
            "--ignore-installed",
            str(PROJECT_ROOT),
        ],
        cwd=tmp_path,
        env=smoke_env,
    )
    assert_success(install_project)

    installed_metadata = run_subprocess(
        [
            str(python_bin),
            "-c",
            "\n".join(
                [
                    "import importlib.metadata as metadata",
                    "import json",
                    "import contracts",
                    (
                        "distribution = "
                        "metadata.distribution('project-ult-contracts')"
                    ),
                    (
                        "scripts = {entry_point.name: entry_point.value "
                        "for entry_point in distribution.entry_points "
                        "if entry_point.group == 'console_scripts'}"
                    ),
                    (
                        "print(json.dumps({"
                        "'package': contracts.__name__, "
                        "'version': contracts.__version__, "
                        "'location': "
                        "str(distribution.locate_file('').resolve()), "
                        "'scripts': scripts"
                        "}, sort_keys=True))"
                    ),
                ]
            ),
        ],
        cwd=tmp_path,
        env=smoke_env,
    )
    assert_success(installed_metadata)
    metadata = json.loads(installed_metadata.stdout)
    install_location = pathlib.Path(metadata.pop("location"))
    assert install_location.is_relative_to(venv_dir.resolve())
    assert metadata == {
        "package": "contracts",
        "version": "0.1.3",
        "scripts": {
            "contracts-export": "contracts.export.__main__:main",
            "contracts-compat": "contracts.compat.__main__:main",
        },
    }

    contracts_export = venv_executable(venv_dir, "contracts-export")
    contracts_compat = venv_executable(venv_dir, "contracts-compat")
    assert contracts_export.is_file()
    assert contracts_compat.is_file()

    baseline_dir = tmp_path / "installed-baseline"
    export_result = run_subprocess(
        [
            str(contracts_export),
            "--output-dir",
            str(baseline_dir),
            "--version",
            "0.1.0",
        ],
        cwd=tmp_path,
        env=smoke_env,
    )
    assert_success(export_result)
    assert (baseline_dir / "manifest.json").is_file()

    compat_result = run_subprocess(
        [
            str(contracts_compat),
            "--baseline",
            str(baseline_dir),
            "--current",
            "HEAD",
        ],
        cwd=tmp_path,
        env=smoke_env,
    )
    assert_success(compat_result)

    packaged_baseline_result = run_subprocess(
        [
            str(contracts_compat),
            "--baseline",
            "0.1.0",
            "--current",
            "HEAD",
        ],
        cwd=tmp_path,
        env=smoke_env,
    )
    assert_success(packaged_baseline_result)


def test_package_discovery_configuration_includes_contracts_tree() -> None:
    setuptools_config = load_pyproject()["tool"]["setuptools"]
    find_config = setuptools_config["packages"]["find"]
    where_dirs = [PROJECT_ROOT / path for path in find_config["where"]]

    discovered_packages = {
        ".".join(init_path.parent.relative_to(where_dir).parts)
        for where_dir in where_dirs
        for init_path in where_dir.rglob("__init__.py")
    }

    assert setuptools_config["package-dir"] == {"": "src"}
    assert {
        "contracts",
        "contracts.compat",
        "contracts.core",
        "contracts.export",
        "contracts.protocols",
        "contracts.schemas",
    } <= discovered_packages


def test_contract_package_skeleton_is_importable() -> None:
    sys.path.insert(0, str(SRC_DIR))
    try:
        imported_modules = [
            importlib.import_module(module_name)
            for module_name in [
                "contracts",
                "contracts.core",
                "contracts.errors",
                "contracts.protocols",
                "contracts.schemas",
                "contracts.export",
                "contracts.compat",
            ]
        ]
    finally:
        sys.path.remove(str(SRC_DIR))

    assert [module.__name__ for module in imported_modules] == [
        "contracts",
        "contracts.core",
        "contracts.errors",
        "contracts.protocols",
        "contracts.schemas",
        "contracts.export",
        "contracts.compat",
    ]


def test_contract_root_exports_public_skeleton_modules() -> None:
    sys.path.insert(0, str(SRC_DIR))
    try:
        contracts = importlib.import_module("contracts")
    finally:
        sys.path.remove(str(SRC_DIR))

    assert contracts.__all__ == [
        "core",
        "errors",
        "protocols",
        "schemas",
        "__version__",
    ]
    assert isinstance(contracts.__version__, str)
    assert contracts.__version__


def test_export_cli_module_runs_successfully(tmp_path: pathlib.Path) -> None:
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(SRC_DIR)
    output_dir = tmp_path / "json_schema"

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "contracts.export",
            "--output-dir",
            str(output_dir),
            "--version",
            "0.1.0",
        ],
        cwd=PROJECT_ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert (output_dir / "manifest.json").is_file()


def test_compat_cli_module_requires_baseline_argument() -> None:
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(SRC_DIR)

    result = subprocess.run(
        [sys.executable, "-m", "contracts.compat"],
        cwd=PROJECT_ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    assert "the following arguments are required: --baseline" in result.stderr


def test_contract_init_modules_have_chinese_docstrings() -> None:
    init_paths = [
        SRC_DIR / "contracts" / "__init__.py",
        SRC_DIR / "contracts" / "core" / "__init__.py",
        SRC_DIR / "contracts" / "protocols" / "__init__.py",
        SRC_DIR / "contracts" / "schemas" / "__init__.py",
        SRC_DIR / "contracts" / "export" / "__init__.py",
        SRC_DIR / "contracts" / "compat" / "__init__.py",
    ]

    for init_path in init_paths:
        module = compile(init_path.read_text(encoding="utf-8"), str(init_path), "exec")
        docstring = module.co_consts[0]

        assert isinstance(docstring, str)
        assert any("\u4e00" <= character <= "\u9fff" for character in docstring)


def test_no_undefined_top_level_contract_files() -> None:
    disallowed_files = [
        SRC_DIR / "contracts" / "legacy.py",
        SRC_DIR / "contracts" / "utils.py",
    ]

    for disallowed_file in disallowed_files:
        assert not disallowed_file.exists()


def test_no_disallowed_schema_maintenance_dependencies() -> None:
    project = load_pyproject()["project"]
    dependencies = list(project["dependencies"])
    for optional_group in project["optional-dependencies"].values():
        dependencies.extend(optional_group)

    dependency_text = "\n".join(dependencies)

    assert dependency_text.count("pydantic") == 1
    assert "avro" not in dependency_text.lower()
    assert "jsonschema-manual" not in dependency_text.lower()


def test_ci_script_is_executable_and_runs_stage_two_checks() -> None:
    ci_script = PROJECT_ROOT / "scripts" / "ci.sh"
    script = ci_script.read_text(encoding="utf-8")

    assert os.access(ci_script, os.X_OK)
    assert "set -euo pipefail" in script
    assert "-m pip install -e '.[dev,shared-fixtures]'" in script
    assert "PYTHONPATH" not in script
    assert "contracts, contracts.schemas, contracts.protocols" in script
    assert "contracts.__version__" in script
    assert "CONTRACTS_VERSION:-0.1.0" not in script
    assert "-m pytest --collect-only -q" in script
    assert "-m pytest -q" in script
    assert "-m contracts.export" in script
    assert "-m contracts.compat" in script
    assert "CONTRACTS_BASELINE" in script
