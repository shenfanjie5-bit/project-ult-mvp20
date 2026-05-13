from __future__ import annotations

from pathlib import Path

from scripts.check_direct_imports import main, scan_for_direct_provider_imports


def test_direct_import_scanner_flags_forbidden_provider_sdks(tmp_path: Path) -> None:
    sample = tmp_path / "bad_imports.py"
    sample.write_text(
        "import openai\n"
        "from anthropic import Anthropic\n"
        "import json\n",
        encoding="utf-8",
    )

    violations = scan_for_direct_provider_imports(tmp_path)

    assert [(violation.line, violation.module) for violation in violations] == [
        (1, "openai"),
        (2, "anthropic"),
    ]
    assert main([str(tmp_path)]) == 1


def test_direct_import_scanner_passes_runtime_and_scripts_tree() -> None:
    repo_root = Path(__file__).resolve().parents[2]

    violations = []
    for relative_path in ("reasoner_runtime", "scripts"):
        violations.extend(scan_for_direct_provider_imports(repo_root / relative_path))

    assert violations == []
    assert main(
        [
            str(repo_root / "reasoner_runtime"),
            str(repo_root / "scripts"),
        ]
    ) == 0
