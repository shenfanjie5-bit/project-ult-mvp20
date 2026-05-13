from __future__ import annotations

import json
from pathlib import Path

from scripts import mini_cycle_runtime_bootstrap


def test_runtime_bootstrap_creates_bounded_dirs_without_printing_secrets(
    monkeypatch,
    tmp_path: Path,
) -> None:
    for key in mini_cycle_runtime_bootstrap.REQUIRED_ENV_KEYS + ("DATABASE_URL",):
        monkeypatch.delenv(key, raising=False)

    report_path = tmp_path / "runtime.json"
    exit_code = mini_cycle_runtime_bootstrap.main(
        [
            "--base-dir",
            str(tmp_path / "runtime"),
            "--profile-name",
            "Batch A",
            "--json-report",
            str(report_path),
        ]
    )

    assert exit_code == 2
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    assert payload["profile_name"] == "batch_a"
    assert payload["summary"]["env_file_written"] is False
    assert payload["summary"]["secrets_printed"] is False
    assert payload["postgres"]["status"] == "missing"
    assert payload["generated_env"]["DP_ICEBERG_CATALOG_NAME"] == (
        "data_platform_real_mini_cycle_batch_a"
    )
    assert (tmp_path / "runtime" / "batch_a" / "raw").is_dir()
    assert (tmp_path / "runtime" / "batch_a" / "warehouse").is_dir()
    assert (tmp_path / "runtime" / "batch_a" / "duckdb").is_dir()


def test_runtime_bootstrap_redacts_existing_dp_pg_dsn(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("DP_PG_DSN", "postgresql://user:secret@localhost/db")
    monkeypatch.setenv("DP_TUSHARE_TOKEN", "live-token-value")

    report = mini_cycle_runtime_bootstrap.build_runtime_profile(
        base_dir=tmp_path,
        profile_name="local",
        create_dirs=False,
        create_pg_database=False,
        admin_dsn_env="DATABASE_URL",
    )

    serialized = json.dumps(report)
    assert "user:secret" not in serialized
    assert "live-token-value" not in serialized
    assert report["postgres"]["status"] == "existing_env"
    assert report["postgres"]["dsn"] == "<redacted:set>"
    assert report["summary"]["runtime_profile_ready"] is True
