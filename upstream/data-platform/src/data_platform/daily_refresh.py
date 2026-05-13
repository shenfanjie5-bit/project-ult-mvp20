"""Mock-scheduler entry point for the daily structured-data refresh."""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import shutil
import socket
import subprocess
import sys
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, is_dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from time import perf_counter
from typing import Any, Literal, NoReturn
from uuid import UUID, uuid4

import pyarrow as pa  # type: ignore[import-untyped]
from pydantic import ValidationError

from data_platform.adapters.base import AssetSpec, FetchParams, FetchableAdapter
from data_platform.adapters.tushare.adapter import (
    EXPLICIT_TS_CODE_RAW_DATASETS,
    EXPLICIT_TS_CODES_PARAM,
    TushareAdapter,
    run_tushare_asset,
)
from data_platform.adapters.tushare.assets import TUSHARE_ASSETS
from data_platform.assets import build_assets, build_resources
from data_platform.config import Settings, get_settings
from data_platform.ddl.iceberg_tables import DEFAULT_TABLE_SPECS, ensure_tables
from data_platform.ddl.runner import MigrationRunner
from data_platform.raw import RawArtifact, RawWriter, check_raw_zone
from data_platform.serving.canonical_writer import (
    WriteResult,
    load_canonical_v2_marts,
)
from data_platform.serving.catalog import DEFAULT_NAMESPACES, ensure_namespaces


StepStatus = Literal["ok", "skipped", "failed"]
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DBT_SCRIPT = PROJECT_ROOT / "scripts" / "dbt.sh"
DBT_EXECUTABLE_ENV = "DP_DBT_EXECUTABLE"
DBT_BIN_ENV = "DBT_BIN"
DATE_FORMAT = "%Y%m%d"
DEFAULT_DBT_SELECTORS = ("staging", "intermediate", "marts_v2", "marts_lineage")
TRUTHY_VALUES = frozenset({"1", "true", "yes", "on"})
DEFAULT_REFRESH_LOCK_STALE_AFTER = timedelta(hours=6)
REFRESH_LOCK_STALE_SECONDS_ENV = "DP_DAILY_REFRESH_LOCK_STALE_SECONDS"
TOP10_TS_CODES_ENV = "DP_TUSHARE_TOP10_TS_CODES"
HK_HOLD_DAILY_REFRESH_DATASET = "hsgt_hold_top10"
HK_HOLD_DAILY_PUBLICATION_LAST_DATE = date(2024, 8, 20)
DATE_FIELD_NAMES = frozenset(
    {
        "actual_date",
        "ann_date",
        "base_date",
        "cal_date",
        "delist_date",
        "div_listdate",
        "end_date",
        "ex_date",
        "exp_date",
        "f_ann_date",
        "float_date",
        "first_ann_date",
        "imp_ann_date",
        "in_date",
        "list_date",
        "modify_date",
        "out_date",
        "pay_date",
        "pre_date",
        "pretrade_date",
        "record_date",
        # M1.13 expansion (precondition 9 closure) — release_date
        # (pledge_detail) and surv_date (stk_surv) require YYYYMMDD
        # mock values so the staging cast strptime succeeds.
        "release_date",
        "setup_date",
        "start_date",
        "surv_date",
        "trade_date",
    }
)
STRING_NUMERIC_FIELD_NAMES = frozenset(
    {
        "adj_factor",
        "after_ratio",
        "after_share",
        "amount",
        "avg_price",
        "base_point",
        "buy",
        "buy_amount",
        "buy_elg_amount",
        "buy_elg_vol",
        "buy_lg_amount",
        "buy_lg_vol",
        "buy_md_amount",
        "buy_md_vol",
        "buy_sm_amount",
        "buy_sm_vol",
        "cash_div",
        "change",
        "change_ratio",
        "change_vol",
        "circ_mv",
        "close",
        "down_limit",
        "dv_ratio",
        "dv_ttm",
        "employees",
        "fd_amount",
        "float_mv",
        "float_share",
        "free_float",
        "free_share",
        "h_total_ratio",
        "high",
        "high_limit",
        "hold_amount",
        "hold_change",
        "hold_float_ratio",
        "hold_ratio",
        "holder_num",
        "holding_amount",
        "last_parent_net",
        "limit_amount",
        "limit_order",
        "limit_up_suc_rate",
        "low",
        "low_limit",
        "mkv",
        "net_amount",
        "net_mf_amount",
        "net_mf_vol",
        "net_profit_max",
        "net_profit_min",
        "open",
        "p_change_max",
        "p_change_min",
        "p_total_ratio",
        "pb",
        "pct_chg",
        "pe",
        "pe_ttm",
        "pledge_count",
        "pledge_amount",
        "pledge_ratio",
        "pledged_amount",
        "pre_close",
        "price",
        "ps",
        "ps_ttm",
        "rank",
        "reg_capital",
        "ratio",
        "rest_pledge",
        "sell",
        "sell_amount",
        "sell_elg_amount",
        "sell_elg_vol",
        "sell_lg_amount",
        "sell_lg_vol",
        "sell_md_amount",
        "sell_md_vol",
        "sell_sm_amount",
        "sell_sm_vol",
        "stk_div",
        "stk_float_ratio",
        "stk_mkv_ratio",
        "total_mv",
        "total_share",
        "turnover_ratio",
        "turnover_rate",
        "turnover_rate_f",
        "unrest_pledge",
        "up_limit",
        "vol",
        "volume_ratio",
        "weight",
    }
)


