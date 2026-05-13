import socket
import urllib.request
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone
from threading import Barrier
from typing import Any

import pytest

from audit_eval.audit import ReplayView
from audit_eval.contracts import AuditRecord, ReplayRecord, RetrospectiveEvaluation
from audit_eval.contracts.common import RetrospectiveHorizon
from audit_eval.retro import (
    HORIZONS,
    HorizonCoverageReport,
    InMemoryRetrospectiveCurrentViewStorage,
    InMemoryRetrospectiveEvaluationReader,
    InMemoryRetrospectiveEvaluationStorage,
    MarketOutcome,
    RetroWindow,
    RetrospectiveBackfillResult,
    RetrospectiveInputError,
    RetrospectiveJob,
    RetrospectiveTarget,
    build_retrospective_summary,
    check_horizon_coverage,
    evaluate_cumulative_alert,
    run_backfill,
)


@pytest.fixture(autouse=True)
def block_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_network_call(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("Retrospective backfill must not call network")

    monkeypatch.setattr(urllib.request, "urlopen", fail_network_call)
    monkeypatch.setattr(socket, "socket", fail_network_call)


class BackfillInputGateway:
    def __init__(
        self,
        *,
        targets: Sequence[RetrospectiveTarget] | None = None,
        outcomes: Sequence[MarketOutcome] | None = None,
    ) -> None:
        self.targets = list(
            targets or [RetrospectiveTarget("cycle_20260401", "recommendation")]
        )
        outcome_values = list(
            outcomes or [_market_outcome(horizon) for horizon in HORIZONS]
        )
        self.outcomes = {
            (outcome.cycle_id, outcome.object_ref, outcome.horizon): outcome
            for outcome in outcome_values
        }
        self.target_calls: list[tuple[str, date]] = []
        self.outcome_calls: list[tuple[RetrospectiveTarget, str, date]] = []

    def list_targets(
        self,
        horizon: RetrospectiveHorizon,
        date_ref: date,
    ) -> Sequence[RetrospectiveTarget]:
        self.target_calls.append((horizon, date_ref))
        return self.targets

    def load_market_outcome(
        self,
        target: RetrospectiveTarget,
        horizon: RetrospectiveHorizon,
        date_ref: date,
    ) -> MarketOutcome:
        self.outcome_calls.append((target, horizon, date_ref))
        return self.outcomes[(target.cycle_id, target.object_ref, horizon)]


class CountingReaderStorage(InMemoryRetrospectiveEvaluationStorage):
    def __init__(self) -> None:
        super().__init__()
        self.append_calls = 0
        self.upsert_calls = 0
        self.loaded_windows: list[RetroWindow] = []

    def append_evaluations(
        self,
        evaluations: Sequence[RetrospectiveEvaluation],
    ) -> list[str]:
        self.append_calls += 1
        return super().append_evaluations(evaluations)

    def upsert_evaluations_by_id(
        self,
        evaluations: Sequence[RetrospectiveEvaluation],
    ) -> Any:
        self.upsert_calls += 1
        return super().upsert_evaluations_by_id(evaluations)

    def load_evaluations(
        self,
        window: RetroWindow,
    ) -> list[RetrospectiveEvaluation]:
        self.loaded_windows.append(window)
        return super().load_evaluations(window)


def _market_outcome(
    horizon: RetrospectiveHorizon,
    *,
    realized_trend_score: float = 3.0,
    realized_risk_score: float = 3.0,
) -> MarketOutcome:
    return MarketOutcome(
        cycle_id="cycle_20260401",
        object_ref="recommendation",
        horizon=horizon,
        realized_trend_score=realized_trend_score,
        realized_risk_score=realized_risk_score,
        hit_rate_rel=0.42,
        baseline_vs_llm_breakdown={"layer": "L7", "horizon": horizon},
    )


def _audit_record() -> AuditRecord:
    return AuditRecord.model_validate(
        {
            "record_id": "audit-cycle_20260401-L7-recommendation",
            "cycle_id": "cycle_20260401",
            "layer": "L7",
            "object_ref": "recommendation",
            "params_snapshot": {},
            "llm_lineage": {"called": False},
            "llm_cost": {},
            "sanitized_input": None,
            "input_hash": None,
            "raw_output": None,
            "parsed_result": {
                "retrospective_seed": {
                    "trend_score": 1.0,
                    "risk_score": 2.0,
                    "baseline_vs_llm_breakdown": {"layer": "L7"},
                }
            },
            "output_hash": None,
            "degradation_flags": {},
            "created_at": "2026-04-01T16:08:00Z",
        }
    )


def _replay_view() -> ReplayView:
    replay_record = ReplayRecord.model_validate(
        {
            "replay_id": "replay-cycle_20260401-recommendation",
            "cycle_id": "cycle_20260401",
            "object_ref": "recommendation",
            "audit_record_ids": ["audit-cycle_20260401-L7-recommendation"],
            "manifest_cycle_id": "cycle_20260401",
            "formal_snapshot_refs": {
                "recommendation": "snapshot://cycle_20260401/recommendation"
            },
            "graph_snapshot_ref": None,
            "dagster_run_id": "dagster-fixture-run-20260401",
            "replay_mode": "read_history",
            "created_at": "2026-04-01T16:09:00Z",
        }
    )
    return ReplayView(
        cycle_id="cycle_20260401",
        object_ref="recommendation",
        replay_record=replay_record,
        audit_records=(_audit_record(),),
        manifest_snapshot_set={
            "recommendation": "snapshot://cycle_20260401/recommendation"
        },
        historical_formal_objects={"recommendation": {"action": "reduce_beta"}},
        graph_snapshot_ref=None,
        graph_snapshot=None,
        dagster_run_summary={},
    )


def _evaluation(
    horizon: RetrospectiveHorizon,
    *,
    object_ref: str = "recommendation",
    day: date = date(2026, 4, 25),
    alert_score: float = 2.0,
) -> RetrospectiveEvaluation:
    return RetrospectiveEvaluation(
        evaluation_id=f"retro-cycle_20260401-{object_ref}-{horizon}",
        cycle_id="cycle_20260401",
        object_ref=object_ref,
        horizon=horizon,
        trend_deviation=alert_score,
        risk_deviation=1.0,
        alert_score=alert_score,
        learning_score=RetrospectiveEvaluation.derive_learning_score(
            alert_score,
            1.0,
        ),
        deviation_level=min(4, int(alert_score)),
        hit_rate_rel=0.42,
        baseline_vs_llm_breakdown={"layer": "L7", "horizon": horizon},
        evaluated_at=datetime(day.year, day.month, day.day, 12, tzinfo=timezone.utc),
    )


def test_run_backfill_writes_all_horizons_and_is_idempotent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    replay_calls: list[tuple[str, str]] = []

    def fake_replay_cycle_object(
        cycle_id: str, object_ref: str, **_kwargs: Any
    ) -> ReplayView:
        replay_calls.append((cycle_id, object_ref))
        return _replay_view()

    monkeypatch.setattr(
        "audit_eval.audit.query.replay_cycle_object",
        fake_replay_cycle_object,
    )
    gateway = BackfillInputGateway()
    storage = CountingReaderStorage()
    expected_ids = tuple(
        f"retro-cycle_20260401-recommendation-{horizon}" for horizon in HORIZONS
    )

    first = run_backfill(
        date(2026, 4, 1),
        input_gateway=gateway,
        storage=storage,
        as_of_date=date(2026, 4, 25),
    )
    second = run_backfill(
        date(2026, 4, 1),
        input_gateway=gateway,
        storage=storage,
        as_of_date=date(2026, 4, 25),
    )

    assert first.job == RetrospectiveJob(date(2026, 4, 1), HORIZONS)
    assert first.written_evaluation_ids == expected_ids
    assert first.skipped_existing_ids == ()
    assert first.coverage.is_complete
    assert first.coverage.coverage_ratio == 1.0
    assert second.written_evaluation_ids == ()
    assert second.skipped_existing_ids == expected_ids
    assert second.coverage.is_complete
    assert storage.append_calls == 0
    assert storage.upsert_calls == 1
    assert [row["evaluation_id"] for row in storage.rows] == list(expected_ids)
    assert [row["horizon"] for row in storage.rows] == list(HORIZONS)
    assert replay_calls == [("cycle_20260401", "recommendation")] * 3
    assert all(window.start == date.min for window in storage.loaded_windows)
    assert all(window.end == date.max for window in storage.loaded_windows)


def test_run_backfill_atomic_upsert_prevents_overlapping_duplicates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    replay_calls: list[tuple[str, str]] = []

    def fake_replay_cycle_object(
        cycle_id: str, object_ref: str, **_kwargs: Any
    ) -> ReplayView:
        replay_calls.append((cycle_id, object_ref))
        return _replay_view()

    monkeypatch.setattr(
        "audit_eval.audit.query.replay_cycle_object",
        fake_replay_cycle_object,
    )
    gateway = BackfillInputGateway()
    storage = CountingReaderStorage()
    barrier = Barrier(2)
    original_upsert = storage.upsert_evaluations_by_id

    def synchronized_upsert(evaluations: Sequence[RetrospectiveEvaluation]) -> Any:
        barrier.wait(timeout=5)
        return original_upsert(evaluations)

    setattr(storage, "upsert_evaluations_by_id", synchronized_upsert)

    def run_once() -> RetrospectiveBackfillResult:
        return run_backfill(
            date(2026, 4, 1),
            horizons=("T+5",),
            input_gateway=gateway,
            storage=storage,
            as_of_date=date(2026, 4, 6),
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _index: run_once(), range(2)))

    evaluation_id = "retro-cycle_20260401-recommendation-T+5"
    written_ids = [
        written_id
        for result in results
        for written_id in result.written_evaluation_ids
    ]
    skipped_ids = [
        skipped_id
        for result in results
        for skipped_id in result.skipped_existing_ids
    ]

    assert written_ids == [evaluation_id]
    assert skipped_ids == [evaluation_id]
    assert [row["evaluation_id"] for row in storage.rows] == [evaluation_id]
    assert all(result.coverage.is_complete for result in results)
    assert storage.upsert_calls == 2
    assert replay_calls == [("cycle_20260401", "recommendation")] * 2


