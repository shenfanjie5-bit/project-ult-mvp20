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
        "fact_id": "fact-1",
        "entity_id": "AAPL",
        "fact_type": "earnings",
        "fact_content": {"headline": "sample"},
        "confidence": 0.8,
        "source_reference": {"source": "fixture"},
        "extracted_at": datetime(2026, 4, 15, 12, 0, tzinfo=timezone.utc),
        "subsystem_id": "subsystem-news",
    }


def test_ex1_candidate_fact_public_api_imports() -> None:
    schemas = import_schemas()

    from contracts.schemas import Ex1CandidateFact

    assert Ex1CandidateFact is schemas.Ex1CandidateFact
    assert "Ex1CandidateFact" in schemas.__all__


def test_ex1_candidate_fact_accepts_valid_payload() -> None:
    schemas = import_schemas()

    fact = schemas.Ex1CandidateFact.model_validate(valid_payload())

    assert fact.fact_id == "fact-1"
    assert fact.entity_id == "AAPL"
    assert fact.fact_type == "earnings"
    assert fact.fact_content == {"headline": "sample"}
    assert fact.confidence == 0.8
    assert fact.source_reference == {"source": "fixture"}
    assert fact.extracted_at.tzinfo is not None
    assert fact.extracted_at.tzinfo.utcoffset(fact.extracted_at) is not None
    assert fact.subsystem_id == "subsystem-news"


@pytest.mark.parametrize(
    "field_name",
    [
        "fact_id",
        "entity_id",
        "fact_type",
        "fact_content",
        "confidence",
        "source_reference",
        "extracted_at",
        "subsystem_id",
    ],
)
def test_ex1_candidate_fact_required_fields_are_enforced(field_name: str) -> None:
    schemas = import_schemas()
    payload = valid_payload()
    payload.pop(field_name)

    with pytest.raises(pydantic.ValidationError):
        schemas.Ex1CandidateFact.model_validate(payload)


@pytest.mark.parametrize("confidence", [0.0, 1.0])
def test_ex1_candidate_fact_accepts_confidence_boundaries(
    confidence: float,
) -> None:
    schemas = import_schemas()
    payload = {**valid_payload(), "confidence": confidence}

    fact = schemas.Ex1CandidateFact.model_validate(payload)

    assert fact.confidence == confidence


@pytest.mark.parametrize("confidence", [-0.01, 1.01])
def test_ex1_candidate_fact_rejects_confidence_outside_unit_interval(
    confidence: float,
) -> None:
    schemas = import_schemas()
    payload = {**valid_payload(), "confidence": confidence}

    with pytest.raises(pydantic.ValidationError):
        schemas.Ex1CandidateFact.model_validate(payload)


@pytest.mark.parametrize(
    ("field_name", "field_value", "match"),
    [
        ("fact_type", "", None),
        ("fact_content", {}, "fact_content must not be empty"),
        ("source_reference", {}, "source_reference must not be empty"),
        ("extracted_at", datetime(2026, 4, 15, 12, 0), "timezone-aware"),
    ],
)
def test_ex1_candidate_fact_rejects_invalid_field_values(
    field_name: str,
    field_value: object,
    match: str | None,
) -> None:
    schemas = import_schemas()
    payload = {**valid_payload(), field_name: field_value}

    with pytest.raises(pydantic.ValidationError, match=match):
        schemas.Ex1CandidateFact.model_validate(payload)


@pytest.mark.parametrize("field_name", ["submitted_at", "ingest_seq"])
def test_ex1_candidate_fact_rejects_ingest_metadata(field_name: str) -> None:
    schemas = import_schemas()
    payload = {
        **valid_payload(),
        field_name: datetime(2026, 4, 15, 12, 5, tzinfo=timezone.utc),
    }

    with pytest.raises(pydantic.ValidationError, match="ingest metadata"):
        schemas.Ex1CandidateFact.model_validate(payload)


def test_ex1_candidate_fact_json_schema_contract() -> None:
    schemas = import_schemas()

    schema = schemas.Ex1CandidateFact.model_json_schema()

    assert set(schema["required"]).issuperset(
        {
            "fact_id",
            "entity_id",
            "fact_type",
            "fact_content",
            "confidence",
            "source_reference",
            "extracted_at",
            "subsystem_id",
        }
    )
    assert schemas.FORBIDDEN_INGEST_METADATA_FIELDS.isdisjoint(schema["properties"])
