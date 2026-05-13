from datetime import datetime, timezone
from math import inf, nan
from typing import Any

import pytest
from pydantic import ValidationError

from audit_eval.contracts import RetrospectiveEvaluation


def _valid_payload() -> dict[str, Any]:
    return {
        "evaluation_id": "retro-cycle_20260410-recommendation-T+1",
        "cycle_id": "cycle_20260410",
        "object_ref": "recommendation",
        "horizon": "T+1",
        "trend_deviation": 2.0,
        "risk_deviation": 1.0,
        "alert_score": 2.0,
        "learning_score": 1.6,
        "deviation_level": 2,
        "hit_rate_rel": 0.42,
        "baseline_vs_llm_breakdown": {"baseline_hit": False, "llm_hit": True},
        "evaluated_at": datetime(2026, 4, 11, tzinfo=timezone.utc),
    }


def test_retrospective_evaluation_fields_match_project_contract() -> None:
    assert tuple(RetrospectiveEvaluation.model_fields) == (
        "evaluation_id",
        "cycle_id",
        "object_ref",
        "horizon",
        "trend_deviation",
        "risk_deviation",
        "alert_score",
        "learning_score",
        "deviation_level",
        "hit_rate_rel",
        "baseline_vs_llm_breakdown",
        "evaluated_at",
    )


def test_retrospective_evaluation_accepts_valid_payload() -> None:
    evaluation = RetrospectiveEvaluation.model_validate(_valid_payload())

    assert evaluation.horizon == "T+1"
    assert evaluation.alert_score == 2.0
    assert evaluation.learning_score == 1.6


def test_retrospective_evaluation_rejects_extra_fields() -> None:
    payload = _valid_payload()
    payload["extra"] = "forbidden"

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        RetrospectiveEvaluation.model_validate(payload)


def test_retrospective_evaluation_rejects_unknown_horizon() -> None:
    payload = _valid_payload()
    payload["horizon"] = "T+2"

    with pytest.raises(ValidationError, match="T\\+1"):
        RetrospectiveEvaluation.model_validate(payload)


@pytest.mark.parametrize(
    ("field_name", "value", "match"),
    [
        ("alert_score", 1.0, "alert_score"),
        ("learning_score", 1.5, "learning_score"),
        ("deviation_level", -1, "deviation_level"),
        ("deviation_level", 5, "deviation_level"),
        ("trend_deviation", -0.1, "trend_deviation"),
        ("risk_deviation", nan, "risk_deviation"),
        ("alert_score", inf, "alert_score"),
        ("learning_score", -inf, "learning_score"),
    ],
)
def test_retrospective_evaluation_rejects_invalid_scores_and_level(
    field_name: str,
    value: object,
    match: str,
) -> None:
    payload = _valid_payload()
    payload[field_name] = value

    with pytest.raises(ValidationError, match=match):
        RetrospectiveEvaluation.model_validate(payload)
