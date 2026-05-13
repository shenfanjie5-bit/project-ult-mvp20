"""Read-only data-platform bindings for real-cycle replay smoke checks."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timezone
from typing import Any, Protocol

from audit_eval.audit.query import ReplayQueryContext
from audit_eval.contracts.audit_record import AuditRecord
from audit_eval.contracts.manifest_draft import CyclePublishManifestDraft
from audit_eval.contracts.replay_record import ReplayRecord


class DataPlatformBindingError(RuntimeError):
    """Raised when data-platform real-cycle reads cannot be bound."""


class _FormalSnapshot(Protocol):
    @property
    def table(self) -> str: ...

    @property
    def snapshot_id(self) -> int: ...


class _CyclePublishManifest(Protocol):
    @property
    def published_cycle_id(self) -> str: ...

    @property
    def published_at(self) -> datetime: ...

    @property
    def formal_table_snapshots(self) -> Mapping[str, _FormalSnapshot]: ...


class _FormalObject(Protocol):
    @property
    def cycle_id(self) -> str: ...

    @property
    def object_type(self) -> str: ...

    @property
    def snapshot_id(self) -> int: ...

    @property
    def payload(self) -> Any: ...


def formal_object_ref(table_identifier: str) -> str:
    """Convert a data-platform formal table key to an audit object ref."""

    prefix = "formal."
    if not table_identifier.startswith(prefix):
        raise DataPlatformBindingError(
            f"formal table identifier must start with {prefix!r}: "
            f"{table_identifier!r}"
        )
    object_ref = table_identifier.removeprefix(prefix)
    if not object_ref:
        raise DataPlatformBindingError(
            f"formal table identifier has no object name: {table_identifier!r}"
        )
    return object_ref


def data_platform_snapshot_ref(table_identifier: str, snapshot_id: int) -> str:
    """Return a stable audit-side ref for a data-platform Iceberg snapshot."""

    object_ref = formal_object_ref(table_identifier)
    if (
        isinstance(snapshot_id, bool)
        or not isinstance(snapshot_id, int)
        or snapshot_id < 1
    ):
        raise DataPlatformBindingError(
            f"snapshot_id must be a positive integer: {snapshot_id!r}"
        )
    return f"data-platform://formal/{object_ref}/snapshots/{snapshot_id}"


def parse_data_platform_snapshot_ref(snapshot_ref: str) -> tuple[str, int]:
    """Parse a snapshot ref emitted by data_platform_snapshot_ref."""

    prefix = "data-platform://formal/"
    marker = "/snapshots/"
    if not snapshot_ref.startswith(prefix) or marker not in snapshot_ref:
        raise DataPlatformBindingError(
            f"unsupported data-platform snapshot ref: {snapshot_ref!r}"
        )
    object_ref, raw_snapshot_id = snapshot_ref.removeprefix(prefix).split(marker, 1)
    if not object_ref or "/" in object_ref:
        raise DataPlatformBindingError(
            f"invalid formal object ref in snapshot ref: {snapshot_ref!r}"
        )
    try:
        snapshot_id = int(raw_snapshot_id)
    except ValueError as exc:
        raise DataPlatformBindingError(
            f"invalid snapshot id in snapshot ref: {snapshot_ref!r}"
        ) from exc
    if snapshot_id < 1:
        raise DataPlatformBindingError(
            f"invalid snapshot id in snapshot ref: {snapshot_ref!r}"
        )
    return object_ref, snapshot_id


class DataPlatformManifestGateway:
    """Read cycle_publish_manifest rows through data-platform's public API."""

    def __init__(
        self,
        load_manifest: Callable[[str], _CyclePublishManifest] | None = None,
    ) -> None:
        self._load_manifest = load_manifest

    def load(self, cycle_id: str) -> CyclePublishManifestDraft:
        manifest = self._load(cycle_id)
        snapshot_refs = {
            formal_object_ref(table_identifier): data_platform_snapshot_ref(
                table_identifier,
                snapshot.snapshot_id,
            )
            for table_identifier, snapshot in manifest.formal_table_snapshots.items()
        }
        return CyclePublishManifestDraft(
            published_cycle_id=manifest.published_cycle_id,
            published_at=manifest.published_at,
            snapshot_refs=snapshot_refs,
        )

    def _load(self, cycle_id: str) -> _CyclePublishManifest:
        if self._load_manifest is not None:
            return self._load_manifest(cycle_id)
        try:
            from data_platform.cycle import get_publish_manifest  # type: ignore[import-not-found]
        except ImportError as exc:
            raise DataPlatformBindingError(
                "data-platform is not importable; install it or set PYTHONPATH"
            ) from exc
        return get_publish_manifest(cycle_id)


