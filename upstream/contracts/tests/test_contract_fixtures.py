from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest
from pydantic import BaseModel, ValidationError


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from contracts.core import __version__
from contracts.errors import ContractError, ErrorCode
from contracts.export import SCHEMA_MODEL_REGISTRY, export_json_schemas
from contracts.schemas import (
    FORBIDDEN_INGEST_METADATA_FIELDS,
    FORMAL_OBJECT_NAMES,
    get_formal_object_model,
)


FIXTURES_ROOT = PROJECT_ROOT / "fixtures"
MANIFEST_PATH = FIXTURES_ROOT / "manifest.json"
EXPECTED_CONSUMERS = {"data-platform", "subsystem-sdk", "main-core"}
REQUIRED_MANIFEST_FIELDS = {
    "path",
    "model",
    "schema_name",
    "valid",
    "consumer",
}
EXPECTED_EXCEPTION_TYPES = {
    "pydantic.ValidationError": ValidationError,
    "contracts.errors.ContractError": ContractError,
}
VALIDATION_STRATEGIES = {"direct_model", "formal_object_registry"}


def load_fixture(path: Path) -> dict[str, object]:
    data = json.loads(path.read_text(encoding="utf-8"))

    assert isinstance(data, dict), f"{path} must contain a JSON object"
    return data


def resolve_model(import_path: str) -> type[BaseModel]:
    module_path, _, model_name = import_path.rpartition(".")

    assert module_path, f"invalid model import path: {import_path}"
    assert model_name, f"invalid model import path: {import_path}"

    module = importlib.import_module(module_path)
    model = getattr(module, model_name)

    assert isinstance(model, type), f"{import_path} is not a class"
    assert issubclass(model, BaseModel), f"{import_path} is not a Pydantic model"
    return model


def manifest_entries() -> list[dict[str, object]]:
    manifest = load_fixture(MANIFEST_PATH)
    fixtures = manifest.get("fixtures")

    assert manifest.get("version") == __version__
    assert isinstance(fixtures, list)
    assert fixtures

    entries: list[dict[str, object]] = []
    for entry in fixtures:
        assert isinstance(entry, dict)
        entries.append(entry)

    return entries


def fixture_path(entry: dict[str, object]) -> Path:
    path_value = entry.get("path")

    assert isinstance(path_value, str)
    relative_path = Path(path_value)
    assert not relative_path.is_absolute()
    return FIXTURES_ROOT / relative_path


def validate_fixture_payload(
    entry: dict[str, object], payload: dict[str, object]
) -> BaseModel:
    model = resolve_model(str(entry["model"]))
    strategy = str(entry.get("validation", "direct_model"))

    if strategy == "direct_model":
        return model.model_validate(payload)

    if strategy == "formal_object_registry":
        object_name = payload.get("object_name")
        if not isinstance(object_name, str):
            return model.model_validate(payload)

        registry_model = get_formal_object_model(object_name)
        assert registry_model is model
        return registry_model.model_validate(payload)

    raise AssertionError(f"unsupported fixture validation strategy: {strategy}")


def contains_value(data: object, expected: str) -> bool:
    if data == expected:
        return True

    if isinstance(data, dict):
        return any(contains_value(value, expected) for value in data.values())

    if isinstance(data, list):
        return any(contains_value(value, expected) for value in data)

    return False


def test_manifest_shape_and_registry_alignment() -> None:
    seen_paths: set[str] = set()

    for entry in manifest_entries():
        assert REQUIRED_MANIFEST_FIELDS.issubset(entry)
        assert isinstance(entry["valid"], bool)

        path = fixture_path(entry)
        assert path.is_file()
        assert path.suffix == ".json"
        assert str(entry["path"]) not in seen_paths
        seen_paths.add(str(entry["path"]))

        consumer = entry["consumer"]
        assert isinstance(consumer, list)
        assert set(consumer) == EXPECTED_CONSUMERS

        strategy = str(entry.get("validation", "direct_model"))
        assert strategy in VALIDATION_STRATEGIES

        schema_name = str(entry["schema_name"])
        model = resolve_model(str(entry["model"]))
        assert schema_name in SCHEMA_MODEL_REGISTRY
        assert SCHEMA_MODEL_REGISTRY[schema_name] is model

        if entry["valid"] is False:
            assert entry.get("expected_exception") in EXPECTED_EXCEPTION_TYPES


