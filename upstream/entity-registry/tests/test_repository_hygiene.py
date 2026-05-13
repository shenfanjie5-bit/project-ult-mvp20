import subprocess

import pytest


def _is_generated_python_artifact(path: str) -> bool:
    return "__pycache__/" in path or path.endswith(".pyc") or ".egg-info/" in path


def test_generated_python_artifacts_are_not_tracked() -> None:
    result = subprocess.run(
        ["git", "ls-files"],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        pytest.skip("git metadata is unavailable")

    tracked_files = result.stdout.splitlines()
    deleted_result = subprocess.run(
        ["git", "ls-files", "--deleted"],
        check=False,
        capture_output=True,
        text=True,
    )
    deleted_files = (
        set(deleted_result.stdout.splitlines())
        if deleted_result.returncode == 0
        else set()
    )
    offenders = [
        path
        for path in tracked_files
        if path not in deleted_files
        if _is_generated_python_artifact(path)
    ]

    assert offenders == []
