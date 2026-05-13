#!/usr/bin/env python3
"""Copy a bounded slice of the external Tushare corpus into Raw Zone.

This is not a live Tushare-token ingestion path. It is an explicitly named
corpus-backed bridge for proving that mounted real corpus data can be shaped
as data-platform Raw Zone artifacts.
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from collections import defaultdict
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Iterable, Sequence

import pandas as pd
import pyarrow as pa  # type: ignore[import-untyped]

from data_platform.adapters.tushare.assets import (
    TUSHARE_BAR_SCHEMA,
    TUSHARE_STOCK_BASIC_SCHEMA,
    TUSHARE_TRADE_CAL_SCHEMA,
)
from data_platform.raw import RawWriter


DEFAULT_CORPUS_ROOT = Path("/Volumes/dockcase2tb/database_all")
DEFAULT_DATASETS = ("stock_basic", "daily", "trade_cal")
DATASET_PATHS = {
    "stock_basic": Path("股票数据/基础数据/股票列表/all.csv"),
    "daily": Path("股票数据/行情数据/历史日线/by_symbol"),
    "trade_cal": Path("股票数据/基础数据/交易日历/all.csv"),
}
DATASET_SCHEMAS = {
    "stock_basic": TUSHARE_STOCK_BASIC_SCHEMA,
    "daily": TUSHARE_BAR_SCHEMA,
    "trade_cal": TUSHARE_TRADE_CAL_SCHEMA,
}


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    result = run_corpus_bridge(
        corpus_root=args.corpus_root,
        raw_zone_path=args.raw_zone_path,
        iceberg_warehouse_path=args.iceberg_warehouse_path,
        dates=_split_csv(args.dates),
        symbols=_split_csv(args.symbols),
        datasets=_split_csv(args.datasets),
        source_id=args.source_id,
    )
    _write_json(args.json_report, result)
    if args.print_json:
        json.dump(result, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
        sys.stdout.write("\n")
    return 0 if result["summary"]["status"] == "ok" else 2


def run_corpus_bridge(
    *,
    corpus_root: Path,
    raw_zone_path: Path,
    iceberg_warehouse_path: Path,
    dates: Sequence[str],
    symbols: Sequence[str],
    datasets: Sequence[str],
    source_id: str,
) -> dict[str, Any]:
    corpus_root = corpus_root.expanduser().resolve(strict=False)
    raw_zone_path = raw_zone_path.expanduser().resolve(strict=False)
    iceberg_warehouse_path = iceberg_warehouse_path.expanduser().resolve(strict=False)

    if not dates:
        return _blocked_result(
            corpus_root=corpus_root,
            raw_zone_path=raw_zone_path,
            iceberg_warehouse_path=iceberg_warehouse_path,
            dates=dates,
            symbols=symbols,
            datasets=datasets,
            source_id=source_id,
            errors=["at least one date is required"],
        )

    writer = RawWriter(
        raw_zone_path=raw_zone_path,
        iceberg_warehouse_path=iceberg_warehouse_path,
    )
    artifacts: list[dict[str, Any]] = []
    errors: list[str] = []

    for dataset in datasets:
        if dataset not in DATASET_PATHS:
            errors.append(f"unsupported dataset: {dataset}")
            continue
        try:
            artifacts.extend(
                _write_dataset(
                    writer=writer,
                    corpus_root=corpus_root,
                    dataset=dataset,
                    dates=dates,
                    symbols=symbols,
                    source_id=source_id,
                )
            )
        except Exception as exc:
            errors.append(f"{dataset}: {exc}")

    return _result_payload(
        corpus_root=corpus_root,
        raw_zone_path=raw_zone_path,
        iceberg_warehouse_path=iceberg_warehouse_path,
        dates=dates,
        symbols=symbols,
        datasets=datasets,
        source_id=source_id,
        artifacts=artifacts,
        errors=errors,
    )


def _blocked_result(
    *,
    corpus_root: Path,
    raw_zone_path: Path,
    iceberg_warehouse_path: Path,
    dates: Sequence[str],
    symbols: Sequence[str],
    datasets: Sequence[str],
    source_id: str,
    errors: list[str],
) -> dict[str, Any]:
    return _result_payload(
        corpus_root=corpus_root,
        raw_zone_path=raw_zone_path,
        iceberg_warehouse_path=iceberg_warehouse_path,
        dates=dates,
        symbols=symbols,
        datasets=datasets,
        source_id=source_id,
        artifacts=[],
        errors=errors,
    )


def _result_payload(
    *,
    corpus_root: Path,
    raw_zone_path: Path,
    iceberg_warehouse_path: Path,
    dates: Sequence[str],
    symbols: Sequence[str],
    datasets: Sequence[str],
    source_id: str,
    artifacts: list[dict[str, Any]],
    errors: list[str],
) -> dict[str, Any]:
    return {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "mode": "corpus_backed_raw_zone_probe",
        "live_tushare_token_used": False,
        "corpus_root": str(corpus_root),
        "raw_zone_path": str(raw_zone_path),
        "iceberg_warehouse_path": str(iceberg_warehouse_path),
        "scope": {
            "dates": list(dates),
            "symbols": list(symbols),
            "datasets": list(datasets),
            "source_id": source_id,
        },
        "artifacts": artifacts,
        "errors": errors,
        "summary": {
            "status": "ok" if not errors else "blocked",
            "artifact_count": len(artifacts),
            "row_count": sum(int(item["row_count"]) for item in artifacts),
            "missing_dataset_or_mapping": errors,
        },
    }


def _write_dataset(
    *,
    writer: RawWriter,
    corpus_root: Path,
    dataset: str,
    dates: Sequence[str],
    symbols: Sequence[str],
    source_id: str,
) -> list[dict[str, Any]]:
    if dataset == "stock_basic":
        frame = _read_stock_basic(corpus_root, symbols)
        return [_write_frame(writer, source_id, dataset, dates[0], frame)]
    if dataset == "daily":
        frame = _read_daily(corpus_root, dates, symbols)
        return [
            _write_frame(writer, source_id, dataset, partition_date, partition_frame)
            for partition_date, partition_frame in _group_by_partition(frame, "trade_date")
        ]
    if dataset == "trade_cal":
        frame = _read_trade_cal(corpus_root, dates)
        return [
            _write_frame(writer, source_id, dataset, partition_date, partition_frame)
            for partition_date, partition_frame in _group_by_partition(frame, "cal_date")
        ]
    raise ValueError(f"unsupported dataset: {dataset}")


def _read_stock_basic(corpus_root: Path, symbols: Sequence[str]) -> pd.DataFrame:
    path = corpus_root / DATASET_PATHS["stock_basic"]
    frame = pd.read_csv(path, dtype=str).fillna("")
    frame = frame[frame["ts_code"].isin(symbols)]
    if frame.empty:
        raise ValueError("no requested symbols found in stock_basic corpus")
    return _align_frame(frame, TUSHARE_STOCK_BASIC_SCHEMA)


def _read_daily(corpus_root: Path, dates: Sequence[str], symbols: Sequence[str]) -> pd.DataFrame:
    by_symbol = corpus_root / DATASET_PATHS["daily"]
    frames: list[pd.DataFrame] = []
    for symbol in symbols:
        matches = sorted(by_symbol.glob(f"{symbol}+*.csv"))
        if not matches:
            raise ValueError(f"missing by_symbol file for {symbol}")
        frame = pd.read_csv(matches[0], dtype=str).fillna("")
        frame = frame[frame["trade_date"].isin(dates)]
        if not frame.empty:
            frames.append(frame)
    if not frames:
        raise ValueError("no daily rows found for requested dates/symbols")
    return _align_frame(pd.concat(frames, ignore_index=True), TUSHARE_BAR_SCHEMA)


def _read_trade_cal(corpus_root: Path, dates: Sequence[str]) -> pd.DataFrame:
    path = corpus_root / DATASET_PATHS["trade_cal"]
    frame = pd.read_csv(path, dtype=str).fillna("")
    frame = frame[frame["cal_date"].isin(dates)]
    if frame.empty:
        raise ValueError("no trade_cal rows found for requested dates")
    return _align_frame(frame, TUSHARE_TRADE_CAL_SCHEMA)


def _align_frame(frame: pd.DataFrame, schema: pa.Schema) -> pd.DataFrame:
    aligned = pd.DataFrame()
    for field in schema:
        aligned[field.name] = frame[field.name].astype(str) if field.name in frame else ""
    return aligned


def _group_by_partition(frame: pd.DataFrame, column: str) -> Iterable[tuple[str, pd.DataFrame]]:
    grouped: dict[str, list[int]] = defaultdict(list)
    for index, value in enumerate(frame[column].astype(str)):
        grouped[value].append(index)
    for partition_date in sorted(grouped):
        yield partition_date, frame.iloc[grouped[partition_date]].reset_index(drop=True)


def _write_frame(
    writer: RawWriter,
    source_id: str,
    dataset: str,
    partition_date: str,
    frame: pd.DataFrame,
) -> dict[str, Any]:
    schema = DATASET_SCHEMAS[dataset]
    table = pa.Table.from_pandas(frame, schema=schema, preserve_index=False)
    artifact = writer.write_arrow(
        source_id=source_id,
        dataset=dataset,
        partition_date=_parse_date(partition_date),
        run_id=str(uuid.uuid4()),
        table=table,
    )
    return {
        "source_id": artifact.source_id,
        "dataset": artifact.dataset,
        "partition_date": artifact.partition_date.isoformat(),
        "path": str(artifact.path),
        "row_count": artifact.row_count,
    }


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus-root", type=Path, default=DEFAULT_CORPUS_ROOT)
    parser.add_argument("--raw-zone-path", type=Path, required=True)
    parser.add_argument("--iceberg-warehouse-path", type=Path, required=True)
    parser.add_argument("--dates", required=True)
    parser.add_argument("--symbols", required=True)
    parser.add_argument("--datasets", default=",".join(DEFAULT_DATASETS))
    parser.add_argument("--source-id", default="tushare")
    parser.add_argument("--json-report", type=Path, required=True)
    parser.add_argument("--print-json", action="store_true")
    return parser.parse_args(argv)


def _split_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _parse_date(value: str) -> date:
    return date(int(value[0:4]), int(value[4:6]), int(value[6:8]))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    raise SystemExit(main())
