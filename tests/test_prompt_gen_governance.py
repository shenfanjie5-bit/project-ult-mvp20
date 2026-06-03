"""Tests for ``scripts/codex_prompt_gen.py`` Z1d governance + status filter.

These tests guard the property that the prompt generator only surfaces
dp_ids that:

  * Are registered in ``config/llm_field_governance.yaml`` (allowlist).
  * Have ``route ∈ {llm_close, llm_web}`` (LLM-fillable routes only).
  * Have ``data_status`` matching the refill rules (Unknown, empty
    Optionality, or event-driven Inactive).
  * Match the user-supplied ``--model-tier`` filter, if any.
"""

from __future__ import annotations

import importlib.util
import sqlite3
import sys
from pathlib import Path

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[1]
# Load codex_prompt_gen.py as a module — scripts/ is not a package.
_SPEC = importlib.util.spec_from_file_location(
    "codex_prompt_gen",
    ROOT / "scripts" / "codex_prompt_gen.py",
)
assert _SPEC is not None and _SPEC.loader is not None
codex_prompt_gen = importlib.util.module_from_spec(_SPEC)
sys.modules["codex_prompt_gen"] = codex_prompt_gen
_SPEC.loader.exec_module(codex_prompt_gen)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _node(
    *,
    dp_id: str,
    data_status: str = "Unknown",
    value=None,
    node_name: str = "test_node",
) -> dict:
    return {
        "node_id": f"TEST.SZ:{dp_id}",
        "dp_id": dp_id,
        "data_status": data_status,
        "value": value,
        "node_name": node_name,
        "materiality": 0.5,
        "required_level": "conditional_required",
    }


@pytest.fixture
def mini_governance() -> dict:
    """A compact governance dict covering the cases the tests need."""

    return {
        "data_points": {
            "L1.position.brand": {
                "route": "llm_close",
                "model_tier": "analysis",
                "refresh_trigger": "annual_filing",
                "source_dependencies": ["L5.is.revenue"],
            },
            "L3.channel.mix": {
                "route": "llm_close",
                "model_tier": "cheap_extract",
                "refresh_trigger": "source_fingerprint_changed",
                "source_dependencies": [],
            },
            "L0.compete.price_war": {
                "route": "llm_close",
                "model_tier": "cheap_classify",
                "refresh_trigger": "event_driven",
                # Non-empty source_dependencies so the fingerprint gate
                # has something real to hash (matches the production
                # governance.yaml entry, which lists news/media deps).
                "source_dependencies": [
                    "L9.industry.compete_risk",
                    "L9.media.report",
                ],
            },
            "L2.newbiz.tam": {
                "route": "llm_close",
                "model_tier": "analysis",
                "refresh_trigger": "annual_filing",
                "source_dependencies": [],
            },
            # Skip-routed field for negative test
            "L5.is.revenue": {
                "route": "skip",  # hypothetical — verifies skip exclusion
                "model_tier": "analysis",
                "refresh_trigger": "quarterly_filing",
            },
            # Derive-routed field for negative test
            "L5.is.gross_margin": {
                "route": "derive",
                "model_tier": "analysis",
                "refresh_trigger": "quarterly_filing",
            },
        }
    }


# ---------------------------------------------------------------------------
# Unit tests for _is_fillable
# ---------------------------------------------------------------------------


def test_unknown_plus_llm_close_is_fillable(mini_governance: dict) -> None:
    node = _node(dp_id="L1.position.brand", data_status="Unknown")
    entry = codex_prompt_gen.get_governance("L1.position.brand", mini_governance)
    ok, reason = codex_prompt_gen._is_fillable(node, entry)
    assert ok is True
    assert reason is None


def test_unknown_plus_skip_route_not_fillable(mini_governance: dict) -> None:
    node = _node(dp_id="L5.is.revenue", data_status="Unknown")
    entry = codex_prompt_gen.get_governance("L5.is.revenue", mini_governance)
    ok, reason = codex_prompt_gen._is_fillable(node, entry)
    assert ok is False
    assert reason == "route=skip"


def test_unknown_plus_derive_route_not_fillable(mini_governance: dict) -> None:
    node = _node(dp_id="L5.is.gross_margin", data_status="Unknown")
    entry = codex_prompt_gen.get_governance(
        "L5.is.gross_margin", mini_governance
    )
    ok, reason = codex_prompt_gen._is_fillable(node, entry)
    assert ok is False
    assert reason == "route=derive"


