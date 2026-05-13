"""Offline replay spike bound to fixture manifests."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from copy import deepcopy
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from audit_eval.audit.query import ReplayQueryContext, replay_cycle_object
from audit_eval.contracts.audit_record import AuditRecord
from audit_eval.contracts.manifest_draft import CyclePublishManifestDraft
from audit_eval.contracts.replay_record import ReplayRecord


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_required_json(path: Path, description: str) -> Any:
    try:
        return _read_json(path)
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"Missing {description} fixture: {path}") from exc


def load_manifest(path: Path) -> CyclePublishManifestDraft:
    """Load the published manifest snapshot set."""

    return CyclePublishManifestDraft.model_validate(_read_json(path))


def load_audit_records(path: Path) -> list[AuditRecord]:
    """Load draft audit records from a fixture JSON array."""

    records = _read_json(path)
    if not isinstance(records, list):
        raise ValueError(f"Expected audit record array in {path}")
    return [AuditRecord.model_validate(record) for record in records]


def load_replay_record(path: Path, object_ref: str) -> ReplayRecord:
    """Load the replay record matching one object reference."""

    records = _read_json(path)
    if not isinstance(records, list):
        raise ValueError(f"Expected replay record array in {path}")

    matches = [
        ReplayRecord.model_validate(record)
        for record in records
        if record.get("object_ref") == object_ref
    ]
    if len(matches) != 1:
        raise KeyError(f"Expected exactly one replay record for {object_ref}")
    return matches[0]


def _fixture_path(cycle_fixture: Path, relative_ref: str) -> Path:
    relative_path = Path(relative_ref)
    if relative_path.is_absolute() or ".." in relative_path.parts:
        raise ValueError(f"Snapshot ref escapes fixture root: {relative_ref}")
    return cycle_fixture / relative_path


def _snapshot_path(cycle_fixture: Path, snapshot_ref: str) -> Path:
    parsed_ref = urlparse(snapshot_ref)

    if parsed_ref.scheme == "snapshot":
        if parsed_ref.netloc != cycle_fixture.name:
            raise ValueError(
                "Snapshot ref cycle does not match loaded fixture cycle"
            )

        ref_path = parsed_ref.path.lstrip("/")
        if not ref_path:
            raise ValueError(f"Snapshot ref has no fixture path: {snapshot_ref}")

        if ref_path.endswith(".json"):
            relative_ref = ref_path
        elif ref_path.startswith("formal_snapshots/"):
            relative_ref = f"{ref_path}.json"
        else:
            relative_ref = f"formal_snapshots/{ref_path}.json"
        return _fixture_path(cycle_fixture, relative_ref)

    if parsed_ref.scheme:
        raise ValueError(f"Unsupported snapshot ref scheme: {parsed_ref.scheme}")
    if not snapshot_ref.endswith(".json"):
        raise ValueError(
            f"Local snapshot refs must point to JSON fixtures: {snapshot_ref}"
        )
    return _fixture_path(cycle_fixture, snapshot_ref)


def _graph_snapshot_path(cycle_fixture: Path, graph_snapshot_ref: str) -> Path:
    parsed_ref = urlparse(graph_snapshot_ref)

    if parsed_ref.scheme != "graph":
        raise ValueError(
            f"Unsupported graph snapshot ref scheme: {parsed_ref.scheme}"
        )
    if parsed_ref.netloc != cycle_fixture.name:
        raise ValueError(
            "Graph snapshot ref cycle does not match loaded fixture cycle"
        )

    ref_path = parsed_ref.path.lstrip("/")
    if not ref_path:
        raise ValueError(
            f"Graph snapshot ref has no fixture path: {graph_snapshot_ref}"
        )

    if ref_path.endswith(".json"):
        relative_ref = ref_path
    elif ref_path.startswith("graph_snapshots/"):
        relative_ref = f"{ref_path}.json"
    else:
        relative_ref = f"graph_snapshots/{ref_path}.json"
    return _fixture_path(cycle_fixture, relative_ref)


def _dagster_run_summary_path(cycle_fixture: Path, dagster_run_id: str) -> Path:
    run_id_path = Path(dagster_run_id)
    if (
        not dagster_run_id
        or run_id_path.is_absolute()
        or len(run_id_path.parts) != 1
        or ".." in run_id_path.parts
    ):
        raise ValueError(f"Dagster run id escapes fixture root: {dagster_run_id}")
    return _fixture_path(cycle_fixture, f"dagster_runs/{dagster_run_id}.json")


class FixtureReplayRepository:
    """Fixture-backed repository used by the spike CLI wrapper."""

    def __init__(self, cycle_fixture: Path) -> None:
        self.cycle_fixture = cycle_fixture

    def get_replay_record(
        self,
        cycle_id: str,
        object_ref: str,
    ) -> ReplayRecord | None:
        if self.cycle_fixture.name != cycle_id:
            return None

        records = _read_required_json(
            self.cycle_fixture / "replay_records.json",
            "replay records",
        )
        if not isinstance(records, list):
            raise ValueError(
                f"Expected replay record array in {self.cycle_fixture}"
            )

        matches = [
            ReplayRecord.model_validate(record)
            for record in records
            if record.get("cycle_id") == cycle_id
            and record.get("object_ref") == object_ref
        ]
        if len(matches) > 1:
            raise ValueError(
                f"Expected at most one replay record for {cycle_id}/{object_ref}"
            )
        return matches[0] if matches else None

    def get_audit_records(self, record_ids: Sequence[str]) -> list[AuditRecord]:
        records = load_audit_records(self.cycle_fixture / "audit_records.json")
        requested_ids = set(record_ids)
        return [record for record in records if record.record_id in requested_ids]


class FixtureManifestGateway:
    """Fixture-backed cycle_publish_manifest gateway."""

    def __init__(self, fixture_root: Path) -> None:
        self.fixture_root = fixture_root

    def load(self, cycle_id: str) -> CyclePublishManifestDraft:
        return load_manifest(self.fixture_root / cycle_id / "manifest.json")


class FixtureFormalSnapshotGateway:
    """Fixture-backed formal snapshot gateway."""

    def __init__(self, cycle_fixture: Path) -> None:
        self.cycle_fixture = cycle_fixture

    def load_snapshot(self, snapshot_ref: str) -> dict[str, Any]:
        snapshot_path = _snapshot_path(self.cycle_fixture, snapshot_ref)
        snapshot = _read_required_json(
            snapshot_path,
            f"formal snapshot for {snapshot_ref}",
        )
        if not isinstance(snapshot, dict):
            raise ValueError(f"Expected snapshot object in {snapshot_path}")
        return snapshot


class FixtureGraphSnapshotGateway:
    """Fixture-backed graph snapshot gateway."""

    def __init__(self, cycle_fixture: Path) -> None:
        self.cycle_fixture = cycle_fixture

    def load(self, graph_snapshot_ref: str) -> dict[str, Any]:
        graph_path = _graph_snapshot_path(self.cycle_fixture, graph_snapshot_ref)
        graph_snapshot = _read_required_json(
            graph_path,
            f"graph snapshot summary for {graph_snapshot_ref}",
        )
        if not isinstance(graph_snapshot, dict):
            raise ValueError(f"Expected graph snapshot summary object in {graph_path}")
        return graph_snapshot


class FixtureDagsterRunGateway:
    """Fixture-backed Dagster run summary gateway."""

    def __init__(self, cycle_fixture: Path) -> None:
        self.cycle_fixture = cycle_fixture

    def load_summary(self, dagster_run_id: str) -> dict[str, Any]:
        dagster_path = _dagster_run_summary_path(self.cycle_fixture, dagster_run_id)
        dagster_summary = _read_required_json(
            dagster_path,
            f"Dagster run summary for {dagster_run_id}",
        )
        if not isinstance(dagster_summary, dict):
            raise ValueError(f"Expected Dagster run summary object in {dagster_path}")
        return dagster_summary


def _fixture_context(fixture_root: Path, cycle_id: str) -> ReplayQueryContext:
    cycle_fixture = fixture_root / cycle_id
    return ReplayQueryContext(
        repository=FixtureReplayRepository(cycle_fixture),
        manifest_gateway=FixtureManifestGateway(fixture_root),
        formal_gateway=FixtureFormalSnapshotGateway(cycle_fixture),
        dagster_gateway=FixtureDagsterRunGateway(cycle_fixture),
        graph_gateway=FixtureGraphSnapshotGateway(cycle_fixture),
    )


def reconstruct_replay_view(
    cycle_id: str,
    object_ref: str,
    fixture_root: Path,
) -> dict[str, Any]:
    """Rebuild a read-history replay view from offline fixture files."""

    replay_view = replay_cycle_object(
        cycle_id=cycle_id,
        object_ref=object_ref,
        context=_fixture_context(fixture_root, cycle_id),
    )
    return _spike_cli_view(replay_view.to_dict())


def _spike_cli_view(replay_view: dict[str, Any]) -> dict[str, Any]:
    """Return CLI-compatible replay JSON with the legacy graph alias."""

    cli_view = deepcopy(replay_view)
    if "graph_snapshot" in cli_view and "graph_snapshot_summary" not in cli_view:
        cli_view["graph_snapshot_summary"] = deepcopy(cli_view["graph_snapshot"])
    return cli_view


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cycle-id", required=True)
    parser.add_argument("--object-ref", required=True)
    parser.add_argument(
        "--fixtures",
        type=Path,
        required=True,
        help="Root directory containing spike cycle fixtures.",
    )
    args = parser.parse_args(argv)

    replay_view = reconstruct_replay_view(
        cycle_id=args.cycle_id,
        object_ref=args.object_ref,
        fixture_root=args.fixtures,
    )
    json.dump(replay_view, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
