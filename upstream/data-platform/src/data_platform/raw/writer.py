"""Raw Zone artifact writer and reader helpers."""

from __future__ import annotations

import gzip
import hashlib
import json
import os
import re
import uuid
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, TypeAlias
from urllib.parse import unquote, urlparse

import fcntl
import pyarrow as pa  # type: ignore[import-untyped]
import pyarrow.parquet as pq  # type: ignore[import-untyped]


JsonPayload: TypeAlias = dict[str, Any] | list[dict[str, Any]]

_ULID_RE = re.compile(r"^[0-7][0-9A-HJKMNP-TV-Z]{25}$")
_MANIFEST_VERSION = 2
_RAW_MANIFEST_METADATA_FIELDS = (
    "provider",
    "source_interface_id",
    "doc_api",
    "partition_key",
    "request_params_hash",
    "schema_hash",
)


@dataclass(frozen=True, slots=True)
class RawArtifact:
    """Metadata for one Raw Zone artifact."""

    source_id: str
    dataset: str
    partition_date: date
    run_id: str
    path: Path
    row_count: int
    written_at: datetime
    metadata: dict[str, Any] = field(default_factory=dict)


class RawArtifactExists(FileExistsError):
    """Raised when the same Raw Zone artifact already exists."""


class RawZonePathError(ValueError):
    """Raised when Raw Zone paths cross an Iceberg warehouse boundary."""