def test_optionality_with_none_value_is_fillable(mini_governance: dict) -> None:
    node = _node(
        dp_id="L2.newbiz.tam", data_status="Optionality", value=None
    )
    entry = codex_prompt_gen.get_governance("L2.newbiz.tam", mini_governance)
    ok, reason = codex_prompt_gen._is_fillable(node, entry)
    assert ok is True
    assert reason is None


def test_optionality_with_empty_dict_is_fillable(mini_governance: dict) -> None:
    node = _node(
        dp_id="L2.newbiz.tam",
        data_status="Optionality",
        value={"current_contribution": None, "future_option_value": None},
    )
    entry = codex_prompt_gen.get_governance("L2.newbiz.tam", mini_governance)
    ok, _ = codex_prompt_gen._is_fillable(node, entry)
    assert ok is True


def test_optionality_with_filled_value_not_fillable(
    mini_governance: dict,
) -> None:
    node = _node(
        dp_id="L2.newbiz.tam",
        data_status="Optionality",
        value={"current_contribution": 0.3, "future_option_value": None},
    )
    entry = codex_prompt_gen.get_governance("L2.newbiz.tam", mini_governance)
    ok, reason = codex_prompt_gen._is_fillable(node, entry)
    assert ok is False
    assert reason == "optionality_already_filled"


def test_inactive_event_driven_without_db_context_not_fillable(
    mini_governance: dict,
) -> None:
    """Z5 Fix 3 backward-compat: without db_path/ts_code we can't evaluate
    the fingerprint, so we conservatively skip rather than spam codex."""

    # L0.compete.price_war is event_driven in governance.
    node = _node(
        dp_id="L0.compete.price_war", data_status="Inactive", value=None
    )
    entry = codex_prompt_gen.get_governance(
        "L0.compete.price_war", mini_governance
    )
    ok, reason = codex_prompt_gen._is_fillable(node, entry)
    assert ok is False
    assert reason == "inactive_event_no_db_context"


def test_inactive_static_not_fillable(mini_governance: dict) -> None:
    # L1.position.brand is NOT event_driven in governance (refresh_trigger
    # is annual_filing) and not in EVENT_DRIVEN_DP_IDS → static Inactive
    # should never be re-filled.
    node = _node(
        dp_id="L1.position.brand", data_status="Inactive", value=None
    )
    entry = codex_prompt_gen.get_governance("L1.position.brand", mini_governance)
    ok, reason = codex_prompt_gen._is_fillable(node, entry)
    assert ok is False
    assert reason == "inactive_static"


# ---------------------------------------------------------------------------
# Z5 Fix 3: event-driven Inactive must pass fingerprint gating.
#
# Root cause: _is_fillable previously returned True unconditionally for
# Inactive + event_driven, so cheap_classify pass re-prompted codex every
# run with no signal that anything changed.
# ---------------------------------------------------------------------------


def test_inactive_event_driven_no_baseline_fingerprint_is_fillable(
    tmp_path: Path, mini_governance: dict
) -> None:
    """Inactive + event_driven + no source_fingerprint_at_fill yet
    → fillable (baseline-missing path)."""

    db_path = _make_z2_db(
        tmp_path,
        [
            (
                "000063.SZ",
                "L9.industry.compete_risk",
                '{"signal": "no_event"}',
                "Inactive",
                None,
                "tushare_news",
                1700000000,
            ),
            (
                "000063.SZ",
                "L9.media.report",
                '{"signal": "no_report"}',
                "Inactive",
                None,
                "media_feed",
                1700000000,
            ),
        ],
    )
    node = _node(
        dp_id="L0.compete.price_war", data_status="Inactive", value=None
    )
    # No source_fingerprint_at_fill on the node — legacy / first-run.
    entry = codex_prompt_gen.get_governance(
        "L0.compete.price_war", mini_governance
    )
    ok, reason = codex_prompt_gen._is_fillable(
        node, entry, db_path=db_path, ts_code="000063.SZ"
    )
    assert ok is True
    assert reason == "refresh:fingerprint_baseline_missing"


