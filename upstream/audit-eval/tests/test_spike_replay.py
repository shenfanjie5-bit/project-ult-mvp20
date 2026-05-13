import json
import shutil
import socket
import urllib.request
from pathlib import Path
from typing import Any

import pytest

from audit_eval.audit.errors import DagsterSummaryMissing, GraphSnapshotMissing
from audit_eval.audit.errors import SnapshotLoadError
from scripts import spike_replay


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "spike"


@pytest.fixture(autouse=True)
def block_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_network_call(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("Replay spike must not call network")

    monkeypatch.setattr(urllib.request, "urlopen", fail_network_call)
    monkeypatch.setattr(socket, "socket", fail_network_call)


def _run_cli(
    capsys: pytest.CaptureFixture[str],
    fixture_root: Path = FIXTURE_ROOT,
) -> dict[str, Any]:
    result = spike_replay.main(
        [
            "--cycle-id",
            "cycle_20260410",
            "--object-ref",
            "recommendation",
            "--fixtures",
            str(fixture_root),
        ]
    )
    assert result == 0
    return json.loads(capsys.readouterr().out)


def test_cli_outputs_package_replay_view_fields(
    capsys: pytest.CaptureFixture[str],
) -> None:
    replay_view = _run_cli(capsys)

    assert set(replay_view) >= {
        "audit_records",
        "dagster_run_summary",
        "graph_snapshot",
        "graph_snapshot_ref",
        "graph_snapshot_summary",
        "manifest_snapshot_set",
        "historical_formal_objects",
        "replay_record",
    }
    manifest_refs = set(replay_view["manifest_snapshot_set"].values())
    historical_objects = replay_view["historical_formal_objects"]

    assert set(historical_objects) == {"world_state", "recommendation"}
    for historical_object in historical_objects.values():
        assert historical_object["source_ref"] in manifest_refs
    assert replay_view["graph_snapshot_ref"] == (
        "graph://cycle_20260410/portfolio_graph"
    )
    assert replay_view["graph_snapshot_summary"]["graph_snapshot_ref"] == (
        replay_view["graph_snapshot_ref"]
    )
    assert replay_view["dagster_run_summary"]["run_id"] == (
        "dagster-fixture-run-20260410"
    )
    assert replay_view["replay_record"]["created_at"] == "2026-04-10T16:09:00Z"


def test_cli_core_path_calls_package_query(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    calls: list[tuple[str, str, object]] = []

    class FakeReplayView:
        def to_dict(self) -> dict[str, Any]:
            return {"cycle_id": "cycle_20260410", "object_ref": "recommendation"}

    def fake_replay_cycle_object(
        cycle_id: str,
        object_ref: str,
        context: object,
    ) -> FakeReplayView:
        calls.append((cycle_id, object_ref, context))
        return FakeReplayView()

    monkeypatch.setattr(
        spike_replay,
        "replay_cycle_object",
        fake_replay_cycle_object,
    )

    replay_view = _run_cli(capsys)

    assert replay_view == {
        "cycle_id": "cycle_20260410",
        "object_ref": "recommendation",
    }
    assert [(cycle_id, object_ref) for cycle_id, object_ref, _context in calls] == [
        ("cycle_20260410", "recommendation")
    ]


def test_manifest_ref_selects_snapshot_file_not_object_name(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    fixture_copy = tmp_path / "spike"
    shutil.copytree(FIXTURE_ROOT, fixture_copy)
    cycle_fixture = fixture_copy / "cycle_20260410"

    manifest_snapshot_ref = (
        "snapshot://cycle_20260410/formal_snapshots/"
        "recommendation_manifest_bound.json"
    )
    manifest_path = cycle_fixture / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["snapshot_refs"]["recommendation"] = manifest_snapshot_ref
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    replay_records_path = cycle_fixture / "replay_records.json"
    replay_records = json.loads(replay_records_path.read_text(encoding="utf-8"))
    for replay_record in replay_records:
        if replay_record["object_ref"] == "recommendation":
            replay_record["formal_snapshot_refs"][
                "recommendation"
            ] = manifest_snapshot_ref
    replay_records_path.write_text(json.dumps(replay_records), encoding="utf-8")

    bound_snapshot_path = (
        cycle_fixture / "formal_snapshots" / "recommendation_manifest_bound.json"
    )
    bound_snapshot = {
        "snapshot_ref": manifest_snapshot_ref,
        "object_ref": "recommendation",
        "as_of": "2026-04-10",
        "recommendation": {
            "action": "raise_cash",
            "confidence": 0.91,
            "source_world_state_ref": "snapshot://cycle_20260410/world_state",
        },
    }
    bound_snapshot_path.write_text(json.dumps(bound_snapshot), encoding="utf-8")

    replay_view = _run_cli(capsys, fixture_copy)

    recommendation = replay_view["historical_formal_objects"]["recommendation"]
    assert recommendation["source_ref"] == manifest_snapshot_ref
    assert recommendation["data"]["snapshot_ref"] == manifest_snapshot_ref
    assert recommendation["data"]["recommendation"]["action"] == "raise_cash"

    bound_snapshot["snapshot_ref"] = "snapshot://cycle_20260410/recommendation"
    bound_snapshot_path.write_text(json.dumps(bound_snapshot), encoding="utf-8")

    with pytest.raises(SnapshotLoadError, match="not bound"):
        _run_cli(capsys, fixture_copy)


def test_missing_graph_snapshot_summary_raises_typed_error(tmp_path: Path) -> None:
    fixture_copy = tmp_path / "spike"
    shutil.copytree(FIXTURE_ROOT, fixture_copy)
    graph_summary_path = (
        fixture_copy
        / "cycle_20260410"
        / "graph_snapshots"
        / "portfolio_graph.json"
    )
    graph_summary_path.unlink()

    with pytest.raises(GraphSnapshotMissing, match="portfolio_graph"):
        spike_replay.main(
            [
                "--cycle-id",
                "cycle_20260410",
                "--object-ref",
                "recommendation",
                "--fixtures",
                str(fixture_copy),
            ]
        )


def test_missing_dagster_run_summary_raises_typed_error(tmp_path: Path) -> None:
    fixture_copy = tmp_path / "spike"
    shutil.copytree(FIXTURE_ROOT, fixture_copy)
    dagster_summary_path = (
        fixture_copy
        / "cycle_20260410"
        / "dagster_runs"
        / "dagster-fixture-run-20260410.json"
    )
    dagster_summary_path.unlink()

    with pytest.raises(DagsterSummaryMissing, match="dagster-fixture-run"):
        spike_replay.main(
            [
                "--cycle-id",
                "cycle_20260410",
                "--object-ref",
                "recommendation",
                "--fixtures",
                str(fixture_copy),
            ]
        )
