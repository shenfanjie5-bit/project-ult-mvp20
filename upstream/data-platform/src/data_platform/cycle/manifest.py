"""Formal publish manifest metadata API."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final

from data_platform.cycle.models import CYCLE_METADATA_TABLE, _cycle_date_from_id
from data_platform.cycle.repository import (
    InvalidCycleTransition,
    _create_engine,
    _text,
)
from data_platform.formal_registry import (
    REQUIRED_FORMAL_OBJECT_NAMES,
    validate_formal_object_name,
)

CYCLE_PUBLISH_MANIFEST_TABLE: Final[str] = "data_platform.cycle_publish_manifest"
_FORMAL_NAMESPACE_PREFIX: Final[str] = "formal."
FORMAL_RECOMMENDATION_SNAPSHOT: Final[str] = "formal.recommendation_snapshot"


class PublishManifestNotFound(LookupError):
    """Raised when a publish manifest or its cycle does not exist."""

    def __init__(self, cycle_id: str | None = None) -> None:
        self.cycle_id = cycle_id
        if cycle_id is None:
            super().__init__("publish manifest not found")
        else:
            super().__init__(f"publish manifest not found: {cycle_id}")


class ManifestAlreadyPublished(RuntimeError):
    """Raised when a cycle already has a publish manifest."""

    def __init__(self, cycle_id: str) -> None:
        self.cycle_id = cycle_id
        super().__init__(f"cycle already has a publish manifest: {cycle_id}")


class InvalidFormalSnapshotManifest(ValueError):
    """Raised when formal_table_snapshots violates the manifest contract."""


@dataclass(frozen=True, slots=True)
class FormalTableSnapshot:
    """One formal Iceberg table snapshot pinned by a published cycle."""

    table: str
    snapshot_id: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "table", _validate_formal_table_key(self.table))
        object.__setattr__(self, "snapshot_id", _validate_snapshot_id(self.snapshot_id))


@dataclass(frozen=True, slots=True)
class CyclePublishManifest:
    """A row from data_platform.cycle_publish_manifest."""

    published_cycle_id: str
    published_at: datetime
    formal_table_snapshots: dict[str, FormalTableSnapshot]

    def __post_init__(self) -> None:
        _cycle_date_from_id(self.published_cycle_id)
        if not isinstance(self.published_at, datetime):
            msg = "published_at must be a datetime"
            raise TypeError(msg)
        object.__setattr__(
            self,
            "formal_table_snapshots",
            _normalize_snapshot_manifest(self.formal_table_snapshots),
        )


def publish_manifest(
    cycle_id: str,
    formal_table_snapshots: Mapping[str, int | Mapping[str, int] | FormalTableSnapshot],
    *,
    recommendation_provenance: object | None = None,
) -> CyclePublishManifest:
    """Persist one cycle publish manifest and mark the cycle as published."""

    _cycle_date_from_id(cycle_id)
    snapshots = _normalize_snapshot_manifest(formal_table_snapshots)
    _preflight_recommendation_snapshot_publish(
        cycle_id=cycle_id,
        snapshots=snapshots,
        recommendation_provenance=recommendation_provenance,
    )
    payload = json.dumps(_snapshot_payload(snapshots), allow_nan=False, sort_keys=True)

    from sqlalchemy.exc import IntegrityError

    engine = _create_engine()
    try:
        with engine.begin() as connection:
            cycle = (
                connection.execute(
                    _text(
                        f"""
                    SELECT cycle_id, status
                    FROM {CYCLE_METADATA_TABLE}
                    WHERE cycle_id = :cycle_id
                    FOR UPDATE
                    """
                    ),
                    {"cycle_id": cycle_id},
                )
                .mappings()
                .one_or_none()
            )
            if cycle is None:
                raise PublishManifestNotFound(cycle_id)

            existing = (
                connection.execute(
                    _text(
                        f"""
                    SELECT published_cycle_id
                    FROM {CYCLE_PUBLISH_MANIFEST_TABLE}
                    WHERE published_cycle_id = :cycle_id
                    """
                    ),
                    {"cycle_id": cycle_id},
                )
                .mappings()
                .one_or_none()
            )
            if existing is not None:
                raise ManifestAlreadyPublished(cycle_id)

            current_status = str(cycle["status"])
            if current_status != "phase3":
                raise InvalidCycleTransition(cycle_id, current_status, "published")

            try:
                row = (
                    connection.execute(
                        _text(
                            f"""
                        INSERT INTO {CYCLE_PUBLISH_MANIFEST_TABLE} (
                            published_cycle_id,
                            formal_table_snapshots
                        )
                        VALUES (
                            :cycle_id,
                            CAST(:formal_table_snapshots AS jsonb)
                        )
                        RETURNING
                            published_cycle_id,
                            published_at,
                            formal_table_snapshots
                        """
                        ),
                        {
                            "cycle_id": cycle_id,
                            "formal_table_snapshots": payload,
                        },
                    )
                    .mappings()
                    .one()
                )
            except IntegrityError as exc:
                if _is_unique_violation(exc):
                    raise ManifestAlreadyPublished(cycle_id) from exc
                raise

            connection.execute(
                _text(
                    f"""
                    UPDATE {CYCLE_METADATA_TABLE}
                    SET status = CAST('published' AS data_platform.cycle_status),
                        updated_at = now()
                    WHERE cycle_id = :cycle_id
                    """
                ),
                {"cycle_id": cycle_id},
            )
            return _manifest_from_row(row)
    finally:
        engine.dispose()


def get_publish_manifest(cycle_id: str) -> CyclePublishManifest:
    """Return the publish manifest for one cycle."""

    _cycle_date_from_id(cycle_id)
    engine = _create_engine()
    try:
        with engine.connect() as connection:
            row = (
                connection.execute(
                    _text(
                        f"""
                    SELECT
                        published_cycle_id,
                        published_at,
                        formal_table_snapshots
                    FROM {CYCLE_PUBLISH_MANIFEST_TABLE}
                    WHERE published_cycle_id = :cycle_id
                    """
                    ),
                    {"cycle_id": cycle_id},
                )
                .mappings()
                .one_or_none()
            )
            if row is None:
                raise PublishManifestNotFound(cycle_id)
            return _manifest_from_row(row)
    finally:
        engine.dispose()


def get_latest_publish_manifest() -> CyclePublishManifest:
    """Return the newest publish manifest from PostgreSQL metadata."""

    engine = _create_engine()
    try:
        with engine.connect() as connection:
            row = (
                connection.execute(
                    _text(
                        f"""
                    SELECT
                        published_cycle_id,
                        published_at,
                        formal_table_snapshots
                    FROM {CYCLE_PUBLISH_MANIFEST_TABLE}
                    ORDER BY published_at DESC, published_cycle_id DESC
                    LIMIT 1
                    """
                    )
                )
                .mappings()
                .one_or_none()
            )
            if row is None:
                raise PublishManifestNotFound()
            return _manifest_from_row(row)
    finally:
        engine.dispose()


def get_publish_manifest_for_snapshot(
    snapshot_id: int,
    table_identifier: str,
) -> CyclePublishManifest:
    """Return the newest manifest that publishes table_identifier at snapshot_id."""

    validated_snapshot_id = validate_snapshot_id(snapshot_id)
    validated_table_identifier = _validate_formal_table_key(table_identifier)
    engine = _create_engine()
    try:
        with engine.connect() as connection:
            row = (
                connection.execute(
                    _text(
                        f"""
                    SELECT
                        published_cycle_id,
                        published_at,
                        formal_table_snapshots
                    FROM {CYCLE_PUBLISH_MANIFEST_TABLE}
                    WHERE jsonb_extract_path_text(
                        formal_table_snapshots,
                        :table_identifier,
                        'snapshot_id'
                    ) = :snapshot_id
                    ORDER BY published_at DESC, published_cycle_id DESC
                    LIMIT 1
                    """
                    ),
                    {
                        "table_identifier": validated_table_identifier,
                        "snapshot_id": str(validated_snapshot_id),
                    },
                )
                .mappings()
                .one_or_none()
            )
            if row is None:
                raise PublishManifestNotFound()
            return _manifest_from_row(row)
    finally:
        engine.dispose()


def _normalize_snapshot_manifest(
    formal_table_snapshots: Mapping[str, object],
) -> dict[str, FormalTableSnapshot]:
    if not isinstance(formal_table_snapshots, Mapping):
        msg = "formal_table_snapshots must be a non-empty mapping"
        raise InvalidFormalSnapshotManifest(msg)
    if not formal_table_snapshots:
        msg = "formal_table_snapshots must not be empty"
        raise InvalidFormalSnapshotManifest(msg)

    snapshots = {
        _validate_formal_table_key(table): _coerce_snapshot(table, value)
        for table, value in formal_table_snapshots.items()
    }
    _require_formal_snapshot_keys(snapshots)
    return snapshots


def _coerce_snapshot(table: object, value: object) -> FormalTableSnapshot:
    validated_table = _validate_formal_table_key(table)
    if isinstance(value, FormalTableSnapshot):
        if value.table != validated_table:
            msg = (
                "FormalTableSnapshot.table must match its manifest key: "
                f"{value.table!r} != {validated_table!r}"
            )
            raise InvalidFormalSnapshotManifest(msg)
        return value

    if isinstance(value, Mapping):
        if "snapshot_id" not in value:
            msg = f"formal snapshot entry must include snapshot_id: {validated_table!r}"
            raise InvalidFormalSnapshotManifest(msg)
        return FormalTableSnapshot(
            table=validated_table,
            snapshot_id=_validate_snapshot_id(value["snapshot_id"]),
        )

    return FormalTableSnapshot(
        table=validated_table,
        snapshot_id=_validate_snapshot_id(value),
    )


def _validate_formal_table_key(table: object) -> str:
    if not isinstance(table, str):
        msg = f"formal table key must be a string: {table!r}"
        raise InvalidFormalSnapshotManifest(msg)
    if table != table.strip():
        msg = f"formal table key must not include surrounding whitespace: {table!r}"
        raise InvalidFormalSnapshotManifest(msg)
    if not table.startswith(_FORMAL_NAMESPACE_PREFIX):
        msg = f"formal table key must start with 'formal.': {table!r}"
        raise InvalidFormalSnapshotManifest(msg)
    if any(part == "" for part in table.split(".")):
        msg = f"formal table key must not contain empty namespace parts: {table!r}"
        raise InvalidFormalSnapshotManifest(msg)
    object_name = table.removeprefix(_FORMAL_NAMESPACE_PREFIX)
    try:
        validate_formal_object_name(object_name)
    except ValueError as exc:
        raise InvalidFormalSnapshotManifest(str(exc)) from exc
    return table


def _require_formal_snapshot_keys(
    snapshots: Mapping[str, FormalTableSnapshot],
) -> None:
    required_keys = {
        f"{_FORMAL_NAMESPACE_PREFIX}{name}"
        for name in REQUIRED_FORMAL_OBJECT_NAMES
    }
    missing = sorted(required_keys - set(snapshots))
    if missing:
        msg = f"formal_table_snapshots missing required keys: {missing}"
        raise InvalidFormalSnapshotManifest(msg)


def _preflight_recommendation_snapshot_publish(
    *,
    cycle_id: str,
    snapshots: Mapping[str, FormalTableSnapshot],
    recommendation_provenance: object | None,
) -> None:
    from data_platform.cycle.recommendation_provenance import (
        preflight_recommendation_snapshot_publish,
    )

    preflight_recommendation_snapshot_publish(
        cycle_id=cycle_id,
        recommendation_snapshot=snapshots[FORMAL_RECOMMENDATION_SNAPSHOT],
        provenance=recommendation_provenance,
    )


def validate_snapshot_id(snapshot_id: object) -> int:
    """Validate a formal table snapshot id from API or manifest input."""

    if isinstance(snapshot_id, bool) or not isinstance(snapshot_id, int):
        msg = f"snapshot_id must be a positive integer: {snapshot_id!r}"
        raise InvalidFormalSnapshotManifest(msg)
    if snapshot_id < 1:
        msg = f"snapshot_id must be a positive integer: {snapshot_id!r}"
        raise InvalidFormalSnapshotManifest(msg)
    return snapshot_id


def _validate_snapshot_id(snapshot_id: object) -> int:
    return validate_snapshot_id(snapshot_id)


def _snapshot_payload(
    snapshots: Mapping[str, FormalTableSnapshot],
) -> dict[str, dict[str, int]]:
    return {table: {"snapshot_id": snapshot.snapshot_id} for table, snapshot in snapshots.items()}


def _manifest_from_row(row: Mapping[str, Any]) -> CyclePublishManifest:
    raw_snapshots = row["formal_table_snapshots"]
    if isinstance(raw_snapshots, str):
        try:
            raw_snapshots = json.loads(raw_snapshots)
        except json.JSONDecodeError as exc:
            msg = "stored formal_table_snapshots must be valid JSON"
            raise InvalidFormalSnapshotManifest(msg) from exc

    if not isinstance(raw_snapshots, Mapping):
        msg = "stored formal_table_snapshots must be a JSON object"
        raise InvalidFormalSnapshotManifest(msg)

    return CyclePublishManifest(
        published_cycle_id=str(row["published_cycle_id"]),
        published_at=row["published_at"],
        formal_table_snapshots=_normalize_snapshot_manifest(raw_snapshots),
    )


def _is_unique_violation(exc: Exception) -> bool:
    original = getattr(exc, "orig", None)
    sqlstate = getattr(original, "sqlstate", None)
    if sqlstate is None:
        diagnostic = getattr(original, "diag", None)
        sqlstate = getattr(diagnostic, "sqlstate", None)
    return sqlstate == "23505"


__all__ = [
    "CYCLE_PUBLISH_MANIFEST_TABLE",
    "CyclePublishManifest",
    "FORMAL_RECOMMENDATION_SNAPSHOT",
    "FormalTableSnapshot",
    "InvalidFormalSnapshotManifest",
    "ManifestAlreadyPublished",
    "PublishManifestNotFound",
    "get_publish_manifest_for_snapshot",
    "get_latest_publish_manifest",
    "get_publish_manifest",
    "publish_manifest",
    "validate_snapshot_id",
]