@dataclass(frozen=True)
class DailyRefreshStepResult:
    name: str
    status: StepStatus
    duration_ms: int
    metadata: dict[str, Any]


@dataclass(frozen=True)
class DailyRefreshResult:
    partition_date: date
    steps: list[DailyRefreshStepResult]
    ok: bool


class DailyRefreshConfigError(RuntimeError):
    """Raised when the daily refresh environment is incomplete."""


class DailyRefreshStepError(RuntimeError):
    """Raised by a refresh step with structured failure metadata."""

    def __init__(self, message: str, metadata: Mapping[str, Any]) -> None:
        super().__init__(message)
        self.metadata = dict(metadata)


class DailyRefreshLockError(DailyRefreshStepError):
    """Raised when another refresh owns the same catalog/date critical section."""


@dataclass(frozen=True)
class _DailyRefreshLock:
    path: Path
    fd: int
    owner_token: str

    def release(self) -> None:
        try:
            if _refresh_lock_matches_owner(self.path, self.fd, self.owner_token):
                with contextlib.suppress(FileNotFoundError):
                    self.path.unlink()
        finally:
            with contextlib.suppress(OSError):
                os.close(self.fd)


@dataclass(frozen=True)
class _RefreshAssetPlan:
    assets: tuple[AssetSpec, ...]
    skipped_assets: tuple[dict[str, Any], ...]


class _JsonArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise ValueError(message)


class _MockTushareAdapter(FetchableAdapter):
    """Local fixture adapter used by CI and mock scheduler smoke tests."""

    def source_id(self) -> str:
        return "tushare"

    def get_assets(self) -> list[AssetSpec]:
        return list(TUSHARE_ASSETS)

    def get_resources(self) -> dict[str, Any]:
        return {"source_id": self.source_id(), "mode": "mock"}

    def get_staging_dbt_models(self) -> list[str]:
        return [f"stg_{asset.dataset}" for asset in TUSHARE_ASSETS]

    def get_quota_config(self) -> dict[str, Any]:
        return {"requests_per_minute": 1_000_000, "daily_credit_quota": None}

    def fetch(self, asset_id: str, params: FetchParams) -> pa.Table:
        asset = _asset_by_name(self.get_assets(), asset_id)
        partition_date = params.get("partition_date")
        if not isinstance(partition_date, date):
            msg = "mock adapter requires partition_date"
            raise ValueError(msg)
        return _mock_table(asset, partition_date)