def test_inactive_event_driven_unchanged_fingerprint_not_fillable(
    tmp_path: Path, mini_governance: dict
) -> None:
    """Inactive + event_driven + fingerprint unchanged → NOT fillable
    (the gating that fixes the cheap_classify spam bug)."""

    from mvp20.fingerprint import compute_dependency_fingerprint

    db_path = _make_z2_db(
        tmp_path,
        [
            (
                "000063.SZ",
                "L9.industry.compete_risk",
                '{"signal": "no_event"}',
                "Inactive",
                None,
                "tushare_news",
                1700000000,
            ),
            (
                "000063.SZ",
                "L9.media.report",
                '{"signal": "no_report"}',
                "Inactive",
                None,
                "media_feed",
                1700000000,
            ),
        ],
    )
    current = compute_dependency_fingerprint(
        "000063.SZ",
        ["L9.industry.compete_risk", "L9.media.report"],
        db_path,
    )
    assert current is not None

    node = _node(
        dp_id="L0.compete.price_war", data_status="Inactive", value=None
    )
    node["source_fingerprint_at_fill"] = current
    entry = codex_prompt_gen.get_governance(
        "L0.compete.price_war", mini_governance
    )
    ok, reason = codex_prompt_gen._is_fillable(
        node, entry, db_path=db_path, ts_code="000063.SZ"
    )
    assert ok is False
    assert reason == "inactive_event_no_change:fingerprint_unchanged"


def test_inactive_event_driven_fingerprint_changed_is_fillable(
    tmp_path: Path, mini_governance: dict
) -> None:
    """Inactive + event_driven + stored fingerprint stale → fillable."""

    db_path = _make_z2_db(
        tmp_path,
        [
            (
                "000063.SZ",
                "L9.industry.compete_risk",
                '{"signal": "new_event_today"}',
                "Inactive",
                None,
                "tushare_news",
                1700000000,
            ),
            (
                "000063.SZ",
                "L9.media.report",
                '{"signal": "no_report"}',
                "Inactive",
                None,
                "media_feed",
                1700000000,
            ),
        ],
    )
    node = _node(
        dp_id="L0.compete.price_war", data_status="Inactive", value=None
    )
    node["source_fingerprint_at_fill"] = "deadbeefdeadbeef"  # stale
    entry = codex_prompt_gen.get_governance(
        "L0.compete.price_war", mini_governance
    )
    ok, reason = codex_prompt_gen._is_fillable(
        node, entry, db_path=db_path, ts_code="000063.SZ"
    )
    assert ok is True
    assert reason is not None
    assert reason.startswith("refresh:source_changed_")


def test_known_not_fillable(mini_governance: dict) -> None:
    node = _node(
        dp_id="L1.position.brand",
        data_status="Known",
        value={"score": 0.8},
    )
    entry = codex_prompt_gen.get_governance("L1.position.brand", mini_governance)
    ok, reason = codex_prompt_gen._is_fillable(node, entry)
    assert ok is False
    assert reason == "preserved_known"


def test_na_not_fillable(mini_governance: dict) -> None:
    node = _node(dp_id="L1.position.brand", data_status="N/A")
    entry = codex_prompt_gen.get_governance("L1.position.brand", mini_governance)
    ok, reason = codex_prompt_gen._is_fillable(node, entry)
    assert ok is False
    assert reason == "preserved_n/a"


def test_dp_id_not_in_governance_not_fillable(mini_governance: dict) -> None:
    node = _node(dp_id="L99.nonexistent.field", data_status="Unknown")
    entry = codex_prompt_gen.get_governance(
        "L99.nonexistent.field", mini_governance
    )
    assert entry is None
    ok, reason = codex_prompt_gen._is_fillable(node, entry)
    assert ok is False
    assert reason == "not_in_governance"


def test_model_tier_analysis_filter_excludes_cheap_extract(
    mini_governance: dict,
) -> None:
    node = _node(dp_id="L3.channel.mix", data_status="Unknown")
    entry = codex_prompt_gen.get_governance("L3.channel.mix", mini_governance)
    ok, reason = codex_prompt_gen._is_fillable(
        node, entry, model_tier_filter="analysis"
    )
    assert ok is False
    assert reason == "tier_mismatch_cheap_extract"


def test_model_tier_cheap_extract_filter_includes_cheap_extract(
    mini_governance: dict,
) -> None:
    node = _node(dp_id="L3.channel.mix", data_status="Unknown")
    entry = codex_prompt_gen.get_governance("L3.channel.mix", mini_governance)
    ok, _ = codex_prompt_gen._is_fillable(
        node, entry, model_tier_filter="cheap_extract"
    )
    assert ok is True


