"""Tests for the L6 alpha result snapshot schema."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from main_core.common.schemas import AlphaResultSnapshot, single_prompt_result


def _alpha_payload() -> dict[str, object]:
    return {
        "cycle_id": "cycle_001",
        "entity_id": "ENT_001",
        "analyzer_type": "single_prompt_v1",
        "score": 0.72,
        "confidence": 0.81,
        "rationale": "quality and momentum are aligned",
        "similar_cases": [{"entity_id": "ENT_009", "score": 0.69}],
        "status": "ok",
    }


def test_alpha_result_happy_path_round_trips_json() -> None:
    result = AlphaResultSnapshot(**_alpha_payload())

    assert AlphaResultSnapshot.from_json(result.to_json()) == result


def test_single_prompt_result_factory_sets_p2_default_analyzer_type() -> None:
    payload = _alpha_payload()
    payload.pop("analyzer_type")

    result = single_prompt_result(**payload)

    assert result.analyzer_type == "single_prompt_v1"


def test_alpha_result_accepts_multi_agent_v1_happy_path() -> None:
    payload = _alpha_payload()
    payload["analyzer_type"] = "multi_agent_v1"

    result = AlphaResultSnapshot(**payload)

    assert result.analyzer_type == "multi_agent_v1"
    assert result.status == "ok"


def test_alpha_result_missing_field_fails() -> None:
    payload = _alpha_payload()
    payload.pop("entity_id")

    with pytest.raises(ValidationError):
        AlphaResultSnapshot(**payload)


def test_alpha_result_rejects_unknown_analyzer_type() -> None:
    payload = _alpha_payload()
    payload["analyzer_type"] = "gpt5_v2"

    with pytest.raises(ValidationError):
        AlphaResultSnapshot(**payload)


def test_alpha_result_rejects_inconclusive_with_score() -> None:
    payload = _alpha_payload()
    payload["status"] = "inconclusive"
    payload["score"] = 0.5

    with pytest.raises(ValidationError, match="score=None"):
        AlphaResultSnapshot(**payload)


def test_alpha_result_rejects_non_finite_score() -> None:
    payload = _alpha_payload()
    payload["score"] = float("nan")

    with pytest.raises(ValidationError):
        AlphaResultSnapshot(**payload)


def test_alpha_result_rejects_non_finite_confidence() -> None:
    payload = _alpha_payload()
    payload["confidence"] = float("inf")

    with pytest.raises(ValidationError):
        AlphaResultSnapshot(**payload)
