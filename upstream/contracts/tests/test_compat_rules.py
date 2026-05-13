from __future__ import annotations

import json
import pathlib
import shutil
import sys
from collections.abc import Callable

import pytest


PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_DIR))

from contracts.compat import (  # noqa: E402
    COMPATIBILITY_RULES,
    CompatibilityCheckResult,
    CompatibilityEvent,
    CompatibilityRule,
    compare_schema_sets,
    load_schema_directory,
)
from contracts.core import Severity  # noqa: E402
from contracts.export import export_json_schemas  # noqa: E402


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


def compare_export_dirs(
    baseline: pathlib.Path,
    current: pathlib.Path,
) -> CompatibilityCheckResult:
    return compare_schema_sets(
        load_schema_directory(baseline),
        load_schema_directory(current),
        baseline_label=str(baseline),
        current_label=str(current),
    )


def compare_committed_baseline_to_current(
    current: pathlib.Path,
) -> CompatibilityCheckResult:
    return compare_export_dirs(
        PROJECT_ROOT / "artifacts/baselines/0.1.0/json_schema",
        current,
    )


def export_current_resolution_case_schema(tmp_path: pathlib.Path) -> pathlib.Path:
    current = tmp_path / "current"
    export_json_schemas(current, version="0.1.0")
    return current


def resolution_case_rule(
    schema: dict[str, object],
    decision: str,
) -> dict[str, object]:
    all_of = schema["allOf"]
    assert isinstance(all_of, list)

    for rule in all_of:
        assert isinstance(rule, dict)
        condition = rule["if"]
        assert isinstance(condition, dict)
        properties = condition["properties"]
        assert isinstance(properties, dict)
        decision_schema = properties["decision"]
        assert isinstance(decision_schema, dict)
        if decision_schema.get("const") == decision:
            return rule

    raise AssertionError(f"missing ResolutionCase rule for decision={decision!r}")


def change_types(result: CompatibilityCheckResult) -> set[str]:
    return {event.change_type for event in result.events}


def test_compatibility_models_and_rules_are_contract_models() -> None:
    rule = CompatibilityRule(
        rule_id="example_rule",
        rule_name="Example rule",
        severity=Severity.ERROR,
        description="Example compatibility rule.",
        applies_to=("schema",),
    )
    event = CompatibilityEvent(
        schema_name="ex1_candidate_fact",
        change_type="field_removed",
        json_pointer="/properties/confidence",
        message="field removed",
        breaking=True,
    )
    result = CompatibilityCheckResult(
        baseline="baseline",
        current="current",
        events=(event,),
    )

    assert rule.severity is Severity.ERROR
    assert COMPATIBILITY_RULES
    assert not result.is_compatible


def test_load_schema_directory_reads_manifest_and_rejects_invalid_inputs(
    tmp_path: pathlib.Path,
) -> None:
    baseline, _ = export_schema_pair(tmp_path)

    schemas = load_schema_directory(baseline)

    assert "ex1_candidate_fact" in schemas

    with pytest.raises(ValueError, match="manifest.json not found"):
        load_schema_directory(tmp_path / "missing")

    manifest_path = baseline / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["artifacts"].append(dict(manifest["artifacts"][0]))
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(ValueError, match="duplicate schema name"):
        load_schema_directory(baseline)


def test_load_schema_directory_rejects_missing_schema_file(
    tmp_path: pathlib.Path,
) -> None:
    baseline, _ = export_schema_pair(tmp_path)
    (baseline / "ex1_candidate_fact.schema.json").unlink()

    with pytest.raises(ValueError, match="schema file missing for ex1_candidate_fact"):
        load_schema_directory(baseline)


def test_load_schema_directory_rejects_invalid_json(tmp_path: pathlib.Path) -> None:
    baseline, _ = export_schema_pair(tmp_path)
    (baseline / "ex1_candidate_fact.schema.json").write_text(
        "{not-json",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="invalid JSON"):
        load_schema_directory(baseline)


def test_compare_schema_sets_detects_deleted_schema(tmp_path: pathlib.Path) -> None:
    baseline_dir, _ = export_schema_pair(tmp_path)
    baseline = load_schema_directory(baseline_dir)
    current = dict(baseline)
    current.pop("ex1_candidate_fact")

    result = compare_schema_sets(baseline, current)

    assert not result.is_compatible
    assert any(
        event.schema_name == "ex1_candidate_fact"
        and event.change_type == "schema_removed"
        and event.breaking
        for event in result.events
    )


