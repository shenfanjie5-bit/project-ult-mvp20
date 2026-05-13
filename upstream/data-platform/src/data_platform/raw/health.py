"""Raw Zone directory health checks."""

from __future__ import annotations

import gzip
import json
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Literal, Mapping

from data_platform.raw.writer import (
    RawArtifact,
    RawReader,
    _read_manifest,
    _validate_path_segment,
    _validate_run_id,
)


IssueSeverity = Literal["error", "warning"]

_PARTITION_RE = re.compile(r"^dt=(?P<partition>\d{8})$")
_ARTIFACT_EXTENSIONS = (".parquet", ".json.gz")
_MANIFEST_ARTIFACT_FIELD_TYPES = {
    "source_id": str,
    "dataset": str,
    "partition_date": str,
    "run_id": str,
    "path": str,
    "row_count": int,
    "written_at": str,
}
_OPTIONAL_MANIFEST_FIELD_TYPES: dict[str, type[Any]] = {
    "manifest_version": int,
    "provider": str,
    "source_interface_id": str,
    "doc_api": str,
    "partition_key": list,
    "request_params_hash": str,
    "schema_hash": str,
}
_OPTIONAL_ARTIFACT_FIELD_TYPES: dict[str, type[Any]] = {
    "provider": str,
    "source_interface_id": str,
    "doc_api": str,
    "partition_key": list,
    "request_params_hash": str,
    "schema_hash": str,
}


@dataclass(frozen=True)
class RawHealthIssue:
    """One Raw Zone health check finding."""

    severity: IssueSeverity
    path: Path
    code: str
    message: str


@dataclass(frozen=True)
class RawHealthReport:
    """Raw Zone health check result."""

    root: Path
    checked_artifacts: int
    issues: list[RawHealthIssue]

    @property
    def ok(self) -> bool:
        """Return true when no error-severity findings were detected."""

        return not any(issue.severity == "error" for issue in self.issues)


def check_raw_zone(
    root: str | Path | None = None,
    *,
    source_id: str | None = None,
    dataset: str | None = None,
    partition_date: date | None = None,
    deep: bool = False,
) -> RawHealthReport:
    """Scan Raw Zone artifacts and manifests for contract violations."""

    raw_root = _default_root(root)
    issues: list[RawHealthIssue] = []

    _validate_optional_filter(source_id, "source_id", raw_root, issues)
    _validate_optional_filter(dataset, "dataset", raw_root, issues)
    if issues:
        return RawHealthReport(root=raw_root, checked_artifacts=0, issues=issues)

    if not raw_root.exists():
        issues.append(
            RawHealthIssue(
                severity="error",
                path=raw_root,
                code="root_missing",
                message="Raw Zone root does not exist",
            )
        )
        return RawHealthReport(root=raw_root, checked_artifacts=0, issues=issues)

    if not raw_root.is_dir():
        issues.append(
            RawHealthIssue(
                severity="error",
                path=raw_root,
                code="root_not_directory",
                message="Raw Zone root is not a directory",
            )
        )
        return RawHealthReport(root=raw_root, checked_artifacts=0, issues=issues)

    checked_artifacts = 0
    for partition in _iter_partitions(raw_root, source_id, dataset, partition_date, issues):
        checked_artifacts += _check_partition(
            raw_root=raw_root,
            source_id=partition.source_id,
            dataset=partition.dataset,
            partition_date=partition.partition_date,
            partition_path=partition.path,
            deep=deep,
            issues=issues,
        )

    return RawHealthReport(root=raw_root, checked_artifacts=checked_artifacts, issues=issues)


@dataclass(frozen=True)
class _RawPartition:
    source_id: str
    dataset: str
    partition_date: date
    path: Path


def _default_root(root: str | Path | None) -> Path:
    if root is not None:
        return Path(root).expanduser()

    from data_platform.config import get_settings

    return get_settings().raw_zone_path.expanduser()


def _validate_optional_filter(
    value: str | None,
    field_name: str,
    root: Path,
    issues: list[RawHealthIssue],
) -> None:
    if value is None:
        return
    try:
        _validate_path_segment(value, field_name)
    except ValueError as exc:
        issues.append(
            RawHealthIssue(
                severity="error",
                path=root,
                code="invalid_filter",
                message=str(exc),
            )
        )