def run_daily_refresh(
    partition_date: date,
    *,
    mock: bool = False,
    select: Sequence[str] | None = None,
    json_report: Path | None = None,
) -> DailyRefreshResult:
    """Run one daily refresh and optionally write a structured JSON report."""

    steps: list[DailyRefreshStepResult] = []

    try:
        settings = _load_settings()
        _prepare_runtime_paths(settings)
        adapter = _build_adapter(mock=mock)
        all_assets = adapter.get_assets()
        selected_assets = _select_assets(all_assets, select)
        refresh_plan = _refresh_asset_plan(selected_assets, partition_date, mock=mock)
        asset_specs = build_assets([adapter])
    except Exception as exc:
        _append_failed_step(steps, "config", exc, started_at=perf_counter())
        result = _result(partition_date, steps)
        _write_report_if_requested(json_report, result)
        return result

    if not refresh_plan.assets:
        skip_metadata = _no_refreshable_assets_metadata(
            mock=mock,
            asset_specs_count=len(asset_specs),
            skipped_assets=refresh_plan.skipped_assets,
        )
        _append_skipped_step(steps, "adapter", skip_metadata)
        for step_name in ("dbt_run", "dbt_test", "canonical", "raw_health"):
            _append_skipped_step(steps, step_name, skip_metadata)
        result = _result(partition_date, steps)
        _write_report_if_requested(json_report, result)
        return result

    lock_started_at = perf_counter()
    try:
        refresh_lock = _acquire_refresh_lock(settings, partition_date)
    except DailyRefreshLockError as exc:
        _append_failed_step(steps, "refresh_lock", exc, started_at=lock_started_at)
        result = _result(partition_date, steps)
        _write_report_if_requested(json_report, result)
        return result

    try:
        if not _append_step(
            steps,
            "adapter",
            lambda: _run_adapter_step(
                adapter,
                settings,
                partition_date,
                refresh_plan.assets,
                asset_specs_count=len(asset_specs),
                skipped_assets=refresh_plan.skipped_assets,
                mock=mock,
            ),
        ):
            result = _result(partition_date, steps)
            _write_report_if_requested(json_report, result)
            return result

        dbt_selectors = _dbt_selectors(refresh_plan.assets, all_assets)
        if not _append_step(
            steps,
            "dbt_run",
            lambda: _run_dbt_step(
                "run",
                settings,
                partition_date,
                selectors=dbt_selectors,
            ),
        ):
            result = _result(partition_date, steps)
            _write_report_if_requested(json_report, result)
            return result

        if not _append_step(
            steps,
            "dbt_test",
            lambda: _run_dbt_step(
                "test",
                settings,
                partition_date,
                selectors=dbt_selectors,
            ),
        ):
            result = _result(partition_date, steps)
            _write_report_if_requested(json_report, result)
            return result

        if not _append_step(
            steps,
            "canonical",
            lambda: _run_canonical_step(settings, refresh_plan.assets, all_assets),
        ):
            result = _result(partition_date, steps)
            _write_report_if_requested(json_report, result)
            return result

        _append_step(
            steps,
            "raw_health",
            lambda: _run_raw_health_step(
                settings,
                partition_date,
                refresh_plan.assets,
                source_id=adapter.source_id(),
            ),
        )
        result = _result(partition_date, steps)
        _write_report_if_requested(json_report, result)
        return result
    finally:
        refresh_lock.release()


def main(argv: Sequence[str] | None = None) -> int:
    parser = _JsonArgumentParser(description="Run the data-platform daily refresh.")
    parser.add_argument("--date", required=True, help="partition date in YYYYMMDD format")
    parser.add_argument("--mock", action="store_true", help="use local fixture adapter data")
    parser.add_argument("--select", help="comma-separated asset names or datasets")
    parser.add_argument("--json-report", type=Path, help="write a daily refresh JSON report")

    try:
        args = parser.parse_args(argv)
        partition_date = _parse_partition_date(args.date)
    except Exception as exc:
        print(f"Daily refresh failed: {exc}", file=sys.stderr)
        return 2

    result = run_daily_refresh(
        partition_date,
        mock=args.mock or _env_flag("DP_DAILY_REFRESH_MOCK"),
        select=_split_select(args.select),
        json_report=args.json_report,
    )
    if result.ok:
        return 0

    failed_step = next((step for step in result.steps if step.status == "failed"), None)
    detail = "unknown failure" if failed_step is None else failed_step.metadata.get("error", "")
    print(f"Daily refresh failed: {detail}", file=sys.stderr)
    return 2 if failed_step is not None and failed_step.name == "config" else 1


def _load_settings() -> Settings:
    try:
        return get_settings()
    except ValidationError as exc:
        missing = {
            str(error["loc"][0]).upper()
            for error in exc.errors()
            if error.get("type") == "missing" and error.get("loc")
        }
        if "PG_DSN" in missing:
            msg = "DP_PG_DSN is required for the PostgreSQL-backed Iceberg catalog"
            raise DailyRefreshConfigError(msg) from exc
        msg = "daily refresh settings are incomplete: " + ", ".join(sorted(missing))
        raise DailyRefreshConfigError(msg) from exc


def _prepare_runtime_paths(settings: Settings) -> None:
    settings.ensure_data_storage_directories()
    settings.iceberg_warehouse_path.expanduser().mkdir(parents=True, exist_ok=True)
    settings.duckdb_path.expanduser().parent.mkdir(parents=True, exist_ok=True)


def _build_adapter(*, mock: bool) -> FetchableAdapter:
    if mock:
        return _MockTushareAdapter()
    return TushareAdapter()


def _refresh_asset_plan(
    selected_assets: Sequence[AssetSpec],
    partition_date: date,
    *,
    mock: bool,
) -> _RefreshAssetPlan:
    refreshable_assets: list[AssetSpec] = []
    skipped_assets: list[dict[str, Any]] = []
    for asset in selected_assets:
        skip_metadata = _daily_refresh_skip_for_asset(
            asset,
            partition_date,
            mock=mock,
        )
        if skip_metadata is None:
            refreshable_assets.append(asset)
        else:
            skipped_assets.append(skip_metadata)
    return _RefreshAssetPlan(tuple(refreshable_assets), tuple(skipped_assets))


