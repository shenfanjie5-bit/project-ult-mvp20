"""Validate that an LLM-emitted ``value`` conforms to its dp_id's
``output_schema`` declared in ``docs/data_sources/llm_derived_nodes.md``
(Sections 3 + 4 + 4a + 4b).

Fix B (B2): catch schema drift before it lands in the overlay yaml. The
codex_low/minimax A/B run showed that low-thinking models often invent
keys (``product_categories`` / ``portfolio_balance`` / ``evidence_summary``)
instead of the spec'd shape (``products: [{name, revenue_pct}]``). The
downstream aggregator depends on the spec'd keys, so any drift quietly
corrupts the score pipeline.

Used by:
    * ``scripts/apply_yaml_patch.py`` — reject (or warn on) patches with
      schema violations via ``--strict-schema``.
    * ``scripts/verify_overlay_closed_loop.py`` — soft-warn on schema
      drift via ``--check-schema``. Never auto-demotes (the value may
      still be useful, just shape-different).

Coverage strategy
-----------------
Hand-curated minimal schema per LLM dp_id, extracted from
``llm_derived_nodes.md`` Sections 3+4+4a+4b. Each entry declares:

    {
        "required": {key: type_or_tuple, ...},
        "optional": {key: type_or_tuple, ...},
        # optional, only for dp_ids with array-of-dict shape:
        "<list_key>_item_schema": {field: type_or_tuple, ...},
    }

Partial coverage is fine for v1 — when a dp_id is absent from
``DP_SCHEMA``, ``validate_value`` returns ``[]`` (no errors). New schemas
can be added incrementally as the team observes new drift patterns.

Type model
----------
* Bare types (``str`` / ``int`` / ``float`` / ``list`` / ``dict``) match
  Python ``isinstance``.
* Tuples are unions — ``(int, type(None))`` means int-or-null.
* ``bool`` is intentionally **not** included in the int-union default;
  Python ``bool`` is a subclass of ``int`` so you'd have to filter
  explicitly if a field must reject booleans. For now no schema relies
  on that distinction.

Output codes
------------
``validate_value`` and ``validate_overlay_node`` return a list of
human-readable error strings. Soft warnings are prefixed with
``[warn]`` so callers can distinguish hard errors from advisory ones
(strict mode promotes ``[warn]`` to hard errors).
"""

from __future__ import annotations

from typing import Any


# Type aliases — kept verbose so the schemas read like the docs do.
_INT_OR_NULL = (int, type(None))
_FLOAT_OR_NULL = (float, int, type(None))  # accept int where float expected
_NUM_OR_NULL = (float, int, type(None))
_STR_OR_NULL = (str, type(None))


# ---------------------------------------------------------------------------
# Schema registry
# ---------------------------------------------------------------------------
#
# Order roughly mirrors llm_derived_nodes.md (Section 3 industry → Section 4
# company → 4a Group A → 4b Group C). Comments cite the source line so the
# next reader can cross-check quickly.


