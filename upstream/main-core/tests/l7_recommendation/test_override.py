"""Tests for L7 human override handling."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from main_core.common.errors import MainCoreError
from main_core.common.schemas import OverrideRecord, RecommendationSnapshot
from main_core.l7_recommendation import (
    InMemoryOverrideStore,
    apply_override,
    find_override,
    submit_override,
)


def _override_payload(**updates: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "cycle_id": "cycle_l7",
        "entity_id": "ENT_A",
        "submitted_by": "analyst",
        "action_type": "buy",
        "rationale": "human override",
        "submitted_at": datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC),
    }
    payload.update(updates)
    return payload


def _candidate(**updates: object) -> RecommendationSnapshot:
    payload: dict[str, object] = {
        "cycle_id": "cycle_l7",
        "entity_id": "ENT_A",
        "action_type": "hold",
        "rating": "B",
        "confidence": 0.6,
        "triggered_by": "system",
        "override_applied": False,
        "constraints_applied": {"existing": "kept"},
    }
    payload.update(updates)
    return RecommendationSnapshot(**payload)


def test_submit_override_accepts_mapping_and_stores_validated_record() -> None:
    store = InMemoryOverrideStore()

    override = submit_override(_override_payload(), store=store)

    assert isinstance(override, OverrideRecord)
    assert override.action_type == "buy"
    assert store.records == (override,)
    with pytest.raises(ValidationError):
        OverrideRecord.model_validate({**override.model_dump(), "action_type": "sell"})


def test_submit_override_accepts_existing_record() -> None:
    store = InMemoryOverrideStore()
    override = OverrideRecord(**_override_payload(action_type="reduce"))

    stored_override = submit_override(override, store=store)

    assert stored_override == override
    assert stored_override is not override
    assert store.records == (stored_override,)


def test_find_override_returns_matching_cycle_entity_record() -> None:
    first = OverrideRecord(**_override_payload(entity_id="ENT_B", action_type="reduce"))
    second = OverrideRecord(**_override_payload())

    assert find_override([first, second], "cycle_l7", "ENT_A") == second
    assert find_override([first, second], "cycle_l7", "ENT_Z") is None


def test_apply_override_sets_human_audit_fields_and_keeps_constraints() -> None:
    override = OverrideRecord(**_override_payload(action_type="reduce"))

    result = apply_override(_candidate(), override)

    assert result.action_type == "reduce"
    assert result.rating == "C"
    assert result.triggered_by == "human_decision"
    assert result.override_applied is True
    assert result.constraints_applied == {"existing": "kept"}


def test_apply_override_rejects_non_matching_override() -> None:
    override = OverrideRecord(**_override_payload(entity_id="ENT_B"))

    with pytest.raises(MainCoreError, match="entity_id"):
        apply_override(_candidate(), override)


def test_override_record_rejects_naive_submitted_at() -> None:
    payload = _override_payload(submitted_at=datetime(2026, 1, 2, 3, 4, 5))

    with pytest.raises(ValidationError, match="timezone-aware UTC"):
        OverrideRecord(**payload)


class _RecordingFalseyStore:
    """Custom override store that is falsey but functionally valid.

    Regression for #51: ``store or _DEFAULT_OVERRIDE_STORE`` would silently
    bypass falsey custom stores. ``store if store is not None else ...`` does
    not.
    """

    def __init__(self) -> None:
        self.saved: list[OverrideRecord] = []

    def __bool__(self) -> bool:
        return False

    def save(self, override: OverrideRecord) -> OverrideRecord:
        self.saved.append(override)
        return override

    def list_overrides(self):  # type: ignore[no-untyped-def]
        return tuple(self.saved)


def test_submit_override_does_not_bypass_falsey_custom_store() -> None:
    store = _RecordingFalseyStore()
    override = OverrideRecord(**_override_payload())

    submit_override(override, store=store)

    assert store.saved == [override]