class RawWriter:
    """Write Raw Zone Parquet and JSON artifacts."""

    def __init__(
        self,
        raw_zone_path: str | Path | None = None,
        *,
        iceberg_warehouse_path: str | Path | None = None,
    ) -> None:
        self.raw_zone_path = _default_raw_zone_path(raw_zone_path)
        self.iceberg_warehouse_path = _default_iceberg_warehouse_path(iceberg_warehouse_path)
        _ensure_not_in_iceberg_warehouse(self.raw_zone_path, self.iceberg_warehouse_path)

    def write_arrow(
        self,
        source_id: str,
        dataset: str,
        partition_date: date,
        run_id: str,
        table: pa.Table,
        *,
        metadata: Mapping[str, Any] | None = None,
        request_params: Mapping[str, Any] | None = None,
    ) -> RawArtifact:
        """Write a pyarrow table to Raw Zone parquet."""

        artifact_path = self._artifact_path(source_id, dataset, partition_date, run_id, "parquet")
        row_count = int(table.num_rows)

        def write_tmp(tmp_path: Path) -> None:
            pq.write_table(table, tmp_path)

        return self._write_artifact(
            source_id=source_id,
            dataset=dataset,
            partition_date=partition_date,
            run_id=run_id,
            artifact_path=artifact_path,
            row_count=row_count,
            metadata=_manifest_metadata(metadata, request_params, dataset=dataset),
            write_tmp=write_tmp,
        )

    def write_json(
        self,
        source_id: str,
        dataset: str,
        partition_date: date,
        run_id: str,
        payload: JsonPayload,
        *,
        metadata: Mapping[str, Any] | None = None,
        request_params: Mapping[str, Any] | None = None,
    ) -> RawArtifact:
        """Write a JSON payload to Raw Zone gzip-compressed JSON."""

        artifact_path = self._artifact_path(source_id, dataset, partition_date, run_id, "json.gz")
        row_count = 1 if isinstance(payload, dict) else len(payload)

        def write_tmp(tmp_path: Path) -> None:
            with gzip.open(tmp_path, "wt", encoding="utf-8") as file:
                json.dump(payload, file, ensure_ascii=False)

        return self._write_artifact(
            source_id=source_id,
            dataset=dataset,
            partition_date=partition_date,
            run_id=run_id,
            artifact_path=artifact_path,
            row_count=row_count,
            metadata=_manifest_metadata(metadata, request_params, dataset=dataset),
            write_tmp=write_tmp,
        )

    def _write_artifact(
        self,
        *,
        source_id: str,
        dataset: str,
        partition_date: date,
        run_id: str,
        artifact_path: Path,
        row_count: int,
        metadata: dict[str, Any],
        write_tmp: Callable[[Path], None],
    ) -> RawArtifact:
        artifact_path.parent.mkdir(parents=True, exist_ok=True)

        tmp_path = artifact_path.with_name(f".{artifact_path.name}.{uuid.uuid4().hex}.tmp")
        try:
            write_tmp(tmp_path)
            with _partition_lock(self._lock_path(artifact_path.parent)):
                self._raise_if_run_id_exists(artifact_path.parent, run_id, artifact_path)
                _materialize_artifact(tmp_path, artifact_path)

                artifact = RawArtifact(
                    source_id=source_id,
                    dataset=dataset,
                    partition_date=partition_date,
                    run_id=run_id,
                    path=artifact_path,
                    row_count=row_count,
                    written_at=datetime.now(tz=UTC),
                    metadata=metadata,
                )
                try:
                    self._write_manifest(artifact)
                except Exception as exc:
                    try:
                        artifact_path.unlink(missing_ok=True)
                    except OSError as cleanup_exc:
                        exc.add_note(
                            f"failed to remove uncommitted raw artifact {artifact_path}: "
                            f"{cleanup_exc}"
                        )
                    raise
                return artifact
        except Exception:
            tmp_path.unlink(missing_ok=True)
            raise

    def _artifact_path(
        self,
        source_id: str,
        dataset: str,
        partition_date: date,
        run_id: str,
        extension: str,
    ) -> Path:
        _validate_path_segment(source_id, "source_id")
        _validate_path_segment(dataset, "dataset")
        _validate_run_id(run_id)

        partition = f"dt={partition_date:%Y%m%d}"
        path = self.raw_zone_path / source_id / dataset / partition / f"{run_id}.{extension}"
        _ensure_path_stays_under(path, self.raw_zone_path)
        _ensure_not_in_iceberg_warehouse(path, self.iceberg_warehouse_path)
        return path

    def _manifest_path(self, partition_path: Path) -> Path:
        return partition_path / "_manifest.json"

    def _lock_path(self, partition_path: Path) -> Path:
        return partition_path / "._manifest.lock"

    def _raise_if_run_id_exists(
        self,
        partition_path: Path,
        run_id: str,
        artifact_path: Path,
    ) -> None:
        self._raise_if_manifest_contains_run_id(partition_path, run_id)
        self._remove_unmanifested_run_artifacts(partition_path, run_id, artifact_path)

    def _remove_unmanifested_run_artifacts(
        self,
        partition_path: Path,
        run_id: str,
        artifact_path: Path,
    ) -> None:
        existing_paths = {artifact_path}
        for existing_path in partition_path.glob(f"{run_id}.*"):
            if existing_path.name.endswith(".tmp"):
                continue
            existing_paths.add(existing_path)

        for existing_path in sorted(existing_paths, key=str):
            if not existing_path.exists():
                continue
            try:
                existing_path.unlink()
            except OSError as exc:
                raise RawArtifactExists(
                    f"uncommitted raw artifact could not be recovered for run_id={run_id!r}: "
                    f"{existing_path}"
                ) from exc

    def _raise_if_manifest_contains_run_id(self, partition_path: Path, run_id: str) -> None:
        manifest_path = self._manifest_path(partition_path)
        if not manifest_path.exists():
            return

        manifest = _read_manifest(manifest_path)
        for artifact in _manifest_artifacts(manifest):
            if artifact.get("run_id") == run_id:
                raise RawArtifactExists(f"raw artifact already exists for run_id={run_id!r}")

    def _write_manifest(self, artifact: RawArtifact) -> None:
        manifest_path = self._manifest_path(artifact.path.parent)
        existing_artifacts: list[dict[str, Any]] = []
        if manifest_path.exists():
            existing_artifacts = _manifest_artifacts(_read_manifest(manifest_path))

        artifact_dict = _artifact_to_dict(artifact)
        artifacts = [*existing_artifacts, artifact_dict]
        artifacts.sort(key=lambda item: str(item["written_at"]))

        manifest = {
            "manifest_version": _MANIFEST_VERSION,
            "source_id": artifact.source_id,
            "dataset": artifact.dataset,
            "partition_date": artifact.partition_date.isoformat(),
            **_manifest_header_metadata(artifact.metadata),
            "artifacts": artifacts,
        }
        tmp_path = manifest_path.with_name(f".{manifest_path.name}.{uuid.uuid4().hex}.tmp")
        try:
            with tmp_path.open("w", encoding="utf-8") as file:
                json.dump(manifest, file, ensure_ascii=False, indent=2, sort_keys=True)
                file.write("\n")
            os.replace(tmp_path, manifest_path)
        except Exception:
            tmp_path.unlink(missing_ok=True)
            raise