def test_model_tier_all_no_filter(mini_governance: dict) -> None:
    # With "all", both cheap_extract and analysis pass.
    node_cheap = _node(dp_id="L3.channel.mix", data_status="Unknown")
    node_analysis = _node(dp_id="L1.position.brand", data_status="Unknown")
    entry_cheap = codex_prompt_gen.get_governance(
        "L3.channel.mix", mini_governance
    )
    entry_analysis = codex_prompt_gen.get_governance(
        "L1.position.brand", mini_governance
    )
    ok1, _ = codex_prompt_gen._is_fillable(
        node_cheap, entry_cheap, model_tier_filter="all"
    )
    ok2, _ = codex_prompt_gen._is_fillable(
        node_analysis, entry_analysis, model_tier_filter="all"
    )
    assert ok1 is True
    assert ok2 is True


# ---------------------------------------------------------------------------
# Tests for _filter_nodes (the higher-level dispatcher)
# ---------------------------------------------------------------------------


def test_filter_nodes_separates_fillable_from_skipped(
    mini_governance: dict,
) -> None:
    nodes = [
        _node(dp_id="L1.position.brand", data_status="Unknown"),
        _node(dp_id="L3.channel.mix", data_status="Unknown"),
        _node(dp_id="L5.is.revenue", data_status="Unknown"),  # skip route
        _node(
            dp_id="L2.newbiz.tam",
            data_status="Optionality",
            value={"current_contribution": 0.5, "future_option_value": None},
        ),  # already filled optionality
        _node(dp_id="L99.foo.bar", data_status="Unknown"),  # not in gov
    ]
    fillable, skipped = codex_prompt_gen._filter_nodes(nodes, mini_governance)
    fillable_dps = [n["dp_id"] for n in fillable]
    assert set(fillable_dps) == {"L1.position.brand", "L3.channel.mix"}
    skip_map = dict(skipped)
    assert skip_map["L5.is.revenue"] == "route=skip"
    assert skip_map["L99.foo.bar"] == "not_in_governance"
    assert skip_map["L2.newbiz.tam"] == "optionality_already_filled"


def test_filter_nodes_with_layer_prefix(mini_governance: dict) -> None:
    # Use Unknown L0 dp_id to keep filtering semantics independent of
    # the Z5-Fix-3 fingerprint gate on Inactive event-driven nodes.
    nodes = [
        _node(dp_id="L0.compete.price_war", data_status="Unknown"),
        _node(dp_id="L1.position.brand", data_status="Unknown"),
        _node(dp_id="L3.channel.mix", data_status="Unknown"),
    ]
    fillable, _ = codex_prompt_gen._filter_nodes(
        nodes, mini_governance, layer_prefix="L0."
    )
    assert [n["dp_id"] for n in fillable] == ["L0.compete.price_war"]


def test_filter_nodes_with_layer_exclude(mini_governance: dict) -> None:
    nodes = [
        _node(dp_id="L0.compete.price_war", data_status="Inactive"),
        _node(dp_id="L1.position.brand", data_status="Unknown"),
    ]
    fillable, _ = codex_prompt_gen._filter_nodes(
        nodes, mini_governance, layer_exclude=("L0.",)
    )
    assert [n["dp_id"] for n in fillable] == ["L1.position.brand"]


def test_filter_nodes_with_model_tier_filter(mini_governance: dict) -> None:
    nodes = [
        _node(dp_id="L1.position.brand", data_status="Unknown"),  # analysis
        _node(dp_id="L3.channel.mix", data_status="Unknown"),  # cheap_extract
    ]
    fillable, _ = codex_prompt_gen._filter_nodes(
        nodes, mini_governance, model_tier_filter="cheap_extract"
    )
    assert [n["dp_id"] for n in fillable] == ["L3.channel.mix"]


# ---------------------------------------------------------------------------
# Tests for _preserved_dp_ids (ban list)
# ---------------------------------------------------------------------------


