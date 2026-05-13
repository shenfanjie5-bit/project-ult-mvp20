import json
import subprocess
import sys
from pathlib import Path

from scripts.m4_8_focused_resolution_proof import run_proof


PROOF_SCRIPT = Path("scripts/m4_8_focused_resolution_proof.py")


def test_runner_summary_shape_is_stable() -> None:
    summary = run_proof()

    assert summary["proof"] == "m4.8-focused-resolution-proof"
    assert summary["case_count"] == 5
    assert summary["audit_payload_verified"] is True
    assert summary["contract_projection_verified"] is True
    assert summary["core_library_changes_required"] is False
    assert [case["name"] for case in summary["cases"]] == [
        "deterministic_exact",
        "deterministic_code",
        "deterministic_rule",
        "ambiguous_fuzzy_candidate",
        "unresolved_fail_closed",
    ]


def test_deterministic_exact_code_and_rule_hits_are_resolved() -> None:
    summary = run_proof()
    cases = {case["name"]: case for case in summary["cases"]}

    assert cases["deterministic_exact"] == {
        "name": "deterministic_exact",
        "mention": "贵州茅台",
        "resolved_entity_id": "ENT_STOCK_600519.SH",
        "resolution_method": "deterministic",
        "resolution_confidence": 1.0,
        "decision_type": "auto",
        "candidate_entity_ids": ["ENT_STOCK_600519.SH"],
        "audit_payload_verified": True,
        "contract_projection_verified": True,
        "auto_selected": True,
    }
    assert cases["deterministic_code"]["resolved_entity_id"] == "ENT_STOCK_000001.SZ"
    assert cases["deterministic_code"]["resolution_method"] == "deterministic"
    assert cases["deterministic_code"]["candidate_entity_ids"] == [
        "ENT_STOCK_000001.SZ"
    ]
    assert cases["deterministic_rule"]["resolved_entity_id"] == "ENT_STOCK_600519.SH"
    assert cases["deterministic_rule"]["resolution_method"] == "deterministic"


def test_ambiguous_fuzzy_candidates_are_not_auto_selected() -> None:
    summary = run_proof()
    ambiguous = _case(summary, "ambiguous_fuzzy_candidate")

    assert ambiguous["resolved_entity_id"] is None
    assert ambiguous["resolution_method"] == "unresolved"
    assert ambiguous["resolution_confidence"] is None
    assert ambiguous["decision_type"] == "manual_review"
    assert ambiguous["candidate_entity_ids"] == [
        "ENT_STOCK_300750.SZ",
        "ENT_STOCK_03750.HK",
    ]
    assert ambiguous["auto_selected"] is False


def test_unresolved_fail_closed_has_no_synthetic_candidate() -> None:
    summary = run_proof()
    unresolved = _case(summary, "unresolved_fail_closed")

    assert unresolved["resolved_entity_id"] is None
    assert unresolved["resolution_method"] == "unresolved"
    assert unresolved["decision_type"] == "auto"
    assert unresolved["candidate_entity_ids"] == []
    assert unresolved["auto_selected"] is False


def test_audit_payload_and_contract_projection_are_verified_per_case() -> None:
    summary = run_proof()

    for case in summary["cases"]:
        assert case["audit_payload_verified"] is True
        assert case["contract_projection_verified"] is True


def test_summary_uses_injected_fake_fuzzy_backend_without_production_claim() -> None:
    summary = run_proof()
    serialized = json.dumps(summary, ensure_ascii=False).lower()

    assert summary["fuzzy_backend"] == "injected_fake"
    assert "splink" not in serialized
    assert "production" not in summary["fuzzy_backend"].lower()


def test_script_writes_stdout_and_summary_json(tmp_path: Path) -> None:
    output_path = tmp_path / "summary.json"

    stdout_run = subprocess.run(
        [sys.executable, str(PROOF_SCRIPT)],
        check=True,
        text=True,
        capture_output=True,
    )
    file_run = subprocess.run(
        [sys.executable, str(PROOF_SCRIPT), "--summary-json", str(output_path)],
        check=True,
        text=True,
        capture_output=True,
    )

    stdout_summary = json.loads(stdout_run.stdout)
    file_summary = json.loads(output_path.read_text(encoding="utf-8"))
    assert stdout_summary == run_proof()
    assert file_summary == run_proof()
    assert file_run.stdout == ""


def _case(summary: dict, name: str) -> dict:
    return next(case for case in summary["cases"] if case["name"] == name)
