#!/usr/bin/env python3
"""Run a targeted semantic pass for selected DockCase header signatures."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import audit_dockcase_csv_semantics as base

DEFAULT_SOURCE = ROOT / "docs/audit/dockcase_csv_semantics_2026-06-18.json"
DEFAULT_DATA_ROOT = Path("/Volumes/dockcase2tb/database_all")
DEFAULT_JSON_OUTPUT = ROOT / "docs/audit/dockcase_backlog_batch_2026-06-18.json"
DEFAULT_MD_OUTPUT = ROOT / "docs/audit/dockcase_backlog_batch_2026-06-18.md"


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _target_signatures(source: dict[str, Any], ranks: set[int]) -> dict[int, tuple[str, ...]]:
    out: dict[int, tuple[str, ...]] = {}
    for row in source.get("signatures", []):
        rank = int(row.get("signature_rank") or 0)
        if rank in ranks:
            out[rank] = tuple(str(col) for col in row.get("columns", []))
    return out


def _rank_for_header(targets: dict[int, tuple[str, ...]], header: tuple[str, ...]) -> int | None:
    for rank, columns in targets.items():
        if columns == header:
            return rank
    return None


def _sample_file(sig: base.SignatureSample, path: Path, rel: str, *, rows_per_file: int) -> None:
    file_rows = 0
    for row in base._iter_rows(path, max_rows=rows_per_file):
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
                    {"path": rel, "column_count": len(sig.columns), "row_width": len(row)}
                )
        base._check_domain_row(sig, rel, row)
        for idx, column in enumerate(sig.columns):
            value = row[idx] if idx < len(row) else ""
            base._profile_value(sig, column, value)
    if file_rows:
        sig.sampled_files += 1


def build_report(
    source_path: Path,
    data_root: Path,
    *,
    ranks: set[int],
    max_files_per_signature: int,
    rows_per_file: int,
    as_of_date: dt.date,
) -> dict[str, Any]:
    started = time.time()
    source = _load(source_path)
    targets = _target_signatures(source, ranks)
    samples = {
        rank: base.SignatureSample(columns=columns)
        for rank, columns in targets.items()
    }
    for sample in samples.values():
        for column in sample.columns:
            sample.column_profiles.setdefault(column, base.ColumnProfile())
    discovered = {rank: 0 for rank in targets}
    selected = {rank: 0 for rank in targets}
    errors: list[dict[str, str]] = []
    files_seen = 0

    if not data_root.exists():
        return {
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "status": "missing_data_root",
            "data_root": str(data_root),
            "source_path": str(source_path),
            "target_ranks": sorted(ranks),
            "summary": {"files_seen": 0, "matched_files": 0, "sampled_rows": 0},
            "signatures": [],
        }

    for path in base._walk_csv(data_root, base.DEFAULT_PRUNES):
        files_seen += 1
        rel = base._rel(path, data_root)
        try:
            header = base._read_header(path)
        except Exception as exc:  # noqa: BLE001
            errors.append({"path": rel, "error": str(exc)})
            continue
        rank = _rank_for_header(targets, header)
        if rank is None:
            continue
        discovered[rank] += 1
        sig = samples[rank]
        sig.file_count += 1
        if len(sig.examples) < max_files_per_signature:
            sig.examples.append(rel)
        if selected[rank] >= max_files_per_signature:
            continue
        selected[rank] += 1
        try:
            _sample_file(sig, path, rel, rows_per_file=rows_per_file)
        except Exception as exc:  # noqa: BLE001
            sig.read_errors.append({"path": rel, "error": str(exc)})

    signature_payloads: list[dict[str, Any]] = []
    for rank in sorted(samples):
        payload = base._signature_payload(rank, samples[rank], as_of_date=as_of_date)
        payload["target_signature_rank"] = rank
        payload["matched_files"] = discovered[rank]
        payload["selected_files_limit"] = max_files_per_signature
        payload["additional_files_sampled_this_batch"] = payload["sampled_files"]
        signature_payloads.append(payload)

    return {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "elapsed_s": round(time.time() - started, 3),
        "status": "ready",
        "data_root": str(data_root),
        "source_path": str(source_path),
        "target_ranks": sorted(ranks),
        "parameters": {
            "max_files_per_signature": max_files_per_signature,
            "rows_per_file": rows_per_file,
            "as_of_date": as_of_date.isoformat(),
        },
        "summary": {
            "files_seen": files_seen,
            "matched_files": sum(discovered.values()),
            "sampled_files": sum(row["sampled_files"] for row in signature_payloads),
            "sampled_rows": sum(row["sampled_rows"] for row in signature_payloads),
            "row_width_mismatch_count": sum(row["row_width_mismatch_count"] for row in signature_payloads),
            "issue_counts": _sum_issue_counts(signature_payloads),
            "header_read_error_count": len(errors),
        },
        "header_read_errors": errors[:50],
        "signatures": signature_payloads,
    }


def _sum_issue_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        for issue, count in (row.get("issue_counts") or {}).items():
            counts[str(issue)] = counts.get(str(issue), 0) + int(count)
    return counts


def write_markdown(report: dict[str, Any], output: Path) -> None:
    summary = report.get("summary", {})
    lines = [
        "# DOCKCASE backlog batch semantic pass",
        "",
        f"- Generated: `{report.get('generated_at')}`",
        f"- Status: `{report.get('status')}`",
        f"- Data root: `{report.get('data_root')}`",
        f"- Source: `{report.get('source_path')}`",
        f"- Target ranks: `{report.get('target_ranks')}`",
        f"- Matched files: `{summary.get('matched_files')}`",
        f"- Sampled files / rows: `{summary.get('sampled_files')}` / `{summary.get('sampled_rows')}`",
        f"- Header read errors: `{summary.get('header_read_error_count')}`",
        "",
        "## Issue Counts",
        "",
    ]
    issues = summary.get("issue_counts") or {}
    if issues:
        for issue, count in sorted(issues.items()):
            lines.append(f"- `{issue}`: {count}")
    else:
        lines.append("- No issues found in this batch.")
    lines.extend(["", "## Signatures", ""])
    for row in report.get("signatures", []):
        lines.extend([
            f"### Rank `{row.get('target_signature_rank')}`",
            "",
            f"- Matched files: `{row.get('matched_files')}`",
            f"- Sampled files / rows: `{row.get('sampled_files')}` / `{row.get('sampled_rows')}`",
            f"- Columns: `{', '.join(row.get('columns', [])[:12])}`",
            "",
        ])
        examples = row.get("examples", [])[:8]
        if examples:
            lines.append("Examples:")
            for example in examples:
                lines.append(f"- `{example}`")
            lines.append("")
    output.write_text("\n".join(lines), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default=str(DEFAULT_SOURCE))
    parser.add_argument("--data-root", default=str(DEFAULT_DATA_ROOT))
    parser.add_argument("--ranks", default="46")
    parser.add_argument("--max-files-per-signature", type=int, default=50)
    parser.add_argument("--rows-per-file", type=int, default=200)
    parser.add_argument("--as-of-date", default="2026-06-18")
    parser.add_argument("--output", default=str(DEFAULT_JSON_OUTPUT))
    parser.add_argument("--markdown-output", default=str(DEFAULT_MD_OUTPUT))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    ranks = {int(item.strip()) for item in args.ranks.split(",") if item.strip()}
    report = build_report(
        Path(args.source),
        Path(args.data_root),
        ranks=ranks,
        max_files_per_signature=args.max_files_per_signature,
        rows_per_file=args.rows_per_file,
        as_of_date=dt.date.fromisoformat(args.as_of_date),
    )
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_markdown(report, Path(args.markdown_output))
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
