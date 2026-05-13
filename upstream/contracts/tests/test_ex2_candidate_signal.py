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
        "signal_id": "signal-1",
        "signal_type": "sentiment_shift",
        "direction": "bullish",
        "magnitude": 0.4,
        "affected_entities": ["AAPL"],
        "affected_sectors": ["technology"],
        "time_horizon": "short_term",
        "evidence": ["fact-1"],
        "confidence": 0.7,
        "subsystem_id": "subsystem-news",
    }


def test_ex2_candidate_signal_public_api_imports() -> None:
    schemas = import_schemas()

    from contracts.schemas import Ex2CandidateSignal

    assert Ex2CandidateSignal is schemas.Ex2CandidateSignal
    assert "Ex2CandidateSignal" in schemas.__all__


def test_ex2_candidate_signal_accepts_valid_payload() -> None:
    schemas = import_schemas()

    signal = schemas.Ex2CandidateSignal.model_validate(valid_payload())

    assert signal.signal_id == "signal-1"
    assert signal.signal_type == "sentiment_shift"
    assert signal.direction.value == "bullish"
    assert signal.magnitude == 0.4
    assert signal.affected_entities == ["AAPL"]
    assert signal.affected_sectors == ["technology"]
    assert signal.time_horizon == "short_term"
    assert signal.evidence == ["fact-1"]
    assert signal.confidence == 0.7
    assert signal.subsystem_id == "subsystem-news"


@pytest.mark.parametrize(
    "field_name",
    [
        # v0.1.3: affected_sectors STAYS required (presence guaranteed for
        # consumers). What changed: list min_length=1 → no min_length, so
        # empty list [] is now valid. Positive coverage:
        # test_ex_payloads.py::test_ex2_affected_sectors_empty_list_is_valid.
        "signal_id",
        "signal_type",
        "direction",
        "magnitude",
        "affected_entities",
        "affected_sectors",
        "time_horizon",
        "evidence",
        "confidence",
        "subsystem_id",
    ],
)
def test_ex2_candidate_signal_required_fields_are_enforced(
    field_name: str,
) -> None:
    schemas = import_schemas()
    payload = valid_payload()
    payload.pop(field_name)

    with pytest.raises(pydantic.ValidationError):
        schemas.Ex2CandidateSignal.model_validate(payload)


@pytest.mark.parametrize(
    ("field_name", "field_value"),
    [
        ("signal_type", ""),
        ("direction", "sideways"),
        ("magnitude", -0.01),
        ("affected_entities", []),
        # affected_sectors=[] is now ACCEPTED as of v0.1.3 (field stays
        # required, but list-level min_length=1 constraint was removed;
        # element SectorId min_length=1 still applies). Positive coverage
        # in test_ex_payloads.py::test_ex2_affected_sectors_empty_list_is_valid.
        ("time_horizon", ""),
        ("evidence", []),
        ("confidence", -0.01),
        ("confidence", 1.01),
    ],
)
def test_ex2_candidate_signal_rejects_invalid_field_values(
    field_name: str,
    field_value: object,
) -> None:
    schemas = import_schemas()
    payload = {**valid_payload(), field_name: field_value}

    with pytest.raises(pydantic.ValidationError):
        schemas.Ex2CandidateSignal.model_validate(payload)


@pytest.mark.parametrize("field_name", ["submitted_at", "ingest_seq"])
def test_ex2_candidate_signal_rejects_ingest_metadata(field_name: str) -> None:
    schemas = import_schemas()
    payload = {
        **valid_payload(),
        field_name: datetime(2026, 4, 15, 12, 5, tzinfo=timezone.utc),
    }

    with pytest.raises(pydantic.ValidationError, match="ingest metadata"):
        schemas.Ex2CandidateSignal.model_validate(payload)


def test_ex2_candidate_signal_json_schema_contract() -> None:
    schemas = import_schemas()

    schema = schemas.Ex2CandidateSignal.model_json_schema()

    assert set(schema["required"]).issuperset(
        {
            # v0.1.3: affected_sectors STAYS required (presence preserved
            # for consumers); list min_length=1 was the only relaxation.
            "signal_id",
            "signal_type",
            "direction",
            "magnitude",
            "affected_entities",
            "affected_sectors",
            "time_horizon",
            "evidence",
            "confidence",
            "subsystem_id",
        }
    )
    assert schemas.FORBIDDEN_INGEST_METADATA_FIELDS.isdisjoint(schema["properties"])
    assert schema["properties"]["direction"] == {"$ref": "#/$defs/Direction"}
    assert set(schema["$defs"]["Direction"]["enum"]) == {
        "bullish",
        "bearish",
        "neutral",
    }
