"""Tests for the L7 recommendation snapshot schema."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from main_core.common.schemas import RecommendationSnapshot


def _recommendation_payload() -> dict[str, object]:
    return {
        "cycle_id": "cycle_001",
        "entity_id": "ENT_001",
        "action_type": "buy",
        "rating": "A",
        "confidence": 0.77,
        "triggered_by": "system",
        "override_applied": False,
        "constraints_applied": {"regime": "risk_on"},
    }


def test_recommendation_happy_path_round_trips_json() -> None:
    recommendation = RecommendationSnapshot(**_recommendation_payload())

    assert RecommendationSnapshot.from_json(recommendation.to_json()) == recommendation


def test_recommendation_missing_field_fails() -> None:
    payload = _recommendation_payload()
    payload.pop("triggered_by")

    with pytest.raises(ValidationError):
        RecommendationSnapshot(**payload)


def test_recommendation_rejects_unknown_action_type() -> None:
    payload = _recommendation_payload()
    payload["action_type"] = "sell"

    with pytest.raises(ValidationError):
        RecommendationSnapshot(**payload)


def test_recommendation_rejects_inconclusive_with_confidence() -> None:
    payload = _recommendation_payload()
    payload["action_type"] = "inconclusive"
    payload["confidence"] = 0.5

    with pytest.raises(ValidationError, match="confidence=None"):
        RecommendationSnapshot(**payload)
