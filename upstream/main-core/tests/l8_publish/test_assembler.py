"""Tests for L8 publish bundle assembly."""

from __future__ import annotations

import pytest

from main_core.common.errors import ManifestPublishError
from main_core.l8_publish import formal_object_ref, formal_object_refs, prepare_publish_bundle
from main_core.l8_publish.assembler import collect_formal_objects
from main_core.l8_publish.dashboard import DASHBOARD_SNAPSHOT_KEY
from main_core.l8_publish.refs import (
    ALPHA_RESULT_SNAPSHOT_KEY,
    CANONICAL_FORMAL_OBJECT_KEYS,
    OFFICIAL_ALPHA_POOL_KEY,
    RECOMMENDATION_SNAPSHOT_KEY,
    WORLD_STATE_SNAPSHOT_KEY,
)
from main_core.l8_publish.report import FORMAL_REPORT_KEY
from tests.l8_publish import (
    FakeFormalObjectSource,
    RecordingPublishPort,
    alpha_result,
    pool,
    recommendation,
    world_state,
)

SINGLE_OBJECT_COUNT = 1
ALPHA_RESULT_COUNT = 2


def test_collect_formal_objects_loads_source_in_layer_order() -> None:
    source = FakeFormalObjectSource()

    formal_objects = collect_formal_objects("cycle_l8", source)

    assert tuple(formal_objects) == CANONICAL_FORMAL_OBJECT_KEYS
    assert source.calls == [
        ("world_state", "cycle_l8"),
        ("pool", "cycle_l8"),
        ("alpha", "cycle_l8"),
        ("recommendation", "cycle_l8"),
    ]


def test_prepare_publish_bundle_returns_canonical_formal_object_entries() -> None:
    source = FakeFormalObjectSource()
    publish_port = RecordingPublishPort()

    bundle = prepare_publish_bundle(
        "cycle_l8",
        source=source,
        publish_port=publish_port,
    )

    bundle_payload = bundle.model_dump(mode="json")
    formal_objects = bundle_payload["formal_objects"]
    assert bundle.cycle_id == "cycle_l8"
    assert tuple(formal_objects) == (
        *CANONICAL_FORMAL_OBJECT_KEYS,
        DASHBOARD_SNAPSHOT_KEY,
        FORMAL_REPORT_KEY,
    )
    assert set(formal_objects[WORLD_STATE_SNAPSHOT_KEY]) == {
        "count",
        "payload",
        "ref",
    }
    assert formal_objects[WORLD_STATE_SNAPSHOT_KEY]["payload"] == (
        source.world_state.model_dump(mode="json")
    )
    assert formal_objects[ALPHA_RESULT_SNAPSHOT_KEY]["payload"] == [
        alpha.model_dump(mode="json")
        for alpha in source.alpha_results
    ]
    assert formal_objects[OFFICIAL_ALPHA_POOL_KEY]["count"] == SINGLE_OBJECT_COUNT
    assert formal_objects[ALPHA_RESULT_SNAPSHOT_KEY]["count"] == ALPHA_RESULT_COUNT
    assert formal_object_ref(bundle, WORLD_STATE_SNAPSHOT_KEY) == (
        "world_state_snapshot/cycle_l8/ref"
    )
    assert formal_object_refs(bundle, RECOMMENDATION_SNAPSHOT_KEY) == (
        "recommendation_snapshot/cycle_l8/ref",
    )
    assert bundle_payload["manifest_candidate"]["manifest_ref"] == "manifest/cycle_l8"
    assert bundle_payload["audit_payload"]["object_counts"] == {
        WORLD_STATE_SNAPSHOT_KEY: SINGLE_OBJECT_COUNT,
        OFFICIAL_ALPHA_POOL_KEY: SINGLE_OBJECT_COUNT,
        ALPHA_RESULT_SNAPSHOT_KEY: ALPHA_RESULT_COUNT,
        RECOMMENDATION_SNAPSHOT_KEY: ALPHA_RESULT_COUNT,
        DASHBOARD_SNAPSHOT_KEY: SINGLE_OBJECT_COUNT,
        FORMAL_REPORT_KEY: SINGLE_OBJECT_COUNT,
    }
    assert bundle_payload["audit_payload"]["inconclusive_count"] == SINGLE_OBJECT_COUNT
    assert (
        bundle_payload["audit_payload"]["alpha_inconclusive_count"]
        == SINGLE_OBJECT_COUNT
    )
    assert (
        bundle_payload["audit_payload"]["recommendation_inconclusive_count"]
        == SINGLE_OBJECT_COUNT
    )
    assert bundle_payload["audit_payload"]["override_applied_count"] == SINGLE_OBJECT_COUNT
    assert bundle_payload["retrospective_seed"]["selected_entity_ids"] == [
        "ENT_A",
        "ENT_B",
    ]
    assert bundle_payload["retrospective_seed"]["recommendation_entity_ids"] == [
        "ENT_A",
        "ENT_B",
    ]
    assert formal_objects[DASHBOARD_SNAPSHOT_KEY]["payload"]["world_state_ref"] == (
        "world_state_snapshot/cycle_l8/ref"
    )
    assert formal_objects[FORMAL_REPORT_KEY]["payload"]["recommendation_ref"] == (
        formal_objects[DASHBOARD_SNAPSHOT_KEY]["payload"]["recommendation_ref"]
    )
    assert bundle_payload["manifest_candidate"]["table_snapshots"][
        DASHBOARD_SNAPSHOT_KEY
    ] == "dashboard_snapshot-snapshot"
    assert bundle_payload["manifest_candidate"]["table_snapshots"][
        FORMAL_REPORT_KEY
    ] == "report-snapshot"


