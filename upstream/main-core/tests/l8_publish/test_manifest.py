"""Tests for L8 formal object commits and manifest semantics."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import pytest

from main_core.common.errors import ManifestPublishError
from main_core.common.types import CycleId
from main_core.l8_publish import (
    CommittedFormalObject,
    ManifestWriteResult,
    prepare_publish_bundle,
)
from main_core.l8_publish.dashboard import DASHBOARD_SNAPSHOT_KEY
from main_core.l8_publish.manifest import (
    build_manifest_candidate,
    commit_formal_objects,
    write_manifest_after_commits,
)
from main_core.l8_publish.refs import (
    ALPHA_RESULT_SNAPSHOT_KEY,
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


def test_commit_formal_objects_uses_stable_publish_order() -> None:
    formal_objects = {
        RECOMMENDATION_SNAPSHOT_KEY: (recommendation("ENT_A"),),
        ALPHA_RESULT_SNAPSHOT_KEY: (alpha_result("ENT_A"),),
        WORLD_STATE_SNAPSHOT_KEY: world_state(),
        OFFICIAL_ALPHA_POOL_KEY: pool(("ENT_A",)),
    }
    publish_port = RecordingPublishPort()

    committed_objects = commit_formal_objects(
        "cycle_l8",
        formal_objects,
        publish_port,
    )
    manifest = write_manifest_after_commits(
        "cycle_l8",
        committed_objects,
        publish_port,
    )

    assert [call[1] for call in publish_port.commit_calls] == [
        WORLD_STATE_SNAPSHOT_KEY,
        OFFICIAL_ALPHA_POOL_KEY,
        ALPHA_RESULT_SNAPSHOT_KEY,
        RECOMMENDATION_SNAPSHOT_KEY,
    ]
    assert publish_port.manifest_calls == [("cycle_l8", committed_objects)]
    assert manifest.manifest_ref == "manifest/cycle_l8"


@pytest.mark.parametrize(
    ("override", "match"),
    [
        ({"ref": ""}, "ref must be non-empty"),
        ({"snapshot_id": ""}, "snapshot_id must be non-empty"),
        ({"payload_hash": ""}, "payload_hash must be non-empty"),
        ({"row_count": -1}, "row_count must be non-negative"),
        ({"row_count": 0}, "row_count mismatch"),
    ],
)
def test_commit_formal_objects_rejects_invalid_commit_result(
    override: Mapping[str, Any],
    match: str,
) -> None:
    publish_port = InvalidCommitResultPublishPort(override=override)

    with pytest.raises(ManifestPublishError, match=match):
        commit_formal_objects(
            "cycle_l8",
            {WORLD_STATE_SNAPSHOT_KEY: world_state()},
            publish_port,
        )


def test_build_manifest_candidate_includes_commit_and_manifest_refs() -> None:
    publish_port = RecordingPublishPort()
    committed_objects = commit_formal_objects(
        "cycle_l8",
        {WORLD_STATE_SNAPSHOT_KEY: world_state()},
        publish_port,
    )
    manifest = write_manifest_after_commits("cycle_l8", committed_objects, publish_port)

    candidate = build_manifest_candidate("cycle_l8", committed_objects, manifest)

    assert candidate["object_refs"] == {
        WORLD_STATE_SNAPSHOT_KEY: "world_state_snapshot/cycle_l8/ref",
    }
    assert candidate["manifest_ref"] == "manifest/cycle_l8"
    assert candidate["table_snapshots"] == {
        WORLD_STATE_SNAPSHOT_KEY: "world_state_snapshot-snapshot",
    }


@pytest.mark.parametrize(
    ("override", "match"),
    [
        ({"manifest_ref": ""}, "manifest_ref must be non-empty"),
        ({"manifest_version": ""}, "manifest_version must be non-empty"),
        ({"table_snapshots": []}, "table_snapshots must be a mapping"),
        ({"table_snapshots": {}}, "missing committed object keys"),
        (
            {"table_snapshots": {WORLD_STATE_SNAPSHOT_KEY: "stale-snapshot"}},
            "snapshot_id mismatch",
        ),
        (
            {
                "table_snapshots": {
                    WORLD_STATE_SNAPSHOT_KEY: "world_state_snapshot-snapshot",
                    "unrelated_snapshot": "unrelated-snapshot",
                },
            },
            "unexpected object keys",
        ),
        (
            {"table_snapshots": {WORLD_STATE_SNAPSHOT_KEY: ""}},
            "table_snapshots entry must be non-empty",
        ),
    ],
)
def test_write_manifest_after_commits_rejects_invalid_manifest_result(
    override: Mapping[str, Any],
    match: str,
) -> None:
    publish_port = RecordingPublishPort()
    committed_objects = commit_formal_objects(
        "cycle_l8",
        {WORLD_STATE_SNAPSHOT_KEY: world_state()},
        publish_port,
    )
    invalid_manifest_port = InvalidManifestResultPublishPort(override=override)

    with pytest.raises(ManifestPublishError, match=match):
        write_manifest_after_commits(
            "cycle_l8",
            committed_objects,
            invalid_manifest_port,
        )


def test_prepare_publish_bundle_does_not_write_manifest_after_commit_failure() -> None:
    publish_port = RecordingPublishPort(fail_on_object_key=ALPHA_RESULT_SNAPSHOT_KEY)

    with pytest.raises(ManifestPublishError, match="failed to commit"):
        prepare_publish_bundle(
            "cycle_l8",
            source=FakeFormalObjectSource(),
            publish_port=publish_port,
        )

    assert [call[1] for call in publish_port.commit_calls] == [
        WORLD_STATE_SNAPSHOT_KEY,
        OFFICIAL_ALPHA_POOL_KEY,
        ALPHA_RESULT_SNAPSHOT_KEY,
    ]
    assert publish_port.manifest_calls == []


def test_prepare_publish_bundle_raises_when_manifest_write_fails() -> None:
    publish_port = RecordingPublishPort(fail_manifest=True)

    with pytest.raises(ManifestPublishError, match="manifest"):
        prepare_publish_bundle(
            "cycle_l8",
            source=FakeFormalObjectSource(),
            publish_port=publish_port,
        )

    assert [call[1] for call in publish_port.commit_calls] == [
        WORLD_STATE_SNAPSHOT_KEY,
        OFFICIAL_ALPHA_POOL_KEY,
        ALPHA_RESULT_SNAPSHOT_KEY,
        RECOMMENDATION_SNAPSHOT_KEY,
        DASHBOARD_SNAPSHOT_KEY,
        FORMAL_REPORT_KEY,
    ]
    assert publish_port.manifest_calls == []


class InvalidCommitResultPublishPort(RecordingPublishPort):
    def __init__(self, *, override: Mapping[str, Any]) -> None:
        super().__init__()
        self.override = dict(override)

    def commit_formal_object(
        self,
        *,
        cycle_id: CycleId,
        object_key: str,
        payload: Mapping[str, Any],
    ) -> CommittedFormalObject:
        committed = super().commit_formal_object(
            cycle_id=cycle_id,
            object_key=object_key,
            payload=payload,
        )
        return CommittedFormalObject(
            object_key=self.override.get("object_key", committed.object_key),
            ref=self.override.get("ref", committed.ref),
            snapshot_id=self.override.get("snapshot_id", committed.snapshot_id),
            payload_hash=self.override.get("payload_hash", committed.payload_hash),
            row_count=self.override.get("row_count", committed.row_count),
        )


class InvalidManifestResultPublishPort(RecordingPublishPort):
    def __init__(self, *, override: Mapping[str, Any]) -> None:
        super().__init__()
        self.override = dict(override)

    def write_cycle_manifest(
        self,
        *,
        cycle_id: CycleId,
        committed_objects: Sequence[CommittedFormalObject],
        expected_manifest_ref: str | None = None,
    ) -> ManifestWriteResult:
        committed_tuple = tuple(committed_objects)
        self.manifest_calls.append((cycle_id, committed_tuple))
        table_snapshots = {
            committed.object_key: committed.snapshot_id
            for committed in committed_tuple
        }
        return ManifestWriteResult(
            manifest_ref=self.override.get("manifest_ref", f"manifest/{cycle_id}"),
            manifest_version=self.override.get("manifest_version", "v1"),
            table_snapshots=self.override.get("table_snapshots", table_snapshots),
        )
