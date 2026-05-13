from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone

import pydantic
import pytest

from contracts.schemas import (
    FORBIDDEN_INGEST_METADATA_FIELDS,
    Ex0Metadata,
    Ex1CandidateFact,
    Ex2CandidateSignal,
    Ex3CandidateGraphDelta,
)


PayloadFactory = Callable[[], dict[str, object]]


def valid_ex0_payload() -> dict[str, object]:
    return {
        "subsystem_id": "subsystem-news",
        "version": "0.1.0",
        "heartbeat_at": datetime(2026, 4, 15, 12, 0, tzinfo=timezone.utc),
        "status": "ok",
        "last_output_at": datetime(2026, 4, 15, 11, 55, tzinfo=timezone.utc),
        "pending_count": 0,
    }


def valid_ex1_payload() -> dict[str, object]:
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


def valid_ex2_payload() -> dict[str, object]:
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


def valid_ex3_payload() -> dict[str, object]:
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


EX_MODEL_REQUIRED_FIELDS: dict[type[pydantic.BaseModel], set[str]] = {
    Ex0Metadata: {
        "subsystem_id",
        "version",
        "heartbeat_at",
        "status",
        "last_output_at",
        "pending_count",
    },
    Ex1CandidateFact: {
        "fact_id",
        "entity_id",
        "fact_type",
        "fact_content",
        "confidence",
        "source_reference",
        "extracted_at",
        "subsystem_id",
    },
    Ex2CandidateSignal: {
        # v0.1.3: affected_sectors STAYS required (consumers can rely on
        # presence) but list min_length=1 was removed (announcement-style
        # producers without sector data emit []). See positive coverage:
        # test_ex2_affected_sectors_empty_list_is_valid below.
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
    },
    Ex3CandidateGraphDelta: {
        "delta_id",
        "delta_type",
        "source_node",
        "target_node",
        "relation_type",
        "properties",
        "evidence",
        "subsystem_id",
    },
}


EX_MODEL_PAYLOADS: tuple[tuple[type[pydantic.BaseModel], PayloadFactory], ...] = (
    (Ex0Metadata, valid_ex0_payload),
    (Ex1CandidateFact, valid_ex1_payload),
    (Ex2CandidateSignal, valid_ex2_payload),
    (Ex3CandidateGraphDelta, valid_ex3_payload),
)


REQUIRED_FIELD_CASES: tuple[
    tuple[type[pydantic.BaseModel], PayloadFactory, str],
    ...,
] = (
    tuple(
        (model, payload_factory, field_name)
        for model, payload_factory in EX_MODEL_PAYLOADS
        for field_name in sorted(EX_MODEL_REQUIRED_FIELDS[model])
    )
)


@pytest.mark.parametrize(("model", "payload_factory"), EX_MODEL_PAYLOADS)
def test_valid_ex_payloads_validate(
    model: type[pydantic.BaseModel],
    payload_factory: PayloadFactory,
) -> None:
    payload = payload_factory()

    parsed = model.model_validate(payload)

    # exclude_unset=True asserts "what was explicitly provided round-trips
    # exactly" — independent of optional fields added in later contracts
    # versions (e.g. producer_context / Ex1.evidence in v0.1.3).
    assert parsed.model_dump(exclude_unset=True) == payload


@pytest.mark.parametrize(
    ("model", "payload_factory", "field_name"),
    REQUIRED_FIELD_CASES,
)
def test_required_fields_are_enforced(
    model: type[pydantic.BaseModel],
    payload_factory: PayloadFactory,
    field_name: str,
) -> None:
    payload = payload_factory()
    payload.pop(field_name)

    with pytest.raises(pydantic.ValidationError):
        model.model_validate(payload)


@pytest.mark.parametrize(("model", "payload_factory"), EX_MODEL_PAYLOADS)
def test_extra_fields_are_rejected_for_all_ex_payloads(
    model: type[pydantic.BaseModel],
    payload_factory: PayloadFactory,
) -> None:
    payload = {**payload_factory(), "unexpected_field": "not allowed"}

    with pytest.raises(pydantic.ValidationError):
        model.model_validate(payload)