def _daily_refresh_skip_for_asset(
    asset: AssetSpec,
    partition_date: date,
    *,
    mock: bool,
) -> dict[str, Any] | None:
    if mock:
        return None
    if asset.dataset != HK_HOLD_DAILY_REFRESH_DATASET:
        return None
    if partition_date <= HK_HOLD_DAILY_PUBLICATION_LAST_DATE:
        return None

    return {
        "asset": asset.name,
        "dataset": asset.dataset,
        "source_interface_id": asset.metadata.get("source_interface_id", asset.dataset),
        "doc_api": asset.metadata.get("doc_api", "hk_hold"),
        "partition_date": f"{partition_date:%Y%m%d}",
        "status": "skipped",
        "reason_type": "daily_publication_discontinued",
        "reason": (
            "Tushare hk_hold daily northbound publication ended after "
            f"{HK_HOLD_DAILY_PUBLICATION_LAST_DATE:%Y-%m-%d}; the daily refresh "
            "does not fetch post-cutoff current-date hk_hold pages"
        ),
        "daily_publication_last_date": HK_HOLD_DAILY_PUBLICATION_LAST_DATE.isoformat(),
        "replacement_cadence": "quarterly_disclosure",
        "skip_policy": "fail_closed_no_daily_live_freshness_claim",
    }


def _no_refreshable_assets_metadata(
    *,
    mock: bool,
    asset_specs_count: int,
    skipped_assets: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    return {
        "mock": mock,
        "asset_specs_count": asset_specs_count,
        "artifact_count": 0,
        "artifacts": [],
        "skipped_assets": list(skipped_assets),
        "reason": "no refreshable assets remain after applying daily refresh gates",
    }


def _run_adapter_step(
    adapter: FetchableAdapter,
    settings: Settings,
    partition_date: date,
    selected_assets: Sequence[AssetSpec],
    *,
    asset_specs_count: int,
    skipped_assets: Sequence[Mapping[str, Any]] = (),
    mock: bool,
) -> dict[str, Any]:
    artifacts: list[RawArtifact] = []
    writer = RawWriter(
        settings.raw_zone_path,
        iceberg_warehouse_path=settings.iceberg_warehouse_path,
    )
    for asset in selected_assets:
        if mock:
            table = adapter.fetch(asset.name, {"partition_date": partition_date})
            artifacts.append(
                writer.write_arrow(
                    adapter.source_id(),
                    asset.dataset,
                    partition_date,
                    str(uuid4()),
                    table,
                    metadata=asset.metadata,
                    request_params={"partition_date": partition_date},
                )
            )
            continue
        artifacts.append(
            run_tushare_asset(
                asset.name,
                partition_date,
                params=_live_fetch_params_for_asset(asset),
                raw_writer=writer,
            )
        )

    return {
        "mock": mock,
        "asset_specs_count": asset_specs_count,
        "artifact_count": len(artifacts),
        "artifacts": [_raw_artifact_metadata(artifact) for artifact in artifacts],
        "skipped_assets": list(skipped_assets),
    }


def _run_dbt_step(
    command: Literal["run", "test"],
    settings: Settings,
    partition_date: date,
    *,
    selectors: Sequence[str],
) -> dict[str, Any]:
    profiles_dir = settings.duckdb_path.expanduser().parent / "daily_refresh_dbt_profiles"
    target_path = (
        settings.duckdb_path.expanduser().parent
        / "daily_refresh_dbt_target"
        / f"{command}_{partition_date:%Y%m%d}"
    )
    profiles_dir.mkdir(parents=True, exist_ok=True)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    _write_duckdb_profile(profiles_dir / "profiles.yml")

    args = [
        command,
        "--profiles-dir",
        str(profiles_dir),
        "--target-path",
        str(target_path),
        "--select",
        *selectors,
    ]
    return _run_dbt_command(args, settings)


def _run_dbt_command(args: Sequence[str], settings: Settings) -> dict[str, Any]:
    env = os.environ.copy()
    dbt_executable = _resolve_dbt_executable(env)
    if dbt_executable is None:
        msg = (
            "dbt executable is not installed; expected DP_DBT_EXECUTABLE, dbt on PATH, "
            ".venv-py312/bin/dbt, .venv-py313/bin/dbt, or .venv/bin/dbt"
        )
        raise DailyRefreshStepError(msg, {"error": msg, "error_type": "missing_dbt"})

    env.update(
        {
            "DP_DATA_STORAGE_ROOT_PATH": str(settings.data_storage_root_path),
            "DP_RAW_ZONE_PATH": str(settings.raw_zone_path),
            "DP_PROCESSED_DATA_PATH": str(settings.processed_data_path),
            "DP_DUCKDB_PATH": str(settings.duckdb_path),
            DBT_EXECUTABLE_ENV: dbt_executable,
            "DP_ICEBERG_WAREHOUSE_PATH": str(settings.iceberg_warehouse_path),
            "DP_PG_DSN": str(settings.pg_dsn),
            "PYTHONPATH": f"{PROJECT_ROOT / 'src'}{os.pathsep}{env.get('PYTHONPATH', '')}",
        }
    )
    process_args = [str(DBT_SCRIPT), *args]
    completed = subprocess.run(
        process_args,
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=300,
    )
    metadata = {
        "command": process_args,
        "dbt_executable": dbt_executable,
        "returncode": completed.returncode,
        "stdout_tail": _tail(completed.stdout),
        "stderr_tail": _tail(completed.stderr),
    }
    if completed.returncode != 0:
        msg = f"dbt command failed with exit code {completed.returncode}"
        metadata["error"] = msg
        metadata["error_type"] = "dbt_command_failed"
        raise DailyRefreshStepError(msg, metadata)
    return metadata


def _resolve_dbt_executable(env: Mapping[str, str] | None = None) -> str | None:
    environ = os.environ if env is None else env
    for key in (DBT_EXECUTABLE_ENV, DBT_BIN_ENV):
        explicit = environ.get(key)
        if explicit:
            return _which_executable(explicit, path=environ.get("PATH"))

    for candidate in (
        PROJECT_ROOT / ".venv-py312" / "bin" / "dbt",
        PROJECT_ROOT / ".venv-py313" / "bin" / "dbt",
    ):
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)

    path_dbt = shutil.which("dbt", path=environ.get("PATH"))
    if path_dbt is not None:
        return path_dbt

    local_dbt = PROJECT_ROOT / ".venv" / "bin" / "dbt"
    if local_dbt.is_file() and os.access(local_dbt, os.X_OK):
        return str(local_dbt)
    return None


