from __future__ import annotations

import json
import pathlib
import subprocess
import sys

from tests.conftest import PROJECT_ROOT, load_console_script, src_pythonpath_env


def test_python_module_export_cli_writes_json_schemas(tmp_path: pathlib.Path) -> None:
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
        env=src_pythonpath_env(),
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert (output_dir / "manifest.json").is_file()
    assert (output_dir / "ex0_metadata.schema.json").is_file()


def test_contracts_export_entry_point_is_callable(tmp_path: pathlib.Path) -> None:
    main = load_console_script(
        "contracts-export",
        "contracts.export.__main__:main",
    )

    output_dir = tmp_path / "entrypoint_schemas"

    assert main(["--out", str(output_dir), "--version", "0.1.0"]) == 0
    manifest = json.loads(
        (output_dir / "manifest.json").read_text(encoding="utf-8")
    )
    assert "ex0_metadata" in {
        artifact["name"] for artifact in manifest["artifacts"]
    }