def test_run_backfill_immature_batch_fails_before_partial_write() -> None:
    gateway = BackfillInputGateway()
    storage = CountingReaderStorage()

    with pytest.raises(RetrospectiveInputError, match="T\\+20.*not mature"):
        run_backfill(
            date(2026, 4, 1),
            input_gateway=gateway,
            storage=storage,
            as_of_date=date(2026, 4, 20),
        )

    assert gateway.target_calls == []
    assert storage.append_calls == 0
    assert storage.upsert_calls == 0
    assert storage.rows == []
    assert storage.loaded_windows == []


def test_run_backfill_filters_to_object_ref_before_compute(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    replay_calls: list[tuple[str, str]] = []

    def fake_replay_cycle_object(
        cycle_id: str, object_ref: str, **_kwargs: Any
    ) -> ReplayView:
        replay_calls.append((cycle_id, object_ref))
        return _replay_view()

    monkeypatch.setattr(
        "audit_eval.audit.query.replay_cycle_object",
        fake_replay_cycle_object,
    )
    gateway = BackfillInputGateway(
        targets=[
            RetrospectiveTarget("cycle_20260401", "risk_model"),
            RetrospectiveTarget("cycle_20260401", "recommendation"),
        ],
    )
    storage = CountingReaderStorage()

    result = run_backfill(
        date(2026, 4, 1),
        horizons=("T+1",),
        object_ref=" recommendation ",
        input_gateway=gateway,
        storage=storage,
        as_of_date=date(2026, 4, 2),
    )

    assert result.job == RetrospectiveJob(
        date(2026, 4, 1),
        ("T+1",),
        "recommendation",
    )
    assert result.coverage.object_refs == ("recommendation",)
    assert replay_calls == [("cycle_20260401", "recommendation")]
    assert gateway.outcome_calls == [
        (
            RetrospectiveTarget("cycle_20260401", "recommendation"),
            "T+1",
            date(2026, 4, 1),
        )
    ]


def test_run_backfill_rejects_blank_object_ref_before_boundaries() -> None:
    gateway = BackfillInputGateway()
    storage = CountingReaderStorage()

    with pytest.raises(RetrospectiveInputError, match="object_ref"):
        run_backfill(
            date(2026, 4, 1),
            object_ref=" ",
            input_gateway=gateway,
            storage=storage,
            as_of_date=date(2026, 4, 25),
        )

    assert gateway.target_calls == []
    assert storage.rows == []


def test_run_backfill_rejects_unmatched_object_ref_before_compute(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    replay_calls: list[tuple[str, str]] = []

    def fake_replay_cycle_object(
        cycle_id: str, object_ref: str, **_kwargs: Any
    ) -> ReplayView:
        replay_calls.append((cycle_id, object_ref))
        return _replay_view()

    monkeypatch.setattr(
        "audit_eval.audit.query.replay_cycle_object",
        fake_replay_cycle_object,
    )
    gateway = BackfillInputGateway(
        targets=[RetrospectiveTarget("cycle_20260401", "risk_model")],
    )
    storage = CountingReaderStorage()

    with pytest.raises(RetrospectiveInputError, match="recommendation"):
        run_backfill(
            date(2026, 4, 1),
            horizons=("T+1", "T+5"),
            object_ref="recommendation",
            input_gateway=gateway,
            storage=storage,
            as_of_date=date(2026, 4, 6),
        )

    assert replay_calls == []
    assert gateway.target_calls == [
        ("T+1", date(2026, 4, 1)),
        ("T+5", date(2026, 4, 1)),
    ]
    assert gateway.outcome_calls == []
    assert storage.rows == []
    assert storage.loaded_windows == []


def test_check_horizon_coverage_reports_missing_horizons() -> None:
    report = check_horizon_coverage(
        [
            _evaluation("T+1"),
            _evaluation("T+20"),
            _evaluation("T+5", object_ref="risk_model"),
        ],
        object_refs=("recommendation", "risk_model"),
    )

    assert not report.is_complete
    assert report.covered_count == 3
    assert report.expected_count == 6
    assert report.coverage_ratio == 0.5
    assert report.missing_horizons_by_object["recommendation"] == ("T+5",)
    assert report.missing_horizons_by_object["risk_model"] == ("T+1", "T+20")


def test_summary_reads_multi_horizon_backfill_and_alert_ignores_non_t_plus_1(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "audit_eval.audit.query.replay_cycle_object",
        lambda *_args, **_kwargs: _replay_view(),
    )
    storage = CountingReaderStorage()
    run_backfill(
        date(2026, 4, 1),
        input_gateway=BackfillInputGateway(),
        storage=storage,
        as_of_date=date(2026, 4, 25),
    )
    current_view = InMemoryRetrospectiveCurrentViewStorage()
    window = f"{date.min.isoformat()}..{date.max.isoformat()}"

    summary_t5 = build_retrospective_summary(
        window,
        horizon="T+5",
        reader=storage,
        current_view=current_view,
        generated_at=datetime(2026, 4, 25, tzinfo=timezone.utc),
    )
    summary_t20 = build_retrospective_summary(
        window,
        horizon="T+20",
        reader=storage,
        current_view=current_view,
        generated_at=datetime(2026, 4, 25, tzinfo=timezone.utc),
    )

    assert summary_t5.horizon == "T+5"
    assert summary_t5.evaluation_count == 1
    assert summary_t5.alert_state.level == "NONE"
    assert summary_t20.horizon == "T+20"
    assert summary_t20.evaluation_count == 1
    assert summary_t20.alert_state.level == "NONE"
    assert len(current_view.summary_rows) == 2
    assert len(current_view.alert_state_rows) == 2

    alert = evaluate_cumulative_alert(
        [_evaluation("T+5", alert_score=4.0), _evaluation("T+20", alert_score=4.0)],
        evaluated_at=datetime(2026, 4, 25, tzinfo=timezone.utc),
    )
    assert alert.level == "NONE"
    assert alert.metrics["daily_alert_score_max"] == {}


def test_reader_filtering_and_coverage_use_same_horizon_object_semantics() -> None:
    reader = InMemoryRetrospectiveEvaluationReader(
        [
            _evaluation("T+5", object_ref="recommendation"),
            _evaluation("T+1", object_ref="recommendation"),
            _evaluation("T+5", object_ref="risk_model"),
        ]
    )
    window = RetroWindow(
        date.min,
        date.max,
        horizon="T+5",
        object_ref="recommendation",
    )

    loaded = reader.load_evaluations(window)
    report = check_horizon_coverage(
        loaded,
        expected_horizons=("T+5",),
        object_refs=("recommendation",),
    )

    assert reader.loaded_windows == [window]
    assert [evaluation.evaluation_id for evaluation in loaded] == [
        "retro-cycle_20260401-recommendation-T+5"
    ]
    assert report.is_complete
    assert report.covered_horizons_by_object["recommendation"] == ("T+5",)


def test_backfill_exports_are_available() -> None:
    assert run_backfill.__name__ == "run_backfill"
    assert check_horizon_coverage.__name__ == "check_horizon_coverage"
    assert RetrospectiveJob.__name__ == "RetrospectiveJob"
    assert RetrospectiveBackfillResult.__name__ == "RetrospectiveBackfillResult"
    assert HorizonCoverageReport.__name__ == "HorizonCoverageReport"
