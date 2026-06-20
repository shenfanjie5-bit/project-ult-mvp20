from __future__ import annotations

from datetime import datetime
from pathlib import Path

from mvp20.llm_context import (
    ASIA_SHANGHAI,
    build_single_stock_context,
    normalize_evidence_item,
)


def test_evidence_normalizer_blocks_non_decision_statuses() -> None:
    base = {
        "evidence_ref": "ev_test",
        "kind": "unit",
        "source_system": "unit",
        "source_ref": "unit://row",
        "ts_code": "000977.SZ",
        "value_json": {"scalar": 1},
        "age_seconds": 60,
        "origin_ts_code": "000977.SZ",
    }

    known = normalize_evidence_item(**base, data_status="Known")
    assert known.llm_usable is True
    assert known.use_scope == "supporting_signal"
    assert known.model_dump(mode="json", by_alias=True)["_origin_ts_code"] == "000977.SZ"

    mock = normalize_evidence_item(**{**base, "evidence_ref": "ev_mock"}, data_status="Mock")
    assert mock.llm_usable is False
    assert mock.use_scope == "blocked"
    assert mock.verification_status == "rejected"

    unknown = normalize_evidence_item(
        **{**base, "evidence_ref": "ev_unknown"},
        data_status="Unknown",
    )
    assert unknown.llm_usable is False
    assert unknown.use_scope == "blocked"

    proxy = normalize_evidence_item(
        **{**base, "evidence_ref": "ev_proxy"},
        data_status="Proxy",
    )
    assert proxy.llm_usable is False
    assert proxy.use_scope == "diagnostic_only"

    inactive = normalize_evidence_item(
        **{**base, "evidence_ref": "ev_inactive"},
        data_status="Inactive",
    )
    assert inactive.llm_usable is False
    assert inactive.use_scope == "context_only"

    stale = normalize_evidence_item(
        **{**base, "evidence_ref": "ev_stale", "age_seconds": 30 * 3600},
        data_status="Known",
    )
    assert stale.llm_usable is False
    assert stale.freshness_status == "stale"
    assert stale.use_scope == "diagnostic_only"


def test_single_stock_context_freezes_probability_semantics() -> None:
    now = datetime(2026, 6, 21, 2, 45, tzinfo=ASIA_SHANGHAI)
    ctx = build_single_stock_context(
        repo_root=Path("."),
        ts_code="000977.SZ",
        horizon="5d",
        max_evidence=40,
        now=now,
    )
    payload = ctx.model_dump(mode="json", by_alias=True)

    assert payload["schema_version"] == "single_stock_decision_context.v1"
    assert payload["market"] == "A_share"
    assert payload["evidence_counts"]["total"] <= 40
    assert payload["input_hash"].startswith("sha256:")
    assert payload["context_id"].startswith("ctx_")
    assert any("_origin_ts_code" in item for item in payload["evidence_pack"])

    probabilities = {p["evidence_ref"]: p for p in payload["model_probabilities"]}
    assert "ev_signal_5d_000977_SZ" in probabilities
    assert "ev_signal_up_5d_000977_SZ" in probabilities
    signal_5d = probabilities["ev_signal_5d_000977_SZ"]
    assert signal_5d["target_kind"] == "relative_cross_section_median"
    assert "not absolute P(up)" in signal_5d["probability_semantics"]
    assert signal_5d["use_scope"] == "diagnostic_only"

    signal_up = probabilities["ev_signal_up_5d_000977_SZ"]
    assert signal_up["target_kind"] == "absolute_up_5d"
    assert signal_up["use_scope"] == "diagnostic_only"

    serialized = str(payload["model_probabilities"])
    assert "final_score" not in serialized
    assert "trading_signal_v2" not in serialized

    ctx_again = build_single_stock_context(
        repo_root=Path("."),
        ts_code="000977.SZ",
        horizon="5d",
        max_evidence=40,
        now=now,
    )
    assert ctx_again.input_hash == ctx.input_hash
    assert ctx_again.context_id == ctx.context_id


def test_non_a_share_context_is_explicitly_unsupported() -> None:
    payload = build_single_stock_context(
        repo_root=Path("."),
        ts_code="NVDA.US",
        market="US",
        horizon="5d",
    )
    assert isinstance(payload, dict)
    assert payload["status"] == "unsupported"
    assert payload["market"] == "US"
    assert payload["context"] is None
