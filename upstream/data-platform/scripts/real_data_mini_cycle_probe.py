#!/usr/bin/env python3
"""Probe the real-data mini-cycle backend prerequisites and runnable lanes.

This script is intentionally narrow. It records whether the real Tushare,
PostgreSQL/Iceberg, dbt, cycle metadata, formal serving, and audit/replay
lanes can run in the current operator environment. It never falls back to
mock data when reporting real-data status.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = PROJECT_ROOT.parent
DEFAULT_DATES = ("20260415",)
DEFAULT_SYMBOLS = ("600519.SH", "000001.SZ", "000063.SZ")
REQUIRED_ENV_KEYS = (
    "DP_PG_DSN",
    "DP_TUSHARE_TOKEN",
    "DP_RAW_ZONE_PATH",
    "DP_ICEBERG_WAREHOUSE_PATH",
    "DP_DUCKDB_PATH",
    "DP_ICEBERG_CATALOG_NAME",
)
SENSITIVE_ENV_KEYS = ("DP_PG_DSN", "DATABASE_URL", "DP_TUSHARE_TOKEN")
TAIL_LIMIT = 4000


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    dates = _split_csv(args.dates)
    symbols = _split_csv(args.symbols)
    report = build_probe_report(
        dates=dates,
        symbols=symbols,
        run_commands=not args.no_run,
        artifact_dir=args.artifact_dir,
    )
    _write_json(args.json_report, report)
    if args.print_json:
        json.dump(report, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
        sys.stdout.write("\n")
    return 0 if report["summary"]["real_cycle_runnable"] else 2


def build_probe_report(
    *,
    dates: Sequence[str],
    symbols: Sequence[str],
    run_commands: bool,
    artifact_dir: Path,
) -> dict[str, Any]:
    artifact_dir.mkdir(parents=True, exist_ok=True)
    env_status = _environment_status()
    commands: list[dict[str, Any]] = []

    if run_commands:
        commands.append(
            _run_command(
                name="external_tushare_corpus_smoke",
                command=["bash", "scripts/external_smoke_tushare_corpus.sh"],
                cwd=PROJECT_ROOT,
                timeout=300,
            )
        )
        commands.append(
            _run_command(
                name="tushare_token_raw_ingestion_probe",
                command=[
                    sys.executable,
                    "-m",
                    "data_platform.adapters.tushare.adapter",
                    "--asset",
                    "tushare_daily",
                    "--date",
                    dates[0],
                ],
                cwd=PROJECT_ROOT,
                timeout=60,
            )
        )
        commands.append(
            _run_command(
                name="daily_refresh_real_probe",
                command=[
                    "bash",
                    "scripts/daily_refresh.sh",
                    "--date",
                    dates[0],
                    "--select",
                    "stock_basic,daily",
                    "--json-report",
                    str(artifact_dir / f"daily-refresh-real-probe-{dates[0]}.json"),
                ],
                cwd=PROJECT_ROOT,
                timeout=300,
            )
        )
        commands.append(
            _run_command(
                name="audit_eval_fixture_replay_probe",
                command=[
                    sys.executable,
                    "scripts/spike_replay.py",
                    "--cycle-id",
                    "cycle_20260410",
                    "--object-ref",
                    "recommendation",
                    "--fixtures",
                    "tests/fixtures/spike",
                ],
                cwd=WORKSPACE_ROOT / "audit-eval",
                timeout=60,
            )
        )

    checks = _build_checks(env_status, commands)
    real_cycle_runnable = all(check["status"] == "ok" for check in checks)
    blockers = [
        check["name"]
        for check in checks
        if check["status"] in {"blocked", "failed"}
    ]

    return {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "scope": {"dates": list(dates), "symbols": list(symbols)},
        "environment": env_status,
        "commands": commands,
        "checks": checks,
        "summary": {
            "real_cycle_runnable": real_cycle_runnable,
            "blockers": blockers,
            "mock_fallback_used": False,
            "allow_p2_real_l1_l8_dry_run": real_cycle_runnable,
        },
    }


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dates", default=",".join(DEFAULT_DATES))
    parser.add_argument("--symbols", default=",".join(DEFAULT_SYMBOLS))
    parser.add_argument(
        "--artifact-dir",
        type=Path,
        default=Path("tmp") / "real-data-mini-cycle",
    )
    parser.add_argument("--json-report", type=Path, required=True)
    parser.add_argument("--print-json", action="store_true")
    parser.add_argument("--no-run", action="store_true")
    return parser.parse_args(argv)


def _split_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _environment_status() -> dict[str, str]:
    status = {
        key: ("set" if os.environ.get(key) else "missing")
        for key in REQUIRED_ENV_KEYS
    }
    status["DATABASE_URL"] = "set" if os.environ.get("DATABASE_URL") else "missing"
    status["dbt_executable"] = "set" if _dbt_executable() else "missing"
    status["external_corpus_root"] = (
        "present" if Path("/Volumes/dockcase2tb/database_all").is_dir() else "missing"
    )
    return status


def _dbt_executable() -> str | None:
    return shutil.which("dbt") or (
        str(PROJECT_ROOT / ".venv" / "bin" / "dbt")
        if (PROJECT_ROOT / ".venv" / "bin" / "dbt").exists()
        else None
    )


def _run_command(
    *,
    name: str,
    command: list[str],
    cwd: Path,
    timeout: int,
) -> dict[str, Any]:
    env = os.environ.copy()
    env["PYTHONPATH"] = _pythonpath_for(cwd, env.get("PYTHONPATH", ""))
    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            env=env,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
        )
        return {
            "name": name,
            "command": command,
            "cwd": str(cwd),
            "returncode": completed.returncode,
            "stdout_tail": _redacted_tail(completed.stdout),
            "stderr_tail": _redacted_tail(completed.stderr),
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "name": name,
            "command": command,
            "cwd": str(cwd),
            "returncode": None,
            "timeout_seconds": timeout,
            "stdout_tail": _redacted_tail(exc.stdout or ""),
            "stderr_tail": _redacted_tail(exc.stderr or ""),
            "error": "timeout",
        }


def _pythonpath_for(cwd: Path, existing: str) -> str:
    candidates = [PROJECT_ROOT / "src"]
    if cwd.name == "audit-eval":
        candidates.insert(0, cwd / "src")
    paths = [str(path) for path in candidates]
    if existing:
        paths.append(existing)
    return os.pathsep.join(paths)


def _redacted_tail(value: str | bytes) -> str:
    if isinstance(value, bytes):
        text = value.decode("utf-8", errors="replace")
    else:
        text = value
    for key in SENSITIVE_ENV_KEYS:
        secret = os.environ.get(key)
        if secret:
            text = text.replace(secret, f"<redacted:{key}>")
    return text[-TAIL_LIMIT:]


def _build_checks(
    env_status: dict[str, str],
    commands: Sequence[dict[str, Any]],
) -> list[dict[str, Any]]:
    command_by_name = {command["name"]: command for command in commands}
    missing_env = [
        key for key in REQUIRED_ENV_KEYS if env_status.get(key) == "missing"
    ]

    checks: list[dict[str, Any]] = []
    corpus_command = command_by_name.get("external_tushare_corpus_smoke")
    checks.append(
        _command_check(
            "external_tushare_corpus_available",
            corpus_command,
            blocked_if=env_status["external_corpus_root"] == "missing",
            blocked_reason="external corpus root is not mounted",
        )
    )

    raw_command = command_by_name.get("tushare_token_raw_ingestion_probe")
    raw_status = _command_check(
        "tushare_token_raw_ingestion",
        raw_command,
        blocked_if=env_status["DP_TUSHARE_TOKEN"] == "missing",
        blocked_reason="DP_TUSHARE_TOKEN is missing; no mock fallback used",
    )
    checks.append(raw_status)

    daily_command = command_by_name.get("daily_refresh_real_path")
    if daily_command is None:
        daily_command = command_by_name.get("daily_refresh_real_probe")
    checks.append(
        _command_check(
            "daily_refresh_dbt_canonical_real_path",
            daily_command,
            blocked_if=bool(missing_env),
            blocked_reason="missing required DP environment: " + ", ".join(missing_env),
        )
    )

    pg_dependent_status = "blocked" if missing_env else "unknown"
    pg_dependent_reason = (
        "requires real PostgreSQL/Iceberg daily refresh success first"
        if missing_env
        else "not executed by this probe"
    )
    for name in (
        "cycle_metadata_candidate_freeze",
        "formal_object_commit_publish_manifest",
        "formal_serving_manifest_snapshot_read",
    ):
        checks.append({"name": name, "status": pg_dependent_status, "reason": pg_dependent_reason})

    audit_command = command_by_name.get("audit_eval_fixture_replay_probe")
    audit_check = _command_check(
        "audit_eval_replay_entrypoint",
        audit_command,
        blocked_if=False,
        blocked_reason="",
    )
    if audit_check["status"] == "ok":
        audit_check["real_cycle_binding"] = "fixture_only"
        audit_check["reason"] = (
            "audit-eval replay CLI is available, but this probe found no "
            "real cycle manifest gateway wired to data-platform formal snapshots"
        )
    checks.append(audit_check)
    return checks


def _command_check(
    name: str,
    command: dict[str, Any] | None,
    *,
    blocked_if: bool,
    blocked_reason: str,
) -> dict[str, Any]:
    if blocked_if:
        return {"name": name, "status": "blocked", "reason": blocked_reason}
    if command is None:
        return {"name": name, "status": "unknown", "reason": "command not run"}
    if command.get("returncode") == 0:
        return {"name": name, "status": "ok", "command": command["name"]}
    return {
        "name": name,
        "status": "failed",
        "command": command["name"],
        "returncode": command.get("returncode"),
    }


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    raise SystemExit(main())
