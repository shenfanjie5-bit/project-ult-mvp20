"""Integration coverage for dashboard/report publication."""

from __future__ import annotations

from collections.abc import Sequence

import pytest

from main_core.common.errors import ManifestPublishError
from main_core.common.types import CycleId
from main_core.l8_publish import prepare_publish_bundle
from main_core.l8_publish.dashboard import DASHBOARD_SNAPSHOT_KEY
from main_core.l8_publish.publish_port import (
    CommittedFormalObject,
    ManifestWriteResult,
)
from main_core.l8_publish.refs import (
    ALPHA_RESULT_SNAPSHOT_KEY,
    OFFICIAL_ALPHA_POOL_KEY,
    RECOMMENDATION_SNAPSHOT_KEY,
    WORLD_STATE_SNAPSHOT_KEY,
)
from main_core.l8_publish.report import FORMAL_REPORT_KEY
from tests.l8_publish import FakeFormalObjectSource, RecordingPublishPort


def test_prepare_publish_bundle_commits_dashboard_and_report_before_manifest() -> None:
    publish_port = RecordingPublishPort()

    bundle = prepare_publish_bundle(
        "cycle_l8",
        source=FakeFormalObjectSource(),
        publish_port=publish_port,
    )
    payload = bundle.model_dump(mode="json")

    assert tuple(payload["formal_objects"]) == (
        WORLD_STATE_SNAPSHOT_KEY,
        OFFICIAL_ALPHA_POOL_KEY,
        ALPHA_RESULT_SNAPSHOT_KEY,
        RECOMMENDATION_SNAPSHOT_KEY,
        DASHBOARD_SNAPSHOT_KEY,
        FORMAL_REPORT_KEY,
    )
    assert [call[1] for call in publish_port.commit_calls] == [
        WORLD_STATE_SNAPSHOT_KEY,
        OFFICIAL_ALPHA_POOL_KEY,
        ALPHA_RESULT_SNAPSHOT_KEY,
        RECOMMENDATION_SNAPSHOT_KEY,
        DASHBOARD_SNAPSHOT_KEY,
        FORMAL_REPORT_KEY,
    ]
    assert len(publish_port.manifest_calls) == 1
    assert set(payload["manifest_candidate"]["table_snapshots"]) == {
        WORLD_STATE_SNAPSHOT_KEY,
        OFFICIAL_ALPHA_POOL_KEY,
        ALPHA_RESULT_SNAPSHOT_KEY,
        RECOMMENDATION_SNAPSHOT_KEY,
        DASHBOARD_SNAPSHOT_KEY,
        FORMAL_REPORT_KEY,
    }

    dashboard = payload["formal_objects"][DASHBOARD_SNAPSHOT_KEY]["payload"]
    report = payload["formal_objects"][FORMAL_REPORT_KEY]["payload"]
    assert dashboard["world_state_ref"] == payload["formal_objects"][
        WORLD_STATE_SNAPSHOT_KEY
    ]["ref"]
    assert dashboard["pool_ref"] == payload["formal_objects"][OFFICIAL_ALPHA_POOL_KEY][
        "ref"
    ]
    assert dashboard["recommendation_ref"] == payload["formal_objects"][
        RECOMMENDATION_SNAPSHOT_KEY
    ]["ref"]
    assert report["recommendation_ref"] == dashboard["recommendation_ref"]
    assert dashboard["summary_cards"]["recommendations"][
        "override_applied_count"
    ] == 1
    assert dashboard["summary_cards"]["recommendations"]["by_action"][
        "inconclusive"
    ] == 1
    assert report["narrative_sections"]["inconclusive_summary"][
        "recommendation_inconclusive_count"
    ] == 1
    assert report["narrative_sections"]["override_summary"][
        "override_applied_count"
    ] == 1


def test_formal_report_uses_reserved_manifest_ref_in_committed_payload() -> None:
    manifest_ref = "pg://cycle_publish_manifest/cycle_l8/v42"
    publish_port = RecordingPublishPort(manifest_ref=manifest_ref)

    bundle = prepare_publish_bundle(
        "cycle_l8",
        source=FakeFormalObjectSource(),
        publish_port=publish_port,
    )
    payload = bundle.model_dump(mode="json")
    report_commit_payload = next(
        commit_payload
        for _, object_key, commit_payload in publish_port.commit_calls
        if object_key == FORMAL_REPORT_KEY
    )

    assert publish_port.reserve_manifest_ref_calls == ["cycle_l8"]
    assert payload["manifest_candidate"]["manifest_ref"] == manifest_ref
    assert payload["formal_objects"][FORMAL_REPORT_KEY]["payload"]["appendix_refs"][
        "manifest_ref"
    ] == manifest_ref
    assert report_commit_payload["appendix_refs"]["manifest_ref"] == manifest_ref


def test_manifest_ref_mismatch_fails_before_visible_manifest_write() -> None:
    publish_port = MismatchedManifestRefPublishPort(
        reserved_manifest_ref="manifest/cycle_l8/reserved",
        actual_manifest_ref="pg://cycle_publish_manifest/cycle_l8/v43",
    )

    with pytest.raises(ManifestPublishError, match="reserved manifest_ref"):
        prepare_publish_bundle(
            "cycle_l8",
            source=FakeFormalObjectSource(),
            publish_port=publish_port,
        )

    report_commit_payload = next(
        commit_payload
        for _, object_key, commit_payload in publish_port.commit_calls
        if object_key == FORMAL_REPORT_KEY
    )
    assert publish_port.reserve_manifest_ref_calls == ["cycle_l8"]
    assert publish_port.manifest_calls == []
    assert report_commit_payload["appendix_refs"]["manifest_ref"] == (
        "manifest/cycle_l8/reserved"
    )
    assert report_commit_payload["appendix_refs"]["manifest_ref"] != (
        "pg://cycle_publish_manifest/cycle_l8/v43"
    )


class MismatchedManifestRefPublishPort(RecordingPublishPort):
    def __init__(
        self,
        *,
        reserved_manifest_ref: str,
        actual_manifest_ref: str,
    ) -> None:
        super().__init__(manifest_ref=reserved_manifest_ref)
        self.actual_manifest_ref = actual_manifest_ref

    def write_cycle_manifest(
        self,
        *,
        cycle_id: CycleId,
        committed_objects: Sequence[CommittedFormalObject],
        expected_manifest_ref: str | None = None,
    ) -> ManifestWriteResult:
        committed_tuple = tuple(committed_objects)
        if expected_manifest_ref != self.actual_manifest_ref:
            raise ManifestPublishError(
                "reserved manifest_ref does not match publish target",
            )
        self.manifest_calls.append((cycle_id, committed_tuple))
        return ManifestWriteResult(
            manifest_ref=self.actual_manifest_ref,
            manifest_version="v1",
            table_snapshots={
                committed.object_key: committed.snapshot_id
                for committed in committed_tuple
            },
        )
