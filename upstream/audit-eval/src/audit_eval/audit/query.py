"""Read-history replay query API."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Protocol

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
from audit_eval.audit.manifest_gateway import (
    FormalSnapshotGateway,
    ManifestGateway,
)
from audit_eval.audit.replay_view import ReplayView
from audit_eval.contracts.audit_record import AuditRecord
from audit_eval.contracts.manifest_draft import CyclePublishManifestDraft
from audit_eval.contracts.replay_record import ReplayRecord


class ReplayRepository(Protocol):
    """Repository boundary for formal replay and audit records."""

    def get_replay_record(
        self,
        cycle_id: str,
        object_ref: str,
    ) -> ReplayRecord | None:
        """Return the replay record for cycle_id/object_ref, if present."""

    def get_audit_records(self, record_ids: Sequence[str]) -> list[AuditRecord]:
        """Return audit records matching record_ids."""


class DagsterRunGateway(Protocol):
    """Gateway for Dagster run history summaries."""

    def load_summary(self, dagster_run_id: str) -> dict[str, Any]:
        """Load a run-history summary by run id."""


class GraphSnapshotGateway(Protocol):
    """Gateway for graph snapshot summaries."""

    def load(self, graph_snapshot_ref: str) -> dict[str, Any]:
        """Load a graph snapshot by explicit snapshot ref."""


@dataclass(frozen=True)
class ReplayQueryContext:
    """Injected dependencies for read-history replay reconstruction."""

    repository: ReplayRepository
    manifest_gateway: ManifestGateway
    formal_gateway: FormalSnapshotGateway
    dagster_gateway: DagsterRunGateway | None = None
    graph_gateway: GraphSnapshotGateway | None = None


def replay_cycle_object(
    cycle_id: str,
    object_ref: str,
    context: ReplayQueryContext | None = None,
) -> ReplayView:
    """Rebuild a ReplayView from formal historical records without model calls."""

    if context is None:
        raise ReplayQueryError(
            "No default replay query context is configured; pass context=..."
        )

    replay_record = context.repository.get_replay_record(cycle_id, object_ref)
    if replay_record is None:
        raise ReplayRecordNotFound(
            f"No replay_record found for cycle_id={cycle_id!r}, "
            f"object_ref={object_ref!r}"
        )
    _validate_replay_record_binding(replay_record, cycle_id, object_ref)

    manifest = context.manifest_gateway.load(replay_record.manifest_cycle_id)
    manifest_snapshot_refs = _validate_manifest_binding(
        replay_record=replay_record,
        manifest=manifest,
        object_ref=object_ref,
    )

    audit_records = _load_audit_records(context.repository, replay_record)
    historical_formal_objects = _load_historical_formal_objects(
        formal_gateway=context.formal_gateway,
        snapshot_refs=manifest_snapshot_refs,
    )
    graph_snapshot = _load_graph_snapshot(context, replay_record)
    dagster_run_summary = _load_dagster_summary(context, replay_record)

    return ReplayView(
        cycle_id=cycle_id,
        object_ref=object_ref,
        replay_record=replay_record,
        audit_records=audit_records,
        manifest_snapshot_set=dict(manifest.snapshot_refs),
        historical_formal_objects=historical_formal_objects,
        graph_snapshot_ref=replay_record.graph_snapshot_ref,
        graph_snapshot=graph_snapshot,
        dagster_run_summary=dagster_run_summary,
    )


def _validate_replay_record_binding(
    replay_record: ReplayRecord,
    cycle_id: str,
    object_ref: str,
) -> None:
    if replay_record.cycle_id != cycle_id:
        raise ReplayQueryError(
            "ReplayRecord.cycle_id does not match requested cycle_id: "
            f"{replay_record.cycle_id!r} != {cycle_id!r}"
        )
    if replay_record.object_ref != object_ref:
        raise ReplayQueryError(
            "ReplayRecord.object_ref does not match requested object_ref: "
            f"{replay_record.object_ref!r} != {object_ref!r}"
        )
    if replay_record.replay_mode != "read_history":
        raise ReplayModeError(
            f'ReplayRecord.replay_mode must be "read_history", got '
            f"{replay_record.replay_mode!r}"
        )


def _validate_manifest_binding(
    replay_record: ReplayRecord,
    manifest: CyclePublishManifestDraft,
    object_ref: str,
) -> dict[str, str]:
    if manifest.published_cycle_id != replay_record.manifest_cycle_id:
        raise ManifestBindingError(
            "Manifest published_cycle_id does not match replay_record "
            f"manifest_cycle_id: {manifest.published_cycle_id!r} != "
            f"{replay_record.manifest_cycle_id!r}"
        )

    if object_ref not in replay_record.formal_snapshot_refs:
        raise ManifestBindingError(
            f"ReplayRecord.formal_snapshot_refs missing object_ref {object_ref!r}"
        )
    if object_ref not in manifest.snapshot_refs:
        raise ManifestBindingError(
            f"Manifest snapshot_refs missing object_ref {object_ref!r}"
        )

    manifest_snapshot_refs: dict[str, str] = {}
    for formal_object_ref, replay_snapshot_ref in (
        replay_record.formal_snapshot_refs.items()
    ):
        if not isinstance(replay_snapshot_ref, str):
            raise ManifestBindingError(
                "ReplayRecord.formal_snapshot_refs values must be strings: "
                f"{formal_object_ref!r}"
            )
        try:
            manifest_snapshot_ref = manifest.snapshot_refs[formal_object_ref]
        except KeyError as exc:
            raise ManifestBindingError(
                "Manifest snapshot_refs missing replay formal object "
                f"{formal_object_ref!r}"
            ) from exc
        if replay_snapshot_ref != manifest_snapshot_ref:
            raise ManifestBindingError(
                f"Replay snapshot ref for {formal_object_ref!r} does not "
                "match manifest snapshot ref"
            )
        manifest_snapshot_refs[formal_object_ref] = manifest_snapshot_ref
    return manifest_snapshot_refs


def _load_audit_records(
    repository: ReplayRepository,
    replay_record: ReplayRecord,
) -> tuple[AuditRecord, ...]:
    records = repository.get_audit_records(replay_record.audit_record_ids)
    records_by_id = {record.record_id: record for record in records}
    missing_record_ids = [
        record_id
        for record_id in replay_record.audit_record_ids
        if record_id not in records_by_id
    ]
    if missing_record_ids:
        missing = ", ".join(missing_record_ids)
        raise AuditRecordMissing(
            "ReplayRecord.audit_record_ids reference missing AuditRecord rows: "
            f"{missing}"
        )

    ordered_records = tuple(
        records_by_id[record_id] for record_id in replay_record.audit_record_ids
    )
    for record in ordered_records:
        if record.cycle_id != replay_record.cycle_id:
            raise AuditRecordMissing(
                "AuditRecord.cycle_id does not match replay_record.cycle_id for "
                f"{record.record_id!r}"
            )
    return ordered_records


def _load_historical_formal_objects(
    formal_gateway: FormalSnapshotGateway,
    snapshot_refs: dict[str, str],
) -> dict[str, Any]:
    historical_formal_objects: dict[str, Any] = {}
    for formal_object_ref, snapshot_ref in snapshot_refs.items():
        try:
            snapshot = formal_gateway.load_snapshot(snapshot_ref)
        except SnapshotLoadError:
            raise
        except Exception as exc:
            raise SnapshotLoadError(
                f"Failed to load manifest-bound snapshot {snapshot_ref!r}"
            ) from exc

        if not isinstance(snapshot, dict):
            raise SnapshotLoadError(
                f"Formal snapshot {snapshot_ref!r} did not return an object"
            )
        if snapshot.get("snapshot_ref") != snapshot_ref:
            raise SnapshotLoadError(
                f"Formal snapshot payload is not bound to {snapshot_ref!r}"
            )
        historical_formal_objects[formal_object_ref] = {
            "source_ref": snapshot_ref,
            "data": snapshot,
        }
    return historical_formal_objects


def _load_graph_snapshot(
    context: ReplayQueryContext,
    replay_record: ReplayRecord,
) -> dict[str, Any] | None:
    graph_snapshot_ref = replay_record.graph_snapshot_ref
    if graph_snapshot_ref is None:
        return None
    if context.graph_gateway is None:
        raise GraphSnapshotMissing(
            f"No graph gateway configured for {graph_snapshot_ref!r}"
        )

    try:
        graph_snapshot = context.graph_gateway.load(graph_snapshot_ref)
    except GraphSnapshotMissing:
        raise
    except Exception as exc:
        raise GraphSnapshotMissing(
            f"Failed to load graph snapshot {graph_snapshot_ref!r}"
        ) from exc

    if not isinstance(graph_snapshot, dict):
        raise GraphSnapshotMissing(
            f"Graph snapshot {graph_snapshot_ref!r} did not return an object"
        )
    _require_context_identity(
        payload=graph_snapshot,
        identity_key="graph_snapshot_ref",
        expected_identity=graph_snapshot_ref,
        cycle_id=replay_record.cycle_id,
        error_type=GraphSnapshotMissing,
    )
    return graph_snapshot


def _load_dagster_summary(
    context: ReplayQueryContext,
    replay_record: ReplayRecord,
) -> dict[str, Any]:
    if context.dagster_gateway is None:
        raise DagsterSummaryMissing(
            f"No Dagster gateway configured for {replay_record.dagster_run_id!r}"
        )

    try:
        dagster_run_summary = context.dagster_gateway.load_summary(
            replay_record.dagster_run_id
        )
    except DagsterSummaryMissing:
        raise
    except Exception as exc:
        raise DagsterSummaryMissing(
            f"Failed to load Dagster run summary {replay_record.dagster_run_id!r}"
        ) from exc

    if not isinstance(dagster_run_summary, dict):
        raise DagsterSummaryMissing(
            "Dagster run summary did not return an object for "
            f"{replay_record.dagster_run_id!r}"
        )
    _require_context_identity(
        payload=dagster_run_summary,
        identity_key="run_id",
        expected_identity=replay_record.dagster_run_id,
        cycle_id=replay_record.cycle_id,
        error_type=DagsterSummaryMissing,
    )
    return dagster_run_summary


def _require_context_identity(
    payload: dict[str, Any],
    identity_key: str,
    expected_identity: str,
    cycle_id: str,
    error_type: type[ReplayQueryError],
) -> None:
    if identity_key not in payload:
        raise error_type(f"Context payload missing {identity_key!r}")
    if payload[identity_key] != expected_identity:
        raise error_type(
            f"Context payload {identity_key!r} does not match replay record: "
            f"{payload[identity_key]!r} != {expected_identity!r}"
        )
    if "cycle_id" not in payload:
        raise error_type("Context payload missing 'cycle_id'")
    if payload["cycle_id"] != cycle_id:
        raise error_type(
            "Context payload 'cycle_id' does not match replay record: "
            f"{payload['cycle_id']!r} != {cycle_id!r}"
        )


__all__ = [
    "DagsterRunGateway",
    "GraphSnapshotGateway",
    "ReplayQueryContext",
    "ReplayRepository",
    "replay_cycle_object",
]
