"""Tests for ``scripts/apply_yaml_patch.py`` patch hardening."""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import apply_yaml_patch as ayp  # noqa: E402


def test_strict_schema_rejects_numeric_evidence_quality(tmp_path: Path) -> None:
    overlay = tmp_path / "overlay.yaml"
    patch = tmp_path / "patch.yaml"
    overlay.write_text(
        yaml.safe_dump(
            {
                "nodes": [
                    {
                        "dp_id": "L1.role.tag",
                        "data_status": "Unknown",
                        "required_level": "conditional_required",
                        "missing_reason": "pending",
                        "value": None,
                    }
                ]
            },
            allow_unicode=True,
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    patch.write_text(
        yaml.safe_dump(
            {
                "nodes": [
                    {
                        "dp_id": "L1.role.tag",
                        "data_status": "Known",
                        "evidence_quality": 0.74,
                        "value": {"tags": ["行业终端制造商"]},
                    }
                ]
            },
            allow_unicode=True,
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    updated, unmatched, errors = ayp.apply_patch(
        overlay, patch, strict_schema=True
    )

    assert updated == 0
    assert unmatched == 0
    assert "L1.role.tag" in errors
    assert any("evidence_quality" in e for e in errors["L1.role.tag"])


def test_dump_overlay_yaml_keeps_formula_on_one_line() -> None:
    dumped = ayp._dump_overlay_yaml(
        {"scores": {"path_scores": {"formula": ayp.FORMULA_TEXT}}}
    )

    assert f"formula: {ayp.FORMULA_TEXT}" in dumped
    assert "\n      Confidence × Time Factor" not in dumped


def test_strict_schema_rejects_natural_language_residue(tmp_path: Path) -> None:
    overlay = tmp_path / "overlay.yaml"
    patch = tmp_path / "patch.yaml"
    overlay.write_text(
        yaml.safe_dump(
            {
                "nodes": [
                    {
                        "dp_id": "L1.position.growth_rank",
                        "data_status": "Unknown",
                        "required_level": "conditional_required",
                        "missing_reason": "pending",
                        "value": None,
                    }
                ]
            },
            allow_unicode=True,
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    patch.write_text(
        yaml.safe_dump(
            {
                "nodes": [
                    {
                        "dp_id": "L1.position.growth_rank",
                        "data_status": "Known",
                        "value": {
                            "rank": None,
                            "share_pct": None,
                            "trend": "decline",
                            "source_year": "2026Q1",
                            "market_size_unit": None,
                            "notes": "rank 和 share_pct 因缺少本地证据留空。",
                        },
                    }
                ]
            },
            allow_unicode=True,
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    updated, unmatched, errors = ayp.apply_patch(
        overlay, patch, strict_schema=True
    )

    assert updated == 0
    assert unmatched == 0
    assert "L1.position.growth_rank" in errors
    assert any("schema/enum residue" in e for e in errors["L1.position.growth_rank"])
