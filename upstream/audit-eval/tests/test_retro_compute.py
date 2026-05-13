import json
import re
import socket
import urllib.request
from collections.abc import Sequence
from copy import deepcopy
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, cast

import pytest

from audit_eval._boundary import BoundaryViolationError
from audit_eval.audit import (
    InMemoryFormalAuditStorageAdapter,
    ReplayQueryContext,
    ReplayView,
    build_in_memory_replay_query_context,
    persist_audit_records,
    persist_replay_records,
)
from audit_eval.contracts import (
    AuditRecord,
    AuditWriteBundle,
    CyclePublishManifestDraft,
    RetrospectiveEvaluation,
)
from audit_eval.contracts.common import RetrospectiveHorizon
from audit_eval.retro import (
    InMemoryRetrospectiveEvaluationStorage,
    MarketOutcome,
    RetrospectiveInputError,
    RetrospectiveSeed,
    RetrospectiveTarget,
    UnsupportedRetrospectiveHorizon,
    calculate_deviation,
    compute_retrospective,
    extract_retrospective_seed,
    get_default_evaluation_storage,
    get_default_input_gateway,
)
from audit_eval.retro.compute import _deviation_level
from audit_eval.retro.storage import RetrospectiveStorageError


SPIKE_FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "spike" / "cycle_20260410"
RETRO_FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "retro" / "t_plus_1"


