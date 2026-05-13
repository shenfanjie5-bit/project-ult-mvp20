import socket
import urllib.request
from collections.abc import Sequence
from datetime import date
from typing import Any

import pytest

from audit_eval._boundary import BoundaryViolationError
from audit_eval.audit import ReplayView
from audit_eval.audit.query import ReplayQueryContext
from audit_eval.contracts import AuditRecord, ReplayRecord, RetrospectiveEvaluation
from audit_eval.contracts.common import RetrospectiveHorizon
from audit_eval.retro import (
    HORIZONS,
    InMemoryRetrospectiveEvaluationStorage,
    MarketOutcome,
    RetrospectiveInputError,
    RetrospectiveTarget,
    UnsupportedRetrospectiveHorizon,
    compute_retrospective,
    extract_retrospective_seed,
    horizon_to_days,
    is_outcome_mature,
    require_mature_horizon,
    resolve_evaluation_date,
)


@pytest.fixture(autouse=True)
def block_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_network_call(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("Retrospective compute must not call network")

    monkeypatch.setattr(urllib.request, "urlopen", fail_network_call)
    monkeypatch.setattr(socket, "socket", fail_network_call)


class CountingRetrospectiveStorage(InMemoryRetrospectiveEvaluationStorage):
    def __init__(self) -> None:
        super().__init__()
        self.append_calls = 0

    def append_evaluations(
        self,
        evaluations: Sequence[RetrospectiveEvaluation],
    ) -> list[str]:
        self.append_calls += 1
        return super().append_evaluations(evaluations)


class MultiHorizonInputGateway:
    def __init__(
        self,
        outcomes: dict[tuple[str, str, str], MarketOutcome],
        targets: Sequence[RetrospectiveTarget] | None = None,
    ) -> None:
        self.targets = list(
            targets or [RetrospectiveTarget("cycle_20260401", "recommendation")]
        )
        self.outcomes = outcomes
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


def _outcome(
    horizon: RetrospectiveHorizon,
    *,
    realized_trend_score: float = 3.5,
    realized_risk_score: float = 0.5,
    breakdown: dict[str, Any] | None = None,
) -> MarketOutcome:
    return MarketOutcome(
        cycle_id="cycle_20260401",
        object_ref="recommendation",
        horizon=horizon,
        realized_trend_score=realized_trend_score,
        realized_risk_score=realized_risk_score,
        hit_rate_rel=0.7,
        baseline_vs_llm_breakdown=breakdown or {"layer": "L7", "horizon": horizon},
    )


def _gateway_for_horizons(
    *horizons: RetrospectiveHorizon,
    outcomes: Sequence[MarketOutcome] | None = None,
) -> MultiHorizonInputGateway:
    outcome_values = list(outcomes or [_outcome(horizon) for horizon in horizons])
    return MultiHorizonInputGateway(
        {
            (outcome.cycle_id, outcome.object_ref, outcome.horizon): outcome
            for outcome in outcome_values
        }
    )


def _audit_record(
    *,
    record_id: str,
    object_ref: str,
    seed_payload: dict[str, Any] | None,
) -> AuditRecord:
    parsed_result: dict[str, Any] = {}
    if seed_payload is not None:
        parsed_result["retrospective_seed"] = seed_payload
    return AuditRecord.model_validate(
        {
            "record_id": record_id,
            "cycle_id": "cycle_20260401",
            "layer": "L7",
            "object_ref": object_ref,
            "params_snapshot": {},
            "llm_lineage": {"called": False},
            "llm_cost": {},
            "sanitized_input": None,
            "input_hash": None,
            "raw_output": None,
            "parsed_result": parsed_result,
            "output_hash": None,
            "degradation_flags": {},
            "created_at": "2026-04-01T16:08:00Z",
        }
    )


def _replay_record() -> ReplayRecord:
    return ReplayRecord.model_validate(
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


def _replay_view_with_records(records: Sequence[AuditRecord]) -> ReplayView:
    return ReplayView(
        cycle_id="cycle_20260401",
        object_ref="recommendation",
        replay_record=_replay_record(),
        audit_records=tuple(records),
        manifest_snapshot_set={
            "recommendation": "snapshot://cycle_20260401/recommendation"
        },
        historical_formal_objects={"recommendation": {"action": "reduce_beta"}},
        graph_snapshot_ref=None,
        graph_snapshot=None,
        dagster_run_summary={},
    )


def _replay_view_with_seed(seed_payload: dict[str, Any] | None = None) -> ReplayView:
    return _replay_view_with_records(
        [
            _audit_record(
                record_id="audit-cycle_20260401-L7-recommendation",
                object_ref="recommendation",
                seed_payload=seed_payload
                or {
                    "trend_score": 1.0,
                    "risk_score": 2.0,
                    "baseline_vs_llm_breakdown": {"layer": "L7"},
                },
            )
        ]
    )


def test_horizon_helpers_resolve_maturity_dates() -> None:
    assert HORIZONS == ("T+1", "T+5", "T+20")
    assert horizon_to_days("T+1") == 1
    assert horizon_to_days("T+5") == 5
    assert horizon_to_days("T+20") == 20
    assert resolve_evaluation_date(date(2026, 4, 1), "T+20") == date(2026, 4, 21)
    assert is_outcome_mature("T+5", date(2026, 4, 1), date(2026, 4, 6))
    assert not is_outcome_mature("T+20", date(2026, 4, 1), date(2026, 4, 20))

    with pytest.raises(RetrospectiveInputError, match="not mature"):
        require_mature_horizon("T+20", date(2026, 4, 1), date(2026, 4, 20))

    with pytest.raises(UnsupportedRetrospectiveHorizon, match="Unsupported"):
        horizon_to_days("T+2")  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("horizon", "as_of_date"),
    [
        ("T+5", date(2026, 4, 6)),
        ("T+20", date(2026, 4, 21)),
    ],
)
def test_compute_retrospective_supports_mature_multi_horizon(
    horizon: RetrospectiveHorizon,
    as_of_date: date,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, str, ReplayQueryContext | None]] = []
    replay_view = _replay_view_with_seed()

    def fake_replay_cycle_object(
        cycle_id: str,
        object_ref: str,
        context: ReplayQueryContext | None = None,
    ) -> ReplayView:
        calls.append((cycle_id, object_ref, context))
        return replay_view

    monkeypatch.setattr(
        "audit_eval.audit.query.replay_cycle_object",
        fake_replay_cycle_object,
    )
    gateway = _gateway_for_horizons(horizon)
    storage = CountingRetrospectiveStorage()

    evaluations = compute_retrospective(
        horizon,
        date(2026, 4, 1),
        input_gateway=gateway,
        storage=storage,
        as_of_date=as_of_date,
    )

    assert len(evaluations) == 1
    evaluation = evaluations[0]
    assert evaluation.evaluation_id == f"retro-cycle_20260401-recommendation-{horizon}"
    assert evaluation.horizon == horizon
    assert evaluation.trend_deviation == 2.5
    assert evaluation.risk_deviation == 1.5
    assert evaluation.alert_score == 2.5
    assert evaluation.learning_score == pytest.approx(2.1)
    assert storage.append_calls == 1
    assert storage.rows[0]["evaluation_id"] == evaluation.evaluation_id
    assert gateway.target_calls == [(horizon, date(2026, 4, 1))]
    assert gateway.outcome_calls == [
        (
            RetrospectiveTarget("cycle_20260401", "recommendation"),
            horizon,
            date(2026, 4, 1),
        )
    ]
    assert calls == [("cycle_20260401", "recommendation", None)]


