from __future__ import annotations

import gzip
import hashlib
import json
import os
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

pa = pytest.importorskip("pyarrow")
pq = pytest.importorskip("pyarrow.parquet")

from data_platform.raw import RawArtifactExists, RawReader, RawWriter, RawZonePathError  # noqa: E402


PARTITION_DATE = date(2026, 4, 15)


@pytest.fixture
def source_id() -> str:
    return f"source-{uuid.uuid4().hex}"


@pytest.fixture
def raw_zone_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    env_path = os.environ.get("DP_RAW_ZONE_PATH")
    path = Path(env_path) if env_path else tmp_path / "raw"
    if not env_path:
        monkeypatch.setenv("DP_RAW_ZONE_PATH", str(path))
    monkeypatch.setenv(
        "DP_ICEBERG_WAREHOUSE_PATH",
        str(tmp_path / "iceberg" / "warehouse"),
    )
    return path


def test_write_arrow_round_trips_as_parquet(
    raw_zone_path: Path,
    source_id: str,
) -> None:
    run_id = str(uuid.uuid4())
    table = pa.table({"symbol": ["000001.SZ"]})

    artifact = RawWriter().write_arrow(
        source_id,
        "stock_basic",
        PARTITION_DATE,
        run_id,
        table,
    )

    assert artifact.path == (
        raw_zone_path / source_id / "stock_basic" / "dt=20260415" / f"{run_id}.parquet"
    )
    assert artifact.row_count == 1

    read_back = pq.read_table(artifact.path)
    assert read_back.num_rows == 1


def test_write_json_records_row_count_in_manifest(
    raw_zone_path: Path,
    source_id: str,
) -> None:
    run_id = uuid.uuid4().hex

    artifact = RawWriter().write_json(
        source_id,
        "stock_basic",
        PARTITION_DATE,
        run_id,
        [{"symbol": "000001.SZ"}, {"symbol": "000002.SZ"}],
    )

    with gzip.open(artifact.path, "rt", encoding="utf-8") as file:
        assert json.load(file) == [{"symbol": "000001.SZ"}, {"symbol": "000002.SZ"}]

    manifest_path = raw_zone_path / source_id / "stock_basic" / "dt=20260415" / "_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert manifest["partition_date"] == "2026-04-15"
    assert "row_count" not in manifest
    assert manifest["artifacts"][0]["row_count"] == 2


