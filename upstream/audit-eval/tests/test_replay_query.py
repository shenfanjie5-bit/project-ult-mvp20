import json
import re
import socket
import time
import urllib.request
from collections.abc import Sequence
from pathlib import Path
from typing import Any, cast

import pytest

from audit_eval.audit import ReplayView, replay_cycle_object
from audit_eval.audit.errors import (
    AuditRecordMissing,
    DagsterSummaryMissing,
    GraphSnapshotMissing,
    ManifestBindingError,
    ReplayModeError,
    ReplayQueryError,
    ReplayRecordNotFound,
    SnapshotLoadError,
)
from audit_eval.audit.query import ReplayQueryContext
from audit_eval.contracts.audit_record import AuditRecord
from audit_eval.contracts.manifest_draft import CyclePublishManifestDraft
from audit_eval.contracts.replay_record import ReplayRecord


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "spike" / "cycle_20260410"


@pytest.fixture(autouse=True)
def block_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_network_call(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("Replay query must not call network")

    monkeypatch.setattr(urllib.request, "urlopen", fail_network_call)
    monkeypatch.setattr(socket, "socket", fail_network_call)


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _fixture_manifest() -> CyclePublishManifestDraft:
    return CyclePublishManifestDraft.model_validate(
        _read_json(FIXTURE_ROOT / "manifest.json")
    )


def _fixture_audit_records() -> dict[str, AuditRecord]:
    payloads = _read_json(FIXTURE_ROOT / "audit_records.json")
    records = [AuditRecord.model_validate(payload) for payload in payloads]
    return {record.record_id: record for record in records}


def _fixture_replay_records() -> dict[tuple[str, str], ReplayRecord]:
    payloads = _read_json(FIXTURE_ROOT / "replay_records.json")
    records = [ReplayRecord.model_validate(payload) for payload in payloads]
    return {(record.cycle_id, record.object_ref): record for record in records}


def _fixture_snapshots() -> dict[str, dict[str, Any]]:
    return {
        "snapshot://cycle_20260410/world_state": _read_json(
            FIXTURE_ROOT / "formal_snapshots" / "world_state.json"
        ),
        "snapshot://cycle_20260410/recommendation": _read_json(
            FIXTURE_ROOT / "formal_snapshots" / "recommendation.json"
        ),
    }


def _fixture_graph_snapshot() -> dict[str, Any]:
    return _read_json(FIXTURE_ROOT / "graph_snapshots" / "portfolio_graph.json")


def _fixture_dagster_summary() -> dict[str, Any]:
    return _read_json(
        FIXTURE_ROOT / "dagster_runs" / "dagster-fixture-run-20260410.json"
    )


class FakeReplayRepository:
    def __init__(
        self,
        calls: list[str],
        replay_records: dict[tuple[str, str], ReplayRecord] | None = None,
        audit_records: dict[str, AuditRecord] | None = None,
    ) -> None:
        self.calls = calls
        self.replay_records = (
            _fixture_replay_records() if replay_records is None else replay_records
        )
        self.audit_records = (
            _fixture_audit_records() if audit_records is None else audit_records
        )

    def get_replay_record(
        self,
        cycle_id: str,
        object_ref: str,
    ) -> ReplayRecord | None:
        self.calls.append("replay_record")
        return self.replay_records.get((cycle_id, object_ref))

    def get_audit_records(self, record_ids: Sequence[str]) -> list[AuditRecord]:
        self.calls.append("audit_records")
        return [
            self.audit_records[record_id]
            for record_id in record_ids
            if record_id in self.audit_records
        ]


class FakeManifestGateway:
    def __init__(
        self,
        calls: list[str],
        manifest: CyclePublishManifestDraft | None = None,
    ) -> None:
        self.calls = calls
        self.manifest = _fixture_manifest() if manifest is None else manifest

    def load(self, cycle_id: str) -> CyclePublishManifestDraft:
        self.calls.append("manifest")
        return self.manifest


class FakeFormalSnapshotGateway:
    def __init__(
        self,
        calls: list[str],
        snapshots: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        self.calls = calls
        self.snapshots = _fixture_snapshots() if snapshots is None else snapshots

    def load_snapshot(self, snapshot_ref: str) -> dict[str, Any]:
        self.calls.append(f"formal:{snapshot_ref}")
        return self.snapshots[snapshot_ref]


class FakeGraphSnapshotGateway:
    def __init__(self, calls: list[str], payload: Any | None = None) -> None:
        self.calls = calls
        self.payload = _fixture_graph_snapshot() if payload is None else payload

    def load(self, graph_snapshot_ref: str) -> dict[str, Any]:
        self.calls.append("graph")
        return cast(dict[str, Any], self.payload)


class FakeDagsterRunGateway:
    def __init__(self, calls: list[str], payload: Any | None = None) -> None:
        self.calls = calls
        self.payload = _fixture_dagster_summary() if payload is None else payload

    def load_summary(self, dagster_run_id: str) -> dict[str, Any]:
        self.calls.append("dagster")
        return cast(dict[str, Any], self.payload)


def _context(
    *,
    replay_record: ReplayRecord | None = None,
    replay_records: dict[tuple[str, str], ReplayRecord] | None = None,
    audit_records: dict[str, AuditRecord] | None = None,
    manifest: CyclePublishManifestDraft | None = None,
    snapshots: dict[str, dict[str, Any]] | None = None,
    graph_payload: Any | None = None,
    dagster_payload: Any | None = None,
    graph_gateway: Any = "default",
    dagster_gateway: Any = "default",
) -> tuple[ReplayQueryContext, list[str]]:
    calls: list[str] = []
    if replay_record is not None:
        replay_records = {
            (replay_record.cycle_id, replay_record.object_ref): replay_record
        }

    context = ReplayQueryContext(
        repository=FakeReplayRepository(calls, replay_records, audit_records),
        manifest_gateway=FakeManifestGateway(calls, manifest),
        formal_gateway=FakeFormalSnapshotGateway(calls, snapshots),
        dagster_gateway=(
            FakeDagsterRunGateway(calls, dagster_payload)
            if dagster_gateway == "default"
            else dagster_gateway
        ),
        graph_gateway=(
            FakeGraphSnapshotGateway(calls, graph_payload)
            if graph_gateway == "default"
            else graph_gateway
        ),
    )
    return context, calls


def _recommendation_replay_record() -> ReplayRecord:
    return _fixture_replay_records()[("cycle_20260410", "recommendation")]


def test_replay_cycle_object_returns_manifest_bound_replay_view() -> None:
    context, calls = _context()

    started_at = time.perf_counter()
    replay_view = replay_cycle_object(
        "cycle_20260410",
        "recommendation",
        context=context,
    )
    elapsed_seconds = time.perf_counter() - started_at

    assert elapsed_seconds < 5
    assert isinstance(replay_view, ReplayView)
    assert calls == [
        "replay_record",
        "manifest",
        "audit_records",
        "formal:snapshot://cycle_20260410/world_state",
        "formal:snapshot://cycle_20260410/recommendation",
        "graph",
        "dagster",
    ]

    replay_dict = replay_view.to_dict()
    assert set(replay_dict) >= {
        "audit_records",
        "dagster_run_summary",
        "graph_snapshot",
        "graph_snapshot_ref",
        "historical_formal_objects",
        "manifest_snapshot_set",
        "replay_record",
    }
    assert "graph_snapshot_summary" not in replay_dict
    json.dumps(replay_dict)

    manifest_refs = set(replay_dict["manifest_snapshot_set"].values())
    historical_objects = replay_dict["historical_formal_objects"]
    assert set(historical_objects) == {"world_state", "recommendation"}
    for historical_object in historical_objects.values():
        assert historical_object["source_ref"] in manifest_refs
        assert historical_object["data"]["snapshot_ref"] == historical_object[
            "source_ref"
        ]
    assert replay_dict["graph_snapshot_ref"] == (
        "graph://cycle_20260410/portfolio_graph"
    )
    assert replay_dict["graph_snapshot"]["graph_snapshot_ref"] == (
        replay_dict["graph_snapshot_ref"]
    )
    assert replay_dict["dagster_run_summary"]["run_id"] == (
        "dagster-fixture-run-20260410"
    )


def test_replay_cycle_object_allows_distinct_manifest_cycle_id() -> None:
    replay_record = _recommendation_replay_record().model_copy(
        update={"manifest_cycle_id": "manifest-cycle_20260410"}
    )
    manifest = _fixture_manifest().model_copy(
        update={"published_cycle_id": "manifest-cycle_20260410"}
    )
    context, calls = _context(replay_record=replay_record, manifest=manifest)

    replay_view = replay_cycle_object(
        "cycle_20260410",
        "recommendation",
        context=context,
    )

    assert calls[0:2] == ["replay_record", "manifest"]
    assert replay_view.cycle_id == "cycle_20260410"
    assert replay_view.replay_record.manifest_cycle_id == "manifest-cycle_20260410"
    assert replay_view.manifest_snapshot_set == dict(manifest.snapshot_refs)


def test_default_context_fails_closed() -> None:
    with pytest.raises(ReplayQueryError, match="No default replay query context"):
        replay_cycle_object("cycle_20260410", "recommendation")


def test_missing_replay_record_raises_typed_error() -> None:
    context, _calls = _context(replay_records={})

    with pytest.raises(ReplayRecordNotFound):
        replay_cycle_object("cycle_20260410", "recommendation", context=context)


def test_non_read_history_replay_mode_raises_typed_error() -> None:
    replay_record = _recommendation_replay_record().model_copy(
        update={"replay_mode": cast(Any, "rerun_model")}
    )
    context, calls = _context(replay_record=cast(ReplayRecord, replay_record))

    with pytest.raises(ReplayModeError):
        replay_cycle_object("cycle_20260410", "recommendation", context=context)

    assert calls == ["replay_record"]


def test_missing_referenced_audit_record_raises_typed_error() -> None:
    replay_record = _recommendation_replay_record().model_copy(
        update={
            "audit_record_ids": [
                *_recommendation_replay_record().audit_record_ids,
                "audit-missing",
            ]
        }
    )
    context, _calls = _context(replay_record=replay_record)

    with pytest.raises(AuditRecordMissing, match="audit-missing"):
        replay_cycle_object("cycle_20260410", "recommendation", context=context)


def test_manifest_missing_object_ref_raises_binding_error() -> None:
    manifest = _fixture_manifest().model_copy(deep=True)
    del manifest.snapshot_refs["recommendation"]
    context, _calls = _context(manifest=manifest)

    with pytest.raises(ManifestBindingError, match="recommendation"):
        replay_cycle_object("cycle_20260410", "recommendation", context=context)


def test_manifest_cycle_id_mismatch_raises_binding_error() -> None:
    replay_record = _recommendation_replay_record().model_copy(
        update={"manifest_cycle_id": "cycle_other"}
    )
    context, _calls = _context(replay_record=replay_record)

    with pytest.raises(ManifestBindingError, match="manifest_cycle_id"):
        replay_cycle_object("cycle_20260410", "recommendation", context=context)


def test_replay_snapshot_ref_mismatch_raises_binding_error() -> None:
    replay_record = _recommendation_replay_record().model_copy(deep=True)
    replay_record.formal_snapshot_refs["recommendation"] = (
        "snapshot://cycle_20260410/recommendation_other"
    )
    context, _calls = _context(replay_record=replay_record)

    with pytest.raises(ManifestBindingError, match="recommendation"):
        replay_cycle_object("cycle_20260410", "recommendation", context=context)


def test_snapshot_load_failure_raises_typed_error() -> None:
    snapshots = _fixture_snapshots()
    del snapshots["snapshot://cycle_20260410/recommendation"]
    context, _calls = _context(snapshots=snapshots)

    with pytest.raises(SnapshotLoadError, match="recommendation"):
        replay_cycle_object("cycle_20260410", "recommendation", context=context)


def test_snapshot_ref_mismatch_raises_typed_error() -> None:
    snapshots = _fixture_snapshots()
    snapshots["snapshot://cycle_20260410/recommendation"] = {
        **snapshots["snapshot://cycle_20260410/recommendation"],
        "snapshot_ref": "snapshot://cycle_20260410/recommendation_other",
    }
    context, _calls = _context(snapshots=snapshots)

    with pytest.raises(SnapshotLoadError, match="not bound"):
        replay_cycle_object("cycle_20260410", "recommendation", context=context)


def test_graph_gateway_required_when_replay_record_has_graph_ref() -> None:
    context, _calls = _context(graph_gateway=None)

    with pytest.raises(GraphSnapshotMissing, match="No graph gateway"):
        replay_cycle_object("cycle_20260410", "recommendation", context=context)


def test_dagster_gateway_required_for_run_summary() -> None:
    context, _calls = _context(dagster_gateway=None)

    with pytest.raises(DagsterSummaryMissing, match="No Dagster gateway"):
        replay_cycle_object("cycle_20260410", "recommendation", context=context)


@pytest.mark.parametrize(
    "graph_payload",
    [
        {"cycle_id": "cycle_20260410"},
        {
            "graph_snapshot_ref": "graph://cycle_20260410/wrong_graph",
            "cycle_id": "cycle_20260410",
        },
        {"graph_snapshot_ref": "graph://cycle_20260410/portfolio_graph"},
        {
            "graph_snapshot_ref": "graph://cycle_20260410/portfolio_graph",
            "cycle_id": "cycle_other",
        },
    ],
)
def test_graph_snapshot_requires_explicit_identity_metadata(
    graph_payload: dict[str, Any],
) -> None:
    context, _calls = _context(graph_payload=graph_payload)

    with pytest.raises(GraphSnapshotMissing):
        replay_cycle_object("cycle_20260410", "recommendation", context=context)


@pytest.mark.parametrize(
    "dagster_payload",
    [
        {"cycle_id": "cycle_20260410"},
        {
            "run_id": "dagster-wrong-run",
            "cycle_id": "cycle_20260410",
        },
        {"run_id": "dagster-fixture-run-20260410"},
        {
            "run_id": "dagster-fixture-run-20260410",
            "cycle_id": "cycle_other",
        },
    ],
)
def test_dagster_summary_requires_explicit_identity_metadata(
    dagster_payload: dict[str, Any],
) -> None:
    context, _calls = _context(dagster_payload=dagster_payload)

    with pytest.raises(DagsterSummaryMissing):
        replay_cycle_object("cycle_20260410", "recommendation", context=context)


def test_audit_package_has_no_provider_or_http_client_dependencies() -> None:
    forbidden = re.compile(r"\b(openai|anthropic|requests|httpx)\b")
    for path in (Path(__file__).parents[1] / "src" / "audit_eval" / "audit").glob(
        "*.py"
    ):
        assert forbidden.search(path.read_text(encoding="utf-8")) is None, path
