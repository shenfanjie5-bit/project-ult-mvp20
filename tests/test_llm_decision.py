from __future__ import annotations

from datetime import datetime
from pathlib import Path

from mvp20.llm_context import ASIA_SHANGHAI, build_single_stock_context
from mvp20.llm_decision import build_dry_run_decision, validate_decision_output


def _context_payload() -> dict:
    ctx = build_single_stock_context(
        repo_root=Path("."),
        ts_code="000977.SZ",
        horizon="5d",
        max_evidence=40,
        now=datetime(2026, 6, 21, 2, 50, tzinfo=ASIA_SHANGHAI),
    )
    return ctx.model_dump(mode="json", by_alias=True)


def test_dry_run_decision_is_inconclusive_and_valid() -> None:
    context = _context_payload()
    decision = build_dry_run_decision(context)

    assert decision["status"] == "inconclusive"
    assert decision["action_type"] == "inconclusive"
    assert decision["confidence"] is None
    assert decision["audit_record"]["llm_lineage"]["called"] is False
    assert decision["validation_result"]["passed"] is True
    assert "primary_probability_unavailable" in decision["degradation_flags"]
    assert validate_decision_output(context, decision)["passed"] is True


def test_validator_rejects_unknown_evidence_ref() -> None:
    context = _context_payload()
    decision = build_dry_run_decision(context)
    decision["positive_driver_claims"] = [
        {
            "claim_id": "pos_missing",
            "claim_use": "supporting",
            "text": "This claim cites an evidence ref outside the context.",
            "evidence_refs": ["ev_missing"],
            "confidence": 0.5,
        }
    ]
    validation = validate_decision_output(context, decision)

    assert validation["passed"] is False
    assert any("unknown evidence_ref ev_missing" in err for err in validation["errors"])


def test_validator_rejects_unusable_supporting_evidence() -> None:
    context = _context_payload()
    decision = build_dry_run_decision(context)
    unusable = next(
        item
        for item in context["evidence_pack"]
        if item["llm_usable"] is False
    )
    decision["positive_driver_claims"] = [
        {
            "claim_id": "pos_unusable",
            "claim_use": "supporting",
            "text": "This claim incorrectly uses stale or rejected evidence.",
            "evidence_refs": [unusable["evidence_ref"]],
            "confidence": 0.5,
        }
    ]
    validation = validate_decision_output(context, decision)

    assert validation["passed"] is False
    assert any("not LLM-usable" in err for err in validation["errors"])


def test_validator_rejects_relative_signal_as_absolute_up_probability() -> None:
    context = _context_payload()
    decision = build_dry_run_decision(context)
    for estimate in decision["probability_estimates"]:
        if estimate["evidence_ref"] == "ev_signal_5d_000977_SZ":
            estimate["target_kind"] = "absolute_up_5d"
            estimate["probability_semantics"] = "P(5d return > 0)"
            estimate["use_scope"] = "primary"
            break
    validation = validate_decision_output(context, decision)

    assert validation["passed"] is False
    assert any("relative artifact cannot be used as absolute_up_5d" in err for err in validation["errors"])
    assert any("not primary in context" in err for err in validation["errors"])
