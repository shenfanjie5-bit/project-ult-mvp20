from __future__ import annotations

from mvp20.llm_extraction import prepare_extraction_snapshot, validate_extraction_output


def _context() -> dict:
    return {
        "schema_version": "single_stock_decision_context.v1",
        "context_id": "ctx_unit",
        "input_hash": "sha256:context",
        "cycle_id": "unit",
        "ts_code": "000001.SZ",
        "market": "A_share",
        "horizon": "5d",
        "horizon_days": 5,
        "as_of": "2026-06-23T00:00:00+08:00",
        "evidence_pack": [
            {
                "evidence_ref": "ev_unit_channel",
                "llm_usable": True,
                "freshness_status": "fresh",
                "verification_status": "verified",
                "availability_status": "available",
                "use_scope": "supporting",
            }
        ],
    }


def test_extraction_snapshot_accepts_valid_dp_schema() -> None:
    output = {
        "fields": [
            {
                "dp_id": "L3.channel.mix",
                "data_status": "Known",
                "value": {
                    "direct_pct": 30.0,
                    "distributor_pct": 40.0,
                    "ecommerce_pct": 20.0,
                    "others_pct": 10.0,
                    "trend": "stable",
                },
                "confidence": 0.7,
                "evidence_refs": ["ev_unit_channel"],
            }
        ]
    }

    snapshot = prepare_extraction_snapshot(_context(), output, dry_run=False)

    assert snapshot["extraction_id"].startswith("xtr_")
    assert snapshot["context_ref"]["context_hash"] == "sha256:context"
    assert snapshot["validation_result"]["passed"] is True


def test_extraction_rejects_unknown_evidence_ref() -> None:
    output = {
        "fields": [
            {
                "dp_id": "L3.channel.mix",
                "data_status": "Known",
                "value": {
                    "direct_pct": 30.0,
                    "distributor_pct": 40.0,
                    "ecommerce_pct": 20.0,
                    "others_pct": 10.0,
                },
                "evidence_refs": ["ev_missing"],
            }
        ]
    }

    result = validate_extraction_output(_context(), output)

    assert result["passed"] is False
    assert any("unknown evidence_ref ev_missing" in err for err in result["errors"])


def test_extraction_rejects_invalid_dp_schema() -> None:
    output = {
        "fields": [
            {
                "dp_id": "L3.channel.mix",
                "data_status": "Known",
                "value": {
                    "direct_pct": "thirty",
                    "distributor_pct": 40.0,
                    "ecommerce_pct": 20.0,
                    "others_pct": 10.0,
                },
                "evidence_refs": ["ev_unit_channel"],
            }
        ]
    }

    result = validate_extraction_output(_context(), output)

    assert result["passed"] is False
    assert any("direct_pct" in err for err in result["errors"])


def _valid_channel_value() -> dict:
    return {
        "direct_pct": 30.0,
        "distributor_pct": 40.0,
        "ecommerce_pct": 20.0,
        "others_pct": 10.0,
        "trend": "stable",
    }


def test_extraction_rejects_stale_or_unusable_evidence() -> None:
    context = _context()
    context["evidence_pack"] = [
        {
            "evidence_ref": "ev_stale_signal",
            "llm_usable": False,
            "freshness_status": "stale",
            "verification_status": "review_required",
            "availability_status": "available",
            "use_scope": "diagnostic_only",
        }
    ]
    output = {
        "fields": [
            {
                "dp_id": "L3.channel.mix",
                "data_status": "Known",
                "value": _valid_channel_value(),
                "confidence": 0.7,
                "evidence_refs": ["ev_stale_signal"],
            }
        ]
    }

    result = validate_extraction_output(context, output)

    assert result["passed"] is False
    assert any("not llm_usable" in e for e in result["errors"])
    assert any("freshness_status=stale" in e for e in result["errors"])
    assert any("verification_status=review_required" in e for e in result["errors"])


def test_extraction_rejects_unbound_context() -> None:
    context = _context()
    context.pop("context_id")
    output = {
        "fields": [
            {
                "dp_id": "L3.channel.mix",
                "data_status": "Known",
                "value": _valid_channel_value(),
                "confidence": 0.7,
                "evidence_refs": ["ev_unit_channel"],
            }
        ]
    }

    result = validate_extraction_output(context, output)
    assert result["passed"] is False
    assert any("context missing context_id" in e for e in result["errors"])

    snapshot = prepare_extraction_snapshot(context, None, dry_run=True)
    assert snapshot["context_ref"]["context_hash"] is None
    assert snapshot["validation_result"]["passed"] is False


def test_extraction_empty_fields_not_passed() -> None:
    result = validate_extraction_output(_context(), {"fields": []})

    assert result["passed"] is False
    assert any("no fields" in e for e in result["errors"])


def test_extraction_id_stable_across_dry_run() -> None:
    output = {
        "fields": [
            {
                "dp_id": "L3.channel.mix",
                "data_status": "Known",
                "value": _valid_channel_value(),
                "confidence": 0.7,
                "evidence_refs": ["ev_unit_channel"],
            }
        ]
    }

    dry = prepare_extraction_snapshot(_context(), dict(output), dry_run=True)
    real = prepare_extraction_snapshot(_context(), dict(output), dry_run=False)

    # Same extracted content -> same content-addressed id, even though the
    # llm_lineage.called audit flag differs.
    assert dry["extraction_id"] == real["extraction_id"]
    assert dry["audit_record"]["llm_lineage"]["called"] is False
    assert real["audit_record"]["llm_lineage"]["called"] is True


def test_extraction_id_stable_without_asof() -> None:
    ctx = _context()
    ctx.pop("as_of", None)
    output = {
        "fields": [
            {
                "dp_id": "L3.channel.mix",
                "data_status": "Known",
                "value": _valid_channel_value(),
                "confidence": 0.7,
                "evidence_refs": ["ev_unit_channel"],
            }
        ]
    }

    first = prepare_extraction_snapshot(ctx, dict(output), dry_run=True)
    second = prepare_extraction_snapshot(ctx, dict(output), dry_run=True)

    # The now()-fallback as_of must not leak into the id.
    assert first["extraction_id"] == second["extraction_id"]
