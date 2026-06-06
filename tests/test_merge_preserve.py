"""Tests for merge_preserve_existing_overlay — Z1a root-cause fix.

These tests guard the property that ``generate-overlays`` must NEVER wipe out
codex-filled Known / N/A / non-empty-Optionality / non-event-Inactive nodes
when regenerating overlays. The previous bug regenerated 353 stock yamls
from SLOT_DEFS verbatim and erased 4854 Known cell values.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from mvp20.overlays import (
    EVENT_DRIVEN_DP_IDS,
    Membership,
    _should_preserve_node,
    apply_status_induced_invariants,
    build_stock_overlay,
    generate_overlay_files,
    merge_preserve_existing_overlay,
    normalize_overlay_file_status,
    sanitize_node_scalar_fields,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_existing_overlay(node: dict[str, Any]) -> dict[str, Any]:
    """Build a minimal existing-overlay dict containing one node."""
    return {
        "schema_version": 1,
        "ts_code": "TEST.SZ",
        "nodes": [node],
    }


def _make_generated_overlay(node: dict[str, Any]) -> dict[str, Any]:
    """Build a minimal freshly-generated overlay dict containing one node."""
    return {
        "schema_version": 1,
        "ts_code": "TEST.SZ",
        "nodes": [node],
    }


def _existing_node(
    *,
    node_id: str = "TEST.SZ:L1.position.brand",
    dp_id: str = "L1.position.brand",
    data_status: str = "Known",
    value: Any = None,
    confidence: float | None = 0.8,
    evidence_sources: list[Any] | None = None,
    last_updated: str | None = "2026-01-15T00:00:00Z",
    missing_reason: str | None = None,
) -> dict[str, Any]:
    return {
        "node_id": node_id,
        "dp_id": dp_id,
        "data_status": data_status,
        "status": data_status,
        "value": value if value is not None else {"score": 0.7, "note": "leader"},
        "confidence": confidence,
        "evidence_sources": evidence_sources
        if evidence_sources is not None
        else [{"kind": "local_dp_id", "ref": "fin.revenue_share_2026q1"}],
        "last_updated": last_updated,
        "data_source": "codex_local_fill",
        "missing_reason": missing_reason,
        # Structural fields that SLOT_DEFS would also produce
        "node_name": "品牌力与认知度",
        "materiality": 0.65,
    }


def _generated_node(
    *,
    node_id: str = "TEST.SZ:L1.position.brand",
    dp_id: str = "L1.position.brand",
    data_status: str = "Unknown",
    value: Any = None,
) -> dict[str, Any]:
    """A 'fresh' node as generate_overlay_files would emit — Unknown, no value."""
    return {
        "node_id": node_id,
        "dp_id": dp_id,
        "data_status": data_status,
        "status": data_status,
        "value": value,
        "confidence": None,
        "evidence_sources": [],
        "last_updated": None,
        "data_source": None,
        "missing_reason": "pending LLM/company-specific research",
        "node_name": "品牌力与认知度",
        "materiality": 0.65,
        # Structural field added later by SLOT_DEFS expansion
        "calculation_type": "multiplicative_factor",
    }


# ---------------------------------------------------------------------------
# Branch 1: Known fully preserved
# ---------------------------------------------------------------------------


def test_known_node_value_evidence_confidence_preserved() -> None:
    existing_node = _existing_node(data_status="Known")
    generated_node = _generated_node(data_status="Unknown")
    existing = _make_existing_overlay(existing_node)
    generated = _make_generated_overlay(generated_node)

    merged = merge_preserve_existing_overlay(generated, existing)

    out_node = merged["nodes"][0]
    assert out_node["data_status"] == "Known"
    assert out_node["status"] == "Known"
    assert out_node["value"] == {"score": 0.7, "note": "leader"}
    assert out_node["confidence"] == 0.8
    assert out_node["evidence_sources"] == [
        {"kind": "local_dp_id", "ref": "fin.revenue_share_2026q1"}
    ]
    assert out_node["last_updated"] == "2026-01-15T00:00:00Z"
    assert out_node["data_source"] == "codex_local_fill"
    # Generated structural field still flows through
    assert out_node["calculation_type"] == "multiplicative_factor"


# ---------------------------------------------------------------------------
# Branch 2: N/A preserved
# ---------------------------------------------------------------------------


def test_na_node_preserved() -> None:
    existing_node = _existing_node(
        data_status="N/A",
        value=None,
        confidence=None,
        missing_reason="company does not operate this segment",
    )
    generated_node = _generated_node(data_status="Unknown")
    merged = merge_preserve_existing_overlay(
        _make_generated_overlay(generated_node),
        _make_existing_overlay(existing_node),
    )
    out = merged["nodes"][0]
    assert out["data_status"] == "N/A"
    assert out["missing_reason"] == "company does not operate this segment"


# ---------------------------------------------------------------------------
# Branch 3: Optionality with non-empty value preserved
# ---------------------------------------------------------------------------


def test_optionality_with_non_empty_value_preserved() -> None:
    existing_node = _existing_node(
        node_id="TEST.SZ:L2.newbiz.tam",
        dp_id="L2.newbiz.tam",
        data_status="Optionality",
        value={"current_contribution": 0.3, "future_option_value": None},
        confidence=0.6,
    )
    generated_node = _generated_node(
        node_id="TEST.SZ:L2.newbiz.tam",
        dp_id="L2.newbiz.tam",
        data_status="Optionality",
        value={"current_contribution": None, "future_option_value": None},
    )
    merged = merge_preserve_existing_overlay(
        _make_generated_overlay(generated_node),
        _make_existing_overlay(existing_node),
    )
    out = merged["nodes"][0]
    assert out["value"]["current_contribution"] == 0.3
    assert out["confidence"] == 0.6


def test_optionality_with_only_future_value_preserved() -> None:
    existing_node = _existing_node(
        node_id="TEST.SZ:L2.newbiz.tam",
        dp_id="L2.newbiz.tam",
        data_status="Optionality",
        value={"current_contribution": None, "future_option_value": 0.4},
    )
    generated_node = _generated_node(
        node_id="TEST.SZ:L2.newbiz.tam",
        dp_id="L2.newbiz.tam",
        data_status="Optionality",
        value={"current_contribution": None, "future_option_value": None},
    )
    merged = merge_preserve_existing_overlay(
        _make_generated_overlay(generated_node),
        _make_existing_overlay(existing_node),
    )
    assert merged["nodes"][0]["value"]["future_option_value"] == 0.4


# ---------------------------------------------------------------------------
# Branch 4: Optionality fully empty → NOT preserved (allows refresh)
# ---------------------------------------------------------------------------


def test_optionality_all_empty_not_preserved() -> None:
    existing_node = _existing_node(
        node_id="TEST.SZ:L2.newbiz.tam",
        dp_id="L2.newbiz.tam",
        data_status="Optionality",
        value={"current_contribution": None, "future_option_value": None},
        confidence=None,
    )
    # Generated has a fresh different value — this simulates a later refill
    generated_node = _generated_node(
        node_id="TEST.SZ:L2.newbiz.tam",
        dp_id="L2.newbiz.tam",
        data_status="Optionality",
        value={"current_contribution": "PLACEHOLDER", "future_option_value": None},
    )
    merged = merge_preserve_existing_overlay(
        _make_generated_overlay(generated_node),
        _make_existing_overlay(existing_node),
    )
    # Should NOT preserve empty existing → generated wins
    assert merged["nodes"][0]["value"]["current_contribution"] == "PLACEHOLDER"


# ---------------------------------------------------------------------------
# Branch 5: Inactive non-event preserved
# ---------------------------------------------------------------------------


def test_inactive_non_event_preserved() -> None:
    # Pick a dp_id that is NOT in EVENT_DRIVEN_DP_IDS
    non_event_dp_id = "L0.supply.inventory"
    assert non_event_dp_id not in EVENT_DRIVEN_DP_IDS

    existing_node = _existing_node(
        node_id=f"TEST.SZ:{non_event_dp_id}",
        dp_id=non_event_dp_id,
        data_status="Inactive",
        value={"reason": "structurally inactive"},
    )
    generated_node = _generated_node(
        node_id=f"TEST.SZ:{non_event_dp_id}",
        dp_id=non_event_dp_id,
        data_status="Unknown",
    )
    merged = merge_preserve_existing_overlay(
        _make_generated_overlay(generated_node),
        _make_existing_overlay(existing_node),
    )
    out = merged["nodes"][0]
    assert out["data_status"] == "Inactive"
    assert out["value"] == {"reason": "structurally inactive"}


# ---------------------------------------------------------------------------
# Branch 6: Inactive event-type NOT preserved
# ---------------------------------------------------------------------------


def test_inactive_event_driven_not_preserved() -> None:
    # Pick a known event-driven dp_id
    event_dp_id = "L0.compete.price_war"
    assert event_dp_id in EVENT_DRIVEN_DP_IDS

    existing_node = _existing_node(
        node_id=f"TEST.SZ:{event_dp_id}",
        dp_id=event_dp_id,
        data_status="Inactive",
        value={"reason": "no price war detected"},
    )
    generated_node = _generated_node(
        node_id=f"TEST.SZ:{event_dp_id}",
        dp_id=event_dp_id,
        data_status="Inactive",
        value=None,
    )
    merged = merge_preserve_existing_overlay(
        _make_generated_overlay(generated_node),
        _make_existing_overlay(existing_node),
    )
    # Event-driven Inactive should be allowed to regenerate (transient state)
    out = merged["nodes"][0]
    assert out["value"] is None
    # data_status stays Inactive (came from generated), but value/evidence wiped
    assert out["evidence_sources"] == []


# ---------------------------------------------------------------------------
# Branch 7: Unknown NOT preserved
# ---------------------------------------------------------------------------


def test_unknown_not_preserved() -> None:
    existing_node = _existing_node(
        data_status="Unknown",
        value=None,
        confidence=None,
        evidence_sources=[],
        last_updated=None,
    )
    generated_node = _generated_node(
        data_status="Unknown",
        value=None,
    )
    merged = merge_preserve_existing_overlay(
        _make_generated_overlay(generated_node),
        _make_existing_overlay(existing_node),
    )
    # Unknown nodes are regenerated → output mirrors generated
    out = merged["nodes"][0]
    assert out["data_status"] == "Unknown"
    assert out["value"] is None


# ---------------------------------------------------------------------------
# --force bypass
# ---------------------------------------------------------------------------


def test_force_true_overwrites_known() -> None:
    existing_node = _existing_node(data_status="Known")
    generated_node = _generated_node(data_status="Unknown")
    merged = merge_preserve_existing_overlay(
        _make_generated_overlay(generated_node),
        _make_existing_overlay(existing_node),
        force=True,
    )
    out = merged["nodes"][0]
    # With force=True, generated wins even for Known nodes
    assert out["data_status"] == "Unknown"
    assert out["value"] is None
    assert out["confidence"] is None


# ---------------------------------------------------------------------------
# New slot does not disturb existing Known
# ---------------------------------------------------------------------------


def test_new_slot_added_does_not_break_existing_known() -> None:
    existing = _make_existing_overlay(_existing_node(data_status="Known"))
    # Generated overlay adds a brand-new dp_id slot
    generated = {
        "schema_version": 1,
        "ts_code": "TEST.SZ",
        "nodes": [
            _generated_node(data_status="Unknown"),
            _generated_node(
                node_id="TEST.SZ:L1.position.NEW_SLOT",
                dp_id="L1.position.NEW_SLOT",
            ),
        ],
    }
    merged = merge_preserve_existing_overlay(generated, existing)

    by_dp = {n["dp_id"]: n for n in merged["nodes"]}
    # Existing Known is preserved
    assert by_dp["L1.position.brand"]["data_status"] == "Known"
    assert by_dp["L1.position.brand"]["value"] == {"score": 0.7, "note": "leader"}
    # New slot shows up as Unknown
    assert by_dp["L1.position.NEW_SLOT"]["data_status"] == "Unknown"
    assert by_dp["L1.position.NEW_SLOT"]["value"] is None


# ---------------------------------------------------------------------------
# Idempotency — running twice should not drift
# ---------------------------------------------------------------------------


def test_merge_preserve_is_idempotent() -> None:
    existing = _make_existing_overlay(_existing_node(data_status="Known"))
    generated = _make_generated_overlay(_generated_node(data_status="Unknown"))

    first = merge_preserve_existing_overlay(generated, existing)
    # Feed first back as the new "existing" — second pass should be identical
    second = merge_preserve_existing_overlay(generated, first)
    assert first == second


# ---------------------------------------------------------------------------
# existing is None → generated returned untouched
# ---------------------------------------------------------------------------


def test_no_existing_file_returns_generated_verbatim() -> None:
    generated = _make_generated_overlay(_generated_node())
    merged = merge_preserve_existing_overlay(generated, None)
    assert merged == generated


# ---------------------------------------------------------------------------
# _should_preserve_node unit branches
# ---------------------------------------------------------------------------


def test_should_preserve_branches() -> None:
    assert _should_preserve_node({"data_status": "Known"}) is True
    assert _should_preserve_node({"data_status": "N/A"}) is True
    assert _should_preserve_node({"data_status": "Unknown"}) is False
    assert _should_preserve_node({"data_status": "Unavailable"}) is False
    assert _should_preserve_node({"data_status": "Proxy"}) is False

    # Optionality cases
    assert _should_preserve_node(
        {"data_status": "Optionality", "value": {"current_contribution": 0.5, "future_option_value": None}}
    ) is True
    assert _should_preserve_node(
        {"data_status": "Optionality", "value": {"current_contribution": None, "future_option_value": 0.2}}
    ) is True
    assert _should_preserve_node(
        {"data_status": "Optionality", "value": {"current_contribution": None, "future_option_value": None}}
    ) is False
    assert _should_preserve_node(
        {"data_status": "Optionality", "value": None}
    ) is False
    assert _should_preserve_node(
        {"data_status": "Optionality", "value": "not-a-dict"}
    ) is False

    # Inactive event vs non-event
    assert _should_preserve_node(
        {"data_status": "Inactive", "dp_id": "L0.compete.price_war"}
    ) is False
    assert _should_preserve_node(
        {"data_status": "Inactive", "dp_id": "L0.supply.inventory"}
    ) is True


# ---------------------------------------------------------------------------
# End-to-end: generate_overlay_files preserves Known across regenerations
# ---------------------------------------------------------------------------


def _write_minimal_universe(tmp_path: Path) -> tuple[Path, Path, Path, Path, Path]:
    """Build a tiny universe with 1 industry + 1 stock so generate_overlay_files
    can be exercised without depending on the real config corpus."""
    universe_path = tmp_path / "universe.yaml"
    industries_path = tmp_path / "industries.yaml"
    industry_graphs_dir = tmp_path / "industry_graphs"
    industry_overlays_dir = tmp_path / "industry_overlays"
    stock_overlays_dir = tmp_path / "stock_overlays"

    universe_path.write_text(
        yaml.safe_dump(
            {
                "constituents": [
                    {
                        "ts_code": "999999.SZ",
                        "name": "测试公司",
                        "industry_ids": ["TEST_INDUSTRY"],
                        "role": "target",
                        "pool": "regular",
                    }
                ]
            },
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    industries_path.write_text(
        yaml.safe_dump(
            {
                "industries": [
                    {
                        "id": "TEST_INDUSTRY",
                        "display_name": "测试行业",
                        "graph_status": "present",
                    }
                ]
            },
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    return (
        universe_path,
        industries_path,
        industry_graphs_dir,
        industry_overlays_dir,
        stock_overlays_dir,
    )


def test_end_to_end_known_preserved_across_regenerate(tmp_path: Path) -> None:
    (
        universe_path,
        industries_path,
        industry_graphs_dir,
        industry_overlays_dir,
        stock_overlays_dir,
    ) = _write_minimal_universe(tmp_path)

    # 1st pass — fresh generation
    generate_overlay_files(
        universe_path=universe_path,
        industries_path=industries_path,
        industry_graphs_dir=industry_graphs_dir,
        industry_overlays_dir=industry_overlays_dir,
        stock_overlays_dir=stock_overlays_dir,
    )

    overlay_path = stock_overlays_dir / "TEST_INDUSTRY" / "999999.SZ.yaml"
    assert overlay_path.exists()

    # Simulate codex filling one Known node — pick L1.position.brand
    payload = yaml.safe_load(overlay_path.read_text(encoding="utf-8"))
    brand_node = next(n for n in payload["nodes"] if n["dp_id"] == "L1.position.brand")
    brand_node["data_status"] = "Known"
    brand_node["status"] = "Known"
    brand_node["value"] = {"score": 0.92, "note": "明确龙头"}
    brand_node["confidence"] = 0.85
    brand_node["evidence_sources"] = [
        {"kind": "local_dp_id", "ref": "fin.brand_index"}
    ]
    brand_node["last_updated"] = "2026-05-13T00:00:00Z"
    overlay_path.write_text(
        yaml.safe_dump(payload, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )

    # 2nd pass — must NOT wipe the codex-filled Known node
    generate_overlay_files(
        universe_path=universe_path,
        industries_path=industries_path,
        industry_graphs_dir=industry_graphs_dir,
        industry_overlays_dir=industry_overlays_dir,
        stock_overlays_dir=stock_overlays_dir,
    )

    payload_after = yaml.safe_load(overlay_path.read_text(encoding="utf-8"))
    brand_after = next(
        n for n in payload_after["nodes"] if n["dp_id"] == "L1.position.brand"
    )
    assert brand_after["data_status"] == "Known"
    assert brand_after["value"] == {"score": 0.92, "note": "明确龙头"}
    assert brand_after["confidence"] == 0.85
    assert brand_after["evidence_sources"] == [
        {"kind": "local_dp_id", "ref": "fin.brand_index"}
    ]


def test_end_to_end_force_wipes_known(tmp_path: Path) -> None:
    (
        universe_path,
        industries_path,
        industry_graphs_dir,
        industry_overlays_dir,
        stock_overlays_dir,
    ) = _write_minimal_universe(tmp_path)

    generate_overlay_files(
        universe_path=universe_path,
        industries_path=industries_path,
        industry_graphs_dir=industry_graphs_dir,
        industry_overlays_dir=industry_overlays_dir,
        stock_overlays_dir=stock_overlays_dir,
    )

    overlay_path = stock_overlays_dir / "TEST_INDUSTRY" / "999999.SZ.yaml"
    payload = yaml.safe_load(overlay_path.read_text(encoding="utf-8"))
    brand_node = next(n for n in payload["nodes"] if n["dp_id"] == "L1.position.brand")
    brand_node["data_status"] = "Known"
    brand_node["status"] = "Known"
    brand_node["value"] = {"score": 0.92}
    overlay_path.write_text(
        yaml.safe_dump(payload, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )

    # Force regenerate — should wipe the Known value back to Unknown defaults
    generate_overlay_files(
        universe_path=universe_path,
        industries_path=industries_path,
        industry_graphs_dir=industry_graphs_dir,
        industry_overlays_dir=industry_overlays_dir,
        stock_overlays_dir=stock_overlays_dir,
        force=True,
    )

    payload_after = yaml.safe_load(overlay_path.read_text(encoding="utf-8"))
    brand_after = next(
        n for n in payload_after["nodes"] if n["dp_id"] == "L1.position.brand"
    )
    assert brand_after["data_status"] == "Unknown"
    assert brand_after["value"] is None


# ---------------------------------------------------------------------------
# apply_status_induced_invariants — post-codex normalization (compile-clean N/A)
# ---------------------------------------------------------------------------

def test_apply_status_invariants_fixes_na_missing_policy() -> None:
    """An N/A node codex left with the SLOT_DEFS-default missing_policy is
    repaired to not_applicable_remove + active_weight 0 + status mirror."""
    overlay = {"nodes": [{
        "dp_id": "L4.price.subscription", "data_status": "N/A", "status": "Unknown",
        "missing_policy": "unknown_reduce_confidence", "active_weight": 1.0,
    }]}
    n = apply_status_induced_invariants(overlay)
    assert n == 1
    node = overlay["nodes"][0]
    assert node["missing_policy"] == "not_applicable_remove"
    assert node["active_weight"] == 0.0
    assert node["status"] == "N/A"  # data_status mirrored into legacy field


def test_apply_status_invariants_inactive_and_optionality() -> None:
    overlay = {"nodes": [
        {"dp_id": "a", "data_status": "Inactive", "status": "Inactive",
         "missing_policy": "unknown_reduce_confidence", "active_weight": 1.0},
        {"dp_id": "b", "data_status": "Optionality", "status": "Optionality",
         "missing_policy": "unknown_reduce_confidence"},
    ]}
    assert apply_status_induced_invariants(overlay) == 2
    assert overlay["nodes"][0]["missing_policy"] == "inactive_zero_weight"
    assert overlay["nodes"][0]["active_weight"] == 0.0
    assert overlay["nodes"][1]["missing_policy"] == "optionality_track"


def test_apply_status_invariants_leaves_known_and_unknown_untouched() -> None:
    """Known / Unknown nodes are not in the induced map → no change, count 0."""
    overlay = {"nodes": [
        {"dp_id": "k", "data_status": "Known", "missing_policy": "optional_skip"},
        {"dp_id": "u", "data_status": "Unknown", "missing_policy": "unknown_reduce_confidence"},
    ]}
    assert apply_status_induced_invariants(overlay) == 0
    assert overlay["nodes"][0]["missing_policy"] == "optional_skip"


def test_apply_status_invariants_idempotent() -> None:
    overlay = {"nodes": [{
        "dp_id": "x", "data_status": "N/A", "status": "Unknown",
        "missing_policy": "unknown_reduce_confidence", "active_weight": 1.0,
    }]}
    assert apply_status_induced_invariants(overlay) == 1
    assert apply_status_induced_invariants(overlay) == 0  # already canonical


def test_normalize_overlay_file_status_roundtrip(tmp_path: Path) -> None:
    p = tmp_path / "x.yaml"
    p.write_text(yaml.safe_dump({"nodes": [{
        "dp_id": "L4.price.subscription", "data_status": "N/A", "status": "Unknown",
        "missing_policy": "unknown_reduce_confidence", "active_weight": 1.0,
    }]}, allow_unicode=True), encoding="utf-8")
    assert normalize_overlay_file_status(p) == 1
    reloaded = yaml.safe_load(p.read_text(encoding="utf-8"))
    assert reloaded["nodes"][0]["missing_policy"] == "not_applicable_remove"
    assert normalize_overlay_file_status(p) == 0  # second pass writes nothing
    assert normalize_overlay_file_status(tmp_path / "missing.yaml") == 0  # absent → 0


def test_sanitize_confidence_list_recovers_evidence() -> None:
    """A fill that wrote the evidence list into ``confidence`` (would crash
    compile binding a list to a scalar column) is repaired: evidence recovered
    into the empty evidence_sources slot, confidence nulled."""
    ev = [{"kind": "local_dp_id", "dp_id": "L5.is.revenue"}]
    overlay = {"nodes": [{"dp_id": "x", "confidence": ev, "evidence_sources": []}]}
    assert sanitize_node_scalar_fields(overlay) == 1
    node = overlay["nodes"][0]
    assert node["confidence"] is None
    assert node["evidence_sources"] == ev  # moved, not lost


def test_sanitize_confidence_list_without_clobbering_existing_evidence() -> None:
    existing = [{"kind": "web_analysis"}]
    overlay = {"nodes": [{"dp_id": "x", "confidence": [{"kind": "local_dp_id"}],
                          "evidence_sources": existing}]}
    assert sanitize_node_scalar_fields(overlay) == 1
    assert overlay["nodes"][0]["confidence"] is None
    assert overlay["nodes"][0]["evidence_sources"] == existing  # not overwritten


def test_sanitize_leaves_scalar_confidence_and_nulls_bad_materiality() -> None:
    overlay = {"nodes": [
        {"dp_id": "ok", "confidence": 0.7, "materiality": 0.8},
        {"dp_id": "bad", "materiality": ["x"]},
    ]}
    assert sanitize_node_scalar_fields(overlay) == 1  # only the bad-materiality node
    assert overlay["nodes"][0]["confidence"] == 0.7
    assert overlay["nodes"][1]["materiality"] is None


# ---------------------------------------------------------------------------
# build_stock_overlay is consumed correctly (smoke)
# ---------------------------------------------------------------------------


def test_merge_preserves_through_full_built_overlay() -> None:
    membership = Membership(
        ts_code="000001.SZ",
        name="测试",
        industry_id="TEST",
        primary_industry=True,
        all_industries=("TEST",),
        role="target",
        pool="regular",
    )
    overlay_a = build_stock_overlay(membership)
    # Fill a node as if codex did it
    brand = next(n for n in overlay_a["nodes"] if n.get("dp_id") == "L1.position.brand")
    brand["data_status"] = "Known"
    brand["status"] = "Known"
    brand["value"] = {"score": 0.5}
    brand["confidence"] = 0.7
    brand["evidence_sources"] = [{"kind": "local_dp_id", "ref": "ref1"}]

    overlay_b = build_stock_overlay(membership)  # freshly rebuilt — all Unknown

    merged = merge_preserve_existing_overlay(overlay_b, overlay_a)
    brand_merged = next(
        n for n in merged["nodes"] if n.get("dp_id") == "L1.position.brand"
    )
    assert brand_merged["data_status"] == "Known"
    assert brand_merged["value"] == {"score": 0.5}


# ---------------------------------------------------------------------------
# Z5 Fix 1: status-induced field consistency on merge_preserve.
#
# When the existing node carries a non-default status (N/A / Inactive /
# Optionality), merge_preserve must also re-induce missing_policy and
# active_weight so the merged node passes ``validate_stock_overlay``:
#   * N/A node ⇒ missing_policy=not_applicable_remove (validator hard error
#     otherwise — see overlays.py:963)
#   * Inactive non-event ⇒ missing_policy=inactive_zero_weight, active_weight=0
#   * Optionality (filled) ⇒ missing_policy=optionality_track
#   * Known ⇒ keep SLOT_DEFS default missing_policy (different per dp_id)
# ---------------------------------------------------------------------------


def _na_node_with_default_state_fields() -> dict[str, Any]:
    """Existing N/A node where the prior merge left missing_policy /
    active_weight at SLOT_DEFS defaults — the bug we're fixing."""

    return {
        "node_id": "TEST.SZ:L1.position.brand",
        "dp_id": "L1.position.brand",
        "data_status": "N/A",
        "status": "N/A",
        "value": None,
        "confidence": None,
        "evidence_sources": [],
        "last_updated": "2026-01-15T00:00:00Z",
        "data_source": "codex_local_fill",
        "missing_reason": "company does not operate this segment",
        "node_name": "品牌力与认知度",
        "materiality": 0.65,
        # The mismatched state — SLOT_DEFS defaults that should be overridden
        "missing_policy": "unknown_reduce_confidence",
        "active_weight": 1.0,
    }


