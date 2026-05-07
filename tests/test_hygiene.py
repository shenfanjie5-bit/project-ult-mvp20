from pathlib import Path
import shutil
import subprocess


ROOT = Path(__file__).resolve().parents[1]


def test_gitignore_blocks_runtime_payload_and_manifest_artifacts() -> None:
    git = shutil.which("git") or "/usr/bin/git"
    samples = (
        "runtime/run.json",
        "artifacts/evidence.json",
        "raw_payload.json",
        "provider_payload.json",
        "payloads/raw.json",
        "local.dsn",
        "evidence.parquet",
        "run.stdout",
        "run.stderr",
        "run.exitcode",
        "run.manifest",
        "run.manifest.json",
        "run_manifest.json",
        ".env.local",
    )

    for sample in samples:
        result = subprocess.run(
            [git, "check-ignore", "--quiet", sample],
            cwd=ROOT,
            check=False,
        )
        assert result.returncode == 0, f"{sample} must be ignored"
