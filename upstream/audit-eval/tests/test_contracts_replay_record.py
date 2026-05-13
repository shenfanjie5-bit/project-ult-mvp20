import json
from pathlib import Path
from typing import Any, cast

import pytest
from pydantic import ValidationError

from audit_eval.contracts import ReplayRecord


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "spike" / "cycle_20260410"
REPLAY_RECORD_FIELDS = (
    "replay_id",
    "cycle_id",
    "object_ref",
    "audit_record_ids",
    "manifest_cycle_id",
    "formal_snapshot_refs",
    "graph_snapshot_ref",
    "dagster_run_id",
    "replay_mode",
    "created_at",
)


def _replay_payload() -> dict[str, Any]:
    payloads = json.loads((FIXTURE_ROOT / "replay_records.json").read_text())
    return payloads[1]


def test_replay_record_schema_fields_are_exact() -> None:
    assert tuple(ReplayRecord.model_fields) == REPLAY_RECORD_FIELDS
    assert ReplayRecord.model_config["extra"] == "forbid"


def test_replay_record_fixture_round_trips() -> None:
    payloads = json.loads((FIXTURE_ROOT / "replay_records.json").read_text())

    records = [ReplayRecord.model_validate(payload) for payload in payloads]
    round_tripped = [
        ReplayRecord.model_validate(record.model_dump(mode="json"))
        for record in records
    ]

    assert [record.object_ref for record in round_tripped] == [
        "world_state",
        "recommendation",
    ]
    assert round_tripped[1].graph_snapshot_ref == (
        "graph://cycle_20260410/portfolio_graph"
    )


def test_replay_record_forbids_non_read_history_mode() -> None:
    payload = _replay_payload()
    payload["replay_mode"] = cast(Any, "rerun_model")

    with pytest.raises(ValidationError):
        ReplayRecord.model_validate(payload)


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("audit_record_ids", []),
        ("manifest_cycle_id", ""),
        ("formal_snapshot_refs", {}),
        ("dagster_run_id", ""),
    ],
)
def test_replay_record_rejects_empty_required_bindings(
    field_name: str,
    value: object,
) -> None:
    payload = _replay_payload()
    payload[field_name] = value

    with pytest.raises(ValidationError, match=field_name):
        ReplayRecord.model_validate(payload)


def test_replay_record_requires_dagster_run_id_key() -> None:
    payload = _replay_payload()
    del payload["dagster_run_id"]

    with pytest.raises(ValidationError):
        ReplayRecord.model_validate(payload)


def test_replay_record_requires_graph_snapshot_ref_key_but_allows_null() -> None:
    payload = _replay_payload()
    del payload["graph_snapshot_ref"]
    with pytest.raises(ValidationError):
        ReplayRecord.model_validate(payload)

    payload = _replay_payload()
    payload["graph_snapshot_ref"] = None
    record = ReplayRecord.model_validate(payload)
    assert record.graph_snapshot_ref is None


@pytest.mark.parametrize(
    "formal_snapshot_refs",
    [
        {"recommendation": 123},
        {"recommendation": True},
        {"recommendation": ""},
        {"": "snapshot://cycle_20260410/recommendation"},
        ["snapshot://cycle_20260410/recommendation"],
    ],
)
def test_replay_record_requires_string_snapshot_ref_mapping(
    formal_snapshot_refs: object,
) -> None:
    payload = _replay_payload()
    payload["formal_snapshot_refs"] = formal_snapshot_refs

    with pytest.raises(ValidationError, match="formal_snapshot_refs"):
        ReplayRecord.model_validate(payload)


def test_replay_record_forbids_extra_fields() -> None:
    payload = _replay_payload()
    payload["unexpected"] = True

    with pytest.raises(ValidationError):
        ReplayRecord.model_validate(payload)