def _iter_partitions(
    root: Path,
    source_id: str | None,
    dataset: str | None,
    partition_date: date | None,
    issues: list[RawHealthIssue],
) -> list[_RawPartition]:
    partitions: list[_RawPartition] = []
    for source_path in _iter_dirs(root, source_id):
        source_name = source_path.name
        for dataset_path in _iter_dirs(source_path, dataset):
            dataset_name = dataset_path.name
            if partition_date is not None:
                partition_path = dataset_path / _partition_dir_name(partition_date)
                if partition_path.exists() and partition_path.is_dir():
                    partitions.append(
                        _RawPartition(source_name, dataset_name, partition_date, partition_path)
                    )
                continue

            for partition_path in sorted(dataset_path.iterdir(), key=lambda path: path.name):
                if not partition_path.is_dir():
                    continue
                parsed_partition_date = _parse_partition_dir(partition_path, issues)
                if parsed_partition_date is None:
                    continue
                partitions.append(
                    _RawPartition(
                        source_name,
                        dataset_name,
                        parsed_partition_date,
                        partition_path,
                    )
                )
    return partitions


def _iter_dirs(parent: Path, requested_name: str | None) -> list[Path]:
    if requested_name is not None:
        path = parent / requested_name
        return [path] if path.exists() and path.is_dir() else []
    return sorted((path for path in parent.iterdir() if path.is_dir()), key=lambda path: path.name)


def _parse_partition_dir(
    partition_path: Path,
    issues: list[RawHealthIssue],
) -> date | None:
    match = _PARTITION_RE.fullmatch(partition_path.name)
    if match is None:
        issues.append(
            RawHealthIssue(
                severity="error",
                path=partition_path,
                code="invalid_partition_dir",
                message="Raw partition directories must match dt=YYYYMMDD",
            )
        )
        return None

    partition_value = match.group("partition")
    try:
        return date(
            int(partition_value[0:4]),
            int(partition_value[4:6]),
            int(partition_value[6:8]),
        )
    except ValueError:
        issues.append(
            RawHealthIssue(
                severity="error",
                path=partition_path,
                code="invalid_partition_dir",
                message="Raw partition directory contains an invalid calendar date",
            )
        )
        return None


def _check_partition(
    *,
    raw_root: Path,
    source_id: str,
    dataset: str,
    partition_date: date,
    partition_path: Path,
    deep: bool,
    issues: list[RawHealthIssue],
) -> int:
    manifest_path = partition_path / "_manifest.json"
    artifacts: list[RawArtifact] = []
    listed_paths: set[Path] = set()

    if manifest_path.exists():
        manifest = _read_partition_manifest(manifest_path, issues)
        if manifest is not None:
            _check_manifest_header(manifest, source_id, dataset, partition_date, manifest_path, issues)
            if _check_manifest_artifact_entries(manifest, manifest_path, issues):
                artifacts = _read_partition_artifacts(
                    raw_root,
                    source_id,
                    dataset,
                    partition_date,
                    manifest_path,
                    issues,
                )

    _check_duplicate_run_ids(artifacts, issues)
    for artifact in artifacts:
        listed_path = _check_artifact(
            raw_root=raw_root,
            partition_path=partition_path,
            artifact=artifact,
            expected_source_id=source_id,
            expected_dataset=dataset,
            expected_partition_date=partition_date,
            deep=deep,
            issues=issues,
        )
        if listed_path is not None:
            listed_paths.add(listed_path)

    _check_orphan_artifacts(partition_path, listed_paths, issues)
    return len(artifacts)


def _read_partition_manifest(
    manifest_path: Path,
    issues: list[RawHealthIssue],
) -> dict[str, Any] | None:
    try:
        manifest = _read_manifest(manifest_path)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        issues.append(
            RawHealthIssue(
                severity="error",
                path=manifest_path,
                code="manifest_parse_error",
                message=f"Raw manifest could not be parsed: {exc}",
            )
        )
        return None

    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list):
        issues.append(
            RawHealthIssue(
                severity="error",
                path=manifest_path,
                code="manifest_artifacts_invalid",
                message="Raw manifest must contain an artifacts list",
            )
        )
    return manifest


def _check_manifest_header(
    manifest: dict[str, Any],
    source_id: str,
    dataset: str,
    partition_date: date,
    manifest_path: Path,
    issues: list[RawHealthIssue],
) -> None:
    expected_values = {
        "source_id": source_id,
        "dataset": dataset,
        "partition_date": partition_date.isoformat(),
    }
    for field_name, expected_value in expected_values.items():
        actual_value = manifest.get(field_name)
        if actual_value == expected_value:
            continue
        issues.append(
            RawHealthIssue(
                severity="error",
                path=manifest_path,
                code="manifest_field_mismatch",
                message=(
                    f"Raw manifest field {field_name!r} must be {expected_value!r}; "
                    f"got {actual_value!r}"
                ),
            )
        )
    _check_optional_fields(manifest, _OPTIONAL_MANIFEST_FIELD_TYPES, manifest_path, issues)


