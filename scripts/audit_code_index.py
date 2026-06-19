#!/usr/bin/env python3
"""Build a static code index for source-bearing project roots.

This is a lightweight audit tool: it reads source files, counts lines/imports/
definitions/risk markers, and writes a JSON summary. It never imports project
modules, so it cannot trigger runtime side effects.
"""
from __future__ import annotations

import argparse
import ast
import json
import os
import re
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path


DEFAULT_ROOTS = (
    "mvp20",
    "scripts",
    "pit_backtest",
    "tests",
    "upstream",
    "factor_research",
    "FrontEnd/src",
    "FrontEnd/scripts",
    "FrontEnd/src-tauri/src",
)

CODE_EXTENSIONS = {
    ".py",
    ".pyi",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".mjs",
    ".cjs",
    ".rs",
    ".sh",
    ".sql",
    ".css",
}

PRUNE_DIRS = {
    ".git",
    ".venv",
    ".venv_research",
    "__pycache__",
    "node_modules",
    "dist",
    "target",
    ".pytest_cache",
    ".ruff_cache",
}

RISK_PATTERNS = (
    "TODO",
    "FIXME",
    "NotImplemented",
    "raise NotImplemented",
    "stub",
    "skeleton",
    "placeholder",
    "fixture: true",
    "UPSTREAM_UNAVAILABLE",
)

TS_IMPORT_RE = re.compile(r"^\s*import\s+", re.MULTILINE)
TS_EXPORT_RE = re.compile(r"^\s*export\s+", re.MULTILINE)
TS_FUNCTION_RE = re.compile(
    r"\bfunction\s+[A-Za-z_][A-Za-z0-9_]*|"
    r"\b(?:const|let|var)\s+[A-Za-z_][A-Za-z0-9_]*\s*=\s*(?:async\s*)?\([^)]*\)\s*=>"
)
RUST_ITEM_RE = re.compile(r"^\s*(?:pub\s+)?(?:async\s+)?(?:fn|struct|enum|trait|impl)\b",
                          re.MULTILINE)


@dataclass
class FileIndex:
    path: str
    extension: str
    bytes: int
    lines: int
    code_lines: int
    imports: int = 0
    definitions: int = 0
    classes: int = 0
    functions: int = 0
    exports: int = 0
    risk_hits: int = 0
    parse_error: str | None = None


@dataclass
class CodeIndex:
    files: list[FileIndex] = field(default_factory=list)
    errors: list[dict[str, str]] = field(default_factory=list)


def _should_prune_dir(path: Path) -> bool:
    return any(part in PRUNE_DIRS for part in path.parts)


def _is_code_file(path: Path) -> bool:
    return path.suffix.lower() in CODE_EXTENSIONS


def iter_code_files(repo: Path, roots: tuple[str, ...]) -> list[Path]:
    files: list[Path] = []
    for root_name in roots:
        root = repo / root_name
        if not root.exists():
            continue
        for current, dirs, names in os.walk(root):
            current_path = Path(current)
            dirs[:] = [d for d in dirs if not _should_prune_dir(current_path / d)]
            if _should_prune_dir(current_path):
                continue
            for name in names:
                path = current_path / name
                if _is_code_file(path):
                    files.append(path)
    return sorted(files)


def _line_counts(text: str) -> tuple[int, int]:
    lines = text.splitlines()
    code_lines = sum(1 for line in lines if line.strip())
    return len(lines), code_lines


def _risk_hits(text: str) -> int:
    return sum(text.count(pattern) for pattern in RISK_PATTERNS)


def _index_python(text: str) -> tuple[int, int, int, int, str | None]:
    try:
        tree = ast.parse(text)
    except SyntaxError as exc:
        return 0, 0, 0, 0, f"SyntaxError: {exc.msg} line {exc.lineno}"
    imports = classes = functions = 0
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            imports += 1
        elif isinstance(node, ast.ClassDef):
            classes += 1
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            functions += 1
    return imports, classes + functions, classes, functions, None


def _index_ts_like(text: str) -> tuple[int, int, int]:
    imports = len(TS_IMPORT_RE.findall(text))
    exports = len(TS_EXPORT_RE.findall(text))
    definitions = len(TS_FUNCTION_RE.findall(text))
    return imports, exports, definitions


def _index_rust(text: str) -> int:
    return len(RUST_ITEM_RE.findall(text))


