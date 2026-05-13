"""Lite replay query wiring backed by in-memory formal storage."""

from __future__ import annotations

from collections.abc import Sequence
from copy import deepcopy

from audit_eval.audit.errors import ReplayQueryError
from audit_eval.audit.manifest_gateway import FormalSnapshotGateway, ManifestGateway
from audit_eval.audit.query import (
    DagsterRunGateway,
    GraphSnapshotGateway,
    ReplayQueryContext,
)
from audit_eval.audit.storage import InMemoryFormalAuditStorageAdapter
from audit_eval.contracts.audit_record import AuditRecord
from audit_eval.contracts.replay_record import ReplayRecord


class InMemoryReplayRepository:
    """Replay repository reading rows appended to in-memory formal storage."""

    def __init__(self, storage: InMemoryFormalAuditStorageAdapter) -> None:
        self.storage = storage

    def get_replay_record(
        self,
        cycle_id: str,
        object_ref: str,
    ) -> ReplayRecord | None:
        matches = [
            ReplayRecord.model_validate(deepcopy(row))
            for row in self.storage.replay_rows
            if row.get("cycle_id") == cycle_id and row.get("object_ref") == object_ref
        ]
        if len(matches) > 1:
            raise ReplayQueryError(
                "Expected at most one replay_record for "
                f"cycle_id={cycle_id!r}, object_ref={object_ref!r}"
            )
        return matches[0] if matches else None

    def get_replay_record_by_id(self, replay_id: str) -> ReplayRecord | None:
        matches = [
            ReplayRecord.model_validate(deepcopy(row))
            for row in self.storage.replay_rows
            if row.get("replay_id") == replay_id
        ]
        if len(matches) > 1:
            raise ReplayQueryError(
                f"Expected at most one replay_record for replay_id={replay_id!r}"
            )
        return matches[0] if matches else None

    def get_audit_records(self, record_ids: Sequence[str]) -> list[AuditRecord]:
        requested_ids = set(record_ids)
        if not requested_ids:
            return []

        records_by_id: dict[str, AuditRecord] = {}
        duplicate_record_ids: list[str] = []
        for row in self.storage.audit_rows:
            record_id = row.get("record_id")
            if record_id not in requested_ids:
                continue
            if record_id in records_by_id:
                duplicate_record_ids.append(record_id)
                continue
            records_by_id[record_id] = AuditRecord.model_validate(deepcopy(row))

        if duplicate_record_ids:
            duplicates = ", ".join(sorted(set(duplicate_record_ids)))
            raise ReplayQueryError(f"Duplicate audit_record rows found: {duplicates}")

        return [
            records_by_id[record_id]
            for record_id in record_ids
            if record_id in records_by_id
        ]


def build_in_memory_replay_query_context(
    *,
    storage: InMemoryFormalAuditStorageAdapter,
    manifest_gateway: ManifestGateway,
    formal_gateway: FormalSnapshotGateway,
    dagster_gateway: DagsterRunGateway | None = None,
    graph_gateway: GraphSnapshotGateway | None = None,
) -> ReplayQueryContext:
    """Build a replay query context over rows appended to in-memory storage."""

    return ReplayQueryContext(
        repository=InMemoryReplayRepository(storage),
        manifest_gateway=manifest_gateway,
        formal_gateway=formal_gateway,
        dagster_gateway=dagster_gateway,
        graph_gateway=graph_gateway,
    )


__all__ = [
    "InMemoryReplayRepository",
    "build_in_memory_replay_query_context",
]
