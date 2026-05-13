from __future__ import annotations

import json
import pathlib
import shutil
import subprocess
import sys
from collections.abc import Callable

from tests.conftest import (
    PROJECT_ROOT,
    load_console_script,
    prepend_src_path,
    src_pythonpath_env,
)

with prepend_src_path():
    from contracts.export import export_json_schemas


def export_schema_pair(tmp_path: pathlib.Path) -> tuple[pathlib.Path, pathlib.Path]:
    baseline = tmp_path / "baseline"
    current = tmp_path / "current"
    export_json_schemas(baseline, version="0.1.0")
    shutil.copytree(baseline, current)
    return baseline, current


def read_schema(schema_dir: pathlib.Path, schema_name: str) -> dict[str, object]:
    return json.loads(
        (schema_dir / f"{schema_name}.schema.json").read_text(encoding="utf-8")
    )


def write_schema(
    schema_dir: pathlib.Path,
    schema_name: str,
    schema: dict[str, object],
) -> None:
    (schema_dir / f"{schema_name}.schema.json").write_text(
        json.dumps(schema, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def mutate_schema(
    schema_dir: pathlib.Path,
    schema_name: str,
    mutator: Callable[[dict[str, object]], None],
) -> None:
    schema = read_schema(schema_dir, schema_name)
    mutator(schema)
    write_schema(schema_dir, schema_name, schema)


def run_compat(
    baseline: pathlib.Path,
    current: pathlib.Path | str,
    *extra_args: str,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "contracts.compat",
            "--baseline",
            str(baseline),
            "--current",
            str(current),
            *extra_args,
        ],
        cwd=PROJECT_ROOT,
        env=src_pythonpath_env(),
        check=False,
        capture_output=True,
        text=True,
    )


def test_python_module_compat_cli_accepts_head_for_same_source(
    tmp_path: pathlib.Path,
) -> None:
    baseline = tmp_path / "baseline"
    output = tmp_path / "result.json"
    export_json_schemas(baseline, version="0.1.0")

    result = run_compat(baseline, "HEAD", "--output", str(output))

    assert result.returncode == 0, result.stderr
    result_json = json.loads(output.read_text(encoding="utf-8"))
    assert result_json["current"] == "HEAD"
    assert result_json["events"] == []


def test_python_module_compat_cli_accepts_checked_in_baseline_version(
    tmp_path: pathlib.Path,
) -> None:
    output = tmp_path / "result.json"

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "contracts.compat",
            "--baseline",
            "0.1.0",
            "--current",
            "HEAD",
            "--output",
            str(output),
        ],
        cwd=PROJECT_ROOT,
        env=src_pythonpath_env(),
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    result_json = json.loads(output.read_text(encoding="utf-8"))
    assert result_json["baseline"] == "0.1.0"
    assert result_json["current"] == "HEAD"


def test_contracts_compat_entry_point_is_callable(tmp_path: pathlib.Path) -> None:
    main = load_console_script(
        "contracts-compat",
        "contracts.compat.__main__:main",
    )
    baseline = tmp_path / "baseline"
    export_json_schemas(baseline, version="0.1.0")

    assert main(["--baseline", str(baseline), "--current", "HEAD"]) == 0


def test_cli_returns_one_for_deleted_exported_schema_file(
    tmp_path: pathlib.Path,
) -> None:
    baseline, current = export_schema_pair(tmp_path)
    (current / "ex1_candidate_fact.schema.json").unlink()

    result = run_compat(baseline, current)

    assert result.returncode == 1
    assert "INCOMPATIBLE_CONTRACT_CHANGE" in result.stderr
    assert "ex1_candidate_fact" in result.stderr
    assert "schema_removed" in result.stderr


def test_cli_records_optional_field_addition_as_compatible(
    tmp_path: pathlib.Path,
) -> None:
    baseline, current = export_schema_pair(tmp_path)
    output = tmp_path / "result.json"

    def add_optional_field(schema: dict[str, object]) -> None:
        properties = schema["properties"]
        assert isinstance(properties, dict)
        properties["producer_note"] = {"type": "string"}

    mutate_schema(current, "ex1_candidate_fact", add_optional_field)

    result = run_compat(baseline, current, "--output", str(output))

    assert result.returncode == 0, result.stderr
    result_json = json.loads(output.read_text(encoding="utf-8"))
    assert result_json["events"] == [
        {
            "breaking": False,
            "change_type": "optional_field_added",
            "json_pointer": "/properties/producer_note",
            "message": "optional field 'producer_note' was added",
            "schema_name": "ex1_candidate_fact",
        }
    ]


def test_cli_returns_one_for_required_field_addition(
    tmp_path: pathlib.Path,
) -> None:
    baseline, current = export_schema_pair(tmp_path)

    def add_required_field(schema: dict[str, object]) -> None:
        properties = schema["properties"]
        required = schema["required"]
        assert isinstance(properties, dict)
        assert isinstance(required, list)
        properties["producer_note"] = {"type": "string"}
        required.append("producer_note")

    mutate_schema(current, "ex1_candidate_fact", add_required_field)

    result = run_compat(baseline, current)

    assert result.returncode == 1
    assert "INCOMPATIBLE_CONTRACT_CHANGE" in result.stderr
    assert "ex1_candidate_fact" in result.stderr
    assert "/required/producer_note" in result.stderr
    assert "required_field_added" in result.stderr


def test_cli_returns_one_for_type_ref_and_enum_breaking_changes(
    tmp_path: pathlib.Path,
) -> None:
    baseline, current = export_schema_pair(tmp_path)

    def change_confidence_type(schema: dict[str, object]) -> None:
        properties = schema["properties"]
        assert isinstance(properties, dict)
        confidence = properties["confidence"]
        assert isinstance(confidence, dict)
        confidence["type"] = "string"

    def change_direction_ref_and_enum(schema: dict[str, object]) -> None:
        properties = schema["properties"]
        defs = schema["$defs"]
        assert isinstance(properties, dict)
        assert isinstance(defs, dict)
        direction_property = properties["direction"]
        direction_def = defs["Direction"]
        assert isinstance(direction_property, dict)
        assert isinstance(direction_def, dict)
        direction_property["$ref"] = "#/$defs/ChangedDirection"
        enum_values = direction_def["enum"]
        assert isinstance(enum_values, list)
        enum_values.remove("neutral")

    mutate_schema(current, "ex1_candidate_fact", change_confidence_type)
    mutate_schema(current, "ex2_candidate_signal", change_direction_ref_and_enum)

    result = run_compat(baseline, current)

    assert result.returncode == 1
    assert "field_type_changed" in result.stderr
    assert "field_ref_changed" in result.stderr
    assert "enum_value_removed" in result.stderr
    assert "/$defs/Direction/enum" in result.stderr


def test_cli_records_enum_value_addition_as_compatible(
    tmp_path: pathlib.Path,
) -> None:
    baseline, current = export_schema_pair(tmp_path)
    output = tmp_path / "result.json"

    def add_enum_value(schema: dict[str, object]) -> None:
        defs = schema["$defs"]
        assert isinstance(defs, dict)
        direction = defs["Direction"]
        assert isinstance(direction, dict)
        enum_values = direction["enum"]
        assert isinstance(enum_values, list)
        enum_values.append("sideways")

    mutate_schema(current, "ex2_candidate_signal", add_enum_value)

    result = run_compat(baseline, current, "--output", str(output))

    assert result.returncode == 0, result.stderr
    result_json = json.loads(output.read_text(encoding="utf-8"))
    assert result_json["events"][0]["change_type"] == "enum_value_added"
    assert result_json["events"][0]["breaking"] is False
