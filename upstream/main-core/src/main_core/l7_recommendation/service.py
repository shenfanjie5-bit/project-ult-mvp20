"""Service entrypoint for formal L7 recommendation generation."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

from main_core.common.contexts import RecommendationConstraintInputs
from main_core.common.errors import MainCoreError
from main_core.common.protocols import RecommendationConstraintProvider
from main_core.common.schemas import (
    AlphaResultSnapshot,
    OfficialAlphaPool,
    OverrideRecord,
    RecommendationSnapshot,
    WorldStateSnapshot,
)
from main_core.l7_recommendation import override as override_module
from main_core.l7_recommendation.constraints import DefaultConstraintProvider
from main_core.l7_recommendation.override import (
    OverrideStore,
    apply_override,
    find_override,
)

BUY_SCORE_THRESHOLD = 0.65
REDUCE_SCORE_THRESHOLD = 0.35


def generate_recommendations(  # noqa: PLR0913
    pool: OfficialAlphaPool,
    analyses: Sequence[AlphaResultSnapshot],
    world_state: WorldStateSnapshot,
    *,
    constraint_provider: RecommendationConstraintProvider | None = None,
    overrides: Sequence[OverrideRecord] | None = None,
    override_store: OverrideStore | None = None,
    risk_context: Mapping[str, Any] | None = None,
) -> list[RecommendationSnapshot]:
    """Generate one formal recommendation per selected pool entity."""

    active_overrides = _resolve_overrides(pool, overrides, override_store)
    analysis_by_entity = _validate_inputs(pool, analyses, world_state, active_overrides)
    active_provider = constraint_provider or DefaultConstraintProvider()
    constraint_inputs = RecommendationConstraintInputs(
        world_state=world_state,
        risk_context=dict(risk_context or {}),
    )

    recommendations: list[RecommendationSnapshot] = []
    for entity_id in pool.selected_entities:
        candidate = _candidate_from_analysis(analysis_by_entity[str(entity_id)])
        source_is_inconclusive = candidate.action_type == "inconclusive"
        matching_override = find_override(active_overrides, pool.cycle_id, entity_id)
        override_was_applied = matching_override is not None
        if matching_override is not None:
            candidate = apply_override(candidate, matching_override)
        if source_is_inconclusive:
            candidate = _force_inconclusive(candidate)

        gated_candidate = active_provider.gate(constraint_inputs, candidate)
        _validate_gated_identity(gated_candidate, pool.cycle_id, entity_id)
        if source_is_inconclusive:
            gated_candidate = _force_inconclusive(gated_candidate)
        if override_was_applied and (
            not gated_candidate.override_applied
            or gated_candidate.triggered_by != "human_decision"
        ):
            gated_candidate = gated_candidate.model_copy(
                update={
                    "triggered_by": "human_decision",
                    "override_applied": True,
                },
            )
        recommendations.append(gated_candidate)

    return recommendations


def _resolve_overrides(
    pool: OfficialAlphaPool,
    overrides: Sequence[OverrideRecord] | None,
    override_store: OverrideStore | None,
) -> tuple[OverrideRecord, ...]:
    if overrides is not None:
        return _latest_overrides_by_cycle_entity(overrides)

    active_store = (
        override_store if override_store is not None else _default_override_store()
    )
    return _latest_overrides_by_cycle_entity(
        tuple(
            override
            for override in active_store.list_overrides()
            if override.cycle_id == pool.cycle_id
        ),
    )


def _latest_overrides_by_cycle_entity(
    overrides: Sequence[OverrideRecord],
) -> tuple[OverrideRecord, ...]:
    latest_by_key: dict[tuple[str, str], OverrideRecord] = {}
    for override in overrides:
        latest_by_key[(str(override.cycle_id), str(override.entity_id))] = override
    return tuple(latest_by_key.values())


def _default_override_store() -> OverrideStore:
    return override_module._DEFAULT_OVERRIDE_STORE


def _validate_inputs(
    pool: OfficialAlphaPool,
    analyses: Sequence[AlphaResultSnapshot],
    world_state: WorldStateSnapshot,
    overrides: Sequence[OverrideRecord],
) -> dict[str, AlphaResultSnapshot]:
    if pool.cycle_id != world_state.cycle_id:
        raise MainCoreError("pool.cycle_id must match world_state.cycle_id")

    selected_entity_ids = {str(entity_id) for entity_id in pool.selected_entities}
    analysis_by_entity: dict[str, AlphaResultSnapshot] = {}
    for analysis in analyses:
        if analysis.cycle_id != pool.cycle_id:
            raise MainCoreError("analysis cycle_id must match pool.cycle_id")

        entity_id = str(analysis.entity_id)
        if entity_id not in selected_entity_ids:
            raise MainCoreError("analysis entity_id must belong to pool.selected_entities")
        if entity_id in analysis_by_entity:
            raise MainCoreError("duplicate analysis for selected entity")
        analysis_by_entity[entity_id] = analysis

    missing_entity_ids = selected_entity_ids - set(analysis_by_entity)
    if missing_entity_ids:
        raise MainCoreError("missing analysis for selected entity")

    for override in overrides:
        if override.cycle_id != pool.cycle_id:
            raise MainCoreError("override cycle_id must match pool.cycle_id")

    return analysis_by_entity


def _candidate_from_analysis(analysis: AlphaResultSnapshot) -> RecommendationSnapshot:
    if analysis.status == "inconclusive":
        return RecommendationSnapshot(
            cycle_id=analysis.cycle_id,
            entity_id=analysis.entity_id,
            action_type="inconclusive",
            rating=None,
            confidence=None,
            triggered_by="system",
            override_applied=False,
            constraints_applied={},
        )

    if analysis.score is None:
        raise MainCoreError("ok analysis score must not be None")
    if not math.isfinite(analysis.score):
        raise MainCoreError("ok analysis score must be finite")
    if not math.isfinite(analysis.confidence):
        raise MainCoreError("ok analysis confidence must be finite")

    action_type = _action_for_score(analysis.score)
    return RecommendationSnapshot(
        cycle_id=analysis.cycle_id,
        entity_id=analysis.entity_id,
        action_type=action_type,
        rating=_rating_for_action(action_type),
        confidence=analysis.confidence,
        triggered_by="system",
        override_applied=False,
        constraints_applied={},
    )


def _force_inconclusive(candidate: RecommendationSnapshot) -> RecommendationSnapshot:
    if (
        candidate.action_type == "inconclusive"
        and candidate.rating is None
        and candidate.confidence is None
    ):
        return candidate
    return candidate.model_copy(
        update={
            "action_type": "inconclusive",
            "rating": None,
            "confidence": None,
        },
    )


def _validate_gated_identity(
    candidate: RecommendationSnapshot,
    cycle_id: str,
    entity_id: str,
) -> None:
    if candidate.cycle_id != cycle_id:
        raise MainCoreError("constraint gate must preserve recommendation cycle_id")
    if candidate.entity_id != entity_id:
        raise MainCoreError("constraint gate must preserve recommendation entity_id")


def _action_for_score(score: float) -> str:
    if score >= BUY_SCORE_THRESHOLD:
        return "buy"
    if score <= REDUCE_SCORE_THRESHOLD:
        return "reduce"
    return "hold"


def _rating_for_action(action_type: str) -> str:
    ratings = {
        "buy": "A",
        "hold": "B",
        "reduce": "C",
    }
    return ratings[action_type]


__all__ = [
    "BUY_SCORE_THRESHOLD",
    "REDUCE_SCORE_THRESHOLD",
    "generate_recommendations",
]