DP_SCHEMA: dict[str, dict[str, Any]] = {
    # -------------------------------------------------------------------
    # Section 3 — Industry-level L0 fields (14 conditional_required)
    # llm_derived_nodes.md §3 table; outputs are typically a yoy_pct +
    # trend pair, sometimes with absolute_pct / delta. Schemas there are
    # described prose-style; we capture the canonical superset shape.
    # -------------------------------------------------------------------
    "L0.demand.terminal": {
        "required": {"yoy_pct": _NUM_OR_NULL, "trend": _STR_OR_NULL},
        "optional": {"notes": str, "magnitude": _STR_OR_NULL,
                     "evidence_summary": str},
    },
    "L0.demand.user_count": {
        "required": {"yoy_pct": _NUM_OR_NULL, "trend": _STR_OR_NULL},
        "optional": {"notes": str, "evidence_summary": str},
    },
    "L0.demand.frequency": {
        "required": {"yoy_pct": _NUM_OR_NULL, "trend": _STR_OR_NULL},
        "optional": {"notes": str},
    },
    "L0.demand.penetration": {
        "required": {"absolute_pct": _NUM_OR_NULL, "delta_pct": _NUM_OR_NULL},
        "optional": {"trend": _STR_OR_NULL, "notes": str},
    },
    "L0.demand.replacement": {
        "required": {"months": _NUM_OR_NULL, "trend": _STR_OR_NULL},
        "optional": {"notes": str},
    },
    "L0.supply.capacity": {
        "required": {"yoy_pct": _NUM_OR_NULL, "trend": _STR_OR_NULL},
        "optional": {"notes": str, "magnitude": _STR_OR_NULL},
    },
    "L0.supply.channel_service": {
        "required": {"qualitative": _STR_OR_NULL, "magnitude": _STR_OR_NULL},
        "optional": {"trend": _STR_OR_NULL, "notes": str},
    },
    "L0.supply.chain_eff": {
        "required": {"qualitative": _STR_OR_NULL, "magnitude": _STR_OR_NULL},
        "optional": {"trend": _STR_OR_NULL, "notes": str},
    },
    "L0.price.discount": {
        "required": {"yoy_delta_pct": _NUM_OR_NULL, "trend": _STR_OR_NULL},
        "optional": {"notes": str},
    },
    "L0.price.pricing_power": {
        "required": {"strength": str, "trend": _STR_OR_NULL},
        "optional": {"notes": str, "evidence_summary": str},
    },
    "L0.cost.rent": {
        "required": {"yoy_pct": _NUM_OR_NULL, "trend": _STR_OR_NULL},
        "optional": {"notes": str},
    },
    "L0.cost.cac": {
        "required": {"yoy_pct": _NUM_OR_NULL, "trend": _STR_OR_NULL},
        "optional": {"notes": str},
    },
    "L0.compete.price_war": {
        "required": {
            "active": (bool, type(None)),
            "intensity": _STR_OR_NULL,
        },
        "optional": {"duration_months": _NUM_OR_NULL, "notes": str,
                     "evidence_summary": str},
    },
    "L0.compete.new_entrant": {
        "required": {"count": _INT_OR_NULL, "threat_level": _STR_OR_NULL},
        "optional": {"notes": str, "evidence_summary": str},
    },

    # -------------------------------------------------------------------
    # Section 3a — X5 Group B industry add-ons (5 conditional_required).
    # Schemas verbatim from §3a table.
    # -------------------------------------------------------------------
    "L0.price.contract_spot": {
        "required": {
            "contract_pct": _FLOAT_OR_NULL,
            "spot_pct": _FLOAT_OR_NULL,
            "spread_pct": _FLOAT_OR_NULL,
            "trend": _STR_OR_NULL,
        },
        "optional": {"notes": str},
    },
    "L0.price.product_asp": {
        "required": {
            "asp_value": _FLOAT_OR_NULL,
            "asp_unit": _STR_OR_NULL,
            "yoy_pct": _FLOAT_OR_NULL,
            "qoq_pct": _FLOAT_OR_NULL,
            "trend": _STR_OR_NULL,
        },
        "optional": {"notes": str},
    },
    "L0.supply.inventory": {
        "required": {
            "inventory_days": _FLOAT_OR_NULL,
            "vs_normal_pct": _FLOAT_OR_NULL,
            "channel_inventory_state": _STR_OR_NULL,
            "trend": _STR_OR_NULL,
        },
        "optional": {"notes": str},
    },
    "L0.sentiment.social": {
        "required": {
            "sentiment_score": _FLOAT_OR_NULL,
            "volume_idx": _FLOAT_OR_NULL,
        },
        "optional": {
            "top_themes": list,
            "trend": _STR_OR_NULL,
            "evidence_quality": str,
            "notes": str,
        },
    },

    # -------------------------------------------------------------------
    # Section 4.1 — L1-L2 company positioning soft-metrics
    # -------------------------------------------------------------------
    "L1.position.channel_edge": {
        "required": {"strength": str},
        "optional": {
            "components": list,
            "peers_comparison": dict,
            "evidence_summary": str,
        },
    },
    "L1.position.stickiness": {
        "required": {
            "retention_rate": _FLOAT_OR_NULL,
            "switching_cost": _STR_OR_NULL,
        },
        "optional": {"churn_signals": list, "evidence_summary": str},
    },
    "L2.newbiz.tam": {
        "required": {
            "tam_usd_or_cny": _NUM_OR_NULL,
            "tam_year": _INT_OR_NULL,
            "source": _STR_OR_NULL,
        },
        "optional": {"notes": str, "evidence_summary": str},
    },
    "L2.newbiz.uncertainty": {
        "required": {"level": str},
        "optional": {
            "factors": list,
            "catalyst_required": list,
            "evidence_summary": str,
        },
    },

    # -------------------------------------------------------------------
    # Section 4.2 — L3 product/customer/channel/region
    # -------------------------------------------------------------------
    "L3.product.lifecycle": {
        "required": {
            "phase": str,
            "competitive_score": _NUM_OR_NULL,
        },
        "optional": {"notes": str, "evidence_summary": str},
    },
    "L3.customer.segment_mix": {
        "required": {
            "segments": list,
            "concentration_top5_pct": _FLOAT_OR_NULL,
        },
        "optional": {"notes": str},
        "segments_item_schema": {
            "name": str,
            "revenue_pct": _FLOAT_OR_NULL,
        },
    },
    "L3.channel.mix": {
        "required": {
            "direct_pct": _FLOAT_OR_NULL,
            "distributor_pct": _FLOAT_OR_NULL,
            "ecommerce_pct": _FLOAT_OR_NULL,
            "others_pct": _FLOAT_OR_NULL,
        },
        "optional": {"notes": str, "trend": _STR_OR_NULL},
    },
    "L3.region.tier_mix": {
        "required": {
            "tier1_pct": _FLOAT_OR_NULL,
            "tier2_pct": _FLOAT_OR_NULL,
            "tier3_pct": _FLOAT_OR_NULL,
            "overseas_pct": _FLOAT_OR_NULL,
        },
        "optional": {"notes": str},
    },
    "L3.delivery.lead_time": {
        "required": {
            "lead_time_days": _NUM_OR_NULL,
            "on_time_rate": _FLOAT_OR_NULL,
            "trend": _STR_OR_NULL,
        },
        "optional": {"notes": str},
    },
    "L3.delivery.csat": {
        "required": {
            "nps_or_csat": _FLOAT_OR_NULL,
            "complaint_rate": _FLOAT_OR_NULL,
            "trend": _STR_OR_NULL,
        },
        "optional": {"notes": str, "evidence_summary": str},
    },

    # -------------------------------------------------------------------
    # Section 4.3 — L4 company operational soft-metrics
    # -------------------------------------------------------------------
    "L4.volume.foot_traffic": {
        "required": {"yoy_pct": _FLOAT_OR_NULL},
        "optional": {"monthly_trend": list, "notes": str},
    },
    "L4.volume.frequency": {
        "required": {
            "frequency_per_user": _FLOAT_OR_NULL,
            "yoy_delta_pct": _FLOAT_OR_NULL,
        },
        "optional": {"notes": str},
    },
    "L4.price.subscription": {
        "required": {"tiers": list, "trend": _STR_OR_NULL},
        "optional": {"notes": str},
        "tiers_item_schema": {
            "name": str,
            "price": _NUM_OR_NULL,
            "currency": _STR_OR_NULL,
        },
    },
    "L4.price.discount": {
        "required": {
            "avg_discount_pct": _FLOAT_OR_NULL,
            "trend": _STR_OR_NULL,
        },
        "optional": {
            "season_high": (bool, type(None)),
            "notes": str,
        },
    },
    "L4.eff.capacity_utilization": {
        "required": {
            "utilization_pct": _FLOAT_OR_NULL,
            "trend": _STR_OR_NULL,
        },
        "optional": {"bottleneck": _STR_OR_NULL, "notes": str},
    },
    "L4.eff.conversion_retention": {
        "required": {
            "conversion_pct": _FLOAT_OR_NULL,
            "retention_30d": _FLOAT_OR_NULL,
            "repurchase_rate": _FLOAT_OR_NULL,
            "trend": _STR_OR_NULL,
        },
        "optional": {"notes": str},
    },
    "L4.share.customer_channel": {
        "required": {
            "customer_share_top5": _FLOAT_OR_NULL,
            "channel_share": _FLOAT_OR_NULL,
            "region_share": _FLOAT_OR_NULL,
            "trend": _STR_OR_NULL,
        },
        "optional": {"notes": str},
    },

    # -------------------------------------------------------------------
    # Section 4.4 — L5 financial off-disclosure signals
    # -------------------------------------------------------------------
    "L5.surprise.buy_whisper": {
        "required": {
            "whisper_eps": _FLOAT_OR_NULL,
            "whisper_revenue": _NUM_OR_NULL,
            "vs_consensus_pct": _FLOAT_OR_NULL,
            "source_count": _INT_OR_NULL,
        },
        "optional": {"notes": str, "evidence_summary": str},
    },

    # -------------------------------------------------------------------
    # Section 4a — X5 Group A company portrait (16 dp_ids)
    # -------------------------------------------------------------------
    "L1.position.market_share": {
        "required": {
            "rank": _INT_OR_NULL,
            "share_pct": _FLOAT_OR_NULL,
        },
        "optional": {
            "peers": list,
            "trend": _STR_OR_NULL,
            "source_year": _STR_OR_NULL,
            "market_size_unit": _STR_OR_NULL,
            "evidence_summary": str,
            "notes": str,
        },
    },
    "L1.position.brand": {
        "required": {"tier": _STR_OR_NULL},
        "optional": {
            "category": _STR_OR_NULL,
            "qualitative_signals": list,
            "evidence_summary": str,
            "notes": str,
        },
    },
    "L1.position.tech_barrier": {
        "required": {
            "moat_score": _NUM_OR_NULL,
        },
        "optional": {
            "patent_count_known": _INT_OR_NULL,
            "key_tech": list,
            "rd_intensity_pct": _FLOAT_OR_NULL,
            "evidence_summary": str,
            "notes": str,
        },
    },
    "L1.position.cost_edge": {
        "required": {"duration": str},
        "optional": {
            "vs_peers_gp_pct": _FLOAT_OR_NULL,
            "drivers": list,
            "evidence_summary": str,
            "notes": str,
        },
    },
    "L1.position.pricing_power": {
        "required": {"strength": str},
        "optional": {
            "asp_yoy_pct": _FLOAT_OR_NULL,
            "switching_cost": _STR_OR_NULL,
            "evidence": list,
            "evidence_summary": str,
            "notes": str,
        },
    },
    "L2.segment.cash_contrib": {
        "required": {"segments": list},
        "optional": {"notes": str, "evidence_summary": str},
        "segments_item_schema": {
            "name": str,
            "revenue_pct": _FLOAT_OR_NULL,
            "gross_margin_pct": _FLOAT_OR_NULL,
            "cash_contrib_pct": _FLOAT_OR_NULL,
        },
    },
    "L2.segment.industry_exposure": {
        "required": {"exposures": list},
        "optional": {
            "cyclical_sensitivity": _STR_OR_NULL,
            "notes": str,
            "evidence_summary": str,
        },
        "exposures_item_schema": {
            "industry_id": str,
            "weight_pct": _FLOAT_OR_NULL,
        },
    },
    "L2.segment.compete_landscape": {
        "required": {"competitive_intensity": str},
        "optional": {
            "top_peers": list,
            "top3_share_pct": _FLOAT_OR_NULL,
            "evidence_summary": str,
            "notes": str,
        },
    },
    "L2.segment.business_risk": {
        "required": {"risk_factors": list},
        "optional": {
            "net_risk": _STR_OR_NULL,
            "evidence_summary": str,
            "notes": str,
        },
        "risk_factors_item_schema": {
            "type": str,
            "severity": str,
            "rationale": _STR_OR_NULL,
        },
    },
    "L2.newbiz.commercialization": {
        "required": {"stage": str},
        "optional": {
            "traction_signals": list,
            "rev_share_pct": _FLOAT_OR_NULL,
            "current_contribution": (dict, type(None)),
            "future_option_value": (dict, type(None)),
            "evidence_summary": str,
            "notes": str,
        },
    },
    "L2.newbiz.revenue_contrib": {
        "required": {"revenue_pct": _FLOAT_OR_NULL},
        "optional": {
            "qoq_growth_pct": _FLOAT_OR_NULL,
            "current_contribution": (dict, type(None)),
            "future_option_value": (dict, type(None)),
            "evidence_summary": str,
            "notes": str,
        },
    },
    "L2.newbiz.valuation_contrib": {
        "required": {"est_valuation_contribution_pct": _FLOAT_OR_NULL},
        "optional": {
            "method": _STR_OR_NULL,
            "current_contribution": (dict, type(None)),
            "future_option_value": (dict, type(None)),
            "notes": str,
            "evidence_summary": str,
        },
    },
    "L3.customer.solvency": {
        "required": {"top_customers_solvency": list},
        "optional": {
            "ar_concentration_risk": _STR_OR_NULL,
            "evidence_summary": str,
            "notes": str,
        },
        "top_customers_solvency_item_schema": {
            "name_proxy": str,
            "credit_signal": str,
        },
    },
    "L3.channel.overseas": {
        "required": {"overseas_revenue_pct": _FLOAT_OR_NULL},
        "optional": {
            "key_markets": list,
            "localization_stage": _STR_OR_NULL,
            "evidence_summary": str,
            "notes": str,
        },
    },
    "L3.region.key_risk": {
        "required": {"key_region": _STR_OR_NULL, "risk_type": _STR_OR_NULL},
        "optional": {
            "severity": _STR_OR_NULL,
            "exposure_pct": _FLOAT_OR_NULL,
            "evidence_summary": str,
            "notes": str,
        },
    },
    "L3.delivery.capacity_supply": {
        "required": {"supplier_concentration": _STR_OR_NULL},
        "optional": {
            "capacity_utilization_pct": _FLOAT_OR_NULL,
            "bottleneck": _STR_OR_NULL,
            "evidence_summary": str,
            "notes": str,
        },
    },

    # -------------------------------------------------------------------
    # Section 4b — X5 Group C L4 operational soft-metrics (6 dp_ids)
    # -------------------------------------------------------------------
    "L4.price.asp_aov_arpu": {
        "required": {"metric_kind": str, "value": _NUM_OR_NULL},
        "optional": {
            "currency": _STR_OR_NULL,
            "yoy_pct": _FLOAT_OR_NULL,
            "trend": _STR_OR_NULL,
            "notes": str,
            "evidence_summary": str,
        },
    },
    "L4.price.pricing_power": {
        "required": {"strength": str},
        "optional": {
            "recent_price_adjustment": _STR_OR_NULL,
            "customer_pushback": _STR_OR_NULL,
            "evidence_summary": str,
            "notes": str,
        },
    },
    "L4.price.elasticity": {
        "required": {"elasticity": _FLOAT_OR_NULL},
        "optional": {
            "estimation_method": _STR_OR_NULL,
            "notes": str,
            "evidence_summary": str,
        },
    },
    "L4.cost.cac_production": {
        "required": {"cac_or_unit_cost": _FLOAT_OR_NULL},
        "optional": {
            "trend": _STR_OR_NULL,
            "drivers": list,
            "evidence_summary": str,
            "notes": str,
        },
    },
    "L4.cost.rent_energy_logistics": {
        "required": {},
        "optional": {
            "rent_yoy_pct": _FLOAT_OR_NULL,
            "energy_yoy_pct": _FLOAT_OR_NULL,
            "logistics_yoy_pct": _FLOAT_OR_NULL,
            "trend": _STR_OR_NULL,
            "notes": str,
            "evidence_summary": str,
        },
    },
    "L4.eff.store_labor": {
        "required": {},
        "optional": {
            "revenue_per_employee": _FLOAT_OR_NULL,
            "revenue_per_store": _FLOAT_OR_NULL,
            "yoy_pct": _FLOAT_OR_NULL,
            "trend": _STR_OR_NULL,
            "notes": str,
            "evidence_summary": str,
        },
    },

    # -------------------------------------------------------------------
    # Extras observed in the codebase / A/B test (not in §3-§4b directly
    # but registered in governance + frequently emitted by codex). The
    # L3.product.portfolio schema was the original schema-drift trigger
    # (low-thinking model emits [str] instead of [{name, revenue_pct}]).
    # -------------------------------------------------------------------
    "L3.product.portfolio": {
        "required": {"products": list},
        "optional": {
            "notes": str,
            "evidence_summary": str,
        },
        "products_item_schema": {
            "name": str,
            "revenue_pct": _FLOAT_OR_NULL,
        },
    },
    "L3.product.margin_mix": {
        "required": {},
        "optional": {
            "gross_margin_pct": _FLOAT_OR_NULL,
            "margin_tier": _STR_OR_NULL,
            "product_margin_split": list,
            "notes": str,
            "evidence_summary": str,
        },
        "product_margin_split_item_schema": {
            "product": _STR_OR_NULL,
            "gross_margin_pct": _FLOAT_OR_NULL,
        },
    },
    "L3.customer.concentration": {
        "required": {},
        "optional": {
            "top5_revenue_pct": _FLOAT_OR_NULL,
            "top10_revenue_pct": _FLOAT_OR_NULL,
            "concentration_trend": _STR_OR_NULL,
            "notes": str,
            "evidence_summary": str,
        },
    },
}


