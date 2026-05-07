from pathlib import Path

import yaml

from mvp20.manifest import validate_manifest


ROOT = Path(__file__).resolve().parents[1]


def test_slot_manifest_is_valid_but_live_blocked() -> None:
    result = validate_manifest(ROOT / "config" / "mvp20.universe.yaml")

    assert result.ok
    assert result.decision_target_count == 20
    assert result.live_evidence_blocked is True
    assert result.warnings


def test_manifest_requires_exactly_20_targets(tmp_path: Path) -> None:
    manifest = yaml.safe_load((ROOT / "config" / "mvp20.universe.yaml").read_text())
    manifest["decision_targets"] = manifest["decision_targets"][:19]
    path = tmp_path / "bad.yaml"
    path.write_text(yaml.safe_dump(manifest), encoding="utf-8")

    result = validate_manifest(path)

    assert not result.ok
    assert "decision_targets must contain exactly 20 stocks" in result.errors


def test_manifest_rejects_duplicate_targets(tmp_path: Path) -> None:
    manifest = yaml.safe_load((ROOT / "config" / "mvp20.universe.yaml").read_text())
    manifest["decision_targets"][1]["ts_code"] = manifest["decision_targets"][0]["ts_code"]
    path = tmp_path / "bad.yaml"
    path.write_text(yaml.safe_dump(manifest), encoding="utf-8")

    result = validate_manifest(path)

    assert not result.ok
    assert any(error.startswith("duplicate decision target") for error in result.errors)
