import json
import math
import socket
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone
from pathlib import Path
from threading import Barrier
from typing import Any, cast

import pytest

from audit_eval._boundary import BoundaryViolationError
from audit_eval.contracts import RetrospectiveEvaluation
from audit_eval.retro import (
    AlertState,
    InMemoryRetrospectiveCurrentViewStorage,
    InMemoryRetrospectiveEvaluationReader,
    RetroWindow,
    RetrospectiveSummary,
    RetrospectiveSummaryError,
    RetrospectiveStorageError,
    build_retrospective_summary,
)
from audit_eval.retro.dates import filter_evaluations_for_window

FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "retro" / "summary"


@pytest.fixture(autouse=True)
def block_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_network_call(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("Retrospective summary must not call network")

    monkeypatch.setattr(urllib.request, "urlopen", fail_network_call)
    monkeypatch.setattr(socket, "socket", fail_network_call)


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _summary_evaluations() -> list[RetrospectiveEvaluation]:
    return [
        _evaluation_from_fixture(payload)
        for payload in _read_json(FIXTURE_ROOT / "summary_evaluations.json")
    ]


def _evaluation_from_fixture(payload: dict[str, Any]) -> RetrospectiveEvaluation:
    trend_deviation = payload["trend_deviation"]
    risk_deviation = payload["risk_deviation"]
    alert_score = RetrospectiveEvaluation.derive_alert_score(
        trend_deviation,
        risk_deviation,
    )
    return RetrospectiveEvaluation(
        evaluation_id=payload["evaluation_id"],
        cycle_id=payload["cycle_id"],
        object_ref=payload["object_ref"],
        horizon=payload["horizon"],
        trend_deviation=trend_deviation,
        risk_deviation=risk_deviation,
        alert_score=alert_score,
        learning_score=RetrospectiveEvaluation.derive_learning_score(
            trend_deviation,
            risk_deviation,
        ),
        deviation_level=min(4, int(math.floor(alert_score))),
        hit_rate_rel=payload["hit_rate_rel"],
        baseline_vs_llm_breakdown=payload["baseline_vs_llm_breakdown"],
        evaluated_at=datetime.fromisoformat(payload["evaluated_at"]),
    )


def _single_evaluation(
    *,
    baseline_vs_llm_breakdown: dict[str, Any] | None = None,
    object_ref: str = "recommendation",
    cycle_id: str = "cycle_20260401",
    trend_deviation: float = 1.0,
    risk_deviation: float = 0.0,
    evaluated_at: datetime | None = None,
) -> RetrospectiveEvaluation:
    return RetrospectiveEvaluation(
        evaluation_id=f"retro-{cycle_id}-{object_ref}-T+1",
        cycle_id=cycle_id,
        object_ref=object_ref,
        horizon="T+1",
        trend_deviation=trend_deviation,
        risk_deviation=risk_deviation,
        alert_score=RetrospectiveEvaluation.derive_alert_score(
            trend_deviation,
            risk_deviation,
        ),
        learning_score=RetrospectiveEvaluation.derive_learning_score(
            trend_deviation,
            risk_deviation,
        ),
        deviation_level=1,
        hit_rate_rel=0.8,
        baseline_vs_llm_breakdown=baseline_vs_llm_breakdown or {"layer": "L7"},
        evaluated_at=evaluated_at or datetime(2026, 4, 1, 12, tzinfo=timezone.utc),
    )


def _current_view_summary(
    *,
    date_window: str,
    horizon: str,
    label: str,
    window_start: date = date(2026, 4, 1),
    object_ref: str | None = None,
) -> RetrospectiveSummary:
    alert_state = AlertState(
        level="NONE",
        reason_codes=(),
        window_start=window_start,
        window_end=window_start,
        evaluated_at=datetime(2026, 4, 2, tzinfo=timezone.utc),
        metrics={"source": label},
    )
    return RetrospectiveSummary(
        date_window=date_window,
        window_start=window_start,
        window_end=window_start,
        horizon=horizon,  # type: ignore[arg-type]
        evaluation_count=1,
        composite_learning_score_mean=1.0,
        trend=0.0,
        baseline_vs_llm_breakdown={"source": label},
        l7_hit_rate_rel_trend=None,
        alert_state=alert_state,
        generated_at=datetime(2026, 4, 2, tzinfo=timezone.utc),
        object_ref=object_ref,
    )


def test_build_retrospective_summary_aggregates_and_upserts_current_view(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from audit_eval.audit import query as audit_query

    def fail_replay(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("summary must only read analytical evaluations")

    monkeypatch.setattr(audit_query, "replay_cycle_object", fail_replay)
    window = "2026-04-01..2026-04-04"
    expected_window = RetroWindow(date(2026, 4, 1), date(2026, 4, 4))
    reader = InMemoryRetrospectiveEvaluationReader(_summary_evaluations())
    current_view = InMemoryRetrospectiveCurrentViewStorage()

    summary = build_retrospective_summary(
        window,
        reader=reader,
        current_view=current_view,
        generated_at=datetime(2026, 4, 5, tzinfo=timezone.utc),
    )

    assert reader.loaded_windows == [expected_window]
    assert summary.date_window == "2026-04-01..2026-04-04"
    assert summary.window_start == date(2026, 4, 1)
    assert summary.window_end == date(2026, 4, 4)
    assert summary.horizon == "T+1"
    assert summary.evaluation_count == 4
    assert summary.composite_learning_score_mean == pytest.approx(1.8)
    assert summary.trend == pytest.approx(1.4)
    assert summary.baseline_vs_llm_breakdown == {
        "alpha": 4.0,
        "layer": {"L7": 4},
        "llm_hit": {"false": 2, "true": 2},
        "winner": {"baseline": 2, "llm": 2},
    }
    assert summary.l7_hit_rate_rel_trend == pytest.approx(-0.4)
    assert summary.alert_state.level == "WARNING"
    assert len(current_view.summary_rows) == 1
    assert len(current_view.alert_state_rows) == 1
    assert current_view.summary_rows[0]["evaluation_count"] == 4
    assert current_view.alert_state_rows[0]["level"] == "WARNING"


def test_public_summary_api_accepts_main_core_window_string() -> None:
    reader = InMemoryRetrospectiveEvaluationReader(_summary_evaluations())
    current_view = InMemoryRetrospectiveCurrentViewStorage()

    summary = build_retrospective_summary(
        "2026-04-01..2026-04-07",
        reader=reader,
        current_view=current_view,
        generated_at=datetime(2026, 4, 8, tzinfo=timezone.utc),
    )

    assert reader.loaded_windows == [RetroWindow(date(2026, 4, 1), date(2026, 4, 7))]
    assert summary.date_window == "2026-04-01..2026-04-07"
    assert summary.evaluation_count == 4
    assert len(current_view.summary_rows) == 1


def test_public_summary_api_passes_validated_filters_to_reader() -> None:
    reader = InMemoryRetrospectiveEvaluationReader([_single_evaluation()])
    current_view = InMemoryRetrospectiveCurrentViewStorage()

    summary = build_retrospective_summary(
        "2026-04-01..2026-04-01",
        horizon="T+1",
        object_ref="recommendation",
        reader=reader,
        current_view=current_view,
        generated_at=datetime(2026, 4, 2, tzinfo=timezone.utc),
    )

    assert reader.loaded_windows == [
        RetroWindow(
            date(2026, 4, 1),
            date(2026, 4, 1),
            horizon="T+1",
            object_ref="recommendation",
        )
    ]
    assert summary.object_ref == "recommendation"
    assert summary.evaluation_count == 1


def test_public_summary_api_rejects_invalid_horizon_before_storage_lookup() -> None:
    with pytest.raises(ValueError, match="horizon"):
        build_retrospective_summary(
            "2026-04-01..2026-04-01",
            horizon="T+2",  # type: ignore[arg-type]
        )


def test_public_summary_api_rejects_empty_object_filter_before_storage_lookup() -> None:
    with pytest.raises(ValueError, match="object_ref"):
        build_retrospective_summary(
            "2026-04-01..2026-04-01",
            object_ref=" ",
        )


def test_public_summary_api_rejects_non_contract_window_format() -> None:
    with pytest.raises(ValueError, match="YYYY-MM-DD..YYYY-MM-DD"):
        build_retrospective_summary("20260401..20260407")


def test_summary_single_record_has_zero_trend_and_no_l7_hit_rate_trend() -> None:
    reader = InMemoryRetrospectiveEvaluationReader([_single_evaluation()])
    current_view = InMemoryRetrospectiveCurrentViewStorage()

    summary = build_retrospective_summary(
        "2026-04-01..2026-04-01",
        reader=reader,
        current_view=current_view,
        generated_at=datetime(2026, 4, 2, tzinfo=timezone.utc),
    )

    assert summary.trend == 0.0
    assert summary.l7_hit_rate_rel_trend is None
    assert len(current_view.summary_rows) == 1
    assert len(current_view.alert_state_rows) == 1


def test_summary_current_view_upserts_by_window_and_horizon() -> None:
    reader = InMemoryRetrospectiveEvaluationReader([_single_evaluation()])
    current_view = InMemoryRetrospectiveCurrentViewStorage()

    first = build_retrospective_summary(
        "2026-04-01..2026-04-01",
        reader=reader,
        current_view=current_view,
        generated_at=datetime(2026, 4, 2, tzinfo=timezone.utc),
    )
    second = build_retrospective_summary(
        "2026-04-01..2026-04-01",
        reader=reader,
        current_view=current_view,
        generated_at=datetime(2026, 4, 3, tzinfo=timezone.utc),
    )

    assert first.date_window == second.date_window
    assert len(current_view.summary_rows) == 1
    assert len(current_view.alert_state_rows) == 1
    assert current_view.summary_rows[0]["generated_at"] == datetime(
        2026,
        4,
        3,
        tzinfo=timezone.utc,
    )


def test_summary_current_view_keeps_distinct_object_scopes() -> None:
    reader = InMemoryRetrospectiveEvaluationReader(
        [
            _single_evaluation(object_ref="recommendation"),
            _single_evaluation(object_ref="risk_model"),
        ]
    )
    current_view = InMemoryRetrospectiveCurrentViewStorage()
    generated_at = datetime(2026, 4, 2, tzinfo=timezone.utc)

    recommendation_summary = build_retrospective_summary(
        "2026-04-01..2026-04-01",
        object_ref="recommendation",
        reader=reader,
        current_view=current_view,
        generated_at=generated_at,
    )
    risk_summary = build_retrospective_summary(
        "2026-04-01..2026-04-01",
        object_ref="risk_model",
        reader=reader,
        current_view=current_view,
        generated_at=generated_at,
    )

    expected_keys = {
        ("2026-04-01..2026-04-01", "T+1", "recommendation"),
        ("2026-04-01..2026-04-01", "T+1", "risk_model"),
    }
    assert recommendation_summary.object_ref == "recommendation"
    assert risk_summary.object_ref == "risk_model"
    assert set(current_view._summary_keys) == expected_keys
    assert set(current_view._alert_state_keys) == expected_keys
    assert {row["object_ref"] for row in current_view.summary_rows} == {
        "recommendation",
        "risk_model",
    }
    assert {row["object_ref"] for row in current_view.alert_state_rows} == {
        "recommendation",
        "risk_model",
    }


def test_summary_current_view_pair_upsert_is_thread_safe_by_window_and_horizon() -> (
    None
):
    class RacingCurrentViewStorage(InMemoryRetrospectiveCurrentViewStorage):
        def __init__(self) -> None:
            super().__init__()
            self.alert_barrier = Barrier(2)

        def upsert_alert_state(self, alert_state: AlertState) -> str:
            self.alert_barrier.wait(timeout=5)
            return super().upsert_alert_state(alert_state)

    current_view = RacingCurrentViewStorage()
    summaries = [
        _current_view_summary(
            date_window="2026-04-01..2026-04-01",
            horizon="T+1",
            label="one",
            window_start=date(2026, 4, 1),
        ),
        _current_view_summary(
            date_window="2026-04-02..2026-04-02",
            horizon="T+5",
            label="two",
            window_start=date(2026, 4, 2),
        ),
    ]

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(
                current_view.upsert_summary_and_alert_state,
                summary,
                summary.alert_state,
            )
            for summary in summaries
        ]
        for future in futures:
            future.result(timeout=5)

    expected_keys = {
        ("2026-04-01..2026-04-01", "T+1", None),
        ("2026-04-02..2026-04-02", "T+5", None),
    }
    assert set(current_view._summary_keys) == expected_keys
    assert set(current_view._alert_state_keys) == expected_keys
    assert {
        cast(dict[str, object], row["metrics"])["source"]
        for row in current_view.alert_state_rows
    } == {
        "one",
        "two",
    }


def test_reader_and_summary_use_same_business_date_filtering() -> None:
    evaluation = _single_evaluation().model_copy(
        update={"evaluated_at": datetime(2026, 4, 10, tzinfo=timezone.utc)}
    )
    window = RetroWindow(date(2026, 4, 1), date(2026, 4, 1))
    reader = InMemoryRetrospectiveEvaluationReader([evaluation])
    current_view = InMemoryRetrospectiveCurrentViewStorage()

    loaded = reader.load_evaluations(window)
    summary = build_retrospective_summary(
        "2026-04-01..2026-04-01",
        reader=reader,
        current_view=current_view,
        generated_at=datetime(2026, 4, 2, tzinfo=timezone.utc),
    )

    assert filter_evaluations_for_window([evaluation], window) == loaded
    assert summary.evaluation_count == 1


def test_summary_trend_orders_by_business_date_not_evaluated_at() -> None:
    reader = InMemoryRetrospectiveEvaluationReader(
        [
            _single_evaluation(
                cycle_id="cycle_20260404",
                trend_deviation=10.0,
                evaluated_at=datetime(2026, 4, 1, tzinfo=timezone.utc),
            ),
            _single_evaluation(
                cycle_id="cycle_20260403",
                trend_deviation=9.0,
                evaluated_at=datetime(2026, 4, 2, tzinfo=timezone.utc),
            ),
            _single_evaluation(
                cycle_id="cycle_20260402",
                trend_deviation=2.0,
                evaluated_at=datetime(2026, 4, 3, tzinfo=timezone.utc),
            ),
            _single_evaluation(
                cycle_id="cycle_20260401",
                trend_deviation=1.0,
                evaluated_at=datetime(2026, 4, 4, tzinfo=timezone.utc),
            ),
        ]
    )
    current_view = InMemoryRetrospectiveCurrentViewStorage()

    summary = build_retrospective_summary(
        "2026-04-01..2026-04-04",
        reader=reader,
        current_view=current_view,
        generated_at=datetime(2026, 4, 5, tzinfo=timezone.utc),
    )

    assert summary.trend == pytest.approx(4.8)


def test_summary_empty_window_raises_without_current_view_upsert() -> None:
    current_view = InMemoryRetrospectiveCurrentViewStorage()

    with pytest.raises(RetrospectiveSummaryError, match="no evaluations"):
        build_retrospective_summary(
            "2026-04-01..2026-04-01",
            reader=InMemoryRetrospectiveEvaluationReader([]),
            current_view=current_view,
            generated_at=datetime(2026, 4, 2, tzinfo=timezone.utc),
        )

    assert current_view.summary_rows == []
    assert current_view.alert_state_rows == []


def test_summary_current_view_write_is_atomic_when_alert_upsert_fails() -> None:
    class FailingAlertStateStorage(InMemoryRetrospectiveCurrentViewStorage):
        def _upsert_alert_state(
            self,
            alert_state: AlertState,
            *,
            summary_key: Any = None,
        ) -> str:
            super()._upsert_alert_state(alert_state, summary_key=summary_key)
            raise RuntimeError("alert state write failed")

    current_view = FailingAlertStateStorage()

    with pytest.raises(RetrospectiveStorageError, match="upsert current view failed"):
        build_retrospective_summary(
            "2026-04-01..2026-04-01",
            reader=InMemoryRetrospectiveEvaluationReader([_single_evaluation()]),
            current_view=current_view,
            generated_at=datetime(2026, 4, 2, tzinfo=timezone.utc),
        )

    assert current_view.summary_rows == []
    assert current_view.alert_state_rows == []


def test_retro_window_rejects_start_after_end() -> None:
    with pytest.raises(ValueError, match="start"):
        RetroWindow(date(2026, 4, 2), date(2026, 4, 1))


def test_summary_rejects_forbidden_input_payload_before_upsert() -> None:
    current_view = InMemoryRetrospectiveCurrentViewStorage()
    evaluation = _single_evaluation(
        baseline_vs_llm_breakdown={
            "layer": "L7",
            "nested": {"feature_weight_multiplier": 1.2},
        }
    )

    with pytest.raises(
        BoundaryViolationError,
        match=r"\$\.evaluations\[0\]\.baseline_vs_llm_breakdown\.nested"
        r"\.feature_weight_multiplier",
    ):
        build_retrospective_summary(
            "2026-04-01..2026-04-01",
            reader=InMemoryRetrospectiveEvaluationReader([evaluation]),
            current_view=current_view,
            generated_at=datetime(2026, 4, 2, tzinfo=timezone.utc),
        )

    assert current_view.summary_rows == []
    assert current_view.alert_state_rows == []


def test_summary_rejects_forbidden_alert_payload_before_upsert(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import audit_eval.retro.summary as summary_module

    current_view = InMemoryRetrospectiveCurrentViewStorage()

    def forbidden_alert(
        _history: object,
        *,
        evaluated_at: datetime | None = None,
    ) -> AlertState:
        effective_evaluated_at = evaluated_at or datetime(2026, 4, 2)
        return AlertState(
            level="NONE",
            reason_codes=(),
            window_start=date(2026, 4, 1),
            window_end=date(2026, 4, 1),
            evaluated_at=effective_evaluated_at,
            metrics={"feature_weight_multiplier": 1.2},
        )

    monkeypatch.setattr(summary_module, "evaluate_cumulative_alert", forbidden_alert)

    with pytest.raises(
        BoundaryViolationError,
        match=r"\$\.summary\.alert_state\.metrics\.feature_weight_multiplier",
    ):
        summary_module.build_retrospective_summary(
            "2026-04-01..2026-04-01",
            reader=InMemoryRetrospectiveEvaluationReader([_single_evaluation()]),
            current_view=current_view,
            generated_at=datetime(2026, 4, 2, tzinfo=timezone.utc),
        )

    assert current_view.summary_rows == []
    assert current_view.alert_state_rows == []


def test_summary_api_exports_are_available() -> None:
    from audit_eval.retro import (
        RetrospectiveCurrentViewStorage,
        RetrospectiveEvaluationReader,
        evaluate_cumulative_alert,
    )

    assert build_retrospective_summary.__name__ == "build_retrospective_summary"
    assert evaluate_cumulative_alert.__name__ == "evaluate_cumulative_alert"
    assert RetroWindow.__name__ == "RetroWindow"
    assert RetrospectiveEvaluationReader.__name__ == "RetrospectiveEvaluationReader"
    assert RetrospectiveCurrentViewStorage.__name__ == (
        "RetrospectiveCurrentViewStorage"
    )
