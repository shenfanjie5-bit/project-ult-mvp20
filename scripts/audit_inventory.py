#!/usr/bin/env python3
"""Build repeatable file inventory summaries for the repo and DockCase.

The audit goal is coverage evidence, not content extraction: this script walks
the selected trees, stats every included file, and summarizes counts, sizes,
extensions, top-level buckets, and largest files. It deliberately avoids reading
file bodies so it is safe for the 2TB external drive.
"""
from __future__ import annotations

import argparse
import json
import os
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable


DEFAULT_REPO_PRUNES = (
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

DEFAULT_DOCKCASE_PRUNES = (
    "_workspace/.venv",
    "_workspace/node_modules",
)


@dataclass
class Bucket:
    files: int = 0
    dirs: int = 0
    bytes: int = 0


@dataclass
class Inventory:
    root: Path
    prunes: tuple[str, ...]
    exists: bool = False
    files: int = 0
    dirs: int = 0
    bytes: int = 0
    symlinks: int = 0
    errors: list[dict[str, str]] = field(default_factory=list)
    extensions: Counter[str] = field(default_factory=Counter)
    top: dict[str, Bucket] = field(default_factory=lambda: defaultdict(Bucket))
    largest: list[tuple[int, str]] = field(default_factory=list)

    def add_largest(self, size: int, rel: str, limit: int) -> None:
        if limit <= 0:
            return
        self.largest.append((size, rel))
        self.largest.sort(reverse=True)
        del self.largest[limit:]


def _norm_rel(path: Path, root: Path) -> str:
    if path == root:
        return ""
    return path.relative_to(root).as_posix()


def _should_prune(rel: str, prunes: Iterable[str]) -> bool:
    if not rel:
        return False
    for prefix in prunes:
        p = prefix.strip("/")
        if rel == p or rel.startswith(p + "/"):
            return True
    return False


def _extension(path: Path) -> str:
    suffix = path.suffix.lower()
    return suffix if suffix else "[no_ext]"


def scan(root: Path, *, prunes: tuple[str, ...], largest_limit: int = 20) -> Inventory:
    inv = Inventory(root=root, prunes=prunes)
    inv.exists = root.exists()
    if not inv.exists:
        return inv

    stack = [root]
    while stack:
        current = stack.pop()
        try:
            with os.scandir(current) as entries:
                for entry in entries:
                    path = Path(entry.path)
                    rel = _norm_rel(path, root)
                    if _should_prune(rel, prunes):
                        continue
                    try:
                        if entry.is_symlink():
                            inv.symlinks += 1
                            continue
                        if entry.is_dir(follow_symlinks=False):
                            inv.dirs += 1
                            bucket = rel.split("/", 1)[0] if rel else "."
                            inv.top[bucket].dirs += 1
                            stack.append(path)
                            continue
                        if not entry.is_file(follow_symlinks=False):
                            continue
                        st = entry.stat(follow_symlinks=False)
                    except OSError as exc:
                        inv.errors.append({"path": rel, "error": str(exc)})
                        continue

                    size = int(st.st_size)
                    inv.files += 1
                    inv.bytes += size
                    inv.extensions[_extension(path)] += 1
                    bucket = rel.split("/", 1)[0] if rel else "."
                    inv.top[bucket].files += 1
                    inv.top[bucket].bytes += size
                    inv.add_largest(size, rel, largest_limit)
        except OSError as exc:
            inv.errors.append({"path": _norm_rel(current, root), "error": str(exc)})
    return inv


def _human_bytes(n: int) -> str:
    units = ("B", "K", "M", "G", "T")
    value = float(n)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f"{value:.1f}{unit}" if unit != "B" else f"{int(value)}B"
        value /= 1024
    return f"{n}B"


def _bucket_json(bucket: Bucket) -> dict[str, int | str]:
    return {
        "files": bucket.files,
        "dirs": bucket.dirs,
        "bytes": bucket.bytes,
        "human_bytes": _human_bytes(bucket.bytes),
    }


def to_json(inv: Inventory, *, top_limit: int) -> dict:
    top_items = sorted(inv.top.items(), key=lambda item: (item[1].bytes, item[1].files),
                       reverse=True)[:top_limit]
    return {
        "root": str(inv.root),
        "exists": inv.exists,
        "prunes": list(inv.prunes),
        "files": inv.files,
        "dirs": inv.dirs,
        "bytes": inv.bytes,
        "human_bytes": _human_bytes(inv.bytes),
        "symlinks_skipped": inv.symlinks,
        "error_count": len(inv.errors),
        "errors": inv.errors[:20],
        "extensions": dict(inv.extensions.most_common(50)),
        "top_level": {name: _bucket_json(bucket) for name, bucket in top_items},
        "largest_files": [
            {"path": rel, "bytes": size, "human_bytes": _human_bytes(size)}
            for size, rel in inv.largest
        ],
    }


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo-root", default=".")
    ap.add_argument("--dockcase-root", default="/Volumes/dockcase2tb")
    ap.add_argument("--output", default=None, help="write JSON summary to this path")
    ap.add_argument("--largest", type=int, default=20)
    ap.add_argument("--top", type=int, default=30)
    ap.add_argument("--skip-dockcase", action="store_true")
    return ap.parse_args()


def main() -> int:
    args = parse_args()
    started = time.time()
    repo = Path(args.repo_root).resolve()
    dock = Path(args.dockcase_root)

    roots: dict[str, tuple[Path, tuple[str, ...]]] = {
        "repo_operational": (repo, DEFAULT_REPO_PRUNES),
    }
    if not args.skip_dockcase:
        roots.update({
            "dockcase": (dock, ()),
            "dockcase_database_all_pruned": (dock / "database_all", DEFAULT_DOCKCASE_PRUNES),
            "dockcase_market_data": (dock / "market_data", ()),
        })

    result = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "elapsed_s": None,
        "scan_mode": "metadata_only_no_file_body_reads",
        "roots": {},
    }
    for name, (root, prunes) in roots.items():
        inv = scan(root, prunes=prunes, largest_limit=args.largest)
        result["roots"][name] = to_json(inv, top_limit=args.top)

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
