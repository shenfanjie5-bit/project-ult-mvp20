from __future__ import annotations

import json
import os
import subprocess
import sys
import uuid
from datetime import date
from pathlib import Path
from typing import Any

import pytest

pa = pytest.importorskip("pyarrow")
pq = pytest.importorskip("pyarrow.parquet")

from data_platform.raw import RawWriter, check_raw_zone  # noqa: E402


PROJECT_ROOT = Path(__file__).resolve().parents[2]
PARTITION_DATE = date(2026, 4, 15)
SOURCE_ID = "tushare"
DATASET = "stock_basic"


def test_check_raw_zone_accepts_rawwriter_parquet_and_json(tmp_path: Path) -> None:
    raw_zone_path = tmp_path / "raw"
    writer = _raw_writer(raw_zone_path, tmp_path)

    writer.write_arrow(
        SOURCE_ID,
        DATASET,
        PARTITION_DATE,
        str(uuid.uuid4()),
        _stock_basic_table(),
    )
    writer.write_json(
        SOURCE_ID,
        DATASET,
        PARTITION_DATE,
        uuid.uuid4().hex,
        [{"ts_code": "000001.SZ"}, {"ts_code": "000002.SZ"}],
    )

    report = check_raw_zone(raw_zone_path, deep=True)

    assert report.ok is True
    assert report.checked_artifacts == 2
    assert report.issues == []


def test_check_raw_zone_accepts_rawwriter_relative_manifest_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    raw_zone_path = Path("relative_raw")
    writer = _raw_writer(raw_zone_path, tmp_path)

    writer.write_arrow(
        SOURCE_ID,
        DATASET,
        PARTITION_DATE,
        str(uuid.uuid4()),
        _stock_basic_table(),
    )

    report = check_raw_zone(raw_zone_path, deep=True)

    assert report.ok is True
    assert report.checked_artifacts == 1
    assert report.issues == []


def test_check_raw_zone_reports_invalid_run_id(tmp_path: Path) -> None:
    raw_zone_path = tmp_path / "raw"
    run_id = "not-a-valid-run-id"
    partition_path = _partition_path(raw_zone_path)
    artifact_path = partition_path / f"{run_id}.parquet"
    partition_path.mkdir(parents=True)
    pq.write_table(_stock_basic_table(), artifact_path)
    _write_manifest(partition_path, [_artifact_entry(run_id)])

    report = check_raw_zone(raw_zone_path)

    assert _issue_codes(report) == {"invalid_run_id"}
    assert report.ok is False


def test_check_raw_zone_reports_missing_artifact(tmp_path: Path) -> None:
    raw_zone_path = tmp_path / "raw"
    run_id = str(uuid.uuid4())
    partition_path = _partition_path(raw_zone_path)
    partition_path.mkdir(parents=True)
    _write_manifest(partition_path, [_artifact_entry(run_id)])

    report = check_raw_zone(raw_zone_path)

    assert "artifact_missing" in _issue_codes(report)
    assert report.ok is False


def test_check_raw_zone_deep_reports_row_count_mismatch(tmp_path: Path) -> None:
    raw_zone_path = tmp_path / "raw"
    writer = _raw_writer(raw_zone_path, tmp_path)
    artifact = writer.write_arrow(
        SOURCE_ID,
        DATASET,
        PARTITION_DATE,
        str(uuid.uuid4()),
        _stock_basic_table(),
    )
    manifest_path = artifact.path.parent / "_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["artifacts"][0]["row_count"] = artifact.row_count + 1
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")

    shallow_report = check_raw_zone(raw_zone_path, deep=False)
    deep_report = check_raw_zone(raw_zone_path, deep=True)

    assert "row_count_mismatch" not in _issue_codes(shallow_report)
    assert "row_count_mismatch" in _issue_codes(deep_report)
    assert shallow_report.ok is True
    assert deep_report.ok is False


def test_check_raw_zone_reports_duplicate_run_id(tmp_path: Path) -> None:
    raw_zone_path = tmp_path / "raw"
    writer = _raw_writer(raw_zone_path, tmp_path)
    artifact = writer.write_arrow(
        SOURCE_ID,
        DATASET,
        PARTITION_DATE,
        str(uuid.uuid4()),
        _stock_basic_table(),
    )
    manifest_path = artifact.path.parent / "_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["artifacts"].append(dict(manifest["artifacts"][0]))
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")

    report = check_raw_zone(raw_zone_path)

    assert "duplicate_run_id" in _issue_codes(report)
    assert report.ok is False


def test_check_raw_zone_reports_orphan_artifact(tmp_path: Path) -> None:
    raw_zone_path = tmp_path / "raw"
    writer = _raw_writer(raw_zone_path, tmp_path)
    artifact = writer.write_arrow(
        SOURCE_ID,
        DATASET,
        PARTITION_DATE,
        str(uuid.uuid4()),
        _stock_basic_table(),
    )
    orphan_path = artifact.path.parent / f"{uuid.uuid4()}.parquet"
    pq.write_table(_stock_basic_table(), orphan_path)

    report = check_raw_zone(raw_zone_path)

    assert "orphan_artifact" in _issue_codes(report)
    assert report.ok is False