def _check_manifest_artifact_entries(
    manifest: dict[str, Any],
    manifest_path: Path,
    issues: list[RawHealthIssue],
) -> bool:
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list):
        return False

    valid = True
    for index, artifact in enumerate(artifacts):
        if not isinstance(artifact, dict):
            issues.append(
                RawHealthIssue(
                    severity="error",
                    path=manifest_path,
                    code="manifest_artifact_invalid",
                    message=f"Raw manifest artifacts[{index}] must be a JSON object",
                )
            )
            valid = False
            continue

        for field_name, field_type in _MANIFEST_ARTIFACT_FIELD_TYPES.items():
            value = artifact.get(field_name)
            if isinstance(value, field_type) and not (
                field_name == "row_count" and isinstance(value, bool)
            ):
                continue
            issues.append(
                RawHealthIssue(
                    severity="error",
                    path=manifest_path,
                    code="manifest_artifact_invalid",
                    message=(
                        f"Raw manifest artifacts[{index}].{field_name} must be "
                        f"{field_type.__name__}"
                    ),
                )
            )
            valid = False
        _check_optional_fields(
            artifact,
            _OPTIONAL_ARTIFACT_FIELD_TYPES,
            manifest_path,
            issues,
            prefix=f"artifacts[{index}].",
        )
    return valid


def _check_optional_fields(
    value: dict[str, Any],
    field_types: Mapping[str, type[Any]],
    path: Path,
    issues: list[RawHealthIssue],
    *,
    prefix: str = "",
) -> None:
    for field_name, field_type in field_types.items():
        if field_name not in value:
            continue
        field_value = value[field_name]
        if isinstance(field_value, field_type) and not (
            field_type is int and isinstance(field_value, bool)
        ):
            continue
        issues.append(
            RawHealthIssue(
                severity="error",
                path=path,
                code="manifest_artifact_invalid",
                message=(
                    f"Raw manifest {prefix}{field_name} must be "
                    f"{field_type.__name__}"
                ),
            )
        )


def _read_partition_artifacts(
    raw_root: Path,
    source_id: str,
    dataset: str,
    partition_date: date,
    manifest_path: Path,
    issues: list[RawHealthIssue],
) -> list[RawArtifact]:
    try:
        return RawReader(raw_root).list_artifacts(source_id, dataset, partition_date)
    except (KeyError, TypeError, ValueError) as exc:
        issues.append(
            RawHealthIssue(
                severity="error",
                path=manifest_path,
                code="manifest_parse_error",
                message=f"Raw manifest artifacts could not be parsed: {exc}",
            )
        )
        return []


def _check_duplicate_run_ids(
    artifacts: list[RawArtifact],
    issues: list[RawHealthIssue],
) -> None:
    seen: dict[str, RawArtifact] = {}
    for artifact in artifacts:
        previous = seen.get(artifact.run_id)
        if previous is None:
            seen[artifact.run_id] = artifact
            continue
        issues.append(
            RawHealthIssue(
                severity="error",
                path=artifact.path,
                code="duplicate_run_id",
                message=(
                    f"Raw manifest repeats run_id {artifact.run_id!r}; "
                    f"first path was {previous.path}"
                ),
            )
        )


def _check_artifact(
    *,
    raw_root: Path,
    partition_path: Path,
    artifact: RawArtifact,
    expected_source_id: str,
    expected_dataset: str,
    expected_partition_date: date,
    deep: bool,
    issues: list[RawHealthIssue],
) -> Path | None:
    artifact_path = _resolve_artifact_path(raw_root, artifact.path, issues)
    if artifact_path is None:
        return None

    _check_artifact_fields(
        artifact,
        expected_source_id,
        expected_dataset,
        expected_partition_date,
        artifact_path,
        issues,
    )
    extension = _artifact_extension(artifact_path)
    expected_name = None if extension is None else f"{artifact.run_id}{extension}"
    if extension is None or artifact_path.name != expected_name:
        issues.append(
            RawHealthIssue(
                severity="error",
                path=artifact_path,
                code="artifact_path_mismatch",
                message="Manifest artifact path must end with <run_id>.parquet or <run_id>.json.gz",
            )
        )

    if _resolve_path(artifact_path.parent) != _resolve_path(partition_path):
        issues.append(
            RawHealthIssue(
                severity="error",
                path=artifact_path,
                code="artifact_path_mismatch",
                message="Manifest artifact path must stay in its partition directory",
            )
        )

    if not artifact_path.exists():
        issues.append(
            RawHealthIssue(
                severity="error",
                path=artifact_path,
                code="artifact_missing",
                message="Manifest references an artifact file that does not exist",
            )
        )
        return artifact_path

    if not artifact_path.is_file():
        issues.append(
            RawHealthIssue(
                severity="error",
                path=artifact_path,
                code="artifact_missing",
                message="Manifest artifact path is not a regular file",
            )
        )
        return artifact_path

    if deep and extension is not None:
        _check_deep_row_count(artifact_path, extension, artifact.row_count, issues)
    return artifact_path