def test_compare_schema_sets_detects_field_removal(tmp_path: pathlib.Path) -> None:
    baseline, current = export_schema_pair(tmp_path)

    def remove_field(schema: dict[str, object]) -> None:
        properties = schema["properties"]
        assert isinstance(properties, dict)
        properties.pop("confidence")

    mutate_schema(current, "ex1_candidate_fact", remove_field)

    result = compare_export_dirs(baseline, current)

    assert not result.is_compatible
    assert "field_removed" in change_types(result)
    assert any(event.json_pointer == "/properties/confidence" for event in result.events)


def test_compare_schema_sets_detects_required_field_changes(
    tmp_path: pathlib.Path,
) -> None:
    baseline, current = export_schema_pair(tmp_path)

    def remove_required(schema: dict[str, object]) -> None:
        required = schema["required"]
        assert isinstance(required, list)
        required.remove("confidence")

    mutate_schema(current, "ex1_candidate_fact", remove_required)
    removed_result = compare_export_dirs(baseline, current)

    assert not removed_result.is_compatible
    assert "required_field_removed" in change_types(removed_result)

    _, current = export_schema_pair(tmp_path / "required-added")

    def add_required(schema: dict[str, object]) -> None:
        properties = schema["properties"]
        required = schema["required"]
        assert isinstance(properties, dict)
        assert isinstance(required, list)
        properties["producer_note"] = {"type": "string"}
        required.append("producer_note")

    baseline = tmp_path / "required-added" / "baseline"
    mutate_schema(current, "ex1_candidate_fact", add_required)
    added_result = compare_export_dirs(baseline, current)

    assert not added_result.is_compatible
    assert "required_field_added" in change_types(added_result)


def test_compare_schema_sets_records_optional_field_addition(
    tmp_path: pathlib.Path,
) -> None:
    baseline, current = export_schema_pair(tmp_path)

    def add_optional_field(schema: dict[str, object]) -> None:
        properties = schema["properties"]
        assert isinstance(properties, dict)
        properties["producer_note"] = {"type": "string"}

    mutate_schema(current, "ex1_candidate_fact", add_optional_field)

    result = compare_export_dirs(baseline, current)

    assert result.is_compatible
    assert [
        event.change_type
        for event in result.events
        if event.schema_name == "ex1_candidate_fact"
    ] == ["optional_field_added"]


def test_compare_schema_sets_detects_type_ref_and_anyof_changes(
    tmp_path: pathlib.Path,
) -> None:
    baseline, current = export_schema_pair(tmp_path)

    def change_confidence_type(schema: dict[str, object]) -> None:
        properties = schema["properties"]
        assert isinstance(properties, dict)
        confidence = properties["confidence"]
        assert isinstance(confidence, dict)
        confidence["type"] = "string"

    def change_direction_ref(schema: dict[str, object]) -> None:
        properties = schema["properties"]
        assert isinstance(properties, dict)
        direction = properties["direction"]
        assert isinstance(direction, dict)
        direction["$ref"] = "#/$defs/ChangedDirection"

    def change_last_output_anyof(schema: dict[str, object]) -> None:
        properties = schema["properties"]
        assert isinstance(properties, dict)
        last_output_at = properties["last_output_at"]
        assert isinstance(last_output_at, dict)
        last_output_at["anyOf"] = [{"type": "string", "format": "date-time"}]

    mutate_schema(current, "ex1_candidate_fact", change_confidence_type)
    mutate_schema(current, "ex2_candidate_signal", change_direction_ref)
    mutate_schema(current, "ex0_metadata", change_last_output_anyof)

    result = compare_export_dirs(baseline, current)

    assert not result.is_compatible
    assert {
        "field_type_changed",
        "field_ref_changed",
        "field_any_of_changed",
    }.issubset(change_types(result))


def test_compare_schema_sets_detects_runtime_validation_metadata_changes(
    tmp_path: pathlib.Path,
) -> None:
    baseline, current = export_schema_pair(tmp_path)

    def remove_score_strictness(schema: dict[str, object]) -> None:
        properties = schema["properties"]
        assert isinstance(properties, dict)
        score = properties["score"]
        assert isinstance(score, dict)
        score.pop("x-contract-runtime-validation")

    mutate_schema(current, "alpha_result", remove_score_strictness)

    result = compare_export_dirs(baseline, current)

    assert not result.is_compatible
    assert "field_runtime_validation_changed" in change_types(result)


def test_compare_schema_sets_detects_schema_invariant_changes(
    tmp_path: pathlib.Path,
) -> None:
    baseline, current = export_schema_pair(tmp_path)

    def remove_resolution_case_invariants(schema: dict[str, object]) -> None:
        schema.pop("allOf")

    mutate_schema(current, "resolution_case", remove_resolution_case_invariants)

    result = compare_export_dirs(baseline, current)

    assert not result.is_compatible
    assert "schema_invariant_changed" in change_types(result)


