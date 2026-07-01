from pathlib import Path

from scripts import run_3_stock_non_llm_vs_gpt55_ab as ab


def test_load_target_fields_from_full_summary() -> None:
    fields = ab._load_target_fields(
        Path("docs/audit/2026-06-23_a_share_all_stock_llm_vs_non_llm_extractors_summary.json")
    )

    assert len(fields) == 55
    assert "L1.role.tag" in fields
    assert "L3.channel.mix" in fields


def test_ab_compare_detects_scalar_close() -> None:
    comparison = ab._ab_compare(
        {"data_status": "Proxy", "value": {"score": 0.5}},
        {
            "data_status": "Proxy",
            "value": {"score": 0.56},
            "schema": {"valid": True, "errors": []},
            "evidence_issues": [],
        },
    )

    assert comparison["bucket"] == "scalar_close"
    assert comparison["scalar_close"] is True


def test_ab_compare_prioritizes_schema_invalid() -> None:
    comparison = ab._ab_compare(
        {"data_status": "Known", "value": {"score": 0.5}},
        {
            "data_status": "Known",
            "value": {"score": 0.5},
            "schema": {"valid": False, "errors": ["bad"]},
            "evidence_issues": [],
        },
    )

    assert comparison["bucket"] == "schema_invalid"


def test_evidence_issues_rejects_closed_loop_urls() -> None:
    issues = ab._evidence_issues(
        {
            "data_status": "Known",
            "evidence_sources": [
                {"kind": "external_url", "url": "https://example.com", "excerpt": "x"}
            ],
        }
    )

    assert "evidence_0_bad_kind:external_url" in issues
    assert "evidence_0_url_not_allowed" in issues
