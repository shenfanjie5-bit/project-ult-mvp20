from __future__ import annotations

import pathlib
import sys
from datetime import datetime, timedelta, timezone

import pydantic
import pytest


PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from contracts.core import Zone
from contracts.errors import ContractError, ErrorCode
from contracts.schemas import (
    FORMAL_OBJECT_REGISTRY,
    AlphaResultSnapshot,
    AuditRecord,
    CycleMetadata,
    CyclePhase,
    DashboardSnapshot,
    FormalObjectBase,
    FormalObjectName,
    OfficialAlphaPool,
    RecommendationSnapshot,
    ReplayRecord,
    Report,
    WorldStateSnapshot,
    get_formal_object_model,
)


STARTED_AT = datetime(2026, 4, 15, 12, 0, tzinfo=timezone.utc)
EXPECTED_FORMAL_OBJECT_MODELS: dict[
    FormalObjectName, type[FormalObjectBase]
] = {
    FormalObjectName.WORLD_STATE_SNAPSHOT: WorldStateSnapshot,
    FormalObjectName.OFFICIAL_ALPHA_POOL: OfficialAlphaPool,
    FormalObjectName.ALPHA_RESULT_SNAPSHOT: AlphaResultSnapshot,
    FormalObjectName.RECOMMENDATION_SNAPSHOT: RecommendationSnapshot,
    FormalObjectName.DASHBOARD_SNAPSHOT: DashboardSnapshot,
    FormalObjectName.REPORT: Report,
    FormalObjectName.AUDIT_RECORD: AuditRecord,
    FormalObjectName.REPLAY_RECORD: ReplayRecord,
}


def valid_formal_object_payload(name: FormalObjectName) -> dict[str, object]:
    return {
        "object_id": f"{name.value}-001",
        "version": "0.1.0",
        "created_at": STARTED_AT,
        "payload": {"object_name": name.value},
    }


def valid_cycle_payload() -> dict[str, object]:
    return {
        "cycle_id": "cycle-20260415-001",
        "phase": CyclePhase.COLLECTING,
        "started_at": STARTED_AT,
    }


def test_formal_object_registry_is_exact() -> None:
    assert set(FORMAL_OBJECT_REGISTRY) == set(FormalObjectName)
    assert dict(FORMAL_OBJECT_REGISTRY) == EXPECTED_FORMAL_OBJECT_MODELS
    assert len(FORMAL_OBJECT_REGISTRY) == 8

    for name, model in EXPECTED_FORMAL_OBJECT_MODELS.items():
        assert get_formal_object_model(name) is model
        assert get_formal_object_model(name.value) is model


def test_backtest_result_is_not_a_formal_object() -> None:
    assert "backtest_result" not in {name.value for name in FormalObjectName}
    assert "backtest_result" not in {
        name.value for name in FORMAL_OBJECT_REGISTRY
    }

    with pytest.raises(ValueError):
        FormalObjectName("backtest_result")

    with pytest.raises(ContractError) as exc_info:
        get_formal_object_model("backtest_result")

    assert exc_info.value.code is ErrorCode.UNKNOWN_FORMAL_OBJECT
    assert exc_info.value.details == {"object_name": "backtest_result"}


def test_each_formal_object_model_validates_minimal_payload() -> None:
    for name, model in EXPECTED_FORMAL_OBJECT_MODELS.items():
        instance = model.model_validate(valid_formal_object_payload(name))

        assert instance.object_name is name
        assert instance.object_id == f"{name.value}-001"
        assert instance.zone is Zone.FORMAL
        assert instance.cycle_id is None
        assert instance.payload == {"object_name": name.value}


@pytest.mark.parametrize(
    "field_name",
    ["object_id", "version", "created_at", "payload"],
)
def test_formal_object_envelope_requires_core_fields(field_name: str) -> None:
    payload = valid_formal_object_payload(FormalObjectName.REPORT)
    payload.pop(field_name)

    with pytest.raises(pydantic.ValidationError):
        Report.model_validate(payload)


def test_formal_object_zone_is_fixed_to_formal() -> None:
    payload = {
        **valid_formal_object_payload(FormalObjectName.REPORT),
        "zone": Zone.ANALYTICAL,
    }

    with pytest.raises(pydantic.ValidationError):
        Report.model_validate(payload)


def test_cycle_metadata_phase_enum_is_exact() -> None:
    assert {phase.value for phase in CyclePhase} == {
        "collecting",
        "analyzing",
        "publishing",
        "completed",
        "failed",
    }


def test_cycle_metadata_time_constraints() -> None:
    in_progress = CycleMetadata.model_validate(valid_cycle_payload())
    assert in_progress.phase is CyclePhase.COLLECTING
    assert in_progress.ended_at is None

    ended_at = STARTED_AT + timedelta(minutes=30)
    completed = CycleMetadata.model_validate(
        {
            **valid_cycle_payload(),
            "phase": CyclePhase.COMPLETED,
            "ended_at": ended_at,
        }
    )
    assert completed.ended_at == ended_at

    with pytest.raises(pydantic.ValidationError, match="ended_at"):
        CycleMetadata.model_validate(
            {**valid_cycle_payload(), "ended_at": STARTED_AT - timedelta(seconds=1)}
        )


@pytest.mark.parametrize("phase", ["paused", ""])
def test_cycle_metadata_rejects_unknown_phase(phase: str) -> None:
    with pytest.raises(pydantic.ValidationError):
        CycleMetadata.model_validate({**valid_cycle_payload(), "phase": phase})


@pytest.mark.parametrize("field_name", ["started_at", "ended_at"])
def test_cycle_metadata_rejects_naive_datetimes(field_name: str) -> None:
    payload = {
        **valid_cycle_payload(),
        field_name: datetime(2026, 4, 15, 12, 0),
    }

    with pytest.raises(pydantic.ValidationError, match="timezone-aware"):
        CycleMetadata.model_validate(payload)


@pytest.mark.parametrize("previous_cycle_id", ["", "   "])
def test_cycle_metadata_rejects_empty_previous_cycle_id(
    previous_cycle_id: str,
) -> None:
    payload = {**valid_cycle_payload(), "previous_cycle_id": previous_cycle_id}

    with pytest.raises(pydantic.ValidationError):
        CycleMetadata.model_validate(payload)


def test_cycle_metadata_accepts_previous_cycle_id() -> None:
    payload = {
        **valid_cycle_payload(),
        "previous_cycle_id": "cycle-20260415-000",
    }

    cycle = CycleMetadata.model_validate(payload)

    assert cycle.previous_cycle_id == "cycle-20260415-000"


def test_formal_and_cycle_json_schema_generation() -> None:
    for model in (*EXPECTED_FORMAL_OBJECT_MODELS.values(), CycleMetadata):
        schema = model.model_json_schema()

        assert schema["type"] == "object"
        assert "properties" in schema
