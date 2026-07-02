#!/usr/bin/env python3
"""Audit semantic quality for selected A-share DockCase source datasets.

This is intentionally narrower than ``audit_data_catalog.py``. It reads actual
rows from high-value A-share datasets that feed profiles, factors, and score
components, then checks whether key fields are present, parseable, non-empty,
and internally consistent for a bounded symbol sample.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import time
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Iterable


DEFAULT_DATA_ROOT = "/Volumes/dockcase2tb/database_all"
DEFAULT_SYMBOLS = ("000001.SZ", "300750.SZ", "600519.SH")
TS_CODE_RE = re.compile(r"^\d{6}\.(SZ|SH|BJ)$")


@dataclass(frozen=True)
class DatasetConfig:
    dataset_id: str
    label: str
    relative_path: str
    kind: str
    required_columns: tuple[str, ...]
    date_columns: tuple[str, ...]
    numeric_columns: tuple[str, ...] = ()
    unique_key: tuple[str, ...] = ()
    row_limit: int = 0
    freshness_column: str | None = None


DATASETS = (
    DatasetConfig(
        dataset_id="stock_list",
        label="A-share stock list",
        relative_path="股票数据/基础数据/股票列表/all.csv",
        kind="single_csv",
        required_columns=(
            "ts_code",
            "symbol",
            "name",
            "area",
            "industry",
            "market",
            "list_date",
        ),
        date_columns=("list_date",),
        unique_key=("ts_code",),
    ),
    DatasetConfig(
        dataset_id="daily_bar",
        label="A-share historical daily OHLCV",
        relative_path="股票数据/行情数据/历史日线/by_symbol",
        kind="by_symbol_csv",
        required_columns=(
            "ts_code",
            "trade_date",
            "open",
            "high",
            "low",
            "close",
            "pre_close",
            "pct_chg",
            "vol",
            "amount",
        ),
        date_columns=("trade_date",),
        numeric_columns=(
            "open",
            "high",
            "low",
            "close",
            "pre_close",
            "pct_chg",
            "vol",
            "amount",
        ),
        unique_key=("ts_code", "trade_date"),
        freshness_column="trade_date",
    ),
    DatasetConfig(
        dataset_id="income_statement",
        label="A-share income statement",
        relative_path="股票数据/财务数据/利润表/by_symbol",
        kind="by_symbol_csv",
        required_columns=(
            "ts_code",
            "ann_date",
            "end_date",
            "report_type",
            "total_revenue",
            "operate_profit",
            "n_income",
            "basic_eps",
        ),
        date_columns=("ann_date", "end_date"),
        numeric_columns=("total_revenue", "operate_profit", "n_income", "basic_eps"),
        unique_key=("ts_code", "end_date", "report_type"),
        freshness_column="ann_date",
    ),
    DatasetConfig(
        dataset_id="money_flow",
        label="A-share individual money flow",
        relative_path="股票数据/资金流向数据/个股资金流向/by_symbol",
        kind="by_symbol_csv",
        required_columns=(
            "ts_code",
            "trade_date",
            "buy_elg_amount",
            "sell_elg_amount",
            "net_mf_amount",
        ),
        date_columns=("trade_date",),
        numeric_columns=("buy_elg_amount", "sell_elg_amount", "net_mf_amount"),
        unique_key=("ts_code", "trade_date"),
        freshness_column="trade_date",
    ),
    DatasetConfig(
        dataset_id="broker_forecast",
        label="Sell-side broker forecast",
        relative_path="股票数据/特色数据/券商盈利预测数据/by_symbol",
        kind="by_symbol_csv",
        required_columns=(
            "ts_code",
            "report_date",
            "org_name",
            "author_name",
            "quarter",
            "tp",
            "np",
            "eps",
            "pe",
            "rating",
        ),
        date_columns=("report_date",),
        numeric_columns=("tp", "np", "eps", "pe"),
        unique_key=("ts_code", "report_date", "org_name", "author_name", "quarter"),
        freshness_column="report_date",
    ),
    DatasetConfig(
        dataset_id="index_daily",
        label="Index daily OHLCV",
        relative_path="指数专题/指数日线行情/by_symbol",
        kind="named_csv",
        required_columns=(
            "ts_code",
            "trade_date",
            "close",
            "open",
            "high",
            "low",
            "pct_chg",
            "vol",
            "amount",
        ),
        date_columns=("trade_date",),
        numeric_columns=("close", "open", "high", "low", "pct_chg", "vol", "amount"),
        unique_key=("ts_code", "trade_date"),
        freshness_column="trade_date",
    ),
)


def _read_rows(path: Path, *, max_rows: int = 0) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        rows = []
        for idx, row in enumerate(reader):
            if max_rows and idx >= max_rows:
                break
            rows.append({k: (v or "") for k, v in row.items() if k is not None})
        return list(reader.fieldnames or []), rows


def _find_by_symbol_file(directory: Path, symbol: str) -> Path | None:
    matches = sorted(directory.glob(f"{symbol}+*.csv"))
    return matches[0] if matches else None


def _parse_yyyymmdd(value: str) -> date | None:
    value = value.strip()
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y%m%d").date()
    except ValueError:
        return None


def _parse_float(value: str) -> float | None:
    value = value.strip().replace(",", "")
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _sample_value(value: str, *, limit: int = 120) -> str:
    value = re.sub(r"\s+", " ", value).strip()
    if len(value) <= limit:
        return value
    return value[: limit - 3] + "..."


def _date_metrics(rows: list[dict[str, str]], columns: Iterable[str]) -> dict[str, dict]:
    out = {}
    for col in columns:
        parsed = []
        invalid = 0
        empty = 0
        for row in rows:
            value = row.get(col, "")
            if not value:
                empty += 1
                continue
            item = _parse_yyyymmdd(value)
            if item is None:
                invalid += 1
            else:
                parsed.append(item)
        out[col] = {
            "non_empty": len(parsed) + invalid,
            "empty": empty,
            "invalid": invalid,
            "min": min(parsed).isoformat() if parsed else None,
            "max": max(parsed).isoformat() if parsed else None,
        }
    return out


def _numeric_metrics(rows: list[dict[str, str]], columns: Iterable[str]) -> dict[str, dict]:
    out = {}
    for col in columns:
        parsed = []
        invalid = 0
        empty = 0
        for row in rows:
            value = row.get(col, "")
            if not value:
                empty += 1
                continue
            item = _parse_float(value)
            if item is None:
                invalid += 1
            else:
                parsed.append(item)
        non_empty = len(parsed) + invalid
        out[col] = {
            "non_empty": non_empty,
            "empty": empty,
            "invalid": invalid,
            "parse_ratio": round(len(parsed) / non_empty, 6) if non_empty else None,
            "min": min(parsed) if parsed else None,
            "max": max(parsed) if parsed else None,
        }
    return out


def _duplicate_key_count(rows: list[dict[str, str]], columns: tuple[str, ...]) -> int:
    if not columns:
        return 0
    seen = set()
    duplicates = 0
    for row in rows:
        key = tuple(row.get(col, "") for col in columns)
        if key in seen:
            duplicates += 1
        else:
            seen.add(key)
    return duplicates


def _rows_with_required_values(rows: list[dict[str, str]], columns: tuple[str, ...]) -> int:
    return sum(1 for row in rows if all(row.get(col, "") for col in columns))


def _freshness_lag_days(metrics: dict[str, dict], column: str | None, today: date) -> int | None:
    if not column:
        return None
    latest = (metrics.get(column) or {}).get("max")
    if not latest:
        return None
    return (today - date.fromisoformat(latest)).days


def _stock_list_symbol_checks(rows: list[dict[str, str]], symbols: tuple[str, ...]) -> dict:
    row_symbols = {row.get("ts_code", "") for row in rows}
    return {
        "expected_symbols": list(symbols),
        "present_symbols": [symbol for symbol in symbols if symbol in row_symbols],
        "missing_symbols": [symbol for symbol in symbols if symbol not in row_symbols],
    }


def _file_payload(path: Path, *, root: Path, symbol: str | None = None) -> dict[str, object]:
    payload: dict[str, object] = {
        "path": str(path),
        "path_under_root": path.relative_to(root).as_posix() if path.exists() else None,
        "exists": path.exists(),
    }
    if symbol:
        payload["symbol"] = symbol
    if path.exists():
        payload["bytes"] = path.stat().st_size
        payload["mtime"] = datetime.fromtimestamp(path.stat().st_mtime).isoformat()
    return payload


def _audit_dataset(
    cfg: DatasetConfig,
    *,
    data_root: Path,
    symbols: tuple[str, ...],
    index_files: tuple[str, ...],
    max_rows_per_file: int,
    today: date,
) -> dict:
    base = data_root / cfg.relative_path
    files: list[dict[str, object]] = []
    if cfg.kind == "single_csv":
        files = [_file_payload(base, root=data_root)]
    elif cfg.kind == "by_symbol_csv":
        files = [
            _file_payload(path, root=data_root, symbol=symbol)
            if (path := _find_by_symbol_file(base, symbol))
            else {"symbol": symbol, "path": None, "path_under_root": None, "exists": False}
            for symbol in symbols
        ]
    elif cfg.kind == "named_csv":
        files = [
            _file_payload(base / name, root=data_root)
            for name in index_files
        ]
    else:
        raise ValueError(f"unsupported dataset kind: {cfg.kind}")

    rows: list[dict[str, str]] = []
    columns_seen: set[str] = set()
    errors = []
    loaded_files = 0
    truncated_files = 0
    ts_code_mismatch_count = 0
    invalid_ts_code_count = 0
    file_summaries = []

    for file_info in files:
        if not file_info.get("exists"):
            errors.append({"path": file_info.get("path"), "error": "missing_file"})
            continue
        path = Path(str(file_info["path"]))
        try:
            columns, file_rows = _read_rows(path, max_rows=max_rows_per_file)
            loaded_files += 1
            columns_seen.update(columns)
            if max_rows_per_file and len(file_rows) >= max_rows_per_file:
                truncated_files += 1
            expected_symbol = file_info.get("symbol")
            for row in file_rows:
                ts_code = row.get("ts_code", "")
                if ts_code and not TS_CODE_RE.match(ts_code):
                    invalid_ts_code_count += 1
                if expected_symbol and ts_code and ts_code != expected_symbol:
                    ts_code_mismatch_count += 1
            rows.extend(file_rows)
            file_summaries.append({
                **file_info,
                "row_count_read": len(file_rows),
                "column_count": len(columns),
                "first_row_sample": {
                    key: _sample_value(value)
                    for key, value in (file_rows[0].items() if file_rows else [])
                },
            })
        except Exception as exc:  # noqa: BLE001
            errors.append({"path": file_info.get("path"), "error": str(exc)})

    missing_columns = [col for col in cfg.required_columns if col not in columns_seen]
    date_stats = _date_metrics(rows, cfg.date_columns)
    numeric_stats = _numeric_metrics(rows, cfg.numeric_columns)
    duplicate_key_count = _duplicate_key_count(rows, cfg.unique_key)
    required_complete_rows = _rows_with_required_values(rows, cfg.required_columns)
    freshness_lag = _freshness_lag_days(date_stats, cfg.freshness_column, today)

    issues = []
    if missing_columns:
        issues.append({"severity": "P0", "code": "missing_required_columns", "detail": missing_columns})
    if errors:
        issues.append({"severity": "P1", "code": "file_errors", "detail": len(errors)})
    if rows and required_complete_rows < len(rows):
        issues.append({
            "severity": "P2",
            "code": "required_value_gaps",
            "detail": {"complete_rows": required_complete_rows, "row_count": len(rows)},
        })
    invalid_dates = {col: item["invalid"] for col, item in date_stats.items() if item["invalid"]}
    if invalid_dates:
        issues.append({"severity": "P1", "code": "invalid_dates", "detail": invalid_dates})
    invalid_numbers = {col: item["invalid"] for col, item in numeric_stats.items() if item["invalid"]}
    if invalid_numbers:
        issues.append({"severity": "P1", "code": "invalid_numeric_values", "detail": invalid_numbers})
    if duplicate_key_count:
        issues.append({"severity": "P2", "code": "duplicate_key_rows", "detail": duplicate_key_count})
    if ts_code_mismatch_count:
        issues.append({"severity": "P1", "code": "symbol_file_ts_code_mismatch", "detail": ts_code_mismatch_count})
    if invalid_ts_code_count:
        issues.append({"severity": "P1", "code": "invalid_ts_code", "detail": invalid_ts_code_count})
    if freshness_lag is not None and freshness_lag > 30:
        issues.append({
            "severity": "P2",
            "code": "freshness_lag_gt_30d",
            "detail": {"column": cfg.freshness_column, "lag_days": freshness_lag},
        })

    result = {
        "dataset_id": cfg.dataset_id,
        "label": cfg.label,
        "kind": cfg.kind,
        "base_path": str(base),
        "loaded_files": loaded_files,
        "declared_files": len(files),
        "truncated_files": truncated_files,
        "rows_read": len(rows),
        "required_columns": list(cfg.required_columns),
        "missing_required_columns": missing_columns,
        "required_complete_rows": required_complete_rows,
        "required_complete_ratio": round(required_complete_rows / len(rows), 6) if rows else None,
        "date_stats": date_stats,
        "numeric_stats": numeric_stats,
        "unique_key": list(cfg.unique_key),
        "duplicate_key_count": duplicate_key_count,
        "invalid_ts_code_count": invalid_ts_code_count,
        "symbol_file_ts_code_mismatch_count": ts_code_mismatch_count,
        "freshness_lag_days": freshness_lag,
        "file_summaries": file_summaries,
        "errors": errors[:20],
        "issues": issues,
        "status": "ok" if not issues else "review",
    }
    if cfg.dataset_id == "stock_list":
        result["symbol_checks"] = _stock_list_symbol_checks(rows, symbols)
    return result


def build_report(
    *,
    data_root: Path,
    symbols: tuple[str, ...],
    index_files: tuple[str, ...],
    max_rows_per_file: int,
    today: date | None = None,
) -> dict:
    # ``today`` is injectable so tests with fixed fixture dates don't turn
    # into wall-clock time bombs via the freshness_lag_gt_30d check (the
    # hardcoded 20260601 fixtures started flagging exactly 31 days after
    # they were written).
    today = today or date.today()
    datasets = [
        _audit_dataset(
            cfg,
            data_root=data_root,
            symbols=symbols,
            index_files=index_files,
            max_rows_per_file=max_rows_per_file,
            today=today,
        )
        for cfg in DATASETS
    ]
    total_issues = sum(len(item["issues"]) for item in datasets)
    severity_counts: dict[str, int] = {}
    for item in datasets:
        for issue in item["issues"]:
            severity = issue["severity"]
            severity_counts[severity] = severity_counts.get(severity, 0) + 1
    return {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "scan_mode": "bounded_a_share_semantic_rows",
        "data_root": str(data_root),
        "symbols": list(symbols),
        "index_files": list(index_files),
        "max_rows_per_file": max_rows_per_file,
        "summary": {
            "dataset_count": len(datasets),
            "ok_dataset_count": sum(1 for item in datasets if item["status"] == "ok"),
            "review_dataset_count": sum(1 for item in datasets if item["status"] != "ok"),
            "total_rows_read": sum(int(item["rows_read"]) for item in datasets),
            "total_files_loaded": sum(int(item["loaded_files"]) for item in datasets),
            "total_issues": total_issues,
            "severity_counts": severity_counts,
        },
        "datasets": datasets,
    }


def _markdown(report: dict) -> str:
    lines = [
        "# A-share data semantic audit",
        "",
        f"- Generated at: `{report['generated_at']}`",
        f"- Data root: `{report['data_root']}`",
        f"- Scan mode: `{report['scan_mode']}`",
        f"- Symbols: `{', '.join(report['symbols'])}`",
        f"- Max rows per file: `{report['max_rows_per_file']}`",
        "",
        "## Summary",
        "",
        "| Metric | Value |",
        "|---|---:|",
    ]
    for key, value in report["summary"].items():
        lines.append(f"| `{key}` | `{value}` |")
    lines.extend([
        "",
        "## Dataset results",
        "",
        "| Dataset | Status | Files | Rows | Missing columns | Complete ratio | Freshness lag | Issues |",
        "|---|---|---:|---:|---|---:|---:|---|",
    ])
    for item in report["datasets"]:
        issue_codes = ", ".join(issue["code"] for issue in item["issues"]) or ""
        missing = ", ".join(item["missing_required_columns"]) or ""
        freshness = item["freshness_lag_days"]
        complete = item["required_complete_ratio"]
        lines.append(
            "| {label} | `{status}` | {files} | {rows} | {missing} | {complete} | {freshness} | {issues} |".format(
                label=item["label"],
                status=item["status"],
                files=item["loaded_files"],
                rows=item["rows_read"],
                missing=missing,
                complete="" if complete is None else complete,
                freshness="" if freshness is None else freshness,
                issues=issue_codes,
            )
        )
    lines.extend(["", "## Notes", ""])
    lines.append(
        "- This audit reads real rows for selected high-value A-share sources. It is stronger than header-only cataloging, but it is still bounded sampling, not a full semantic review of every CSV row."
    )
    lines.append(
        "- Review-status datasets are not automatically unusable; they indicate missing files, stale sampled data, duplicate keys, invalid values, or required-field sparsity that should be interpreted per source."
    )
    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-root", default=DEFAULT_DATA_ROOT)
    ap.add_argument("--symbols", default=",".join(DEFAULT_SYMBOLS))
    ap.add_argument(
        "--index-files",
        default="000001.SH+上证指数.csv",
        help="comma-separated index CSV files under 指数专题/指数日线行情/by_symbol",
    )
    ap.add_argument("--max-rows-per-file", type=int, default=0,
                    help="0 means read all rows from the bounded file sample")
    ap.add_argument("--output-json", default="docs/audit/a_share_data_semantics_2026-06-18.json")
    ap.add_argument("--output-md", default="docs/audit/a_share_data_semantics_2026-06-18.md")
    return ap.parse_args()


def main() -> int:
    args = parse_args()
    symbols = tuple(item.strip() for item in args.symbols.split(",") if item.strip())
    index_files = tuple(item.strip() for item in args.index_files.split(",") if item.strip())
    report = build_report(
        data_root=Path(args.data_root),
        symbols=symbols,
        index_files=index_files,
        max_rows_per_file=args.max_rows_per_file,
    )
    json_text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output_json:
        out = Path(args.output_json)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json_text + "\n", encoding="utf-8")
    else:
        print(json_text)
    if args.output_md:
        out_md = Path(args.output_md)
        out_md.parent.mkdir(parents=True, exist_ok=True)
        out_md.write_text(_markdown(report), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