@pytest.mark.parametrize(("model", "payload_factory"), EX_MODEL_PAYLOADS)
@pytest.mark.parametrize("field_name", sorted(FORBIDDEN_INGEST_METADATA_FIELDS))
def test_ingest_metadata_is_rejected_for_all_ex_payloads(
    model: type[pydantic.BaseModel],
    payload_factory: PayloadFactory,
    field_name: str,
) -> None:
    payload = {
        **payload_factory(),
        field_name: datetime(2026, 4, 15, 12, 5, tzinfo=timezone.utc),
    }

    with pytest.raises(pydantic.ValidationError, match="ingest metadata"):
        model.model_validate(payload)


@pytest.mark.parametrize(("model", "payload_factory"), EX_MODEL_PAYLOADS)
def test_ex_json_schema_required_fields_match_contract(
    model: type[pydantic.BaseModel],
    payload_factory: PayloadFactory,
) -> None:
    del payload_factory

    schema = model.model_json_schema()

    assert set(schema["required"]) == EX_MODEL_REQUIRED_FIELDS[model]
    assert FORBIDDEN_INGEST_METADATA_FIELDS.isdisjoint(schema["properties"])


@pytest.mark.parametrize(
    ("field_name", "field_value", "match"),
    [
        ("pending_count", -1, None),
        ("status", "unknown", None),
        ("heartbeat_at", datetime(2026, 4, 15, 12, 0), "timezone-aware"),
    ],
)
def test_ex0_invalid_values_are_rejected(
    field_name: str,
    field_value: object,
    match: str | None,
) -> None:
    payload = {**valid_ex0_payload(), field_name: field_value}

    with pytest.raises(pydantic.ValidationError, match=match):
        Ex0Metadata.model_validate(payload)


@pytest.mark.parametrize(
    ("field_name", "field_value"),
    [
        ("confidence", -0.01),
        ("confidence", 1.01),
        ("fact_content", {}),
        ("source_reference", {}),
    ],
)
def test_ex1_invalid_values_are_rejected(
    field_name: str,
    field_value: object,
) -> None:
    payload = {**valid_ex1_payload(), field_name: field_value}

    with pytest.raises(pydantic.ValidationError):
        Ex1CandidateFact.model_validate(payload)


@pytest.mark.parametrize(
    ("field_name", "field_value"),
    [
        ("direction", "sideways"),
        ("magnitude", -0.01),
        ("affected_entities", []),
        # affected_sectors=[] is now ACCEPTED as of v0.1.3 (field stays
        # required, but list-level min_length=1 constraint was removed;
        # element SectorId min_length=1 still applies). See positive
        # coverage in test_ex2_affected_sectors_empty_list_is_valid below.
        ("evidence", []),
    ],
)
def test_ex2_invalid_values_are_rejected(
    field_name: str,
    field_value: object,
) -> None:
    payload = {**valid_ex2_payload(), field_name: field_value}

    with pytest.raises(pydantic.ValidationError):
        Ex2CandidateSignal.model_validate(payload)


@pytest.mark.parametrize(
    ("field_name", "field_value"),
    [
        ("delta_type", ""),
        ("relation_type", ""),
        ("evidence", []),
    ],
)
def test_ex3_invalid_values_are_rejected(
    field_name: str,
    field_value: object,
) -> None:
    payload = {**valid_ex3_payload(), field_name: field_value}

    with pytest.raises(pydantic.ValidationError):
        Ex3CandidateGraphDelta.model_validate(payload)


def test_ex3_empty_properties_is_valid() -> None:
    payload = {**valid_ex3_payload(), "properties": {}}

    delta = Ex3CandidateGraphDelta.model_validate(payload)

    assert delta.properties == {}


# -- v0.1.3 backward-compatible additions ---------------------------------
# producer_context extension slot (Ex1/Ex2/Ex3) + Ex1.evidence canonical
# slot + relaxed Ex2.affected_sectors. These positive tests guard the
# subsystem-announcement follow-up #3 cross-repo reconciliation contract.


