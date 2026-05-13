import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from audit_eval.contracts import RetrospectiveEvaluation
from audit_eval.contracts.common import RetrospectiveHorizon
from audit_eval.retro import evaluate_cumulative_alert

FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "retro" / "summary"


def _read_alert_cases() -> dict[str, list[dict[str, Any]]]:
    return json.loads(
        (FIXTURE_ROOT / "alert_cases.json").read_text(encoding="utf-8")
    )


def _evaluation(
    *,
    day: str,
    alert_score: float,
    hit_rate_rel: float | None,
    layer: str = "L7",
    horizon: RetrospectiveHorizon = "T+1",
    suffix: str = "",
) -> RetrospectiveEvaluation:
    return RetrospectiveEvaluation(
        evaluation_id=f"retro-{day}-{alert_score}-{horizon}{suffix}",
        cycle_id=f"cycle_{day.replace('-', '')}",
        object_ref="recommendation",
        horizon=horizon,
        trend_deviation=alert_score,
        risk_deviation=0.0,
        alert_score=alert_score,
        learning_score=RetrospectiveEvaluation.derive_learning_score(
            alert_score,
            0.0,
        ),
        deviation_level=min(4, int(math.floor(alert_score))),
        hit_rate_rel=hit_rate_rel,
        baseline_vs_llm_breakdown={"layer": layer},
        evaluated_at=datetime.fromisoformat(f"{day}T12:00:00+00:00"),
    )


def _case_evaluations(case_name: str) -> list[RetrospectiveEvaluation]:
    return [
        _evaluation(
            day=payload["day"],
            alert_score=payload["alert_score"],
            hit_rate_rel=payload["hit_rate_rel"],
            layer=payload["layer"],
            suffix=f"-{index}",
        )
        for index, payload in enumerate(_read_alert_cases()[case_name])
    ]


def test_cumulative_alert_warns_on_three_consecutive_days_ge_2() -> None:
    alert = evaluate_cumulative_alert(
        _case_evaluations("warning"),
        evaluated_at=datetime(2026, 4, 4, tzinfo=timezone.utc),
    )

    assert alert.level == "WARNING"
    assert "CONSECUTIVE_3_DAYS_ALERT_SCORE_GE_2" in alert.reason_codes
    assert alert.window_start.isoformat() == "2026-04-01"
    assert alert.window_end.isoformat() == "2026-04-03"


def test_cumulative_alert_critical_on_three_consecutive_days_ge_3() -> None:
    alert = evaluate_cumulative_alert(
        _case_evaluations("critical"),
        evaluated_at=datetime(2026, 4, 4, tzinfo=timezone.utc),
    )

    assert alert.level == "CRITICAL"
    assert "CONSECUTIVE_3_DAYS_ALERT_SCORE_GE_3" in alert.reason_codes


def test_cumulative_alert_critical_on_four_of_recent_five_days_ge_2() -> None:
    history = [
        _evaluation(day="2026-04-01", alert_score=2.0, hit_rate_rel=0.8),
        _evaluation(day="2026-04-02", alert_score=2.1, hit_rate_rel=0.8),
        _evaluation(day="2026-04-03", alert_score=1.0, hit_rate_rel=0.8),
        _evaluation(day="2026-04-04", alert_score=2.2, hit_rate_rel=0.8),
        _evaluation(day="2026-04-05", alert_score=2.3, hit_rate_rel=0.8),
    ]

    alert = evaluate_cumulative_alert(
        history,
        evaluated_at=datetime(2026, 4, 6, tzinfo=timezone.utc),
    )

    assert alert.level == "CRITICAL"
    assert "ROLLING_5_DAYS_4_DAYS_ALERT_SCORE_GE_2" in alert.reason_codes


def test_cumulative_alert_emergency_on_five_consecutive_days_ge_2() -> None:
    alert = evaluate_cumulative_alert(
        _case_evaluations("emergency"),
        evaluated_at=datetime(2026, 4, 6, tzinfo=timezone.utc),
    )

    assert alert.level == "EMERGENCY"
    assert "CONSECUTIVE_5_DAYS_ALERT_SCORE_GE_2" in alert.reason_codes


def test_cumulative_alert_emergency_on_three_days_ge_3_with_low_l7_hit_rate() -> None:
    alert = evaluate_cumulative_alert(
        _case_evaluations("emergency_l7_low_hit_rate"),
        evaluated_at=datetime(2026, 4, 4, tzinfo=timezone.utc),
    )

    assert alert.level == "EMERGENCY"
    assert (
        "CONSECUTIVE_3_DAYS_ALERT_SCORE_GE_3_AND_L7_HIT_RATE_REL_LT_0_35"
        in alert.reason_codes
    )
    assert alert.metrics["l7_hit_rate_rel_mean"] == pytest.approx(0.34)


def test_cumulative_alert_hit_rate_boundary_equal_0_35_is_not_emergency() -> None:
    alert = evaluate_cumulative_alert(
        _case_evaluations("boundary_hit_rate"),
        evaluated_at=datetime(2026, 4, 4, tzinfo=timezone.utc),
    )

    assert alert.level == "CRITICAL"
    assert (
        "CONSECUTIVE_3_DAYS_ALERT_SCORE_GE_3_AND_L7_HIT_RATE_REL_LT_0_35"
        not in alert.reason_codes
    )
    assert alert.metrics["l7_hit_rate_rel_mean"] == pytest.approx(0.35)


