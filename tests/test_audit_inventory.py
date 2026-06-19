from pathlib import Path

from scripts import audit_inventory


def test_scan_counts_files_extensions_and_prunes(tmp_path: Path) -> None:
    (tmp_path / "keep").mkdir()
    (tmp_path / "keep" / "a.py").write_text("print('x')\n", encoding="utf-8")
    (tmp_path / "keep" / "b").write_text("plain\n", encoding="utf-8")
    (tmp_path / ".venv").mkdir()
    (tmp_path / ".venv" / "hidden.py").write_text("skip\n", encoding="utf-8")

    inv = audit_inventory.scan(tmp_path, prunes=(".venv",), largest_limit=5)
    data = audit_inventory.to_json(inv, top_limit=10)

    assert data["exists"] is True
    assert data["files"] == 2
    assert data["extensions"][".py"] == 1
    assert data["extensions"]["[no_ext]"] == 1
    assert ".venv" not in data["top_level"]
    assert data["top_level"]["keep"]["files"] == 2


def test_scan_prunes_nested_relative_prefix(tmp_path: Path) -> None:
    (tmp_path / "_workspace" / ".venv").mkdir(parents=True)
    (tmp_path / "_workspace" / "_meta").mkdir(parents=True)
    (tmp_path / "_workspace" / ".venv" / "ignored.py").write_text(
        "skip\n", encoding="utf-8"
    )
    (tmp_path / "_workspace" / "_meta" / "kept.json").write_text(
        "{}\n", encoding="utf-8"
    )

    inv = audit_inventory.scan(tmp_path, prunes=("_workspace/.venv",), largest_limit=5)
    data = audit_inventory.to_json(inv, top_limit=10)

    assert data["files"] == 1
    assert data["extensions"][".json"] == 1
    assert data["top_level"]["_workspace"]["files"] == 1
