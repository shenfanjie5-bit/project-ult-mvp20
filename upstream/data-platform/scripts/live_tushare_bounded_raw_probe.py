#!/usr/bin/env python3
"""Run a bounded live Tushare Raw Zone probe without PostgreSQL.

The probe is intentionally narrower than daily_refresh: it writes Raw Zone
artifacts for a small date/symbol/dataset scope and records the exact live
scope used. It never prints the Tushare token.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from collections.abc import Sequence
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pyarrow as pa  # type: ignore[import-untyped]

from data_platform.adapters.base import AssetSpec
from data_platform.adapters.tushare.adapter import (
    TOKEN_ENV_VAR,
    AdapterConfigError,
    TushareAdapter,
)
from data_platform.raw import RawArtifact, RawWriter

DEFAULT_DATE = "20260415"
DEFAULT_SYMBOLS = ("600519.SH", "000001.SZ")
DEFAULT_DATASETS = ("daily", "trade_cal")
SUPPORTED_DATASETS = ("stock_basic", "daily", "trade_cal")


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        report = run_probe(
            partition_date=_parse_date(args.date),
            symbols=_split_csv(args.symbols),
            datasets=_split_csv(args.datasets),
            raw_zone_path=args.raw_zone_path,
            iceberg_warehouse_path=args.iceberg_warehouse_path,
        )
    except Exception as exc:
        payload = {
            "ok": False,
            "error": str(exc),
            "error_type": type(exc).__name__,
            "live_tushare_token_used": bool(os.environ.get(TOKEN_ENV_VAR)),
        }
        _write_json(args.json_report, payload)
        if args.print_json:
            json.dump(payload, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
            sys.stdout.write("\n")
        return 2

    _write_json(args.json_report, report)
    if args.print_json:
        json.dump(report, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
        sys.stdout.write("\n")
    return 0 if report["ok"] else 1


def run_probe(
    *,
    partition_date: date,
    symbols: Sequence[str],
    datasets: Sequence[str],
    raw_zone_path: Path,
    iceberg_warehouse_path: Path,
    adapter: TushareAdapter | None = None,
) -> dict[str, Any]:
    _validate_symbols(symbols)
    normalized_datasets = _validate_datasets(datasets)

    token_present = bool(os.environ.get(TOKEN_ENV_VAR))
    if adapter is None and not token_present:
        raise AdapterConfigError(f"{TOKEN_ENV_VAR} is required for live bounded probe")

    adapter = adapter or TushareAdapter()
    writer = RawWriter(
        raw_zone_path=raw_zone_path,
        iceberg_warehouse_path=iceberg_warehouse_path,
    )
    assets_by_dataset = {asset.dataset: asset for asset in adapter.get_assets()}
    dataset_results: list[dict[str, Any]] = []

    for dataset in normalized_datasets:
        asset = assets_by_dataset[dataset]
        if dataset == "daily":
            dataset_results.append(
                _run_daily_probe(adapter, writer, asset, partition_date, symbols)
            )
        elif dataset == "trade_cal":
            dataset_results.append(_run_trade_cal_probe(adapter, writer, asset, partition_date))
        elif dataset == "stock_basic":
            dataset_results.append(
                _run_stock_basic_probe(adapter, writer, asset, partition_date, symbols)
            )

    artifact_paths = [
        path
        for result in dataset_results
        for path in result.get("artifact_paths", [])
    ]
    return {
        "ok": all(result["status"] == "ok" for result in dataset_results),
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "mode": "live_tushare_bounded_raw_probe",
        "live_tushare_token_used": token_present,
        "scope": {
            "date": f"{partition_date:%Y%m%d}",
            "symbols": list(symbols),
            "datasets": normalized_datasets,
        },
        "raw_zone_path": str(raw_zone_path),
        "iceberg_warehouse_path": str(iceberg_warehouse_path),
        "artifact_paths": artifact_paths,
        "datasets": dataset_results,
        "integration_notes": {
            "pg_required": False,
            "daily_refresh_selected_assets": True,
            "daily_refresh_symbol_filter": False,
            "raw_zone_artifacts_dbt_source_compatible": True,
            "dbt_or_canonical_executed": False,
        },
    }


def _run_daily_probe(
    adapter: TushareAdapter,
    writer: RawWriter,
    asset: AssetSpec,
    partition_date: date,
    symbols: Sequence[str],
) -> dict[str, Any]:
    trade_date = f"{partition_date:%Y%m%d}"
    tables: list[pa.Table] = []
    calls: list[dict[str, Any]] = []
    for symbol in symbols:
        params = {"ts_code": symbol, "trade_date": trade_date}
        table = adapter.fetch(asset.name, params)
        tables.append(table)
        calls.append(
            {
                "params": params,
                "supports_symbol_filter": True,
                "symbol_filter_applied": True,
                "row_count": table.num_rows,
            }
        )

    combined = _concat_or_empty(tables, asset.schema)
    artifact = writer.write_arrow(
        adapter.source_id(),
        asset.dataset,
        partition_date,
        str(uuid.uuid4()),
        combined,
    )
    return _dataset_result(
        asset.dataset,
        artifact,
        upstream_row_count=sum(call["row_count"] for call in calls),
        request_count=len(calls),
        calls=calls,
        supports_symbol_filter=True,
        symbol_filter_applied=True,
        bounded_strategy="per-symbol ts_code + single trade_date",
    )


def _run_trade_cal_probe(
    adapter: TushareAdapter,
    writer: RawWriter,
    asset: AssetSpec,
    partition_date: date,
) -> dict[str, Any]:
    cal_date = f"{partition_date:%Y%m%d}"
    params = {"start_date": cal_date, "end_date": cal_date}
    table = adapter.fetch(asset.name, params)
    artifact = writer.write_arrow(
        adapter.source_id(),
        asset.dataset,
        partition_date,
        str(uuid.uuid4()),
        table,
    )
    return _dataset_result(
        asset.dataset,
        artifact,
        upstream_row_count=table.num_rows,
        request_count=1,
        calls=[
            {
                "params": params,
                "supports_symbol_filter": False,
                "symbol_filter_applied": False,
                "row_count": table.num_rows,
            }
        ],
        supports_symbol_filter=False,
        symbol_filter_applied=False,
        bounded_strategy="single-day start_date=end_date; no symbol dimension",
    )


def _run_stock_basic_probe(
    adapter: TushareAdapter,
    writer: RawWriter,
    asset: AssetSpec,
    partition_date: date,
    symbols: Sequence[str],
) -> dict[str, Any]:
    params = {"list_status": "L"}
    table = adapter.fetch(asset.name, params)
    bounded_table = _filter_table_to_symbols(table, symbols)
    artifact = writer.write_arrow(
        adapter.source_id(),
        asset.dataset,
        partition_date,
        str(uuid.uuid4()),
        bounded_table,
    )
    return _dataset_result(
        asset.dataset,
        artifact,
        upstream_row_count=table.num_rows,
        request_count=1,
        calls=[
            {
                "params": params,
                "supports_symbol_filter": False,
                "symbol_filter_applied": False,
                "post_fetch_symbol_filter_applied": True,
                "row_count": bounded_table.num_rows,
                "upstream_row_count": table.num_rows,
            }
        ],
        supports_symbol_filter=False,
        symbol_filter_applied=False,
        bounded_strategy=(
            "Tushare stock_basic has no ts_code request filter; fetched active listings "
            "with list_status=L and wrote only requested symbols"
        ),
    )


def _dataset_result(
    dataset: str,
    artifact: RawArtifact,
    *,
    upstream_row_count: int,
    request_count: int,
    calls: list[dict[str, Any]],
    supports_symbol_filter: bool,
    symbol_filter_applied: bool,
    bounded_strategy: str,
) -> dict[str, Any]:
    return {
        "dataset": dataset,
        "status": "ok",
        "supports_symbol_filter": supports_symbol_filter,
        "symbol_filter_applied": symbol_filter_applied,
        "bounded_strategy": bounded_strategy,
        "request_count": request_count,
        "upstream_row_count": upstream_row_count,
        "row_count": artifact.row_count,
        "artifact_paths": [str(artifact.path)],
        "manifest_path": str(artifact.path.parent / "_manifest.json"),
        "calls": calls,
    }


def _concat_or_empty(tables: Sequence[pa.Table], schema: pa.Schema) -> pa.Table:
    non_empty = [table for table in tables if table.num_rows > 0]
    if not non_empty:
        return pa.table({field.name: [] for field in schema}, schema=schema)
    return pa.concat_tables(non_empty, promote_options="none")


def _filter_table_to_symbols(table: pa.Table, symbols: Sequence[str]) -> pa.Table:
    symbol_set = set(symbols)
    rows = [row for row in table.to_pylist() if row.get("ts_code") in symbol_set]
    return pa.table(
        {field.name: [row[field.name] for row in rows] for field in table.schema},
        schema=table.schema,
    )


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", default=DEFAULT_DATE, help="Raw partition date in YYYYMMDD")
    parser.add_argument("--symbols", default=",".join(DEFAULT_SYMBOLS))
    parser.add_argument("--datasets", default=",".join(DEFAULT_DATASETS))
    parser.add_argument("--raw-zone-path", type=Path, required=True)
    parser.add_argument("--iceberg-warehouse-path", type=Path, required=True)
    parser.add_argument("--json-report", type=Path, required=True)
    parser.add_argument("--print-json", action="store_true")
    return parser.parse_args(argv)


def _parse_date(value: str) -> date:
    try:
        parsed = datetime.strptime(value, "%Y%m%d").date()
    except ValueError as exc:
        raise ValueError(f"date must use YYYYMMDD format: {value!r}") from exc
    if f"{parsed:%Y%m%d}" != value:
        raise ValueError(f"date must use YYYYMMDD format: {value!r}")
    return parsed


def _split_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _validate_symbols(symbols: Sequence[str]) -> None:
    if not symbols:
        raise ValueError("at least one symbol is required")


def _validate_datasets(datasets: Sequence[str]) -> list[str]:
    if not datasets:
        raise ValueError("at least one dataset is required")
    unsupported = [dataset for dataset in datasets if dataset not in SUPPORTED_DATASETS]
    if unsupported:
        raise ValueError(
            "unsupported bounded Tushare dataset(s): "
            + ", ".join(unsupported)
            + "; supported: "
            + ", ".join(SUPPORTED_DATASETS)
        )
    return list(dict.fromkeys(datasets))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    raise SystemExit(main())