def test_cumulative_alert_hit_rate_just_below_0_35_is_emergency() -> None:
    history = [
        _evaluation(day="2026-04-01", alert_score=3.0, hit_rate_rel=0.35),
        _evaluation(day="2026-04-02", alert_score=3.1, hit_rate_rel=0.35),
        _evaluation(
            day="2026-04-03",
            alert_score=3.2,
            hit_rate_rel=0.349999999999,
        ),
    ]

    alert = evaluate_cumulative_alert(
        history,
        evaluated_at=datetime(2026, 4, 4, tzinfo=timezone.utc),
    )

    assert alert.level == "EMERGENCY"
    assert (
        "CONSECUTIVE_3_DAYS_ALERT_SCORE_GE_3_AND_L7_HIT_RATE_REL_LT_0_35"
        in alert.reason_codes
    )


def test_cumulative_alert_uses_cycle_business_date_over_evaluated_at() -> None:
    history = [
        _evaluation(
            day="2026-04-01",
            alert_score=2.0,
            hit_rate_rel=0.8,
            suffix="-1",
        ).model_copy(
            update={"evaluated_at": datetime(2026, 4, 10, tzinfo=timezone.utc)}
        ),
        _evaluation(
            day="2026-04-02",
            alert_score=2.1,
            hit_rate_rel=0.8,
            suffix="-2",
        ).model_copy(
            update={"evaluated_at": datetime(2026, 4, 10, tzinfo=timezone.utc)}
        ),
        _evaluation(
            day="2026-04-03",
            alert_score=2.2,
            hit_rate_rel=0.8,
            suffix="-3",
        ).model_copy(
            update={"evaluated_at": datetime(2026, 4, 10, tzinfo=timezone.utc)}
        ),
    ]

    alert = evaluate_cumulative_alert(
        history,
        evaluated_at=datetime(2026, 4, 11, tzinfo=timezone.utc),
    )

    assert alert.level == "WARNING"
    assert alert.window_start.isoformat() == "2026-04-01"
    assert alert.window_end.isoformat() == "2026-04-03"


def test_cumulative_alert_l7_emergency_uses_latest_breached_window() -> None:
    history = [
        _evaluation(day="2026-03-25", alert_score=1.0, hit_rate_rel=0.1),
        _evaluation(day="2026-03-26", alert_score=1.0, hit_rate_rel=0.1),
        _evaluation(day="2026-03-27", alert_score=1.0, hit_rate_rel=0.1),
        _evaluation(day="2026-04-01", alert_score=3.0, hit_rate_rel=0.5),
        _evaluation(day="2026-04-02", alert_score=3.1, hit_rate_rel=0.5),
        _evaluation(day="2026-04-03", alert_score=3.2, hit_rate_rel=0.5),
    ]

    alert = evaluate_cumulative_alert(
        history,
        evaluated_at=datetime(2026, 4, 4, tzinfo=timezone.utc),
    )

    assert alert.level == "CRITICAL"
    assert (
        "CONSECUTIVE_3_DAYS_ALERT_SCORE_GE_3_AND_L7_HIT_RATE_REL_LT_0_35"
        not in alert.reason_codes
    )
    assert alert.metrics["l7_hit_rate_rel_mean"] == pytest.approx(0.5)
    assert alert.metrics["l7_hit_rate_rel_count"] == 3


def test_cumulative_alert_uses_daily_max_and_input_order_does_not_matter() -> None:
    history = [
        _evaluation(day="2026-04-03", alert_score=2.2, hit_rate_rel=0.8),
        _evaluation(day="2026-04-01", alert_score=1.0, hit_rate_rel=0.8),
        _evaluation(
            day="2026-04-01",
            alert_score=2.5,
            hit_rate_rel=0.8,
            suffix="-max",
        ),
        _evaluation(day="2026-04-02", alert_score=2.1, hit_rate_rel=0.8),
    ]

    alert = evaluate_cumulative_alert(
        history,
        evaluated_at=datetime(2026, 4, 4, tzinfo=timezone.utc),
    )

    assert alert.level == "WARNING"
    assert alert.metrics["daily_alert_score_max"]["2026-04-01"] == 2.5


def test_cumulative_alert_ignores_non_t_plus_1_evaluations() -> None:
    history = [
        _evaluation(
            day="2026-04-01",
            alert_score=4.0,
            hit_rate_rel=0.1,
            horizon="T+5",
        ),
        _evaluation(
            day="2026-04-02",
            alert_score=4.0,
            hit_rate_rel=0.1,
            horizon="T+5",
        ),
        _evaluation(day="2026-04-03", alert_score=1.0, hit_rate_rel=0.8),
    ]

    alert = evaluate_cumulative_alert(
        history,
        evaluated_at=datetime(2026, 4, 4, tzinfo=timezone.utc),
    )

    assert alert.level == "NONE"
    assert alert.metrics["daily_alert_score_max"] == {"2026-04-03": 1.0}


def test_cumulative_alert_no_data_returns_none() -> None:
    alert = evaluate_cumulative_alert(
        [],
        evaluated_at=datetime(2026, 4, 4, tzinfo=timezone.utc),
    )

    assert alert.level == "NONE"
    assert alert.reason_codes == ()
    assert alert.window_start.isoformat() == "2026-04-04"
    assert alert.window_end.isoformat() == "2026-04-04"