@pytest.fixture(autouse=True)
def block_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_network_call(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("Retrospective compute must not call network")

    monkeypatch.setattr(urllib.request, "urlopen", fail_network_call)
    monkeypatch.setattr(socket, "socket", fail_network_call)


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _retro_bundle() -> AuditWriteBundle:
    return AuditWriteBundle.model_validate(
        _read_json(RETRO_FIXTURE_ROOT / "write_bundle.json")
    )


def _fixture_outcomes() -> dict[tuple[str, str, str], MarketOutcome]:
    outcomes: dict[tuple[str, str, str], MarketOutcome] = {}
    for payload in _read_json(RETRO_FIXTURE_ROOT / "market_outcomes.json"):
        outcome = MarketOutcome(
            cycle_id=payload["cycle_id"],
            object_ref=payload["object_ref"],
            horizon=payload["horizon"],
            realized_trend_score=payload["realized_trend_score"],
            realized_risk_score=payload["realized_risk_score"],
            hit_rate_rel=payload["hit_rate_rel"],
            baseline_vs_llm_breakdown=payload["baseline_vs_llm_breakdown"],
        )
        outcomes[(outcome.cycle_id, outcome.object_ref, outcome.horizon)] = outcome
    return outcomes


class StaticManifestGateway:
    def __init__(self, manifest: CyclePublishManifestDraft) -> None:
        self.manifest = manifest
        self.loaded_cycle_ids: list[str] = []

    def load(self, cycle_id: str) -> CyclePublishManifestDraft:
        self.loaded_cycle_ids.append(cycle_id)
        return self.manifest


class StaticFormalSnapshotGateway:
    def __init__(self, snapshots: dict[str, dict[str, Any]]) -> None:
        self.snapshots = snapshots
        self.loaded_snapshot_refs: list[str] = []

    def load_snapshot(self, snapshot_ref: str) -> dict[str, Any]:
        self.loaded_snapshot_refs.append(snapshot_ref)
        return self.snapshots[snapshot_ref]


class StaticGraphSnapshotGateway:
    def __init__(self, snapshot: dict[str, Any]) -> None:
        self.snapshot = snapshot

    def load(self, graph_snapshot_ref: str) -> dict[str, Any]:
        return self.snapshot


class StaticDagsterRunGateway:
    def __init__(self, summary: dict[str, Any]) -> None:
        self.summary = summary

    def load_summary(self, dagster_run_id: str) -> dict[str, Any]:
        return self.summary


class TrackingRepository:
    def __init__(self, delegate: Any) -> None:
        self.delegate = delegate
        self.calls: list[str] = []

    def get_replay_record(self, cycle_id: str, object_ref: str) -> Any:
        self.calls.append(f"replay_record:{cycle_id}:{object_ref}")
        return self.delegate.get_replay_record(cycle_id, object_ref)

    def get_audit_records(self, record_ids: Sequence[str]) -> list[AuditRecord]:
        self.calls.append("audit_records")
        return self.delegate.get_audit_records(record_ids)


class FixtureInputGateway:
    def __init__(
        self,
        *,
        targets: Sequence[RetrospectiveTarget] | None = None,
        outcomes: dict[tuple[str, str, str], MarketOutcome] | None = None,
    ) -> None:
        self.targets = list(
            targets or [RetrospectiveTarget("cycle_20260410", "recommendation")]
        )
        self.outcomes = _fixture_outcomes() if outcomes is None else outcomes
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


def _replay_context_from_persisted_bundle() -> tuple[
    ReplayQueryContext,
    TrackingRepository,
    StaticManifestGateway,
    StaticFormalSnapshotGateway,
]:
    bundle = _retro_bundle()
    formal_storage = InMemoryFormalAuditStorageAdapter()
    persist_audit_records(bundle, formal_storage)
    persist_replay_records(bundle, formal_storage)

    manifest_gateway = StaticManifestGateway(
        CyclePublishManifestDraft.model_validate(
            _read_json(SPIKE_FIXTURE_ROOT / "manifest.json")
        )
    )
    formal_gateway = StaticFormalSnapshotGateway(
        {
            "snapshot://cycle_20260410/world_state": _read_json(
                SPIKE_FIXTURE_ROOT / "formal_snapshots" / "world_state.json"
            ),
            "snapshot://cycle_20260410/recommendation": _read_json(
                SPIKE_FIXTURE_ROOT / "formal_snapshots" / "recommendation.json"
            ),
        }
    )
    base_context = build_in_memory_replay_query_context(
        storage=formal_storage,
        manifest_gateway=manifest_gateway,
        formal_gateway=formal_gateway,
        graph_gateway=StaticGraphSnapshotGateway(
            _read_json(SPIKE_FIXTURE_ROOT / "graph_snapshots" / "portfolio_graph.json")
        ),
        dagster_gateway=StaticDagsterRunGateway(
            _read_json(
                SPIKE_FIXTURE_ROOT
                / "dagster_runs"
                / "dagster-fixture-run-20260410.json"
            )
        ),
    )
    repository = TrackingRepository(base_context.repository)
    context = ReplayQueryContext(
        repository=repository,
        manifest_gateway=base_context.manifest_gateway,
        formal_gateway=base_context.formal_gateway,
        graph_gateway=base_context.graph_gateway,
        dagster_gateway=base_context.dagster_gateway,
    )
    return context, repository, manifest_gateway, formal_gateway


def test_compute_retrospective_t_plus_1_uses_replay_and_appends_evaluation() -> None:
    context, repository, manifest_gateway, formal_gateway = (
        _replay_context_from_persisted_bundle()
    )
    gateway = FixtureInputGateway()
    storage = CountingRetrospectiveStorage()

    evaluations = compute_retrospective(
        "T+1",
        date(2026, 4, 10),
        replay_context=context,
        input_gateway=gateway,
        storage=storage,
        as_of_date=date(2026, 4, 11),
    )

    assert len(evaluations) == 1
    evaluation = evaluations[0]
    assert evaluation.evaluation_id == "retro-cycle_20260410-recommendation-T+1"
    assert evaluation.trend_deviation == 2.0
    assert evaluation.risk_deviation == 1.0
    assert evaluation.alert_score == 2.0
    assert evaluation.learning_score == 1.6
    assert evaluation.deviation_level == 2
    assert evaluation.hit_rate_rel == 0.42
    assert evaluation.baseline_vs_llm_breakdown == {
        "baseline_trend_score": 0.5,
        "llm_trend_adjustment": 0.5,
        "baseline_risk_score": 1.5,
        "llm_risk_adjustment": 0.5,
        "baseline_hit": False,
        "llm_hit": True,
        "notes": "fixture outcome",
    }
    assert storage.append_calls == 1
    assert storage.rows[0]["evaluation_id"] == evaluation.evaluation_id
    assert gateway.target_calls == [("T+1", date(2026, 4, 10))]
    assert gateway.outcome_calls == [
        (
            RetrospectiveTarget("cycle_20260410", "recommendation"),
            "T+1",
            date(2026, 4, 10),
        )
    ]
    assert repository.calls == [
        "replay_record:cycle_20260410:recommendation",
        "audit_records",
    ]
    assert manifest_gateway.loaded_cycle_ids == ["cycle_20260410"]
    assert formal_gateway.loaded_snapshot_refs == [
        "snapshot://cycle_20260410/world_state",
        "snapshot://cycle_20260410/recommendation",
    ]


def test_extract_retrospective_seed_uses_canonical_audit_records(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context, _repository, _manifest_gateway, _formal_gateway = (
        _replay_context_from_persisted_bundle()
    )
    from audit_eval.audit.query import replay_cycle_object

    replay_view = replay_cycle_object(
        "cycle_20260410",
        "recommendation",
        context=context,
    )

    def fail_to_dict(_self: ReplayView) -> dict[str, Any]:
        raise AssertionError("extract_retrospective_seed must not use to_dict")

    monkeypatch.setattr(ReplayView, "to_dict", fail_to_dict)

    seed = extract_retrospective_seed(replay_view)

    assert seed == RetrospectiveSeed(
        cycle_id="cycle_20260410",
        object_ref="recommendation",
        expected_trend_score=1.0,
        expected_risk_score=2.0,
        baseline_vs_llm_breakdown={
            "baseline_trend_score": 0.5,
            "llm_trend_adjustment": 0.5,
            "baseline_risk_score": 1.5,
            "llm_risk_adjustment": 0.5,
        },
    )


@pytest.mark.parametrize(
    "seed_payload",
    [
        {},
        {"trend_score": "high", "risk_score": 2.0},
        {"trend_score": 1.0, "risk_score": "low"},
    ],
)
def test_extract_retrospective_seed_rejects_missing_or_non_numeric_scores(
    seed_payload: dict[str, Any],
) -> None:
    replay_view = _replay_view_with_seed(seed_payload)

    with pytest.raises(RetrospectiveInputError, match="trend_score|risk_score"):
        extract_retrospective_seed(replay_view)


def test_calculate_deviation_returns_absolute_t_plus_1_deviation() -> None:
    result = calculate_deviation(
        RetrospectiveSeed("cycle", "object", 1.0, 4.0, {"layer": "L7"}),
        MarketOutcome("cycle", "object", "T+1", 3.5, 1.0, None, {"source": "test"}),
    )

    assert result.trend_deviation == 2.5
    assert result.risk_deviation == 3.0
    assert result.hit_rate_rel is None
    assert result.baseline_vs_llm_breakdown == {"layer": "L7", "source": "test"}


def test_compute_retrospective_calls_replay_cycle_object(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, str, ReplayQueryContext | None]] = []
    replay_view = _replay_view_with_seed({"trend_score": 1.0, "risk_score": 2.0})

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
    storage = CountingRetrospectiveStorage()
    gateway = FixtureInputGateway()
    context = cast(ReplayQueryContext, object())

    compute_retrospective(
        "T+1",
        date(2026, 4, 10),
        replay_context=context,
        input_gateway=gateway,
        storage=storage,
        as_of_date=date(2026, 4, 11),
    )

    assert calls == [("cycle_20260410", "recommendation", context)]
    assert storage.append_calls == 1


def test_compute_retrospective_rejects_immature_t_plus_1_without_append() -> None:
    storage = CountingRetrospectiveStorage()

    with pytest.raises(RetrospectiveInputError, match="not mature"):
        compute_retrospective(
            "T+1",
            date(2026, 4, 10),
            input_gateway=FixtureInputGateway(),
            storage=storage,
            as_of_date=date(2026, 4, 10),
        )

    assert storage.append_calls == 0
    assert storage.rows == []


def test_compute_retrospective_rejects_unknown_horizon_without_append() -> None:
    storage = CountingRetrospectiveStorage()

    with pytest.raises(UnsupportedRetrospectiveHorizon, match="Unsupported"):
        compute_retrospective(
            "T+2",  # type: ignore[arg-type]
            date(2026, 4, 10),
            input_gateway=FixtureInputGateway(),
            storage=storage,
            as_of_date=date(2026, 4, 30),
        )

    assert storage.append_calls == 0
    assert storage.rows == []


def test_compute_retrospective_rejects_forbidden_field_in_outcome_without_append(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    outcome = deepcopy(_fixture_outcomes()[("cycle_20260410", "recommendation", "T+1")])
    outcome.baseline_vs_llm_breakdown["nested"] = {"feature_weight_multiplier": 1.2}
    gateway = FixtureInputGateway(
        outcomes={("cycle_20260410", "recommendation", "T+1"): outcome}
    )
    replay_view = _replay_view_with_seed({"trend_score": 1.0, "risk_score": 2.0})
    monkeypatch.setattr(
        "audit_eval.audit.query.replay_cycle_object",
        lambda *_args, **_kwargs: replay_view,
    )
    storage = CountingRetrospectiveStorage()

    with pytest.raises(
        BoundaryViolationError,
        match=r"\$\.outcome\.baseline_vs_llm_breakdown\.nested"
        r"\.feature_weight_multiplier",
    ):
        compute_retrospective(
            "T+1",
            date(2026, 4, 10),
            input_gateway=gateway,
            storage=storage,
            as_of_date=date(2026, 4, 11),
        )

    assert storage.append_calls == 0
    assert storage.rows == []


def test_in_memory_storage_rejects_forbidden_field_without_append() -> None:
    storage = InMemoryRetrospectiveEvaluationStorage()
    evaluation = RetrospectiveEvaluation(
        evaluation_id="retro-cycle_20260410-recommendation-T+1",
        cycle_id="cycle_20260410",
        object_ref="recommendation",
        horizon="T+1",
        trend_deviation=2.0,
        risk_deviation=1.0,
        alert_score=2.0,
        learning_score=1.6,
        deviation_level=2,
        hit_rate_rel=0.42,
        baseline_vs_llm_breakdown={
            "nested": {"feature_weight_multiplier": 1.2},
        },
        evaluated_at=datetime(2026, 4, 11, tzinfo=timezone.utc),
    )

    with pytest.raises(
        BoundaryViolationError,
        match=r"\$\.evaluations\[0\]\.baseline_vs_llm_breakdown\.nested"
        r"\.feature_weight_multiplier",
    ):
        storage.append_evaluations([evaluation])

    assert storage.rows == []


def test_extract_seed_rejects_forbidden_field_in_seed_metadata() -> None:
    replay_view = _replay_view_with_seed(
        {
            "trend_score": 1.0,
            "risk_score": 2.0,
            "metadata": {"feature_weight_multiplier": 1.2},
        }
    )

    with pytest.raises(
        BoundaryViolationError,
        match=r"feature_weight_multiplier",
    ):
        extract_retrospective_seed(replay_view)


def test_compute_retrospective_validation_error_prevents_partial_append(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gateway = FixtureInputGateway(
        outcomes={
            ("cycle_20260410", "recommendation", "T+1"): MarketOutcome(
                "cycle_other",
                "recommendation",
                "T+1",
                3.0,
                3.0,
                0.42,
                {},
            )
        }
    )
    replay_view = _replay_view_with_seed({"trend_score": 1.0, "risk_score": 2.0})
    monkeypatch.setattr(
        "audit_eval.audit.query.replay_cycle_object",
        lambda *_args, **_kwargs: replay_view,
    )
    storage = CountingRetrospectiveStorage()

    with pytest.raises(RetrospectiveInputError, match="cycle_id"):
        compute_retrospective(
            "T+1",
            date(2026, 4, 10),
            input_gateway=gateway,
            storage=storage,
            as_of_date=date(2026, 4, 11),
        )

    assert storage.append_calls == 0
    assert storage.rows == []


def test_default_retro_dependencies_fail_closed() -> None:
    with pytest.raises(RetrospectiveInputError, match="No default"):
        get_default_input_gateway()

    with pytest.raises(RetrospectiveStorageError, match="No default"):
        get_default_evaluation_storage()


def test_retro_package_has_no_provider_or_http_client_dependencies() -> None:
    forbidden = re.compile(r"\b(openai|anthropic|requests|httpx)\b")
    for path in (Path(__file__).parents[1] / "src" / "audit_eval" / "retro").glob(
        "*.py"
    ):
        assert forbidden.search(path.read_text(encoding="utf-8")) is None, path


def test_deviation_level_clamps_to_project_range() -> None:
    assert _deviation_level(0.0) == 0
    assert _deviation_level(2.9) == 2
    assert _deviation_level(7.0) == 4


def _replay_view_with_seed(seed_payload: dict[str, Any]) -> ReplayView:
    audit_record = AuditRecord.model_validate(
        {
            "record_id": "audit-cycle_20260410-L7-recommendation",
            "cycle_id": "cycle_20260410",
            "layer": "L7",
            "object_ref": "recommendation",
            "params_snapshot": {},
            "llm_lineage": {"called": False},
            "llm_cost": {},
            "sanitized_input": None,
            "input_hash": None,
            "raw_output": None,
            "parsed_result": {"retrospective_seed": seed_payload},
            "output_hash": None,
            "degradation_flags": {},
            "created_at": "2026-04-10T16:08:00Z",
        }
    )
    replay_record = _retro_bundle().replay_records_by_object_ref()["recommendation"]
    return ReplayView(
        cycle_id="cycle_20260410",
        object_ref="recommendation",
        replay_record=replay_record,
        audit_records=(audit_record,),
        manifest_snapshot_set={},
        historical_formal_objects={},
        graph_snapshot_ref=None,
        graph_snapshot=None,
        dagster_run_summary={},
    )
