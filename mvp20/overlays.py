"""Overlay schema generation, validation, and SQLite compilation.

The overlay layer is the static/quarterly graph contract that sits below the
minute-level ``realtime_current`` table. It is intentionally file-first:

* industry overlays live at ``config/industry_overlays/<industry_id>.yaml``
* stock overlays live at
  ``config/stock_overlays/<industry_id>/<ts_code>.yaml``
* compiled snapshots are materialized into SQLite for fast frontend reads

The schema mirrors the operating rules in ``图谱设计.md``: every node declares
missing-data policy, calculation type, aggregation policy, materiality, and
alert behavior. Hierarchy edges and causal edges are kept separate so the
compiler can reject causal transmission hidden inside a parent-child edge.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

import yaml


SCHEMA_VERSION = 1
STOCK_TEMPLATE_VERSION = "stock-overlay-v2"
INDUSTRY_TEMPLATE_VERSION = "industry-overlay-v2"
DEFAULT_PERIOD = "2026-Q1"
PENDING_INDUSTRY_ID = "SPACE_ECONOMY"

DATA_STATUSES = {
    "Known",
    "N/A",
    "Unknown",
    "Unavailable",
    "Proxy",
    "Inactive",
    "Low Materiality",
    "Optionality",
}
REQUIRED_LEVELS = {"required", "conditional_required", "optional"}
MISSING_POLICIES = {
    "known",
    "not_applicable_remove",
    "unknown_reduce_confidence",
    "inactive_zero_weight",
    "low_materiality_fold",
    "optionality_track",
}
CALCULATION_TYPES = {
    "none",
    "raw_value",
    "additive",
    "subtractive",
    "multiplicative_factor",
    "ratio_metric",
    "weighted_contribution",
    "risk_factor",
    "confidence_multiplier",
    "bottleneck_min",
    "and_gate",
    "or_gate",
    "threshold",
    "saturation",
    "scenario_weighted",
    "time_decay",
    "bayesian_update",
    "dedup_correlation",
    "reflexivity",
    "dcf",
}
AGGREGATION_POLICIES = {
    "none",
    "add_uncertainty_penalty",
    "renormalize_siblings",
    "weighted_average",
    "weighted_sum",
    "multiply_chain",
    "subtract_risk",
    "ratio_derive",
    "multiplicative_factor",
    "confidence_adjusted",
    "min_capacity_constraint",
    "and_all_required",
    "or_max_trigger",
    "threshold_trigger",
    "saturation_curve",
    "scenario_probability_weighted",
    "time_decay_half_life",
    "bayesian_confidence_update",
    "deduplicate_correlated_inputs",
    "feedback_loop_limited",
    "discounted_cash_flow",
    "no_aggregation",
}
ALERT_POLICIES = {
    "error_if_missing",
    "warn_if_material",
    "warn_if_stale",
    "no_alert",
}

_FIELD_GOVERNANCE_CACHE: Any | None = None
_FIELD_GOVERNANCE_LOADED = False


@dataclass(frozen=True)
class SlotDef:
    dp_id: str
    node_name: str
    node_type: str
    layer: str
    direction: str = "positive"
    base_weight: float = 1.0
    active_weight: float = 1.0
    required_level: str = "conditional_required"
    data_status: str = "Unknown"
    missing_policy: str = "unknown_reduce_confidence"
    calculation_type: str = "weighted_contribution"
    aggregation_policy: str = "add_uncertainty_penalty"
    alert_policy: str = "warn_if_material"
    materiality: float = 0.6
    update_frequency: str = "quarterly"
    time_horizon: tuple[str, ...] = ("short", "medium", "long")
    related_metrics: tuple[str, ...] = ()
    trigger_condition: str | None = None
    invalidation_condition: str | None = None
    default_missing_reason: str | None = "pending LLM/company-specific research"
    value: Any = None


INDUSTRY_DERIVED_SLOTS: tuple[SlotDef, ...] = (
    SlotDef("L0.demand.terminal", "终端需求强度", "Industry Demand", "industry_macro", materiality=0.8, calculation_type="multiplicative_factor", aggregation_policy="multiply_chain"),
    SlotDef("L0.demand.user_count", "用户/客户数量变化", "Industry Demand", "industry_macro", materiality=0.6, calculation_type="multiplicative_factor", aggregation_policy="multiply_chain"),
    SlotDef("L0.demand.frequency", "使用频次/替换频率", "Industry Demand", "industry_macro", materiality=0.55, calculation_type="multiplicative_factor", aggregation_policy="multiply_chain"),
    SlotDef("L0.demand.penetration", "渗透率变化", "Industry Demand", "industry_macro", materiality=0.65, calculation_type="multiplicative_factor", aggregation_policy="multiply_chain"),
    SlotDef("L0.demand.replacement", "替换周期与更新需求", "Industry Demand", "industry_macro", materiality=0.55, calculation_type="multiplicative_factor", aggregation_policy="multiply_chain"),
    SlotDef("L0.supply.capacity", "行业供给/产能", "Industry Supply", "industry_supply", materiality=0.75, calculation_type="bottleneck_min", aggregation_policy="min_capacity_constraint"),
    SlotDef("L0.supply.channel_service", "渠道与服务能力", "Industry Supply", "industry_supply", materiality=0.55, calculation_type="weighted_contribution", aggregation_policy="weighted_average"),
    SlotDef("L0.supply.chain_eff", "供应链效率", "Industry Supply", "industry_supply", materiality=0.6, calculation_type="multiplicative_factor", aggregation_policy="multiply_chain"),
    SlotDef("L0.price.discount", "折扣与价格压力", "Industry Price", "industry_price", direction="negative", materiality=0.7, calculation_type="risk_factor", aggregation_policy="subtract_risk"),
    SlotDef("L0.price.pricing_power", "行业定价权", "Industry Price", "industry_price", materiality=0.75, calculation_type="multiplicative_factor", aggregation_policy="multiply_chain"),
    SlotDef("L0.cost.rent", "租金/固定成本压力", "Industry Cost", "industry_cost", direction="negative", materiality=0.5, calculation_type="risk_factor", aggregation_policy="subtract_risk"),
    SlotDef("L0.cost.cac", "获客成本/营销成本", "Industry Cost", "industry_cost", direction="negative", materiality=0.6, calculation_type="risk_factor", aggregation_policy="subtract_risk"),
    SlotDef("L0.compete.price_war", "价格战风险", "Industry Competition", "industry_competition", direction="negative", materiality=0.8, data_status="Inactive", missing_policy="inactive_zero_weight", calculation_type="threshold", aggregation_policy="threshold_trigger", active_weight=0.0, default_missing_reason=None),
    SlotDef("L0.compete.new_entrant", "新进入者/替代风险", "Industry Competition", "industry_competition", direction="negative", materiality=0.6, data_status="Inactive", missing_policy="inactive_zero_weight", calculation_type="risk_factor", aggregation_policy="subtract_risk", active_weight=0.0, default_missing_reason=None),
)

COMPANY_DERIVED_SLOTS: tuple[SlotDef, ...] = (
    SlotDef("L1.position.channel_edge", "渠道/供应链位置优势", "Company Position", "company_position", materiality=0.75, calculation_type="multiplicative_factor", aggregation_policy="multiply_chain"),
    SlotDef("L1.position.stickiness", "客户粘性与绑定深度", "Company Position", "company_position", materiality=0.8, calculation_type="multiplicative_factor", aggregation_policy="multiply_chain"),
    SlotDef("L2.newbiz.tam", "新业务潜在空间", "Optionality", "business_optionality", required_level="optional", data_status="Optionality", missing_policy="optionality_track", calculation_type="scenario_weighted", aggregation_policy="scenario_probability_weighted", alert_policy="no_alert", materiality=0.65, default_missing_reason=None, value={"current_contribution": None, "future_option_value": None}),
    SlotDef("L2.newbiz.uncertainty", "新业务不确定性", "Optionality Risk", "business_optionality", direction="negative", required_level="optional", data_status="Optionality", missing_policy="optionality_track", calculation_type="scenario_weighted", aggregation_policy="scenario_probability_weighted", alert_policy="no_alert", materiality=0.55, default_missing_reason=None, value={"current_contribution": None, "future_option_value": None}),
    SlotDef("L3.product.lifecycle", "产品生命周期阶段", "Product", "product_market_fit", materiality=0.65, calculation_type="saturation", aggregation_policy="saturation_curve"),
    SlotDef("L3.customer.segment_mix", "客户结构与集中度", "Customer", "customer_structure", materiality=0.85, calculation_type="risk_factor", aggregation_policy="add_uncertainty_penalty"),
    SlotDef("L3.channel.mix", "渠道结构", "Channel", "go_to_market", materiality=0.65, calculation_type="weighted_contribution", aggregation_policy="weighted_average"),
    SlotDef("L3.region.tier_mix", "区域/市场层级结构", "Region", "geographic_exposure", materiality=0.6, calculation_type="weighted_contribution", aggregation_policy="weighted_average"),
    SlotDef("L3.delivery.lead_time", "交付周期", "Operations", "delivery", materiality=0.55, calculation_type="bottleneck_min", aggregation_policy="min_capacity_constraint"),
    SlotDef("L3.delivery.csat", "交付质量/满意度", "Operations", "delivery", materiality=0.45, calculation_type="weighted_contribution", aggregation_policy="weighted_average"),
    SlotDef("L4.volume.foot_traffic", "客流/订单流", "Operating Metric", "validation_metric", materiality=0.65, update_frequency="minute", calculation_type="multiplicative_factor", aggregation_policy="multiply_chain"),
    SlotDef("L4.volume.frequency", "复购/使用频次", "Operating Metric", "validation_metric", materiality=0.55, update_frequency="daily", calculation_type="multiplicative_factor", aggregation_policy="multiply_chain"),
    SlotDef("L4.price.subscription", "订阅/价格模式", "Operating Metric", "pricing_metric", materiality=0.5, calculation_type="ratio_metric", aggregation_policy="ratio_derive"),
    SlotDef("L4.price.discount", "公司折扣率", "Operating Metric", "pricing_metric", direction="negative", materiality=0.65, calculation_type="risk_factor", aggregation_policy="subtract_risk"),
    SlotDef("L4.eff.capacity_utilization", "产能利用率/资源利用率", "Efficiency Metric", "efficiency_metric", materiality=0.75, update_frequency="daily", calculation_type="bottleneck_min", aggregation_policy="min_capacity_constraint"),
    SlotDef("L4.eff.conversion_retention", "转化率/留存率", "Efficiency Metric", "efficiency_metric", materiality=0.7, update_frequency="daily", calculation_type="multiplicative_factor", aggregation_policy="multiply_chain"),
    SlotDef("L4.share.customer_channel", "客户/渠道份额", "Share Metric", "market_share", materiality=0.7, calculation_type="ratio_metric", aggregation_policy="ratio_derive"),
    SlotDef("L5.surprise.buy_whisper", "买方预期差/业绩 whisper", "Expectation", "expectation_gap", materiality=0.85, calculation_type="multiplicative_factor", aggregation_policy="multiply_chain"),
)

# ---------------------------------------------------------------------------
# X5: 26 closed-loop slots filled by codex from LOCAL evidence only
# ---------------------------------------------------------------------------
#
# These are the slots that the X5 closed-loop pipeline asks codex to fill.
# *All* filling must happen from:
#   * inline SQLite dp_id facts injected into the codex prompt, or
#   * other local overlay YAML nodes already filled in earlier phases, or
#   * industry-framework inference (confidence ≤ 0.5, marked
#     ``evidence_sources: [{kind: "industry_inference", ...}]``).
#
# Codex must NEVER:
#   * fetch URLs from the web (curl / wget / http URLs in evidence_sources)
#   * quote training-set facts about specific companies
#   * hallucinate URLs as evidence
#
# When no local evidence supports a slot, codex outputs
# ``data_status: Unknown`` + ``missing_reason: "no_local_evidence"``.
#
# Group A: company-portrait reinforcement (L1 / L2 / L3) — 16 slots
# Group B: industry-state补强 (L0) — 4 net-new slots (L0.price.discount lives
#          in INDUSTRY_DERIVED_SLOTS already and is NOT duplicated here)
# Group C: operating-metric soft KPIs (L4) — 6 slots
_X5_GROUP_B_L0_SLOTS: tuple[SlotDef, ...] = (
    # L0.price.discount is already in INDUSTRY_DERIVED_SLOTS — do not redeclare.
    SlotDef("L0.price.contract_spot", "长协 vs 现货价差", "Industry Price", "industry_price", materiality=0.65, calculation_type="ratio_metric", aggregation_policy="ratio_derive"),
    SlotDef("L0.price.product_asp", "行业产品 ASP", "Industry Price", "industry_price", materiality=0.7, calculation_type="multiplicative_factor", aggregation_policy="multiply_chain"),
    SlotDef("L0.supply.inventory", "行业库存水平", "Industry Supply", "industry_supply", direction="negative", materiality=0.65, calculation_type="risk_factor", aggregation_policy="subtract_risk"),
    SlotDef("L0.sentiment.social", "社交情绪/舆情", "Industry Sentiment", "industry_macro", materiality=0.4, calculation_type="multiplicative_factor", aggregation_policy="multiply_chain"),
)

X5_DERIVED_SLOTS: tuple[SlotDef, ...] = (
    # ── Group A.1 — L1 position reinforcement (5 slots) ───────────────────
    SlotDef("L1.position.market_share", "市场份额与排名", "Company Position", "company_position", materiality=0.8, calculation_type="weighted_contribution", aggregation_policy="weighted_average"),
    SlotDef("L1.position.brand", "品牌力与认知度", "Company Position", "company_position", materiality=0.65, calculation_type="multiplicative_factor", aggregation_policy="multiply_chain"),
    SlotDef("L1.position.tech_barrier", "技术壁垒/专利", "Company Position", "company_position", materiality=0.8, calculation_type="multiplicative_factor", aggregation_policy="multiply_chain"),
    SlotDef("L1.position.cost_edge", "成本优势", "Company Position", "company_position", materiality=0.75, calculation_type="multiplicative_factor", aggregation_policy="multiply_chain"),
    SlotDef("L1.position.pricing_power", "公司定价权", "Company Position", "company_position", materiality=0.75, calculation_type="multiplicative_factor", aggregation_policy="multiply_chain"),
    # ── Group A.2 — L2 segment / new business (7 slots) ───────────────────
    SlotDef("L2.segment.cash_contrib", "主营现金贡献结构", "Business Segment", "business_optionality", materiality=0.7, calculation_type="weighted_contribution", aggregation_policy="weighted_average"),
    SlotDef("L2.segment.industry_exposure", "细分行业敞口", "Business Segment", "business_optionality", materiality=0.7, calculation_type="weighted_contribution", aggregation_policy="weighted_average"),
    SlotDef("L2.segment.compete_landscape", "细分竞争格局", "Business Segment", "business_optionality", materiality=0.7, calculation_type="weighted_contribution", aggregation_policy="weighted_average"),
    SlotDef("L2.segment.business_risk", "业务结构性风险", "Business Segment", "business_optionality", direction="negative", materiality=0.7, calculation_type="risk_factor", aggregation_policy="subtract_risk"),
    SlotDef("L2.newbiz.commercialization", "新业务商业化进度", "Optionality", "business_optionality", required_level="optional", data_status="Optionality", missing_policy="optionality_track", calculation_type="scenario_weighted", aggregation_policy="scenario_probability_weighted", alert_policy="no_alert", materiality=0.65, default_missing_reason=None, value={"current_contribution": None, "future_option_value": None}),
    SlotDef("L2.newbiz.revenue_contrib", "新业务当前营收占比", "Optionality", "business_optionality", required_level="optional", data_status="Optionality", missing_policy="optionality_track", calculation_type="scenario_weighted", aggregation_policy="scenario_probability_weighted", alert_policy="no_alert", materiality=0.6, default_missing_reason=None, value={"current_contribution": None, "future_option_value": None}),
    SlotDef("L2.newbiz.valuation_contrib", "新业务估值贡献", "Optionality", "business_optionality", required_level="optional", data_status="Optionality", missing_policy="optionality_track", calculation_type="scenario_weighted", aggregation_policy="scenario_probability_weighted", alert_policy="no_alert", materiality=0.7, default_missing_reason=None, value={"current_contribution": None, "future_option_value": None}),
    # ── Group A.3 — L3 customer / channel / region / delivery (4 slots) ──
    SlotDef("L3.customer.solvency", "大客户偿付能力", "Customer", "customer_structure", direction="negative", materiality=0.7, calculation_type="risk_factor", aggregation_policy="add_uncertainty_penalty"),
    SlotDef("L3.channel.overseas", "海外渠道铺货与本土化", "Channel", "go_to_market", materiality=0.6, calculation_type="weighted_contribution", aggregation_policy="weighted_average"),
    SlotDef("L3.region.key_risk", "重点区域风险", "Region", "geographic_exposure", direction="negative", materiality=0.65, calculation_type="risk_factor", aggregation_policy="subtract_risk"),
    SlotDef("L3.delivery.capacity_supply", "交付产能/供应链稳定", "Operations", "delivery", materiality=0.65, calculation_type="bottleneck_min", aggregation_policy="min_capacity_constraint"),
    # ── Group B — L0 industry补强 (4 net-new slots) ───────────────────────
    # Defined separately in ``_X5_GROUP_B_L0_SLOTS`` so they can also appear
    # in ``build_industry_overlay`` (codex fills these at the industry level
    # and every stock overlay inherits via inherit_from_industry=True). They
    # are still part of ALL_DERIVED_SLOTS below.
    *_X5_GROUP_B_L0_SLOTS,
    # ── Group C — L4 operating soft KPIs (6 slots) ────────────────────────
    SlotDef("L4.price.asp_aov_arpu", "ASP/AOV/ARPU", "Operating Metric", "pricing_metric", materiality=0.7, calculation_type="ratio_metric", aggregation_policy="ratio_derive"),
    SlotDef("L4.price.pricing_power", "公司定价权 (运营)", "Operating Metric", "pricing_metric", materiality=0.7, calculation_type="multiplicative_factor", aggregation_policy="multiply_chain"),
    SlotDef("L4.price.elasticity", "价格弹性", "Operating Metric", "pricing_metric", materiality=0.55, calculation_type="ratio_metric", aggregation_policy="ratio_derive"),
    SlotDef("L4.cost.cac_production", "获客/单位生产成本", "Operating Metric", "efficiency_metric", direction="negative", materiality=0.65, calculation_type="risk_factor", aggregation_policy="subtract_risk"),
    SlotDef("L4.cost.rent_energy_logistics", "租金/能源/物流成本", "Operating Metric", "efficiency_metric", direction="negative", materiality=0.55, calculation_type="risk_factor", aggregation_policy="subtract_risk"),
    SlotDef("L4.eff.store_labor", "门店/人效", "Operating Metric", "efficiency_metric", materiality=0.6, update_frequency="daily", calculation_type="multiplicative_factor", aggregation_policy="multiply_chain"),
)

# ---------------------------------------------------------------------------
# Z3: complete the LLM-candidate coverage to 111 dp_ids (X5 58 + Z3 53).
#
# These slots cover the remaining bucket C + bucket D LLM-fillable fields from
# ``docs/data_sources/field_strategy_v1.md`` §2 that were not yet present in
# the overlay schema. Splitting industry-level vs stock-level keeps the
# inherit_from_industry semantics intact:
#
#   * ``_Z3_INDUSTRY_DERIVED_SLOTS`` — L0.* policy/tech/cost/compete + L9
#     industry/macro slots. Filled at the industry level and inherited by
#     every stock overlay (inherit_from_industry=True) so per-stock duplicate
#     codex effort is avoided.
#   * ``_Z3_COMPANY_DERIVED_SLOTS`` — L1.*/L2.*/L3.*/L4.*/L5.* per-company
#     soft indicators plus L8.* risk offsets and L9.* per-company catalysts.
#     These differ per stock and live on the stock overlay only.
#
# Z2 fingerprint hooks (event_driven / quarterly_filing / etc.) are declared
# in ``config/llm_field_governance.yaml`` — the SlotDef itself only carries
# graph-engine metadata (calculation_type / aggregation_policy / materiality
# / etc.). Event-driven Inactive defaults are encoded directly on the slot
# (status=Inactive + active_weight=0 + missing_policy=inactive_zero_weight)
# so they round-trip through merge_preserve correctly.
# ---------------------------------------------------------------------------

_Z3_INDUSTRY_DERIVED_SLOTS: tuple[SlotDef, ...] = (
    # ── L0 policy (4 slots) — event-driven regulation / subsidy / trade ────
    SlotDef("L0.policy.access_license", "准入与牌照", "Industry Policy", "industry_policy", materiality=0.65, calculation_type="threshold", aggregation_policy="threshold_trigger"),
    SlotDef("L0.policy.regulation", "监管/反垄断", "Industry Policy", "industry_policy", direction="negative", materiality=0.7, calculation_type="risk_factor", aggregation_policy="subtract_risk"),
    SlotDef("L0.policy.subsidy", "行业补贴政策", "Industry Policy", "industry_policy", materiality=0.55, calculation_type="multiplicative_factor", aggregation_policy="multiply_chain"),
    SlotDef("L0.policy.tax_trade", "税收/出口限制", "Industry Policy", "industry_policy", direction="negative", materiality=0.65, calculation_type="risk_factor", aggregation_policy="subtract_risk"),
    # ── L0 tech (3 slots) — technology shocks ──────────────────────────────
    SlotDef("L0.tech.ai_automation", "AI/自动化/降本", "Industry Technology", "industry_tech", materiality=0.6, calculation_type="multiplicative_factor", aggregation_policy="multiply_chain"),
    SlotDef("L0.tech.breakthrough", "技术突破/产品迭代", "Industry Technology", "industry_tech", materiality=0.65, calculation_type="multiplicative_factor", aggregation_policy="multiply_chain"),
    SlotDef("L0.tech.substitute_tech", "替代技术", "Industry Technology", "industry_tech", direction="negative", materiality=0.6, calculation_type="risk_factor", aggregation_policy="subtract_risk"),
    # ── L0 cost (3 slots) — labor / raw material / energy logistics ────────
    SlotDef("L0.cost.energy_logistics", "行业能源/物流成本", "Industry Cost", "industry_cost", direction="negative", materiality=0.55, calculation_type="risk_factor", aggregation_policy="subtract_risk"),
    SlotDef("L0.cost.labor", "行业人工成本", "Industry Cost", "industry_cost", direction="negative", materiality=0.55, calculation_type="risk_factor", aggregation_policy="subtract_risk"),
    SlotDef("L0.cost.raw_material", "原材料价格", "Industry Cost", "industry_cost", direction="negative", materiality=0.65, calculation_type="risk_factor", aggregation_policy="subtract_risk"),
    # ── L0 competition (1 slot) — share concentration ──────────────────────
    SlotDef("L0.compete.share_concentration", "市占率/集中度变化", "Industry Competition", "industry_competition", materiality=0.65, calculation_type="multiplicative_factor", aggregation_policy="multiply_chain"),
    # ── L9 industry / macro (2 slots) — event-driven industry-level ───────
    SlotDef("L9.industry.data_price", "行业数据/价格发布", "Industry Catalyst", "catalyst_industry", materiality=0.5, data_status="Inactive", missing_policy="inactive_zero_weight", calculation_type="or_gate", aggregation_policy="or_max_trigger", active_weight=0.0, default_missing_reason=None),
    SlotDef("L9.macro.geo", "地缘事件", "Macro Catalyst", "catalyst_macro", direction="negative", materiality=0.6, data_status="Inactive", missing_policy="inactive_zero_weight", calculation_type="risk_factor", aggregation_policy="subtract_risk", active_weight=0.0, default_missing_reason=None),
)

_Z3_COMPANY_DERIVED_SLOTS: tuple[SlotDef, ...] = (
    # ── L1 tags / ranks (5 slots) — cheap_extract label fields ─────────────
    SlotDef("L1.role.tag", "行业角色标签", "Company Position", "company_position", materiality=0.55, calculation_type="weighted_contribution", aggregation_policy="weighted_average"),
    SlotDef("L1.model.tag", "商业模式标签", "Company Position", "company_position", materiality=0.55, calculation_type="weighted_contribution", aggregation_policy="weighted_average"),
    SlotDef("L1.moat.tags", "护城河标签", "Company Position", "company_position", materiality=0.7, calculation_type="weighted_contribution", aggregation_policy="weighted_average"),
    SlotDef("L1.stock_attr.tags", "股价属性标签", "Company Position", "company_position", materiality=0.5, calculation_type="weighted_contribution", aggregation_policy="weighted_average"),
    SlotDef("L1.position.growth_rank", "增速排名", "Company Position", "company_position", materiality=0.6, calculation_type="weighted_contribution", aggregation_policy="weighted_average"),
    # ── L2 segment quantitative (2 slots) ──────────────────────────────────
    SlotDef("L2.segment.opex_ratio", "业务线费用率", "Business Segment", "business_optionality", direction="negative", materiality=0.6, calculation_type="ratio_metric", aggregation_policy="ratio_derive"),
    SlotDef("L2.segment.profit_share", "业务线利润占比", "Business Segment", "business_optionality", materiality=0.65, calculation_type="weighted_contribution", aggregation_policy="weighted_average"),
    # ── L3 product / customer / channel / region (8 slots) ─────────────────
    SlotDef("L3.product.portfolio", "产品组合结构", "Product", "product_market_fit", materiality=0.65, calculation_type="weighted_contribution", aggregation_policy="weighted_average"),
    SlotDef("L3.product.margin_mix", "产品毛利/价格结构", "Product", "product_market_fit", materiality=0.7, calculation_type="weighted_contribution", aggregation_policy="weighted_average"),
    SlotDef("L3.customer.concentration", "客户集中度/流失风险", "Customer", "customer_structure", direction="negative", materiality=0.75, calculation_type="risk_factor", aggregation_policy="subtract_risk"),
    SlotDef("L3.channel.cost", "渠道费用", "Channel", "go_to_market", direction="negative", materiality=0.55, calculation_type="risk_factor", aggregation_policy="subtract_risk"),
    SlotDef("L3.channel.efficiency", "渠道效率", "Channel", "go_to_market", materiality=0.6, calculation_type="multiplicative_factor", aggregation_policy="multiply_chain"),
    SlotDef("L3.region.domestic_overseas", "国内/海外收入结构", "Region", "geographic_exposure", materiality=0.65, calculation_type="weighted_contribution", aggregation_policy="weighted_average"),
    SlotDef("L3.region.fx_geo", "汇率/地缘影响", "Region", "geographic_exposure", direction="negative", materiality=0.6, calculation_type="risk_factor", aggregation_policy="subtract_risk"),
    SlotDef("L3.delivery.fulfillment_cost", "履约/售后成本", "Operations", "delivery", direction="negative", materiality=0.5, calculation_type="risk_factor", aggregation_policy="subtract_risk"),
    # ── L4 share / volume soft KPIs (6 slots) ──────────────────────────────
    SlotDef("L4.share.market", "公司市占率", "Share Metric", "market_share", materiality=0.75, calculation_type="ratio_metric", aggregation_policy="ratio_derive"),
    SlotDef("L4.share.substitution", "竞品替代", "Share Metric", "market_share", direction="negative", materiality=0.6, calculation_type="risk_factor", aggregation_policy="subtract_risk"),
    SlotDef("L4.volume.sales", "销量", "Operating Metric", "validation_metric", materiality=0.7, calculation_type="multiplicative_factor", aggregation_policy="multiply_chain"),
    SlotDef("L4.volume.orders", "订单量", "Operating Metric", "validation_metric", materiality=0.7, calculation_type="multiplicative_factor", aggregation_policy="multiply_chain"),
    SlotDef("L4.volume.shipments", "出货量/交付量", "Operating Metric", "validation_metric", materiality=0.65, calculation_type="multiplicative_factor", aggregation_policy="multiply_chain"),
    SlotDef("L4.volume.users", "客户/用户数", "Operating Metric", "validation_metric", materiality=0.65, calculation_type="multiplicative_factor", aggregation_policy="multiply_chain"),
    # ── L5 forecast (1 slot) ───────────────────────────────────────────────
    SlotDef("L5.fcst.beat_probability", "业绩兑现概率", "Expectation", "expectation_gap", materiality=0.7, calculation_type="multiplicative_factor", aggregation_policy="multiply_chain"),
    # ── L8 risk offsets (15 slots) — event-driven default Inactive ─────────
    SlotDef("L8.gov.fraud_control", "财务造假/内控", "Risk Offset", "risk_governance", direction="negative", materiality=0.85, data_status="Inactive", missing_policy="inactive_zero_weight", calculation_type="risk_factor", aggregation_policy="subtract_risk", active_weight=0.0, default_missing_reason=None),
    SlotDef("L8.gov.litigation", "法律诉讼", "Risk Offset", "risk_governance", direction="negative", materiality=0.7, data_status="Inactive", missing_policy="inactive_zero_weight", calculation_type="risk_factor", aggregation_policy="subtract_risk", active_weight=0.0, default_missing_reason=None),
    SlotDef("L8.industry.demand_supply", "行业需求/供给恶化", "Risk Offset", "risk_industry", direction="negative", materiality=0.7, calculation_type="risk_factor", aggregation_policy="subtract_risk"),
    SlotDef("L8.industry.price_war", "行业价格战", "Risk Offset", "risk_industry", direction="negative", materiality=0.7, calculation_type="risk_factor", aggregation_policy="subtract_risk"),
    SlotDef("L8.industry.substitute", "替代品出现", "Risk Offset", "risk_industry", direction="negative", materiality=0.65, calculation_type="risk_factor", aggregation_policy="subtract_risk"),
    SlotDef("L8.op.customer_channel", "客户流失/渠道失效", "Risk Offset", "risk_operation", direction="negative", materiality=0.7, calculation_type="risk_factor", aggregation_policy="subtract_risk"),
    SlotDef("L8.op.order_miss", "订单不兑现", "Risk Offset", "risk_operation", direction="negative", materiality=0.7, calculation_type="risk_factor", aggregation_policy="subtract_risk"),
    SlotDef("L8.op.product_fail", "产品失败", "Risk Offset", "risk_operation", direction="negative", materiality=0.7, calculation_type="risk_factor", aggregation_policy="subtract_risk"),
    SlotDef("L8.reg.license_risk", "牌照/准入风险", "Risk Offset", "risk_regulation", direction="negative", materiality=0.65, calculation_type="risk_factor", aggregation_policy="subtract_risk"),
    SlotDef("L8.reg.subsidy_off", "补贴退坡", "Risk Offset", "risk_regulation", direction="negative", materiality=0.55, calculation_type="risk_factor", aggregation_policy="subtract_risk"),
    SlotDef("L8.reg.tax_trade", "税收/出口限制 (个股)", "Risk Offset", "risk_regulation", direction="negative", materiality=0.65, calculation_type="risk_factor", aggregation_policy="subtract_risk"),
    SlotDef("L8.reg.tighten", "监管收紧/反垄断 (个股)", "Risk Offset", "risk_regulation", direction="negative", materiality=0.65, calculation_type="risk_factor", aggregation_policy="subtract_risk"),
    SlotDef("L8.shock.black_swan", "黑天鹅事件", "Risk Offset", "risk_shock", direction="negative", materiality=0.85, data_status="Inactive", missing_policy="inactive_zero_weight", calculation_type="risk_factor", aggregation_policy="subtract_risk", active_weight=0.0, default_missing_reason=None),
    SlotDef("L8.shock.crisis", "安全/舆情危机", "Risk Offset", "risk_shock", direction="negative", materiality=0.7, data_status="Inactive", missing_policy="inactive_zero_weight", calculation_type="risk_factor", aggregation_policy="subtract_risk", active_weight=0.0, default_missing_reason=None),
    SlotDef("L8.shock.supply_break", "供应中断/客户违约/自然灾害", "Risk Offset", "risk_shock", direction="negative", materiality=0.75, data_status="Inactive", missing_policy="inactive_zero_weight", calculation_type="risk_factor", aggregation_policy="subtract_risk", active_weight=0.0, default_missing_reason=None),
    # ── L9 catalysts (3 stock-level slots) — event-driven defaults ─────────
    SlotDef("L9.company.ma", "并购", "Company Catalyst", "catalyst_company", materiality=0.6, data_status="Inactive", missing_policy="inactive_zero_weight", calculation_type="or_gate", aggregation_policy="or_max_trigger", active_weight=0.0, default_missing_reason=None),
    SlotDef("L9.company.product_order", "新产品发布/大订单", "Company Catalyst", "catalyst_company", materiality=0.65, data_status="Inactive", missing_policy="inactive_zero_weight", calculation_type="or_gate", aggregation_policy="or_max_trigger", active_weight=0.0, default_missing_reason=None),
    SlotDef("L9.media.short_report", "做空报告", "Media Catalyst", "catalyst_media", direction="negative", materiality=0.7, data_status="Inactive", missing_policy="inactive_zero_weight", calculation_type="risk_factor", aggregation_policy="subtract_risk", active_weight=0.0, default_missing_reason=None),
)

# Z3 industry-level slots are inherited from industry → stock (like _X5_GROUP_B_L0_SLOTS).
_Z3_INDUSTRY_DP_IDS: frozenset[str] = frozenset(s.dp_id for s in _Z3_INDUSTRY_DERIVED_SLOTS)

ALL_DERIVED_SLOTS = (
    INDUSTRY_DERIVED_SLOTS
    + COMPANY_DERIVED_SLOTS
    + X5_DERIVED_SLOTS
    + _Z3_INDUSTRY_DERIVED_SLOTS
    + _Z3_COMPANY_DERIVED_SLOTS
)


@dataclass
class OverlayValidationResult:
    ok: bool
    stock_overlay_count: int = 0
    industry_overlay_count: int = 0
    membership_count: int = 0
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Membership:
    ts_code: str
    name: str
    industry_id: str
    primary_industry: bool
    all_industries: tuple[str, ...]
    role: str
    pool: str


def _load_yaml(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _field_governance_registry():
    global _FIELD_GOVERNANCE_CACHE, _FIELD_GOVERNANCE_LOADED
    if not _FIELD_GOVERNANCE_LOADED:
        _FIELD_GOVERNANCE_LOADED = True
        try:
            from mvp20.field_governance import load_default_governance

            _FIELD_GOVERNANCE_CACHE = load_default_governance(strict=False)
        except Exception:
            _FIELD_GOVERNANCE_CACHE = None
    return _FIELD_GOVERNANCE_CACHE


def _apply_field_governance(payload: dict[str, Any], *, overwrite: bool = False) -> dict[str, Any]:
    registry = _field_governance_registry()
    if registry is None:
        return payload
    return registry.apply_to_overlay(payload, overwrite=overwrite)


def load_industries(industries_path: Path) -> list[dict[str, Any]]:
    payload = _load_yaml(industries_path)
    return list(payload.get("industries") or [])


def active_industry_ids(industries_path: Path) -> set[str]:
    return {
        str(i["id"])
        for i in load_industries(industries_path)
        if i.get("graph_status", "present") == "present"
    }


def industry_display_names(industries_path: Path) -> dict[str, str]:
    return {
        str(i["id"]): str(i.get("display_name") or i["id"])
        for i in load_industries(industries_path)
    }


def expand_memberships(universe_path: Path, industries_path: Path) -> list[Membership]:
    universe = _load_yaml(universe_path)
    active_ids = active_industry_ids(industries_path)
    memberships: list[Membership] = []
    for c in universe.get("constituents") or []:
        industry_ids = tuple(str(x) for x in c.get("industry_ids") or [])
        for idx, industry_id in enumerate(industry_ids):
            if industry_id not in active_ids:
                continue
            memberships.append(
                Membership(
                    ts_code=str(c["ts_code"]),
                    name=str(c.get("name") or c["ts_code"]),
                    industry_id=industry_id,
                    primary_industry=(idx == 0),
                    all_industries=industry_ids,
                    role=str(c.get("role") or "target"),
                    pool=str(c.get("pool") or "regular"),
                )
            )
    return memberships


def _node_from_slot(ts_code: str, slot: SlotDef, *, inherit: bool) -> dict[str, Any]:
    node_id = f"{ts_code}:{slot.dp_id}"
    value = slot.value
    if isinstance(value, (dict, list)):
        value = json.loads(json.dumps(value, ensure_ascii=False))

    node = {
        "node_id": node_id,
        "dp_id": slot.dp_id,
        "node_name": slot.node_name,
        "node_type": slot.node_type,
        "layer": slot.layer,
        "parent_node": f"{ts_code}:company",
        "child_nodes": [],
        "direction": slot.direction,
        "base_weight": slot.base_weight,
        "active_weight": slot.active_weight,
        "strength": None,
        "confidence": None,
        "time_horizon": list(slot.time_horizon),
        "status": slot.data_status,
        "priced_in": None,
        "exposure": None,
        "financial_sensitivity": None,
        "valuation_sensitivity": None,
        "related_business": [],
        "related_metrics": list(slot.related_metrics),
        "trigger_condition": slot.trigger_condition,
        "invalidation_condition": slot.invalidation_condition,
        "data_source": None,
        "update_frequency": slot.update_frequency,
        "last_updated": None,
        "required_level": slot.required_level,
        "data_status": slot.data_status,
        "missing_policy": slot.missing_policy,
        "calculation_type": slot.calculation_type,
        "aggregation_policy": slot.aggregation_policy,
        "alert_policy": slot.alert_policy,
        "missing_reason": slot.default_missing_reason,
        "materiality": slot.materiality,
        "data_coverage": None,
        "evidence_quality": None,
        "value": value,
        "evidence_sources": [],
        "derived_slot": True,
        "inherit_from_industry": inherit,
    }
    registry = _field_governance_registry()
    return registry.apply_to_node(node) if registry else node


def _company_root_node(ts_code: str, name: str, industry_id: str) -> dict[str, Any]:
    return {
        "node_id": f"{ts_code}:company",
        "dp_id": "company",
        "node_name": name,
        "node_type": "Company",
        "layer": "company_identity",
        "parent_node": None,
        "child_nodes": [f"{ts_code}:{slot.dp_id}" for slot in ALL_DERIVED_SLOTS],
        "direction": "neutral",
        "base_weight": 1.0,
        "active_weight": 1.0,
        "strength": None,
        "confidence": 1.0,
        "time_horizon": ["short", "medium", "long"],
        "status": "Known",
        "priced_in": None,
        "exposure": None,
        "financial_sensitivity": None,
        "valuation_sensitivity": None,
        "related_business": [],
        "related_metrics": [],
        "trigger_condition": None,
        "invalidation_condition": None,
        "data_source": "config/mvp20.universe.yaml",
        "update_frequency": "quarterly",
        "last_updated": None,
        "required_level": "required",
        "data_status": "Known",
        "missing_policy": "known",
        "calculation_type": "weighted_contribution",
        "aggregation_policy": "weighted_average",
        "alert_policy": "error_if_missing",
        "missing_reason": None,
        "materiality": 1.0,
        "data_coverage": 1.0,
        "evidence_quality": 1.0,
        "value": {"industry_id": industry_id},
        "evidence_sources": ["config/mvp20.universe.yaml"],
        "derived_slot": False,
        "inherit_from_industry": False,
    }


def _hierarchy_edges(ts_code: str) -> list[dict[str, Any]]:
    groups = [
        "L0.demand.terminal",
        "L0.supply.capacity",
        "L1.position.channel_edge",
        "L2.newbiz.tam",
        "L3.customer.segment_mix",
        "L4.eff.capacity_utilization",
        "L5.surprise.buy_whisper",
    ]
    return [
        {
            "edge_id": f"HIER.{ts_code}.{idx:02d}.{dp_id.replace('.', '_')}",
            "from_node": f"{ts_code}:company",
            "to_node": f"{ts_code}:{dp_id}",
            "edge_type": "Parent-Child",
            "direction": "neutral",
            "strength": None,
            "confidence": None,
            "current_status": "active",
        }
        for idx, dp_id in enumerate(groups, start=1)
    ]


def _causal_edges(ts_code: str) -> list[dict[str, Any]]:
    specs = [
        ("demand_to_position", "L0.demand.terminal", "L1.position.channel_edge", "Demand Transmission", "positive"),
        ("pricing_power_to_surprise", "L0.price.pricing_power", "L5.surprise.buy_whisper", "Pricing Transmission", "positive"),
        ("capacity_to_utilization", "L0.supply.capacity", "L4.eff.capacity_utilization", "Capacity Constraint", "positive"),
        ("price_war_to_discount", "L0.compete.price_war", "L4.price.discount", "Competition Risk", "negative"),
        ("discount_to_whisper", "L4.price.discount", "L5.surprise.buy_whisper", "Margin Risk", "negative"),
        ("new_entrant_to_stickiness", "L0.compete.new_entrant", "L1.position.stickiness", "Share Loss Risk", "negative"),
    ]
    return [
        {
            "edge_id": f"CAUSAL.{ts_code}.{name}",
            "from_node": f"{ts_code}:{src}",
            "to_node": f"{ts_code}:{dst}",
            "edge_type": edge_type,
            "direction": direction,
            "strength": None,
            "confidence": None,
            "lag": None,
            "condition": None,
            "failure_condition": None,
            "historical_effectiveness": None,
            "evidence": [],
            "current_status": "inactive",
        }
        for name, src, dst, edge_type, direction in specs
    ]


def build_industry_overlay(
    industry_id: str,
    display_name: str,
    *,
    period: str = DEFAULT_PERIOD,
    graph_status: str = "present",
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "template_version": INDUSTRY_TEMPLATE_VERSION,
        "industry_id": industry_id,
        "industry_name_cn": display_name,
        "period": period,
        "graph_status": graph_status,
        "base_industry_graph": f"config/industry_graphs/{industry_id}.yaml",
        "nodes": [
            {
                "dp_id": slot.dp_id,
                "node_name": slot.node_name,
                "node_type": slot.node_type,
                "layer": slot.layer,
                "direction": slot.direction,
                "base_weight": slot.base_weight,
                "active_weight": slot.active_weight,
                "required_level": slot.required_level,
                "data_status": slot.data_status,
                "missing_policy": slot.missing_policy,
                "calculation_type": slot.calculation_type,
                "aggregation_policy": slot.aggregation_policy,
                "alert_policy": slot.alert_policy,
                "materiality": slot.materiality,
                "update_frequency": slot.update_frequency,
                "value": slot.value,
                "evidence_sources": [],
            }
            # X5: include the 4 net-new Group B L0 slots on the industry overlay
            # too — codex fills them at the industry level and every stock
            # overlay inherits them via inherit_from_industry=True.
            # Z3: same treatment for the 13 new industry-level slots
            # (11 L0.* + 2 L9.industry/macro).
            for slot in (
                INDUSTRY_DERIVED_SLOTS
                + _X5_GROUP_B_L0_SLOTS
                + _Z3_INDUSTRY_DERIVED_SLOTS
            )
        ],
        "coverage": _coverage_for_nodes([]),
        "notes": "Industry L0 derived slots are inherited by stock overlays and filled by agents/quarterly research.",
    }


def build_space_economy_graph_stub(display_name: str, *, period: str = DEFAULT_PERIOD) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "template_version": "industry-graph-v3.1.1-pending",
        "industry_id": PENDING_INDUSTRY_ID,
        "industry_name_cn": display_name,
        "graph_status": "pending",
        "period": period,
        "priors": {
            "boundary": {
                "scope_segments": [],
                "core_judgment": "pending industry graph authoring",
            }
        },
        "nodes": [],
        "edges": [],
        "views": {},
    }


def build_stock_overlay(
    membership: Membership,
    *,
    period: str = DEFAULT_PERIOD,
) -> dict[str, Any]:
    nodes = [
        _company_root_node(membership.ts_code, membership.name, membership.industry_id),
        *[
            _node_from_slot(
                membership.ts_code,
                slot,
                # X5 L0.* slots also inherit from industry overlay (Group B
                # is industry-level补强). Anything in INDUSTRY_DERIVED_SLOTS
                # is always inherited. Z3 industry-level slots (L0.* policy/
                # tech/cost/compete + L9.industry.* / L9.macro.*) also inherit.
                inherit=(
                    slot in INDUSTRY_DERIVED_SLOTS
                    or slot.dp_id.startswith("L0.")
                    or slot.dp_id in _Z3_INDUSTRY_DP_IDS
                ),
            )
            for slot in ALL_DERIVED_SLOTS
        ],
    ]
    hierarchy_edges = _hierarchy_edges(membership.ts_code)
    causal_edges = _causal_edges(membership.ts_code)
    coverage = _coverage_for_nodes(nodes)
    scores = _default_scores(coverage)
    views = _default_views(nodes, hierarchy_edges, causal_edges)

    return {
        "schema_version": SCHEMA_VERSION,
        "template_version": STOCK_TEMPLATE_VERSION,
        "ts_code": membership.ts_code,
        "name": membership.name,
        "industry_id": membership.industry_id,
        "primary_industry": membership.primary_industry,
        "available_industries": list(membership.all_industries),
        "role": membership.role,
        "pool": membership.pool,
        "period": period,
        "base_industry_graph": f"config/industry_graphs/{membership.industry_id}.yaml",
        "industry_overlay_ref": f"config/industry_overlays/{membership.industry_id}.yaml",
        "overlay_layers": [
            "company_identity",
            "industry_macro",
            "industry_supply",
            "industry_price",
            "industry_cost",
            "industry_competition",
            "company_position",
            "business_optionality",
            "product_market_fit",
            "customer_structure",
            "go_to_market",
            "validation_metric",
        ],
        "nodes": nodes,
        "llm_derived_slots": [
            {
                "dp_id": slot.dp_id,
                "node_name": slot.node_name,
                "required_level": slot.required_level,
                "data_status": slot.data_status,
                "missing_policy": slot.missing_policy,
                "calculation_type": slot.calculation_type,
                "aggregation_policy": slot.aggregation_policy,
                "materiality": slot.materiality,
            }
            for slot in ALL_DERIVED_SLOTS
        ],
        "hierarchy_edges": hierarchy_edges,
        "causal_edges": causal_edges,
        "coverage": coverage,
        "scores": scores,
        "views": views,
    }


def _coverage_for_nodes(nodes: list[dict[str, Any]]) -> dict[str, Any]:
    counts = {
        "known_count": 0,
        "unknown_count": 0,
        "na_count": 0,
        "inactive_count": 0,
        "low_materiality_count": 0,
        "optionality_count": 0,
        "required_missing_count": 0,
        "conditional_missing_count": 0,
    }
    applicable_materiality = 0.0
    known_materiality = 0.0
    low_confidence_paths: list[str] = []

    for node in nodes:
        status = node.get("data_status")
        materiality = float(node.get("materiality") or 0)
        if status == "Known":
            counts["known_count"] += 1
            known_materiality += materiality
            applicable_materiality += materiality
        elif status == "N/A":
            counts["na_count"] += 1
        elif status == "Unknown":
            counts["unknown_count"] += 1
            applicable_materiality += materiality
            if node.get("required_level") == "required":
                counts["required_missing_count"] += 1
            elif node.get("required_level") == "conditional_required":
                counts["conditional_missing_count"] += 1
                low_confidence_paths.append(str(node.get("dp_id")))
        elif status == "Inactive":
            counts["inactive_count"] += 1
            applicable_materiality += materiality
        elif status == "Low Materiality":
            counts["low_materiality_count"] += 1
            applicable_materiality += materiality
        elif status == "Optionality":
            counts["optionality_count"] += 1
            applicable_materiality += materiality

    data_coverage = (
        known_materiality / applicable_materiality
        if applicable_materiality > 0
        else None
    )
    return {
        "data_coverage": data_coverage,
        **counts,
        "low_confidence_paths": low_confidence_paths,
    }


def _default_scores(coverage: dict[str, Any]) -> dict[str, Any]:
    data_coverage = coverage.get("data_coverage")
    current_mode = "等待验证"
    if data_coverage is not None and data_coverage >= 0.3:
        current_mode = "可计算-低置信度"
    return {
        "node_scores": {},
        "path_scores": {
            "positive_paths": [],
            "negative_paths": [],
            "net_path_score": None,
            "formula": (
                "Direction × Event Strength × Transmission Strength × Company Exposure × "
                "Business Share × Profit Sensitivity × Confidence × Time Factor × "
                "Surprise × Funding Amplifier - Priced-in Discount - Risk Discount"
            ),
        },
        "company_score": {
            "fundamental_score": None,
            "funding_score": None,
            "risk_score": None,
            "valuation_pressure": None,
            "priced_in_discount": None,
        },
        "stock_final_score": {
            "short_score": None,
            "medium_score": None,
            "long_score": None,
            "current_mode": current_mode,
        },
    }


def _default_views(
    nodes: list[dict[str, Any]],
    hierarchy_edges: list[dict[str, Any]],
    causal_edges: list[dict[str, Any]],
) -> dict[str, Any]:
    by_layer: dict[str, list[str]] = {}
    for node in nodes:
        by_layer.setdefault(str(node.get("layer")), []).append(str(node.get("node_id")))

    causal_ids = [e["edge_id"] for e in causal_edges]
    hier_ids = [e["edge_id"] for e in hierarchy_edges]
    return {
        "causal_path": {
            "node_ids": [n["node_id"] for n in nodes if n.get("derived_slot")],
            "edge_ids": causal_ids,
            "default_depth": 3,
            "top_n": 5,
        },
        "industry_exposure": {
            "node_ids": by_layer.get("industry_macro", []) + by_layer.get("industry_supply", []),
            "edge_ids": causal_ids[:3],
            "default_depth": 3,
            "top_n": 5,
        },
        "business_breakdown": {
            "node_ids": by_layer.get("company_position", []) + by_layer.get("business_optionality", []),
            "edge_ids": hier_ids,
            "default_depth": 3,
            "top_n": 5,
        },
        "financial_expectation": {
            "node_ids": by_layer.get("expectation_gap", []) + by_layer.get("efficiency_metric", []),
            "edge_ids": causal_ids,
            "default_depth": 3,
            "top_n": 5,
        },
        "valuation_expectation": {
            "node_ids": by_layer.get("expectation_gap", []) + by_layer.get("business_optionality", []),
            "edge_ids": causal_ids,
            "default_depth": 3,
            "top_n": 5,
        },
        "risk_offset": {
            "node_ids": by_layer.get("industry_competition", []) + by_layer.get("customer_structure", []),
            "edge_ids": [e["edge_id"] for e in causal_edges if e.get("direction") == "negative"],
            "show_negative_paths": True,
        },
        "funding_sentiment": {
            "node_ids": by_layer.get("expectation_gap", []),
            "edge_ids": [],
            "default_depth": 2,
            "top_n": 5,
        },
    }


def validate_stock_overlay(payload: dict[str, Any], *, path: Path | None = None) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    label = str(path) if path else str(payload.get("ts_code") or "<overlay>")
    registry = _field_governance_registry()
    try:
        from mvp20.field_governance import FIELD_ROLES, SCORE_TARGETS
    except Exception:
        FIELD_ROLES = set()
        SCORE_TARGETS = set()

    required_top = {
        "schema_version",
        "template_version",
        "ts_code",
        "industry_id",
        "primary_industry",
        "period",
        "base_industry_graph",
        "industry_overlay_ref",
        "nodes",
        "hierarchy_edges",
        "causal_edges",
        "coverage",
        "scores",
        "views",
    }
    missing_top = sorted(required_top - set(payload))
    for key in missing_top:
        errors.append(f"{label}: missing top-level field {key}")

    if payload.get("template_version") != STOCK_TEMPLATE_VERSION:
        errors.append(f"{label}: template_version must be {STOCK_TEMPLATE_VERSION}")

    nodes = payload.get("nodes") or []
    node_ids = {n.get("node_id") for n in nodes}
    governance_missing_count = 0
    governance_unknown_count = 0
    required_node = {
        "node_id",
        "node_name",
        "node_type",
        "layer",
        "data_status",
        "missing_policy",
        "calculation_type",
        "aggregation_policy",
    }
    for node in nodes:
        node_label = f"{label}:{node.get('node_id', '<node>')}"
        missing_node = sorted(required_node - set(node))
        for key in missing_node:
            errors.append(f"{node_label}: missing node field {key}")
        status = node.get("data_status")
        if status not in DATA_STATUSES:
            errors.append(f"{node_label}: invalid data_status {status!r}")
        if node.get("required_level") not in REQUIRED_LEVELS:
            errors.append(f"{node_label}: invalid required_level {node.get('required_level')!r}")
        if node.get("missing_policy") not in MISSING_POLICIES:
            errors.append(f"{node_label}: invalid missing_policy {node.get('missing_policy')!r}")
        if node.get("calculation_type") not in CALCULATION_TYPES:
            errors.append(f"{node_label}: invalid calculation_type {node.get('calculation_type')!r}")
        if node.get("aggregation_policy") not in AGGREGATION_POLICIES:
            errors.append(f"{node_label}: invalid aggregation_policy {node.get('aggregation_policy')!r}")
        if node.get("alert_policy") not in ALERT_POLICIES:
            errors.append(f"{node_label}: invalid alert_policy {node.get('alert_policy')!r}")

        field_role = node.get("field_role")
        score_target = node.get("score_target")
        if field_role is not None and FIELD_ROLES and field_role not in FIELD_ROLES:
            errors.append(f"{node_label}: invalid field_role {field_role!r}")
        if score_target is not None and SCORE_TARGETS and score_target not in SCORE_TARGETS:
            errors.append(f"{node_label}: invalid score_target {score_target!r}")
        if registry is not None:
            dp_id = node.get("dp_id")
            if dp_id and dp_id != "company":
                if registry.get(dp_id) is None:
                    governance_unknown_count += 1
                elif not field_role or not score_target:
                    governance_missing_count += 1

        if status == "Unknown" and node.get("required_level") == "required":
            errors.append(f"{node_label}: required node is Unknown")
        if status == "Unknown" and node.get("required_level") == "conditional_required":
            warnings.append(f"{node_label}: conditional_required node is Unknown")
            if not node.get("missing_reason"):
                errors.append(f"{node_label}: Unknown node must include missing_reason")
        if status == "N/A" and node.get("missing_policy") != "not_applicable_remove":
            errors.append(f"{node_label}: N/A node must use not_applicable_remove")
        if status == "Inactive" and float(node.get("active_weight") or 0) > 0.2:
            warnings.append(f"{node_label}: Inactive node should have active_weight near 0")
        if status == "Optionality":
            value = node.get("value")
            if not isinstance(value, dict) or {
                "current_contribution",
                "future_option_value",
            } - set(value):
                errors.append(f"{node_label}: Optionality node must split current_contribution and future_option_value")

    if governance_missing_count:
        warnings.append(
            f"{label}: {governance_missing_count} node(s) missing field governance fields; registry can supplement them"
        )
    if governance_unknown_count:
        warnings.append(
            f"{label}: {governance_unknown_count} node(s) have no data_point_roles entry"
        )

    for edge in payload.get("hierarchy_edges") or []:
        edge_label = f"{label}:{edge.get('edge_id', '<edge>')}"
        if edge.get("edge_type") != "Parent-Child":
            errors.append(f"{edge_label}: hierarchy_edges must use Parent-Child")
        if "Transmission" in str(edge.get("edge_type")) or "Risk" in str(edge.get("edge_type")):
            errors.append(f"{edge_label}: causal edge_type found in hierarchy_edges")
        if edge.get("from_node") not in node_ids or edge.get("to_node") not in node_ids:
            errors.append(f"{edge_label}: hierarchy edge references unknown node")

    for edge in payload.get("causal_edges") or []:
        edge_label = f"{label}:{edge.get('edge_id', '<edge>')}"
        if edge.get("edge_type") == "Parent-Child":
            errors.append(f"{edge_label}: causal_edges cannot use Parent-Child")
        if edge.get("from_node") not in node_ids or edge.get("to_node") not in node_ids:
            errors.append(f"{edge_label}: causal edge references unknown node")

    coverage = payload.get("coverage") or {}
    scores = payload.get("scores") or {}
    final_score = scores.get("stock_final_score") or {}
    if coverage.get("data_coverage") is not None and coverage["data_coverage"] < 0.3:
        if final_score.get("current_mode") != "等待验证":
            errors.append(f"{label}: low data coverage must set current_mode to 等待验证")

    expected_views = {
        "causal_path",
        "industry_exposure",
        "business_breakdown",
        "financial_expectation",
        "valuation_expectation",
        "risk_offset",
        "funding_sentiment",
    }
    missing_views = expected_views - set(payload.get("views") or {})
    for view in sorted(missing_views):
        errors.append(f"{label}: missing view {view}")

    for layer in ("node_scores", "path_scores", "company_score", "stock_final_score"):
        if layer not in scores:
            errors.append(f"{label}: missing score layer {layer}")

    return errors, warnings


def validate_overlay_set(
    stock_overlays_dir: Path,
    industry_overlays_dir: Path,
    universe_path: Path,
    industries_path: Path,
) -> OverlayValidationResult:
    memberships = expand_memberships(universe_path, industries_path)
    errors: list[str] = []
    warnings: list[str] = []

    stock_count = 0
    for membership in memberships:
        path = stock_overlays_dir / membership.industry_id / f"{membership.ts_code}.yaml"
        if not path.exists():
            errors.append(f"missing stock overlay {path}")
            continue
        stock_count += 1
        try:
            payload = _load_yaml(path)
        except yaml.YAMLError as exc:
            errors.append(f"{path}: YAML parse error: {exc}")
            continue
        e, w = validate_stock_overlay(payload, path=path)
        errors.extend(e)
        warnings.extend(w)

    industry_count = 0
    for industry in load_industries(industries_path):
        industry_id = str(industry["id"])
        path = industry_overlays_dir / f"{industry_id}.yaml"
        if not path.exists():
            errors.append(f"missing industry overlay {path}")
        else:
            industry_count += 1

    return OverlayValidationResult(
        ok=not errors,
        stock_overlay_count=stock_count,
        industry_overlay_count=industry_count,
        membership_count=len(memberships),
        errors=errors,
        warnings=warnings,
    )


# ---------------------------------------------------------------------------
# Z1a: merge-preserve helpers — never overwrite codex-filled Known/N/A nodes.
#
# Root cause being fixed: a prior generate-overlays run regenerated 353 stock
# yamls verbatim from SLOT_DEFS, wiping out 4854 codex-filled Known cells'
# ``value``/``evidence_sources``/``confidence``/``last_updated`` fields.
#
# Design (per project owner):
#   * The preserve logic lives in ``merge_preserve_existing_overlay`` and is
#     called explicitly by ``generate_overlay_files``. Do NOT push it into
#     ``_write_yaml_if_changed`` — that helper is a generic file writer used
#     elsewhere, and tying preserve semantics to it would silently change
#     behaviour for unrelated yaml writes.
#   * Preserve rule depends on ``data_status`` × value content × event-type:
#       - Known          → preserve everything (LLM-filled fact)
#       - N/A            → preserve (LLM-judged inapplicability)
#       - Optionality    → preserve only if current_contribution/future_option_value has non-empty value
#       - Inactive       → preserve only if dp_id is NOT event-driven; event-
#                          driven Inactive ("no event right now") is transient
#                          and should refresh when new events arrive
#       - Unknown / *    → don't preserve, allow regeneration
#   * Operators can pass ``--force`` to bypass preserve entirely.
# ---------------------------------------------------------------------------

# Z5 Fix 4: EVENT_DRIVEN_DP_IDS is now derived from the single source of
# truth — ``config/llm_field_governance.yaml`` — so the merge_preserve
# "don't preserve transient Inactive" logic stays in sync with governance.
#
# Pre-Z5 root cause: the set was hardcoded inline. Governance added
# ``L0.sentiment.social`` and ``L0.compete.share_concentration`` (both
# event_driven), but they were missing from the code set; conversely
# ``L9.company.mgmt_litigation`` / ``L9.industry.compete_risk`` /
# ``L9.industry.policy_change`` lived in the code set but had no
# corresponding governance entry. The drift caused wrong merge decisions
# on overlay regenerations.
#
# Computed at import time. If governance changes mid-run, restart the
# process so the new set is picked up.
_GOVERNANCE_PATH = Path(__file__).resolve().parent.parent / "config" / "llm_field_governance.yaml"


def _load_event_driven_from_governance() -> frozenset[str]:
    """Single source of truth for event-driven dp_ids: governance yaml.

    Returns an empty frozenset if the governance file is missing or
    malformed — this is the safe default. Downstream call sites (merge
    preserve, prompt-gen) already treat an empty set as "no event-driven
    overrides" and fall back to the static-Inactive policy.
    """

    if not _GOVERNANCE_PATH.exists():
        return frozenset()
    try:
        gov = yaml.safe_load(_GOVERNANCE_PATH.read_text(encoding="utf-8"))
    except yaml.YAMLError:
        return frozenset()
    data_points = (gov or {}).get("data_points") or {}
    return frozenset(
        dp
        for dp, cfg in data_points.items()
        if isinstance(cfg, dict) and cfg.get("refresh_trigger") == "event_driven"
    )


EVENT_DRIVEN_DP_IDS: frozenset[str] = _load_event_driven_from_governance()

# Fields preserved from existing node when status warrants preservation.
_PRESERVE_FIELDS: tuple[str, ...] = (
    "value",
    "confidence",
    "evidence_sources",
    "last_updated",
    "data_source",
    "missing_reason",
    "source_fingerprint_at_fill",  # Z2: hash of source_dependencies at fill time
    "last_filled_period",          # Z2: filing period stamp for filing triggers
    "last_event_id",               # Z2: event id stamp for event_driven triggers
)


# Z5 Fix 1: canonical mapping from preserved data_status → induced state fields.
# When merge_preserve keeps an existing non-default status (N/A, Inactive,
# Optionality), the validator demands missing_policy / active_weight match the
# status semantics (see ``validate_stock_overlay``: N/A must use
# ``not_applicable_remove``, Inactive should have active_weight near 0). The
# previous merge only kept ``data_status`` itself, so SLOT_DEFS defaults
# (active_weight=1.0, missing_policy=unknown_reduce_confidence) leaked through
# and triggered validator errors / warnings on N/A and non-event Inactive nodes.
#
# Known is *not* listed: different Known dp_ids have different
# SLOT_DEFS-declared missing_policy (e.g. conditional_required Known vs optional
# Known) and the SLOT_DEFS default is the right answer post-fill.
_STATUS_INDUCED_FIELDS: dict[str, dict[str, Any]] = {
    "N/A":         {"missing_policy": "not_applicable_remove",  "active_weight": 0.0},
    "Inactive":    {"missing_policy": "inactive_zero_weight",   "active_weight": 0.0},
    "Optionality": {"missing_policy": "optionality_track"},
    # Known intentionally absent — keep SLOT_DEFS default missing_policy.
}


def _apply_status_induced_fields(merged_node: dict[str, Any], status: str) -> None:
    """When preserving a non-default status, ensure missing_policy /
    active_weight match status semantics (validator demands this)."""

    induced = _STATUS_INDUCED_FIELDS.get(status)
    if not induced:
        return
    for k, v in induced.items():
        merged_node[k] = v


def _should_preserve_node(existing_node: dict[str, Any]) -> bool:
    """Decide whether to preserve value/evidence on an existing node.

    Returns True if value/evidence_sources/etc should be kept untouched when
    the overlay is regenerated.
    """
    status = existing_node.get("data_status")
    dp_id = str(existing_node.get("dp_id") or "")

    if status == "Known":
        return True
    if status == "N/A":
        return True
    if status == "Optionality":
        value = existing_node.get("value")
        if not isinstance(value, dict):
            return False
        has_current = value.get("current_contribution") not in (None, "", {}, [])
        has_future = value.get("future_option_value") not in (None, "", {}, [])
        return has_current or has_future
    if status == "Inactive":
        # Event-driven Inactive ("currently no event") is transient and must
        # be allowed to refresh on the next regeneration.
        if dp_id in EVENT_DRIVEN_DP_IDS:
            return False
        return True
    # Unknown, Unavailable, Proxy, Low Materiality, anything else → regenerate.
    return False


def merge_preserve_existing_overlay(
    generated: dict[str, Any],
    existing: dict[str, Any] | None,
    *,
    force: bool = False,
) -> dict[str, Any]:
    """Merge regenerated overlay with existing yaml, preserving LLM-filled
    Known/N/A/non-empty-Optionality/non-event-Inactive node value & evidence.

    Args:
        generated: freshly regenerated overlay dict (full SLOT_DEFS expansion).
        existing: existing overlay dict loaded from disk, or None if no prior
            file exists (first generation).
        force: if True, skip preserve logic entirely and return ``generated``
            unchanged (operator opt-in for destructive regeneration).

    Returns:
        Merged overlay dict ready for write.
    """
    if force or existing is None:
        return generated

    existing_nodes_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    for n in existing.get("nodes") or []:
        if not isinstance(n, dict):
            continue
        key = (str(n.get("node_id") or ""), str(n.get("dp_id") or ""))
        existing_nodes_by_key[key] = n

    merged_nodes: list[dict[str, Any]] = []
    for new_node in generated.get("nodes") or []:
        if not isinstance(new_node, dict):
            merged_nodes.append(new_node)
            continue
        key = (str(new_node.get("node_id") or ""), str(new_node.get("dp_id") or ""))
        existing_node = existing_nodes_by_key.get(key)
        if existing_node is not None and _should_preserve_node(existing_node):
            # Take generated's structural fields (SLOT_DEFS metadata,
            # field governance, etc) but keep existing value/evidence/etc.
            merged = dict(new_node)
            for fname in _PRESERVE_FIELDS:
                if fname in existing_node:
                    merged[fname] = existing_node[fname]
            # CRITICAL: also preserve data_status itself. The freshly generated
            # node defaults to Unknown for most slots, but a node marked
            # Known/N/A/Optionality/Inactive by codex must keep that status.
            preserved_status: str | None = None
            if "data_status" in existing_node:
                preserved_status = existing_node["data_status"]
                merged["data_status"] = preserved_status
            # Mirror data_status into the legacy ``status`` field where present
            # so coverage/alerts stay consistent.
            if "status" in merged and preserved_status is not None:
                merged["status"] = preserved_status
            # Z5 Fix 1: when keeping a non-default status, also re-induce the
            # status-correlated state fields (missing_policy / active_weight)
            # so the merged node satisfies validator rules (e.g. N/A nodes
            # must use missing_policy=not_applicable_remove, Inactive nodes
            # must carry active_weight≈0).
            if preserved_status is not None:
                _apply_status_induced_fields(merged, preserved_status)
            merged_nodes.append(merged)
        else:
            merged_nodes.append(new_node)

    result = dict(generated)
    result["nodes"] = merged_nodes
    return result


def apply_status_induced_invariants(overlay: dict[str, Any]) -> int:
    """Ensure every node's missing_policy / active_weight / legacy ``status`` field
    match its ``data_status`` semantics (the same canonical mapping merge_preserve
    applies via ``Z5 Fix 1``). Returns the count of nodes modified.

    Runnable as a standalone post-fill pass: codex marks a node N/A by setting
    ``data_status`` AFTER the last generate-overlays, so the merge-time induction
    never sees it and the node reaches compile carrying the SLOT_DEFS default
    ``missing_policy`` → ``N/A node must use not_applicable_remove`` hard error.
    That error fails the WHOLE compile (one bad overlay starves every other stock
    of its compiled snapshot), so the onboard pipeline calls this right after the
    codex fill, before recompile.
    """
    modified = 0
    for node in overlay.get("nodes") or []:
        if not isinstance(node, dict):
            continue
        ds = node.get("data_status")
        induced = _STATUS_INDUCED_FIELDS.get(ds)
        if not induced:
            continue
        changed = False
        for k, v in induced.items():
            if node.get(k) != v:
                node[k] = v
                changed = True
        # mirror data_status into the legacy ``status`` field (validator reads
        # data_status; coverage/alerts read status — keep them consistent).
        if "status" in node and node.get("status") != ds:
            node["status"] = ds
            changed = True
        if changed:
            modified += 1
    return modified


def normalize_overlay_file_status(path: Path) -> int:
    """Load an overlay YAML, apply ``apply_status_induced_invariants``, and write
    it back (via the canonical serializer, only if changed). Returns modified
    node count (0 = no change / file absent / parse error → best-effort)."""
    try:
        overlay = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return 0
    n = apply_status_induced_invariants(overlay)
    if n:
        _write_yaml_if_changed(path, overlay)
    return n


def generate_overlay_files(
    *,
    universe_path: Path,
    industries_path: Path,
    industry_graphs_dir: Path,
    industry_overlays_dir: Path,
    stock_overlays_dir: Path,
    period: str = DEFAULT_PERIOD,
    force: bool = False,
    only_ts_code: str | None = None,
) -> dict[str, int]:
    """Generate industry + stock overlay shells.

    ``only_ts_code`` (case-insensitive) scopes generation to a single stock:
    its overlay shell(s) are (re)generated and NO other stock overlay or any
    industry overlay is touched. This is the onboarding path — a full,
    universe-wide regeneration would otherwise reset every *other* stock's
    event-driven Inactive nodes back to Unknown via merge_preserve (those
    transient Inactive nodes are intentionally NOT preserved), degrading their
    data_coverage. When ``only_ts_code`` is None the behaviour is unchanged
    (full regeneration of every industry + stock overlay).
    """
    display_names = industry_display_names(industries_path)
    industries = load_industries(industries_path)
    memberships = expand_memberships(universe_path, industries_path)
    if only_ts_code is not None:
        want = only_ts_code.upper()
        memberships = [m for m in memberships if m.ts_code.upper() == want]

    industry_overlays_dir.mkdir(parents=True, exist_ok=True)
    stock_overlays_dir.mkdir(parents=True, exist_ok=True)
    industry_graphs_dir.mkdir(parents=True, exist_ok=True)

    # Scoped single-stock generation must not rewrite other stocks' overlays —
    # and regenerating the shared industry overlays would re-touch the files
    # every stock inherits from, so skip them entirely in the scoped path.
    if only_ts_code is not None:
        for membership in memberships:
            out_dir = stock_overlays_dir / membership.industry_id
            out_dir.mkdir(parents=True, exist_ok=True)
            overlay = build_stock_overlay(membership, period=period)
            stock_path = out_dir / f"{membership.ts_code}.yaml"
            existing_stock = _load_yaml(stock_path) if stock_path.exists() else None
            merged_stock = merge_preserve_existing_overlay(
                overlay, existing_stock, force=force
            )
            _write_yaml_if_changed(stock_path, merged_stock)
        return {
            "industry_overlay_count": 0,
            "stock_overlay_count": len(memberships),
            "company_count": len((_load_yaml(universe_path).get("constituents") or [])),
        }

    for industry in industries:
        industry_id = str(industry["id"])
        graph_status = str(industry.get("graph_status") or "present")
        overlay = build_industry_overlay(
            industry_id,
            display_names[industry_id],
            period=period,
            graph_status=graph_status,
        )
        industry_path = industry_overlays_dir / f"{industry_id}.yaml"
        existing_industry = _load_yaml(industry_path) if industry_path.exists() else None
        merged_industry = merge_preserve_existing_overlay(
            overlay, existing_industry, force=force
        )
        _write_yaml_if_changed(industry_path, merged_industry)

        if graph_status == "pending":
            graph_path = industry_graphs_dir / f"{industry_id}.yaml"
            if not graph_path.exists():
                _write_yaml_if_changed(
                    graph_path,
                    build_space_economy_graph_stub(display_names[industry_id], period=period),
                )

    for membership in memberships:
        out_dir = stock_overlays_dir / membership.industry_id
        out_dir.mkdir(parents=True, exist_ok=True)
        overlay = build_stock_overlay(membership, period=period)
        stock_path = out_dir / f"{membership.ts_code}.yaml"
        existing_stock = _load_yaml(stock_path) if stock_path.exists() else None
        merged_stock = merge_preserve_existing_overlay(
            overlay, existing_stock, force=force
        )
        _write_yaml_if_changed(stock_path, merged_stock)

    return {
        "industry_overlay_count": len(industries),
        "stock_overlay_count": len(memberships),
        "company_count": len((_load_yaml(universe_path).get("constituents") or [])),
    }


def compile_overlays_to_sqlite(
    *,
    db_path: Path,
    stock_overlays_dir: Path,
    industry_overlays_dir: Path,
    universe_path: Path,
    industries_path: Path,
) -> OverlayValidationResult:
    from mvp20.storage import replace_compiled_overlays

    validation = validate_overlay_set(
        stock_overlays_dir,
        industry_overlays_dir,
        universe_path,
        industries_path,
    )
    if not validation.ok:
        return validation

    memberships = expand_memberships(universe_path, industries_path)
    by_ts: dict[str, list[str]] = {}
    for membership in memberships:
        by_ts.setdefault(membership.ts_code, []).append(membership.industry_id)

    manifests: list[dict[str, Any]] = []
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    snapshots: list[dict[str, Any]] = []
    alerts: list[dict[str, Any]] = []
    compiled_at = int(time.time())

    for membership in memberships:
        path = stock_overlays_dir / membership.industry_id / f"{membership.ts_code}.yaml"
        payload = _apply_field_governance(_load_yaml(path))
        overlay_errors, overlay_warnings = validate_stock_overlay(payload, path=path)
        if overlay_errors:
            validation.errors.extend(overlay_errors)
            continue
        manifests.append(
            {
                "ts_code": membership.ts_code,
                "industry_id": membership.industry_id,
                "overlay_path": str(path),
                "period": payload.get("period"),
                "primary_industry": 1 if membership.primary_industry else 0,
                "overlay_status": "compiled",
                "updated_at": compiled_at,
            }
        )

        overlay_alerts = _alerts_for_overlay(payload, overlay_warnings, compiled_at)
        alerts.extend(overlay_alerts)

        for node in payload.get("nodes") or []:
            nodes.append(
                {
                    "ts_code": membership.ts_code,
                    "industry_id": membership.industry_id,
                    "node_id": node["node_id"],
                    "dp_id": node.get("dp_id"),
                    "payload_json": json.dumps(node, ensure_ascii=False),
                    "data_status": node.get("data_status"),
                    "required_level": node.get("required_level"),
                    "missing_policy": node.get("missing_policy"),
                    "calculation_type": node.get("calculation_type"),
                    "aggregation_policy": node.get("aggregation_policy"),
                    "materiality": node.get("materiality"),
                    "confidence": node.get("confidence"),
                    "source_overlay_path": str(path),
                }
            )

        for edge_kind, edge_list in (
            ("hierarchy", payload.get("hierarchy_edges") or []),
            ("causal", payload.get("causal_edges") or []),
        ):
            for edge in edge_list:
                edges.append(
                    {
                        "ts_code": membership.ts_code,
                        "industry_id": membership.industry_id,
                        "edge_id": edge["edge_id"],
                        "edge_kind": edge_kind,
                        "from_node": edge.get("from_node"),
                        "to_node": edge.get("to_node"),
                        "edge_type": edge.get("edge_type"),
                        "payload_json": json.dumps(edge, ensure_ascii=False),
                    }
                )

        snapshot_payload = {
            "ts_code": membership.ts_code,
            "industry_id": membership.industry_id,
            "available_industries": by_ts.get(membership.ts_code, [membership.industry_id]),
            "compiled_graph": {
                "nodes": payload.get("nodes") or [],
                "hierarchy_edges": payload.get("hierarchy_edges") or [],
                "causal_edges": payload.get("causal_edges") or [],
                "views": payload.get("views") or {},
            },
            "scores": payload.get("scores") or {},
            "coverage": payload.get("coverage") or {},
            "alerts": overlay_alerts,
            "static_overlay": payload,
            "compiled_at": compiled_at,
        }
        snapshots.append(
            {
                "ts_code": membership.ts_code,
                "industry_id": membership.industry_id,
                "payload_json": json.dumps(snapshot_payload, ensure_ascii=False),
                "graph_version": payload.get("template_version"),
                "data_version": payload.get("period"),
                "updated_at": compiled_at,
            }
        )

    if validation.errors:
        validation.ok = False
        return validation

    replace_compiled_overlays(db_path, manifests, nodes, edges, snapshots, alerts)
    return validation


def _alerts_for_overlay(
    payload: dict[str, Any],
    validation_warnings: Iterable[str],
    created_at: int,
) -> list[dict[str, Any]]:
    alerts: list[dict[str, Any]] = []
    ts_code = str(payload.get("ts_code"))
    industry_id = str(payload.get("industry_id"))

    for node in payload.get("nodes") or []:
        status = node.get("data_status")
        required_level = node.get("required_level")
        severity = None
        code = None
        if status == "Unknown" and required_level == "required":
            severity = "ERROR"
            code = "UNKNOWN_REQUIRED"
        elif status == "Unknown" and required_level == "conditional_required":
            severity = "WARN"
            code = "UNKNOWN_CONDITIONAL_REQUIRED"
        if not severity:
            continue
        alert_id = f"{ts_code}:{industry_id}:{node.get('dp_id')}:{code}"
        alerts.append(
            {
                "alert_id": alert_id,
                "ts_code": ts_code,
                "industry_id": industry_id,
                "dp_id": node.get("dp_id"),
                "severity": severity,
                "code": code,
                "message": node.get("missing_reason") or "node data missing",
                "created_at": created_at,
                "resolved_at": None,
            }
        )

    for idx, warning in enumerate(validation_warnings):
        if "conditional_required node is Unknown" in warning:
            continue
        alerts.append(
            {
                "alert_id": f"{ts_code}:{industry_id}:validation:{idx}",
                "ts_code": ts_code,
                "industry_id": industry_id,
                "dp_id": None,
                "severity": "WARN",
                "code": "VALIDATION_WARNING",
                "message": warning,
                "created_at": created_at,
                "resolved_at": None,
            }
        )
    return alerts


def _write_yaml_if_changed(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rendered = yaml.safe_dump(
        payload,
        allow_unicode=True,
        sort_keys=False,
        width=120,
    )
    if path.exists() and path.read_text(encoding="utf-8") == rendered:
        return
    path.write_text(rendered, encoding="utf-8")