def _live_fetch_params_for_asset(asset: AssetSpec) -> dict[str, Any] | None:
    if asset.dataset not in EXPLICIT_TS_CODE_RAW_DATASETS:
        return None

    ts_codes = _split_csv_env(TOP10_TS_CODES_ENV)
    if not ts_codes:
        msg = (
            f"Tushare {asset.dataset} live refresh requires explicit ts_code scope; "
            f"set {TOP10_TS_CODES_ENV} to a comma-separated symbol list or run the "
            "raw asset CLI with --ts-code"
        )
        raise DailyRefreshStepError(
            msg,
            {
                "error": msg,
                "error_type": "missing_required_fetch_scope",
                "asset": asset.name,
                "dataset": asset.dataset,
                "required_params": ["ts_code"],
                "config_env": TOP10_TS_CODES_ENV,
            },
        )
    return {EXPLICIT_TS_CODES_PARAM: ts_codes}


def _split_csv_env(name: str) -> tuple[str, ...]:
    value = os.environ.get(name)
    if value is None:
        return ()
    return tuple(part.strip() for part in value.split(",") if part.strip())


def _which_executable(candidate: str, *, path: str | None) -> str | None:
    resolved = shutil.which(candidate, path=path)
    if resolved is not None:
        return resolved
    candidate_path = Path(candidate).expanduser()
    if candidate_path.is_file() and os.access(candidate_path, os.X_OK):
        return str(candidate_path)
    return None


def _run_canonical_step(
    settings: Settings,
    selected_assets: Sequence[AssetSpec],
    all_assets: Sequence[AssetSpec],
) -> dict[str, Any]:
    migrations = MigrationRunner().apply_pending(str(settings.pg_dsn))
    resources = build_resources(settings)
    catalog = resources["iceberg_catalog"]
    ensure_namespaces(catalog, DEFAULT_NAMESPACES)
    ensure_tables(catalog, DEFAULT_TABLE_SPECS)

    selected_datasets = {asset.dataset for asset in selected_assets}
    all_datasets = {asset.dataset for asset in all_assets}
    write_results: list[WriteResult] = []
    skipped_writes: list[str] = []

    if selected_datasets == all_datasets:
        write_results.extend(
            load_canonical_v2_marts(
                catalog,
                Path(resources["duckdb_path"]),
            )
        )
    else:
        skipped_writes.append("canonical_v2.canonical_marts")

    return {
        "applied_migrations": migrations,
        "ensured_tables": [f"{spec.namespace}.{spec.name}" for spec in DEFAULT_TABLE_SPECS],
        "write_results": [_write_result_metadata(result) for result in write_results],
        "skipped_writes": skipped_writes,
    }


