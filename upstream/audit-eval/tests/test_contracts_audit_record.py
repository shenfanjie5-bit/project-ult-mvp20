import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from audit_eval.contracts import AuditRecord


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "spike" / "cycle_20260410"
AUDIT_RECORD_FIELDS = (
    "record_id",
    "cycle_id",
    "layer",
    "object_ref",
    "params_snapshot",
    "llm_lineage",
    "llm_cost",
    "sanitized_input",
    "input_hash",
    "raw_output",
    "parsed_result",
    "output_hash",
    "degradation_flags",
    "created_at",
)


def _audit_payload() -> dict[str, Any]:
    payloads = json.loads((FIXTURE_ROOT / "audit_records.json").read_text())
    return payloads[0]


def test_audit_record_schema_fields_are_exact() -> None:
    assert tuple(AuditRecord.model_fields) == AUDIT_RECORD_FIELDS
    assert AuditRecord.model_config["extra"] == "forbid"


def test_audit_record_forbids_extra_fields() -> None:
    payload = _audit_payload()
    payload["unexpected"] = True

    with pytest.raises(ValidationError):
        AuditRecord.model_validate(payload)


def test_audit_record_fixture_round_trips() -> None:
    payloads = json.loads((FIXTURE_ROOT / "audit_records.json").read_text())

    records = [AuditRecord.model_validate(payload) for payload in payloads]
    round_tripped = [
        AuditRecord.model_validate(record.model_dump(mode="json"))
        for record in records
    ]

    assert [record.record_id for record in round_tripped] == [
        "audit-cycle_20260410-L4-world_state",
        "audit-cycle_20260410-L7-recommendation",
    ]


def test_audit_record_requires_each_replay_field_when_llm_called() -> None:
    for field_name in AuditRecord.replay_field_names:
        payload = _audit_payload()
        payload[field_name] = None

        with pytest.raises(ValidationError, match=field_name):
            AuditRecord.model_validate(payload)


@pytest.mark.parametrize(
    ("field_name", "value", "match"),
    [
        ("input_hash", "0" * 64, "input_hash"),
        ("output_hash", "1" * 64, "output_hash"),
        ("input_hash", "sha256:not-a-real-digest", "sha256 digest"),
        ("output_hash", "sha256:not-a-real-digest", "sha256 digest"),
    ],
)
def test_audit_record_recomputes_replay_hashes_when_llm_called(
    field_name: str,
    value: str,
    match: str,
) -> None:
    payload = _audit_payload()
    payload[field_name] = value

    with pytest.raises(ValidationError, match=match):
        AuditRecord.model_validate(payload)


def test_audit_record_validates_lineage_hash_copies_when_present() -> None:
    payload = _audit_payload()
    payload["llm_lineage"] = {
        **payload["llm_lineage"],
        "input_hash": "0" * 64,
    }

    with pytest.raises(ValidationError, match="llm_lineage.input_hash"):
        AuditRecord.model_validate(payload)


def test_audit_record_allows_null_replay_fields_when_llm_not_called() -> None:
    payload = _audit_payload()
    payload["llm_lineage"] = {"called": False}
    for field_name in AuditRecord.replay_field_names:
        payload[field_name] = None

    record = AuditRecord.model_validate(payload)

    assert record.llm_lineage == {"called": False}
    for field_name in AuditRecord.replay_field_names:
        assert getattr(record, field_name) is None


@pytest.mark.parametrize("llm_lineage", [{}, {"called": "false"}, {"called": 1}])
def test_audit_record_requires_typed_llm_called_flag(
    llm_lineage: dict[str, object],
) -> None:
    payload = _audit_payload()
    payload["llm_lineage"] = llm_lineage

    with pytest.raises(ValidationError, match="llm_lineage.called"):
        AuditRecord.model_validate(payload)


def test_audit_record_requires_replay_field_names_even_without_llm_call() -> None:
    payload = _audit_payload()
    payload["llm_lineage"] = {"called": False}
    del payload["sanitized_input"]

    with pytest.raises(ValidationError):
        AuditRecord.model_validate(payload)