class RawReader:
    """Read Raw Zone artifact manifests."""

    def __init__(self, raw_zone_path: str | Path | None = None) -> None:
        self.raw_zone_path = _default_raw_zone_path(raw_zone_path)

    def list_artifacts(
        self,
        source_id: str,
        dataset: str,
        partition_date: date,
    ) -> list[RawArtifact]:
        """Return artifacts for one Raw Zone partition ordered by write time."""

        _validate_path_segment(source_id, "source_id")
        _validate_path_segment(dataset, "dataset")
        partition = f"dt={partition_date:%Y%m%d}"
        partition_path = self.raw_zone_path / source_id / dataset / partition
        _ensure_path_stays_under(partition_path, self.raw_zone_path)

        manifest_path = partition_path / "_manifest.json"
        if not manifest_path.exists():
            return []

        artifacts = [
            _artifact_from_dict(item, raw_zone_root=self.raw_zone_path)
            for item in _manifest_artifacts(_read_manifest(manifest_path))
        ]
        artifacts.sort(key=lambda artifact: artifact.written_at)
        return artifacts


def _default_raw_zone_path(raw_zone_path: str | Path | None) -> Path:
    if raw_zone_path is not None:
        return Path(raw_zone_path).expanduser()

    env_path = os.environ.get("DP_RAW_ZONE_PATH")
    if env_path:
        return Path(env_path).expanduser()

    data_storage_root = os.environ.get("DP_DATA_STORAGE_ROOT_PATH")
    if data_storage_root:
        return Path(data_storage_root).expanduser() / "raw"

    from data_platform.config import get_settings

    return get_settings().raw_zone_path.expanduser()


def _default_iceberg_warehouse_path(
    iceberg_warehouse_path: str | Path | None,
) -> Path | None:
    if iceberg_warehouse_path is not None:
        return Path(iceberg_warehouse_path).expanduser()

    env_path = os.environ.get("DP_ICEBERG_WAREHOUSE_PATH")
    if env_path:
        return Path(env_path).expanduser()

    from data_platform.config import get_settings

    return get_settings().iceberg_warehouse_path.expanduser()


@contextmanager
def _partition_lock(lock_path: Path) -> Iterator[None]:
    with lock_path.open("a+", encoding="utf-8") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def _materialize_artifact(tmp_path: Path, artifact_path: Path) -> None:
    try:
        os.link(tmp_path, artifact_path)
    except FileExistsError as exc:
        raise RawArtifactExists(f"raw artifact already exists: {artifact_path}") from exc
    finally:
        tmp_path.unlink(missing_ok=True)


def _validate_path_segment(value: str, field_name: str) -> None:
    path = Path(value)
    if not value or path.is_absolute() or value in {".", ".."} or len(path.parts) != 1:
        raise ValueError(f"{field_name} must be a single relative path segment")


def _validate_run_id(run_id: str) -> None:
    _validate_path_segment(run_id, "run_id")
    if _is_uuid4(run_id) or _is_ulid(run_id):
        return
    raise ValueError("run_id must be a ULID or UUID4")


def _is_uuid4(value: str) -> bool:
    try:
        parsed = uuid.UUID(value)
    except ValueError:
        return False
    return parsed.version == 4 and value.lower() in {str(parsed), parsed.hex}


