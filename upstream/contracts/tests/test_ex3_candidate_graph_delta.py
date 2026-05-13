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
        "delta_id": "delta-1",
        "delta_type": "upsert_relation",
        "source_node": "AAPL",
        "target_node": "technology",
        "relation_type": "belongs_to_sector",
        "properties": {"weight": 1.0},
        "evidence": ["fact-1"],
        "subsystem_id": "subsystem-news",
    }


def test_ex3_candidate_graph_delta_public_api_imports() -> None:
    schemas = import_schemas()

    from contracts.schemas import Ex3CandidateGraphDelta

    assert Ex3CandidateGraphDelta is schemas.Ex3CandidateGraphDelta
    assert "Ex3CandidateGraphDelta" in schemas.__all__


def test_ex3_candidate_graph_delta_accepts_valid_payload() -> None:
    schemas = import_schemas()

    delta = schemas.Ex3CandidateGraphDelta.model_validate(valid_payload())

    assert delta.delta_id == "delta-1"
    assert delta.delta_type == "upsert_relation"
    assert delta.source_node == "AAPL"
    assert delta.target_node == "technology"
    assert delta.relation_type == "belongs_to_sector"
    assert delta.properties == {"weight": 1.0}
    assert delta.evidence == ["fact-1"]
    assert delta.subsystem_id == "subsystem-news"


def test_ex3_candidate_graph_delta_accepts_empty_properties() -> None:
    schemas = import_schemas()
    payload = {**valid_payload(), "properties": {}}

    delta = schemas.Ex3CandidateGraphDelta.model_validate(payload)

    assert delta.properties == {}


@pytest.mark.parametrize(
    "field_name",
    [
        "delta_id",
        "delta_type",
        "source_node",
        "target_node",
        "relation_type",
        "properties",
        "evidence",
        "subsystem_id",
    ],
)
def test_ex3_candidate_graph_delta_required_fields_are_enforced(
    field_name: str,
) -> None:
    schemas = import_schemas()
    payload = valid_payload()
    payload.pop(field_name)

    with pytest.raises(pydantic.ValidationError):
        schemas.Ex3CandidateGraphDelta.model_validate(payload)


@pytest.mark.parametrize(
    ("field_name", "field_value"),
    [
        ("delta_type", ""),
        ("delta_type", "   "),
        ("source_node", ""),
        ("source_node", "   "),
        ("target_node", ""),
        ("target_node", "   "),
        ("relation_type", ""),
        ("relation_type", "   "),
        ("evidence", []),
        ("evidence", [""]),
        ("evidence", ["   "]),
    ],
)
def test_ex3_candidate_graph_delta_rejects_invalid_field_values(
    field_name: str,
    field_value: object,
) -> None:
    schemas = import_schemas()
    payload = {**valid_payload(), field_name: field_value}

    with pytest.raises(pydantic.ValidationError):
        schemas.Ex3CandidateGraphDelta.model_validate(payload)


@pytest.mark.parametrize("field_name", ["submitted_at", "ingest_seq"])
def test_ex3_candidate_graph_delta_rejects_ingest_metadata(
    field_name: str,
) -> None:
    schemas = import_schemas()
    payload = {
        **valid_payload(),
        field_name: datetime(2026, 4, 15, 12, 5, tzinfo=timezone.utc),
    }

    with pytest.raises(pydantic.ValidationError, match="ingest metadata"):
        schemas.Ex3CandidateGraphDelta.model_validate(payload)


def test_ex3_candidate_graph_delta_json_schema_contract() -> None:
    schemas = import_schemas()

    schema = schemas.Ex3CandidateGraphDelta.model_json_schema()

    assert set(schema["required"]).issuperset(
        {
            "delta_id",
            "delta_type",
            "source_node",
            "target_node",
            "relation_type",
            "properties",
            "evidence",
            "subsystem_id",
        }
    )
    assert schemas.FORBIDDEN_INGEST_METADATA_FIELDS.isdisjoint(schema["properties"])
    assert schema["properties"]["delta_type"]["minLength"] == 1
    assert schema["properties"]["source_node"]["minLength"] == 1
    assert schema["properties"]["target_node"]["minLength"] == 1
    assert schema["properties"]["relation_type"]["minLength"] == 1
    assert schema["properties"]["evidence"]["minItems"] == 1
    assert schema["properties"]["evidence"]["items"]["minLength"] == 1
