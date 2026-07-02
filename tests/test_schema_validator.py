"""Tests for ``mvp20.schema_validator`` (Fix B / B2 — schema drift defence).

Covers the spec sketch:

1.  valid L1.position.market_share value → 0 errors
2.  missing required field "rank" → 1 error
3.  wrong type (rank: "first" is str not int) → 1 error
4.  unknown extra field → 1 warning (or hard error in strict mode)
5.  L3.product.portfolio products: [str] (low-thinking output) → error
    products[i] not dict
6.  validate_overlay_node on codex_low yaml L3.product.portfolio (drift)
    → catches the unknown-keys
7.  validate_overlay_node Known → runs validation; Unknown → skips
8.  Schema coverage stats are sane (10+ dp_ids covered, multiple layers)
9.  validate_value returns [] for any dp_id without schema (forward-compat)
10. Empty Optionality (value=None) is skipped
11. Optionality with empty dict is skipped
12. None as value → explicit "value is None" error
13. Non-dict value (str / list) → "value not dict" error
14. Module symbol API is stable for downstream callers
15. Integration regression: hand-crafted A/B yaml fragment matches the
    low-thinking drift pattern observed in production.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from mvp20 import schema_validator  # noqa: E402


# ---------------------------------------------------------------------------
# 1-4: validate_value happy/sad paths for L1.position.market_share
# ---------------------------------------------------------------------------


def test_market_share_valid_no_errors() -> None:
    value = {
        "rank": 2,
        "share_pct": 17.5,
        "peers": ["AMD", "Intel"],
        "trend": "up",
        "source_year": "2026",
    }
    errors = schema_validator.validate_value("L1.position.market_share", value)
    assert errors == []


def test_market_share_missing_required_rank() -> None:
    value = {"share_pct": 17.5}
    errors = schema_validator.validate_value("L1.position.market_share", value)
    assert any("rank" in e and "missing required" in e for e in errors)


def test_market_share_wrong_type_rank_string() -> None:
    value = {"rank": "first", "share_pct": 17.5}
    errors = schema_validator.validate_value("L1.position.market_share", value)
    assert any("rank" in e and "wrong type" in e for e in errors)


def test_market_share_unknown_key_is_warn_in_default_mode() -> None:
    value = {
        "rank": 1,
        "share_pct": 25.0,
        "diversification": "high",  # unknown key
    }
    errors = schema_validator.validate_value("L1.position.market_share", value)
    warns = [e for e in errors if e.startswith("[warn]")]
    assert any("diversification" in w for w in warns)


def test_market_share_unknown_key_is_hard_error_in_strict_mode() -> None:
    value = {
        "rank": 1,
        "share_pct": 25.0,
        "diversification": "high",
    }
    errors = schema_validator.validate_value(
        "L1.position.market_share", value, strict=True
    )
    hard = [e for e in errors if not e.startswith("[warn]")]
    assert any("diversification" in e and "not in schema" in e for e in hard)


def test_l1_tag_schema_requires_tags_only() -> None:
    errors = schema_validator.validate_value(
        "L1.role.tag",
        {"tags": ["龙头供应商"], "role": "leader"},
        strict=True,
    )
    assert any("unknown field 'role'" in e for e in errors)


def test_growth_rank_schema_rejects_legacy_keys_in_strict_mode() -> None:
    errors = schema_validator.validate_value(
        "L1.position.growth_rank",
        {
            "rank": None,
            "share_pct": None,
            "trend": "modest_growth",
            "source_year": "2026Q1",
            "market_size_unit": None,
            "growth_pct": 10.2,
            "rank_bucket": "top",
        },
        strict=True,
    )
    assert any("unknown field 'growth_pct'" in e for e in errors)
    assert any("unknown field 'rank_bucket'" in e for e in errors)


# ---------------------------------------------------------------------------
# 5: L3.product.portfolio drift — products: [str] instead of [{name, ...}]
# ---------------------------------------------------------------------------


def test_l3_portfolio_products_as_list_of_str_caught() -> None:
    """The low-thinking model emits ``products: ["GPU", "Networking"]``
    which is unparsable by the aggregator. This must be caught."""

    value = {"products": ["GPU", "Networking", "Auto"]}
    errors = schema_validator.validate_value("L3.product.portfolio", value)
    assert any(
        "products[" in e and "not dict" in e for e in errors
    ), f"expected products[i] not dict error, got: {errors}"


def test_l3_portfolio_products_proper_shape_passes() -> None:
    value = {
        "products": [
            {"name": "GPU accelerators", "revenue_pct": 75.0},
            {"name": "Networking", "revenue_pct": 12.0},
            {"name": "Automotive", "revenue_pct": None},
        ],
        "notes": "Q4 2026 breakdown",
    }
    errors = schema_validator.validate_value("L3.product.portfolio", value)
    assert errors == []


# ---------------------------------------------------------------------------
# 6: validate_overlay_node on the codex_low minimax-style drift case
# ---------------------------------------------------------------------------


def test_overlay_node_minimax_low_thinking_drift_caught() -> None:
    """Real-world A/B observation: minimax (low-thinking) emitted the
    L3.product.portfolio value with invented keys ``product_categories``,
    ``portfolio_balance``, ``evidence_summary`` instead of ``products``.

    The schema-validator must flag this as drift. The legitimate
    ``evidence_summary`` is in the optional set so it doesn't false-positive.
    """

    node = {
        "dp_id": "L3.product.portfolio",
        "data_status": "Known",
        "value": {
            "product_categories": ["无线基站", "光传输", "数据通信"],
            "portfolio_balance": "运营商业务为主",
            "evidence_summary": "产品线覆盖完整",
        },
    }
    errors = schema_validator.validate_overlay_node(node)
    # Missing required "products" + unknown keys must both surface.
    assert any(
        "products" in e and "missing required" in e for e in errors
    ), f"expected missing products field, got: {errors}"
    unknown_warns = [
        e
        for e in errors
        if "unknown field" in e
        and ("product_categories" in e or "portfolio_balance" in e)
    ]
    assert unknown_warns, (
        f"expected drift warnings for product_categories / portfolio_balance, "
        f"got: {errors}"
    )


# ---------------------------------------------------------------------------
# 7: validate_overlay_node status gating
# ---------------------------------------------------------------------------


def test_overlay_node_known_runs_validation() -> None:
    node = {
        "dp_id": "L1.position.market_share",
        "data_status": "Known",
        "value": {"share_pct": 5.5},  # missing required "rank"
    }
    errors = schema_validator.validate_overlay_node(node)
    assert any("rank" in e for e in errors)


def test_overlay_node_unknown_skips_validation() -> None:
    """Unknown nodes legitimately have value=None; the validator must
    not flag them — that's the whole point of the Unknown status."""

    node = {
        "dp_id": "L1.position.market_share",
        "data_status": "Unknown",
        "value": None,
    }
    errors = schema_validator.validate_overlay_node(node)
    assert errors == []