def _acquire_refresh_lock(
    settings: Settings,
    partition_date: date,
) -> _DailyRefreshLock:
    lock_path = _refresh_lock_path(settings, partition_date)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    owner_token = uuid4().hex
    payload = {
        "catalog": settings.iceberg_catalog_name,
        "host": socket.gethostname(),
        "owner_token": owner_token,
        "partition_date": f"{partition_date:%Y%m%d}",
        "pid": os.getpid(),
        "acquired_at": datetime.now(UTC).isoformat(timespec="seconds"),
    }
    flags = os.O_CREAT | os.O_EXCL | os.O_RDWR
    fd: int | None = None
    for attempt in range(2):
        try:
            fd = os.open(lock_path, flags, 0o600)
            break
        except FileExistsError as exc:
            owner_metadata = _read_refresh_lock_owner(lock_path)
            if attempt == 0 and _refresh_lock_is_reclaimable(owner_metadata):
                with contextlib.suppress(FileNotFoundError):
                    lock_path.unlink()
                continue

            metadata: dict[str, Any] = {
                "error": "daily refresh already running for catalog/date",
                "error_type": "refresh_lock_held",
                "catalog": settings.iceberg_catalog_name,
                "partition_date": f"{partition_date:%Y%m%d}",
                "lock_path": str(lock_path),
                "lock_owner": owner_metadata,
            }
            raise DailyRefreshLockError(metadata["error"], metadata) from exc
    if fd is None:
        msg = f"refresh lock could not be acquired: {lock_path}"
        raise DailyRefreshLockError(msg, {"error": msg, "error_type": "refresh_lock_failed"})

    try:
        os.write(fd, (json.dumps(payload, sort_keys=True) + "\n").encode("utf-8"))
    except Exception:
        with contextlib.suppress(OSError):
            os.close(fd)
        with contextlib.suppress(FileNotFoundError):
            lock_path.unlink()
        raise
    return _DailyRefreshLock(path=lock_path, fd=fd, owner_token=owner_token)


