"""Tests for the L7 recommendation constraint provider protocol contract."""

from __future__ import annotations

from typing import get_type_hints

from main_core.common.contexts import RecommendationConstraintInputs
from main_core.common.protocols import (
    RecommendationConstraintProvider,
    RecommendationConstraintProviderBase,
)
from main_core.common.schemas import RecommendationSnapshot, WorldStateSnapshot
from main_core.l7_recommendation import DefaultConstraintProvider

CYCLE_ID = "cycle_001"
ENTITY_ID = "ENT_001"


def _world_state() -> WorldStateSnapshot:
    return WorldStateSnapshot(
        cycle_id=CYCLE_ID,
        baseline_regime="neutral",
        llm_delta=0,
        final_regime="neutral",
        llm_rationale="stub",
        actual_model_used="none",
        actual_provider="none",
        fallback_path=[],
    )


def _constraint_inputs() -> RecommendationConstraintInputs:
    return RecommendationConstraintInputs(
        world_state=_world_state(),
        risk_context={"gross_exposure": 0.0},
    )


def _candidate() -> RecommendationSnapshot:
    return RecommendationSnapshot(
        cycle_id=CYCLE_ID,
        entity_id=ENTITY_ID,
        action_type="hold",
        rating="neutral",
        confidence=0.5,
        triggered_by="system",
        override_applied=False,
        constraints_applied={},
    )


def test_constraint_provider_protocol_imports() -> None:
    assert RecommendationConstraintProvider is not None
    assert RecommendationConstraintProviderBase is not None


def test_default_constraint_provider_matches_runtime_protocol() -> None:
    provider = DefaultConstraintProvider()

    assert isinstance(provider, RecommendationConstraintProvider)


def test_default_constraint_provider_returns_neutral_candidate_unchanged() -> None:
    provider = DefaultConstraintProvider()
    candidate = _candidate()

    gated_candidate = provider.gate(_constraint_inputs(), candidate)

    assert gated_candidate is candidate


def test_gate_signature_uses_pydantic_models() -> None:
    annotations = get_type_hints(RecommendationConstraintProvider.gate)

    assert annotations["inputs"] is RecommendationConstraintInputs
    assert annotations["candidate"] is RecommendationSnapshot
    assert annotations["return"] is RecommendationSnapshot