def test_overlay_node_na_with_correct_policy_skips_validation() -> None:
    """N/A node with correct ``not_applicable_remove`` policy passes
    value-shape validation (the compiler-parity check is satisfied)."""

    node = {
        "dp_id": "L1.position.market_share",
        "data_status": "N/A",
        "missing_policy": "not_applicable_remove",
        "value": None,
    }
    assert schema_validator.validate_overlay_node(node) == []


def test_overlay_node_na_with_wrong_policy_errors() -> None:
    """Compiler-parity rule: N/A status REQUIRES
    ``missing_policy=not_applicable_remove`` or compile-overlays rejects."""

    node = {
        "dp_id": "L1.position.market_share",
        "data_status": "N/A",
        "missing_policy": "unknown_reduce_confidence",  # wrong
        "value": None,
    }
    errors = schema_validator.validate_overlay_node(node)
    assert any("not_applicable_remove" in e for e in errors), errors


def test_overlay_node_unknown_required_errors() -> None:
    """Compiler-parity rule: ``required`` node left Unknown is a hard
    error — required slots must always be filled (or downgraded)."""

    node = {
        "dp_id": "L1.position.market_share",
        "data_status": "Unknown",
        "required_level": "required",
        "value": None,
    }
    errors = schema_validator.validate_overlay_node(node)
    assert any("required" in e and "Unknown" in e for e in errors), errors


