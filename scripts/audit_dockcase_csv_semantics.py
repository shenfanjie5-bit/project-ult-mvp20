#!/usr/bin/env python3
"""Stratified semantic samples for DockCase CSV data.

This complements ``audit_data_catalog.py``. The catalog proves file/header shape
for all CSV files; this script groups files by header signature and reads a
bounded number of real data rows per signature to check field-level semantics.
It is deliberately sample-based and does not claim full row coverage.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import math
import os
import re
import time
from collections import Counter, deque
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable


DEFAULT_DATA_ROOT = "/Volumes/dockcase2tb/database_all"
DEFAULT_JSON_OUTPUT = "docs/audit/dockcase_csv_semantics_2026-06-18.json"
DEFAULT_MD_OUTPUT = "docs/audit/dockcase_csv_semantics_2026-06-18.md"
DEFAULT_PRUNES = (
    ".git",
    ".venv",
    "node_modules",
    "dist",
    "target",
    ".venv_research",
    "_workspace/.venv",
    "_workspace/node_modules",
)

MISSING_VALUES = {"", "-", "--", "nan", "none", "null", "n/a", "na", "None", "NULL"}
MISSING_VALUES_LOWER = {item.lower() for item in MISSING_VALUES}
DATE_NAME_HINTS = {
    "date",
    "trade_date",
    "ann_date",
    "f_ann_date",
    "end_date",
    "start_date",
    "cal_date",
    "in_date",
    "out_date",
    "report_date",
    "update_date",
}
FRESHNESS_DATE_PRIORITY = (
    "trade_date",
    "nav_date",
    "cal_date",
    "ann_date",
    "f_ann_date",
    "report_date",
    "end_date",
)
NUMERIC_HINT_RE = re.compile(
    r"(^|_)(amount|amt|assets?|balance|buy|close|count|debt|eps|fee|float|"
    r"high|income|liab|limit|low|margin|money|net|num|open|pct|price|profit|"
    r"ratio|rate|revenue|roe|roa|sell|share|turnover|value|vol|volume|"
    r"weight|yield|chg|pe|pb|ps|dv|mv|roe_dt|or_yoy|bps|cfps|tr)$",
    re.IGNORECASE,
)
TEXT_ID_HINT_RE = re.compile(
    r"(^|_)(code|id|name|symbol|market|exchange|type|level|industry|sector|"
    r"area|province|city|desc|title|url|source|author|status|flag|class|"
    r"period|quarter|freq|unit|currency|remark|memo|tag|label|kind)$",
    re.IGNORECASE,
)
TS_CODE_RE = re.compile(r"^(?:[A-Za-z0-9]{1,16}\.[A-Za-z]{2,8}|[A-Z0-9]{1,16})$")


@dataclass
class ColumnProfile:
    non_empty: int = 0
    empty: int = 0
    numeric_valid: int = 0
    numeric_invalid: int = 0
    numeric_min: float | None = None
    numeric_max: float | None = None
    date_valid: int = 0
    date_invalid: int = 0
    date_min: str | None = None
    date_max: str | None = None
    ts_code_valid: int = 0
    ts_code_invalid: int = 0
    sample_values: list[str] = field(default_factory=list)
    _sample_seen: set[str] = field(default_factory=set, repr=False)

    def add_sample(self, value: str, *, limit: int = 8) -> None:
        if value in self._sample_seen or len(self.sample_values) >= limit:
            return
        self._sample_seen.add(value)
        self.sample_values.append(_short(value, limit=80))


@dataclass
class SignatureSample:
    columns: tuple[str, ...]
    file_count: int = 0
    examples: list[str] = field(default_factory=list)
    sampled_files: int = 0
    sampled_rows: int = 0
    total_cells: int = 0
    empty_cells: int = 0
    row_width_mismatch_count: int = 0
    row_width_mismatch_examples: list[dict[str, Any]] = field(default_factory=list)
    duplicate_sampled_rows: int = 0
    read_errors: list[dict[str, str]] = field(default_factory=list)
    domain_issue_counts: Counter[str] = field(default_factory=Counter)
    domain_issue_examples: list[dict[str, Any]] = field(default_factory=list)
    domain_issue_examples_by_code: dict[str, list[dict[str, Any]]] = field(
        default_factory=dict,
    )
    column_profiles: dict[str, ColumnProfile] = field(default_factory=dict)
    _seen_rows: set[tuple[str, ...]] = field(default_factory=set, repr=False)
    _seen_grain_keys_by_file: dict[str, set[tuple[str, ...]]] = field(
        default_factory=dict,
        repr=False,
    )


def _rel(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def _should_prune(rel: str, prunes: Iterable[str]) -> bool:
    for prefix in prunes:
        p = prefix.strip("/")
        if rel == p or rel.startswith(p + "/") or f"/{p}/" in f"/{rel}/":
            return True
    return False


def _walk_csv(root: Path, prunes: tuple[str, ...]) -> Iterable[Path]:
    for current, dirs, names in os.walk(root):
        current_path = Path(current)
        rel_current = "" if current_path == root else _rel(current_path, root)
        # Sort both so scan order (and the shard/max-files boundaries built
        # on it) is deterministic across filesystems — ext4 readdir order
        # differs from APFS and changed which files a bounded scan skipped
        # on CI.
        dirs[:] = sorted(
            d for d in dirs
            if not _should_prune(f"{rel_current}/{d}".strip("/"), prunes)
        )
        for name in sorted(names):
            if name.startswith("._"):
                continue
            if not name.lower().endswith(".csv"):
                continue
            path = current_path / name
            rel = _rel(path, root)
            if not _should_prune(rel, prunes):
                yield path


def _short(value: str, *, limit: int = 160) -> str:
    value = re.sub(r"\s+", " ", value).strip()
    if len(value) <= limit:
        return value
    return value[: limit - 3] + "..."


def _is_missing(value: str) -> bool:
    return value.strip() in MISSING_VALUES


def _parse_number(value: str) -> float | None:
    text = value.strip().replace(",", "")
    if text.endswith("%"):
        text = text[:-1]
    if not text or text.lower() in MISSING_VALUES_LOWER:
        return None
    try:
        out = float(text)
    except ValueError:
        return None
    if not math.isfinite(out):
        return None
    return out


def _parse_date(value: str) -> str | None:
    text = value.strip()
    if not text:
        return None
    try:
        if re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", text):
            return dt.datetime.strptime(text, "%Y-%m-%d %H:%M:%S").date().isoformat()
        if re.fullmatch(r"\d{8}", text):
            parsed = dt.date(int(text[:4]), int(text[4:6]), int(text[6:8]))
            return parsed.isoformat()
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
            return dt.date.fromisoformat(text).isoformat()
    except ValueError:
        return None
    return None


@lru_cache(maxsize=None)
def _is_date_column(column: str) -> bool:
    name = column.lower()
    if name in {"update_flag", "date_type"}:
        return False
    return name in DATE_NAME_HINTS or name.endswith("_date")


@lru_cache(maxsize=None)
def _is_text_identifier_column(column: str) -> bool:
    name = column.lower()
    return bool(TEXT_ID_HINT_RE.search(name)) or name.endswith("_code")


@lru_cache(maxsize=None)
def _is_numeric_hint_column(column: str) -> bool:
    return bool(NUMERIC_HINT_RE.search(column.lower()))


def _read_header(path: Path) -> tuple[str, ...]:
    with path.open("r", encoding="utf-8-sig", errors="replace", newline="") as f:
        return tuple(next(csv.reader(f), ()))


def _iter_rows(path: Path, *, max_rows: int) -> Iterable[tuple[str, ...]]:
    if max_rows <= 0:
        return
    if max_rows == 1:
        head_limit = 1
    else:
        head_limit = max_rows // 2
    tail_limit = max_rows - head_limit
    head: list[tuple[str, ...]] = []
    tail: deque[tuple[str, ...]] = deque(maxlen=tail_limit)
    with path.open("r", encoding="utf-8-sig", errors="replace", newline="") as f:
        reader = csv.reader(f)
        next(reader, None)
        for row in reader:
            if not any(cell.strip() for cell in row):
                continue
            row_tuple = tuple(row)
            if len(head) < head_limit:
                head.append(row_tuple)
            elif tail_limit:
                tail.append(row_tuple)
    for row in head + list(tail):
        yield row


def _by_symbol_code(rel: str) -> str | None:
    match = re.search(r"/by_symbol/([^/]+)\.csv$", "/" + rel)
    if not match:
        return None
    return match.group(1).split("+", 1)[0].strip()


def _norm_code(value: str) -> str:
    return value.strip().upper()


def _add_domain_issue(
    sig: SignatureSample,
    code: str,
    rel: str,
    details: dict[str, Any],
    *,
    limit: int = 20,
    per_code_limit: int = 10,
) -> None:
    payload = {"issue": code, "path": rel, **details}
    sig.domain_issue_counts[code] += 1
    by_code = sig.domain_issue_examples_by_code.setdefault(code, [])
    if len(by_code) < per_code_limit:
        by_code.append(payload)
    if len(sig.domain_issue_examples) < limit:
        sig.domain_issue_examples.append(payload)


def _row_map(columns: tuple[str, ...], row: tuple[str, ...]) -> dict[str, str]:
    return {column: row[idx] if idx < len(row) else "" for idx, column in enumerate(columns)}


def _grain_columns(columns: tuple[str, ...]) -> tuple[str, ...]:
    names = set(columns)
    if {"ts_code", "trade_date", "con_code"}.issubset(names):
        return ("ts_code", "trade_date", "con_code")
    if {"ts_code", "trade_date", "price", "vol", "amount", "buyer", "seller"}.issubset(names):
        return ("ts_code", "trade_date", "price", "vol", "amount", "buyer", "seller")
    if {"ts_code", "trade_date"}.issubset(names):
        cols = ["ts_code", "trade_date"]
        if "freq" in names:
            cols.append("freq")
        return tuple(cols)
    if {"index_code", "con_code", "trade_date"}.issubset(names):
        return ("index_code", "con_code", "trade_date")
    if {"ts_code", "end_date", "report_type"}.issubset(names):
        cols = ["ts_code", "end_date", "report_type"]
        for optional in ("end_type", "f_ann_date", "ann_date", "comp_type", "update_flag"):
            if optional in names:
                cols.append(optional)
        return tuple(cols)
    if {"ts_code", "ann_date", "holder_name"}.issubset(names):
        cols = ["ts_code", "ann_date", "holder_name"]
        for optional in (
            "holder_type",
            "in_de",
            "change_vol",
            "change_ratio",
            "after_share",
            "after_ratio",
            "float_date",
            "float_share",
            "float_ratio",
            "share_type",
            "pledge_amount",
            "start_date",
            "end_date",
            "pledgor",
        ):
            if optional in names:
                cols.append(optional)
        return tuple(cols)
    return ()


def _num_from_map(row_by_col: dict[str, str], column: str) -> float | None:
    if column not in row_by_col:
        return None
    return _parse_number(row_by_col[column])


def _is_zero_like(value: float | None) -> bool:
    return value is not None and abs(value) < 1e-12


def _num_is_zero_or_missing(row_by_col: dict[str, str], column: str) -> bool:
    if column not in row_by_col:
        return True
    raw = row_by_col[column]
    if _is_missing(raw):
        return True
    parsed = _parse_number(raw)
    return parsed is not None and _is_zero_like(parsed)


def _is_zero_ohlc_no_trade_carry_forward(
    row_by_col: dict[str, str],
    *,
    open_: float,
    high: float,
    low: float,
    close: float,
) -> bool:
    if not (_is_zero_like(open_) and _is_zero_like(high) and _is_zero_like(low)):
        return False
    if close <= 0:
        return False
    quiet_columns = ("vol", "volume", "amount", "change", "pct_chg", "pct_change")
    return all(_num_is_zero_or_missing(row_by_col, column) for column in quiet_columns)


def _check_file_code_consistency(
    sig: SignatureSample,
    rel: str,
    row_by_col: dict[str, str],
) -> None:
    expected_code = _by_symbol_code(rel)
    if not expected_code:
        return
    candidate_column = ""
    if "index_code" in row_by_col:
        candidate_column = "index_code"
    elif "ts_code" in row_by_col and "con_code" not in row_by_col:
        if {"l1_code", "l2_code", "l3_code"}.intersection(row_by_col):
            return
        candidate_column = "ts_code"
    elif "symbol" in row_by_col:
        candidate_column = "symbol"
    if not candidate_column:
        return
    actual = row_by_col.get(candidate_column, "")
    if actual and _norm_code(actual) != _norm_code(expected_code):
        issue = (
            "index_by_symbol_bundle_mismatch"
            if rel.startswith("指数专题/") and candidate_column == "ts_code"
            else "by_symbol_code_mismatch"
        )
        _add_domain_issue(
            sig,
            issue,
            rel,
            {
                "expected": expected_code,
                "column": candidate_column,
                "actual": actual,
            },
        )


def _check_ohlc_invariants(
    sig: SignatureSample,
    rel: str,
    row_by_col: dict[str, str],
) -> None:
    required = ("open", "high", "low", "close")
    if not set(required).issubset(row_by_col):
        return
    values = {column: _num_from_map(row_by_col, column) for column in required}
    if any(value is None for value in values.values()):
        return
    open_, high, low, close = (
        values["open"],
        values["high"],
        values["low"],
        values["close"],
    )
    assert open_ is not None and high is not None and low is not None and close is not None
    if min(open_, high, low, close) < 0:
        _add_domain_issue(
            sig,
            "negative_ohlc_value",
            rel,
            {"open": open_, "high": high, "low": low, "close": close},
        )
        return
    if _is_zero_ohlc_no_trade_carry_forward(
        row_by_col,
        open_=open_,
        high=high,
        low=low,
        close=close,
    ):
        _add_domain_issue(
            sig,
            "zero_ohlc_no_trade_carry_forward",
            rel,
            {"open": open_, "high": high, "low": low, "close": close},
        )
        return
    if high < max(open_, low, close) or low > min(open_, high, close):
        _add_domain_issue(
            sig,
            "ohlc_invariant_violation",
            rel,
            {"open": open_, "high": high, "low": low, "close": close},
        )


def _check_grain_duplicate(
    sig: SignatureSample,
    rel: str,
    row_by_col: dict[str, str],
) -> None:
    columns = _grain_columns(sig.columns)
    if not columns:
        return
    values = tuple(row_by_col.get(column, "") for column in columns)
    if any(not value for value in values):
        return
    key = (*columns, *values)
    seen_for_file = sig._seen_grain_keys_by_file.setdefault(rel, set())
    if key in seen_for_file:
        _add_domain_issue(
            sig,
            "duplicate_grain_key_sample",
            rel,
            {"key_columns": list(columns), "key_values": list(values)},
        )
    else:
        seen_for_file.add(key)


def _check_domain_row(
    sig: SignatureSample,
    rel: str,
    row: tuple[str, ...],
) -> None:
    row_by_col = _row_map(sig.columns, row)
    _check_file_code_consistency(sig, rel, row_by_col)
    _check_ohlc_invariants(sig, rel, row_by_col)
    _check_grain_duplicate(sig, rel, row_by_col)


def _profile_value(sig: SignatureSample, column: str, value: str) -> None:
    profile = sig.column_profiles.setdefault(column, ColumnProfile())
    if _is_missing(value):
        profile.empty += 1
        sig.empty_cells += 1
        return

    profile.non_empty += 1
    profile.add_sample(value)

    if _is_date_column(column):
        parsed_date = _parse_date(value)
        if parsed_date is None:
            profile.date_invalid += 1
        else:
            profile.date_valid += 1
            profile.date_min = (
                parsed_date if profile.date_min is None else min(profile.date_min, parsed_date)
            )
            profile.date_max = (
                parsed_date if profile.date_max is None else max(profile.date_max, parsed_date)
            )

    if column.lower() == "ts_code":
        if TS_CODE_RE.fullmatch(value.strip()):
            profile.ts_code_valid += 1
        else:
            profile.ts_code_invalid += 1

    if not _is_date_column(column) and not _is_text_identifier_column(column):
        parsed_num = _parse_number(value)
        if parsed_num is None:
            profile.numeric_invalid += 1
        else:
            profile.numeric_valid += 1
            profile.numeric_min = (
                parsed_num if profile.numeric_min is None else min(profile.numeric_min, parsed_num)
            )
            profile.numeric_max = (
                parsed_num if profile.numeric_max is None else max(profile.numeric_max, parsed_num)
            )


def scan_csv_semantics(
    data_root: Path,
    *,
    files_per_signature: int,
    rows_per_file: int,
    prunes: tuple[str, ...] = DEFAULT_PRUNES,
    as_of_date: dt.date | None = None,
) -> dict[str, Any]:
    started = time.time()
    as_of_date = as_of_date or dt.date.today()
    signatures: dict[tuple[str, ...], SignatureSample] = {}
    csv_files_seen = 0
    header_read_errors: list[dict[str, str]] = []

    if not data_root.exists():
        return {
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "elapsed_s": 0.0,
            "data_root": str(data_root),
            "exists": False,
            "scan_mode": "missing_data_root",
            "parameters": {
                "files_per_signature": files_per_signature,
                "rows_per_file": rows_per_file,
                "sample_strategy": "head_tail",
                "as_of_date": as_of_date.isoformat(),
            },
            "summary": {"csv_files_seen": 0, "signature_count": 0},
            "signatures": [],
        }

    for path in _walk_csv(data_root, prunes):
        csv_files_seen += 1
        rel = _rel(path, data_root)
        try:
            header = _read_header(path)
        except Exception as exc:  # noqa: BLE001
            header_read_errors.append({"path": rel, "error": str(exc)})
            continue
        sig = signatures.setdefault(header, SignatureSample(columns=header))
        sig.file_count += 1
        if len(sig.examples) < files_per_signature:
            sig.examples.append(rel)

    for sig in signatures.values():
        for column in sig.columns:
            sig.column_profiles.setdefault(column, ColumnProfile())
        for rel in sig.examples:
            path = data_root / rel
            try:
                file_rows = 0
                for row in _iter_rows(path, max_rows=rows_per_file):
                    sig.sampled_rows += 1
                    file_rows += 1
                    sig.total_cells += len(sig.columns)
                    if row in sig._seen_rows:
                        sig.duplicate_sampled_rows += 1
                    else:
                        sig._seen_rows.add(row)
                    if len(row) != len(sig.columns):
                        sig.row_width_mismatch_count += 1
                        if len(sig.row_width_mismatch_examples) < 5:
                            sig.row_width_mismatch_examples.append(
                                {
                                    "path": rel,
                                    "column_count": len(sig.columns),
                                    "row_width": len(row),
                                }
                            )
                    _check_domain_row(sig, rel, row)
                    for idx, column in enumerate(sig.columns):
                        value = row[idx] if idx < len(row) else ""
                        _profile_value(sig, column, value)
                if file_rows:
                    sig.sampled_files += 1
            except Exception as exc:  # noqa: BLE001
                sig.read_errors.append({"path": rel, "error": str(exc)})

    signature_rows = [
        _signature_payload(index + 1, sig, as_of_date=as_of_date)
        for index, sig in enumerate(
            sorted(signatures.values(), key=lambda item: item.file_count, reverse=True)
        )
    ]
    issue_counts = Counter()
    for row in signature_rows:
        issue_counts.update(row["issue_counts"])

    files_grouped_by_signature = sum(sig.file_count for sig in signatures.values())
    selected_signature_count = sum(1 for sig in signatures.values() if sig.examples)
    sampled_signature_count = sum(1 for sig in signatures.values() if sig.sampled_rows)
    selected_file_count = sum(len(sig.examples) for sig in signatures.values())
    sampled_files = sum(sig.sampled_files for sig in signatures.values())
    sampled_rows = sum(sig.sampled_rows for sig in signatures.values())
    unselected_files_due_to_signature_file_limit = max(
        files_grouped_by_signature - selected_file_count,
        0,
    )
    selected_files_without_sampled_rows = max(selected_file_count - sampled_files, 0)
    unsampled_signature_count = max(len(signatures) - sampled_signature_count, 0)
    signatures_selected_but_no_sampled_rows = sum(
        1 for sig in signatures.values() if sig.examples and not sig.sampled_rows
    )
    sampling_coverage = {
        "sampled_signature_ratio": round(
            sampled_signature_count / len(signatures),
            4,
        ) if signatures else 0.0,
        "selected_file_ratio_of_grouped_csv": round(
            selected_file_count / files_grouped_by_signature,
            4,
        ) if files_grouped_by_signature else 0.0,
        "sampled_file_ratio_of_grouped_csv": round(
            sampled_files / files_grouped_by_signature,
            4,
        ) if files_grouped_by_signature else 0.0,
        "sampled_rows_per_sampled_file": round(
            sampled_rows / sampled_files,
            2,
        ) if sampled_files else 0.0,
    }

    summary = {
        "csv_files_seen": csv_files_seen,
        "header_read_error_count": len(header_read_errors),
        "files_grouped_by_signature": files_grouped_by_signature,
        "signature_count": len(signatures),
        "selected_signature_count": selected_signature_count,
        "sampled_signature_count": sampled_signature_count,
        "unsampled_signature_count": unsampled_signature_count,
        "selected_files": selected_file_count,
        "sampled_files": sampled_files,
        "sampled_rows": sampled_rows,
        "unselected_files_due_to_signature_file_limit": (
            unselected_files_due_to_signature_file_limit
        ),
        "selected_files_without_sampled_rows": selected_files_without_sampled_rows,
        "signatures_selected_but_no_sampled_rows": signatures_selected_but_no_sampled_rows,
        "sampling_coverage": sampling_coverage,
        "coverage_gaps": {
            "header_read_error_files": len(header_read_errors),
            "unsampled_signatures": unsampled_signature_count,
            "signatures_selected_but_no_sampled_rows": (
                signatures_selected_but_no_sampled_rows
            ),
            "csv_files_not_selected_for_row_sampling": (
                unselected_files_due_to_signature_file_limit
            ),
            "csv_files_selected_but_no_sampled_rows": selected_files_without_sampled_rows,
            "bounded_row_sampling": True,
        },
        "row_width_mismatch_count": sum(
            sig.row_width_mismatch_count for sig in signatures.values()
        ),
        "duplicate_sampled_rows": sum(sig.duplicate_sampled_rows for sig in signatures.values()),
        "domain_issue_counts": dict(
            sum((sig.domain_issue_counts for sig in signatures.values()), Counter())
        ),
        "issue_counts": dict(issue_counts),
        "high_issue_signatures": [
            {
                "signature_rank": row["signature_rank"],
                "file_count": row["file_count"],
                "sampled_rows": row["sampled_rows"],
                "issue_counts": row["issue_counts"],
                "columns": row["columns"][:12],
                "examples": row["examples"][:3],
            }
            for row in signature_rows
            if row["issue_counts"]
        ][:20],
        "high_file_count_sampling_limits": [
            {
                "signature_rank": row["signature_rank"],
                "file_count": row["file_count"],
                "selected_files": row["selected_files"],
                "sampled_files": row["sampled_files"],
                "sampled_rows": row["sampled_rows"],
                "unselected_files_due_to_limit": row[
                    "unselected_files_due_to_limit"
                ],
                "columns": row["columns"][:12],
                "examples": row["examples"][:3],
            }
            for row in signature_rows
            if row["unselected_files_due_to_limit"] > 0
        ][:20],
        "no_sampled_row_signatures": [
            {
                "signature_rank": row["signature_rank"],
                "file_count": row["file_count"],
                "selected_files": row["selected_files"],
                "sampled_files": row["sampled_files"],
                "read_errors": row["read_errors"][:3],
                "columns": row["columns"][:12],
                "examples": row["examples"][:3],
            }
            for row in signature_rows
            if row["sampled_rows"] == 0
        ][:20],
    }
    return {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "elapsed_s": round(time.time() - started, 3),
        "data_root": str(data_root),
        "exists": True,
        "scan_mode": "header_signature_stratified_bounded_row_semantics",
        "parameters": {
            "files_per_signature": files_per_signature,
            "rows_per_file": rows_per_file,
            "sample_strategy": "head_tail",
            "as_of_date": as_of_date.isoformat(),
            "prunes": list(prunes),
        },
        "summary": summary,
        "header_read_errors": header_read_errors[:50],
        "signatures": signature_rows,
    }


def _freshness_payload(
    date_columns: list[dict[str, Any]],
    *,
    as_of_date: dt.date,
) -> dict[str, Any]:
    by_name = {str(item["column"]).lower(): item for item in date_columns}
    selected: dict[str, Any] | None = None
    for name in FRESHNESS_DATE_PRIORITY:
        item = by_name.get(name)
        if item and item.get("max"):
            selected = item
            break
    if selected is None:
        for item in date_columns:
            if item.get("max"):
                selected = item
                break
    if selected is None:
        return {}
    max_date = dt.date.fromisoformat(str(selected["max"]))
    return {
        "primary_date_column": selected["column"],
        "max_date": max_date.isoformat(),
        "as_of_date": as_of_date.isoformat(),
        "lag_days": (as_of_date - max_date).days,
    }


def _signature_payload(
    signature_rank: int,
    sig: SignatureSample,
    *,
    as_of_date: dt.date,
) -> dict[str, Any]:
    issue_counts = Counter()
    date_columns: list[dict[str, Any]] = []
    numeric_columns: list[dict[str, Any]] = []
    ts_code_columns: list[dict[str, Any]] = []
    sparse_columns: list[dict[str, Any]] = []
    categorical_columns: list[dict[str, Any]] = []

    for column in sig.columns:
        profile = sig.column_profiles[column]
        total = profile.non_empty + profile.empty
        non_empty_ratio = round(profile.non_empty / total, 4) if total else 0.0
        if _is_date_column(column):
            payload = {
                "column": column,
                "non_empty": profile.non_empty,
                "empty": profile.empty,
                "invalid": profile.date_invalid,
                "min": profile.date_min,
                "max": profile.date_max,
                "samples": profile.sample_values[:5],
            }
            date_columns.append(payload)
            if profile.date_invalid:
                issue_counts["invalid_date"] += profile.date_invalid
        elif column.lower() == "ts_code":
            payload = {
                "column": column,
                "non_empty": profile.non_empty,
                "empty": profile.empty,
                "valid": profile.ts_code_valid,
                "invalid": profile.ts_code_invalid,
                "samples": profile.sample_values[:5],
            }
            ts_code_columns.append(payload)
            if profile.ts_code_invalid:
                issue_counts["invalid_ts_code"] += profile.ts_code_invalid
        else:
            numeric_total = profile.numeric_valid + profile.numeric_invalid
            numeric_ratio = (
                round(profile.numeric_valid / numeric_total, 4) if numeric_total else 0.0
            )
            is_numeric = (
                profile.numeric_valid > 0
                and (numeric_ratio >= 0.8 or _is_numeric_hint_column(column))
                and not _is_text_identifier_column(column)
            )
            if is_numeric:
                payload = {
                    "column": column,
                    "non_empty": profile.non_empty,
                    "empty": profile.empty,
                    "numeric_valid": profile.numeric_valid,
                    "numeric_invalid": profile.numeric_invalid,
                    "parse_ratio": numeric_ratio,
                    "min": profile.numeric_min,
                    "max": profile.numeric_max,
                    "samples": profile.sample_values[:5],
                }
                numeric_columns.append(payload)
                if _is_numeric_hint_column(column) and profile.numeric_invalid:
                    issue_counts["invalid_numeric"] += profile.numeric_invalid
            else:
                categorical_columns.append(
                    {
                        "column": column,
                        "non_empty": profile.non_empty,
                        "empty": profile.empty,
                        "non_empty_ratio": non_empty_ratio,
                        "samples": profile.sample_values[:5],
                    }
                )
        if total and non_empty_ratio < 0.05:
            sparse_columns.append(
                {
                    "column": column,
                    "non_empty": profile.non_empty,
                    "empty": profile.empty,
                    "non_empty_ratio": non_empty_ratio,
                }
            )

    empty_cell_ratio = round(sig.empty_cells / sig.total_cells, 4) if sig.total_cells else 0.0
    if sig.sampled_rows == 0:
        issue_counts["no_sampled_rows"] += 1
    if sig.row_width_mismatch_count:
        issue_counts["row_width_mismatch"] += sig.row_width_mismatch_count
    if sig.read_errors:
        issue_counts["csv_read_error"] += len(sig.read_errors)
    if empty_cell_ratio > 0.5:
        issue_counts["high_empty_cell_ratio_signature"] += 1
    if sparse_columns:
        issue_counts["sparse_columns_lt_5pct_non_empty"] += len(sparse_columns)
    issue_counts.update(sig.domain_issue_counts)
    freshness = _freshness_payload(date_columns, as_of_date=as_of_date)
    if freshness:
        lag_days = int(freshness["lag_days"])
        primary_column = str(freshness["primary_date_column"])
        if lag_days < -7:
            issue_counts["future_primary_date_gt_7d"] += 1
        elif primary_column in {"trade_date", "nav_date", "cal_date"} and lag_days > 45:
            issue_counts["stale_primary_market_date_gt_45d"] += 1

    return {
        "signature_rank": signature_rank,
        "file_count": sig.file_count,
        "column_count": len(sig.columns),
        "columns": list(sig.columns),
        "examples": sig.examples,
        "selected_files": len(sig.examples),
        "sampled_files": sig.sampled_files,
        "selected_files_without_sampled_rows": max(
            len(sig.examples) - sig.sampled_files,
            0,
        ),
        "unselected_files_due_to_limit": max(sig.file_count - len(sig.examples), 0),
        "sampled_rows": sig.sampled_rows,
        "total_cells": sig.total_cells,
        "empty_cells": sig.empty_cells,
        "empty_cell_ratio": empty_cell_ratio,
        "duplicate_sampled_rows": sig.duplicate_sampled_rows,
        "row_width_mismatch_count": sig.row_width_mismatch_count,
        "row_width_mismatch_examples": sig.row_width_mismatch_examples,
        "read_errors": sig.read_errors,
        "domain_issue_counts": dict(sig.domain_issue_counts),
        "domain_issue_examples": sig.domain_issue_examples,
        "domain_issue_examples_by_code": sig.domain_issue_examples_by_code,
        "freshness": freshness,
        "issue_counts": dict(issue_counts),
        "column_profiles": {
            "date": date_columns,
            "numeric": numeric_columns,
            "ts_code": ts_code_columns,
            "sparse": sparse_columns[:30],
            "categorical_samples": categorical_columns[:30],
        },
    }


def write_markdown(report: dict[str, Any], output: Path) -> None:
    summary = report.get("summary", {})
    lines = [
        "# DOCKCASE CSV stratified semantic audit",
        "",
        f"- Generated: `{report.get('generated_at')}`",
        f"- Data root: `{report.get('data_root')}`",
        f"- Scan mode: `{report.get('scan_mode')}`",
        f"- Elapsed: `{report.get('elapsed_s')}` seconds",
        f"- Sample strategy: `{report.get('parameters', {}).get('sample_strategy')}`",
        f"- As-of date: `{report.get('parameters', {}).get('as_of_date')}`",
        f"- CSV files seen: `{summary.get('csv_files_seen')}`",
        f"- Files grouped by signature: `{summary.get('files_grouped_by_signature')}`",
        f"- Header signatures: `{summary.get('signature_count')}`",
        f"- Selected signatures: `{summary.get('selected_signature_count')}`",
        f"- Sampled signatures: `{summary.get('sampled_signature_count')}`",
        f"- Selected files: `{summary.get('selected_files')}`",
        f"- Sampled files / rows: `{summary.get('sampled_files')}` / `{summary.get('sampled_rows')}`",
        f"- Header read errors: `{summary.get('header_read_error_count')}`",
        "",
        "## Sampling Coverage",
        "",
    ]
    coverage = summary.get("sampling_coverage", {})
    coverage_gaps = summary.get("coverage_gaps", {})
    if coverage:
        lines.extend(
            [
                "| Metric | Value |",
                "|---|---:|",
                f"| Sampled signature ratio | `{coverage.get('sampled_signature_ratio')}` |",
                f"| Selected file ratio of grouped CSV | `{coverage.get('selected_file_ratio_of_grouped_csv')}` |",
                f"| Sampled file ratio of grouped CSV | `{coverage.get('sampled_file_ratio_of_grouped_csv')}` |",
                f"| Sampled rows per sampled file | `{coverage.get('sampled_rows_per_sampled_file')}` |",
                "",
            ]
        )
    if coverage_gaps:
        lines.extend(
            [
                "| Coverage gap | Count |",
                "|---|---:|",
                f"| Header-read error files | `{coverage_gaps.get('header_read_error_files')}` |",
                f"| Unsampled signatures | `{coverage_gaps.get('unsampled_signatures')}` |",
                f"| Signatures selected but no sampled rows | `{coverage_gaps.get('signatures_selected_but_no_sampled_rows')}` |",
                f"| CSV files not selected for row sampling | `{coverage_gaps.get('csv_files_not_selected_for_row_sampling')}` |",
                f"| CSV files selected but no sampled rows | `{coverage_gaps.get('csv_files_selected_but_no_sampled_rows')}` |",
                "",
            ]
        )
    lines.extend([
        "## Issue Counts",
        "",
    ])
    issue_counts = summary.get("issue_counts", {})
    if issue_counts:
        for key, value in sorted(issue_counts.items()):
            lines.append(f"- `{key}`: {value}")
    else:
        lines.append("- No sampled semantic issues detected.")
    domain_issue_counts = summary.get("domain_issue_counts", {})
    lines.extend(["", "## Domain Issue Counts", ""])
    if domain_issue_counts:
        for key, value in sorted(domain_issue_counts.items()):
            lines.append(f"- `{key}`: {value}")
    else:
        lines.append("- No sampled domain-invariant issues detected.")
    lines.extend([
        "",
        "## Largest Header Signatures",
        "",
        "| Rank | Files | Sampled rows | Empty cell ratio | Issues | Columns | Example |",
        "|---:|---:|---:|---:|---|---|---|",
    ])
    for row in report.get("signatures", [])[:30]:
        issue_text = ", ".join(
            f"{key}={value}" for key, value in sorted(row.get("issue_counts", {}).items())
        ) or "-"
        columns = ", ".join(row.get("columns", [])[:8])
        if len(row.get("columns", [])) > 8:
            columns += ", ..."
        example = row.get("examples", [""])[0] if row.get("examples") else ""
        lines.append(
            "| {rank} | {files} | {rows} | {empty:.4f} | {issues} | {cols} | `{example}` |".format(
                rank=row.get("signature_rank"),
                files=row.get("file_count"),
                rows=row.get("sampled_rows"),
                empty=row.get("empty_cell_ratio") or 0.0,
                issues=issue_text.replace("|", "\\|"),
                cols=columns.replace("|", "\\|"),
                example=example,
            )
        )

    high_issue = summary.get("high_issue_signatures", [])
    lines.extend(["", "## Highest-Issue Signatures", ""])
    if not high_issue:
        lines.append("- No sampled signatures reported semantic issues.")
    else:
        for row in high_issue[:20]:
            issues = ", ".join(
                f"{key}={value}" for key, value in sorted(row.get("issue_counts", {}).items())
            )
            lines.append(
                f"- Rank {row.get('signature_rank')}, files {row.get('file_count')}, "
                f"sampled rows {row.get('sampled_rows')}: {issues}; "
                f"example `{(row.get('examples') or [''])[0]}`"
            )
    limited = summary.get("high_file_count_sampling_limits", [])
    lines.extend(["", "## Largest Sampling-Limited Signatures", ""])
    if not limited:
        lines.append("- No signatures were limited by the files-per-signature cap.")
    else:
        for row in limited[:20]:
            lines.append(
                f"- Rank {row.get('signature_rank')}, files {row.get('file_count')}, "
                f"selected {row.get('selected_files')}, sampled files "
                f"{row.get('sampled_files')}, sampled rows {row.get('sampled_rows')}, "
                f"unselected {row.get('unselected_files_due_to_limit')}; "
                f"example `{(row.get('examples') or [''])[0]}`"
            )
    no_rows = summary.get("no_sampled_row_signatures", [])
    lines.extend(["", "## Signatures Without Sampled Rows", ""])
    if not no_rows:
        lines.append("- Every selected signature yielded at least one sampled row.")
    else:
        for row in no_rows[:20]:
            lines.append(
                f"- Rank {row.get('signature_rank')}, files {row.get('file_count')}, "
                f"selected {row.get('selected_files')}, sampled files "
                f"{row.get('sampled_files')}; example "
                f"`{(row.get('examples') or [''])[0]}`"
            )
    lines.extend([
        "",
        "## Interpretation",
        "",
        "This audit is stronger than first-row cataloging because it samples real rows "
        "from each header signature and now records the file/signature sampling "
        "boundary explicitly. It is still bounded evidence: it does not read every "
        "CSV row and high sparsity can be normal for some vendor tables.",
        "",
    ])
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-root", default=DEFAULT_DATA_ROOT)
    ap.add_argument("--output", default=DEFAULT_JSON_OUTPUT)
    ap.add_argument("--markdown-output", default=DEFAULT_MD_OUTPUT)
    ap.add_argument("--files-per-signature", type=int, default=3)
    ap.add_argument("--rows-per-file", type=int, default=100)
    ap.add_argument("--as-of-date", default=dt.date.today().isoformat())
    ap.add_argument("--no-write", action="store_true")
    return ap.parse_args()


def main() -> int:
    args = parse_args()
    report = scan_csv_semantics(
        Path(args.data_root),
        files_per_signature=args.files_per_signature,
        rows_per_file=args.rows_per_file,
        as_of_date=dt.date.fromisoformat(args.as_of_date),
    )
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.no_write:
        print(text)
        return 0
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(text + "\n", encoding="utf-8")
    write_markdown(report, Path(args.markdown_output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
