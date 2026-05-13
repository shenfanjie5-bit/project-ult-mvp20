from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import threading
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest

from data_platform import daily_refresh
from data_platform.config import reset_settings_cache
from data_platform.serving.canonical_writer import (
    CANONICAL_LINEAGE_MART_LOAD_SPECS,
    CANONICAL_V2_MART_LOAD_SPECS,
    WriteResult,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
PARTITION_DATE = date(2026, 4, 15)


def test_mock_daily_refresh_is_repeatable_and_writes_report(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _set_daily_refresh_env(monkeypatch, tmp_path)
    assert "DP_TUSHARE_TOKEN" not in os.environ
    _install_fast_success_stubs(monkeypatch)

    first_report = tmp_path / "daily-refresh-first.json"
    second_report = tmp_path / "daily-refresh-second.json"

    first = daily_refresh.run_daily_refresh(
        PARTITION_DATE,
        mock=True,
        json_report=first_report,
    )
    second = daily_refresh.run_daily_refresh(
        PARTITION_DATE,
        mock=True,
        json_report=second_report,
    )

    assert first.ok is True
    assert second.ok is True
    assert [step.name for step in second.steps] == [
        "adapter",
        "dbt_run",
        "dbt_test",
        "canonical",
        "raw_health",
    ]
    assert {step.status for step in second.steps} == {"ok"}

    report = json.loads(second_report.read_text(encoding="utf-8"))
    assert report["ok"] is True
    assert report["partition_date"] == "2026-04-15"
    assert {step["name"] for step in report["steps"]} >= {
        "adapter",
        "dbt_run",
        "dbt_test",
        "canonical",
        "raw_health",
    }
    assert all(isinstance(step["duration_ms"], int) for step in report["steps"])

    adapter_step = _step(report, "adapter")
    assert adapter_step["metadata"]["mock"] is True
    assert adapter_step["metadata"]["artifact_count"] == len(daily_refresh.TUSHARE_ASSETS)
    assert all(
        UUID(artifact["run_id"]).version == 4
        for artifact in adapter_step["metadata"]["artifacts"]
    )

    stock_basic_manifest = json.loads(
        (
            tmp_path
            / "raw"
            / "tushare"
            / "stock_basic"
            / "dt=20260415"
            / "_manifest.json"
        ).read_text(encoding="utf-8")
    )
    assert len(stock_basic_manifest["artifacts"]) == 2
    assert all(
        UUID(artifact["run_id"]).version == 4
        for artifact in stock_basic_manifest["artifacts"]
    )

    canonical_step = _step(report, "canonical")
    write_results = canonical_step["metadata"]["write_results"]
    assert [item["row_count"] for item in write_results] == [
        1
    ] * (
        len(CANONICAL_V2_MART_LOAD_SPECS)
        + len(CANONICAL_LINEAGE_MART_LOAD_SPECS)
    )
    assert canonical_step["metadata"]["skipped_writes"] == []

    raw_health_step = _step(report, "raw_health")
    assert raw_health_step["metadata"]["checked_artifacts"] == 2 * len(
        daily_refresh.TUSHARE_ASSETS
    )
    assert raw_health_step["metadata"]["issues"] == []


def test_daily_refresh_reports_missing_dp_pg_dsn(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    _set_daily_refresh_env(monkeypatch, tmp_path, include_pg_dsn=False)
    report_path = tmp_path / "missing-dsn-report.json"

    result = daily_refresh.run_daily_refresh(
        PARTITION_DATE,
        mock=True,
        json_report=report_path,
    )

    assert result.ok is False
    assert result.steps[0].name == "config"
    assert result.steps[0].status == "failed"
    assert "DP_PG_DSN is required" in result.steps[0].metadata["error"]

    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["ok"] is False
    assert "DP_PG_DSN is required" in report["steps"][0]["metadata"]["error"]


def test_daily_refresh_full_dbt_selectors_include_v2_and_lineage() -> None:
    assets = daily_refresh.TUSHARE_ASSETS

    assert daily_refresh._dbt_selectors(assets, assets) == (
        "staging",
        "intermediate",
        "marts_v2",
        "marts_lineage",
    )


def test_daily_refresh_partial_dbt_selectors_keep_legacy_staging_path() -> None:
    selected_assets = [daily_refresh.TUSHARE_ASSETS[0]]

    assert daily_refresh._dbt_selectors(
        selected_assets,
        daily_refresh.TUSHARE_ASSETS,
    ) == (f"stg_{selected_assets[0].dataset}",)


def test_live_top10_refresh_requires_configured_ts_codes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asset = next(
        asset for asset in daily_refresh.TUSHARE_ASSETS if asset.dataset == "top10_holders"
    )
    monkeypatch.delenv("DP_TUSHARE_TOP10_TS_CODES", raising=False)

    with pytest.raises(
        daily_refresh.DailyRefreshStepError,
        match="requires explicit ts_code",
    ):
        daily_refresh._live_fetch_params_for_asset(asset)


def test_live_top10_refresh_uses_configured_ts_codes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asset = next(
        asset for asset in daily_refresh.TUSHARE_ASSETS if asset.dataset == "top10_holders"
    )
    monkeypatch.setenv("DP_TUSHARE_TOP10_TS_CODES", "000001.SZ, 600519.SH")

    assert daily_refresh._live_fetch_params_for_asset(asset) == {
        "ts_codes": ("000001.SZ", "600519.SH")
    }


def test_live_hk_hold_daily_refresh_skips_after_publication_cutoff(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _set_daily_refresh_env(monkeypatch, tmp_path)
    monkeypatch.setenv("DP_TUSHARE_TOKEN", "test-token")

    def fail_if_called(*_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("post-cutoff hk_hold daily refresh must be gated")

    monkeypatch.setattr(daily_refresh, "run_tushare_asset", fail_if_called)

    result = daily_refresh.run_daily_refresh(
        date(2026, 5, 4),
        mock=False,
        select=["hsgt_hold_top10"],
    )

    assert result.ok is True
    assert [(step.name, step.status) for step in result.steps] == [
        ("adapter", "skipped"),
        ("dbt_run", "skipped"),
        ("dbt_test", "skipped"),
        ("canonical", "skipped"),
        ("raw_health", "skipped"),
    ]
    adapter_metadata = result.steps[0].metadata
    assert adapter_metadata["artifact_count"] == 0
    assert adapter_metadata["artifacts"] == []
    assert adapter_metadata["skipped_assets"] == [
        {
            "asset": "tushare_hsgt_hold_top10",
            "dataset": "hsgt_hold_top10",
            "source_interface_id": "hsgt_hold_top10",
            "doc_api": "hk_hold",
            "partition_date": "20260504",
            "status": "skipped",
            "reason_type": "daily_publication_discontinued",
            "reason": (
                "Tushare hk_hold daily northbound publication ended after "
                "2024-08-20; the daily refresh does not fetch post-cutoff "
                "current-date hk_hold pages"
            ),
            "daily_publication_last_date": "2024-08-20",
            "replacement_cadence": "quarterly_disclosure",
            "skip_policy": "fail_closed_no_daily_live_freshness_claim",
        }
    ]
    assert list((tmp_path / "raw").rglob("*.parquet")) == []


def test_hk_hold_daily_refresh_cutoff_keeps_last_publication_date_live() -> None:
    asset = next(
        asset for asset in daily_refresh.TUSHARE_ASSETS if asset.dataset == "hsgt_hold_top10"
    )

    assert (
        daily_refresh._daily_refresh_skip_for_asset(
            asset,
            date(2024, 8, 20),
            mock=False,
        )
        is None
    )
    assert daily_refresh._daily_refresh_skip_for_asset(
        asset,
        date(2024, 8, 21),
        mock=False,
    )["reason_type"] == "daily_publication_discontinued"


def test_hk_hold_skip_plan_makes_full_live_refresh_partial_after_cutoff() -> None:
    all_assets = daily_refresh.TUSHARE_ASSETS

    plan = daily_refresh._refresh_asset_plan(
        all_assets,
        date(2026, 5, 4),
        mock=False,
    )

    assert "hsgt_hold_top10" not in {asset.dataset for asset in plan.assets}
    assert [item["dataset"] for item in plan.skipped_assets] == ["hsgt_hold_top10"]
    assert daily_refresh._dbt_selectors(plan.assets, all_assets) != (
        "staging",
        "intermediate",
        "marts_v2",
        "marts_lineage",
    )


def test_mock_adapter_values_cover_dbt_cast_fields() -> None:
    assets_by_dataset = {asset.dataset: asset for asset in daily_refresh.TUSHARE_ASSETS}

    forecast = daily_refresh._mock_table(assets_by_dataset["forecast"], PARTITION_DATE)
    stk_limit = daily_refresh._mock_table(assets_by_dataset["stk_limit"], PARTITION_DATE)
    moneyflow = daily_refresh._mock_table(assets_by_dataset["moneyflow"], PARTITION_DATE)
    trade_cal = daily_refresh._mock_table(assets_by_dataset["trade_cal"], PARTITION_DATE)

    assert forecast.column("first_ann_date").to_pylist() == ["20260415"]
    assert forecast.column("p_change_min").to_pylist() == ["1.123456789012345678"]
    assert forecast.column("p_change_max").to_pylist() == ["1.123456789012345678"]
    assert stk_limit.column("up_limit").to_pylist() == ["1.123456789012345678"]
    assert stk_limit.column("down_limit").to_pylist() == ["1.123456789012345678"]
    assert moneyflow.column("buy_sm_vol").to_pylist() == ["1.123456789012345678"]
    assert moneyflow.column("net_mf_amount").to_pylist() == ["1.123456789012345678"]
    assert trade_cal.column("exchange").to_pylist() == ["SSE"]
    assert trade_cal.column("is_open").to_pylist() == ["1"]


def test_daily_refresh_script_reports_missing_dp_pg_dsn(tmp_path: Path) -> None:
    env = os.environ.copy()
    env.update(
        {
            "DP_RAW_ZONE_PATH": str(tmp_path / "raw"),
            "DP_ICEBERG_WAREHOUSE_PATH": str(tmp_path / "warehouse"),
            "DP_DUCKDB_PATH": str(tmp_path / "duckdb" / "data_platform.duckdb"),
            "DP_ICEBERG_CATALOG_NAME": "data_platform_daily_refresh_test",
            "DP_ENV": "test",
            "PYTHON": sys.executable,
            "PYTHONPATH": str(PROJECT_ROOT / "src"),
        }
    )
    env.pop("DP_PG_DSN", None)
    env.pop("DP_TUSHARE_TOKEN", None)
    report_path = tmp_path / "script-missing-dsn.json"

    result = subprocess.run(
        [
            "bash",
            str(PROJECT_ROOT / "scripts" / "daily_refresh.sh"),
            "--date",
            "20260415",
            "--mock",
            "--json-report",
            str(report_path),
        ],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )

    assert result.returncode == 2
    assert "DP_PG_DSN is required" in result.stderr
    assert "Daily refresh OK" not in result.stdout

    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["ok"] is False
    assert report["steps"][0]["name"] == "config"


def test_concurrent_daily_refresh_same_date_fails_before_raw_dbt_and_canonical(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _set_daily_refresh_env(monkeypatch, tmp_path)
    _install_fast_success_stubs(monkeypatch)
    first_dbt_started = threading.Event()
    release_first_run = threading.Event()
    dbt_calls: list[list[str]] = []

    def fake_run_dbt_command(args: list[str], settings: Any) -> dict[str, Any]:
        dbt_calls.append(args)
        if args[0] == "run" and not first_dbt_started.is_set():
            first_dbt_started.set()
            assert release_first_run.wait(timeout=5)
        return {
            "command": ["dbt", *args],
            "dbt_executable": "dbt",
            "returncode": 0,
            "stdout_tail": "",
            "stderr_tail": "",
            "duckdb_path": str(settings.duckdb_path),
        }

    monkeypatch.setattr(daily_refresh, "_run_dbt_command", fake_run_dbt_command)
    first_result: dict[str, daily_refresh.DailyRefreshResult] = {}
    first_error: list[BaseException] = []

    def run_first() -> None:
        try:
            first_result["result"] = daily_refresh.run_daily_refresh(
                PARTITION_DATE,
                mock=True,
            )
        except BaseException as exc:  # pragma: no cover - re-raised by assertion
            first_error.append(exc)

    first_thread = threading.Thread(target=run_first)
    first_thread.start()
    assert first_dbt_started.wait(timeout=5)

    second = daily_refresh.run_daily_refresh(PARTITION_DATE, mock=True)
    release_first_run.set()
    first_thread.join(timeout=5)

    assert first_error == []
    assert not first_thread.is_alive()
    assert first_result["result"].ok is True
    assert second.ok is False
    assert [step.name for step in second.steps] == ["refresh_lock"]
    assert second.steps[-1].metadata["error_type"] == "refresh_lock_held"
    assert "already running" in second.steps[-1].metadata["error"]
    assert all(
        step.name not in {"adapter", "dbt_run", "dbt_test", "canonical"}
        for step in second.steps
    )
    assert [call[0] for call in dbt_calls] == ["run", "test"]
    stock_basic_manifest = json.loads(
        (
            tmp_path
            / "raw"
            / "tushare"
            / "stock_basic"
            / "dt=20260415"
            / "_manifest.json"
        ).read_text(encoding="utf-8")
    )
    assert len(stock_basic_manifest["artifacts"]) == 1
    assert UUID(stock_basic_manifest["artifacts"][0]["run_id"]).version == 4


def test_daily_refresh_reclaims_stale_lock(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _set_daily_refresh_env(monkeypatch, tmp_path)
    _install_fast_success_stubs(monkeypatch)
    monkeypatch.setenv("DP_DAILY_REFRESH_LOCK_STALE_SECONDS", "1")
    monkeypatch.setattr(daily_refresh, "_process_is_alive", lambda _pid: False)
    settings = daily_refresh._load_settings()
    lock_path = daily_refresh._refresh_lock_path(settings, PARTITION_DATE)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_text(
        json.dumps(
            {
                "catalog": settings.iceberg_catalog_name,
                "host": socket.gethostname(),
                "partition_date": "20260415",
                "pid": 12345,
                "acquired_at": (datetime.now(UTC) - timedelta(seconds=5)).isoformat(),
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    result = daily_refresh.run_daily_refresh(PARTITION_DATE, mock=True)

    assert result.ok is True
    assert [step.name for step in result.steps] == [
        "adapter",
        "dbt_run",
        "dbt_test",
        "canonical",
        "raw_health",
    ]
    assert not lock_path.exists()


def test_daily_refresh_does_not_reclaim_stale_lock_with_live_owner(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _set_daily_refresh_env(monkeypatch, tmp_path)
    _install_fast_success_stubs(monkeypatch)
    monkeypatch.setenv("DP_DAILY_REFRESH_LOCK_STALE_SECONDS", "1")
    settings = daily_refresh._load_settings()
    lock_path = daily_refresh._refresh_lock_path(settings, PARTITION_DATE)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    owner = {
        "catalog": settings.iceberg_catalog_name,
        "host": socket.gethostname(),
        "partition_date": "20260415",
        "pid": os.getpid(),
        "acquired_at": (datetime.now(UTC) - timedelta(seconds=5)).isoformat(),
    }
    lock_path.write_text(
        json.dumps(owner, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    result = daily_refresh.run_daily_refresh(PARTITION_DATE, mock=True)

    assert result.ok is False
    assert [step.name for step in result.steps] == ["refresh_lock"]
    assert result.steps[0].metadata["error_type"] == "refresh_lock_held"
    assert json.loads(lock_path.read_text(encoding="utf-8")) == owner


def test_refresh_lock_release_does_not_remove_replacement_lock(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _set_daily_refresh_env(monkeypatch, tmp_path)
    settings = daily_refresh._load_settings()
    lock = daily_refresh._acquire_refresh_lock(settings, PARTITION_DATE)
    replacement_owner = {
        "catalog": settings.iceberg_catalog_name,
        "host": socket.gethostname(),
        "owner_token": "replacement",
        "partition_date": "20260415",
        "pid": os.getpid(),
        "acquired_at": datetime.now(UTC).isoformat(),
    }

    lock.path.unlink()
    lock.path.write_text(
        json.dumps(replacement_owner, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    lock.release()

    assert json.loads(lock.path.read_text(encoding="utf-8")) == replacement_owner


def test_mock_daily_refresh_real_pipeline_repeatable_when_pg_available(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    pg_dsn = os.environ.get("DP_DAILY_REFRESH_TEST_PG_DSN")
    if not pg_dsn:
        pytest.skip(
            "DP_DAILY_REFRESH_TEST_PG_DSN is required for the non-stubbed "
            "daily refresh integration test"
        )
    local_dbt = PROJECT_ROOT / ".venv" / "bin" / "dbt"
    if shutil.which("dbt") is None and not local_dbt.exists():
        pytest.skip("dbt executable is required for the non-stubbed daily refresh test")

    _set_daily_refresh_env(monkeypatch, tmp_path)
    monkeypatch.setenv("DP_PG_DSN", pg_dsn)
    monkeypatch.setenv(
        "DP_ICEBERG_CATALOG_NAME",
        f"data_platform_daily_refresh_{tmp_path.name}",
    )
    reset_settings_cache()

    first = daily_refresh.run_daily_refresh(PARTITION_DATE, mock=True)
    second = daily_refresh.run_daily_refresh(PARTITION_DATE, mock=True)

    assert first.ok is True
    assert second.ok is True
    assert [step.name for step in second.steps] == [
        "adapter",
        "dbt_run",
        "dbt_test",
        "canonical",
        "raw_health",
    ]
    first_rows = [
        item["row_count"]
        for item in _result_step(first, "canonical").metadata["write_results"]
    ]
    second_rows = [
        item["row_count"]
        for item in _result_step(second, "canonical").metadata["write_results"]
    ]
    assert first_rows == second_rows
    assert len(second_rows) == (
        len(CANONICAL_V2_MART_LOAD_SPECS)
        + len(CANONICAL_LINEAGE_MART_LOAD_SPECS)
    )
    assert all(row_count > 0 for row_count in second_rows)


def _set_daily_refresh_env(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    include_pg_dsn: bool = True,
) -> dict[str, str]:
    values = {
        "DP_RAW_ZONE_PATH": str(tmp_path / "raw"),
        "DP_ICEBERG_WAREHOUSE_PATH": str(tmp_path / "warehouse"),
        "DP_DUCKDB_PATH": str(tmp_path / "duckdb" / "data_platform.duckdb"),
        "DP_ICEBERG_CATALOG_NAME": "data_platform_daily_refresh_test",
        "DP_ENV": "test",
    }
    if include_pg_dsn:
        values["DP_PG_DSN"] = "postgresql://dp:dp@localhost/data_platform_daily_refresh_test"
    else:
        monkeypatch.delenv("DP_PG_DSN", raising=False)

    for key, value in values.items():
        monkeypatch.setenv(key, value)
    monkeypatch.delenv("DP_TUSHARE_TOKEN", raising=False)
    reset_settings_cache()
    return values


def _install_fast_success_stubs(monkeypatch: pytest.MonkeyPatch) -> None:
    dbt_calls: list[list[str]] = []
    snapshots = iter(range(1001, 2000))

    class FakeMigrationRunner:
        def apply_pending(self, dsn: str) -> list[str]:
            assert dsn.startswith("postgresql://")
            return []

    def fake_run_dbt_command(args: list[str], settings: Any) -> dict[str, Any]:
        dbt_calls.append(args)
        return {
            "command": ["dbt", *args],
            "dbt_executable": "dbt",
            "returncode": 0,
            "stdout_tail": "",
            "stderr_tail": "",
            "duckdb_path": str(settings.duckdb_path),
        }

    def fake_build_resources(settings: Any) -> dict[str, Any]:
        return {
            "iceberg_catalog": object(),
            "duckdb_path": settings.duckdb_path,
        }

    def fake_load_v2_marts(_catalog: object, _duckdb_path: Path) -> list[WriteResult]:
        return [
            WriteResult(
                table=spec.identifier,
                snapshot_id=next(snapshots),
                row_count=1,
                duration_ms=0,
            )
            for spec in (
                *CANONICAL_V2_MART_LOAD_SPECS,
                *CANONICAL_LINEAGE_MART_LOAD_SPECS,
            )
        ]

    monkeypatch.setattr(daily_refresh, "MigrationRunner", FakeMigrationRunner)
    monkeypatch.setattr(daily_refresh, "_run_dbt_command", fake_run_dbt_command)
    monkeypatch.setattr(daily_refresh, "build_resources", fake_build_resources)
    monkeypatch.setattr(daily_refresh, "ensure_namespaces", lambda *_args: None)
    monkeypatch.setattr(daily_refresh, "ensure_tables", lambda *_args: [])
    monkeypatch.setattr(daily_refresh, "load_canonical_v2_marts", fake_load_v2_marts)


def _step(report: dict[str, Any], name: str) -> dict[str, Any]:
    for step in report["steps"]:
        if step["name"] == name:
            return step
    raise AssertionError(f"missing daily refresh step: {name}")


def _result_step(
    result: daily_refresh.DailyRefreshResult,
    name: str,
) -> daily_refresh.DailyRefreshStepResult:
    for step in result.steps:
        if step.name == name:
            return step
    raise AssertionError(f"missing daily refresh result step: {name}")