@pytest.mark.parametrize(("model", "payload_factory"), EX_MODEL_PAYLOADS[1:])
def test_ex_payloads_default_producer_context_to_none(
    model: type[pydantic.BaseModel],
    payload_factory: PayloadFactory,
) -> None:
    """Ex1/Ex2/Ex3 default ``producer_context`` to None when omitted."""

    instance = model.model_validate(payload_factory())

    assert instance.producer_context is None


@pytest.mark.parametrize(("model", "payload_factory"), EX_MODEL_PAYLOADS[1:])
def test_ex_payloads_accept_producer_context_dict(
    model: type[pydantic.BaseModel],
    payload_factory: PayloadFactory,
) -> None:
    """Ex1/Ex2/Ex3 accept arbitrary opaque dict in ``producer_context``."""

    extension = {
        "announcement_id": "ANN-2026-001",
        "evidence_spans_detail": [
            {"section_id": "s1", "start_offset": 0, "end_offset": 10, "quote": "..."}
        ],
        "source_fact_ids": ["fact-1"],
    }
    payload = {**payload_factory(), "producer_context": extension}

    instance = model.model_validate(payload)

    assert instance.producer_context == extension


@pytest.mark.parametrize(("model", "payload_factory"), EX_MODEL_PAYLOADS[1:])
def test_ex_payloads_accept_producer_context_explicit_none(
    model: type[pydantic.BaseModel],
    payload_factory: PayloadFactory,
) -> None:
    """Explicit ``producer_context=None`` is equivalent to omission."""

    payload = {**payload_factory(), "producer_context": None}

    instance = model.model_validate(payload)

    assert instance.producer_context is None


@pytest.mark.parametrize(("model", "payload_factory"), EX_MODEL_PAYLOADS[1:])
def test_ex_payloads_still_reject_unknown_extra_fields_after_v013(
    model: type[pydantic.BaseModel],
    payload_factory: PayloadFactory,
) -> None:
    """v0.1.3 extension is whitelist-only — unknown extras still rejected.

    Guards against producer_context becoming a back-door for arbitrary
    field smuggling.
    """

    payload = {**payload_factory(), "ad_hoc_extra_field": "should be rejected"}

    with pytest.raises(pydantic.ValidationError):
        model.model_validate(payload)


def test_ex1_evidence_defaults_to_none() -> None:
    """Ex1.evidence is optional (None) — backward-compat for v0.1.2 producers."""

    fact = Ex1CandidateFact.model_validate(valid_ex1_payload())

    assert fact.evidence is None


def test_ex1_evidence_explicit_none_is_valid() -> None:
    payload = {**valid_ex1_payload(), "evidence": None}

    fact = Ex1CandidateFact.model_validate(payload)

    assert fact.evidence is None


def test_ex1_evidence_accepts_canonical_ref_list() -> None:
    """Ex1 producers may opt in to canonical evidence refs (announcement use case)."""

    payload = {**valid_ex1_payload(), "evidence": ["ANN-1#section_1:0-50"]}

    fact = Ex1CandidateFact.model_validate(payload)

    assert fact.evidence == ["ANN-1#section_1:0-50"]


def test_ex1_evidence_rejects_empty_string_ref() -> None:
    """When evidence is provided, individual refs must satisfy EvidenceRef
    (min_length=1) — guards against silent accept of empty strings."""

    payload = {**valid_ex1_payload(), "evidence": [""]}

    with pytest.raises(pydantic.ValidationError):
        Ex1CandidateFact.model_validate(payload)


def test_ex2_affected_sectors_empty_list_is_valid() -> None:
    """Explicit affected_sectors=[] is now valid (was rejected in v0.1.2)."""

    payload = {**valid_ex2_payload(), "affected_sectors": []}

    signal = Ex2CandidateSignal.model_validate(payload)

    assert signal.affected_sectors == []


def test_ex2_affected_sectors_non_empty_still_works() -> None:
    """Pre-v0.1.3 producers (with non-empty affected_sectors) keep working."""

    payload = {**valid_ex2_payload(), "affected_sectors": ["technology", "energy"]}

    signal = Ex2CandidateSignal.model_validate(payload)

    assert signal.affected_sectors == ["technology", "energy"]