def _resolve_artifact_path(
    raw_root: Path,
    artifact_path: Path,
    issues: list[RawHealthIssue],
) -> Path | None:
    path = artifact_path.expanduser()
    if not path.is_absolute():
        if not _path_is_under(path, raw_root):
            path = raw_root / path
    if not _path_is_under(path, raw_root):
        issues.append(
            RawHealthIssue(
                severity="error",
                path=path,
                code="artifact_path_escaped_root",
                message="Manifest artifact path escapes the Raw Zone root",
            )
        )
        return None
    return path


def _check_artifact_fields(
    artifact: RawArtifact,
    expected_source_id: str,
    expected_dataset: str,
    expected_partition_date: date,
    artifact_path: Path,
    issues: list[RawHealthIssue],
) -> None:
    field_values = {
        "source_id": (artifact.source_id, expected_source_id),
        "dataset": (artifact.dataset, expected_dataset),
        "partition_date": (artifact.partition_date, expected_partition_date),
    }
    for field_name, (actual_value, expected_value) in field_values.items():
        if actual_value == expected_value:
            continue
        issues.append(
            RawHealthIssue(
                severity="error",
                path=artifact_path,
                code="artifact_field_mismatch",
                message=(
                    f"Raw artifact field {field_name!r} must be {expected_value!r}; "
                    f"got {actual_value!r}"
                ),
            )
        )

    try:
        _validate_run_id(artifact.run_id)
    except ValueError as exc:
        issues.append(
            RawHealthIssue(
                severity="error",
                path=artifact_path,
                code="invalid_run_id",
                message=str(exc),
            )
        )


def _check_deep_row_count(
    artifact_path: Path,
    extension: str,
    expected_row_count: int,
    issues: list[RawHealthIssue],
) -> None:
    try:
        actual_row_count = _read_row_count(artifact_path, extension)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        issues.append(
            RawHealthIssue(
                severity="error",
                path=artifact_path,
                code="artifact_read_error",
                message=f"Artifact row count could not be read: {exc}",
            )
        )
        return

    if actual_row_count != expected_row_count:
        issues.append(
            RawHealthIssue(
                severity="error",
                path=artifact_path,
                code="row_count_mismatch",
                message=(
                    f"Manifest row_count is {expected_row_count}; "
                    f"artifact contains {actual_row_count} rows"
                ),
            )
        )


def _read_row_count(artifact_path: Path, extension: str) -> int:
    if extension == ".parquet":
        import pyarrow.parquet as pq  # type: ignore[import-untyped]

        metadata = pq.read_metadata(artifact_path)
        return int(metadata.num_rows)

    with gzip.open(artifact_path, "rt", encoding="utf-8") as file:
        payload = json.load(file)
    if isinstance(payload, list):
        return len(payload)
    if isinstance(payload, dict):
        return 1
    raise ValueError("Raw JSON artifact must contain a JSON object or list of objects")


def _check_orphan_artifacts(
    partition_path: Path,
    listed_paths: set[Path],
    issues: list[RawHealthIssue],
) -> None:
    resolved_listed_paths = {_resolve_path(path) for path in listed_paths}
    for artifact_path in sorted(partition_path.iterdir(), key=lambda path: path.name):
        if not artifact_path.is_file() or _artifact_extension(artifact_path) is None:
            continue
        if _resolve_path(artifact_path) in resolved_listed_paths:
            continue
        issues.append(
            RawHealthIssue(
                severity="error",
                path=artifact_path,
                code="orphan_artifact",
                message="Raw artifact file is not listed in _manifest.json",
            )
        )


def _artifact_extension(path: Path) -> str | None:
    for extension in _ARTIFACT_EXTENSIONS:
        if path.name.endswith(extension):
            return extension
    return None


def _partition_dir_name(partition_date: date) -> str:
    return f"dt={partition_date:%Y%m%d}"


def _path_is_under(path: Path, root: Path) -> bool:
    try:
        _resolve_path(path).relative_to(_resolve_path(root))
    except ValueError:
        return False
    return True


def _resolve_path(path: Path) -> Path:
    return path.expanduser().resolve(strict=False)


__all__ = [
    "RawHealthIssue",
    "RawHealthReport",
    "check_raw_zone",
]
