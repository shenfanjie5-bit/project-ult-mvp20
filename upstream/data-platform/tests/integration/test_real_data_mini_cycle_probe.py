from __future__ import annotations

import json
from pathlib import Path

from scripts import real_data_mini_cycle_probe


def test_probe_blocks_real_cycle_without_required_env(
    monkeypatch,
    tmp_path: Path,
) -> None:
    for key in real_data_mini_cycle_probe.REQUIRED_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)

    report = real_data_mini_cycle_probe.build_probe_report(
        dates=["20260415"],
        symbols=["600519.SH"],
        run_commands=False,
        artifact_dir=tmp_path,
    )

    assert report["scope"] == {
        "dates": ["20260415"],
        "symbols": ["600519.SH"],
    }
    assert report["summary"]["real_cycle_runnable"] is False
    assert report["summary"]["mock_fallback_used"] is False
    assert report["summary"]["allow_p2_real_l1_l8_dry_run"] is False
    assert "daily_refresh_dbt_canonical_real_path" in report["summary"]["blockers"]
    assert {
        key: report["environment"][key]
        for key in real_data_mini_cycle_probe.REQUIRED_ENV_KEYS
    } == {key: "missing" for key in real_data_mini_cycle_probe.REQUIRED_ENV_KEYS}


def test_main_writes_json_report_and_returns_blocked(
    monkeypatch,
    tmp_path: Path,
) -> None:
    for key in real_data_mini_cycle_probe.REQUIRED_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    output = tmp_path / "probe.json"

    exit_code = real_data_mini_cycle_probe.main(
        [
            "--dates",
            "20260415",
            "--symbols",
            "600519.SH,000001.SZ",
            "--json-report",
            str(output),
            "--artifact-dir",
            str(tmp_path / "artifacts"),
            "--no-run",
        ]
    )

    assert exit_code == 2
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["summary"]["real_cycle_runnable"] is False
    assert payload["scope"]["symbols"] == ["600519.SH", "000001.SZ"]