def test_overlay_node_unknown_conditional_required_needs_reason() -> None:
    """Compiler-parity rule: ``conditional_required`` Unknown nodes must
    explain themselves via ``missing_reason``."""

    node_missing = {
        "dp_id": "L1.position.market_share",
        "data_status": "Unknown",
        "required_level": "conditional_required",
        "missing_reason": None,
        "value": None,
    }
    errors = schema_validator.validate_overlay_node(node_missing)
    assert any("missing_reason" in e for e in errors), errors

    node_with_reason = {
        "dp_id": "L1.position.market_share",
        "data_status": "Unknown",
        "required_level": "conditional_required",
        "missing_reason": "annual report didn't disclose 排名",
        "value": None,
    }
    assert schema_validator.validate_overlay_node(node_with_reason) == []


def test_overlay_node_inactive_skips_validation() -> None:
    node = {
        "dp_id": "L0.compete.price_war",
        "data_status": "Inactive",
        "value": None,
    }
    assert schema_validator.validate_overlay_node(node) == []


def test_overlay_node_empty_optionality_skips_validation() -> None:
    """Optionality with value=None or empty dict isn't yet filled —
    skip rather than producing spurious 'missing required' errors."""

    node_none = {
        "dp_id": "L2.newbiz.tam",
        "data_status": "Optionality",
        "value": None,
    }
    assert schema_validator.validate_overlay_node(node_none) == []

    node_empty = {
        "dp_id": "L2.newbiz.tam",
        "data_status": "Optionality",
        "value": {},
    }
    assert schema_validator.validate_overlay_node(node_empty) == []


def test_overlay_node_filled_optionality_with_split_passes() -> None:
    """Filled Optionality with BOTH ``current_contribution`` and
    ``future_option_value`` keys passes the compiler-parity rule."""

    node = {
        "dp_id": "L2.newbiz.tam",
        "data_status": "Optionality",
        "value": {
            "current_contribution": {"revenue_share_pct": 3.2},
            "future_option_value": {
                "tam_usd_or_cny": 1e10,
                "tam_year": 2027,
                "source": "company filing",
            },
        },
    }
    errors = schema_validator.validate_overlay_node(node)
    # No hard errors expected — Optionality outer-dict layer accepts the
    # split shape; nested current_contribution / future_option_value are
    # free-form sub-dicts (not in DP_SCHEMA), so value-shape validator
    # treats unknown keys as warn at most.
    hard = [e for e in errors if not e.startswith("[warn]")]
    assert hard == [], f"unexpected hard errors: {hard}"


def test_overlay_node_filled_optionality_missing_future_errors() -> None:
    """Compiler-parity rule: filled Optionality with ONLY
    ``current_contribution`` (no ``future_option_value``) is rejected."""

    node = {
        "dp_id": "L2.newbiz.tam",
        "data_status": "Optionality",
        "value": {
            "tam_usd_or_cny": 1e10,
            "tam_year": 2027,
            "source": "company filing",
            "current_contribution": {"some": "thing"},  # missing future_option_value
        },
    }
    errors = schema_validator.validate_overlay_node(node)
    assert any(
        "current_contribution" in e and "future_option_value" in e
        for e in errors
    ), errors


