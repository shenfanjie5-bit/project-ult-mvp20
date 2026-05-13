#!/usr/bin/env python3
from __future__ import annotations

import argparse
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path


REQUIRED_REPOSITORY_FILES: tuple[str, ...] = (
    # Generated artifacts must stay ignored and checked in CI.
    ".gitignore",
    ".github/workflows/ci.yml",
    # Core package and adapter surface.
    "src/data_platform/__init__.py",
    "src/data_platform/adapters/base.py",
    "src/data_platform/adapters/tushare/adapter.py",
    "src/data_platform/adapters/tushare/assets.py",
    "src/data_platform/assets.py",
    "src/data_platform/config/settings.py",
    "src/data_platform/daily_refresh.py",
    "src/data_platform/raw/health.py",
    "src/data_platform/raw/writer.py",
    # Canonical DDL, serving, and schema-evolution implementation.
    "src/data_platform/ddl/iceberg_tables.py",
    "src/data_platform/ddl/runner.py",
    "src/data_platform/serving/canonical_writer.py",
    "src/data_platform/serving/catalog.py",
    "src/data_platform/serving/reader.py",
    "src/data_platform/serving/schema_evolution.py",
    # dbt project artifacts required for structured data reproducibility.
    "src/data_platform/dbt/dbt_project.yml",
    "src/data_platform/dbt/macros/stg_latest_raw.sql",
    "src/data_platform/dbt/models/staging/_schema.yml",
    "src/data_platform/dbt/models/staging/stg_stock_basic.sql",
    "src/data_platform/dbt/models/intermediate/_schema.yml",
    "src/data_platform/dbt/models/intermediate/int_price_bars_adjusted.sql",
    "src/data_platform/dbt/models/marts_v2/_schema.yml",
    "src/data_platform/dbt/models/marts_v2/mart_fact_price_bar_v2.sql",
    "src/data_platform/dbt/models/marts_lineage/_schema.yml",
    "src/data_platform/dbt/models/marts_lineage/mart_lineage_fact_price_bar.sql",
    "src/data_platform/dbt/tests/assert_raw_manifest_fresh.sql",
    # Operator scripts and CI guard.
    "scripts/canonical_backfill.py",
    "scripts/check_repository_artifacts.py",
    "scripts/daily_refresh.sh",
    "scripts/dbt.sh",
    "scripts/init_iceberg_catalog.py",
    # Representative tests for each restored milestone area.
    "tests/test_assets.py",
    "tests/test_repository_artifact_guard.py",
    "tests/adapters/test_tushare.py",
    "tests/dbt/test_tushare_staging_models.py",
    "tests/dbt/test_intermediate_models.py",
    "tests/dbt/test_marts_models.py",
    "tests/ddl/test_iceberg_tables.py",
    "tests/integration/test_daily_refresh.py",
    "tests/raw/test_writer.py",
    "tests/serving/test_canonical_writer.py",
)


@dataclass(frozen=True)
class RepositoryArtifactCheck:
    tracked_paths: tuple[str, ...]
    generated_artifacts: tuple[str, ...]
    missing_required_paths: tuple[str, ...]
    has_platform_source: bool
    has_tests: bool

    @property
    def ok(self) -> bool:
        return (
            not self.generated_artifacts
            and not self.missing_required_paths
            and self.has_platform_source
            and self.has_tests
        )

    def error_messages(self) -> list[str]:
        messages: list[str] = []
        if self.generated_artifacts:
            messages.append("generated Python or runtime artifacts are tracked:")
            messages.extend(f"  - {path}" for path in self.generated_artifacts)
        if self.missing_required_paths:
            messages.append("required repository files are missing:")
            messages.extend(f"  - {path}" for path in self.missing_required_paths)
        if not self.has_platform_source:
            messages.append("no tracked Python source files found under src/data_platform/")
        if not self.has_tests:
            messages.append("no tracked Python test files found under tests/")
        return messages


def git_ls_files(repo_root: Path) -> tuple[str, ...]:
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=repo_root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        stderr = result.stderr.decode(errors="replace").strip()
        raise RuntimeError(f"git ls-files failed: {stderr}")

    return tuple(
        path
        for path in result.stdout.decode(errors="replace").split("\0")
        if path
    )


def check_tracked_paths(paths: Sequence[str]) -> RepositoryArtifactCheck:
    normalized_paths = tuple(_normalize_path(path) for path in paths)
    tracked_path_set = set(normalized_paths)
    generated_artifacts = tuple(
        path for path in normalized_paths if _is_generated_or_runtime_artifact(path)
    )
    missing_required_paths = tuple(
        path for path in REQUIRED_REPOSITORY_FILES if path not in tracked_path_set
    )

    return RepositoryArtifactCheck(
        tracked_paths=normalized_paths,
        generated_artifacts=generated_artifacts,
        missing_required_paths=missing_required_paths,
        has_platform_source=any(_is_platform_source(path) for path in normalized_paths),
        has_tests=any(_is_test_source(path) for path in normalized_paths),
    )


def _normalize_path(path: str) -> str:
    return path.replace("\\", "/").strip("/")


_RUNTIME_ARTIFACT_SUFFIXES = (".parquet", "_manifest.json")
_RUNTIME_ARTIFACT_MARKERS = ("stdout", "stderr", "exitcode")


def _is_generated_or_runtime_artifact(path: str) -> bool:
    parts = path.split("/")
    filename = parts[-1]
    return (
        path.endswith((".pyc", ".pyo"))
        or "__pycache__" in parts
        or any(part.endswith(".egg-info") for part in parts)
        or filename.endswith(_RUNTIME_ARTIFACT_SUFFIXES)
        or any(marker in filename for marker in _RUNTIME_ARTIFACT_MARKERS)
    )


def _is_platform_source(path: str) -> bool:
    return path.startswith("src/data_platform/") and path.endswith(".py")


def _is_test_source(path: str) -> bool:
    return path.startswith("tests/") and path.endswith(".py")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Fail if generated Python/runtime artifacts are tracked or if "
            "required source/test files are missing from the git index."
        )
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="repository root to inspect; defaults to this script's parent checkout",
    )
    args = parser.parse_args(argv)

    try:
        tracked_paths = git_ls_files(args.repo_root)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    check = check_tracked_paths(tracked_paths)
    if check.ok:
        print(
            "Repository artifact guard passed: required source, dbt, scripts, "
            "and tests are tracked, and no generated Python/runtime artifacts "
            "are tracked."
        )
        return 0

    print("Repository artifact guard failed:", file=sys.stderr)
    for message in check.error_messages():
        print(message, file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
