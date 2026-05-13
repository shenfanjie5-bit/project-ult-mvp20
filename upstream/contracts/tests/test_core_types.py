from __future__ import annotations

import importlib
import pathlib
import sys
from datetime import datetime, timezone

import pydantic
import pytest


PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"


def import_core() -> object:
    sys.path.insert(0, str(SRC_DIR))
    try:
        return importlib.import_module("contracts.core")
    finally:
        sys.path.remove(str(SRC_DIR))


def test_core_reexports_shared_types() -> None:
    core = import_core()

    for public_name in [
        "ContractBaseModel",
        "ExType",
        "Direction",
        "Severity",
        "Zone",
        "HeartbeatStatus",
        "EntityId",
        "SubsystemId",
        "CycleId",
        "FactId",
        "SignalId",
        "DeltaId",
        "NodeId",
        "EvidenceRef",
        "VersionString",
        "SectorId",
        "AwareDatetime",
        "Confidence",
        "Score",
        "Magnitude",
    ]:
        assert hasattr(core, public_name)
        assert public_name in core.__all__


def test_shared_enum_values_are_stable() -> None:
    core = import_core()

    assert core.ExType.EX_0.value == "Ex-0"
    assert core.ExType.EX_1.value == "Ex-1"
    assert core.ExType.EX_2.value == "Ex-2"
    assert core.ExType.EX_3.value == "Ex-3"
    assert core.Direction.BULLISH.value == "bullish"
    assert core.Direction.BEARISH.value == "bearish"
    assert core.Direction.NEUTRAL.value == "neutral"
    assert core.Severity.ERROR.value == "error"
    assert core.Severity.WARNING.value == "warning"
    assert core.Severity.INFO.value == "info"
    assert core.Zone.FORMAL.value == "formal"
    assert core.Zone.ANALYTICAL.value == "analytical"
    assert core.HeartbeatStatus.OK.value == "ok"
    assert core.HeartbeatStatus.DEGRADED.value == "degraded"
    assert core.HeartbeatStatus.FAILED.value == "failed"


def test_contract_base_model_forbids_unknown_fields() -> None:
    core = import_core()

    class ExampleContract(core.ContractBaseModel):
        entity_id: core.EntityId

    with pytest.raises(pydantic.ValidationError):
        ExampleContract(entity_id="entity-1", unexpected="value")


def test_contract_base_model_strips_strings_and_validates_assignment() -> None:
    core = import_core()

    class ExampleContract(core.ContractBaseModel):
        entity_id: core.EntityId
        confidence: core.Confidence

    contract = ExampleContract(entity_id=" entity-1 ", confidence=0.5)

    assert contract.entity_id == "entity-1"

    with pytest.raises(pydantic.ValidationError):
        contract.confidence = 1.1


def test_aware_datetime_rejects_naive_datetimes_with_stable_error_code() -> None:
    core = import_core()

    class TimestampContract(core.ContractBaseModel):
        observed_at: core.AwareDatetime

    assert TimestampContract(
        observed_at=datetime(2026, 4, 15, 12, 0, tzinfo=timezone.utc)
    ).observed_at.tzinfo is not None

    with pytest.raises(
        pydantic.ValidationError,
        match="CONTRACT_VALIDATION_ERROR",
    ):
        TimestampContract(observed_at=datetime(2026, 4, 15, 12, 0))


def test_identifier_aliases_reject_empty_strings() -> None:
    core = import_core()

    class IdentifierContract(core.ContractBaseModel):
        entity_id: core.EntityId
        subsystem_id: core.SubsystemId
        cycle_id: core.CycleId
        fact_id: core.FactId
        signal_id: core.SignalId
        delta_id: core.DeltaId
        node_id: core.NodeId
        evidence_ref: core.EvidenceRef
        version: core.VersionString
        sector_id: core.SectorId

    valid_payload = {
        "entity_id": "entity-1",
        "subsystem_id": "subsystem-1",
        "cycle_id": "cycle-1",
        "fact_id": "fact-1",
        "signal_id": "signal-1",
        "delta_id": "delta-1",
        "node_id": "node-1",
        "evidence_ref": "evidence-1",
        "version": "0.1.0",
        "sector_id": "technology",
    }

    contract = IdentifierContract(**valid_payload)

    assert contract.entity_id == "entity-1"

    for field_name in valid_payload:
        invalid_payload = {**valid_payload, field_name: ""}
        with pytest.raises(pydantic.ValidationError):
            IdentifierContract(**invalid_payload)


@pytest.mark.parametrize("confidence", [-0.01, 1.01])
def test_confidence_rejects_values_outside_unit_interval(confidence: float) -> None:
    core = import_core()

    class ConfidenceContract(core.ContractBaseModel):
        confidence: core.Confidence

    with pytest.raises(pydantic.ValidationError):
        ConfidenceContract(confidence=confidence)


@pytest.mark.parametrize(
    "confidence",
    [True, "0.5", float("inf"), float("-inf"), float("nan")],
)
def test_confidence_rejects_coerced_or_non_finite_values(
    confidence: object,
) -> None:
    core = import_core()

    class ConfidenceContract(core.ContractBaseModel):
        confidence: core.Confidence

    with pytest.raises(pydantic.ValidationError):
        ConfidenceContract(confidence=confidence)


def test_magnitude_rejects_negative_values() -> None:
    core = import_core()

    class MagnitudeContract(core.ContractBaseModel):
        magnitude: core.Magnitude

    assert MagnitudeContract(magnitude=0).magnitude == 0.0

    with pytest.raises(pydantic.ValidationError):
        MagnitudeContract(magnitude=-0.01)


@pytest.mark.parametrize(
    "magnitude",
    [True, "0.5", float("inf"), float("nan")],
)
def test_magnitude_rejects_coerced_or_non_finite_values(
    magnitude: object,
) -> None:
    core = import_core()

    class MagnitudeContract(core.ContractBaseModel):
        magnitude: core.Magnitude

    with pytest.raises(pydantic.ValidationError):
        MagnitudeContract(magnitude=magnitude)


@pytest.mark.parametrize("score", [-1.01, 1.01])
def test_score_rejects_values_outside_signed_unit_interval(score: float) -> None:
    core = import_core()

    class ScoreContract(core.ContractBaseModel):
        score: core.Score

    with pytest.raises(pydantic.ValidationError):
        ScoreContract(score=score)


@pytest.mark.parametrize(
    "score",
    [True, "0.5", float("inf"), float("-inf"), float("nan")],
)
def test_score_rejects_coerced_or_non_finite_values(score: object) -> None:
    core = import_core()

    class ScoreContract(core.ContractBaseModel):
        score: core.Score

    with pytest.raises(pydantic.ValidationError):
        ScoreContract(score=score)
