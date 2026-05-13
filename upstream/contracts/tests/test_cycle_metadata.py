from __future__ import annotations

import importlib
import pathlib
import sys
from datetime import datetime, timedelta, timezone

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
        "cycle_id": "cycle-20260415-001",
        "phase": "collecting",
        "started_at": datetime(2026, 4, 15, 12, 0, tzinfo=timezone.utc),
    }


def test_cycle_metadata_public_api_imports() -> None:
    schemas = import_schemas()

    from contracts.schemas import CycleMetadata, CyclePhase

    assert CycleMetadata is schemas.CycleMetadata
    assert CyclePhase is schemas.CyclePhase
    assert "CycleMetadata" in schemas.__all__
    assert "CyclePhase" in schemas.__all__


def test_cycle_phase_values_are_stable() -> None:
    schemas = import_schemas()

    assert {phase.value for phase in schemas.CyclePhase} == {
        "collecting",
        "analyzing",
        "publishing",
        "completed",
        "failed",
    }


def test_cycle_metadata_accepts_in_progress_cycle() -> None:
    schemas = import_schemas()

    cycle = schemas.CycleMetadata.model_validate(valid_payload())

    assert cycle.cycle_id == "cycle-20260415-001"
    assert cycle.phase is schemas.CyclePhase.COLLECTING
    assert cycle.ended_at is None
    assert cycle.previous_cycle_id is None
    assert cycle.version == "0.1.3"


def test_cycle_metadata_accepts_finished_cycle() -> None:
    schemas = import_schemas()
    ended_at = datetime(2026, 4, 15, 12, 30, tzinfo=timezone.utc)
    payload = {
        **valid_payload(),
        "phase": "completed",
        "ended_at": ended_at,
        "previous_cycle_id": "cycle-20260415-000",
    }

    cycle = schemas.CycleMetadata.model_validate(payload)

    assert cycle.phase is schemas.CyclePhase.COMPLETED
    assert cycle.ended_at == ended_at
    assert cycle.previous_cycle_id == "cycle-20260415-000"


@pytest.mark.parametrize("field_name", ["cycle_id", "phase", "started_at"])
def test_cycle_metadata_required_fields_are_enforced(field_name: str) -> None:
    schemas = import_schemas()
    payload = valid_payload()
    payload.pop(field_name)

    with pytest.raises(pydantic.ValidationError):
        schemas.CycleMetadata.model_validate(payload)


def test_cycle_metadata_json_schema_marks_core_fields_required() -> None:
    schemas = import_schemas()

    schema = schemas.CycleMetadata.model_json_schema()

    assert set(schema["required"]).issuperset(
        {"cycle_id", "phase", "started_at"}
    )


def test_cycle_metadata_rejects_ended_at_before_started_at() -> None:
    schemas = import_schemas()
    payload = {
        **valid_payload(),
        "ended_at": datetime(2026, 4, 15, 11, 59, tzinfo=timezone.utc),
    }

    with pytest.raises(pydantic.ValidationError, match="ended_at"):
        schemas.CycleMetadata.model_validate(payload)


@pytest.mark.parametrize("field_name", ["started_at", "ended_at"])
def test_cycle_metadata_rejects_naive_datetimes(field_name: str) -> None:
    schemas = import_schemas()
    payload = {**valid_payload(), field_name: datetime(2026, 4, 15, 12, 0)}

    with pytest.raises(pydantic.ValidationError, match="timezone-aware"):
        schemas.CycleMetadata.model_validate(payload)


def test_cycle_metadata_rejects_unknown_phase() -> None:
    schemas = import_schemas()
    payload = {**valid_payload(), "phase": "paused"}

    with pytest.raises(pydantic.ValidationError):
        schemas.CycleMetadata.model_validate(payload)


@pytest.mark.parametrize("previous_cycle_id", [None, "cycle-20260415-000"])
def test_cycle_metadata_accepts_optional_previous_cycle_id(
    previous_cycle_id: object,
) -> None:
    schemas = import_schemas()
    payload = {**valid_payload(), "previous_cycle_id": previous_cycle_id}

    cycle = schemas.CycleMetadata.model_validate(payload)

    assert cycle.previous_cycle_id == previous_cycle_id


def test_cycle_metadata_rejects_empty_previous_cycle_id() -> None:
    schemas = import_schemas()
    payload = {**valid_payload(), "previous_cycle_id": ""}

    with pytest.raises(pydantic.ValidationError):
        schemas.CycleMetadata.model_validate(payload)


def test_cycle_metadata_rejected_assignment_leaves_state_unchanged() -> None:
    schemas = import_schemas()
    started_at = datetime(2026, 4, 15, 12, 0, tzinfo=timezone.utc)
    ended_at = started_at + timedelta(minutes=30)
    cycle = schemas.CycleMetadata.model_validate(
        {
            **valid_payload(),
            "started_at": started_at,
            "ended_at": ended_at,
        }
    )
    original_state = cycle.model_dump()

    with pytest.raises(pydantic.ValidationError):
        cycle.started_at = ended_at + timedelta(seconds=1)
    assert cycle.model_dump() == original_state

    with pytest.raises(pydantic.ValidationError):
        cycle.ended_at = started_at - timedelta(seconds=1)
    assert cycle.model_dump() == original_state
