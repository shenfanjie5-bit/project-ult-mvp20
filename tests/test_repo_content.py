from pathlib import Path

from scripts import audit_repo_content


def test_repo_content_reads_text_bodies_and_risk_markers(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    (root / "a.py").write_text("def f():\n    pass  # TODO stub\n", encoding="utf-8")
    (root / "README.md").write_text("# Title\nbody\n", encoding="utf-8")
    ignored = root / ".venv"
    ignored.mkdir()
    (ignored / "ignored.py").write_text("TODO\n", encoding="utf-8")

    audit = audit_repo_content.scan(
        root,
        max_text_bytes=1000,
        sample_limit=10,
        top_limit=10,
    )
    data = audit_repo_content.to_json(audit, top_limit=10)

    assert data["files_seen"] == 2
    assert data["text_files_read"] == 2
    assert data["text_lines_read"] == 4
    assert data["risk_hits"]["TODO"] == 1
    assert data["risk_hits"]["stub"] == 1
    risky_paths = {row["path"] for row in data["risky_files"]}
    assert risky_paths == {"a.py"}
    assert all(row["sha256"] for row in data["file_samples"])


def test_repo_content_skips_binary_and_large_files(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    (root / "data.sqlite").write_bytes(b"sqlite bytes")
    (root / "large.txt").write_text("x" * 20, encoding="utf-8")
    (root / "nul.bin").write_bytes(b"abc\x00def")

    audit = audit_repo_content.scan(
        root,
        max_text_bytes=10,
        sample_limit=1,
        top_limit=10,
    )
    data = audit_repo_content.to_json(audit, top_limit=10)

    assert data["files_seen"] == 3
    assert data["text_files_read"] == 0
    assert data["skipped_binary"] == 2
    assert data["skipped_too_large"] == 1
    assert data["skip_reasons"]["binary_extension:.sqlite"] == 1
    assert data["skip_reasons"]["binary_sniff"] == 1
    assert data["skip_reasons"]["too_large_for_full_text_read"] == 1
    assert len(data["skipped_file_samples"]) == 1
    assert data["skipped_file_fingerprints_count"] == 3
    assert {row["reason"] for row in data["skipped_file_fingerprints"]} == {
        "binary_extension:.sqlite",
        "binary_sniff",
        "too_large_for_full_text_read",
    }
    assert all(row["head_tail_sha256"] for row in data["skipped_file_fingerprints"])
    assert data["largest_skipped_files"][0]["path"] == "large.txt"
