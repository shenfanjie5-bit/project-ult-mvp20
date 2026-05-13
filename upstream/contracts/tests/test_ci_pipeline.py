from __future__ import annotations

import json
import os
import pathlib
import shlex
import shutil
import subprocess
import sys


PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
CI_SCRIPT = PROJECT_ROOT / "scripts" / "ci.sh"
DEFAULT_BASELINE = PROJECT_ROOT / "artifacts" / "baselines" / "0.1.3" / "json_schema"


def ci_python() -> str:
    if sys.prefix != sys.base_prefix:
        return sys.executable

    local_venv_python = PROJECT_ROOT / ".venv" / "bin" / "python"
    if local_venv_python.is_file():
        return str(local_venv_python)

    return sys.executable


def can_import_contracts_without_pythonpath(python_bin: str) -> bool:
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    result = subprocess.run(
        [python_bin, "-c", "import contracts"],
        cwd=PROJECT_ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def make_python_wrapper(
    tmp_path: pathlib.Path,
    python_bin: str,
) -> tuple[str, pathlib.Path]:
    pip_log = tmp_path / "pip-install-args.txt"
    wrapper = tmp_path / "ci-python"
    wrapper.write_text(
        "\n".join(
            [
                "#!/usr/bin/env bash",
                "set -euo pipefail",
                (
                    'if [[ "$#" -ge 4 && "$1" == "-m" '
                    '&& "$2" == "pip" && "$3" == "install" ]]; then'
                ),
                f"  printf '%s\\n' \"$@\" > {shlex.quote(str(pip_log))}",
                "  exit 0",
                "fi",
                f"exec {shlex.quote(python_bin)} \"$@\"",
                "",
            ]
        ),
        encoding="utf-8",
    )
    wrapper.chmod(0o755)
    return str(wrapper), pip_log


def export_baseline(output_dir: pathlib.Path, python_bin: str) -> None:
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(SRC_DIR)

    result = subprocess.run(
        [
            python_bin,
            "-m",
            "contracts.export",
            "--output-dir",
            str(output_dir),
        ],
        cwd=PROJECT_ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr


def run_ci_script(
    baseline: pathlib.Path | None,
    python_bin: str,
    pip_log: pathlib.Path,
    *,
    cwd: pathlib.Path = PROJECT_ROOT,
) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    if can_import_contracts_without_pythonpath(python_bin):
        environment.pop("PYTHONPATH", None)
    else:
        environment["PYTHONPATH"] = str(SRC_DIR)
    existing_pytest_addopts = environment.get("PYTEST_ADDOPTS", "")
    environment["PYTEST_ADDOPTS"] = (
        f"{existing_pytest_addopts} --ignore=tests/test_ci_pipeline.py"
    ).strip()
    environment["PYTHON"] = python_bin
    environment["PIP_DISABLE_PIP_VERSION_CHECK"] = "1"
    if baseline is None:
        environment.pop("CONTRACTS_BASELINE", None)
    else:
        environment["CONTRACTS_BASELINE"] = str(baseline)
    environment.pop("CONTRACTS_VERSION", None)

    result = subprocess.run(
        ["bash", str(CI_SCRIPT)],
        cwd=cwd,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )
    assert pip_log.read_text(encoding="utf-8").splitlines() == [
        "-m",
        "pip",
        "install",
        "-e",
        ".[dev,shared-fixtures]",
    ]
    return result


def add_required_baseline_field(schema_path: pathlib.Path) -> None:
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    properties = schema["properties"]
    required = schema["required"]
    assert isinstance(properties, dict)
    assert isinstance(required, list)

    properties["ci_breaking_required_field"] = {"type": "string"}
    required.append("ci_breaking_required_field")
    schema_path.write_text(
        json.dumps(schema, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def test_ci_script_passes_with_matching_baseline(tmp_path: pathlib.Path) -> None:
    baseline = tmp_path / "baseline"
    python_bin = ci_python()
    export_baseline(baseline, python_bin)
    wrapper_python, pip_log = make_python_wrapper(tmp_path, python_bin)

    result = run_ci_script(baseline, wrapper_python, pip_log)

    assert result.returncode == 0, result.stderr
    assert "tests/test_ci_pipeline.py" not in result.stdout


def test_ci_script_passes_with_default_committed_baseline(
    tmp_path: pathlib.Path,
) -> None:
    python_bin = ci_python()
    wrapper_python, pip_log = make_python_wrapper(tmp_path, python_bin)

    result = run_ci_script(None, wrapper_python, pip_log, cwd=tmp_path)

    assert DEFAULT_BASELINE.is_dir()
    assert result.returncode == 0, result.stderr


def test_ci_script_fails_on_breaking_change(tmp_path: pathlib.Path) -> None:
    baseline = tmp_path / "baseline"
    python_bin = ci_python()
    shutil.copytree(DEFAULT_BASELINE, baseline)
    add_required_baseline_field(baseline / "ex1_candidate_fact.schema.json")
    wrapper_python, pip_log = make_python_wrapper(tmp_path, python_bin)

    result = run_ci_script(baseline, wrapper_python, pip_log)

    assert result.returncode == 1
    assert "INCOMPATIBLE_CONTRACT_CHANGE" in result.stderr
    assert "field_removed" in result.stderr
    assert "ci_breaking_required_field" in result.stderr