def test_overlay_node_filled_optionality_missing_current_errors() -> None:
    """Compiler-parity rule: filled Optionality with ONLY
    ``future_option_value`` (no ``current_contribution``) is rejected."""

    node = {
        "dp_id": "L2.newbiz.tam",
        "data_status": "Optionality",
        "value": {
            "future_option_value": {"tam_year": 2027},
        },
    }
    errors = schema_validator.validate_overlay_node(node)
    assert any(
        "current_contribution" in e and "future_option_value" in e
        for e in errors
    ), errors


def test_overlay_node_filled_optionality_non_dict_value_errors() -> None:
    """Compiler-parity rule: Optionality ``value`` that's not a dict
    (e.g. raw scalar 0.5 or a list) is rejected."""

    node = {
        "dp_id": "L2.newbiz.tam",
        "data_status": "Optionality",
        "value": 0.5,
    }
    errors = schema_validator.validate_overlay_node(node)
    assert any("dict" in e for e in errors), errors


# ---------------------------------------------------------------------------
# 8-9: misc API surface
# ---------------------------------------------------------------------------


def test_schema_coverage_summary() -> None:
    cov = schema_validator.schema_coverage()
    assert cov["total"] >= 30, (
        f"expected at least 30 dp_ids covered, got {cov['total']}"
    )
    # Multiple layers represented.
    for layer in ("L0", "L1", "L2", "L3", "L4", "L5"):
        assert cov.get(layer, 0) > 0, f"layer {layer} not covered"


def test_unregistered_dp_id_returns_no_errors() -> None:
    """Forward-compat: a dp_id without registered schema must not
    produce errors. This lets new dp_ids land without coordination."""

    assert schema_validator.validate_value("L99.fake.thing", {"foo": 1}) == []


def test_none_value_is_explicit_error() -> None:
    errors = schema_validator.validate_value(
        "L1.position.market_share", None
    )
    assert any("value is None" in e for e in errors)


def test_non_dict_value_is_error() -> None:
    errors = schema_validator.validate_value(
        "L1.position.market_share", "rank=1"
    )
    assert any("not dict" in e and "str" in e for e in errors)


def test_module_public_api_is_stable() -> None:
    """Downstream callers (apply_yaml_patch / verify_overlay_closed_loop)
    rely on these names."""

    assert hasattr(schema_validator, "DP_SCHEMA")
    assert callable(schema_validator.validate_value)
    assert callable(schema_validator.validate_overlay_node)
    assert callable(schema_validator.schema_coverage)


def test_natural_language_schema_key_residue_warns() -> None:
    value = {
        "rank": None,
        "share_pct": None,
        "trend": "decline",
        "source_year": "2026Q1",
        "market_size_unit": None,
        "notes": "rank 和 share_pct 因缺少本地证据留空。",
    }

    errors = schema_validator.validate_value("L1.position.growth_rank", value)

    assert any(e.startswith("[warn]") and "schema/enum residue" in e for e in errors)


def test_stock_attr_valuation_guardrail_text_warns() -> None:
    value = {
        "tags": ["估值修复"],
        "notes": "未把估值倍数、分位数或百分位数字写入标签。",
    }

    errors = schema_validator.validate_value("L1.stock_attr.tags", value)

    assert any(e.startswith("[warn]") and "valuation guardrail" in e for e in errors)


def test_channel_mix_chinese_trend_warns() -> None:
    value = {
        "direct_pct": 100.0,
        "distributor_pct": 0.0,
        "ecommerce_pct": 0.0,
        "others_pct": 0.0,
        "trend": "直销占主导",
    }

    errors = schema_validator.validate_value("L3.channel.mix", value)

    assert any(e.startswith("[warn]") and "trend must be enum-like" in e for e in errors)


def test_channel_mix_all_null_percentages_with_trend_warns() -> None:
    value = {
        "direct_pct": None,
        "distributor_pct": None,
        "ecommerce_pct": None,
        "others_pct": None,
        "trend": "direct_sales_dominant",
    }

    errors = schema_validator.validate_value("L3.channel.mix", value)

    assert any(
        e.startswith("[warn]") and "trend must be null when all channel percentages are null" in e
        for e in errors
    )


