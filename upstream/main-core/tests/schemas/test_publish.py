"""Tests for publish bundle and override record schemas."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from main_core.common.schemas import OverrideRecord, PublishBundle


def _publish_payload() -> dict[str, object]:
    return {
        "cycle_id": "cycle_001",
        "formal_objects": {"world_state": {"ref": "world_state_snapshot/cycle_001"}},
        "manifest_candidate": {"snapshot_id": "snap_001"},
        "audit_payload": {"actor": "system"},
        "retrospective_seed": {"window": "1d"},
    }


def _override_payload() -> dict[str, object]:
    return {
        "cycle_id": "cycle_001",
        "entity_id": "ENT_001",
        "submitted_by": "analyst_001",
        "action_type": "hold",
        "rationale": "manual risk review",
        "submitted_at": datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC),
    }


def test_publish_bundle_happy_path_round_trips_json() -> None:
    bundle = PublishBundle(**_publish_payload())

    assert PublishBundle.from_json(bundle.to_json()) == bundle


def test_publish_bundle_missing_field_fails() -> None:
    payload = _publish_payload()
    payload.pop("audit_payload")

    with pytest.raises(ValidationError):
        PublishBundle(**payload)


def test_publish_bundle_rejects_wrong_formal_objects_type() -> None:
    payload = _publish_payload()
    payload["formal_objects"] = []

    with pytest.raises(ValidationError):
        PublishBundle(**payload)


def test_override_record_happy_path_round_trips_json() -> None:
    override = OverrideRecord(**_override_payload())

    assert OverrideRecord.from_json(override.to_json()) == override


def test_override_record_missing_field_fails() -> None:
    payload = _override_payload()
    payload.pop("submitted_at")

    with pytest.raises(ValidationError):
        OverrideRecord(**payload)


def test_override_record_rejects_unknown_action_type() -> None:
    payload = _override_payload()
    payload["action_type"] = "skip"

    with pytest.raises(ValidationError):
        OverrideRecord(**payload)
