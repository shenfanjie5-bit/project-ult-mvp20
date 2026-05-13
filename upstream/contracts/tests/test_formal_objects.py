from __future__ import annotations

import importlib
import pathlib
import sys
from datetime import datetime, timezone

import pydantic
import pytest


PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"


def import_schemas() -> object:
    sys.path.insert(0, str(SRC_DIR))
    try:
        return importlib.import_module("contracts.schemas")
    finally:
        sys.path.remove(str(SRC_DIR))


def valid_payload() -> dict[str, object]:
    return {
        "object_id": "formal-object-1",
        "version": "0.1.0",
        "created_at": datetime(2026, 4, 15, 12, 0, tzinfo=timezone.utc),
        "payload": {"status": "ready"},
    }


def test_formal_objects_public_api_imports() -> None:
    schemas = import_schemas()

    for public_name in [
        "FormalObjectName",
        "FormalObjectBase",
        "WorldStateSnapshot",
        "OfficialAlphaPool",
        "AlphaResultSnapshot",
        "RecommendationSnapshot",
        "DashboardSnapshot",
        "Report",
        "AuditRecord",
        "ReplayRecord",
        "FORMAL_OBJECT_REGISTRY",
        "FORMAL_OBJECT_NAMES",
        "get_formal_object_model",
    ]:
        assert hasattr(schemas, public_name)
        assert public_name in schemas.__all__


def test_formal_object_names_are_exactly_the_frozen_set() -> None:
    schemas = import_schemas()

    expected_values = {
        "world_state_snapshot",
        "official_alpha_pool",
        "alpha_result_snapshot",
        "recommendation_snapshot",
        "dashboard_snapshot",
        "report",
        "audit_record",
        "replay_record",
    }

    assert {name.value for name in schemas.FormalObjectName} == expected_values
    assert "backtest_result" not in {
        name.value for name in schemas.FormalObjectName
    }


def test_formal_object_registry_matches_enum_exactly() -> None:
    schemas = import_schemas()

    assert set(schemas.FORMAL_OBJECT_REGISTRY) == set(schemas.FormalObjectName)
    assert tuple(schemas.FORMAL_OBJECT_REGISTRY) == schemas.FORMAL_OBJECT_NAMES
    assert len(schemas.FORMAL_OBJECT_REGISTRY) == 8


def test_each_formal_object_model_can_be_instantiated_from_registry() -> None:
    schemas = import_schemas()
    core = importlib.import_module("contracts.core")

    for object_name, model in schemas.FORMAL_OBJECT_REGISTRY.items():
        instance = model(**valid_payload())

        assert isinstance(instance, schemas.FormalObjectBase)
        assert instance.zone is core.Zone.FORMAL
        assert instance.object_name is object_name
        assert instance.cycle_id is None
        assert instance.payload == {"status": "ready"}


def test_get_formal_object_model_accepts_enum_and_string_names() -> None:
    schemas = import_schemas()

    assert (
        schemas.get_formal_object_model(schemas.FormalObjectName.REPORT)
        is schemas.Report
    )
    assert schemas.get_formal_object_model("report") is schemas.Report


def test_backtest_result_is_rejected_as_unknown_formal_object() -> None:
    schemas = import_schemas()
    errors = importlib.import_module("contracts.errors")

    with pytest.raises(errors.ContractError) as exc_info:
        schemas.get_formal_object_model("backtest_result")

    assert exc_info.value.code is errors.ErrorCode.UNKNOWN_FORMAL_OBJECT
    assert exc_info.value.details == {"object_name": "backtest_result"}


@pytest.mark.parametrize(
    "field_name",
    ["object_id", "version", "created_at", "payload"],
)
def test_formal_object_required_fields_are_enforced(field_name: str) -> None:
    schemas = import_schemas()
    payload = valid_payload()
    payload.pop(field_name)

    with pytest.raises(pydantic.ValidationError):
        schemas.Report(**payload)


def test_formal_object_created_at_must_be_timezone_aware() -> None:
    schemas = import_schemas()
    payload = {
        **valid_payload(),
        "created_at": datetime(2026, 4, 15, 12, 0),
    }

    with pytest.raises(pydantic.ValidationError):
        schemas.Report(**payload)


@pytest.mark.parametrize("object_id", ["", " "])
def test_formal_object_id_must_not_be_blank(object_id: str) -> None:
    schemas = import_schemas()
    payload = {**valid_payload(), "object_id": object_id}

    with pytest.raises(pydantic.ValidationError):
        schemas.Report(**payload)


def test_formal_object_zone_is_fixed_to_formal() -> None:
    schemas = import_schemas()
    payload = {**valid_payload(), "zone": "analytical"}

    with pytest.raises(pydantic.ValidationError):
        schemas.Report(**payload)


def test_formal_object_name_literal_is_fixed_per_model() -> None:
    schemas = import_schemas()
    payload = {**valid_payload(), "object_name": "audit_record"}

    with pytest.raises(pydantic.ValidationError):
        schemas.Report(**payload)