def test_compare_schema_sets_allows_resolution_case_unresolved_relaxation(
    tmp_path: pathlib.Path,
) -> None:
    current = export_current_resolution_case_schema(tmp_path)
    result = compare_committed_baseline_to_current(current)

    assert result.is_compatible
    assert not [
        event
        for event in result.events
        if event.schema_name == "resolution_case" and event.breaking
    ]


def test_compare_schema_sets_rejects_extra_resolution_case_all_of_rule(
    tmp_path: pathlib.Path,
) -> None:
    current = export_current_resolution_case_schema(tmp_path)

    def add_extra_rule(schema: dict[str, object]) -> None:
        all_of = schema["allOf"]
        assert isinstance(all_of, list)
        all_of.append(
            {
                "if": {"properties": {"decision": {"const": "matched"}}},
                "then": {"properties": {"confidence": {"minimum": 0.95}}},
            }
        )

    mutate_schema(current, "resolution_case", add_extra_rule)
    result = compare_committed_baseline_to_current(current)

    assert not result.is_compatible
    assert any(
        event.schema_name == "resolution_case"
        and event.change_type == "schema_invariant_changed"
        and event.json_pointer == "/allOf"
        for event in result.events
    )


def test_compare_schema_sets_rejects_missing_resolution_case_all_of_rule(
    tmp_path: pathlib.Path,
) -> None:
    current = export_current_resolution_case_schema(tmp_path)

    def remove_unresolved_rule(schema: dict[str, object]) -> None:
        all_of = schema["allOf"]
        assert isinstance(all_of, list)
        all_of.remove(resolution_case_rule(schema, "unresolved"))

    mutate_schema(current, "resolution_case", remove_unresolved_rule)
    result = compare_committed_baseline_to_current(current)

    assert not result.is_compatible
    assert any(
        event.schema_name == "resolution_case"
        and event.change_type == "schema_invariant_changed"
        and event.json_pointer == "/allOf"
        for event in result.events
    )


@pytest.mark.parametrize("decision", ["matched", "ambiguous"])
@pytest.mark.parametrize("min_items", [None, 2])
def test_compare_schema_sets_rejects_changed_resolution_case_candidate_min_items(
    tmp_path: pathlib.Path,
    decision: str,
    min_items: int | None,
) -> None:
    current = export_current_resolution_case_schema(tmp_path)

    def change_min_items(schema: dict[str, object]) -> None:
        rule = resolution_case_rule(schema, decision)
        then = rule["then"]
        assert isinstance(then, dict)
        properties = then["properties"]
        assert isinstance(properties, dict)
        candidate_entities = properties["candidate_entities"]
        assert isinstance(candidate_entities, dict)
        if min_items is None:
            candidate_entities.pop("minItems")
        else:
            candidate_entities["minItems"] = min_items

    mutate_schema(current, "resolution_case", change_min_items)
    result = compare_committed_baseline_to_current(current)

    assert not result.is_compatible
    assert any(
        event.schema_name == "resolution_case"
        and event.change_type == "schema_invariant_changed"
        and event.json_pointer == "/allOf"
        for event in result.events
    )


def test_compare_schema_sets_compares_enum_values_conservatively(
    tmp_path: pathlib.Path,
) -> None:
    baseline, current = export_schema_pair(tmp_path)

    def remove_enum_value(schema: dict[str, object]) -> None:
        defs = schema["$defs"]
        assert isinstance(defs, dict)
        direction = defs["Direction"]
        assert isinstance(direction, dict)
        enum_values = direction["enum"]
        assert isinstance(enum_values, list)
        enum_values.remove("neutral")

    mutate_schema(current, "ex2_candidate_signal", remove_enum_value)
    removed_result = compare_export_dirs(baseline, current)

    assert not removed_result.is_compatible
    assert "enum_value_removed" in change_types(removed_result)
    assert any(
        event.json_pointer == "/$defs/Direction/enum"
        for event in removed_result.events
    )

    baseline, current = export_schema_pair(tmp_path / "enum-added")

    def add_enum_value(schema: dict[str, object]) -> None:
        defs = schema["$defs"]
        assert isinstance(defs, dict)
        direction = defs["Direction"]
        assert isinstance(direction, dict)
        enum_values = direction["enum"]
        assert isinstance(enum_values, list)
        enum_values.append("sideways")

    mutate_schema(current, "ex2_candidate_signal", add_enum_value)
    added_result = compare_export_dirs(baseline, current)

    assert added_result.is_compatible
    assert "enum_value_added" in change_types(added_result)