# ---------------------------------------------------------------------------
# Item-schema enforcement on nested arrays
# ---------------------------------------------------------------------------


def test_segments_item_schema_wrong_type() -> None:
    """L3.customer.segment_mix.segments[i].revenue_pct must be number-or-null."""

    value = {
        "segments": [
            {"name": "运营商", "revenue_pct": "70%"},  # str, not number
        ],
        "concentration_top5_pct": 80.0,
    }
    errors = schema_validator.validate_value(
        "L3.customer.segment_mix", value
    )
    assert any(
        "segments[0].revenue_pct" in e and "wrong type" in e
        for e in errors
    )


def test_cash_contrib_segments_proper_shape() -> None:
    value = {
        "segments": [
            {
                "name": "GPU",
                "revenue_pct": 75.0,
                "gross_margin_pct": 78.0,
                "cash_contrib_pct": 85.0,
            },
            {
                "name": "Networking",
                "revenue_pct": 12.0,
                "gross_margin_pct": None,
                "cash_contrib_pct": None,
            },
        ]
    }
    assert (
        schema_validator.validate_value("L2.segment.cash_contrib", value)
        == []
    )


# ---------------------------------------------------------------------------
# Integration: replay the production drift case end-to-end
# ---------------------------------------------------------------------------


def test_codex_high_vs_low_drift_rate_demonstration() -> None:
    """Synthetic before/after demonstrating high-thinking vs low-thinking
    drift detection. The high-thinking case (codex_000063 analysis run)
    follows the spec; the low-thinking case (minimax analysis run)
    drifts. Schema validator catches one and not the other."""

    high_value = {
        "products": [
            {"name": "无线通信产品", "revenue_pct": None},
            {"name": "有线交换", "revenue_pct": None},
        ],
        "notes": "产品组合来自本地公司业务描述，未披露分产品收入占比。",
    }
    low_value = {
        "product_categories": ["无线基站", "光传输", "数据通信"],
        "portfolio_balance": "运营商业务为主",
        "evidence_summary": "产品线覆盖完整",
    }

    high_errors = schema_validator.validate_value(
        "L3.product.portfolio", high_value
    )
    low_errors = schema_validator.validate_value(
        "L3.product.portfolio", low_value
    )

    assert high_errors == [], (
        f"high-thinking output should pass schema, got: {high_errors}"
    )
    assert low_errors, (
        "low-thinking output must trigger schema errors, got none"
    )
    # The signature drift: low-thinking emits product_categories key.
    assert any("product_categories" in e for e in low_errors)
    # AND it's missing required products list.
    assert any("products" in e and "missing required" in e for e in low_errors)


# ---------------------------------------------------------------------------
# Provenance hygiene (data_source vs data_status)
# ---------------------------------------------------------------------------


def test_unknown_node_with_derived_data_source_fails_strict_only() -> None:
    """Review #6: Unknown/Unavailable nodes carry value=None, so a
    ``*_derived`` data_source misattributes a derivation that does not
    exist. Strict (writer-gate) mode rejects it; default mode stays lenient
    so existing overlays with the legacy pattern still load."""

    node = {
        "dp_id": "L4.eff.capacity_utilization",
        "data_status": "Unknown",
        "required_level": "conditional_required",
        "missing_reason": "candidate_unavailable",
        "data_source": "llm_derived",
        "value": None,
    }
    strict_errors = schema_validator.validate_overlay_node(node, strict=True)
    assert any("data_source" in e for e in strict_errors), strict_errors
    assert schema_validator.validate_overlay_node(node, strict=False) == []

    # Null provenance on an Unknown node is the approved shape.
    node["data_source"] = None
    assert schema_validator.validate_overlay_node(node, strict=True) == []

    # Non-derived labels (raw feed names etc.) are untouched by the rule.
    node["data_source"] = "tushare"
    node["data_status"] = "Unavailable"
    assert schema_validator.validate_overlay_node(node, strict=True) == []