def test_check_raw_zone_reports_invalid_partition_dir(tmp_path: Path) -> None:
    raw_zone_path = tmp_path / "raw"
    (raw_zone_path / SOURCE_ID / DATASET / "dt=2026-04-15").mkdir(parents=True)

    report = check_raw_zone(raw_zone_path)

    assert _issue_codes(report) == {"invalid_partition_dir"}
    assert report.ok is False


def test_check_raw_zone_reports_bad_manifest(tmp_path: Path) -> None:
    raw_zone_path = tmp_path / "raw"
    partition_path = _partition_path(raw_zone_path)
    partition_path.mkdir(parents=True)
    (partition_path / "_manifest.json").write_text("{", encoding="utf-8")

    report = check_raw_zone(raw_zone_path)

    assert "manifest_parse_error" in _issue_codes(report)
    assert report.ok is False


def test_check_raw_zone_reports_malformed_manifest_artifact_entry(
    tmp_path: Path,
) -> None:
    raw_zone_path = tmp_path / "raw"
    partition_path = _partition_path(raw_zone_path)
    partition_path.mkdir(parents=True)
    manifest = {
        "source_id": SOURCE_ID,
        "dataset": DATASET,
        "partition_date": PARTITION_DATE.isoformat(),
        "artifacts": [
            "not-an-object",
            {
                "source_id": SOURCE_ID,
                "dataset": DATASET,
                "partition_date": PARTITION_DATE.isoformat(),
                "run_id": str(uuid.uuid4()),
                "path": f"{SOURCE_ID}/{DATASET}/dt=20260415/missing.parquet",
                "row_count": "3",
                "written_at": "2026-04-15T01:00:00+00:00",
            },
        ],
    }
    (partition_path / "_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    report = check_raw_zone(raw_zone_path)

    assert _issue_codes(report) == {"manifest_artifact_invalid"}
    assert report.ok is False


def test_check_raw_zone_cli_emits_json_and_error_return_code(tmp_path: Path) -> None:
    raw_zone_path = tmp_path / "raw"
    partition_path = _partition_path(raw_zone_path)
    partition_path.mkdir(parents=True)
    _write_manifest(partition_path, [_artifact_entry(str(uuid.uuid4()))])
    env = os.environ.copy()
    env["PYTHONPATH"] = str(PROJECT_ROOT / "src")

    result = subprocess.run(
        [
            sys.executable,
            str(PROJECT_ROOT / "scripts" / "check_raw_zone.py"),
            "--root",
            str(raw_zone_path),
            "--json",
        ],
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    payload = json.loads(result.stdout)

    assert result.returncode == 1
    assert payload["ok"] is False
    assert payload["checked_artifacts"] == 1
    assert {issue["code"] for issue in payload["issues"]} == {"artifact_missing"}


def _raw_writer(raw_zone_path: Path, tmp_path: Path) -> RawWriter:
    return RawWriter(
        raw_zone_path=raw_zone_path,
        iceberg_warehouse_path=tmp_path / "iceberg" / "warehouse",
    )


def _partition_path(raw_zone_path: Path) -> Path:
    return raw_zone_path / SOURCE_ID / DATASET / "dt=20260415"


def _stock_basic_table() -> Any:
    return pa.table(
        {
            "ts_code": ["000001.SZ", "000002.SZ", "000003.BJ"],
            "symbol": ["000001", "000002", "000003"],
            "name": ["Ping An Bank", "Vanke A", "Test BJ"],
            "area": ["Shenzhen", "Shenzhen", ""],
            "industry": ["Bank", "Real Estate", ""],
            "market": ["Main", "Main", "BJ"],
            "list_status": ["L", "L", "D"],
            "list_date": [19910403, 19910129, 20200101],
        }
    )


def _artifact_entry(run_id: str, *, row_count: int = 3) -> dict[str, Any]:
    return {
        "source_id": SOURCE_ID,
        "dataset": DATASET,
        "partition_date": PARTITION_DATE.isoformat(),
        "run_id": run_id,
        "path": f"{SOURCE_ID}/{DATASET}/dt=20260415/{run_id}.parquet",
        "row_count": row_count,
        "written_at": "2026-04-15T01:00:00+00:00",
    }


def _write_manifest(partition_path: Path, artifacts: list[dict[str, Any]]) -> None:
    manifest = {
        "source_id": SOURCE_ID,
        "dataset": DATASET,
        "partition_date": PARTITION_DATE.isoformat(),
        "artifacts": artifacts,
    }
    (partition_path / "_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _issue_codes(report: Any) -> set[str]:
    return {issue.code for issue in report.issues}
