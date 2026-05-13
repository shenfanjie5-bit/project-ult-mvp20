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
        "subsystem_id": "subsystem-news",
        "version": "0.1.0",
        "heartbeat_at": datetime(2026, 4, 15, 12, 0, tzinfo=timezone.utc),
        "status": "ok",
        "last_output_at": datetime(2026, 4, 15, 11, 55, tzinfo=timezone.utc),
        "pending_count": 0,
    }


def test_ex0_metadata_public_api_imports() -> None:
    schemas = import_schemas()

    from contracts.schemas import BaseExPayload, Ex0Metadata

    assert BaseExPayload is schemas.BaseExPayload
    assert Ex0Metadata is schemas.Ex0Metadata
    assert "BaseExPayload" in schemas.__all__
    assert "Ex0Metadata" in schemas.__all__
    assert "FORBIDDEN_INGEST_METADATA_FIELDS" in schemas.__all__
    assert schemas.FORBIDDEN_INGEST_METADATA_FIELDS == frozenset(
        {"submitted_at", "ingest_seq"}
    )


def test_ex0_metadata_accepts_minimal_valid_payload() -> None:
    schemas = import_schemas()
    payload = valid_payload()

    metadata = schemas.Ex0Metadata.model_validate(payload)

    assert metadata.subsystem_id == "subsystem-news"
    assert metadata.version == "0.1.0"
    assert metadata.status.value == "ok"
    assert metadata.pending_count == 0
    assert metadata.heartbeat_at.tzinfo is not None
    assert metadata.heartbeat_at.tzinfo.utcoffset(metadata.heartbeat_at) is not None
    assert metadata.last_output_at is not None
    assert metadata.last_output_at.tzinfo is not None


@pytest.mark.parametrize(
    "field_name",
    [
        "subsystem_id",
        "version",
        "heartbeat_at",
        "status",
        "last_output_at",
        "pending_count",
    ],
)
def test_ex0_metadata_required_fields_are_enforced(field_name: str) -> None:
    schemas = import_schemas()
    payload = valid_payload()
    payload.pop(field_name)

    with pytest.raises(pydantic.ValidationError):
        schemas.Ex0Metadata.model_validate(payload)


@pytest.mark.parametrize("field_name", ["submitted_at", "ingest_seq"])
def test_ex0_metadata_rejects_ingest_metadata(field_name: str) -> None:
    schemas = import_schemas()
    payload = {
        **valid_payload(),
        field_name: datetime(2026, 4, 15, 12, 5, tzinfo=timezone.utc),
    }

    with pytest.raises(pydantic.ValidationError, match="ingest metadata"):
        schemas.Ex0Metadata.model_validate(payload)


def test_ex0_metadata_json_schema_excludes_ingest_metadata() -> None:
    schemas = import_schemas()

    schema = schemas.Ex0Metadata.model_json_schema()

    assert set(schema["required"]).issuperset(
        {
            "subsystem_id",
            "version",
            "heartbeat_at",
            "status",
            "last_output_at",
            "pending_count",
        }
    )
    assert schemas.FORBIDDEN_INGEST_METADATA_FIELDS.isdisjoint(schema["properties"])


def test_ex0_metadata_accepts_null_last_output_at() -> None:
    schemas = import_schemas()
    payload = {**valid_payload(), "last_output_at": None}

    metadata = schemas.Ex0Metadata.model_validate(payload)

    assert metadata.last_output_at is None


def test_ex0_metadata_rejects_negative_pending_count() -> None:
    schemas = import_schemas()
    payload = {**valid_payload(), "pending_count": -1}

    with pytest.raises(pydantic.ValidationError):
        schemas.Ex0Metadata.model_validate(payload)


@pytest.mark.parametrize("pending_count", [True, "1"])
def test_ex0_metadata_rejects_coerced_pending_count(
    pending_count: object,
) -> None:
    schemas = import_schemas()
    payload = {**valid_payload(), "pending_count": pending_count}

    with pytest.raises(pydantic.ValidationError):
        schemas.Ex0Metadata.model_validate(payload)


def test_ex0_metadata_rejects_unknown_status() -> None:
    schemas = import_schemas()
    payload = {**valid_payload(), "status": "unknown"}

    with pytest.raises(pydantic.ValidationError):
        schemas.Ex0Metadata.model_validate(payload)


@pytest.mark.parametrize("field_name", ["heartbeat_at", "last_output_at"])
def test_ex0_metadata_rejects_naive_datetimes(field_name: str) -> None:
    schemas = import_schemas()
    payload = {**valid_payload(), field_name: datetime(2026, 4, 15, 12, 0)}

    with pytest.raises(pydantic.ValidationError, match="timezone-aware"):
        schemas.Ex0Metadata.model_validate(payload)
