"""Tests for ``scripts/collector_supervisor.sh``.

These are integration tests — they actually invoke the bash script with
subprocess and verify start/stop/restart/status/tail behave correctly.
To keep CI cheap we set ``COLLECTOR_SOURCE=mock`` so no external API is
hit; the python collector still runs end-to-end and writes to a
temp-redirected SQLite path.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "collector_supervisor.sh"
PID_FILE = ROOT / "runtime" / "collector.pid"
LOG_FILE = ROOT / "runtime" / "collector.log"


def _run(*args: str, env_extra: dict | None = None) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    # Use the mock source so tests don't touch live APIs / quotas.
    env.setdefault("COLLECTOR_SOURCE", "mock")
    env.setdefault("COLLECTOR_INTERVAL", "2")
    # The collector daemon refuses fabricated mock sources in production
    # (see scripts/collector.py MOCK_GATE_ENV). This smoke test legitimately
    # exercises the mock path end-to-end, so opt in explicitly. The var
    # propagates through the supervisor's nohup subshell into the python child.
    env.setdefault("MVP20_ALLOW_MOCK", "1")
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        [str(SCRIPT), *args],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
    )


@pytest.fixture(autouse=True)
def _ensure_executable_and_clean():
    """Make sure the script is +x, and that we start each test STOPPED."""

    if not SCRIPT.exists():
        pytest.skip(f"{SCRIPT} not present")
    SCRIPT.chmod(0o755)
    # Skip if user does not have a .venv (CI may not).
    if not (ROOT / ".venv" / "bin" / "python").exists():
        pytest.skip("project .venv missing; supervisor smoke test skipped")
    # Quiet stop just in case a prior test crashed mid-run.
    _run("stop")
    yield
    _run("stop")


def _wait_until(predicate, timeout: float = 10.0, interval: float = 0.3) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return False


def test_status_when_stopped():
    """status before start should report STOPPED."""

    result = _run("status")
    assert result.returncode == 0
    assert "STOPPED" in result.stdout


def test_start_writes_pid_and_log():
    """start should create runtime/collector.pid and runtime/collector.log."""

    result = _run("start")
    assert result.returncode == 0
    assert "collector started" in result.stdout or "already running" in result.stdout
    assert _wait_until(lambda: PID_FILE.exists()), "PID file never appeared"

    # Status flips to RUNNING.
    status = _run("status")
    assert "RUNNING" in status.stdout
    # Log file should grow within a couple of seconds.
    assert _wait_until(lambda: LOG_FILE.exists() and LOG_FILE.stat().st_size > 0)


def test_double_start_is_idempotent():
    """Calling start twice should not spawn a second supervisor."""

    _run("start")
    assert _wait_until(lambda: PID_FILE.exists())
    first_pid = PID_FILE.read_text().strip()

    second = _run("start")
    assert second.returncode == 0
    assert "already running" in second.stdout
    assert PID_FILE.read_text().strip() == first_pid


def test_stop_removes_pid_and_reports_stopped():
    """stop should kill the supervisor and remove the PID file."""

    _run("start")
    assert _wait_until(lambda: PID_FILE.exists())

    stop = _run("stop")
    assert stop.returncode == 0
    assert "stopped" in stop.stdout
    assert _wait_until(lambda: not PID_FILE.exists())

    status = _run("status")
    assert "STOPPED" in status.stdout


def test_restart_yields_new_pid():
    """restart should kill the old supervisor and spawn a new one."""

    _run("start")
    assert _wait_until(lambda: PID_FILE.exists())
    old_pid = PID_FILE.read_text().strip()

    result = _run("restart")
    assert result.returncode == 0
    assert _wait_until(lambda: PID_FILE.exists() and PID_FILE.read_text().strip() != old_pid)


def test_tail_returns_log_lines():
    """tail N should print at most N tail lines."""

    _run("start")
    # Give the collector a moment to write a few lines.
    assert _wait_until(lambda: LOG_FILE.exists() and LOG_FILE.stat().st_size > 0, timeout=15)
    result = _run("tail", "5")
    assert result.returncode == 0
    # Should be at most 5 lines of output (collector lines are present).
    lines = [ln for ln in result.stdout.splitlines() if ln.strip()]
    assert len(lines) <= 5


def test_stale_pid_file_recovers():
    """If the supervisor process is gone but PID file lingers, status reports
    STOPPED and a fresh start succeeds."""

    # Write a definitely-dead PID into the file (PID 1 belongs to launchd / init
    # and kill -0 will succeed; use a high unlikely-to-exist PID instead).
    PID_FILE.parent.mkdir(parents=True, exist_ok=True)
    PID_FILE.write_text("999999\n")

    status = _run("status")
    assert "STOPPED" in status.stdout

    start = _run("start")
    assert start.returncode == 0
    assert _wait_until(
        lambda: PID_FILE.exists() and PID_FILE.read_text().strip() != "999999"
    )


def test_log_rotation_on_oversize(tmp_path):
    """If collector.log already exceeds LOG_ROTATE_SIZE_MB, the next start
    should rotate it into a timestamped archive and create a fresh log."""

    # Seed an oversize log: 2 MB content, then set threshold to 1 MB so the
    # next start triggers rotation.
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    # 1 KB block * 2048 = 2 MB.
    block = b"x" * 1024
    with LOG_FILE.open("wb") as fh:
        for _ in range(2048):
            fh.write(block)
    pre_size = LOG_FILE.stat().st_size
    assert pre_size > 1_000_000

    result = _run("start", env_extra={"LOG_ROTATE_SIZE_MB": "1"})
    assert result.returncode == 0
    assert _wait_until(lambda: PID_FILE.exists())

    # A rotated copy with .YYYYMMDD_HHMMSS suffix should exist.
    rotated = list(LOG_FILE.parent.glob("collector.log.*"))
    assert rotated, "log was not rotated despite exceeding LOG_ROTATE_SIZE_MB"