def _is_ulid(value: str) -> bool:
    return bool(_ULID_RE.fullmatch(value.upper()))


def _ensure_path_stays_under(path: Path, root: Path) -> None:
    if not _path_stays_under(path, root):
        raise RawZonePathError(f"path escapes raw zone root: {path}")


def _path_stays_under(path: Path, root: Path) -> bool:
    try:
        path.expanduser().resolve(strict=False).relative_to(root.expanduser().resolve(strict=False))
    except ValueError:
        return False
    return True


def _ensure_not_in_iceberg_warehouse(path: Path, iceberg_warehouse_path: Path | None) -> None:
    if iceberg_warehouse_path is None:
        return

    resolved_path = path.expanduser().resolve(strict=False)
    resolved_warehouse = iceberg_warehouse_path.expanduser().resolve(strict=False)
    try:
        resolved_path.relative_to(resolved_warehouse)
    except ValueError:
        return

    raise RawZonePathError("raw zone artifacts must not be written inside Iceberg warehouse")


def _artifact_to_dict(artifact: RawArtifact) -> dict[str, Any]:
    return {
        "source_id": artifact.source_id,
        "dataset": artifact.dataset,
        "partition_date": artifact.partition_date.isoformat(),
        "run_id": artifact.run_id,
        "path": str(artifact.path),
        "row_count": artifact.row_count,
        "written_at": artifact.written_at.isoformat(),
        **artifact.metadata,
    }


def _parse_aware_written_at(value: object) -> datetime:
    """Parse a manifest `written_at` ISO string and force tz-awareness.

    Raw Zone manifests written by `_artifact_to_dict` always emit a
    tz-aware `written_at` (RawArtifact.written_at carries tz). But older
    manifests or manually-edited fixtures may carry a naive ISO string.
    Comparing such a naive datetime to the tz-aware values produced by
    `datetime.now(UTC)` raises TypeError — so we coerce naive → UTC the
    same way `_parse_lock_acquired_at` does in daily_refresh.py.
    """

    parsed = datetime.fromisoformat(str(value))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _artifact_from_dict(
    value: dict[str, Any],
    *,
    raw_zone_root: Path | None = None,
) -> RawArtifact:
    path_ref = str(value["path"])
    path = Path(path_ref) if raw_zone_root is None else _artifact_path_from_ref(
        path_ref,
        raw_zone_root,
    )
    return RawArtifact(
        source_id=str(value["source_id"]),
        dataset=str(value["dataset"]),
        partition_date=date.fromisoformat(str(value["partition_date"])),
        run_id=str(value["run_id"]),
        path=path,
        row_count=int(value["row_count"]),
        written_at=_parse_aware_written_at(value["written_at"]),
        metadata=_metadata_from_manifest_value(value),
    )


def _manifest_metadata(
    metadata: Mapping[str, Any] | None,
    request_params: Mapping[str, Any] | None,
    *,
    dataset: str,
) -> dict[str, Any]:
    raw_metadata = dict(metadata or {})
    if request_params is not None:
        raw_metadata["request_params_hash"] = _request_params_hash(request_params)

    manifest_metadata = {
        field_name: _json_safe(raw_metadata[field_name])
        for field_name in _RAW_MANIFEST_METADATA_FIELDS
        if field_name in raw_metadata and raw_metadata[field_name] is not None
    }
    if "partition_key" in manifest_metadata:
        partition_key = manifest_metadata["partition_key"]
        if isinstance(partition_key, str):
            manifest_metadata["partition_key"] = [partition_key]
        elif isinstance(partition_key, tuple):
            manifest_metadata["partition_key"] = list(partition_key)
    _validate_provider_interface_metadata(manifest_metadata, dataset=dataset)
    return manifest_metadata