def test_preserved_collects_known_na_inactive_filled_optionality(
    mini_governance: dict,
) -> None:
    nodes = [
        _node(dp_id="L1.position.brand", data_status="Known", value={"a": 1}),
        _node(dp_id="L3.channel.mix", data_status="N/A"),
        _node(
            dp_id="L2.newbiz.tam",
            data_status="Optionality",
            value={"current_contribution": 0.3},
        ),
        _node(dp_id="L0.compete.price_war", data_status="Inactive"),
        # Unknown — should NOT appear in ban list
        _node(dp_id="L5.is.revenue", data_status="Unknown"),
    ]
    preserved = codex_prompt_gen._preserved_dp_ids(nodes, mini_governance)
    preserved_map = dict(preserved)
    assert preserved_map["L1.position.brand"] == "Known"
    assert preserved_map["L3.channel.mix"] == "N/A"
    assert preserved_map["L2.newbiz.tam"] == "Optionality(filled)"
    # L0.compete.price_war is event-driven, so Inactive is *not* preserved
    assert "L0.compete.price_war" not in preserved_map
    assert "L5.is.revenue" not in preserved_map


def test_preserved_excludes_unregistered_dp_ids(mini_governance: dict) -> None:
    """Meta fields not in governance must NOT appear in the ban list."""

    nodes = [
        _node(dp_id="L1.position.brand", data_status="Known", value={"a": 1}),
        # Non-governance meta field (like the legacy "company" portrait slot)
        _node(dp_id="company", data_status="Known", value={"name": "foo"}),
    ]
    preserved = codex_prompt_gen._preserved_dp_ids(nodes, mini_governance)
    preserved_map = dict(preserved)
    assert "L1.position.brand" in preserved_map
    assert "company" not in preserved_map


# ---------------------------------------------------------------------------
# Tests for governance loader / lookup
# ---------------------------------------------------------------------------


def test_load_governance_returns_real_yaml() -> None:
    gov = codex_prompt_gen.load_governance()
    assert isinstance(gov, dict)
    assert "data_points" in gov
    # Must include the 111 LLM dp_ids registered in Z1b + Z3.
    assert "L1.position.brand" in gov["data_points"]
    assert "L3.channel.mix" in gov["data_points"]


def test_load_governance_missing_returns_empty(tmp_path: Path) -> None:
    gov = codex_prompt_gen.load_governance(tmp_path / "missing.yaml")
    assert gov == {}


def test_get_governance_returns_none_for_unknown_dp() -> None:
    gov = codex_prompt_gen.load_governance()
    assert codex_prompt_gen.get_governance("L99.no.such.field", gov) is None


# ---------------------------------------------------------------------------
# Tests for list-only output
# ---------------------------------------------------------------------------


