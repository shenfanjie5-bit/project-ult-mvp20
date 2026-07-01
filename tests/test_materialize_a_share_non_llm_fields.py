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
    assert schema_validator.validate_overlay_node(merged, strict=True) == []
