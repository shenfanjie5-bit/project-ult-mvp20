"""Tests for formal L7 recommendation generation service."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from inspect import signature

import pytest

from main_core.common.contexts import RecommendationConstraintInputs
from main_core.common.errors import MainCoreError
from main_core.common.schemas import (
    AlphaResultSnapshot,
    FeatureSignalBundle,
    OfficialAlphaPool,
    OverrideRecord,
    RecommendationSnapshot,
    WorldStateSnapshot,
)
from main_core.l5_universe import select_mvp20_decision_pool
from main_core.l7_recommendation import (
    InMemoryOverrideStore,
    generate_recommendations,
    submit_override,
)
from main_core.l7_recommendation.service import (
    BUY_SCORE_THRESHOLD,
    REDUCE_SCORE_THRESHOLD,
)


def _pool(
    selected_entities: Sequence[str] = ("ENT_A", "ENT_B", "ENT_C"),
    *,
    cycle_id: str = "cycle_l7",
) -> OfficialAlphaPool:
    return OfficialAlphaPool(
        cycle_id=cycle_id,
        observation_pool_size=len(selected_entities),
        official_alpha_pool_capacity=100,
        selected_entities=list(selected_entities),
        added_entities=list(selected_entities),
        removed_entities=[],
        freeze_reason_map={},
    )


def _world_state(
    final_regime: str = "neutral",
    *,
    cycle_id: str = "cycle_l7",
) -> WorldStateSnapshot:
    if final_regime == "risk_off":
        baseline_regime = "neutral"
        llm_delta = -1
    elif final_regime == "risk_on":
        baseline_regime = "neutral"
        llm_delta = 1
    else:
        baseline_regime = "neutral"
        llm_delta = 0
    return WorldStateSnapshot(
        cycle_id=cycle_id,
        baseline_regime=baseline_regime,
        llm_delta=llm_delta,
        final_regime=final_regime,
        llm_rationale="fixture",
        actual_model_used="fixture",
        actual_provider="local",
        fallback_path=[],
    )


def _analysis(
    entity_id: str,
    score: float | None,
    *,
    cycle_id: str = "cycle_l7",
    confidence: float = 0.72,
    status: str = "ok",
) -> AlphaResultSnapshot:
    return AlphaResultSnapshot(
        cycle_id=cycle_id,
        entity_id=entity_id,
        analyzer_type="single_prompt_v1",
        score=score,
        confidence=confidence,
        rationale="fixture alpha",
        similar_cases=[],
        status=status,
    )


def _feature_bundle(
    entity_id: str,
    score: float,
    *,
    cycle_id: str = "cycle_l7",
) -> FeatureSignalBundle:
    return FeatureSignalBundle(
        cycle_id=cycle_id,
        entity_id=entity_id,
        feature_values={"momentum": score},
        signal_values={"candidate_score": score},
        graph_features={},
        feature_weight_multiplier={"momentum": 1.0},
    )


def _override(
    entity_id: str,
    action_type: str,
    *,
    cycle_id: str = "cycle_l7",
    submitted_at: datetime | None = None,
) -> OverrideRecord:
    return OverrideRecord(
        cycle_id=cycle_id,
        entity_id=entity_id,
        submitted_by="analyst",
        action_type=action_type,
        rationale="human override",
        submitted_at=submitted_at or datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC),
    )


def test_generate_recommendations_maps_scores_in_pool_order() -> None:
    pool = _pool(("ENT_B", "ENT_A", "ENT_C"))
    analyses = [
        _analysis("ENT_A", BUY_SCORE_THRESHOLD),
        _analysis("ENT_C", REDUCE_SCORE_THRESHOLD),
        _analysis("ENT_B", 0.5),
    ]

    recommendations = generate_recommendations(pool, analyses, _world_state())

    assert [recommendation.entity_id for recommendation in recommendations] == [
        "ENT_B",
        "ENT_A",
        "ENT_C",
    ]
    assert [recommendation.action_type for recommendation in recommendations] == [
        "hold",
        "buy",
        "reduce",
    ]
    assert [recommendation.rating for recommendation in recommendations] == ["B", "A", "C"]


def test_generate_recommendations_with_mvp20_pool_ignores_related_risk_entities() -> None:
    manifest_targets = tuple(f"ENT_T{index:02d}" for index in range(1, 21))
    related_entities = ("ENT_RELATED_A", "ENT_RELATED_B")
    world_state = _world_state()
    bundles = [
        *[
            _feature_bundle(entity_id, float(index))
            for index, entity_id in enumerate(manifest_targets)
        ],
        _feature_bundle(related_entities[0], 999.0),
        _feature_bundle(related_entities[1], 998.0),
    ]
    pool = select_mvp20_decision_pool(world_state, bundles, manifest_targets)
    analyses = [
        _analysis(entity_id, BUY_SCORE_THRESHOLD)
        for entity_id in manifest_targets
    ]

    recommendations = generate_recommendations(
        pool,
        analyses,
        world_state,
        risk_context={"related_entities": related_entities},
    )

    assert [recommendation.entity_id for recommendation in recommendations] == list(
        manifest_targets
    )
    assert not any(
        recommendation.entity_id in related_entities
        for recommendation in recommendations
    )


def test_generate_recommendations_passes_inconclusive_through_explicitly() -> None:
    pool = _pool(("ENT_A",))
    analyses = [_analysis("ENT_A", None, status="inconclusive", confidence=0.0)]

    [recommendation] = generate_recommendations(pool, analyses, _world_state())

    assert recommendation.action_type == "inconclusive"
    assert recommendation.rating is None
    assert recommendation.confidence is None
    assert recommendation.triggered_by == "system"


@pytest.mark.parametrize("override_action", ["buy", "hold", "reduce"])
def test_generate_recommendations_keeps_inconclusive_after_action_override(
    override_action: str,
) -> None:
    pool = _pool(("ENT_A",))
    analyses = [_analysis("ENT_A", None, status="inconclusive", confidence=0.0)]

    [recommendation] = generate_recommendations(
        pool,
        analyses,
        _world_state(),
        overrides=[_override("ENT_A", override_action)],
    )

    assert recommendation.action_type == "inconclusive"
    assert recommendation.rating is None
    assert recommendation.confidence is None
    assert recommendation.triggered_by == "human_decision"
    assert recommendation.override_applied is True


def test_generate_recommendations_rejects_analysis_outside_pool() -> None:
    pool = _pool(("ENT_A",))

    with pytest.raises(MainCoreError, match="pool.selected_entities"):
        generate_recommendations(
            pool,
            [_analysis("ENT_A", 0.5), _analysis("ENT_Z", 0.5)],
            _world_state(),
        )


def test_generate_recommendations_rejects_missing_analysis() -> None:
    pool = _pool(("ENT_A", "ENT_B"))

    with pytest.raises(MainCoreError, match="missing analysis"):
        generate_recommendations(pool, [_analysis("ENT_A", 0.5)], _world_state())


def test_generate_recommendations_rejects_duplicate_analysis() -> None:
    pool = _pool(("ENT_A",))

    with pytest.raises(MainCoreError, match="duplicate analysis"):
        generate_recommendations(
            pool,
            [_analysis("ENT_A", 0.5), _analysis("ENT_A", 0.6)],
            _world_state(),
        )


@pytest.mark.parametrize(
    "kwargs",
    [
        {"pool": _pool(cycle_id="cycle_pool_other")},
        {"analyses": [_analysis("ENT_A", 0.5, cycle_id="cycle_analysis_other")]},
        {"overrides": [_override("ENT_A", "buy", cycle_id="cycle_override_other")]},
    ],
)
def test_generate_recommendations_rejects_cycle_mismatch(kwargs: dict[str, object]) -> None:
    pool = kwargs.get("pool", _pool(("ENT_A",)))
    analyses = kwargs.get("analyses", [_analysis("ENT_A", 0.5)])
    overrides = kwargs.get("overrides", [])

    with pytest.raises(MainCoreError, match="cycle_id"):
        generate_recommendations(
            pool,
            analyses,
            _world_state(),
            overrides=overrides,
        )


def test_generate_recommendations_applies_override_before_risk_off_gate() -> None:
    pool = _pool(("ENT_A",))

    [recommendation] = generate_recommendations(
        pool,
        [_analysis("ENT_A", 0.5)],
        _world_state("risk_off"),
        overrides=[_override("ENT_A", "buy")],
    )

    assert recommendation.action_type == "hold"
    assert recommendation.triggered_by == "human_decision"
    assert recommendation.override_applied is True
    assert recommendation.constraints_applied["regime_gate"] == "risk_off_buy_to_hold"


def test_submit_override_default_store_feeds_recommendation_generation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    default_store = InMemoryOverrideStore(
        [_override("ENT_Z", "reduce", cycle_id="cycle_other")],
    )
    monkeypatch.setattr(
        "main_core.l7_recommendation.override._DEFAULT_OVERRIDE_STORE",
        default_store,
    )
    pool = _pool(("ENT_A",))

    submit_override(_override("ENT_A", "buy"))
    [recommendation] = generate_recommendations(
        pool,
        [_analysis("ENT_A", 0.5)],
        _world_state("risk_off"),
    )

    assert recommendation.action_type == "hold"
    assert recommendation.triggered_by == "human_decision"
    assert recommendation.override_applied is True
    assert recommendation.constraints_applied["regime_gate"] == "risk_off_buy_to_hold"


def test_submit_override_default_store_latest_matching_submission_wins(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    default_store = InMemoryOverrideStore()
    monkeypatch.setattr(
        "main_core.l7_recommendation.override._DEFAULT_OVERRIDE_STORE",
        default_store,
    )
    pool = _pool(("ENT_A",))

    submit_override(
        _override(
            "ENT_A",
            "buy",
            submitted_at=datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC),
        ),
    )
    submit_override(
        _override(
            "ENT_A",
            "reduce",
            submitted_at=datetime(2026, 1, 2, 3, 4, 6, tzinfo=UTC),
        ),
    )
    [recommendation] = generate_recommendations(
        pool,
        [_analysis("ENT_A", 0.5)],
        _world_state("risk_off"),
    )

    assert recommendation.action_type == "reduce"
    assert recommendation.rating == "C"
    assert recommendation.triggered_by == "human_decision"
    assert recommendation.override_applied is True
    assert "regime_gate" not in recommendation.constraints_applied


def test_generate_recommendations_honors_explicit_falsey_override_store(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FalseyOverrideStore(InMemoryOverrideStore):
        def __len__(self) -> int:
            return 0

    default_store = InMemoryOverrideStore([_override("ENT_A", "buy")])
    monkeypatch.setattr(
        "main_core.l7_recommendation.override._DEFAULT_OVERRIDE_STORE",
        default_store,
    )
    pool = _pool(("ENT_A",))

    [recommendation] = generate_recommendations(
        pool,
        [_analysis("ENT_A", 0.5)],
        _world_state(),
        override_store=FalseyOverrideStore(),
    )

    assert recommendation.action_type == "hold"
    assert recommendation.triggered_by == "system"
    assert recommendation.override_applied is False


def test_generate_recommendations_force_inconclusive_passes_schema_validation() -> None:
    pool = _pool(("ENT_A",))

    [recommendation] = generate_recommendations(
        pool,
        [_analysis("ENT_A", 0.8)],
        _world_state(),
        risk_context={"force_inconclusive": True},
    )

    assert recommendation.action_type == "inconclusive"
    assert recommendation.rating is None
    assert recommendation.confidence is None
    assert RecommendationSnapshot.model_validate(recommendation.model_dump()) == recommendation


def test_generate_recommendations_preserves_override_audit_after_custom_gate() -> None:
    class AuditingBrokenGate:
        def gate(
            self,
            inputs: RecommendationConstraintInputs,
            candidate: RecommendationSnapshot,
        ) -> RecommendationSnapshot:
            return candidate.model_copy(
                update={
                    "action_type": "reduce",
                    "rating": "C",
                    "triggered_by": "system",
                    "override_applied": False,
                },
            )

    pool = _pool(("ENT_A",))

    [recommendation] = generate_recommendations(
        pool,
        [_analysis("ENT_A", 0.8)],
        _world_state(),
        constraint_provider=AuditingBrokenGate(),
        overrides=[_override("ENT_A", "buy")],
    )

    assert recommendation.action_type == "reduce"
    assert recommendation.triggered_by == "human_decision"
    assert recommendation.override_applied is True


@pytest.mark.parametrize(
    ("field_name", "field_value"),
    [
        ("cycle_id", "cycle_gate_other"),
        ("entity_id", "ENT_GATE_OTHER"),
    ],
)
def test_generate_recommendations_rejects_constraint_gate_identity_drift(
    field_name: str,
    field_value: str,
) -> None:
    class DriftingGate:
        def gate(
            self,
            inputs: RecommendationConstraintInputs,
            candidate: RecommendationSnapshot,
        ) -> RecommendationSnapshot:
            return candidate.model_copy(update={field_name: field_value})

    pool = _pool(("ENT_A",))

    with pytest.raises(MainCoreError, match=field_name):
        generate_recommendations(
            pool,
            [_analysis("ENT_A", 0.8)],
            _world_state(),
            constraint_provider=DriftingGate(),
        )


def test_generate_recommendations_has_no_previous_recommendation_parameter() -> None:
    parameter_names = set(signature(generate_recommendations).parameters)

    assert "previous_recommendation" not in parameter_names
    assert "last_recommendation" not in parameter_names