class DataPlatformFormalSnapshotGateway:
    """Read formal objects only by manifest-published snapshot refs."""

    def __init__(
        self,
        load_formal_by_snapshot: Callable[[int, str], _FormalObject] | None = None,
    ) -> None:
        self._load_formal_by_snapshot = load_formal_by_snapshot

    def load_snapshot(self, snapshot_ref: str) -> dict[str, Any]:
        object_ref, snapshot_id = parse_data_platform_snapshot_ref(snapshot_ref)
        formal_object = self._load(snapshot_id, object_ref)
        if formal_object.object_type != object_ref:
            raise DataPlatformBindingError(
                "data-platform formal object_type does not match snapshot ref: "
                f"{formal_object.object_type!r} != {object_ref!r}"
            )
        if formal_object.snapshot_id != snapshot_id:
            raise DataPlatformBindingError(
                "data-platform formal snapshot_id does not match snapshot ref: "
                f"{formal_object.snapshot_id!r} != {snapshot_id!r}"
            )
        return {
            "snapshot_ref": snapshot_ref,
            "cycle_id": formal_object.cycle_id,
            "object_type": formal_object.object_type,
            "snapshot_id": formal_object.snapshot_id,
            "row_count": _payload_row_count(formal_object.payload),
            "payload": _payload_records(formal_object.payload),
        }

    def _load(self, snapshot_id: int, object_type: str) -> _FormalObject:
        if self._load_formal_by_snapshot is not None:
            return self._load_formal_by_snapshot(snapshot_id, object_type)
        try:
            from data_platform.serving.formal import get_formal_by_snapshot  # type: ignore[import-not-found]
        except ImportError as exc:
            raise DataPlatformBindingError(
                "data-platform is not importable; install it or set PYTHONPATH"
            ) from exc
        return get_formal_by_snapshot(snapshot_id, object_type)


class RealCycleSmokeRepository:
    """In-memory technical replay records for read-only real-cycle smoke checks."""

    def __init__(
        self,
        *,
        cycle_id: str,
        object_ref: str,
        manifest: CyclePublishManifestDraft,
        created_at: datetime | None = None,
    ) -> None:
        if object_ref not in manifest.snapshot_refs:
            raise DataPlatformBindingError(
                f"manifest for {cycle_id!r} does not publish object_ref "
                f"{object_ref!r}"
            )
        self._cycle_id = cycle_id
        self._object_ref = object_ref
        self._created_at = created_at or datetime.now(timezone.utc)
        self._audit_record = AuditRecord(
            record_id=f"audit-real-cycle-smoke-{cycle_id}-{object_ref}",
            cycle_id=cycle_id,
            layer="L8",
            object_ref=object_ref,
            params_snapshot={
                "binding": "data-platform-published-cycle",
                "manifest_cycle_id": manifest.published_cycle_id,
            },
            llm_lineage={"called": False},
            llm_cost={},
            sanitized_input=None,
            input_hash=None,
            raw_output=None,
            parsed_result=None,
            output_hash=None,
            degradation_flags={
                "real_cycle_query_smoke": True,
                "recommendation_generated": False,
            },
            created_at=self._created_at,
        )
        self._replay_record = ReplayRecord(
            replay_id=f"replay-real-cycle-smoke-{cycle_id}-{object_ref}",
            cycle_id=cycle_id,
            object_ref=object_ref,
            audit_record_ids=[self._audit_record.record_id],
            manifest_cycle_id=manifest.published_cycle_id,
            formal_snapshot_refs=dict(manifest.snapshot_refs),
            graph_snapshot_ref=None,
            dagster_run_id=(
                f"data-platform-published-cycle:{manifest.published_cycle_id}"
            ),
            replay_mode="read_history",
            created_at=self._created_at,
        )

    def get_replay_record(
        self,
        cycle_id: str,
        object_ref: str,
    ) -> ReplayRecord | None:
        if cycle_id == self._cycle_id and object_ref == self._object_ref:
            return self._replay_record
        return None

    def get_audit_records(self, record_ids: Sequence[str]) -> list[AuditRecord]:
        requested = set(record_ids)
        if self._audit_record.record_id in requested:
            return [self._audit_record]
        return []


