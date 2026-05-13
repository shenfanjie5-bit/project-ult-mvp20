from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
GUARD_SCRIPT = PROJECT_ROOT / "scripts" / "check_repository_artifacts.py"
HOLDINGS_QUEUE_FREEZE_RUNBOOK = (
    PROJECT_ROOT / "docs" / "runbook" / "holdings-queue-freeze-rollout.md"
)


def _load_guard_module() -> object:
    spec = importlib.util.spec_from_file_location(
        "check_repository_artifacts", GUARD_SCRIPT
    )
    assert spec is not None
    assert spec.loader is not None

    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_guard_accepts_tracked_source_and_tests_without_generated_artifacts() -> None:
    guard = _load_guard_module()

    check = guard.check_tracked_paths(guard.REQUIRED_REPOSITORY_FILES)

    assert check.ok
    assert check.generated_artifacts == ()
    assert check.missing_required_paths == ()
    assert check.error_messages() == []


def test_guard_rejects_token_source_and_test_only_repository() -> None:
    guard = _load_guard_module()

    check = guard.check_tracked_paths(
        [
            "src/data_platform/__init__.py",
            "tests/test_smoke.py",
        ]
    )

    assert not check.ok
    messages = check.error_messages()
    assert "required repository files are missing:" in messages
    assert "  - src/data_platform/adapters/tushare/adapter.py" in messages
    assert "  - src/data_platform/dbt/dbt_project.yml" in messages
    assert "  - scripts/dbt.sh" in messages


def test_guard_rejects_generated_artifacts_and_missing_sources() -> None:
    guard = _load_guard_module()

    check = guard.check_tracked_paths(
        [
            "src/data_platform/adapters/__pycache__/adapter.cpython-314.pyc",
            "src/project_ult_data_platform.egg-info/PKG-INFO",
            "tests/dbt/fixtures/raw/tushare/weekly/dt=20260415/_manifest.json",
            "tests/dbt/fixtures/raw/tushare/weekly/dt=20260415/run.parquet",
            "tmp/provider.stdout.txt",
            "tmp/provider.stderr.txt",
            "tmp/provider.exitcode",
            "README.md",
        ]
    )

    assert not check.ok
    assert check.generated_artifacts == (
        "src/data_platform/adapters/__pycache__/adapter.cpython-314.pyc",
        "src/project_ult_data_platform.egg-info/PKG-INFO",
        "tests/dbt/fixtures/raw/tushare/weekly/dt=20260415/_manifest.json",
        "tests/dbt/fixtures/raw/tushare/weekly/dt=20260415/run.parquet",
        "tmp/provider.stdout.txt",
        "tmp/provider.stderr.txt",
        "tmp/provider.exitcode",
    )
    messages = check.error_messages()
    assert messages[:8] == [
        "generated Python or runtime artifacts are tracked:",
        "  - src/data_platform/adapters/__pycache__/adapter.cpython-314.pyc",
        "  - src/project_ult_data_platform.egg-info/PKG-INFO",
        "  - tests/dbt/fixtures/raw/tushare/weekly/dt=20260415/_manifest.json",
        "  - tests/dbt/fixtures/raw/tushare/weekly/dt=20260415/run.parquet",
        "  - tmp/provider.stdout.txt",
        "  - tmp/provider.stderr.txt",
        "  - tmp/provider.exitcode",
    ]
    assert "required repository files are missing:" in messages
    assert "  - src/data_platform/adapters/tushare/adapter.py" in messages
    assert "  - src/data_platform/dbt/dbt_project.yml" in messages
    assert messages[-2:] == [
        "no tracked Python source files found under src/data_platform/",
        "no tracked Python test files found under tests/",
    ]


def test_git_index_has_source_tests_and_no_generated_artifacts() -> None:
    guard = _load_guard_module()

    check = guard.check_tracked_paths(guard.git_ls_files(PROJECT_ROOT))

    assert check.ok, "\n".join(check.error_messages())


def test_gitignore_excludes_generated_python_artifacts() -> None:
    gitignore = (PROJECT_ROOT / ".gitignore").read_text()

    assert "__pycache__/" in gitignore
    assert "*.py[cod]" in gitignore
    assert "*.egg-info/" in gitignore
    assert "tests/dbt/fixtures/raw/**/*.parquet" in gitignore
    assert "tests/dbt/fixtures/raw/**/_manifest.json" in gitignore
    assert "*stdout*" in gitignore
    assert "*stderr*" in gitignore
    assert "*exitcode" in gitignore


def test_holdings_queue_freeze_runbook_uses_sanitized_evidence_shape() -> None:
    text = HOLDINGS_QUEUE_FREEZE_RUNBOOK.read_text(encoding="utf-8")

    receipt_block = _fenced_block_after(text, "## Receipt Shape", "json")
    targeted_freeze_block = _fenced_block_after(
        text,
        "## Targeted Freeze Shape",
        "python",
    )

    assert '"payload":' not in receipt_block
    assert "provider_payload" not in receipt_block
    assert "raw_payload_path" not in receipt_block
    assert "submit_candidate_idempotent" in text
    assert "CandidateSubmitReceipt.as_public_dict()" in text
    assert "`submit_candidate` is not acceptable" in text
    assert "DP_PG_DSN=<redacted-dsn>" in text
    assert "stdout/stderr" in text
    assert "rejection_counts" in text
    assert "rejections_by_reason_type" in text
    assert "submitted_by=\"subsystem-holdings\"" in text
    assert "payload_type=\"Ex-3\"" in text
    assert "submitted_by=\"subsystem-holdings\"" in targeted_freeze_block
    assert "payload_type=\"Ex-3\"" in targeted_freeze_block
    assert "not broad/default rollout" in text
    assert "does not enable broad/default freeze rollout" in text
    assert "commit hash" in text
    assert _unexpected_runbook_fragments(text) == []


def _fenced_block_after(text: str, heading: str, language: str) -> str:
    section_start = text.index(heading)
    marker = f"```{language}"
    start = text.index(marker, section_start) + len(marker)
    end = text.index("```", start)
    return text[start:end]


def _unexpected_runbook_fragments(text: str) -> list[str]:
    forbidden_fragments = (
        "/Users/",
        "/Volumes/",
        ".parquet",
        "_manifest.json",
        "stdout_tail",
        "stderr_tail",
        '"stdout"',
        '"stderr"',
        "exitcode:",
        "raw_payload_path",
        "provider_payload",
        "DATABASE_URL=",
        "NEO4J_PASSWORD=",
        "postgresql://",
        "bolt://",
        "neo4j+s://",
    )
    matches = [fragment for fragment in forbidden_fragments if fragment in text]
    non_redacted_pg_dsn = [
        line.strip()
        for line in text.splitlines()
        if "DP_PG_DSN=" in line and "DP_PG_DSN=<redacted-dsn>" not in line
    ]
    matches.extend(non_redacted_pg_dsn)
    return matches
