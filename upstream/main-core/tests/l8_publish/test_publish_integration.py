"""Minimal P2 L1-L8 style publication integration tests."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from main_core.common.contexts import AlphaAnalysisContext
from main_core.common.errors import ManifestPublishError
from main_core.common.schemas import FeatureSignalBundle
from main_core.l4_world_state import derive_world_state
from main_core.l5_universe import select_official_alpha_pool
from main_core.l6_alpha import (
    AlphaReasonerResponse,
    SinglePromptAnalyzer,
    StaticAlphaReasonerPort,
    analyze_stock,
)
from main_core.l7_recommendation import (
    InMemoryOverrideStore,
    generate_recommendations,
    submit_override,
)
from main_core.l8_publish import prepare_publish_bundle
from main_core.l8_publish.refs import RECOMMENDATION_SNAPSHOT_KEY
from tests.l8_publish import (
    FakeFormalObjectSource,
    RecordingPublishPort,
    alpha_result,
    pool,
    recommendation,
)


class SourceWithPreviousRecommendationTrap(FakeFormalObjectSource):
    def load_previous_recommendations(self, cycle_id: str) -> None:
        raise AssertionError(f"L8 must not read previous recommendations for {cycle_id}")


def test_publish_consumes_current_l7_output_without_previous_recommendations() -> None:
    cycle_id = "cycle_l8_integration"
    bundles = [
        _feature_bundle(cycle_id, "ENT_A", 6.0),
        _feature_bundle(cycle_id, "ENT_B", 4.0),
    ]
    world_state = derive_world_state(bundles[0])
    pool = select_official_alpha_pool(world_state, bundles, capacity=2)

    alpha_results = [
        analyze_stock(
            "ENT_A",
            _analysis_context(cycle_id, "ENT_A", bundles, world_state),
            analyzer=SinglePromptAnalyzer(
                StaticAlphaReasonerPort(
                    AlphaReasonerResponse(
                        score=0.74,
                        confidence=0.82,
                        rationale="current-cycle alpha",
                        similar_cases=[],
                    )
                )
            ),
        ),
        analyze_stock(
            "ENT_B",
            _analysis_context(cycle_id, "ENT_B", bundles, world_state),
            analyzer=SinglePromptAnalyzer(
                StaticAlphaReasonerPort(
                    AlphaReasonerResponse(
                        score=None,
                        confidence=0.0,
                        rationale="provider timeout",
                        similar_cases=[],
                        task_failed=True,
                        failure_reason="task-level timeout",
                    )
                )
            ),
        ),
    ]

    override_store = InMemoryOverrideStore()
    submit_override(
        {
            "cycle_id": cycle_id,
            "entity_id": "ENT_A",
            "submitted_by": "analyst",
            "action_type": "reduce",
            "rationale": "current-cycle risk review",
            "submitted_at": datetime(2026, 4, 17, 9, 30, tzinfo=UTC),
        },
        store=override_store,
    )
    recommendations = generate_recommendations(
        pool,
        alpha_results,
        world_state,
        override_store=override_store,
    )
    source = SourceWithPreviousRecommendationTrap(
        loaded_world_state=world_state,
        loaded_pool=pool,
        loaded_alpha_results=alpha_results,
        loaded_recommendations=recommendations,
    )

    bundle = prepare_publish_bundle(
        cycle_id,
        source=source,
        publish_port=RecordingPublishPort(),
    )

    bundle_payload = bundle.model_dump(mode="json")
    recommendation_payload = bundle_payload["formal_objects"][
        RECOMMENDATION_SNAPSHOT_KEY
    ]["payload"]
    assert recommendation_payload == [
        recommendation.model_dump(mode="json")
        for recommendation in recommendations
    ]
    assert recommendation_payload[0]["override_applied"] is True
    assert recommendation_payload[0]["action_type"] == "reduce"
    assert recommendation_payload[1]["action_type"] == "inconclusive"
    assert bundle_payload["audit_payload"]["override_applied_count"] == 1
    assert bundle_payload["audit_payload"]["inconclusive_count"] == 1

    serialized_bundle = json.dumps(bundle_payload, sort_keys=True)
    assert "previous_recommendation" not in serialized_bundle
    assert "last_recommendation" not in serialized_bundle
    assert "fallback_recommendation_ref" not in serialized_bundle


def test_publish_rejects_alpha_results_outside_official_pool_before_commit() -> None:
    source = FakeFormalObjectSource(
        loaded_pool=pool(("ENT_A", "ENT_B")),
        loaded_alpha_results=[
            alpha_result("ENT_A"),
            alpha_result("ENT_B"),
            alpha_result("ENT_Z"),
        ],
        loaded_recommendations=[
            recommendation("ENT_A"),
            recommendation("ENT_B", action_type="hold"),
        ],
    )
    publish_port = RecordingPublishPort()

    with pytest.raises(ManifestPublishError, match="alpha result entity_id"):
        prepare_publish_bundle(
            "cycle_l8",
            source=source,
            publish_port=publish_port,
        )

    assert publish_port.commit_calls == []
    assert publish_port.manifest_calls == []


def _feature_bundle(
    cycle_id: str,
    entity_id: str,
    momentum: float,
) -> FeatureSignalBundle:
    return FeatureSignalBundle(
        cycle_id=cycle_id,
        entity_id=entity_id,
        feature_values={"momentum": momentum},
        signal_values={},
        graph_features={},
        feature_weight_multiplier={"momentum": 1.0},
    )


def _analysis_context(
    cycle_id: str,
    entity_id: str,
    bundles: list[FeatureSignalBundle],
    world_state: object,
) -> AlphaAnalysisContext:
    bundle_by_entity = {
        str(bundle.entity_id): bundle
        for bundle in bundles
    }
    return AlphaAnalysisContext(
        cycle_id=cycle_id,
        entity_id=entity_id,
        feature_bundle=bundle_by_entity[entity_id],
        world_state=world_state,
        similar_cases=[],
    )