@pytest.mark.parametrize(
    "source",
    [
        FakeFormalObjectSource(loaded_world_state=world_state("cycle_other")),
        FakeFormalObjectSource(loaded_pool=pool(cycle_id="cycle_other")),
        FakeFormalObjectSource(
            loaded_alpha_results=[alpha_result("ENT_A", cycle_id="cycle_other")],
        ),
        FakeFormalObjectSource(
            loaded_recommendations=[recommendation("ENT_A", cycle_id="cycle_other")],
        ),
    ],
)
def test_prepare_publish_bundle_rejects_cycle_mismatch_before_commit(
    source: FakeFormalObjectSource,
) -> None:
    publish_port = RecordingPublishPort()

    with pytest.raises(ManifestPublishError, match="cycle_id"):
        prepare_publish_bundle(
            "cycle_l8",
            source=source,
            publish_port=publish_port,
        )

    assert publish_port.commit_calls == []
    assert publish_port.manifest_calls == []


def test_prepare_publish_bundle_rejects_missing_alpha_for_selected_pool_entity() -> None:
    source = FakeFormalObjectSource(
        loaded_pool=pool(("ENT_A", "ENT_B")),
        loaded_alpha_results=[alpha_result("ENT_A")],
        loaded_recommendations=[recommendation("ENT_A")],
    )
    publish_port = RecordingPublishPort()

    with pytest.raises(ManifestPublishError, match="missing alpha result"):
        prepare_publish_bundle(
            "cycle_l8",
            source=source,
            publish_port=publish_port,
        )

    assert publish_port.commit_calls == []
    assert publish_port.manifest_calls == []


def test_prepare_publish_bundle_rejects_recommendation_outside_pool() -> None:
    source = FakeFormalObjectSource(
        loaded_pool=pool(("ENT_A",)),
        loaded_alpha_results=[alpha_result("ENT_A")],
        loaded_recommendations=[recommendation("ENT_Z")],
    )
    publish_port = RecordingPublishPort()

    with pytest.raises(ManifestPublishError, match="pool.selected_entities"):
        prepare_publish_bundle(
            "cycle_l8",
            source=source,
            publish_port=publish_port,
        )

    assert publish_port.commit_calls == []
    assert publish_port.manifest_calls == []


def test_prepare_publish_bundle_rejects_missing_recommendation_for_pool_entity() -> None:
    source = FakeFormalObjectSource(
        loaded_pool=pool(("ENT_A", "ENT_B")),
        loaded_alpha_results=[alpha_result("ENT_A"), alpha_result("ENT_B")],
        loaded_recommendations=[recommendation("ENT_A")],
    )
    publish_port = RecordingPublishPort()

    with pytest.raises(ManifestPublishError, match="missing recommendation"):
        prepare_publish_bundle(
            "cycle_l8",
            source=source,
            publish_port=publish_port,
        )

    assert publish_port.commit_calls == []
    assert publish_port.manifest_calls == []


def test_prepare_publish_bundle_rejects_duplicate_recommendation_entity() -> None:
    source = FakeFormalObjectSource(
        loaded_pool=pool(("ENT_A", "ENT_B")),
        loaded_alpha_results=[alpha_result("ENT_A"), alpha_result("ENT_B")],
        loaded_recommendations=[
            recommendation("ENT_A"),
            recommendation("ENT_A", action_type="hold"),
        ],
    )
    publish_port = RecordingPublishPort()

    with pytest.raises(ManifestPublishError, match="duplicate recommendation_snapshot"):
        prepare_publish_bundle(
            "cycle_l8",
            source=source,
            publish_port=publish_port,
        )

    assert publish_port.commit_calls == []
    assert publish_port.manifest_calls == []


def test_formal_object_ref_rejects_missing_entry() -> None:
    bundle = prepare_publish_bundle(
        "cycle_l8",
        source=FakeFormalObjectSource(),
        publish_port=RecordingPublishPort(),
    )

    with pytest.raises(ManifestPublishError, match="missing formal object"):
        formal_object_ref(bundle, "backtest_result")