class RealCycleSmokeDagsterGateway:
    """Technical run summary for a data-platform manifest read smoke."""

    def __init__(self, *, cycle_id: str) -> None:
        self._cycle_id = cycle_id

    def load_summary(self, dagster_run_id: str) -> dict[str, Any]:
        expected_run_id = f"data-platform-published-cycle:{self._cycle_id}"
        if dagster_run_id != expected_run_id:
            raise DataPlatformBindingError(
                f"unexpected real-cycle smoke run id: {dagster_run_id!r}"
            )
        return {
            "run_id": dagster_run_id,
            "cycle_id": self._cycle_id,
            "source": "data-platform-published-cycle",
            "read_only": True,
        }


def build_data_platform_replay_query_context(
    *,
    cycle_id: str,
    object_ref: str,
    manifest_gateway: DataPlatformManifestGateway | None = None,
    formal_gateway: DataPlatformFormalSnapshotGateway | None = None,
) -> ReplayQueryContext:
    """Build a ReplayQueryContext bound to data-platform published snapshots."""

    manifest_reader = manifest_gateway or DataPlatformManifestGateway()
    manifest = manifest_reader.load(cycle_id)
    repository = RealCycleSmokeRepository(
        cycle_id=cycle_id,
        object_ref=object_ref,
        manifest=manifest,
    )
    return ReplayQueryContext(
        repository=repository,
        manifest_gateway=manifest_reader,
        formal_gateway=formal_gateway or DataPlatformFormalSnapshotGateway(),
        dagster_gateway=RealCycleSmokeDagsterGateway(
            cycle_id=manifest.published_cycle_id,
        ),
        graph_gateway=None,
    )


def _payload_row_count(payload: Any) -> int:
    row_count = getattr(payload, "num_rows", None)
    if isinstance(row_count, int):
        return row_count
    if isinstance(payload, Sequence) and not isinstance(
        payload,
        (str, bytes, bytearray),
    ):
        return len(payload)
    return 0


def _payload_records(payload: Any) -> list[dict[str, Any]]:
    if hasattr(payload, "to_pylist"):
        records = payload.to_pylist()
    elif isinstance(payload, Sequence) and not isinstance(
        payload,
        (str, bytes, bytearray),
    ):
        records = list(payload)
    else:
        records = []
    if not all(isinstance(record, Mapping) for record in records):
        raise DataPlatformBindingError("formal snapshot payload must contain objects")
    return [dict(record) for record in records]


__all__ = [
    "DataPlatformBindingError",
    "DataPlatformFormalSnapshotGateway",
    "DataPlatformManifestGateway",
    "RealCycleSmokeDagsterGateway",
    "RealCycleSmokeRepository",
    "build_data_platform_replay_query_context",
    "data_platform_snapshot_ref",
    "formal_object_ref",
    "parse_data_platform_snapshot_ref",
]