def test_na_merge_induces_not_applicable_remove() -> None:
    """N/A merge must induce missing_policy=not_applicable_remove
    and active_weight=0.0 even if existing node had stale defaults."""

    existing_node = _na_node_with_default_state_fields()
    generated_node = _generated_node(data_status="Unknown")
    # The generated node carries SLOT_DEFS-default state fields
    generated_node["missing_policy"] = "unknown_reduce_confidence"
    generated_node["active_weight"] = 1.0

    merged = merge_preserve_existing_overlay(
        _make_generated_overlay(generated_node),
        _make_existing_overlay(existing_node),
    )
    out = merged["nodes"][0]
    assert out["data_status"] == "N/A"
    assert out["missing_policy"] == "not_applicable_remove"
    assert out["active_weight"] == 0.0


def test_inactive_non_event_merge_induces_inactive_zero_weight() -> None:
    """Non-event Inactive merge must induce missing_policy=inactive_zero_weight
    and active_weight=0.0."""

    # Pick a non-event dp_id (NOT in EVENT_DRIVEN_DP_IDS).
    non_event_dp_id = "L0.supply.inventory"
    assert non_event_dp_id not in EVENT_DRIVEN_DP_IDS

    existing_node = _existing_node(
        node_id=f"TEST.SZ:{non_event_dp_id}",
        dp_id=non_event_dp_id,
        data_status="Inactive",
        value={"reason": "structurally inactive"},
    )
    # Existing node had stale state (the bug we're fixing)
    existing_node["missing_policy"] = "unknown_reduce_confidence"
    existing_node["active_weight"] = 1.0
    generated_node = _generated_node(
        node_id=f"TEST.SZ:{non_event_dp_id}",
        dp_id=non_event_dp_id,
        data_status="Unknown",
    )
    generated_node["missing_policy"] = "unknown_reduce_confidence"
    generated_node["active_weight"] = 1.0

    merged = merge_preserve_existing_overlay(
        _make_generated_overlay(generated_node),
        _make_existing_overlay(existing_node),
    )
    out = merged["nodes"][0]
    assert out["data_status"] == "Inactive"
    assert out["missing_policy"] == "inactive_zero_weight"
    assert out["active_weight"] == 0.0