def test_valid_fixtures_validate_against_declared_models() -> None:
    valid_entries = [entry for entry in manifest_entries() if entry["valid"] is True]

    assert valid_entries
    for entry in valid_entries:
        payload = load_fixture(fixture_path(entry))
        model = resolve_model(str(entry["model"]))
        instance = validate_fixture_payload(entry, payload)

        assert isinstance(instance, model)


def test_invalid_fixtures_raise_expected_exceptions() -> None:
    invalid_entries = [
        entry for entry in manifest_entries() if entry["valid"] is False
    ]

    assert invalid_entries
    for entry in invalid_entries:
        payload = load_fixture(fixture_path(entry))
        expected_exception = EXPECTED_EXCEPTION_TYPES[
            str(entry["expected_exception"])
        ]

        with pytest.raises(expected_exception) as exc_info:
            validate_fixture_payload(entry, payload)

        expected_error_code = entry.get("expected_error_code")
        if expected_error_code is not None:
            assert isinstance(exc_info.value, ContractError)
            assert exc_info.value.code is ErrorCode(str(expected_error_code))


def test_valid_ex_fixtures_do_not_include_ingest_metadata() -> None:
    assert FORBIDDEN_INGEST_METADATA_FIELDS == frozenset(
        {"submitted_at", "ingest_seq"}
    )

    valid_ex_entries = [
        entry
        for entry in manifest_entries()
        if entry["valid"] is True and str(entry["path"]).startswith("valid/ex_payloads/")
    ]
    invalid_ex_entries = [
        entry
        for entry in manifest_entries()
        if entry["valid"] is False
        and str(entry["path"]).startswith("invalid/ex_payloads/")
    ]

    assert len(valid_ex_entries) == 4
    for entry in valid_ex_entries:
        payload = load_fixture(fixture_path(entry))
        assert FORBIDDEN_INGEST_METADATA_FIELDS.isdisjoint(payload)

    invalid_forbidden_fields: set[str] = set()
    for entry in invalid_ex_entries:
        payload = load_fixture(fixture_path(entry))
        invalid_forbidden_fields.update(
            FORBIDDEN_INGEST_METADATA_FIELDS.intersection(payload)
        )

    assert invalid_forbidden_fields == FORBIDDEN_INGEST_METADATA_FIELDS


def test_valid_formal_object_fixtures_cover_closed_object_set() -> None:
    valid_formal_entries = [
        entry
        for entry in manifest_entries()
        if entry["valid"] is True
        and str(entry["path"]).startswith("valid/formal_objects/")
    ]
    expected_names = {name.value for name in FORMAL_OBJECT_NAMES}
    fixture_names = {
        str(load_fixture(fixture_path(entry))["object_name"])
        for entry in valid_formal_entries
    }

    assert len(valid_formal_entries) == 8
    assert fixture_names == expected_names
    assert {str(entry["schema_name"]) for entry in valid_formal_entries} == (
        expected_names
    )


def test_backtest_result_only_appears_in_invalid_fixtures() -> None:
    entries_with_backtest_result: list[dict[str, object]] = []

    for entry in manifest_entries():
        payload = load_fixture(fixture_path(entry))
        if contains_value(payload, "backtest_result"):
            entries_with_backtest_result.append(entry)

    assert entries_with_backtest_result
    assert {
        str(entry["path"]) for entry in entries_with_backtest_result
    } == {"invalid/formal_objects/backtest_result_unknown.json"}
    assert all(entry["valid"] is False for entry in entries_with_backtest_result)


def test_exported_schema_artifacts_cover_valid_fixture_schema_names(
    tmp_path: Path,
) -> None:
    export_json_schemas(tmp_path, version=__version__)
    export_manifest = load_fixture(tmp_path / "manifest.json")
    artifacts = export_manifest["artifacts"]

    assert isinstance(artifacts, list)
    exported_schema_names = {
        artifact["name"] for artifact in artifacts if isinstance(artifact, dict)
    }
    valid_schema_names = {
        str(entry["schema_name"])
        for entry in manifest_entries()
        if entry["valid"] is True
    }

    assert valid_schema_names <= exported_schema_names
    for schema_name in valid_schema_names:
        assert (tmp_path / f"{schema_name}.schema.json").is_file()


def test_all_fixture_json_files_parse_as_standard_json_objects() -> None:
    json_files = sorted(FIXTURES_ROOT.rglob("*.json"))

    assert json_files
    for path in json_files:
        load_fixture(path)
