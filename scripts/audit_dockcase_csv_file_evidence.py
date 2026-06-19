#!/usr/bin/env python3
"""Build per-file evidence for every DockCase business CSV.

The stratified semantic audit reads bounded rows by header signature. This
companion pass is file-complete: every business CSV gets a compact row with
size, header signature, first/tail-row width evidence, and a head/tail binary
fingerprint. It still does not claim semantic validation of every CSV row.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import audit_dockcase_csv_semantics as base

DEFAULT_DATA_ROOT = Path("/Volumes/dockcase2tb/database_all")
DEFAULT_JSON_OUTPUT = ROOT / "docs/audit/dockcase_csv_file_evidence_2026-06-19.json"
DEFAULT_MD_OUTPUT = ROOT / "docs/audit/dockcase_csv_file_evidence_2026-06-19.md"
DEFAULT_EVIDENCE_JSONL_GZ = (
    ROOT / "docs/audit/dockcase_csv_file_evidence_2026-06-19.jsonl.gz"
)


def _head_tail_fingerprint(
    path: Path,
    *,
    size: int,
    sample_bytes: int,
) -> dict[str, Any]:
    with path.open("rb") as fh:
        head = fh.read(sample_bytes)
        if size > sample_bytes:
            fh.seek(max(0, size - sample_bytes))
            tail = fh.read(sample_bytes)
        else:
            tail = b""
    return {
        "head_tail_sha256": hashlib.sha256(head + b"\0TAIL\0" + tail).hexdigest(),
        "head_bytes": len(head),
        "tail_bytes": len(tail),
    }


def _header_signature(columns: tuple[str, ...]) -> str:
    raw = "\x1f".join(columns).encode("utf-8", errors="replace")
    return hashlib.sha256(raw).hexdigest()


def _first_data_row(path: Path) -> tuple[str, ...] | None:
    with path.open("r", encoding="utf-8-sig", errors="replace", newline="") as fh:
        reader = csv.reader(fh)
        next(reader, None)
        for row in reader:
            if any(cell.strip() for cell in row):
                return tuple(row)
    return None


def _last_data_row_from_tail(
    path: Path,
    *,
    size: int,
    header: tuple[str, ...],
    sample_bytes: int,
) -> tuple[str, ...] | None:
    with path.open("rb") as fh:
        if size > sample_bytes:
            fh.seek(max(0, size - sample_bytes))
        raw = fh.read(sample_bytes)
    text = raw.decode("utf-8-sig", errors="replace")
    lines = text.splitlines()
    if size > sample_bytes and lines:
        lines = lines[1:]
    header_line = ",".join(header)
    for line in reversed(lines):
        if not line.strip() or line.strip() == header_line:
            continue
        try:
            parsed = next(csv.reader([line]))
        except csv.Error:
            continue
        if any(cell.strip() for cell in parsed):
            return tuple(parsed)
    return None


def build_report(
    data_root: Path,
    *,
    sample_bytes: int,
    prunes: tuple[str, ...] = base.DEFAULT_PRUNES,
) -> dict[str, Any]:
    started = time.time()
    rows: list[dict[str, Any]] = []
    header_errors: list[dict[str, str]] = []
    fingerprint_errors: list[dict[str, str]] = []
    signature_counts: Counter[str] = Counter()
    column_count_counts: Counter[int] = Counter()
    total_bytes = 0
    files_seen = 0
    first_last_width_mismatch_count = 0
    files_with_data_row_evidence = 0
    header_only_or_no_tail_data = 0

    if not data_root.exists():
        return {
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "elapsed_s": 0.0,
            "data_root": str(data_root),
            "exists": False,
            "scan_mode": "missing_data_root",
            "summary": {"csv_files_seen": 0, "file_evidence_count": 0},
            "file_evidence": [],
        }

    for path in base._walk_csv(data_root, prunes):
        files_seen += 1
        rel = base._rel(path, data_root)
        size = int(path.stat().st_size)
        total_bytes += size
        row: dict[str, Any] = {
            "path": rel,
            "bytes": size,
        }
        try:
            row.update(_head_tail_fingerprint(path, size=size, sample_bytes=sample_bytes))
        except OSError as exc:
            fingerprint_errors.append({"path": rel, "error": str(exc)})
            row["fingerprint_error"] = str(exc)

        try:
            header = base._read_header(path)
        except Exception as exc:  # noqa: BLE001
            header_errors.append({"path": rel, "error": str(exc)})
            row.update({
                "header_read_ok": False,
                "header_error": str(exc),
                "data_row_evidence": "fingerprint_only",
            })
            rows.append(row)
            continue

        signature = _header_signature(header)
        signature_counts[signature] += 1
        column_count_counts[len(header)] += 1
        row.update({
            "header_read_ok": True,
            "header_signature_sha256": signature,
            "column_count": len(header),
        })
        try:
            first_row = _first_data_row(path)
            last_row = _last_data_row_from_tail(
                path,
                size=size,
                header=header,
                sample_bytes=sample_bytes,
            )
        except Exception as exc:  # noqa: BLE001
            row.update({
                "data_row_evidence": "header_only_read_error",
                "data_row_error": str(exc),
            })
            rows.append(row)
            continue

        first_width = len(first_row) if first_row is not None else None
        last_width = len(last_row) if last_row is not None else None
        row.update({
            "has_first_data_row": first_row is not None,
            "has_tail_data_row": last_row is not None,
            "first_data_row_width": first_width,
            "tail_data_row_width": last_width,
            "first_tail_width_mismatch": (
                first_width is not None
                and last_width is not None
                and first_width != last_width
            ),
            "data_row_evidence": (
                "header_first_tail"
                if first_row is not None and last_row is not None
                else "header_only_or_empty"
            ),
        })
        if row["first_tail_width_mismatch"]:
            first_last_width_mismatch_count += 1
        if first_row is not None or last_row is not None:
            files_with_data_row_evidence += 1
        else:
            header_only_or_no_tail_data += 1
        rows.append(row)

    summary = {
        "csv_files_seen": files_seen,
        "file_evidence_count": len(rows),
        "total_bytes": total_bytes,
        "header_read_error_count": len(header_errors),
        "fingerprint_error_count": len(fingerprint_errors),
        "signature_count": len(signature_counts),
        "files_with_data_row_evidence": files_with_data_row_evidence,
        "header_only_or_no_tail_data_files": header_only_or_no_tail_data,
        "first_tail_width_mismatch_count": first_last_width_mismatch_count,
        "all_seen_files_have_evidence_rows": len(rows) == files_seen,
        "all_seen_files_have_head_tail_fingerprint": all(
            bool(row.get("head_tail_sha256")) for row in rows
        ),
        "coverage_boundary": {
            "all_business_csv_files_have_file_evidence": True,
            "full_row_semantic_scan": False,
            "tail_row_is_derived_from_tail_byte_sample": True,
        },
        "top_column_counts": [
            {"column_count": count, "files": files}
            for count, files in column_count_counts.most_common(20)
        ],
        "top_header_signatures": [
            {"header_signature_sha256": signature, "files": files}
            for signature, files in signature_counts.most_common(20)
        ],
    }
    return {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "elapsed_s": round(time.time() - started, 3),
        "data_root": str(data_root),
        "exists": True,
        "scan_mode": "all_business_csv_file_evidence",
        "parameters": {
            "sample_bytes": sample_bytes,
            "prunes": list(prunes),
        },
        "summary": summary,
        "header_read_errors": header_errors[:100],
        "fingerprint_errors": fingerprint_errors[:100],
        "file_evidence": rows,
    }


def write_markdown(report: dict[str, Any], output: Path) -> None:
    summary = report.get("summary", {})
    lines = [
        "# DOCKCASE CSV file evidence audit",
        "",
        f"- Generated: `{report.get('generated_at')}`",
        f"- Data root: `{report.get('data_root')}`",
        f"- Scan mode: `{report.get('scan_mode')}`",
        f"- Elapsed: `{report.get('elapsed_s')}` seconds",
        f"- CSV files seen: `{summary.get('csv_files_seen')}`",
        f"- File evidence rows: `{summary.get('file_evidence_count')}`",
        f"- Header signatures: `{summary.get('signature_count')}`",
        f"- Header read errors: `{summary.get('header_read_error_count')}`",
        f"- Fingerprint errors: `{summary.get('fingerprint_error_count')}`",
        f"- Files with first/tail data-row evidence: `{summary.get('files_with_data_row_evidence')}`",
        f"- First/tail width mismatches: `{summary.get('first_tail_width_mismatch_count')}`",
        "",
        "## Boundary",
        "",
        "- Every business CSV gets a file-level evidence row when the root is mounted.",
        "- The JSON output keeps a compact sample; the full per-file evidence list is stored as gzip JSONL.",
        "- This pass fingerprints head/tail bytes and checks first/tail row widths; it does not semantically validate every row.",
        "",
        "## Top Column Counts",
        "",
        "| Columns | Files |",
        "|---:|---:|",
    ]
    for row in summary.get("top_column_counts", []):
        lines.append(f"| `{row.get('column_count')}` | `{row.get('files')}` |")
    lines.extend(["", "## Top Header Signatures", "", "| SHA-256 | Files |", "|---|---:|"])
    for row in summary.get("top_header_signatures", [])[:10]:
        lines.append(f"| `{row.get('header_signature_sha256')}` | `{row.get('files')}` |")
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", default=str(DEFAULT_DATA_ROOT))
    parser.add_argument("--sample-bytes", type=int, default=65_536)
    parser.add_argument("--output-json", default=str(DEFAULT_JSON_OUTPUT))
    parser.add_argument("--output-md", default=str(DEFAULT_MD_OUTPUT))
    parser.add_argument("--evidence-jsonl-gz", default=str(DEFAULT_EVIDENCE_JSONL_GZ))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_report(
        Path(args.data_root),
        sample_bytes=args.sample_bytes,
    )
    evidence_rows = list(report.pop("file_evidence", []))
    evidence_out = Path(args.evidence_jsonl_gz)
    evidence_out.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(evidence_out, "wt", encoding="utf-8") as fh:
        for row in evidence_rows:
            fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    report["file_evidence_storage"] = {
        "format": "jsonl.gz",
        "path": str(evidence_out),
        "row_count": len(evidence_rows),
    }
    report["file_evidence_sample"] = evidence_rows[:100]
    out = Path(args.output_json)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md = Path(args.output_md)
    md.parent.mkdir(parents=True, exist_ok=True)
    write_markdown(report, md)
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
