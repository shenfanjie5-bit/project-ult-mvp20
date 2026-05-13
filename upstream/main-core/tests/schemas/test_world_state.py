"""Tests for the L4 world state snapshot schema."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from main_core.common.schemas import WorldStateSnapshot


def _world_state_payload() -> dict[str, object]:
    return {
        "cycle_id": "cycle_001",
        "baseline_regime": "neutral",
        "llm_delta": 1,
        "final_regime": "risk_on",
        "llm_rationale": "risk appetite improved",
        "actual_model_used": "reasoner-stub",
        "actual_provider": "local",
        "fallback_path": [],
    }


def test_world_state_happy_path_round_trips_json() -> None:
    snapshot = WorldStateSnapshot(**_world_state_payload())

    assert WorldStateSnapshot.from_json(snapshot.to_json()) == snapshot


def test_world_state_missing_field_fails() -> None:
    payload = _world_state_payload()
    payload.pop("fallback_path")

    with pytest.raises(ValidationError):
        WorldStateSnapshot(**payload)


def test_world_state_rejects_llm_delta_outside_allowed_literal() -> None:
    payload = _world_state_payload()
    payload["llm_delta"] = 2

    with pytest.raises(ValidationError):
        WorldStateSnapshot(**payload)


def test_world_state_rejects_final_regime_mismatch() -> None:
    payload = _world_state_payload()
    payload["final_regime"] = "neutral"

    with pytest.raises(ValidationError, match="final_regime"):
        WorldStateSnapshot(**payload)


def test_world_state_rejects_regime_sequence_overflow() -> None:
    payload = _world_state_payload()
    payload["baseline_regime"] = "risk_on"
    payload["llm_delta"] = 1
    payload["final_regime"] = "risk_on"

    with pytest.raises(ValidationError, match="outside the regime sequence"):
        WorldStateSnapshot(**payload)
