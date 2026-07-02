from pathlib import Path

from mvp20 import schema_validator
from scripts import materialize_a_share_non_llm_fields as mat


def test_status_patch_preserves_unknown_missing_reason() -> None:
    node = {
        "dp_id": "L4.eff.capacity_utilization",
        "data_status": "Proxy",
        "status": "Proxy",
        "required_level": "conditional_required",
        "value": {"utilization_pct": None, "trend": "proxy"},
    }
    candidate = {
        "data_status": "Unknown",
        "value": None,
        "confidence": 0.0,
        "evidence_sources": [],
        "reason": "missing capex or PPE",
    }

    patch = mat._status_patch(
        node=node,
        dp_id="L4.eff.capacity_utilization",
        ts_code="000066.SZ",
        candidate=candidate,
        governance_entry={},
        db_path=Path("/tmp/nonexistent.sqlite"),
        now_iso="2026-06-24T00:00:00+08:00",
    )
    merged = {**node, **patch}

    assert patch["data_status"] == "Unknown"
    assert patch["status"] == "Unknown"
    assert patch["value"] is None
    assert patch["missing_reason"] == "missing capex or PPE"
    # Review #6: an Unknown patch has value=None — no derivation to
    # attribute — so it must NOT be stamped llm_derived (or any *_derived).
    assert patch["data_source"] is None
    assert schema_validator.validate_overlay_node(merged, strict=True) == []


def test_source_from_candidate_maps_non_llm_methods() -> None:
    # Review #1/#7: provenance follows the deterministic extractor that
    # produced the value, mapped via method/category tokens.
    cases = [
        ({"data_status": "Known", "method": "main_business_product_parser", "category": "parser_formula_first"}, "non_llm_parser"),
        ({"data_status": "Known", "method": "channel_mix_regex", "category": "cheap_extract_parser"}, "non_llm_parser"),
        ({"data_status": "Known", "method": "financial_price_signal_text", "category": "cheap_extract_rule"}, "non_llm_parser"),
        ({"data_status": "Proxy", "method": "capex_ppe_proxy", "category": "formula_proxy"}, "non_llm_formula"),
        ({"data_status": "Proxy", "method": "sga_revenue_ratio", "category": "parser_formula_first"}, "non_llm_formula"),
        ({"data_status": "Proxy", "method": "peer_growth_rank", "category": "formula_proxy"}, "non_llm_formula"),
        ({"data_status": "Known", "method": "event_keyword_screen", "category": "event_policy"}, "non_llm_event"),
        ({"data_status": "Known", "method": "segment_revenue_share_runtime", "category": "parser_formula_first"}, "non_llm_runtime"),
        ({"data_status": "Known", "method": "existing_runtime_or_derive", "category": "unclassified"}, "non_llm_runtime"),
        # Unknown/Unavailable: value=None, nothing to attribute.
        ({"data_status": "Unknown", "method": "capex_ppe_proxy", "category": "formula_proxy"}, None),
        ({"data_status": "Unavailable", "method": "no_non_llm_extractor", "category": "strict_no_llm_now"}, None),
        # Unclassifiable available method: never guess a label.
        ({"data_status": "Known", "method": "industry_applicability_matrix", "category": "industry_applicability"}, None),
    ]
    for candidate, expected in cases:
        assert mat._source_from_candidate(candidate) == expected, candidate


def test_status_patch_relabels_available_candidate_over_llm_derived() -> None:
    # Overwrite semantics: the patch replaces value/evidence, so provenance
    # must follow the new candidate even when the node carried a legacy
    # llm_derived stamp from an earlier fill campaign.
    node = {
        "dp_id": "L4.eff.capacity_utilization",
        "data_status": "Unknown",
        "status": "Unknown",
        "required_level": "conditional_required",
        "data_source": "llm_derived",
        "value": None,
    }
    candidate = {
        "data_status": "Proxy",
        "value": {"utilization_pct": None, "trend": "proxy", "score": -0.1},
        "method": "capex_ppe_proxy",
        "category": "formula_proxy",
        "confidence": 0.62,
        "evidence_sources": [],
        "reason": None,
    }
    patch = mat._status_patch(
        node=node,
        dp_id="L4.eff.capacity_utilization",
        ts_code="000066.SZ",
        candidate=candidate,
        governance_entry={},
        db_path=Path("/tmp/nonexistent.sqlite"),
        now_iso="2026-07-01T00:00:00+08:00",
    )
    assert patch["data_source"] == "non_llm_formula"