def test_optionality_filled_merge_induces_optionality_track() -> None:
    """Optionality with filled value preserved → missing_policy=optionality_track."""

    existing_node = _existing_node(
        node_id="TEST.SZ:L2.newbiz.tam",
        dp_id="L2.newbiz.tam",
        data_status="Optionality",
        value={"current_contribution": 0.3, "future_option_value": None},
        confidence=0.6,
    )
    # Existing had wrong missing_policy
    existing_node["missing_policy"] = "unknown_reduce_confidence"
    generated_node = _generated_node(
        node_id="TEST.SZ:L2.newbiz.tam",
        dp_id="L2.newbiz.tam",
        data_status="Optionality",
        value={"current_contribution": None, "future_option_value": None},
    )
    generated_node["missing_policy"] = "unknown_reduce_confidence"

    merged = merge_preserve_existing_overlay(
        _make_generated_overlay(generated_node),
        _make_existing_overlay(existing_node),
    )
    out = merged["nodes"][0]
    assert out["data_status"] == "Optionality"
    assert out["missing_policy"] == "optionality_track"


def test_known_merge_keeps_slot_def_default_missing_policy() -> None:
    """Known merge must NOT override missing_policy / active_weight —
    different Known dp_ids use different SLOT_DEFS defaults (e.g.
    conditional_required Known vs optional Known)."""

    existing_node = _existing_node(data_status="Known")
    # Existing carries the canonical Known state — must round-trip exactly.
    existing_node["missing_policy"] = "unknown_reduce_confidence"
    existing_node["active_weight"] = 1.0

    generated_node = _generated_node(data_status="Unknown")
    # Generated carries SLOT_DEFS default — must NOT be overridden.
    generated_node["missing_policy"] = "unknown_reduce_confidence"
    generated_node["active_weight"] = 1.0

    merged = merge_preserve_existing_overlay(
        _make_generated_overlay(generated_node),
        _make_existing_overlay(existing_node),
    )
    out = merged["nodes"][0]
    assert out["data_status"] == "Known"
    # SLOT_DEFS default flows through; not overridden by induced map.
    assert out["missing_policy"] == "unknown_reduce_confidence"
    assert out["active_weight"] == 1.0


