import json
from pathlib import Path
from typing import Any

from audit_eval.audit import (
    InMemoryFormalAuditStorageAdapter,
    build_in_memory_replay_query_context,
    persist_audit_records,
    persist_replay_records,
    replay_cycle_object,
)
from audit_eval.contracts import AuditWriteBundle, CyclePublishManifestDraft


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "spike" / "cycle_20260410"
SAMPLE_BUNDLE_PATH = (
    Path(__file__).parent / "fixtures" / "audit_writer" / "sample_bundle.json"
)


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


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


def test_persisted_in_memory_rows_feed_replay_reconstruction() -> None:
    bundle = AuditWriteBundle.model_validate(_read_json(SAMPLE_BUNDLE_PATH))
    storage = InMemoryFormalAuditStorageAdapter()

    audit_ids = persist_audit_records(bundle, storage)
    replay_ids = persist_replay_records(bundle, storage)

    manifest = CyclePublishManifestDraft.model_validate(
        _read_json(FIXTURE_ROOT / "manifest.json")
    )
    formal_gateway = StaticFormalSnapshotGateway(
        {
            "snapshot://cycle_20260410/world_state": _read_json(
                FIXTURE_ROOT / "formal_snapshots" / "world_state.json"
            ),
            "snapshot://cycle_20260410/recommendation": _read_json(
                FIXTURE_ROOT / "formal_snapshots" / "recommendation.json"
            ),
        }
    )
    context = build_in_memory_replay_query_context(
        storage=storage,
        manifest_gateway=StaticManifestGateway(manifest),
        formal_gateway=formal_gateway,
        graph_gateway=StaticGraphSnapshotGateway(
            _read_json(FIXTURE_ROOT / "graph_snapshots" / "portfolio_graph.json")
        ),
        dagster_gateway=StaticDagsterRunGateway(
            _read_json(
                FIXTURE_ROOT
                / "dagster_runs"
                / "dagster-fixture-run-20260410.json"
            )
        ),
    )

    replay_view = replay_cycle_object(
        "cycle_20260410",
        "recommendation",
        context=context,
    )

    expected_replay_record = bundle.replay_records_by_object_ref()["recommendation"]
    expected_snapshot_refs = [
        manifest.snapshot_refs["world_state"],
        manifest.snapshot_refs["recommendation"],
    ]

    assert audit_ids == [record.record_id for record in bundle.audit_records]
    assert replay_ids == [record.replay_id for record in bundle.replay_records]
    assert len(storage.audit_rows) == len(bundle.audit_records)
    assert len(storage.replay_rows) == len(bundle.replay_records)
    assert replay_view.replay_record.replay_id == expected_replay_record.replay_id
    assert [record.record_id for record in replay_view.audit_records] == (
        expected_replay_record.audit_record_ids
    )
    assert replay_view.manifest_snapshot_set == manifest.snapshot_refs
    assert formal_gateway.loaded_snapshot_refs == expected_snapshot_refs
    assert replay_view.historical_formal_objects["world_state"]["source_ref"] == (
        "snapshot://cycle_20260410/world_state"
    )
    recommendation = replay_view.historical_formal_objects["recommendation"]
    assert recommendation["source_ref"] == "snapshot://cycle_20260410/recommendation"
    assert recommendation["data"]["recommendation"]["action"] == "reduce_beta"