def _read_refresh_lock_owner(lock_path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(lock_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"parse_error": str(exc)}
    if not isinstance(payload, dict):
        return {"parse_error": "refresh lock payload must be a JSON object"}
    return payload


def _read_refresh_lock_owner_from_fd(fd: int) -> dict[str, Any]:
    try:
        size = max(os.fstat(fd).st_size, 1)
        payload = json.loads(os.pread(fd, size, 0).decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return {"parse_error": str(exc)}
    if not isinstance(payload, dict):
        return {"parse_error": "refresh lock payload must be a JSON object"}
    return payload


def _refresh_lock_matches_owner(lock_path: Path, fd: int, owner_token: str) -> bool:
    try:
        fd_stat = os.fstat(fd)
        path_stat = lock_path.stat()
    except (OSError, FileNotFoundError):
        return False
    if (fd_stat.st_dev, fd_stat.st_ino) != (path_stat.st_dev, path_stat.st_ino):
        return False
    owner_metadata = _read_refresh_lock_owner_from_fd(fd)
    return owner_metadata.get("owner_token") == owner_token


def _refresh_lock_is_reclaimable(owner_metadata: Mapping[str, Any]) -> bool:
    owner_host = owner_metadata.get("host")
    owner_pid = owner_metadata.get("pid")
    if owner_host != socket.gethostname() or not isinstance(owner_pid, int):
        return False
    if _process_is_alive(owner_pid):
        return False

    acquired_at = _parse_lock_acquired_at(owner_metadata.get("acquired_at"))
    if acquired_at is None:
        return True
    stale_after = _refresh_lock_stale_after()
    return datetime.now(UTC) - acquired_at > stale_after


def _parse_lock_acquired_at(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _refresh_lock_stale_after() -> timedelta:
    value = os.environ.get(REFRESH_LOCK_STALE_SECONDS_ENV)
    if value is None:
        return DEFAULT_REFRESH_LOCK_STALE_AFTER
    try:
        seconds = int(value)
    except ValueError:
        return DEFAULT_REFRESH_LOCK_STALE_AFTER
    if seconds < 1:
        return DEFAULT_REFRESH_LOCK_STALE_AFTER
    return timedelta(seconds=seconds)


def _process_is_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _refresh_lock_path(settings: Settings, partition_date: date) -> Path:
    key = f"{settings.iceberg_catalog_name}:{partition_date:%Y%m%d}"
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:24]
    return (
        settings.iceberg_warehouse_path.expanduser()
        / "_daily_refresh_locks"
        / f"{digest}.lock"
    )


def _run_raw_health_step(
    settings: Settings,
    partition_date: date,
    selected_assets: Sequence[AssetSpec],
    *,
    source_id: str,
) -> dict[str, Any]:
    checked_artifacts = 0
    issue_payloads: list[dict[str, Any]] = []
    for asset in selected_assets:
        report = check_raw_zone(
            settings.raw_zone_path,
            source_id=source_id,
            dataset=asset.dataset,
            partition_date=partition_date,
            deep=True,
        )
        checked_artifacts += report.checked_artifacts
        issue_payloads.extend(
            {
                "severity": issue.severity,
                "path": str(issue.path),
                "code": issue.code,
                "message": issue.message,
            }
            for issue in report.issues
        )

    if any(issue["severity"] == "error" for issue in issue_payloads):
        msg = "Raw Zone health check failed"
        raise DailyRefreshStepError(
            msg,
            {
                "error": msg,
                "error_type": "raw_health_failed",
                "checked_artifacts": checked_artifacts,
                "issues": issue_payloads,
            },
        )

    return {
        "checked_artifacts": checked_artifacts,
        "issues": issue_payloads,
    }


def _append_step(
    steps: list[DailyRefreshStepResult],
    name: str,
    callback: Any,
) -> bool:
    started_at = perf_counter()
    try:
        metadata = callback()
    except Exception as exc:
        _append_failed_step(steps, name, exc, started_at=started_at)
        return False

    steps.append(
        DailyRefreshStepResult(
            name=name,
            status="ok",
            duration_ms=_duration_ms(started_at),
            metadata=_json_safe(metadata),
        )
    )
    return True


def _append_skipped_step(
    steps: list[DailyRefreshStepResult],
    name: str,
    metadata: Mapping[str, Any],
) -> None:
    steps.append(
        DailyRefreshStepResult(
            name=name,
            status="skipped",
            duration_ms=0,
            metadata=_json_safe(metadata),
        )
    )


def _append_failed_step(
    steps: list[DailyRefreshStepResult],
    name: str,
    exc: BaseException,
    *,
    started_at: float,
) -> None:
    metadata: dict[str, Any] = {
        "error": str(exc),
        "error_type": type(exc).__name__,
    }
    if isinstance(exc, DailyRefreshStepError):
        metadata.update(exc.metadata)
    steps.append(
        DailyRefreshStepResult(
            name=name,
            status="failed",
            duration_ms=_duration_ms(started_at),
            metadata=_json_safe(metadata),
        )
    )


def _result(partition_date: date, steps: list[DailyRefreshStepResult]) -> DailyRefreshResult:
    return DailyRefreshResult(
        partition_date=partition_date,
        steps=steps,
        ok=not any(step.status == "failed" for step in steps),
    )


def _select_assets(
    assets: Sequence[AssetSpec],
    select: Sequence[str] | None,
) -> list[AssetSpec]:
    tokens = _normalize_select(select)
    if not tokens:
        return list(assets)

    by_name_or_dataset: dict[str, AssetSpec] = {}
    for asset in assets:
        by_name_or_dataset[asset.name] = asset
        by_name_or_dataset[asset.dataset] = asset

    selected: list[AssetSpec] = []
    unknown: list[str] = []
    for token in tokens:
        matched_asset = by_name_or_dataset.get(token)
        if matched_asset is None:
            unknown.append(token)
            continue
        if matched_asset not in selected:
            selected.append(matched_asset)

    if unknown:
        msg = "unknown daily refresh asset selector(s): " + ", ".join(unknown)
        raise ValueError(msg)
    if not selected:
        msg = "daily refresh select resolved to no assets"
        raise ValueError(msg)
    return selected


def _dbt_selectors(
    selected_assets: Sequence[AssetSpec],
    all_assets: Sequence[AssetSpec],
) -> tuple[str, ...]:
    selected_datasets = {asset.dataset for asset in selected_assets}
    all_datasets = {asset.dataset for asset in all_assets}
    if selected_datasets == all_datasets:
        return DEFAULT_DBT_SELECTORS
    return tuple(f"stg_{asset.dataset}" for asset in selected_assets)


def _normalize_select(select: Sequence[str] | None) -> list[str]:
    if select is None:
        return []
    tokens: list[str] = []
    for item in select:
        tokens.extend(part.strip() for part in str(item).split(","))
    return [token for token in tokens if token]


def _split_select(value: str | None) -> list[str] | None:
    if value is None:
        return None
    return _normalize_select([value])


def _asset_by_name(assets: Sequence[AssetSpec], asset_id: str) -> AssetSpec:
    for asset in assets:
        if asset.name == asset_id:
            return asset
    msg = f"unknown mock asset: {asset_id!r}"
    raise ValueError(msg)


def _mock_table(asset: AssetSpec, partition_date: date) -> pa.Table:
    return pa.table(
        {
            field.name: [_mock_value(asset.dataset, field, partition_date)]
            for field in asset.schema
        },
        schema=asset.schema,
    )


def _mock_value(dataset: str, field: pa.Field, partition_date: date) -> Any:
    if field.name in DATE_FIELD_NAMES:
        return _mock_date_value(dataset, field.name, partition_date)
    if field.name == "ts_code":
        if dataset == "fund_portfolio":
            return "001753.OF"
        if dataset in {"index_basic", "index_daily"}:
            return "000300.SH"
        return "000001.SZ"
    if field.name == "index_code":
        return "000300.SH"
    if field.name == "con_code":
        return "000001.SZ"
    if field.name == "exchange":
        return "SSE"
    if field.name == "symbol":
        if dataset == "fund_portfolio":
            return "000001.SZ"
        return "000001"
    if field.name == "list_status":
        return "L"
    if field.name in {"report_type", "comp_type", "is_open"}:
        return "1"
    if field.name == "rank":
        return "1"
    if field.name == "update_flag":
        return "0"
    if field.name == "url":
        return "https://example.test/tushare-fixture"
    if field.name == "rec_time":
        return "10:30:00"
    if field.name in STRING_NUMERIC_FIELD_NAMES:
        return "1.123456789012345678"
    if pa.types.is_decimal(field.type):
        return Decimal("1.123456789012345678")
    return f"{field.name}-fixture"


def _mock_date_value(dataset: str, field_name: str, partition_date: date) -> str | None:
    if dataset == "stock_basic" and field_name == "delist_date":
        return None
    if dataset in {"income", "balancesheet", "cashflow", "fina_indicator"}:
        if field_name == "end_date":
            return f"{partition_date.replace(day=1) - timedelta(days=1):%Y%m%d}"
        if field_name == "f_ann_date":
            return f"{partition_date + timedelta(days=1):%Y%m%d}"
    return f"{partition_date:%Y%m%d}"


def _write_duckdb_profile(path: Path) -> None:
    path.write_text(
        """
data_platform:
  target: daily_refresh
  outputs:
    daily_refresh:
      type: duckdb
      path: "{{ env_var('DP_DUCKDB_PATH') }}"
      threads: 1
""".lstrip(),
        encoding="utf-8",
    )


def _parse_partition_date(value: str) -> date:
    try:
        parsed = datetime.strptime(value, DATE_FORMAT).date()
    except ValueError as exc:
        msg = f"date must use YYYYMMDD format: {value!r}"
        raise ValueError(msg) from exc
    if f"{parsed:%Y%m%d}" != value:
        msg = f"date must use YYYYMMDD format: {value!r}"
        raise ValueError(msg)
    return parsed


def _write_report_if_requested(json_report: Path | None, result: DailyRefreshResult) -> None:
    if json_report is None:
        return
    json_report.expanduser().parent.mkdir(parents=True, exist_ok=True)
    json_report.expanduser().write_text(
        json.dumps(_result_to_dict(result), ensure_ascii=False, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )


def _result_to_dict(result: DailyRefreshResult) -> dict[str, Any]:
    return {
        "partition_date": result.partition_date.isoformat(),
        "ok": result.ok,
        "steps": [
            {
                "name": step.name,
                "status": step.status,
                "duration_ms": step.duration_ms,
                "metadata": _json_safe(step.metadata),
            }
            for step in result.steps
        ],
    }


def _raw_artifact_metadata(artifact: RawArtifact) -> dict[str, Any]:
    parsed_run_id = UUID(artifact.run_id)
    return {
        "source_id": artifact.source_id,
        "dataset": artifact.dataset,
        "partition_date": artifact.partition_date.isoformat(),
        "run_id": artifact.run_id,
        "run_id_version": parsed_run_id.version,
        "path": str(artifact.path),
        "row_count": artifact.row_count,
        "written_at": artifact.written_at.isoformat(),
        "metadata": artifact.metadata,
    }


def _write_result_metadata(result: WriteResult) -> dict[str, Any]:
    return asdict(result)


def _json_safe(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return _json_safe(asdict(value))
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_json_safe(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, str | int | float | bool) or value is None:
        return value
    return str(value)


def _tail(value: str, *, max_lines: int = 40) -> str:
    lines = value.splitlines()
    return "\n".join(lines[-max_lines:])


def _duration_ms(started_at: float) -> int:
    return int((perf_counter() - started_at) * 1000)


def _env_flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in TRUTHY_VALUES


__all__ = [
    "DailyRefreshResult",
    "DailyRefreshStepResult",
    "main",
    "run_daily_refresh",
]


if __name__ == "__main__":
    raise SystemExit(main())
