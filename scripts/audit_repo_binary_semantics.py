#!/usr/bin/env python3
"""Type-aware semantic audit for repo files skipped by the text-body audit."""
from __future__ import annotations

import argparse
import gzip
import importlib.util
import json
import marshal
import pickletools
import re
import sqlite3
import struct
import time
import zipfile
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_REPO_CONTENT = ROOT / "docs/audit/repo_content_2026-06-18.json"
DEFAULT_OUTPUT_JSON = ROOT / "docs/audit/repo_binary_semantics_2026-06-19.json"
DEFAULT_OUTPUT_MD = ROOT / "docs/audit/repo_binary_semantics_2026-06-19.md"


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def _rel(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _read_head(path: Path, size: int = 8192) -> bytes:
    with path.open("rb") as fh:
        return fh.read(size)


def _magic_kind(head: bytes, extension: str) -> str:
    if head.startswith(b"%PDF-"):
        return "pdf"
    if head.startswith(b"SQLite format 3\x00"):
        return "sqlite_database"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png_image"
    if extension == ".npz":
        return "numpy_npz"
    if head.startswith(b"PK\x03\x04"):
        return "zip_container"
    if head.startswith(b"\x1f\x8b"):
        return "gzip_stream"
    if head.startswith(importlib.util.MAGIC_NUMBER):
        return "python_bytecode"
    if extension == ".pyc":
        return "python_bytecode"
    if extension == ".sqlite-wal":
        return "sqlite_wal"
    if extension == ".sqlite-shm":
        return "sqlite_shm"
    if extension == ".pkl":
        return "pickle_payload"
    if head.startswith(b"Bud1") or extension == "[no_ext]" and b"Bud1" in head[:16]:
        return "macos_ds_store"
    if b"\x00" in head[:8192]:
        return "opaque_binary"
    return "large_or_non_utf8_text"


def _source_for_pyc(path: Path) -> Path | None:
    if path.parent.name != "__pycache__":
        return None
    stem = path.name.split(".cpython-", 1)[0].split(".pypy-", 1)[0]
    return path.parent.parent / f"{stem}.py"


def _inspect_pyc(path: Path, root: Path, head: bytes) -> dict[str, Any]:
    out: dict[str, Any] = {
        "magic_hex": head[:4].hex(),
        "matches_current_magic": head[:4] == importlib.util.MAGIC_NUMBER,
    }
    if len(head) >= 16:
        flags = struct.unpack("<I", head[4:8])[0]
        out["flags"] = flags
        out["hash_based"] = bool(flags & 0x01)
    source = _source_for_pyc(path)
    if source is not None:
        out["source_path"] = _rel(source, root)
        out["source_exists"] = source.exists()
    try:
        with path.open("rb") as fh:
            fh.read(16)
            code = marshal.load(fh)
        out["code_object_name"] = getattr(code, "co_name", None)
        code_filename = getattr(code, "co_filename", None)
        if code_filename:
            code_path = Path(str(code_filename))
            if code_path.is_absolute():
                out["code_filename"] = _rel(code_path, root)
            else:
                out["code_filename"] = str(code_filename)
        out["code_consts_count"] = len(getattr(code, "co_consts", ()) or ())
        out["code_names_count"] = len(getattr(code, "co_names", ()) or ())
    except Exception as exc:  # noqa: BLE001
        out["inspect_error"] = f"{type(exc).__name__}: {exc}"
    return out


def _inspect_sqlite(path: Path) -> dict[str, Any]:
    out: dict[str, Any] = {}
    uri = f"file:{path.resolve()}?mode=ro&immutable=1"
    try:
        con = sqlite3.connect(uri, uri=True, timeout=1.0)
        try:
            out["page_count"] = con.execute("PRAGMA page_count").fetchone()[0]
            out["page_size"] = con.execute("PRAGMA page_size").fetchone()[0]
            out["user_version"] = con.execute("PRAGMA user_version").fetchone()[0]
            rows = con.execute(
                "SELECT type, name FROM sqlite_master "
                "WHERE name NOT LIKE 'sqlite_%' ORDER BY type, name"
            ).fetchall()
            counts = Counter(str(row[0]) for row in rows)
            out["object_counts"] = dict(sorted(counts.items()))
            out["objects_sample"] = [
                {"type": str(row[0]), "name": str(row[1])}
                for row in rows[:50]
            ]
            out["schema_object_count"] = len(rows)
        finally:
            con.close()
    except Exception as exc:  # noqa: BLE001
        out["inspect_error"] = f"{type(exc).__name__}: {exc}"
    return out


def _inspect_sqlite_sidecar(path: Path, root: Path, extension: str) -> dict[str, Any]:
    if extension == ".sqlite-wal":
        db_path = path.with_suffix("")
    elif extension == ".sqlite-shm":
        db_path = path.with_suffix("")
    else:
        db_path = path
    return {
        "paired_database_path": _rel(db_path, root),
        "paired_database_exists": db_path.exists(),
    }


def _inspect_npz(path: Path) -> dict[str, Any]:
    out: dict[str, Any] = {}
    try:
        import numpy as np

        with np.load(path, allow_pickle=False) as data:
            arrays = []
            total_nbytes = 0
            for name in data.files:
                arr = data[name]
                total_nbytes += int(getattr(arr, "nbytes", 0))
                arrays.append(
                    {
                        "name": name,
                        "shape": list(arr.shape),
                        "dtype": str(arr.dtype),
                        "nbytes": int(getattr(arr, "nbytes", 0)),
                    }
                )
            out["array_count"] = len(arrays)
            out["arrays"] = arrays[:50]
            out["array_total_nbytes"] = total_nbytes
    except Exception as exc:  # noqa: BLE001
        out["inspect_error"] = f"{type(exc).__name__}: {exc}"
    return out


def _inspect_png(path: Path) -> dict[str, Any]:
    out: dict[str, Any] = {}
    try:
        from PIL import Image

        with Image.open(path) as img:
            out["width"] = img.width
            out["height"] = img.height
            out["mode"] = img.mode
            out["format"] = img.format
    except Exception as exc:  # noqa: BLE001
        out["inspect_error"] = f"{type(exc).__name__}: {exc}"
    return out


def _inspect_pdf(path: Path) -> dict[str, Any]:
    out: dict[str, Any] = {}
    parts = path.parts
    if "annual_reports" in parts:
        idx = parts.index("annual_reports")
        if len(parts) > idx + 1:
            out["stock_code"] = parts[idx + 1]
        match = re.match(r"(\d{4})_", path.name)
        if match:
            out["report_year"] = int(match.group(1))
        out["document_family"] = "annual_report"
    try:
        import pypdfium2 as pdfium

        doc = pdfium.PdfDocument(str(path))
        out["page_count"] = len(doc)
        out["page_count_method"] = "pypdfium2"
    except Exception as exc:  # noqa: BLE001
        out["page_count_error"] = f"{type(exc).__name__}: {exc}"
        try:
            page_count = 0
            with path.open("rb") as fh:
                for chunk in iter(lambda: fh.read(1024 * 1024), b""):
                    page_count += len(re.findall(rb"/Type\s*/Page\b", chunk))
            out["page_count"] = page_count
            out["page_count_method"] = "pdf_marker_scan"
        except Exception as inner_exc:  # noqa: BLE001
            out["inspect_error"] = f"{type(inner_exc).__name__}: {inner_exc}"
    return out


def _inspect_zip(path: Path) -> dict[str, Any]:
    out: dict[str, Any] = {}
    try:
        with zipfile.ZipFile(path) as zf:
            infos = zf.infolist()
            out["entry_count"] = len(infos)
            out["entries_sample"] = [
                {
                    "name": info.filename,
                    "file_size": int(info.file_size),
                    "compress_size": int(info.compress_size),
                }
                for info in infos[:50]
            ]
    except Exception as exc:  # noqa: BLE001
        out["inspect_error"] = f"{type(exc).__name__}: {exc}"
    return out


def _inspect_gzip(path: Path) -> dict[str, Any]:
    out: dict[str, Any] = {}
    try:
        with gzip.open(path, "rb") as fh:
            sample = fh.read(65536)
        out["decompressed_sample_bytes"] = len(sample)
        out["sample_looks_text"] = b"\x00" not in sample[:8192]
    except Exception as exc:  # noqa: BLE001
        out["inspect_error"] = f"{type(exc).__name__}: {exc}"
    return out


def _inspect_pickle(path: Path) -> dict[str, Any]:
    out: dict[str, Any] = {"loaded": False, "load_policy": "not_loaded_for_safety"}
    try:
        ops = []
        with path.open("rb") as fh:
            for idx, (op, arg, pos) in enumerate(pickletools.genops(fh)):
                ops.append({"op": op.name, "arg": repr(arg)[:120], "pos": pos})
                if idx >= 49:
                    break
        out["opcode_sample"] = ops
        out["opcode_sample_count"] = len(ops)
    except Exception as exc:  # noqa: BLE001
        out["inspect_error"] = f"{type(exc).__name__}: {exc}"
    return out


def _inspect_large_text(path: Path) -> dict[str, Any]:
    out: dict[str, Any] = {}
    try:
        line_count = 0
        sample_lines = []
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line_count += 1
                if len(sample_lines) < 5:
                    sample_lines.append(line.rstrip("\n")[:240])
        out["line_count"] = line_count
        out["sample_lines"] = sample_lines
    except Exception as exc:  # noqa: BLE001
        out["inspect_error"] = f"{type(exc).__name__}: {exc}"
    return out


def _inspect_one(root: Path, item: dict[str, Any]) -> dict[str, Any]:
    rel = str(item.get("path") or "")
    path = root / rel
    extension = str(item.get("extension") or path.suffix.lower() or "[no_ext]")
    record: dict[str, Any] = {
        "path": rel,
        "extension": extension,
        "bytes": int(item.get("bytes") or 0),
        "skip_reason": item.get("reason"),
        "head_tail_sha256": item.get("head_tail_sha256"),
        "exists": path.exists(),
    }
    if not path.exists():
        record["semantic_kind"] = "missing_file"
        record["semantic_status"] = "missing"
        return record
    try:
        head = _read_head(path)
    except Exception as exc:  # noqa: BLE001
        record["semantic_kind"] = "unreadable"
        record["semantic_status"] = "error"
        record["inspect_error"] = f"{type(exc).__name__}: {exc}"
        return record

    kind = _magic_kind(head, extension)
    record["semantic_kind"] = kind
    record["magic_hex"] = head[:16].hex()
    details: dict[str, Any]
    if kind == "python_bytecode":
        details = _inspect_pyc(path, root, head)
    elif kind == "sqlite_database":
        details = _inspect_sqlite(path)
    elif kind in {"sqlite_wal", "sqlite_shm"}:
        details = _inspect_sqlite_sidecar(path, root, extension)
    elif kind == "numpy_npz":
        details = _inspect_npz(path)
    elif kind == "png_image":
        details = _inspect_png(path)
    elif kind == "pdf":
        details = _inspect_pdf(path)
    elif kind == "zip_container":
        details = _inspect_zip(path)
    elif kind == "gzip_stream":
        details = _inspect_gzip(path)
    elif kind == "pickle_payload":
        details = _inspect_pickle(path)
    elif kind == "large_or_non_utf8_text":
        details = _inspect_large_text(path)
    else:
        details = {}
    record["details"] = details
    record["semantic_status"] = "error" if "inspect_error" in details else "ok"
    return record


def build_report(repo_root: Path, repo_content_path: Path) -> dict[str, Any]:
    started = time.time()
    repo_content = _load_json(repo_content_path)
    skipped = list(repo_content.get("skipped_file_fingerprints") or [])
    records = [_inspect_one(repo_root, item) for item in skipped]
    kind_counts = Counter(str(row.get("semantic_kind")) for row in records)
    status_counts = Counter(str(row.get("semantic_status")) for row in records)
    extension_counts = Counter(str(row.get("extension")) for row in records)
    pdf_records = [row for row in records if row.get("semantic_kind") == "pdf"]
    sqlite_records = [row for row in records if row.get("semantic_kind") == "sqlite_database"]
    pyc_records = [row for row in records if row.get("semantic_kind") == "python_bytecode"]
    source_missing = sum(
        1
        for row in pyc_records
        if row.get("details", {}).get("source_exists") is False
    )
    summary = {
        "skipped_files_from_repo_content": len(skipped),
        "semantic_records": len(records),
        "semantic_status_counts": dict(sorted(status_counts.items())),
        "semantic_kind_counts": dict(sorted(kind_counts.items())),
        "extension_counts": dict(extension_counts.most_common()),
        "semantic_error_count": int(status_counts.get("error", 0)),
        "missing_file_count": int(status_counts.get("missing", 0)),
        "all_skipped_files_classified": bool(skipped) and len(records) == len(skipped),
        "all_existing_files_have_semantic_kind": all(
            row.get("semantic_kind") for row in records if row.get("exists")
        ),
        "pdf_count": len(pdf_records),
        "pdf_page_count_total": sum(
            int(row.get("details", {}).get("page_count") or 0)
            for row in pdf_records
        ),
        "sqlite_database_count": len(sqlite_records),
        "sqlite_schema_object_count_total": sum(
            int(row.get("details", {}).get("schema_object_count") or 0)
            for row in sqlite_records
        ),
        "python_bytecode_count": len(pyc_records),
        "python_bytecode_missing_source_count": source_missing,
    }
    return {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "elapsed_s": round(time.time() - started, 3),
        "scan_mode": "type_aware_semantic_audit_for_repo_skipped_files",
        "repo_content_path": _rel(repo_content_path, repo_root),
        "summary": summary,
        "records": records,
        "largest_records": sorted(
            records,
            key=lambda row: (int(row.get("bytes") or 0), str(row.get("path"))),
            reverse=True,
        )[:50],
        "error_records": [
            row for row in records
            if row.get("semantic_status") in {"error", "missing"}
        ][:100],
    }


def write_markdown(report: dict[str, Any], output: Path) -> None:
    summary = report["summary"]
    lines = [
        "# Repo binary/large skipped-file semantic audit",
        "",
        f"- Generated: `{report.get('generated_at')}`",
        f"- Scan mode: `{report.get('scan_mode')}`",
        f"- Skipped files audited: `{summary.get('semantic_records')}` / `{summary.get('skipped_files_from_repo_content')}`",
        f"- Semantic errors: `{summary.get('semantic_error_count')}`",
        f"- Missing files: `{summary.get('missing_file_count')}`",
        f"- PDFs: `{summary.get('pdf_count')}` files / `{summary.get('pdf_page_count_total')}` pages",
        f"- SQLite DBs: `{summary.get('sqlite_database_count')}` files / `{summary.get('sqlite_schema_object_count_total')}` schema objects",
        f"- Python bytecode: `{summary.get('python_bytecode_count')}` files / `{summary.get('python_bytecode_missing_source_count')}` missing source files",
        "",
        "## Semantic Kinds",
        "",
        "| Kind | Count |",
        "|---|---:|",
    ]
    for kind, count in summary.get("semantic_kind_counts", {}).items():
        lines.append(f"| `{kind}` | {count} |")
    lines.extend(["", "## Largest Records", "", "| Path | Kind | Bytes | Status |", "|---|---|---:|---|"])
    for row in report.get("largest_records", [])[:20]:
        lines.append(
            f"| `{row.get('path')}` | `{row.get('semantic_kind')}` | {row.get('bytes')} | `{row.get('semantic_status')}` |"
        )
    lines.extend(["", "## Notes", ""])
    lines.append(
        "- This audit covers every binary/large file skipped by the repo text-body audit with format classification and safe structural metadata."
    )
    lines.append(
        "- Pickle payloads are not loaded; only opcode samples are inspected to avoid code execution."
    )
    lines.append(
        "- PDF coverage records document family/path metadata and page counts, not OCR or human reading of every page."
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--repo-content", type=Path, default=DEFAULT_REPO_CONTENT)
    parser.add_argument("--output-json", type=Path, default=DEFAULT_OUTPUT_JSON)
    parser.add_argument("--output-md", type=Path, default=DEFAULT_OUTPUT_MD)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_report(args.repo_root.resolve(), args.repo_content)
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    write_markdown(report, args.output_md)
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