def test_compute_retrospective_rejects_immature_multi_horizon_without_append() -> None:
    storage = CountingRetrospectiveStorage()
    gateway = _gateway_for_horizons("T+20")

    with pytest.raises(RetrospectiveInputError, match="T\\+20.*not mature"):
        compute_retrospective(
            "T+20",
            date(2026, 4, 1),
            input_gateway=gateway,
            storage=storage,
            as_of_date=date(2026, 4, 20),
        )

    assert gateway.target_calls == []
    assert storage.append_calls == 0
    assert storage.rows == []


def test_compute_retrospective_rejects_outcome_horizon_mismatch_without_append(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "audit_eval.audit.query.replay_cycle_object",
        lambda *_args, **_kwargs: _replay_view_with_seed(),
    )
    mismatched_outcome = _outcome("T+1")
    gateway = MultiHorizonInputGateway(
        {
            (
                mismatched_outcome.cycle_id,
                mismatched_outcome.object_ref,
                "T+5",
            ): mismatched_outcome
        }
    )
    storage = CountingRetrospectiveStorage()

    with pytest.raises(RetrospectiveInputError, match="horizon"):
        compute_retrospective(
            "T+5",
            date(2026, 4, 1),
            input_gateway=gateway,
            storage=storage,
            as_of_date=date(2026, 4, 6),
        )

    assert storage.append_calls == 0
    assert storage.rows == []


