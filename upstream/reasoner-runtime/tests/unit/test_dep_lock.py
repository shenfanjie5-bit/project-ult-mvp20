from __future__ import annotations

from pathlib import Path

import pytest

from scripts.verify_deps import (
    main,
    parse_requirements,
    verify_all_requirements_locked,
    verify_dependency_hashes,
)


VALID_HASH = "a" * 64


def test_parse_requirements_reads_pinned_hashes(tmp_path: Path) -> None:
    requirements = tmp_path / "requirements.txt"
    requirements.write_text(
        f"""
litellm==1.83.0 \\
    --hash=sha256:{VALID_HASH}

instructor==1.15.1 \\
    --hash=sha256:{'b' * 64}
""",
        encoding="utf-8",
    )

    parsed = parse_requirements(requirements)

    assert parsed["litellm"].package == "litellm"
    assert parsed["litellm"].version == "1.83.0"
    assert parsed["litellm"].hashes == (VALID_HASH,)
    assert verify_dependency_hashes(requirements, ["litellm", "instructor"]) == []


@pytest.mark.parametrize(
    ("content", "expected_error"),
    [
        (
            f"instructor==1.15.1 --hash=sha256:{VALID_HASH}\n",
            "litellm is missing",
        ),
        (
            f"litellm==1.83.0 --hash=sha256:{VALID_HASH}\n",
            "instructor is missing",
        ),
        (
            f"litellm>=1.83.0 --hash=sha256:{VALID_HASH}\n"
            f"instructor==1.15.1 --hash=sha256:{VALID_HASH}\n",
            "litellm must be pinned",
        ),
        (
            f"litellm==1.83.0\n"
            f"instructor==1.15.1 --hash=sha256:{VALID_HASH}\n",
            "litellm must include",
        ),
        (
            f"litellm==1.83.0 --hash=sha256:not-a-valid-hash\n"
            f"instructor==1.15.1 --hash=sha256:{VALID_HASH}\n",
            "invalid sha256 hash",
        ),
    ],
)
def test_verify_dependency_hashes_reports_invalid_locks(
    tmp_path: Path,
    content: str,
    expected_error: str,
) -> None:
    requirements = tmp_path / "requirements.txt"
    requirements.write_text(content, encoding="utf-8")

    errors = verify_dependency_hashes(requirements, ["litellm", "instructor"])

    assert any(expected_error in error for error in errors)


def test_verify_all_requirements_locked_checks_every_requirement_line(
    tmp_path: Path,
) -> None:
    requirements = tmp_path / "requirements.txt"
    requirements.write_text(
        f"""
--index-url https://example.invalid/simple
litellm==1.83.0 --hash=sha256:{VALID_HASH}
instructor==1.15.1 --hash=sha256:{VALID_HASH}
unhashable==1.0.0
unpinned>=1.0.0 --hash=sha256:{VALID_HASH}
bad-hash==1.0.0 --hash=sha256:not-valid
""",
        encoding="utf-8",
    )

    errors = verify_all_requirements_locked(requirements)

    assert "unhashable must include a sha256 hash" in errors
    assert "unpinned must be pinned with ==" in errors
    assert any("bad-hash has an invalid sha256 hash" in error for error in errors)
    assert not any("--index-url" in error for error in errors)


def test_main_returns_zero_for_valid_requirements(tmp_path: Path) -> None:
    requirements = tmp_path / "requirements.txt"
    requirements.write_text(
        f"litellm==1.83.0 --hash=sha256:{VALID_HASH}\n"
        f"instructor==1.15.1 --hash=sha256:{VALID_HASH}\n",
        encoding="utf-8",
    )

    assert main([str(requirements), "litellm", "instructor"]) == 0


def test_main_all_mode_validates_all_requirement_lines(tmp_path: Path) -> None:
    requirements = tmp_path / "requirements.txt"
    requirements.write_text(
        f"litellm==1.83.0 --hash=sha256:{VALID_HASH}\n"
        f"instructor==1.15.1 --hash=sha256:{VALID_HASH}\n"
        "transitive==1.0.0\n",
        encoding="utf-8",
    )

    assert main([str(requirements), "--all", "litellm", "instructor"]) == 1


def test_main_returns_nonzero_for_invalid_requirements(tmp_path: Path) -> None:
    requirements = tmp_path / "requirements.txt"
    requirements.write_text(
        f"litellm==1.83.0 --hash=sha256:{VALID_HASH}\n",
        encoding="utf-8",
    )

    assert main([str(requirements), "litellm", "instructor"]) == 1
