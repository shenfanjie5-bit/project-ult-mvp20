#!/usr/bin/env python3
"""Build a lightweight schema/catalog audit for local and DockCase data files.

Unlike ``audit_inventory.py`` this script opens data files, but only enough to
capture shape: CSV headers and bounded first-row samples, SQLite table schemas,
small JSON key samples, HTML titles, and PDF file headers. It does not read full
datasets or execute project code.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sqlite3
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable


DEFAULT_ROOTS = (
    "config",
    "runtime",
    "factor_research",
    "docs/audit",
    "/Volumes/dockcase2tb/database_all",
    "/Volumes/dockcase2tb/market_data",
)

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

DATA_EXTENSIONS = {
    ".csv",
    ".json",
    ".jsonl",
    ".sqlite",
    ".sqlite3",
    ".db",
    ".html",
    ".htm",
    ".pdf",
    ".yaml",
    ".yml",
}

HTML_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)


@dataclass
class HeaderSig:
    count: int = 0
    columns: tuple[str, ...] = ()
    examples: list[str] = field(default_factory=list)
    data_row_sample_count: int = 0
    sample_rows: list[dict[str, object]] = field(default_factory=list)
    row_width_mismatch_count: int = 0
    row_width_mismatch_examples: list[dict[str, object]] = field(default_factory=list)


@dataclass
class RootCatalog:
    root: Path
    exists: bool = False
    files_seen: int = 0
    data_files: int = 0
    bytes: int = 0
    extensions: Counter[str] = field(default_factory=Counter)
    csv_files: int = 0
    csv_headers_read: int = 0
    csv_header_errors: list[dict[str, str]] = field(default_factory=list)
    csv_headers: dict[str, HeaderSig] = field(default_factory=dict)
    csv_data_rows_sampled: int = 0
    csv_files_without_sampled_data_row: int = 0
    csv_files_without_sampled_data_row_examples: list[str] = field(default_factory=list)
    csv_data_row_errors: list[dict[str, str]] = field(default_factory=list)
    csv_row_width_mismatch_count: int = 0
    csv_row_width_mismatch_examples: list[dict[str, object]] = field(default_factory=list)
    sqlite_files: int = 0
    sqlite_schema_errors: list[dict[str, str]] = field(default_factory=list)
    sqlite_schemas: list[dict] = field(default_factory=list)
    json_samples: list[dict] = field(default_factory=list)
    html_samples: list[dict] = field(default_factory=list)
    pdf_samples: list[dict] = field(default_factory=list)
    errors: list[dict[str, str]] = field(default_factory=list)


def _is_abs(path: str) -> bool:
    return path.startswith("/")


def _root_path(repo: Path, root: str) -> Path:
    return Path(root) if _is_abs(root) else repo / root


def _rel(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def _should_prune(rel: str, prunes: Iterable[str]) -> bool:
    for prefix in prunes:
        p = prefix.strip("/")
        if rel == p or rel.startswith(p + "/") or f"/{p}/" in f"/{rel}/":
            return True
    return False


def _walk(root: Path, prunes: tuple[str, ...]) -> Iterable[Path]:
    for current, dirs, names in os.walk(root):
        current_path = Path(current)
        rel_current = "" if current_path == root else _rel(current_path, root)
        # Sort both so the walk order (and therefore the sampled rows /
        # max-files boundaries in the reports) is deterministic across
        # filesystems — ext4 readdir order differs from APFS and flipped
        # the sampled files on CI.
        dirs[:] = sorted(
            d for d in dirs
            if not _should_prune(f"{rel_current}/{d}".strip("/"), prunes)
        )
        for name in sorted(names):
            path = current_path / name
            rel = _rel(path, root)
            if not _should_prune(rel, prunes):
                yield path


def _decode_first_line(path: Path, max_bytes: int) -> str:
    with path.open("rb") as f:
        data = f.readline(max_bytes)
    return data.decode("utf-8-sig", errors="replace").strip("\r\n")


def _csv_header(path: Path, max_bytes: int) -> tuple[str, ...]:
    line = _decode_first_line(path, max_bytes)
    if not line:
        return ()
    return tuple(next(csv.reader([line])))


def _csv_header_and_first_row(
    path: Path,
    max_bytes: int,
    *,
    max_physical_lines: int = 20,
) -> tuple[tuple[str, ...], tuple[str, ...] | None]:
    with path.open("rb") as f:
        header_data = f.readline(max_bytes)
        row_data = b""
        for _ in range(max_physical_lines):
            candidate = f.readline(max_bytes)
            if not candidate:
                break
            if candidate.strip():
                row_data = candidate
                break
    header_line = header_data.decode("utf-8-sig", errors="replace").strip("\r\n")
    row_line = row_data.decode("utf-8-sig", errors="replace").strip("\r\n")
    header = tuple(next(csv.reader([header_line]))) if header_line else ()
    row = tuple(next(csv.reader([row_line]))) if row_line else None
    return header, row


def _short_text(value: str, *, limit: int = 160) -> str:
    value = re.sub(r"\s+", " ", value).strip()
    if len(value) <= limit:
        return value
    return value[: limit - 3] + "..."


def _csv_sample_payload(
    rel: str,
    header: tuple[str, ...],
    row: tuple[str, ...],
    *,
    column_limit: int = 30,
) -> dict[str, object]:
    shown_columns = header[:column_limit]
    values = {
        col: _short_text(row[idx]) if idx < len(row) else ""
        for idx, col in enumerate(shown_columns)
    }
    payload: dict[str, object] = {
        "path": rel,
        "column_count": len(header),
        "row_width": len(row),
        "values": values,
    }
    if len(header) > column_limit:
        payload["truncated_columns"] = len(header) - column_limit
    if len(row) > len(header):
        payload["extra_values"] = [_short_text(value) for value in row[len(header):]]
    return payload


def _sample_json(path: Path, rel: str, max_bytes: int) -> dict:
    data = path.read_bytes()[:max_bytes]
    text = data.decode("utf-8-sig", errors="replace")
    obj = json.loads(text)
    if isinstance(obj, dict):
        keys = list(obj.keys())[:20]
        kind = "object"
    elif isinstance(obj, list):
        keys = list(obj[0].keys())[:20] if obj and isinstance(obj[0], dict) else []
        kind = "array"
    else:
        keys = []
        kind = type(obj).__name__
    return {"path": rel, "kind": kind, "keys": keys}


def _sample_html(path: Path, rel: str, max_bytes: int) -> dict:
    text = path.read_bytes()[:max_bytes].decode("utf-8", errors="replace")
    match = HTML_TITLE_RE.search(text)
    title = re.sub(r"\s+", " ", match.group(1)).strip() if match else ""
    return {"path": rel, "title": title[:200]}


def _sample_pdf(path: Path, rel: str) -> dict:
    with path.open("rb") as f:
        head = f.read(16)
    version = head.decode("latin-1", errors="replace").splitlines()[0]
    return {"path": rel, "header": version}


def _sqlite_schema(path: Path, rel: str, *, table_limit: int) -> dict:
    uri = f"file:{path.as_posix()}?mode=ro"
    con = sqlite3.connect(uri, uri=True)
    try:
        tables = [
            row[0]
            for row in con.execute(
                "select name from sqlite_master "
                "where type='table' and name not like 'sqlite_%' order by name"
            )
        ]
        sample = []
        for table in tables[:table_limit]:
            cols = [
                {"name": row[1], "type": row[2], "pk": bool(row[5])}
                for row in con.execute(f'pragma table_info("{table}")')
            ]
            sample.append({"table": table, "columns": cols})
        return {"path": rel, "table_count": len(tables), "tables": sample}
    finally:
        con.close()


def scan_root(
    root: Path,
    *,
    prunes: tuple[str, ...],
    csv_header_limit: int,
    csv_row_sample_limit: int = 0,
    sample_limit: int,
    max_header_bytes: int,
    max_json_bytes: int,
    max_html_bytes: int,
    sqlite_table_limit: int,
) -> RootCatalog:
    out = RootCatalog(root=root, exists=root.exists())
    if not out.exists:
        return out
    json_seen = html_seen = pdf_seen = 0
    for path in _walk(root, prunes):
        try:
            st = path.stat()
        except OSError as exc:
            out.errors.append({"path": path.as_posix(), "error": str(exc)})
            continue
        ext = path.suffix.lower()
        out.files_seen += 1
        if ext not in DATA_EXTENSIONS:
            continue
        rel = _rel(path, root)
        out.data_files += 1
        out.bytes += int(st.st_size)
        out.extensions[ext] += 1

        if ext == ".csv":
            out.csv_files += 1
            if csv_header_limit and out.csv_headers_read >= csv_header_limit:
                continue
            try:
                if csv_row_sample_limit:
                    header, first_row = _csv_header_and_first_row(path, max_header_bytes)
                else:
                    header = _csv_header(path, max_header_bytes)
                    first_row = None
                out.csv_headers_read += 1
                key = "\x1f".join(header)
                sig = out.csv_headers.setdefault(key, HeaderSig(columns=header))
                sig.count += 1
                if len(sig.examples) < 3:
                    sig.examples.append(rel)
                if first_row is None and csv_row_sample_limit:
                    out.csv_files_without_sampled_data_row += 1
                    if len(out.csv_files_without_sampled_data_row_examples) < 20:
                        out.csv_files_without_sampled_data_row_examples.append(rel)
                elif first_row is not None:
                    out.csv_data_rows_sampled += 1
                    sig.data_row_sample_count += 1
                    if len(sig.sample_rows) < csv_row_sample_limit:
                        sig.sample_rows.append(_csv_sample_payload(rel, header, first_row))
                    if len(first_row) != len(header):
                        mismatch = {
                            "path": rel,
                            "column_count": len(header),
                            "row_width": len(first_row),
                        }
                        out.csv_row_width_mismatch_count += 1
                        sig.row_width_mismatch_count += 1
                        if len(out.csv_row_width_mismatch_examples) < 20:
                            out.csv_row_width_mismatch_examples.append(mismatch)
                        if len(sig.row_width_mismatch_examples) < 3:
                            sig.row_width_mismatch_examples.append(mismatch)
            except Exception as exc:  # noqa: BLE001
                out.csv_header_errors.append({"path": rel, "error": str(exc)})
        elif ext in {".sqlite", ".sqlite3", ".db"}:
            out.sqlite_files += 1
            try:
                out.sqlite_schemas.append(
                    _sqlite_schema(path, rel, table_limit=sqlite_table_limit)
                )
            except Exception as exc:  # noqa: BLE001
                out.sqlite_schema_errors.append({"path": rel, "error": str(exc)})
        elif ext == ".json" and json_seen < sample_limit:
            json_seen += 1
            try:
                out.json_samples.append(_sample_json(path, rel, max_json_bytes))
            except Exception as exc:  # noqa: BLE001
                out.json_samples.append({"path": rel, "error": str(exc)})
        elif ext in {".html", ".htm"} and html_seen < sample_limit:
            html_seen += 1
            try:
                out.html_samples.append(_sample_html(path, rel, max_html_bytes))
            except Exception as exc:  # noqa: BLE001
                out.html_samples.append({"path": rel, "error": str(exc)})
        elif ext == ".pdf" and pdf_seen < sample_limit:
            pdf_seen += 1
            try:
                out.pdf_samples.append(_sample_pdf(path, rel))
            except Exception as exc:  # noqa: BLE001
                out.pdf_samples.append({"path": rel, "error": str(exc)})
    return out


def _catalog_json(out: RootCatalog, *, top_headers: int) -> dict:
    headers = sorted(out.csv_headers.values(), key=lambda item: item.count, reverse=True)
    return {
        "root": str(out.root),
        "exists": out.exists,
        "files_seen": out.files_seen,
        "data_files": out.data_files,
        "bytes": out.bytes,
        "extensions": dict(out.extensions.most_common()),
        "csv_files": out.csv_files,
        "csv_headers_read": out.csv_headers_read,
        "csv_header_error_count": len(out.csv_header_errors),
        "csv_header_errors": out.csv_header_errors[:20],
        "csv_data_rows_sampled": out.csv_data_rows_sampled,
        "csv_files_without_sampled_data_row": out.csv_files_without_sampled_data_row,
        "csv_files_without_sampled_data_row_examples": (
            out.csv_files_without_sampled_data_row_examples[:20]
        ),
        "csv_data_row_error_count": len(out.csv_data_row_errors),
        "csv_data_row_errors": out.csv_data_row_errors[:20],
        "csv_row_width_mismatch_count": out.csv_row_width_mismatch_count,
        "csv_row_width_mismatch_examples": out.csv_row_width_mismatch_examples[:20],
        "csv_header_signature_count": len(out.csv_headers),
        "csv_header_signatures": [
            {
                "count": sig.count,
                "columns": list(sig.columns),
                "examples": sig.examples,
                "data_row_sample_count": sig.data_row_sample_count,
                "sample_rows": sig.sample_rows,
                "row_width_mismatch_count": sig.row_width_mismatch_count,
                "row_width_mismatch_examples": sig.row_width_mismatch_examples,
            }
            for sig in headers[:top_headers]
        ],
        "sqlite_files": out.sqlite_files,
        "sqlite_schema_error_count": len(out.sqlite_schema_errors),
        "sqlite_schema_errors": out.sqlite_schema_errors[:20],
        "sqlite_schemas": out.sqlite_schemas,
        "json_samples": out.json_samples,
        "html_samples": out.html_samples,
        "pdf_samples": out.pdf_samples,
        "error_count": len(out.errors),
        "errors": out.errors[:20],
    }


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo-root", default=".")
    ap.add_argument("--roots", default=",".join(DEFAULT_ROOTS))
    ap.add_argument("--output", default=None)
    ap.add_argument("--csv-header-limit", type=int, default=0,
                    help="0 means read headers for all CSV files")
    ap.add_argument("--csv-row-sample-limit", type=int, default=1,
                    help="sample rows retained per CSV header signature; 0 disables row sampling")
    ap.add_argument("--sample-limit", type=int, default=20)
    ap.add_argument("--top-headers", type=int, default=50)
    ap.add_argument("--max-header-bytes", type=int, default=65536)
    ap.add_argument("--max-json-bytes", type=int, default=262144)
    ap.add_argument("--max-html-bytes", type=int, default=65536)
    ap.add_argument("--sqlite-table-limit", type=int, default=25)
    return ap.parse_args()


def main() -> int:
    args = parse_args()
    started = time.time()
    repo = Path(args.repo_root).resolve()
    roots = [r.strip() for r in args.roots.split(",") if r.strip()]
    result = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "elapsed_s": None,
        "scan_mode": (
            "schema_and_first_row_samples_no_full_dataset_reads"
            if args.csv_row_sample_limit
            else "schema_samples_no_full_dataset_reads"
        ),
        "roots": {},
    }
    for root_name in roots:
        root = _root_path(repo, root_name)
        catalog = scan_root(
            root,
            prunes=DEFAULT_PRUNES,
            csv_header_limit=args.csv_header_limit,
            csv_row_sample_limit=args.csv_row_sample_limit,
            sample_limit=args.sample_limit,
            max_header_bytes=args.max_header_bytes,
            max_json_bytes=args.max_json_bytes,
            max_html_bytes=args.max_html_bytes,
            sqlite_table_limit=args.sqlite_table_limit,
        )
        result["roots"][root_name] = _catalog_json(catalog, top_headers=args.top_headers)
    result["elapsed_s"] = round(time.time() - started, 3)
    text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text + "\n", encoding="utf-8")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