def test_extract_retrospective_seed_ignores_upstream_non_target_seed() -> None:
    replay_view = _replay_view_with_records(
        [
            _audit_record(
                record_id="audit-cycle_20260401-L4-world_state",
                object_ref="world_state",
                seed_payload={"trend_score": 99.0, "risk_score": 99.0},
            ),
            _audit_record(
                record_id="audit-cycle_20260401-L7-recommendation",
                object_ref="recommendation",
                seed_payload={"trend_score": 1.0, "risk_score": 2.0},
            ),
        ]
    )

    seed = extract_retrospective_seed(replay_view)

    assert seed.object_ref == "recommendation"
    assert seed.expected_trend_score == 1.0
    assert seed.expected_risk_score == 2.0


def test_extract_retrospective_seed_prefers_parsed_result_over_params() -> None:
    parsed_seed = {"trend_score": 1.0, "risk_score": 2.0}
    params_seed = {"trend_score": 9.0, "risk_score": 9.0}
    record = _audit_record(
        record_id="audit-cycle_20260401-L7-recommendation",
        object_ref="recommendation",
        seed_payload=parsed_seed,
    ).model_copy(update={"params_snapshot": {"retrospective_seed": params_seed}})

    seed = extract_retrospective_seed(_replay_view_with_records([record]))

    assert seed.expected_trend_score == 1.0
    assert seed.expected_risk_score == 2.0


def test_extract_retrospective_seed_allows_duplicate_identical_target_seeds() -> None:
    seed_payload = {"trend_score": 1.0, "risk_score": 2.0}
    replay_view = _replay_view_with_records(
        [
            _audit_record(
                record_id="audit-cycle_20260401-L7-recommendation-a",
                object_ref="recommendation",
                seed_payload=seed_payload,
            ),
            _audit_record(
                record_id="audit-cycle_20260401-L7-recommendation-b",
                object_ref="recommendation",
                seed_payload=seed_payload,
            ),
        ]
    )

    seed = extract_retrospective_seed(replay_view)

    assert seed.expected_trend_score == 1.0
    assert seed.expected_risk_score == 2.0


def test_extract_retrospective_seed_rejects_conflicting_target_seeds() -> None:
    replay_view = _replay_view_with_records(
        [
            _audit_record(
                record_id="audit-cycle_20260401-L7-recommendation-a",
                object_ref="recommendation",
                seed_payload={"trend_score": 1.0, "risk_score": 2.0},
            ),
            _audit_record(
                record_id="audit-cycle_20260401-L7-recommendation-b",
                object_ref="recommendation",
                seed_payload={"trend_score": 1.5, "risk_score": 2.0},
            ),
        ]
    )

    with pytest.raises(RetrospectiveInputError, match="conflicting"):
        extract_retrospective_seed(replay_view)


def test_compute_retrospective_rejects_forbidden_multi_horizon_outcome(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "audit_eval.audit.query.replay_cycle_object",
        lambda *_args, **_kwargs: _replay_view_with_seed(),
    )
    forbidden_outcome = _outcome(
        "T+5",
        breakdown={"nested": {"feature_weight_multiplier": 1.2}},
    )
    gateway = _gateway_for_horizons("T+5", outcomes=[forbidden_outcome])
    storage = CountingRetrospectiveStorage()

    with pytest.raises(
        BoundaryViolationError,
        match=r"\$\.outcome\.baseline_vs_llm_breakdown\.nested"
        r"\.feature_weight_multiplier",
    ):
        compute_retrospective(
            "T+5",
            date(2026, 4, 1),
            input_gateway=gateway,
            storage=storage,
            as_of_date=date(2026, 4, 6),
        )

    assert storage.append_calls == 0
    assert storage.rows == []