def test_write_arrow_records_manifest_v2_metadata(
    raw_zone_path: Path,
    source_id: str,
) -> None:
    run_id = str(uuid.uuid4())
    request_params = {"trade_date": "20260415", "fields": "symbol"}
    metadata = {
        "provider": "tushare",
        "source_interface_id": "daily",
        "doc_api": "daily",
        "partition_key": ("trade_date",),
        "schema_hash": "schema-hash-1",
    }

    artifact = RawWriter().write_arrow(
        source_id,
        "daily",
        PARTITION_DATE,
        run_id,
        pa.table({"symbol": ["000001.SZ"]}),
        metadata=metadata,
        request_params=request_params,
    )

    manifest_path = raw_zone_path / source_id / "daily" / "dt=20260415" / "_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    request_params_hash = hashlib.sha256(
        json.dumps(
            request_params,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    artifact_entry = manifest["artifacts"][0]

    assert artifact.metadata == {
        **metadata,
        "partition_key": ["trade_date"],
        "request_params_hash": request_params_hash,
    }
    assert manifest["manifest_version"] == 2
    assert manifest["provider"] == "tushare"
    assert manifest["source_interface_id"] == "daily"
    assert manifest["doc_api"] == "daily"
    assert manifest["partition_key"] == ["trade_date"]
    assert manifest["request_params_hash"] == request_params_hash
    assert manifest["schema_hash"] == "schema-hash-1"
    assert artifact_entry["provider"] == "tushare"
    assert artifact_entry["source_interface_id"] == "daily"
    assert artifact_entry["doc_api"] == "daily"
    assert artifact_entry["partition_key"] == ["trade_date"]
    assert artifact_entry["request_params_hash"] == request_params_hash
    assert artifact_entry["schema_hash"] == "schema-hash-1"


def test_write_arrow_rejects_unknown_tushare_source_interface_id(
    raw_zone_path: Path,
    source_id: str,
) -> None:
    writer = RawWriter()

    with pytest.raises(ValueError, match="unknown Tushare source_interface_id"):
        writer.write_arrow(
            source_id,
            "daily",
            PARTITION_DATE,
            str(uuid.uuid4()),
            pa.table({"symbol": ["000001.SZ"]}),
            metadata={
                "provider": "tushare",
                "source_interface_id": "not_a_real_interface",
                "doc_api": "daily",
            },
        )


def test_write_arrow_rejects_tushare_doc_api_mismatch(
    raw_zone_path: Path,
    source_id: str,
) -> None:
    writer = RawWriter()

    with pytest.raises(ValueError, match="doc_api does not match source_interface_id"):
        writer.write_arrow(
            source_id,
            "daily",
            PARTITION_DATE,
            str(uuid.uuid4()),
            pa.table({"symbol": ["000001.SZ"]}),
            metadata={
                "provider": "tushare",
                "source_interface_id": "daily",
                "doc_api": "trade_cal",
            },
        )


def test_write_arrow_rejects_tushare_source_interface_dataset_mismatch(
    raw_zone_path: Path,
    source_id: str,
) -> None:
    writer = RawWriter()

    with pytest.raises(ValueError, match="dataset does not match source_interface_id"):
        writer.write_arrow(
            source_id,
            "trade_cal",
            PARTITION_DATE,
            str(uuid.uuid4()),
            pa.table({"cal_date": ["20260415"]}),
            metadata={
                "provider": "tushare",
                "source_interface_id": "trade_cal_futures",
                "doc_api": "trade_cal",
            },
        )


def test_reader_accepts_manifest_without_v2_metadata(
    raw_zone_path: Path,
    source_id: str,
) -> None:
    run_id = str(uuid.uuid4())
    artifact_path = (
        raw_zone_path / source_id / "stock_basic" / "dt=20260415" / f"{run_id}.parquet"
    )
    artifact_path.parent.mkdir(parents=True)
    pq.write_table(pa.table({"symbol": ["000001.SZ"]}), artifact_path)
    manifest = {
        "source_id": source_id,
        "dataset": "stock_basic",
        "partition_date": PARTITION_DATE.isoformat(),
        "artifacts": [
            {
                "source_id": source_id,
                "dataset": "stock_basic",
                "partition_date": PARTITION_DATE.isoformat(),
                "run_id": run_id,
                "path": str(artifact_path),
                "row_count": 1,
                "written_at": "2026-04-15T01:00:00+00:00",
            }
        ],
    }
    (artifact_path.parent / "_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    artifacts = RawReader().list_artifacts(source_id, "stock_basic", PARTITION_DATE)

    assert len(artifacts) == 1
    assert artifacts[0].metadata == {}


def test_repeated_run_id_raises_raw_artifact_exists(
    raw_zone_path: Path,
    source_id: str,
) -> None:
    writer = RawWriter()
    run_id = str(uuid.uuid4())

    writer.write_json(source_id, "stock_basic", PARTITION_DATE, run_id, [{"symbol": "000001.SZ"}])

    with pytest.raises(RawArtifactExists):
        writer.write_json(
            source_id,
            "stock_basic",
            PARTITION_DATE,
            run_id,
            [{"symbol": "000001.SZ"}],
        )


def test_manifest_failure_removes_artifact_and_allows_retry(
    raw_zone_path: Path,
    source_id: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    writer = RawWriter()
    run_id = str(uuid.uuid4())
    artifact_path = (
        raw_zone_path / source_id / "stock_basic" / "dt=20260415" / f"{run_id}.json.gz"
    )
    original_write_manifest = writer._write_manifest
    attempts = 0

    def fail_once_then_write_manifest(artifact: object) -> None:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            assert artifact_path.exists()
            raise RuntimeError("manifest write failed")
        original_write_manifest(artifact)  # type: ignore[arg-type]

    monkeypatch.setattr(writer, "_write_manifest", fail_once_then_write_manifest)

    with pytest.raises(RuntimeError, match="manifest write failed"):
        writer.write_json(
            source_id,
            "stock_basic",
            PARTITION_DATE,
            run_id,
            [{"symbol": "000001.SZ"}],
        )

    assert not artifact_path.exists()
    assert RawReader().list_artifacts(source_id, "stock_basic", PARTITION_DATE) == []

    artifact = writer.write_json(
        source_id,
        "stock_basic",
        PARTITION_DATE,
        run_id,
        [{"symbol": "000001.SZ"}],
    )

    assert artifact.path == artifact_path
    assert artifact.path.exists()
    artifacts = RawReader().list_artifacts(source_id, "stock_basic", PARTITION_DATE)
    assert [item.run_id for item in artifacts] == [run_id]


def test_orphaned_artifact_without_manifest_allows_retry(
    raw_zone_path: Path,
    source_id: str,
) -> None:
    writer = RawWriter()
    run_id = str(uuid.uuid4())
    artifact_path = (
        raw_zone_path / source_id / "stock_basic" / "dt=20260415" / f"{run_id}.json.gz"
    )
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_bytes(b"orphaned artifact from interrupted write")

    artifact = writer.write_json(
        source_id,
        "stock_basic",
        PARTITION_DATE,
        run_id,
        [{"symbol": "000001.SZ"}],
    )

    assert artifact.path == artifact_path
    with gzip.open(artifact.path, "rt", encoding="utf-8") as file:
        assert json.load(file) == [{"symbol": "000001.SZ"}]
    artifacts = RawReader().list_artifacts(source_id, "stock_basic", PARTITION_DATE)
    assert [item.run_id for item in artifacts] == [run_id]


def test_raw_writer_derives_raw_zone_from_data_storage_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data_root = tmp_path / "downloaded-data"
    monkeypatch.delenv("DP_RAW_ZONE_PATH", raising=False)
    monkeypatch.setenv("DP_DATA_STORAGE_ROOT_PATH", str(data_root))
    monkeypatch.setenv(
        "DP_ICEBERG_WAREHOUSE_PATH",
        str(tmp_path / "iceberg" / "warehouse"),
    )

    writer = RawWriter()

    assert writer.raw_zone_path == data_root / "raw"


def test_raw_zone_rejects_iceberg_warehouse_boundary(tmp_path: Path) -> None:
    warehouse_path = tmp_path / "iceberg" / "warehouse"

    with pytest.raises(RawZonePathError):
        RawWriter(
            raw_zone_path=warehouse_path / "raw",
            iceberg_warehouse_path=warehouse_path,
        )


def test_raw_zone_rejects_settings_iceberg_warehouse_boundary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    warehouse_path = tmp_path / "iceberg" / "warehouse"
    monkeypatch.delenv("DP_ICEBERG_WAREHOUSE_PATH", raising=False)

    import data_platform.config as config

    monkeypatch.setattr(
        config,
        "get_settings",
        lambda: SimpleNamespace(iceberg_warehouse_path=warehouse_path),
    )

    with pytest.raises(RawZonePathError):
        RawWriter(raw_zone_path=warehouse_path / "raw")


def test_artifact_path_does_not_enter_iceberg_warehouse(
    raw_zone_path: Path,
    tmp_path: Path,
    source_id: str,
) -> None:
    warehouse_path = tmp_path / "iceberg" / "warehouse"
    artifact = RawWriter(
        raw_zone_path=raw_zone_path,
        iceberg_warehouse_path=warehouse_path,
    ).write_json(
        source_id,
        "stock_basic",
        PARTITION_DATE,
        str(uuid.uuid4()),
        [{"symbol": "000001.SZ"}],
    )

    with pytest.raises(ValueError):
        artifact.path.resolve(strict=False).relative_to(warehouse_path.resolve(strict=False))


def test_list_artifacts_returns_written_at_ascending(
    raw_zone_path: Path,
    source_id: str,
) -> None:
    writer = RawWriter()
    first = writer.write_json(
        source_id,
        "stock_basic",
        PARTITION_DATE,
        str(uuid.uuid4()),
        [{"symbol": "000001.SZ"}],
    )
    second = writer.write_json(
        source_id,
        "stock_basic",
        PARTITION_DATE,
        str(uuid.uuid4()),
        [{"symbol": "000002.SZ"}],
    )

    artifacts = RawReader().list_artifacts(source_id, "stock_basic", PARTITION_DATE)

    assert [artifact.run_id for artifact in artifacts] == [first.run_id, second.run_id]
    assert artifacts[0].written_at <= artifacts[1].written_at


def test_raw_reader_accepts_safe_relative_manifest_artifact_ref(
    raw_zone_path: Path,
    source_id: str,
) -> None:
    run_id = str(uuid.uuid4())
    partition_path = raw_zone_path / source_id / "stock_basic" / "dt=20260415"
    artifact_path = partition_path / f"{run_id}.json.gz"
    artifact_path.parent.mkdir(parents=True)
    artifact_path.write_bytes(b"placeholder")
    _write_manifest_with_path_ref(
        partition_path,
        source_id=source_id,
        run_id=run_id,
        path_ref=f"{source_id}/stock_basic/dt=20260415/{run_id}.json.gz",
    )

    artifacts = RawReader(raw_zone_path).list_artifacts(
        source_id,
        "stock_basic",
        PARTITION_DATE,
    )

    assert [artifact.path for artifact in artifacts] == [artifact_path]


@pytest.mark.parametrize(
    "path_ref",
    [
        "",
        "../escape.json.gz",
        "artifact://outside/root.json.gz",
        "s3://bucket/root.json.gz",
        "/tmp/root.json.gz",
    ],
)
def test_raw_reader_rejects_invalid_manifest_artifact_refs(
    raw_zone_path: Path,
    source_id: str,
    path_ref: str,
) -> None:
    partition_path = raw_zone_path / source_id / "stock_basic" / "dt=20260415"
    partition_path.mkdir(parents=True)
    _write_manifest_with_path_ref(
        partition_path,
        source_id=source_id,
        run_id=str(uuid.uuid4()),
        path_ref=path_ref,
    )

    with pytest.raises(ValueError):
        RawReader(raw_zone_path).list_artifacts(source_id, "stock_basic", PARTITION_DATE)


def test_raw_reader_rejects_symlink_escape_manifest_artifact_ref(
    raw_zone_path: Path,
    tmp_path: Path,
    source_id: str,
) -> None:
    run_id = str(uuid.uuid4())
    partition_path = raw_zone_path / source_id / "stock_basic" / "dt=20260415"
    partition_path.mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / f"{run_id}.json.gz").write_bytes(b"outside")
    (raw_zone_path / "linked").symlink_to(outside)
    _write_manifest_with_path_ref(
        partition_path,
        source_id=source_id,
        run_id=run_id,
        path_ref=f"linked/{run_id}.json.gz",
    )

    with pytest.raises(RawZonePathError):
        RawReader(raw_zone_path).list_artifacts(source_id, "stock_basic", PARTITION_DATE)


def test_raw_reader_rejects_manifest_artifact_ref_to_directory(
    raw_zone_path: Path,
    source_id: str,
) -> None:
    run_id = str(uuid.uuid4())
    partition_path = raw_zone_path / source_id / "stock_basic" / "dt=20260415"
    artifact_dir = partition_path / f"{run_id}.json.gz"
    artifact_dir.mkdir(parents=True)
    _write_manifest_with_path_ref(
        partition_path,
        source_id=source_id,
        run_id=run_id,
        path_ref=f"{source_id}/stock_basic/dt=20260415/{run_id}.json.gz",
    )

    with pytest.raises(ValueError, match="must point to a file"):
        RawReader(raw_zone_path).list_artifacts(source_id, "stock_basic", PARTITION_DATE)


def test_concurrent_same_run_id_allows_one_artifact(
    raw_zone_path: Path,
    source_id: str,
) -> None:
    writer = RawWriter()
    run_id = str(uuid.uuid4())
    barrier = threading.Barrier(2)

    def write() -> str:
        barrier.wait(timeout=5)
        writer.write_json(
            source_id,
            "stock_basic",
            PARTITION_DATE,
            run_id,
            [{"symbol": "000001.SZ"}],
        )
        return "written"

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = []
        for future in [executor.submit(write), executor.submit(write)]:
            try:
                results.append(future.result(timeout=10))
            except RawArtifactExists:
                results.append("exists")

    assert sorted(results) == ["exists", "written"]
    artifacts = RawReader().list_artifacts(source_id, "stock_basic", PARTITION_DATE)
    assert [artifact.run_id for artifact in artifacts] == [run_id]


def test_concurrent_different_run_ids_all_appear_in_manifest(
    raw_zone_path: Path,
    source_id: str,
) -> None:
    writer = RawWriter()
    run_ids = [str(uuid.uuid4()) for _ in range(12)]
    barrier = threading.Barrier(len(run_ids))

    def write(run_id: str) -> str:
        barrier.wait(timeout=5)
        writer.write_json(
            source_id,
            "stock_basic",
            PARTITION_DATE,
            run_id,
            [{"symbol": run_id}],
        )
        return run_id

    with ThreadPoolExecutor(max_workers=len(run_ids)) as executor:
        futures = [executor.submit(write, run_id) for run_id in run_ids]
        written_run_ids = {future.result(timeout=10) for future in futures}

    artifacts = RawReader().list_artifacts(source_id, "stock_basic", PARTITION_DATE)

    assert {artifact.run_id for artifact in artifacts} == written_run_ids
    assert len(artifacts) == len(run_ids)


def _write_manifest_with_path_ref(
    partition_path: Path,
    *,
    source_id: str,
    run_id: str,
    path_ref: str,
) -> None:
    manifest = {
        "source_id": source_id,
        "dataset": "stock_basic",
        "partition_date": PARTITION_DATE.isoformat(),
        "artifacts": [
            {
                "source_id": source_id,
                "dataset": "stock_basic",
                "partition_date": PARTITION_DATE.isoformat(),
                "run_id": run_id,
                "path": path_ref,
                "row_count": 1,
                "written_at": datetime.now(UTC).isoformat(),
            }
        ],
    }
    (partition_path / "_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
