#!/usr/bin/env python3
"""Read and summarize repository text file bodies for audit coverage.

This complements ``audit_inventory.py``. Inventory stats every file but avoids
file bodies; this script reads full bodies for bounded text files, fingerprints
them, and records skip reasons for binary / large files.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable


DEFAULT_PRUNES = (
    ".git",
    ".venv",
    ".playwright-mcp",
    ".pytest_cache",
    ".ruff_cache",
    "FrontEnd/node_modules",
    "FrontEnd/dist",
    "FrontEnd/src-tauri/target",
    "factor_research/.venv_research",
    "project_ult_mvp20.egg-info",
)

BINARY_EXTENSIONS = {
    ".db",
    ".dmg",
    ".gif",
    ".gz",
    ".ico",
    ".jpeg",
    ".jpg",
    ".mp4",
    ".npz",
    ".parquet",
    ".pdf",
    ".png",
    ".pyc",
    ".sqlite",
    ".sqlite-shm",
    ".sqlite-wal",
    ".sqlite3",
    ".zip",
}

RISK_PATTERNS = (
    "TODO",
    "FIXME",
    "NotImplemented",
    "raise NotImplemented",
    "stub",
    "skeleton",
    "placeholder",
    "mock",
    "fixture",
    "UPSTREAM_UNAVAILABLE",
)


@dataclass
class ContentAudit:
    root: Path
    files_seen: int = 0
    bytes_seen: int = 0
    text_files_read: int = 0
    text_bytes_read: int = 0
    text_lines_read: int = 0
    skipped_binary: int = 0
    skipped_too_large: int = 0
    skipped_decode: int = 0
    symlinks_skipped: int = 0
    errors: list[dict[str, str]] = field(default_factory=list)
    extensions: Counter[str] = field(default_factory=Counter)
    skip_reasons: Counter[str] = field(default_factory=Counter)
    risk_hits: Counter[str] = field(default_factory=Counter)
    risky_files: list[dict[str, object]] = field(default_factory=list)
    largest_text_files: list[dict[str, object]] = field(default_factory=list)
    largest_skipped_files: list[dict[str, object]] = field(default_factory=list)
    file_samples: list[dict[str, object]] = field(default_factory=list)
    skipped_file_samples: list[dict[str, object]] = field(default_factory=list)
    skipped_file_fingerprints: list[dict[str, object]] = field(default_factory=list)


def _rel(path: Path, root: Path) -> str:
    return "" if path == root else path.relative_to(root).as_posix()


def _should_prune(rel: str, prunes: Iterable[str]) -> bool:
    if not rel:
        return False
    for prefix in prunes:
        p = prefix.strip("/")
        if rel == p or rel.startswith(p + "/"):
            return True
    return False


def _extension(path: Path) -> str:
    return path.suffix.lower() or "[no_ext]"


def _looks_binary(raw: bytes) -> bool:
    if not raw:
        return False
    if b"\x00" in raw[:8192]:
        return True
    sample = raw[:8192]
    control = sum(1 for b in sample if b < 9 or (13 < b < 32))
    return control / max(1, len(sample)) > 0.05


def _risk_counts(text: str) -> dict[str, int]:
    return {pattern: text.count(pattern) for pattern in RISK_PATTERNS if pattern in text}


def _add_largest(items: list[dict[str, object]], item: dict[str, object], *, limit: int) -> None:
    if limit <= 0:
        return
    items.append(item)
    items.sort(key=lambda row: (int(row.get("bytes", 0)), str(row.get("path", ""))),
               reverse=True)
    del items[limit:]


def _sample_fingerprint(path: Path, *, size: int, sample_bytes: int = 65_536) -> dict[str, object]:
    head = b""
    tail = b""
    with path.open("rb") as fh:
        head = fh.read(sample_bytes)
        if size > sample_bytes:
            fh.seek(max(0, size - sample_bytes))
            tail = fh.read(sample_bytes)
    return {
        "head_tail_sha256": hashlib.sha256(head + b"\0TAIL\0" + tail).hexdigest(),
        "head_bytes": len(head),
        "tail_bytes": len(tail),
    }


def _record_skipped_file(
    out: ContentAudit,
    *,
    path: Path,
    root: Path,
    ext: str,
    size: int,
    reason: str,
    sample_limit: int,
    top_limit: int,
    fingerprint: dict[str, object] | None = None,
) -> None:
    row = {
        "path": _rel(path, root),
        "extension": ext,
        "bytes": size,
        "reason": reason,
    }
    if fingerprint is None:
        try:
            fingerprint = _sample_fingerprint(path, size=size)
        except OSError as exc:
            fingerprint = {"fingerprint_error": str(exc)}
    row.update(fingerprint)
    out.skipped_file_fingerprints.append(row)
    if len(out.skipped_file_samples) < sample_limit:
        out.skipped_file_samples.append(row)
    _add_largest(out.largest_skipped_files, row, limit=top_limit)


def scan(
    root: Path,
    *,
    prunes: tuple[str, ...] = DEFAULT_PRUNES,
    max_text_bytes: int = 2_000_000,
    sample_limit: int = 100,
    top_limit: int = 50,
) -> ContentAudit:
    out = ContentAudit(root=root)
    stack = [root]
    while stack:
        current = stack.pop()
        try:
            with os.scandir(current) as entries:
                for entry in entries:
                    path = Path(entry.path)
                    rel = _rel(path, root)
                    if _should_prune(rel, prunes):
                        continue
                    try:
                        if entry.is_symlink():
                            out.symlinks_skipped += 1
                            continue
                        if entry.is_dir(follow_symlinks=False):
                            stack.append(path)
                            continue
                        if not entry.is_file(follow_symlinks=False):
                            continue
                        st = entry.stat(follow_symlinks=False)
                    except OSError as exc:
                        out.errors.append({"path": rel, "error": str(exc)})
                        continue

                    ext = _extension(path)
                    size = int(st.st_size)
                    out.files_seen += 1
                    out.bytes_seen += size
                    out.extensions[ext] += 1

                    if ext in BINARY_EXTENSIONS:
                        out.skipped_binary += 1
                        reason = f"binary_extension:{ext}"
                        out.skip_reasons[reason] += 1
                        _record_skipped_file(
                            out,
                            path=path,
                            root=root,
                            ext=ext,
                            size=size,
                            reason=reason,
                            sample_limit=sample_limit,
                            top_limit=top_limit,
                        )
                        continue
                    if size > max_text_bytes:
                        out.skipped_too_large += 1
                        reason = "too_large_for_full_text_read"
                        out.skip_reasons[reason] += 1
                        _record_skipped_file(
                            out,
                            path=path,
                            root=root,
                            ext=ext,
                            size=size,
                            reason=reason,
                            sample_limit=sample_limit,
                            top_limit=top_limit,
                        )
                        continue
                    try:
                        raw = path.read_bytes()
                    except OSError as exc:
                        out.errors.append({"path": rel, "error": str(exc)})
                        continue
                    if _looks_binary(raw):
                        out.skipped_binary += 1
                        reason = "binary_sniff"
                        out.skip_reasons[reason] += 1
                        _record_skipped_file(
                            out,
                            path=path,
                            root=root,
                            ext=ext,
                            size=size,
                            reason=reason,
                            sample_limit=sample_limit,
                            top_limit=top_limit,
                            fingerprint={
                                "head_tail_sha256": hashlib.sha256(raw).hexdigest(),
                                "head_bytes": len(raw),
                                "tail_bytes": 0,
                            },
                        )
                        continue
                    try:
                        text = raw.decode("utf-8-sig")
                    except UnicodeDecodeError:
                        try:
                            text = raw.decode("utf-8", errors="replace")
                            out.skipped_decode += 1
                            out.skip_reasons["utf8_decode_replacement"] += 1
                        except Exception as exc:  # noqa: BLE001
                            out.skipped_decode += 1
                            out.skip_reasons["decode_failed"] += 1
                            out.errors.append({"path": rel, "error": str(exc)})
                            continue

                    lines = text.count("\n") + (1 if text and not text.endswith("\n") else 0)
                    digest = hashlib.sha256(raw).hexdigest()
                    risks = _risk_counts(text)
                    out.text_files_read += 1
                    out.text_bytes_read += len(raw)
                    out.text_lines_read += lines
                    for pattern, count in risks.items():
                        out.risk_hits[pattern] += count
                    file_row = {
                        "path": rel,
                        "extension": ext,
                        "bytes": len(raw),
                        "lines": lines,
                        "sha256": digest,
                        "risk_hits": risks,
                    }
                    if len(out.file_samples) < sample_limit:
                        out.file_samples.append(file_row)
                    if risks:
                        out.risky_files.append(file_row)
                    _add_largest(out.largest_text_files, file_row, limit=top_limit)
        except OSError as exc:
            out.errors.append({"path": _rel(current, root), "error": str(exc)})
    out.risky_files.sort(
        key=lambda row: (sum((row.get("risk_hits") or {}).values()), row["path"]),
        reverse=True,
    )
    del out.risky_files[top_limit:]
    return out


def to_json(out: ContentAudit, *, top_limit: int) -> dict[str, object]:
    return {
        "root": str(out.root),
        "scan_mode": "full_body_read_for_bounded_text_files",
        "files_seen": out.files_seen,
        "bytes_seen": out.bytes_seen,
        "text_files_read": out.text_files_read,
        "text_bytes_read": out.text_bytes_read,
        "text_lines_read": out.text_lines_read,
        "skipped_binary": out.skipped_binary,
        "skipped_too_large": out.skipped_too_large,
        "skipped_decode": out.skipped_decode,
        "symlinks_skipped": out.symlinks_skipped,
        "error_count": len(out.errors),
        "errors": out.errors[:20],
        "extensions": dict(out.extensions.most_common(50)),
        "skip_reasons": dict(out.skip_reasons.most_common()),
        "risk_hits": dict(out.risk_hits.most_common()),
        "risky_files": out.risky_files[:top_limit],
        "largest_text_files": out.largest_text_files[:top_limit],
        "largest_skipped_files": out.largest_skipped_files[:top_limit],
        "file_samples": out.file_samples,
        "skipped_file_samples": out.skipped_file_samples,
        "skipped_file_fingerprints_count": len(out.skipped_file_fingerprints),
        "skipped_file_fingerprints": out.skipped_file_fingerprints,
    }


def _markdown(report: dict[str, object]) -> str:
    lines = [
        "# Repo content body audit",
        "",
        f"- Generated at: `{report['generated_at']}`",
        f"- Root: `{report['root']}`",
        f"- Scan mode: `{report['scan_mode']}`",
        "",
        "## Summary",
        "",
        "| Metric | Value |",
        "|---|---:|",
    ]
    for key in (
        "files_seen",
        "text_files_read",
        "text_bytes_read",
        "text_lines_read",
        "skipped_binary",
        "skipped_too_large",
        "skipped_decode",
        "error_count",
    ):
        lines.append(f"| `{key}` | `{report[key]}` |")
    lines.extend(["", "## Skip Reasons", "", "| Reason | Count |", "|---|---:|"])
    for key, value in report["skip_reasons"].items():
        lines.append(f"| `{key}` | {value} |")
    lines.extend([
        "",
        "## Largest Skipped Files",
        "",
        "| Path | Reason | Bytes | Sample SHA-256 |",
        "|---|---|---:|---|",
    ])
    for row in report.get("largest_skipped_files", [])[:10]:
        lines.append(
            f"| `{row['path']}` | `{row['reason']}` | {row['bytes']} | `{row.get('head_tail_sha256', '')}` |"
        )
    lines.extend(["", "## Risk Markers", "", "| Pattern | Count |", "|---|---:|"])
    for key, value in report["risk_hits"].items():
        lines.append(f"| `{key}` | {value} |")
    lines.extend([
        "",
        "## Notes",
        "",
        "- This audit reads full bodies for bounded text files and records SHA-256 digests.",
        "- Binary files, PDFs, SQLite databases, parquet/npz payloads, and text files above the size threshold are counted by reason and fully listed with head/tail SHA-256 fingerprints.",
        "- The audit proves body-level text access and fingerprinting, not human semantic review of every file.",
    ])
    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo-root", default=".")
    ap.add_argument("--max-text-bytes", type=int, default=2_000_000)
    ap.add_argument("--sample-limit", type=int, default=100)
    ap.add_argument("--top-limit", type=int, default=50)
    ap.add_argument("--output-json", default="docs/audit/repo_content_2026-06-18.json")
    ap.add_argument("--output-md", default="docs/audit/repo_content_2026-06-18.md")
    return ap.parse_args()


def main() -> int:
    args = parse_args()
    started = time.time()
    root = Path(args.repo_root).resolve()
    audit = scan(
        root,
        max_text_bytes=args.max_text_bytes,
        sample_limit=args.sample_limit,
        top_limit=args.top_limit,
    )
    report = to_json(audit, top_limit=args.top_limit)
    report["generated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    report["elapsed_s"] = round(time.time() - started, 3)
    report["max_text_bytes"] = args.max_text_bytes
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output_json:
        out = Path(args.output_json)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text + "\n", encoding="utf-8")
    else:
        print(text)
    if args.output_md:
        out_md = Path(args.output_md)
        out_md.parent.mkdir(parents=True, exist_ok=True)
        out_md.write_text(_markdown(report), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
