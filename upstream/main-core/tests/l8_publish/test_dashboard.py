"""Tests for L8 dashboard snapshot builders."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

from main_core.common.errors import ManifestPublishError
from main_core.common.schemas import PublishBundle
from main_core.l8_publish import build_dashboard_snapshot, prepare_publish_bundle
from main_core.l8_publish.refs import WORLD_STATE_SNAPSHOT_KEY
from tests.l8_publish import FakeFormalObjectSource, RecordingPublishPort, pool


def test_build_dashboard_snapshot_happy_path() -> None:
    bundle = _base_bundle()

    dashboard = build_dashboard_snapshot("cycle_l8", bundle)

    assert dashboard.cycle_id == "cycle_l8"
    assert dashboard.world_state_ref == "world_state_snapshot/cycle_l8/ref"
    assert dashboard.pool_ref == "official_alpha_pool/cycle_l8/ref"
    assert dashboard.recommendation_ref == "recommendation_snapshot/cycle_l8/ref"
    assert dashboard.summary_cards["regime"]["final_regime"] == "neutral"
    assert dashboard.summary_cards["pool"] == {
        "selected_count": 2,
        "capacity": 100,
        "added_count": 2,
        "removed_count": 0,
        "observation_pool_size": 2,
        "frozen_count": 0,
    }
    assert dashboard.summary_cards["recommendations"]["by_action"] == {
        "buy": 1,
        "hold": 0,
        "reduce": 0,
        "inconclusive": 1,
    }


def test_build_dashboard_snapshot_rejects_missing_ref() -> None:
    bundle = _mutated_bundle(
        lambda payload: payload["formal_objects"][WORLD_STATE_SNAPSHOT_KEY].pop("ref")
    )

    with pytest.raises(ManifestPublishError, match="ref"):
        build_dashboard_snapshot("cycle_l8", bundle)


def test_build_dashboard_snapshot_rejects_cycle_mismatch() -> None:
    bundle = _mutated_bundle(
        lambda payload: payload["formal_objects"][WORLD_STATE_SNAPSHOT_KEY][
            "payload"
        ].__setitem__("cycle_id", "cycle_other")
    )

    with pytest.raises(ManifestPublishError, match="cycle_id"):
        build_dashboard_snapshot("cycle_l8", bundle)


def test_build_dashboard_snapshot_keeps_inconclusive_recommendations_visible() -> None:
    dashboard = build_dashboard_snapshot("cycle_l8", _base_bundle()).model_dump(
        mode="json"
    )

    assert dashboard["summary_cards"]["inconclusive"] == {
        "alpha_count": 1,
        "recommendation_count": 1,
        "alpha_entity_ids": ["ENT_B"],
        "recommendation_entity_ids": ["ENT_B"],
    }


def test_build_dashboard_snapshot_counts_override_applied_recommendations() -> None:
    dashboard = build_dashboard_snapshot("cycle_l8", _base_bundle()).model_dump(
        mode="json"
    )

    assert dashboard["summary_cards"]["recommendations"]["override_applied_count"] == 1
    assert dashboard["summary_cards"]["overrides"] == {
        "override_applied_count": 1,
        "entity_ids": ["ENT_A"],
    }


def test_build_dashboard_snapshot_allows_empty_recommendation_list() -> None:
    bundle = _base_bundle(
        FakeFormalObjectSource(
            loaded_pool=pool(()),
            loaded_alpha_results=[],
            loaded_recommendations=[],
        )
    )

    dashboard = build_dashboard_snapshot("cycle_l8", bundle)

    assert dashboard.summary_cards["pool"]["selected_count"] == 0
    assert dashboard.summary_cards["recommendations"] == {
        "total_count": 0,
        "by_action": {
            "buy": 0,
            "hold": 0,
            "reduce": 0,
            "inconclusive": 0,
        },
        "override_applied_count": 0,
    }


def test_build_dashboard_snapshot_rejects_stale_world_state_ref() -> None:
    bundle = _mutated_bundle(
        lambda payload: payload["formal_objects"][WORLD_STATE_SNAPSHOT_KEY].__setitem__(
            "ref",
            "world_state_snapshot/cycle_other/ref",
        )
    )

    with pytest.raises(ManifestPublishError, match="cycle_id"):
        build_dashboard_snapshot("cycle_l8", bundle)


@pytest.mark.parametrize(
    "ref",
    [
        "world_state_snapshot/cycle_other/cycle_l8/ref",
        "cycle_l8/world_state_snapshot/ref",
        "world_state_snapshot/ref/cycle_l8",
    ],
)
def test_build_dashboard_snapshot_rejects_misordered_world_state_ref(
    ref: str,
) -> None:
    bundle = _mutated_bundle(
        lambda payload: payload["formal_objects"][WORLD_STATE_SNAPSHOT_KEY].__setitem__(
            "ref",
            ref,
        )
    )

    with pytest.raises(ManifestPublishError, match="canonical"):
        build_dashboard_snapshot("cycle_l8", bundle)


def _base_bundle(source: FakeFormalObjectSource | None = None) -> PublishBundle:
    return prepare_publish_bundle(
        "cycle_l8",
        source=source or FakeFormalObjectSource(),
        publish_port=RecordingPublishPort(),
        derived_builders=(),
    )


def _mutated_bundle(mutator: Callable[[dict[str, Any]], None]) -> PublishBundle:
    payload = _base_bundle().model_dump(mode="python")
    mutator(payload)
    return PublishBundle(**payload)