# ---------------------------------------------------------------------------
# Core validation
# ---------------------------------------------------------------------------


def _type_name(t: Any) -> str:
    """Pretty-print a type / type-tuple for error messages."""

    if isinstance(t, tuple):
        return "|".join(_type_name(x) for x in t)
    if t is type(None):
        return "null"
    return getattr(t, "__name__", str(t))


def _check_type(value: Any, expected: Any) -> bool:
    """isinstance with our union-tuple convention."""

    expected_tuple = expected if isinstance(expected, tuple) else (expected,)
    # Reject `bool` for numeric-required slots to avoid the python
    # quirk where True/False are ints. None values are still allowed
    # via the type(None) entry.
    if value is True or value is False:
        # Only accept booleans when bool was explicitly listed.
        if bool in expected_tuple:
            return True
        return False
    return isinstance(value, expected_tuple)


def validate_value(
    dp_id: str,
    value: Any,
    *,
    strict: bool = False,
) -> list[str]:
    """Return a list of error messages for ``value`` under ``dp_id``'s schema.

    Empty list ⇒ value is shape-conformant. Soft warnings carry the
    ``[warn]`` prefix; in ``strict=True`` mode every unknown-key warning
    is promoted to a hard error (no prefix).

    No schema registered for ``dp_id`` ⇒ ``[]``. This is intentional: we
    don't want to block patches for new dp_ids until their schema lands
    in ``DP_SCHEMA``.
    """

    if dp_id not in DP_SCHEMA:
        return []

    schema = DP_SCHEMA[dp_id]
    errors: list[str] = []

    if value is None:
        errors.append(f"value is None (dp_id={dp_id})")
        return errors

    if not isinstance(value, dict):
        errors.append(
            f"value not dict (got {type(value).__name__}) for dp_id={dp_id}"
        )
        return errors

    # Required fields ----------------------------------------------------
    required = schema.get("required", {})
    for k, t in required.items():
        if k not in value:
            errors.append(f"missing required field {k!r} (dp_id={dp_id})")
            continue
        if not _check_type(value[k], t):
            errors.append(
                f"field {k!r} has wrong type: got "
                f"{type(value[k]).__name__}, expected {_type_name(t)} "
                f"(dp_id={dp_id})"
            )

    # Optional fields ----------------------------------------------------
    optional = schema.get("optional", {})
    for k, t in optional.items():
        if k in value and not _check_type(value[k], t):
            errors.append(
                f"optional field {k!r} has wrong type: got "
                f"{type(value[k]).__name__}, expected {_type_name(t)} "
                f"(dp_id={dp_id})"
            )

    # Unknown-key sweep --------------------------------------------------
    all_known = set(required) | set(optional)
    for k in value:
        if k not in all_known:
            if strict:
                errors.append(
                    f"unknown field {k!r} not in schema (dp_id={dp_id})"
                )
            else:
                errors.append(
                    f"[warn] unknown field {k!r} not in schema "
                    f"(dp_id={dp_id})"
                )

    # Array-of-dict item schemas ----------------------------------------
    # Pattern: any schema key suffixed with ``_item_schema`` describes the
    # shape of dicts inside the list at the matching key. E.g.
    # ``segments_item_schema`` is enforced on each item of ``value["segments"]``.
    for schema_key, item_schema in schema.items():
        if not schema_key.endswith("_item_schema"):
            continue
        list_key = schema_key[: -len("_item_schema")]
        if list_key not in value:
            continue
        items = value[list_key]
        if not isinstance(items, list):
            # Already reported as wrong type if list was required.
            continue
        for i, item in enumerate(items):
            if not isinstance(item, dict):
                errors.append(
                    f"{list_key}[{i}] not dict (got "
                    f"{type(item).__name__}) for dp_id={dp_id}"
                )
                continue
            for ik, it in item_schema.items():
                if ik in item and not _check_type(item[ik], it):
                    errors.append(
                        f"{list_key}[{i}].{ik} wrong type: got "
                        f"{type(item[ik]).__name__}, expected "
                        f"{_type_name(it)} (dp_id={dp_id})"
                    )

    return errors