def test_list_only_industry_format(tmp_path: Path) -> None:
    # Hermetic: copy the real AI_COMPUTE overlay into a temp ``root`` and flip
    # one Known L0 node back to Unknown so there is a deterministic *fillable*
    # node. This exercises the full governance lookup path AND the
    # "Tier distribution" rendering branch (which only emits when ≥1 node is
    # fillable) without depending on how many real overlay nodes happen to be
    # pre-filled — the committed overlay had 27 Unknown (fillable) L0 nodes,
    # but the C1 closed-loop fill flipped them to Known/Inactive, which would
    # otherwise leave Fillable: 0 and drop the tier-distribution section.
    src = ROOT / "config" / "industry_overlays" / "AI_COMPUTE.yaml"
    overlay = yaml.safe_load(src.read_text(encoding="utf-8")) or {}
    flipped = False
    for node in overlay.get("nodes") or []:
        if (
            str(node.get("dp_id") or "").startswith("L0.")
            and node.get("data_status") == "Known"
        ):
            node["data_status"] = "Unknown"
            node["value"] = None
            flipped = True
            break
    assert flipped, "expected at least one Known L0 node to flip to Unknown"

    dst_dir = tmp_path / "config" / "industry_overlays"
    dst_dir.mkdir(parents=True, exist_ok=True)
    (dst_dir / "AI_COMPUTE.yaml").write_text(
        yaml.safe_dump(overlay, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )

    report = codex_prompt_gen.build_list_only_report(
        "AI_COMPUTE", None, root=tmp_path, model_tier_filter="all"
    )
    assert "list-only" in report
    assert "AI_COMPUTE" in report
    assert "Fillable:" in report
    assert "Skipped:" in report
    assert "Tier distribution" in report


def test_list_only_company_with_tier_filter() -> None:
    report = codex_prompt_gen.build_list_only_report(
        "AI_COMPUTE", "000063.SZ", model_tier_filter="cheap_extract"
    )
    # Header reflects the company + the active tier filter.
    assert "stock AI_COMPUTE/000063.SZ" in report
    assert "model_tier=cheap_extract" in report
    # Standard list-only structure is present.
    assert "Fillable:" in report
    assert "Skipped:" in report
    # The tier filter actually filters: dp_ids belonging to OTHER model tiers
    # are bucketed as tier_mismatch. This assertion is hermetic — it does not
    # depend on how many cheap_extract dp_ids happen to be already filled.
    # (The previous assertion pinned a specific dp_id, L3.channel.mix, into the
    # fillable list; it broke once Phase C1 filled that field, dropping it from
    # "Fillable" into "preserved_known".)
    assert "tier_mismatch_" in report


# ---------------------------------------------------------------------------
# Z2: refresh-trigger fingerprint integration with _is_fillable
# ---------------------------------------------------------------------------


def _make_z2_db(tmp_path: Path, rows: list[tuple]) -> Path:
    """Build a tiny realtime_current SQLite for Z2 refresh-trigger tests."""

    db_path = tmp_path / "hot.sqlite"
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            CREATE TABLE realtime_current (
                ts_code TEXT NOT NULL,
                dp_id TEXT NOT NULL,
                value_json TEXT NOT NULL,
                data_status TEXT NOT NULL,
                confidence REAL,
                source TEXT NOT NULL,
                updated_at INTEGER NOT NULL,
                PRIMARY KEY (ts_code, dp_id)
            )
            """
        )
        conn.executemany(
            "INSERT INTO realtime_current VALUES (?, ?, ?, ?, ?, ?, ?)",
            rows,
        )
        conn.commit()
    finally:
        conn.close()
    return db_path


def test_known_with_matching_fingerprint_not_fillable(
    tmp_path: Path, mini_governance: dict
) -> None:
    """Z2: Known + same source fingerprint → preserved."""

    from mvp20.fingerprint import compute_dependency_fingerprint

    db_path = _make_z2_db(
        tmp_path,
        [
            (
                "000063.SZ",
                "L5.is.revenue",
                '{"scalar": 100, "period": "20260331"}',
                "Known",
                0.9,
                "tushare",
                1700000000,
            )
        ],
    )
    current = compute_dependency_fingerprint(
        "000063.SZ", ["L5.is.revenue"], db_path
    )
    assert current is not None

    node = _node(
        dp_id="L1.position.brand",
        data_status="Known",
        value={"score": 0.8},
    )
    node["source_fingerprint_at_fill"] = current
    entry = codex_prompt_gen.get_governance(
        "L1.position.brand", mini_governance
    )
    ok, reason = codex_prompt_gen._is_fillable(
        node, entry, db_path=db_path, ts_code="000063.SZ"
    )
    assert ok is False
    assert reason == "preserved_known:fingerprint_unchanged"


def test_known_with_mismatch_fingerprint_is_fillable(
    tmp_path: Path, mini_governance: dict
) -> None:
    """Z2: Known + stale fingerprint → refresh queued."""

    db_path = _make_z2_db(
        tmp_path,
        [
            (
                "000063.SZ",
                "L5.is.revenue",
                '{"scalar": 100, "period": "20260331"}',
                "Known",
                0.9,
                "tushare",
                1700000000,
            )
        ],
    )

    node = _node(
        dp_id="L1.position.brand",
        data_status="Known",
        value={"score": 0.8},
    )
    node["source_fingerprint_at_fill"] = "0000000000000000"  # stale
    entry = codex_prompt_gen.get_governance(
        "L1.position.brand", mini_governance
    )
    ok, reason = codex_prompt_gen._is_fillable(
        node, entry, db_path=db_path, ts_code="000063.SZ"
    )
    assert ok is True
    assert reason is not None
    assert reason.startswith("refresh:source_changed_")


def test_known_with_no_fingerprint_baseline_is_fillable(
    tmp_path: Path, mini_governance: dict
) -> None:
    """Z2: legacy Known nodes (no fingerprint yet) refresh once for baseline."""

    db_path = _make_z2_db(
        tmp_path,
        [
            (
                "000063.SZ",
                "L5.is.revenue",
                '{"scalar": 100, "period": "20260331"}',
                "Known",
                0.9,
                "tushare",
                1700000000,
            )
        ],
    )
    node = _node(
        dp_id="L1.position.brand",
        data_status="Known",
        value={"score": 0.8},
    )
    # no source_fingerprint_at_fill key on the node
    entry = codex_prompt_gen.get_governance(
        "L1.position.brand", mini_governance
    )
    ok, reason = codex_prompt_gen._is_fillable(
        node, entry, db_path=db_path, ts_code="000063.SZ"
    )
    assert ok is True
    assert reason == "refresh:fingerprint_baseline_missing"


def test_known_without_db_path_still_preserved(mini_governance: dict) -> None:
    """Backward compat: when db_path is None, Known is preserved as before."""

    node = _node(
        dp_id="L1.position.brand",
        data_status="Known",
        value={"score": 0.8},
    )
    node["source_fingerprint_at_fill"] = "irrelevant"
    entry = codex_prompt_gen.get_governance(
        "L1.position.brand", mini_governance
    )
    ok, reason = codex_prompt_gen._is_fillable(node, entry)
    assert ok is False
    assert reason == "preserved_known"


def test_filter_nodes_threads_db_path_and_ts_code(
    tmp_path: Path, mini_governance: dict
) -> None:
    """Integration: _filter_nodes correctly forwards Z2 refresh args."""

    from mvp20.fingerprint import compute_dependency_fingerprint

    db_path = _make_z2_db(
        tmp_path,
        [
            (
                "000063.SZ",
                "L5.is.revenue",
                '{"scalar": 100, "period": "20260331"}',
                "Known",
                0.9,
                "tushare",
                1700000000,
            )
        ],
    )
    current = compute_dependency_fingerprint(
        "000063.SZ", ["L5.is.revenue"], db_path
    )
    matching_node = _node(
        dp_id="L1.position.brand", data_status="Known", value={"x": 1}
    )
    matching_node["source_fingerprint_at_fill"] = current
    stale_node = _node(
        dp_id="L3.channel.mix", data_status="Known", value={"y": 2}
    )
    stale_node["source_fingerprint_at_fill"] = "deadbeefdeadbeef"
    # L3.channel.mix in mini_governance has empty source_dependencies, so
    # it will be preserved with "no_source_dependencies" reason — not a
    # great mismatch demo. Add an extra fillable Unknown row for sanity.
    unknown_node = _node(
        dp_id="L1.position.brand", data_status="Unknown", node_name="other"
    )
    # Note: dp_id collision is OK — _filter_nodes just iterates.

    fillable, skipped = codex_prompt_gen._filter_nodes(
        [matching_node, unknown_node],
        mini_governance,
        db_path=db_path,
        ts_code="000063.SZ",
    )
    fillable_pairs = [(n["dp_id"], n.get("node_name")) for n in fillable]
    # The Known node with matching fingerprint must NOT be in fillable
    assert ("L1.position.brand", "test_node") not in fillable_pairs
    # Unknown one is still fillable
    assert ("L1.position.brand", "other") in fillable_pairs


def test_build_company_prompt_excludes_skip_route() -> None:
    """Integration: full prompt must not list a skip-routed dp_id."""

    prompt = codex_prompt_gen.build_company_prompt(
        "AI_COMPUTE", "000063.SZ", model_tier_filter="all"
    )
    # L5.is.revenue is a real dp_id but governance only has LLM routes
    # registered. It should never appear in the fillable table.
    # The string "L5.is.revenue" itself can show up as source_dependencies
    # for L0.demand.terminal — but only inside the table column. The
    # "待填字段" table rows lead with a backticked dp_id and a pipe.
    # We just check it never appears as a backticked row header at the start
    # of a fillable-table line.
    bad_rows = [
        line
        for line in prompt.splitlines()
        if line.startswith("| `L5.is.revenue` |")
    ]
    assert bad_rows == [], (
        "L5.is.revenue must not appear in the fillable governance table"
    )


# ---------------------------------------------------------------------------
# Z5 Fix 2: tier-aware evidence rule block selection.
#
# Root cause: build_industry_prompt / build_company_prompt unconditionally
# inserted CLOSED_LOOP_RULES (which forbids external URLs) into every
# prompt — even ``--model-tier web_analysis`` prompts, contradicting
# codex_fill_guide.md §2a which allows web URLs with checksum.
# ---------------------------------------------------------------------------


def _node_with_dp(dp_id: str) -> dict:
    return _node(dp_id=dp_id, data_status="Unknown")


def test_render_evidence_rules_pure_closed_loop_uses_closed_rules() -> None:
    """All fillable tiers ∈ {cheap_extract/classify/analysis} → only CLOSED_LOOP_RULES."""

    governance = {
        "data_points": {
            "L1.position.brand": {"model_tier": "analysis"},
            "L3.channel.mix": {"model_tier": "cheap_extract"},
            "L0.compete.price_war": {"model_tier": "cheap_classify"},
        }
    }
    nodes = [
        _node_with_dp("L1.position.brand"),
        _node_with_dp("L3.channel.mix"),
        _node_with_dp("L0.compete.price_war"),
    ]
    block = codex_prompt_gen._render_evidence_rules(nodes, governance)
    assert "禁止访问外部网络" in block
    assert "web_analysis 字段 — 允许 web" not in block
    assert "Tushare" in block
    assert "不能写 `url` 字段" in block


def test_render_evidence_rules_pure_web_analysis_uses_web_rules_only() -> None:
    """All fillable tiers = web_analysis → only WEB_ANALYSIS_RULES, no 禁止访问网络."""

    governance = {
        "data_points": {
            "L2.newbiz.tam": {"model_tier": "web_analysis"},
            "L3.delivery.csat": {"model_tier": "web_analysis"},
        }
    }
    nodes = [
        _node_with_dp("L2.newbiz.tam"),
        _node_with_dp("L3.delivery.csat"),
    ]
    block = codex_prompt_gen._render_evidence_rules(nodes, governance)
    assert "禁止访问外部网络" not in block
    assert "web_analysis 字段 — 允许 web" in block
    # Web-evidence schema requirements must be visible
    assert "checksum" in block
    assert "fetched_at" in block


def test_render_evidence_rules_mixed_tiers_includes_both_blocks() -> None:
    """Mixed closed-loop + web_analysis → both blocks present."""

    governance = {
        "data_points": {
            "L1.position.brand": {"model_tier": "analysis"},
            "L2.newbiz.tam": {"model_tier": "web_analysis"},
        }
    }
    nodes = [
        _node_with_dp("L1.position.brand"),
        _node_with_dp("L2.newbiz.tam"),
    ]
    block = codex_prompt_gen._render_evidence_rules(nodes, governance)
    assert "禁止访问外部网络" in block
    assert "web_analysis 字段 — 允许 web" in block


def test_render_evidence_rules_empty_falls_back_to_closed() -> None:
    """No fillable nodes → safer default is the stricter closed-loop rule."""

    block = codex_prompt_gen._render_evidence_rules(
        [], {"data_points": {}}
    )
    assert "禁止访问外部网络" in block


def test_build_company_prompt_web_analysis_tier_no_closed_loop_ban(
    tmp_path: Path,
) -> None:
    """Real integration: --model-tier web_analysis prompt for AI_COMPUTE/000063.SZ
    must NOT contain the closed-loop "禁止访问网络" ban (Z5 P1.2 root-cause
    regression guard)."""

    prompt = codex_prompt_gen.build_company_prompt(
        "AI_COMPUTE", "000063.SZ", model_tier_filter="web_analysis"
    )
    # If the prompt has any fillable web_analysis dp_ids, it must allow
    # web evidence — the closed-loop ban string must be absent.
    # We can't easily inspect the count without running list-only here,
    # but the existence of a fillable table or "没有可填字段" marker tells us
    # the prompt was generated.
    has_fillable_table = "| dp_id | model_tier" in prompt
    if has_fillable_table:
        assert "禁止访问外部网络" not in prompt, (
            "web_analysis prompt must not contain the closed-loop "
            "'禁止访问外部网络' clause"
        )
        # And it must explain web evidence schema
        assert "checksum" in prompt
        assert "fetched_at" in prompt


def test_annual_report_block_is_closed_loop_local_dp_id_only() -> None:
    """Local annual-report excerpts are SQLite facts, not web evidence."""

    nodes = [_node_with_dp("L3.region.domestic_overseas")]
    realtime = {
        "L9.disclosure.annual_report": {
            "source": "annual_report:cninfo:2025",
            "value": {
                "ar_year": 2025,
                "ar_url": "https://static.cninfo.com.cn/finalpage/x.pdf",
                "sections": {
                    "region_distribution": "境内收入 70%，境外收入 30%。",
                    "revenue_structure": "海外销售占比提升。",
                },
            },
        }
    }

    block = "\n".join(
        codex_prompt_gen._build_annual_report_block(nodes, realtime)
    )
    assert "L3.region.domestic_overseas" in block
    assert "dp_id=L9.disclosure.annual_report" in block
    assert "不要写 `url` 字段" in block
    assert "https://static.cninfo.com.cn" not in block