# ---------------------------------------------------------------------------
# Z5 Fix 4: EVENT_DRIVEN_DP_IDS is derived from governance.yaml.
#
# Pre-Z5 root cause: the frozenset was hardcoded inline and drifted from
# governance — governance had two new event_driven dp_ids that were not
# in the code set, and the code set had three legacy entries with no
# corresponding governance row. This caused merge_preserve to make wrong
# decisions on regeneration.
# ---------------------------------------------------------------------------


def test_event_driven_dp_ids_matches_governance() -> None:
    """The frozenset must equal the governance event_driven set exactly."""

    governance = yaml.safe_load(
        (Path(__file__).resolve().parents[1] / "config" / "llm_field_governance.yaml").read_text(
            encoding="utf-8"
        )
    )
    gov_events = frozenset(
        dp
        for dp, cfg in (governance.get("data_points") or {}).items()
        if isinstance(cfg, dict)
        and cfg.get("refresh_trigger") == "event_driven"
    )
    assert EVENT_DRIVEN_DP_IDS == gov_events
    # Spot-check both directions of drift the fix was guarding against.
    assert "L0.sentiment.social" in EVENT_DRIVEN_DP_IDS
    assert "L0.compete.share_concentration" in EVENT_DRIVEN_DP_IDS
    # Legacy entries with no governance row must be gone.
    assert "L9.company.mgmt_litigation" not in EVENT_DRIVEN_DP_IDS
    assert "L9.industry.compete_risk" not in EVENT_DRIVEN_DP_IDS
    assert "L9.industry.policy_change" not in EVENT_DRIVEN_DP_IDS


def test_event_driven_dp_ids_missing_governance_empty(tmp_path: Path) -> None:
    """If the governance file path is missing, the loader returns empty."""

    from mvp20.overlays import _load_event_driven_from_governance
    import mvp20.overlays as overlays_module

    original = overlays_module._GOVERNANCE_PATH
    overlays_module._GOVERNANCE_PATH = tmp_path / "no-such-governance.yaml"
    try:
        result = _load_event_driven_from_governance()
        assert result == frozenset()
    finally:
        overlays_module._GOVERNANCE_PATH = original


def test_event_driven_dp_ids_sync_between_modules() -> None:
    """The set used inside codex_prompt_gen must be the same object as the
    one exported by mvp20.overlays — no second hardcoded copy lurking."""

    import importlib.util as _iu

    spec = _iu.spec_from_file_location(
        "codex_prompt_gen_z5",
        Path(__file__).resolve().parents[1] / "scripts" / "codex_prompt_gen.py",
    )
    assert spec is not None and spec.loader is not None
    mod = _iu.module_from_spec(spec)
    spec.loader.exec_module(mod)
    set_from_codex = mod._event_driven_dp_ids()
    assert set_from_codex == EVENT_DRIVEN_DP_IDS