def validate_overlay_node(
    node: dict,
    *,
    strict: bool = False,
) -> list[str]:
    """Validate one overlay-yaml node's ``value`` against its dp_id schema.

    Returns a list of error strings (empty list = passes).

    The function fires TWO layers of rules:

    1. **Compiler-parity rules** — mirror the four invariants that
       ``mvp20.overlays`` enforces during ``compile-overlays``. These run
       regardless of status because they describe how the *status itself*
       interacts with policy / required_level / value shape:

       a. ``status == 'Unknown'`` AND ``required_level == 'required'`` →
          hard error (required node was not filled).
       b. ``status == 'Unknown'`` AND ``required_level ==
          'conditional_required'`` AND ``missing_reason`` missing → hard
          error (conditional Unknown must explain itself).
       c. ``status == 'N/A'`` AND ``missing_policy !=
          'not_applicable_remove'`` → hard error (N/A must opt out via
          the remove policy, otherwise it pollutes coverage math).
       d. ``status == 'Optionality'`` with a non-empty ``value`` dict →
          ``value`` must contain BOTH ``current_contribution`` AND
          ``future_option_value`` keys; the Optionality node represents a
          dual-state position (what's already priced in vs. what's the
          option upside) and downstream scoring depends on the split.

       These rules previously lived only in ``overlays.py`` so codex
       fills that the verifier marked clean still failed at compile
       time. Mirroring them here closes that gap.

    2. **Value-shape validation** — run the dp_id-specific schema in
       :data:`DP_SCHEMA` for ``Known`` (and populated ``Optionality``)
       nodes. Unknown / N/A / Inactive nodes legitimately have
       ``value=None`` so this layer is skipped for them.
    """

    if not isinstance(node, dict):
        return ["node is not a dict"]
    dp_id = node.get("dp_id") or ""
    status = node.get("data_status")
    errors: list[str] = []

    # --- Layer 1: compiler-parity status / policy rules -----------------
    if status == "Unknown" and node.get("required_level") == "required":
        errors.append("required node is Unknown")
    if (
        status == "Unknown"
        and node.get("required_level") == "conditional_required"
        and not node.get("missing_reason")
    ):
        errors.append("Unknown node must include missing_reason")
    if (
        status == "N/A"
        and node.get("missing_policy") != "not_applicable_remove"
    ):
        errors.append("N/A node must use missing_policy=not_applicable_remove")
    if status == "Optionality":
        opt_value = node.get("value")
        if isinstance(opt_value, dict) and opt_value:
            # Empty dict {} is treated as "not yet filled" — see Layer 2
            # gating below — so only enforce the split on non-empty dicts.
            missing_keys = {
                "current_contribution",
                "future_option_value",
            } - set(opt_value)
            if missing_keys:
                errors.append(
                    "Optionality node must split current_contribution and "
                    "future_option_value"
                )
        elif opt_value is not None and not isinstance(opt_value, dict):
            errors.append(
                "Optionality value must be a dict with current_contribution "
                "and future_option_value"
            )

    # --- Layer 2: dp_id schema validation -------------------------------
    # Validate Known + populated Optionality slots. Unknown / N/A /
    # Inactive nodes legitimately have value=None or empty.
    if status not in ("Known", "Optionality"):
        return errors
    value = node.get("value")
    if status == "Optionality":
        # Skip empty Optionality (not yet filled, still in candidacy).
        if value is None:
            return errors
        if isinstance(value, dict) and not value:
            return errors
        # Properly-split Optionality wraps the dp_id payload inside
        # ``future_option_value`` (and pairs it with ``current_contribution``).
        # The nested payload is intentionally free-form — operators
        # describe the option upside narratively, sometimes with quantitative
        # sub-fields that do not match the dp_id's "Known" schema. So when
        # the split is present, we trust Layer 1 (key-presence) and stop
        # here. Layer 2 schema validation still applies to ``Known`` and
        # to legacy unsplit Optionality (which Layer 1 already errored on).
        if isinstance(value, dict) and {
            "current_contribution",
            "future_option_value",
        } <= set(value):
            return errors
    return errors + validate_value(dp_id, value, strict=strict)


# ---------------------------------------------------------------------------
# Module-level introspection helpers (used by tests + CLI)
# ---------------------------------------------------------------------------


def schema_coverage() -> dict[str, int]:
    """Return summary stats about the schema registry."""

    total = len(DP_SCHEMA)
    by_layer: dict[str, int] = {}
    for dp in DP_SCHEMA:
        layer = dp.split(".")[0]
        by_layer[layer] = by_layer.get(layer, 0) + 1
    return {"total": total, **by_layer}


__all__ = [
    "DP_SCHEMA",
    "validate_value",
    "validate_overlay_node",
    "schema_coverage",
]