def _validate_provider_interface_metadata(
    metadata: Mapping[str, Any],
    *,
    dataset: str,
) -> None:
    provider = metadata.get("provider")
    source_interface_id = metadata.get("source_interface_id")
    doc_api = metadata.get("doc_api")
    if provider is None and source_interface_id is None and doc_api is None:
        return
    if not (provider and source_interface_id and doc_api):
        raise ValueError(
            "raw manifest provider metadata requires provider, source_interface_id, and doc_api",
        )

    provider_name = str(provider)
    if provider_name != "tushare":
        return

    from data_platform.provider_catalog import TUSHARE_INTERFACE_REGISTRY

    interface_id = str(source_interface_id)
    entry = TUSHARE_INTERFACE_REGISTRY.get(interface_id)
    if entry is None:
        raise ValueError(f"unknown Tushare source_interface_id: {interface_id!r}")
    if entry.doc_api != str(doc_api):
        raise ValueError(
            "raw manifest doc_api does not match source_interface_id: "
            f"source_interface_id={interface_id!r}, doc_api={doc_api!r}, "
            f"expected_doc_api={entry.doc_api!r}",
        )
    if entry.raw_dataset != dataset:
        raise ValueError(
            "raw manifest dataset does not match source_interface_id: "
            f"source_interface_id={interface_id!r}, dataset={dataset!r}, "
            f"expected_raw_dataset={entry.raw_dataset!r}",
        )


def _manifest_header_metadata(metadata: Mapping[str, Any]) -> dict[str, Any]:
    return {
        field_name: metadata[field_name]
        for field_name in _RAW_MANIFEST_METADATA_FIELDS
        if field_name in metadata
    }


def _metadata_from_manifest_value(value: Mapping[str, Any]) -> dict[str, Any]:
    return {
        field_name: value[field_name]
        for field_name in _RAW_MANIFEST_METADATA_FIELDS
        if field_name in value
    }


def _request_params_hash(request_params: Mapping[str, Any]) -> str:
    serialized = json.dumps(
        _json_safe(dict(request_params)),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _json_safe(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, tuple | list):
        return [_json_safe(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, date | datetime):
        return value.isoformat()
    if isinstance(value, str | int | float | bool) or value is None:
        return value
    return str(value)


def _artifact_path_from_ref(ref: str, raw_zone_root: Path) -> Path:
    if not ref or ref != ref.strip():
        msg = f"raw artifact ref must be a non-empty path: {ref!r}"
        raise ValueError(msg)

    parsed = urlparse(ref)
    if parsed.scheme and parsed.scheme != "file":
        msg = f"raw artifact ref uses unsupported scheme: {parsed.scheme!r}"
        raise ValueError(msg)
    if parsed.scheme == "file":
        if parsed.netloc:
            msg = f"raw artifact file ref must not include a network location: {ref!r}"
            raise ValueError(msg)
        path = Path(unquote(parsed.path))
    else:
        path = Path(ref)

    if any(part in {"", ".", ".."} for part in path.parts):
        msg = f"raw artifact ref must not contain traversal segments: {ref!r}"
        raise ValueError(msg)

    if not path.is_absolute() and not _path_stays_under(path, raw_zone_root):
        path = raw_zone_root / path

    _ensure_path_stays_under(path, raw_zone_root)
    if path.exists() and not path.is_file():
        msg = f"raw artifact ref must point to a file when it exists: {ref!r}"
        raise ValueError(msg)
    return path


def _read_manifest(manifest_path: Path) -> dict[str, Any]:
    with manifest_path.open(encoding="utf-8") as file:
        manifest = json.load(file)
    if not isinstance(manifest, dict):
        raise ValueError(f"raw manifest must be a JSON object: {manifest_path}")
    return manifest


def _manifest_artifacts(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    artifacts = manifest.get("artifacts")
    if isinstance(artifacts, list):
        validated_artifacts: list[dict[str, Any]] = []
        for index, artifact in enumerate(artifacts):
            if not isinstance(artifact, dict):
                msg = f"raw manifest artifact at index {index} must be a JSON object"
                raise ValueError(msg)
            validated_artifacts.append(artifact)
        return validated_artifacts
    if "run_id" in manifest:
        return [manifest]
    return []


__all__ = [
    "RawArtifact",
    "RawArtifactExists",
    "RawReader",
    "RawWriter",
    "RawZonePathError",
]
