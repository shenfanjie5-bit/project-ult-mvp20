from pathlib import Path

import yaml

from mvp20.lock import EXPECTED_MODULES, validate_lock


ROOT = Path(__file__).resolve().parents[1]


def test_module_lock_pins_expected_modules_to_full_shas() -> None:
    result = validate_lock(ROOT / "locks" / "modules.lock.yaml")

    assert result.ok
    assert result.module_count == len(EXPECTED_MODULES)


def test_lock_rejects_main_branch_dependency(tmp_path: Path) -> None:
    payload = yaml.safe_load((ROOT / "locks" / "modules.lock.yaml").read_text())
    payload["modules"]["contracts"]["commit"] = "main"
    path = tmp_path / "bad-lock.yaml"
    path.write_text(yaml.safe_dump(payload), encoding="utf-8")

    result = validate_lock(path)

    assert not result.ok
    assert any("commit must be a full 40-char SHA" in error for error in result.errors)
    assert any("main branch dependency is not allowed" in error for error in result.errors)