def index_file(path: Path, repo: Path) -> FileIndex:
    rel = path.relative_to(repo).as_posix()
    raw = path.read_bytes()
    text = raw.decode("utf-8", errors="replace")
    lines, code_lines = _line_counts(text)
    item = FileIndex(
        path=rel,
        extension=path.suffix.lower(),
        bytes=len(raw),
        lines=lines,
        code_lines=code_lines,
        risk_hits=_risk_hits(text),
    )
    if item.extension in {".py", ".pyi"}:
        imports, definitions, classes, functions, parse_error = _index_python(text)
        item.imports = imports
        item.definitions = definitions
        item.classes = classes
        item.functions = functions
        item.parse_error = parse_error
    elif item.extension in {".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"}:
        item.imports, item.exports, item.definitions = _index_ts_like(text)
        item.functions = item.definitions
    elif item.extension == ".rs":
        item.definitions = _index_rust(text)
        item.functions = item.definitions
    return item


def build_index(repo: Path, roots: tuple[str, ...] = DEFAULT_ROOTS) -> CodeIndex:
    out = CodeIndex()
    for path in iter_code_files(repo, roots):
        try:
            out.files.append(index_file(path, repo))
        except OSError as exc:
            out.errors.append({"path": path.as_posix(), "error": str(exc)})
    return out


def _group_for(path: str) -> str:
    if path.startswith("FrontEnd/"):
        parts = path.split("/")
        if len(parts) >= 2:
            return "/".join(parts[:2]) if parts[1] != "src-tauri" else "FrontEnd/src-tauri"
    return path.split("/", 1)[0]


def summarize(index: CodeIndex) -> dict:
    by_ext: Counter[str] = Counter()
    by_group: dict[str, Counter[str]] = defaultdict(Counter)
    total = Counter()
    parse_errors = []
    risk_files = []
    largest = []
    dense_defs = []

    for item in index.files:
        by_ext[item.extension] += 1
        group = _group_for(item.path)
        by_group[group]["files"] += 1
        by_group[group]["bytes"] += item.bytes
        by_group[group]["lines"] += item.lines
        by_group[group]["code_lines"] += item.code_lines
        by_group[group]["imports"] += item.imports
        by_group[group]["definitions"] += item.definitions
        by_group[group]["risk_hits"] += item.risk_hits
        total["files"] += 1
        total["bytes"] += item.bytes
        total["lines"] += item.lines
        total["code_lines"] += item.code_lines
        total["imports"] += item.imports
        total["definitions"] += item.definitions
        total["classes"] += item.classes
        total["functions"] += item.functions
        total["exports"] += item.exports
        total["risk_hits"] += item.risk_hits
        if item.parse_error:
            parse_errors.append({"path": item.path, "error": item.parse_error})
        if item.risk_hits:
            risk_files.append({"path": item.path, "risk_hits": item.risk_hits})
        largest.append({"path": item.path, "lines": item.lines, "bytes": item.bytes})
        dense_defs.append({
            "path": item.path,
            "definitions": item.definitions,
            "functions": item.functions,
            "classes": item.classes,
            "imports": item.imports,
        })

    return {
        "totals": dict(total),
        "extensions": dict(by_ext.most_common()),
        "groups": {
            group: dict(counter)
            for group, counter in sorted(by_group.items())
        },
        "parse_errors": parse_errors[:50],
        "parse_error_count": len(parse_errors),
        "risk_files": sorted(risk_files, key=lambda x: x["risk_hits"], reverse=True)[:50],
        "risk_file_count": len(risk_files),
        "largest_files": sorted(largest, key=lambda x: (x["lines"], x["bytes"]),
                                reverse=True)[:50],
        "definition_dense_files": sorted(dense_defs, key=lambda x: x["definitions"],
                                         reverse=True)[:50],
    }


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo-root", default=".")
    ap.add_argument("--output", default=None)
    ap.add_argument("--roots", default=",".join(DEFAULT_ROOTS),
                    help="comma-separated roots relative to repo")
    return ap.parse_args()


def main() -> int:
    args = parse_args()
    started = time.time()
    repo = Path(args.repo_root).resolve()
    roots = tuple(x.strip() for x in args.roots.split(",") if x.strip())
    index = build_index(repo, roots)
    result = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "elapsed_s": round(time.time() - started, 3),
        "scan_mode": "static_source_text_no_imports",
        "roots": list(roots),
        "errors": index.errors[:50],
        "error_count": len(index.errors),
        **summarize(index),
    }
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
