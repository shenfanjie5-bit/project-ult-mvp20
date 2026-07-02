#!/usr/bin/env python3
"""Compare current overlay LLM fields with local non-LLM extraction candidates.

This is a read-only experiment harness. It does not call an LLM and does not
write stock overlays. The current overlay values are treated as the available
LLM baseline, while local deterministic/parser/formula/event candidates are
generated from ``runtime/hot.sqlite`` and existing project parsers.
"""

from __future__ import annotations

import argparse
import datetime as dt
import importlib
import json
import math
import re
import sqlite3
import sys
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

import yaml
from mvp20 import schema_validator

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

AUDIT_DIR = ROOT / "docs" / "audit"
TODAY = dt.date.today().isoformat()
DEFAULT_JSON_OUTPUT = AUDIT_DIR / f"{TODAY}_a_share_10_stock_llm_vs_non_llm_extractors.json"
DEFAULT_MD_OUTPUT = AUDIT_DIR / f"{TODAY}_a_share_10_stock_llm_vs_non_llm_extractors.md"
A_SHARE_SUFFIXES = (".SH", ".SZ", ".BJ")
YAML_LOADER = getattr(yaml, "CSafeLoader", yaml.SafeLoader)

LLM_TIERS = {"cheap_extract", "cheap_classify", "analysis", "web_analysis"}
AVAILABLE_STATUSES = {"Known", "Proxy", "Optionality", "Inactive", "N/A", "LowMateriality"}
UNKNOWN_STATUSES = {"Unknown", "Unavailable", None, ""}

STRICT_NO_LLM_NOW = {
    "L3.product.portfolio",
    "L3.region.domestic_overseas",
    "L3.customer.concentration",
    "L8.industry.demand_supply",
    "L8.industry.price_war",
    "L9.media.short_report",
    "L8.shock.crisis",
    "L9.company.ma",
    "L9.company.product_order",
}

WEB_ANALYSIS_FIELDS = {
    "L2.newbiz.tam",
    "L3.delivery.csat",
    "L3.delivery.lead_time",
    "L3.product.lifecycle",
    "L4.eff.conversion_retention",
    "L4.share.customer_channel",
    "L4.volume.foot_traffic",
    "L4.volume.frequency",
}

KEEP_LLM_LOCAL_FIELDS = {
    "L1.position.brand",
    "L1.position.channel_edge",
    "L1.position.cost_edge",
    "L1.position.pricing_power",
    "L1.position.stickiness",
    "L1.position.tech_barrier",
    "L2.newbiz.commercialization",
    "L2.newbiz.revenue_contrib",
    "L2.newbiz.uncertainty",
    "L2.newbiz.valuation_contrib",
    "L2.segment.business_risk",
    "L2.segment.compete_landscape",
    "L3.region.key_risk",
    "L4.price.subscription",
    "L5.surprise.buy_whisper",
}

SCRIPT_FILL_FIELDS = {
    "L3.product.portfolio",
    "L3.region.domestic_overseas",
    "L3.customer.concentration",
}

CHEAP_EXTRACT_FIELDS = {
    "L1.role.tag",
    "L1.model.tag",
    "L1.moat.tags",
    "L1.stock_attr.tags",
    "L1.position.growth_rank",
    "L3.channel.mix",
}

FORMULA_FIRST_FIELDS = {
    "L1.position.market_share",
    "L2.segment.industry_exposure",
    "L2.segment.cash_contrib",
    "L2.segment.opex_ratio",
    "L2.segment.profit_share",
    "L3.channel.cost",
    "L3.channel.efficiency",
    "L3.channel.overseas",
    "L3.customer.segment_mix",
    "L3.customer.solvency",
    "L3.delivery.capacity_supply",
    "L3.delivery.fulfillment_cost",
    "L3.product.margin_mix",
    "L3.region.fx_geo",
    "L3.region.tier_mix",
    "L4.cost.cac_production",
    "L4.cost.rent_energy_logistics",
    "L4.eff.capacity_utilization",
    "L4.eff.store_labor",
    "L4.price.asp_aov_arpu",
    "L4.price.discount",
    "L4.price.elasticity",
    "L4.price.pricing_power",
    "L4.share.market",
    "L4.share.substitution",
    "L4.volume.orders",
    "L4.volume.sales",
    "L4.volume.shipments",
    "L4.volume.users",
    "L5.fcst.beat_probability",
    "L8.gov.fraud_control",
    "L8.gov.litigation",
}

EVENT_PATTERNS: dict[str, tuple[str, ...]] = {
    "L8.industry.demand_supply": ("需求下滑", "供给过剩", "库存高企", "产能过剩", "订单下降", "供需恶化"),
    "L8.industry.price_war": ("价格战", "降价", "促销", "打折", "价格下调"),
    "L8.industry.substitute": ("替代", "取代", "新技术", "替代品", "颠覆"),
    "L8.op.customer_channel": ("客户流失", "渠道失效", "渠道调整", "大客户减少", "客户减少"),
    "L8.op.order_miss": ("订单不及预期", "订单取消", "订单延迟", "不兑现", "低于预期"),
    "L8.op.product_fail": ("产品失败", "召回", "质量问题", "延期发布", "研发失败"),
    "L8.reg.license_risk": ("牌照", "许可", "准入", "审批", "资质"),
    "L8.reg.subsidy_off": ("补贴退坡", "补贴取消", "补贴下降", "退坡"),
    "L8.reg.tax_trade": ("关税", "出口管制", "贸易限制", "制裁", "汇率"),
    "L8.reg.tighten": ("监管", "新规", "整改", "反垄断", "处罚", "合规"),
    "L8.shock.black_swan": ("黑天鹅", "战争", "袭击", "爆炸", "重大事故", "不可抗力"),
    "L8.shock.crisis": ("舆情危机", "安全事故", "质量事故", "消费者投诉", "危机"),
    "L8.shock.supply_break": ("供应中断", "断供", "停产", "物流中断", "短缺", "封锁"),
    "L9.company.ma": ("并购", "收购", "重组", "资产注入", "重大资产"),
    "L9.company.product_order": ("大订单", "中标", "新产品", "发布", "量产", "交付"),
    "L9.industry.data_price": ("价格指数", "行业数据", "CPI", "PPI", "PMI", "销量数据"),
    "L9.macro.geo": ("地缘", "战争", "冲突", "制裁", "霍尔木兹", "关税"),
    "L9.media.short_report": ("做空报告", "沽空报告", "卖空报告", "short seller", "short report"),
    "L8.gov.fraud_control": ("财务造假", "内控缺陷", "会计差错", "立案调查", "审计意见"),
    "L8.gov.litigation": ("诉讼", "仲裁", "被告", "判决", "执行", "处罚"),
}

FINANCIAL_SERVICE_MARKERS = (
    "FINANCIAL",
    "证券",
    "券商",
    "银行",
    "保险",
    "金融",
    "资管",
    "资产管理",
    "投资银行",
    "财富管理",
    "融资融券",
    "期货",
    "基金",
    "信托",
)
FINANCIAL_PRICE_SIGNAL_PATTERNS = (
    ("融资融券利率随市场利率下行", "rate_down"),
    ("融资融券利率", "rate_down"),
    ("市场利率下行", "rate_down"),
    ("费率下降", "rate_down"),
    ("佣金率下降", "rate_down"),
    ("佣金费率", "fee_pressure"),
    ("利差收窄", "spread_pressure"),
    ("收益率下行", "yield_down"),
    ("费率下行", "rate_down"),
)
LITIGATION_STRONG_PATTERNS = (
    "诉讼",
    "仲裁",
    "被告",
    "原告",
    "判决",
    "裁定",
    "法院",
    "立案",
    "涉诉",
    "执行案件",
    "强制执行",
    "申请执行",
    "被执行人",
    "失信被执行",
    "行政处罚",
    "罚款",
)
LITIGATION_EXECUTION_CONTEXT = (
    "案件",
    "法院",
    "裁定",
    "判决",
    "强制",
    "申请",
    "被执行",
    "失信",
    "执行人",
    "执行通知",
    "执行异议",
    "执行和解",
)


@dataclass(frozen=True)
class OverlayInfo:
    ts_code: str
    industry_id: str
    name: str
    path: Path


@dataclass(frozen=True)
class RuntimeRow:
    value: Any
    data_status: str
    source: str | None
    updated_at: Any = None


def _load_yaml(path: Path) -> dict[str, Any]:
    payload = yaml.load(path.read_text(encoding="utf-8"), Loader=YAML_LOADER)
    return payload if isinstance(payload, dict) else {}


def _load_jsonish(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (dict, list, int, float, bool)):
        return value
    try:
        return json.loads(str(value))
    except (TypeError, ValueError):
        return value


def _json_safe(value: Any) -> Any:
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, Mapping):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_safe(v) for v in value]
    if isinstance(value, tuple):
        return [_json_safe(v) for v in value]
    if isinstance(value, set):
        return sorted(_json_safe(v) for v in value)
    return value


def _is_a_share_ts_code(ts_code: str) -> bool:
    return ts_code.endswith(A_SHARE_SUFFIXES)


def _overlay_infos(root: Path) -> list[OverlayInfo]:
    out: list[OverlayInfo] = []
    for path in sorted((root / "config" / "stock_overlays").glob("*/*.yaml")):
        ts_code = path.stem
        if not _is_a_share_ts_code(ts_code):
            continue
        header: dict[str, str] = {}
        for line in path.read_text(encoding="utf-8").splitlines()[:40]:
            if line.startswith("ts_code: "):
                header["ts_code"] = line.split(": ", 1)[1].strip()
            elif line.startswith("industry_id: "):
                header["industry_id"] = line.split(": ", 1)[1].strip()
            elif line.startswith("name: "):
                header["name"] = line.split(": ", 1)[1].strip()
        out.append(
            OverlayInfo(
                ts_code=header.get("ts_code") or ts_code,
                industry_id=header.get("industry_id") or path.parent.name,
                name=header.get("name") or "",
                path=path,
            )
        )
    return out


def _llm_scope(
    root: Path,
    *,
    include_cheap_extract: bool,
    include_l0: bool = False,
) -> dict[str, dict[str, Any]]:
    governance = _load_yaml(root / "config" / "llm_field_governance.yaml")
    data_points = governance.get("data_points") or {}
    out: dict[str, dict[str, Any]] = {}
    for dp_id, entry in data_points.items():
        if not include_l0 and str(dp_id).startswith("L0."):
            continue
        if entry.get("route") not in {"llm_close", "llm_web"}:
            continue
        tier = entry.get("model_tier")
        if tier not in LLM_TIERS:
            continue
        if tier == "cheap_extract" and not include_cheap_extract:
            continue
        out[str(dp_id)] = dict(entry)
    return dict(sorted(out.items()))


def _field_roles(root: Path) -> dict[str, dict[str, Any]]:
    payload = _load_yaml(root / "config" / "data_point_roles.yaml")
    data_points = payload.get("data_points") or {}
    return {str(k): dict(v) for k, v in data_points.items()}


def _nodes_by_dp(path: Path) -> dict[str, dict[str, Any]]:
    overlay = _load_yaml(path)
    nodes = overlay.get("nodes") or []
    out: dict[str, dict[str, Any]] = {}
    for node in nodes:
        if isinstance(node, Mapping) and node.get("dp_id"):
            out[str(node["dp_id"])] = dict(node)
    return out


def _available(status: Any) -> bool:
    return str(status or "") in AVAILABLE_STATUSES


def _candidate(
    *,
    data_status: str,
    value: Any = None,
    method: str,
    quality: str,
    category: str,
    confidence: float = 0.0,
    evidence_sources: list[dict[str, Any]] | None = None,
    reason: str | None = None,
) -> dict[str, Any]:
    return {
        "data_status": data_status,
        "value": _json_safe(value),
        "method": method,
        "quality": quality,
        "category": category,
        "confidence": round(max(0.0, min(1.0, confidence)), 4),
        "evidence_sources": evidence_sources or [],
        "reason": reason,
    }


def _runtime_get(
    conn: sqlite3.Connection,
    ts_codes: Iterable[str],
    dp_id: str,
) -> RuntimeRow | None:
    for ts_code in ts_codes:
        row = conn.execute(
            """
            SELECT value_json, data_status, source, updated_at
            FROM realtime_current
            WHERE ts_code = ? AND dp_id = ?
            """,
            (ts_code, dp_id),
        ).fetchone()
        if not row:
            continue
        return RuntimeRow(
            value=_load_jsonish(row[0]),
            data_status=str(row[1] or "Unknown"),
            source=str(row[2]) if row[2] is not None else None,
            updated_at=row[3],
        )
    return None


def _source_ts_codes(info: OverlayInfo) -> list[str]:
    return [info.ts_code, f"INDUSTRY:{info.industry_id}", "MARKET:CN"]


def _runtime_text(row: RuntimeRow | None) -> str:
    if row is None:
        return ""
    value = row.value
    if isinstance(value, Mapping):
        parts: list[str] = []
        for key, item in value.items():
            if isinstance(item, (str, int, float)):
                parts.append(f"{key}: {item}")
            elif isinstance(item, list):
                parts.append(f"{key}: {json.dumps(item[:6], ensure_ascii=False)}")
            elif isinstance(item, Mapping):
                parts.append(f"{key}: {json.dumps(item, ensure_ascii=False)[:1000]}")
        return "\n".join(parts)
    return str(value)


def _annual_sections(row: RuntimeRow | None) -> dict[str, str]:
    if row is None or not isinstance(row.value, Mapping):
        return {}
    sections = row.value.get("sections")
    return {str(k): str(v) for k, v in sections.items()} if isinstance(sections, Mapping) else {}


def _floatish(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        f = float(value)
        return f if math.isfinite(f) else None
    if isinstance(value, str):
        text = value.strip().replace(",", "")
        if text.endswith("%"):
            text = text[:-1]
        try:
            f = float(text)
        except ValueError:
            return None
        return f if math.isfinite(f) else None
    return None


SCALAR_KEYS = (
    "score",
    "scalar",
    "value",
    "yoy_pct",
    "consensus_eps_revision_30d_pct",
    "sga_rd_ratio_revenue",
    "gross_margin",
    "domestic_pct",
    "share_pct",
    "avg_discount_pct",
    "utilization_pct",
    "top5_pct",
    "eps_avg",
)


def _scalar(value: Any) -> float | None:
    f = _floatish(value)
    if f is not None:
        return f
    if isinstance(value, Mapping):
        for key in SCALAR_KEYS:
            if key in value:
                f = _floatish(value.get(key))
                if f is not None:
                    return f
        for item in value.values():
            if isinstance(item, Mapping):
                f = _scalar(item)
                if f is not None:
                    return f
    return None


def _runtime_scalar(conn: sqlite3.Connection, info: OverlayInfo, dp_id: str) -> float | None:
    row = _runtime_get(conn, _source_ts_codes(info), dp_id)
    return _scalar(row.value) if row else None


def _runtime_available(conn: sqlite3.Connection, info: OverlayInfo, dp_id: str) -> RuntimeRow | None:
    row = _runtime_get(conn, _source_ts_codes(info), dp_id)
    return row if row and _available(row.data_status) else None


def _ev(dp_id: str, row: RuntimeRow | None = None) -> list[dict[str, Any]]:
    source = row.source if row else None
    return [{"kind": "local_dp_id", "dp_id": dp_id, "source": source or "runtime"}]


def _full_runtime_text(dp_id: str, row: RuntimeRow | None) -> str:
    if row is None:
        return ""
    if dp_id == "L9.disclosure.annual_report":
        sections = _annual_sections(row)
        if sections:
            return "\n".join(sections.values())
    return _runtime_text(row)


def _local_text_and_evidence(
    conn: sqlite3.Connection,
    info: OverlayInfo,
    dp_ids: Iterable[str],
) -> tuple[str, list[dict[str, Any]]]:
    chunks: list[str] = []
    evidence: list[dict[str, Any]] = []
    for dp_id in dp_ids:
        row = _runtime_get(conn, _source_ts_codes(info), dp_id)
        if row is None:
            continue
        chunks.append(_full_runtime_text(dp_id, row))
        evidence.append(_ev(dp_id, row)[0])
    return "\n".join(chunk for chunk in chunks if chunk), evidence


def _is_financial_service(info: OverlayInfo, text: str = "") -> bool:
    haystack = f"{info.industry_id}\n{info.name}\n{text}".casefold()
    return any(marker.casefold() in haystack for marker in FINANCIAL_SERVICE_MARKERS)


def _event_keyword_hits(dp_id: str, text: str) -> list[str]:
    lowered = text.casefold()
    if dp_id != "L8.gov.litigation":
        return [pattern for pattern in EVENT_PATTERNS.get(dp_id, ()) if pattern.casefold() in lowered]

    hits = [pattern for pattern in LITIGATION_STRONG_PATTERNS if pattern.casefold() in lowered]
    if "执行" not in text:
        return hits

    for match in re.finditer("执行", text):
        start = max(0, match.start() - 12)
        end = min(len(text), match.end() + 24)
        context = text[start:end]
        if any(marker in context for marker in LITIGATION_EXECUTION_CONTEXT):
            hits.append("执行")
            break
    return sorted(set(hits), key=hits.index)


def _financial_price_signal(
    info: OverlayInfo,
    conn: sqlite3.Connection,
) -> dict[str, Any] | None:
    text, evidence = _local_text_and_evidence(
        conn,
        info,
        ("L1.company.main_business", "L9.disclosure.annual_report", "L9.disclosure.qa_recent"),
    )
    if not _is_financial_service(info, text):
        return None
    for pattern, trend in FINANCIAL_PRICE_SIGNAL_PATTERNS:
        if pattern in text:
            segment_gm = _segment_rows(_runtime_available(conn, info, "L2.segment.gross_margin"), "gross_margin_pct")
            high_margin_segments = [
                {"name": item["item"], "gross_margin_pct": item["gross_margin_pct"]}
                for item in segment_gm
                if float(item["gross_margin_pct"]) >= 50.0
            ][:3]
            return {
                "pattern": pattern,
                "trend": trend,
                "evidence_sources": evidence,
                "high_margin_segments": high_margin_segments,
            }
    return None


def _product_portfolio_from_business_candidate(info: OverlayInfo, conn: sqlite3.Connection) -> dict[str, Any]:
    row = _runtime_get(conn, _source_ts_codes(info), "L1.company.main_business")
    value = row.value if row else None
    text = ""
    if isinstance(value, Mapping):
        text = str(value.get("main_business") or value.get("business_scope") or "")
    elif value is not None:
        text = str(value)
    lines = [line.strip() for line in text.replace("\r", "\n").split("\n") if line.strip()]
    source_line = lines[0] if lines else ""
    if not source_line:
        return _candidate(
            data_status="Unknown",
            method="main_business_product_parser",
            quality="source_missing",
            category="parser_formula_first",
            reason="missing L1.company.main_business",
        )

    normalized = re.sub(r"^(主要业务|主营业务|公司主营业务|公司主要从事|主要从事)[为包括：:]*", "", source_line)
    parts = [
        part.strip(" 、，,；;。")
        for part in re.split(r"[、，,；;]|以及|和", normalized)
        if part.strip(" 、，,；;。")
    ]
    products: list[dict[str, Any]] = []
    seen: set[str] = set()
    for part in parts:
        if len(part) < 3 or any(skip in part for skip in ("其他业务", "业务范围", "依法须经批准")):
            continue
        if part in seen:
            continue
        seen.add(part)
        products.append({"name": part, "revenue_pct": None})
    if len(products) < 2:
        return _candidate(
            data_status="Unknown",
            method="main_business_product_parser",
            quality="parser_not_implemented",
            category="parser_formula_first",
            confidence=0.0,
            evidence_sources=_ev("L1.company.main_business", row),
            reason="main business text does not expose an enumerable product list",
        )
    return _candidate(
        data_status="Known",
        value={
            "products": products[:8],
            "evidence_summary": "主营业务文本直接列示业务线；未披露收入占比时 revenue_pct 保持为空。",
            "notes": "按本地 L1.company.main_business 业务线枚举生成产品组合候选。",
        },
        method="main_business_product_parser",
        quality="direct_parser",
        category="parser_formula_first",
        confidence=0.68,
        evidence_sources=_ev("L1.company.main_business", row),
    )


def _domestic_overseas_from_business_candidate(info: OverlayInfo, conn: sqlite3.Connection) -> dict[str, Any]:
    business_row = _runtime_get(conn, _source_ts_codes(info), "L1.company.main_business")
    value = business_row.value if business_row else None
    text = ""
    if isinstance(value, Mapping):
        text = str(value.get("main_business") or value.get("business_scope") or "")
    elif value is not None:
        text = str(value)

    has_domestic = any(marker in text for marker in ("境内", "国内", "中国大陆", "内地"))
    has_overseas = any(marker in text for marker in ("境外", "海外", "国际", "国外"))
    if not (has_domestic and has_overseas):
        return _candidate(
            data_status="Unknown",
            method="main_business_region_parser",
            quality="parser_not_implemented",
            category="parser_formula_first",
            confidence=0.0,
            evidence_sources=_ev("L1.company.main_business", business_row) if business_row else [],
            reason="main business text does not directly expose both domestic and overseas business lines",
        )

    revenue_row = _runtime_get(conn, _source_ts_codes(info), "L5.is.revenue")
    total_revenue = _scalar(revenue_row.value) if revenue_row else None
    evidence = _ev("L1.company.main_business", business_row)
    if revenue_row:
        evidence.extend(_ev("L5.is.revenue", revenue_row))
    return _candidate(
        data_status="Known",
        value={
            "domestic_pct": None,
            "overseas_pct": None,
            "total_revenue_cny": total_revenue,
            "evidence_summary": "主营业务文本同时列示境内和境外业务；未披露境内外收入占比时占比保持为空。",
            "notes": "仅确认境内外业务存在，不把业务存在性伪装成收入结构。",
        },
        method="main_business_region_parser",
        quality="direct_parser",
        category="parser_formula_first",
        confidence=0.58 if total_revenue is None else 0.62,
        evidence_sources=evidence,
    )


def _clip01(value: float) -> float:
    return max(0.0, min(1.0, value))


def _signed_clip(value: float, scale: float) -> float:
    if scale <= 0:
        return 0.0
    return max(-1.0, min(1.0, value / scale))


def _peer_stats(
    conn: sqlite3.Connection,
    infos: list[OverlayInfo],
) -> dict[str, dict[str, Any]]:
    industry_by_ts = {info.ts_code: info.industry_id for info in infos}
    rows = conn.execute(
        """
        SELECT ts_code, dp_id, value_json, data_status
        FROM realtime_current
        WHERE dp_id IN ('L5.is.revenue', 'L5.is.revenue_growth', 'L5.fina.revenue_yoy')
          AND (ts_code LIKE '%.SH' OR ts_code LIKE '%.SZ' OR ts_code LIKE '%.BJ')
        """
    ).fetchall()
    by_ts: dict[str, dict[str, float]] = defaultdict(dict)
    for ts_code, dp_id, value_json, status in rows:
        if ts_code not in industry_by_ts or status not in {"Known", "Proxy"}:
            continue
        value = _scalar(_load_jsonish(value_json))
        if value is not None:
            by_ts[str(ts_code)][str(dp_id)] = value

    grouped_revenue: dict[str, list[tuple[str, float]]] = defaultdict(list)
    grouped_growth: dict[str, list[tuple[str, float]]] = defaultdict(list)
    for ts_code, values in by_ts.items():
        industry = industry_by_ts[ts_code]
        if "L5.is.revenue" in values:
            grouped_revenue[industry].append((ts_code, values["L5.is.revenue"]))
        growth = values.get("L5.is.revenue_growth", values.get("L5.fina.revenue_yoy"))
        if growth is not None:
            grouped_growth[industry].append((ts_code, growth))

    out: dict[str, dict[str, Any]] = {}
    for info in infos:
        values = by_ts.get(info.ts_code, {})
        industry = info.industry_id
        rev_rank = None
        rev_share = None
        rev_peers = sorted(grouped_revenue.get(industry, []), key=lambda x: x[1], reverse=True)
        total_revenue = sum(max(v, 0.0) for _, v in rev_peers)
        for idx, (ts_code, revenue) in enumerate(rev_peers, 1):
            if ts_code == info.ts_code:
                rev_rank = idx
                rev_share = (100.0 * revenue / total_revenue) if total_revenue > 0 else None
                break
        growth_rank = None
        growth_peers = sorted(grouped_growth.get(industry, []), key=lambda x: x[1], reverse=True)
        for idx, (ts_code, _) in enumerate(growth_peers, 1):
            if ts_code == info.ts_code:
                growth_rank = idx
                break
        out[info.ts_code] = {
            "revenue": values.get("L5.is.revenue"),
            "revenue_growth": values.get("L5.is.revenue_growth", values.get("L5.fina.revenue_yoy")),
            "revenue_rank": rev_rank,
            "revenue_share_pct": rev_share,
            "revenue_peer_count": len(rev_peers),
            "growth_rank": growth_rank,
            "growth_peer_count": len(growth_peers),
        }
    return out


def _select_samples(
    infos: list[OverlayInfo],
    scope: Mapping[str, Any],
    *,
    sample_size: int,
) -> list[OverlayInfo]:
    scored: list[tuple[int, int, str, OverlayInfo]] = []
    target_dp_ids = set(scope)
    for info in infos:
        try:
            nodes = _nodes_by_dp(info.path)
        except Exception:
            continue
        available = sum(
            1
            for dp_id in target_dp_ids
            if _available((nodes.get(dp_id) or {}).get("data_status"))
        )
        known = sum(
            1
            for dp_id in target_dp_ids
            if (nodes.get(dp_id) or {}).get("data_status") in {"Known", "Proxy", "Optionality"}
        )
        scored.append((available, known, info.ts_code, info))
    scored.sort(key=lambda item: (-item[0], -item[1], item[2]))

    selected: list[OverlayInfo] = []
    seen_industries: set[str] = set()
    for _, _, _, info in scored:
        if info.industry_id in seen_industries:
            continue
        selected.append(info)
        seen_industries.add(info.industry_id)
        if len(selected) >= sample_size:
            return selected
    for _, _, _, info in scored:
        if info in selected:
            continue
        selected.append(info)
        if len(selected) >= sample_size:
            break
    return selected


def _script_fill_candidates(info: OverlayInfo, db_path: Path) -> dict[str, dict[str, Any]]:
    try:
        module = importlib.import_module("scripts.script_fill")
        extracted = module.extract(
            info.ts_code,
            db_path=db_path,
            include_catalysts=False,
            include_management_change=False,
        )
    except Exception as exc:  # noqa: BLE001
        return {
            dp_id: _candidate(
                data_status="Unknown",
                method="script_fill_error",
                quality="blocked",
                category="existing_deterministic_parser",
                reason=str(exc)[:200],
            )
            for dp_id in SCRIPT_FILL_FIELDS
        }
    out: dict[str, dict[str, Any]] = {}
    for dp_id, payload in extracted.items():
        if dp_id not in SCRIPT_FILL_FIELDS:
            continue
        value = payload.get("value")
        if dp_id == "L3.product.portfolio" and isinstance(value, Mapping):
            value = {
                "products": value.get("products") or [],
                "notes": value.get("source") or "script_fill product parser",
            }
        elif dp_id == "L3.customer.concentration" and isinstance(value, Mapping):
            value = {
                "top5_revenue_pct": value.get("top5_pct"),
                "top10_revenue_pct": None,
                "concentration_trend": None,
                "notes": value.get("source") or "script_fill customer concentration parser",
            }
        out[dp_id] = _candidate(
            data_status=str(payload.get("data_status") or "Known"),
            value=value,
            method="script_fill",
            quality="direct_parser",
            category="existing_deterministic_parser",
            confidence=0.85,
            evidence_sources=payload.get("evidence_sources") or [],
        )
    return out


def _tag_candidate(dp_id: str, info: OverlayInfo, conn: sqlite3.Connection) -> dict[str, Any]:
    main_row = _runtime_get(conn, [info.ts_code], "L1.company.main_business")
    path_row = _runtime_get(conn, [info.ts_code], "L6.path.tag")
    text = f"{info.industry_id}\n{_runtime_text(main_row)}\n{_runtime_text(path_row)}"
    if not text.strip():
        return _candidate(
            data_status="Unknown",
            method="rule_tagging",
            quality="source_missing",
            category="cheap_extract_rule",
            reason="missing main business text",
        )
    tags: list[str] = []
    if dp_id == "L1.role.tag":
        if any(word in text for word in ("设备", "制造", "生产", "材料", "电池", "钢铁", "医药")):
            tags.append("制造/供给")
        if any(word in text for word in ("平台", "服务", "云", "软件", "运营")):
            tags.append("平台/服务")
        if any(word in text for word in ("港口", "物流", "运输")):
            tags.append("基础设施/物流")
    elif dp_id == "L1.model.tag":
        if any(word in text for word in ("订阅", "SaaS", "云服务")):
            tags.append("订阅/云服务")
        if any(word in text for word in ("销售", "生产", "制造")):
            tags.append("产品销售")
        if any(word in text for word in ("工程", "项目", "交付")):
            tags.append("项目交付")
    elif dp_id == "L1.moat.tags":
        if any(word in text for word in ("专利", "研发", "技术", "算法", "创新")):
            tags.append("技术")
        if any(word in text for word in ("龙头", "领先", "全球", "行业领先")):
            tags.append("规模/品牌")
        if any(word in text for word in ("客户", "渠道", "生态")):
            tags.append("客户/渠道")
    elif dp_id == "L1.stock_attr.tags":
        growth = _runtime_scalar(conn, info, "L5.is.revenue_growth")
        if growth is not None:
            tags.append("高增长" if growth >= 20 else "稳增长" if growth >= 0 else "承压")
        if info.industry_id in {"FINANCIAL_HIGH_DIVIDEND"}:
            tags.append("高股息")
        if info.industry_id in {"AI_COMPUTE", "ROBOTICS", "SEMI_EQUIPMENT"}:
            tags.append("科技成长")
    if not tags:
        tags.append(info.industry_id.lower())
    return _candidate(
        data_status="Proxy",
        value={"tags": sorted(set(tags)), "notes": "非LLM关键词标签，仅作候选"},
        method="rule_tagging",
        quality="weak_proxy",
        category="cheap_extract_rule",
        confidence=0.55,
        evidence_sources=_ev("L1.company.main_business", main_row),
    )


def _growth_rank_candidate(info: OverlayInfo, peer: Mapping[str, Any]) -> dict[str, Any]:
    growth = peer.get("revenue_growth")
    if growth is None:
        return _candidate(
            data_status="Unknown",
            method="peer_growth_rank",
            quality="source_missing",
            category="cheap_extract_formula",
            reason="missing revenue growth",
        )
    trend = "modest_growth" if float(growth) > 0 else "decline" if float(growth) < 0 else "mixed"
    return _candidate(
        data_status="Proxy",
        value={
            "rank": peer.get("growth_rank"),
            "share_pct": None,
            "trend": trend,
            "source_year": "latest_runtime",
            "market_size_unit": None,
            "evidence_summary": f"收入同比 {float(growth):.2f}%，行业内增速排名 {peer.get('growth_rank')}/{peer.get('growth_peer_count')}",
            "notes": "非LLM收入增速排名代理，不含直接市占率证据",
        },
        method="peer_growth_rank",
        quality="proxy",
        category="cheap_extract_formula",
        confidence=0.62,
        evidence_sources=[{"kind": "local_dp_id", "dp_id": "L5.is.revenue_growth", "source": "runtime"}],
    )


def _channel_mix_candidate(info: OverlayInfo, conn: sqlite3.Connection) -> dict[str, Any]:
    ar_row = _runtime_get(conn, [info.ts_code], "L9.disclosure.annual_report")
    sections = _annual_sections(ar_row)
    text = "\n".join(sections.values())
    parsed = _parse_channel_mix_from_text(text) if text else None
    if parsed:
        total = sum(v for k, v in parsed.items() if k.endswith("_pct"))
        status = "Known" if 95 <= total <= 105 else "Proxy"
        return _candidate(
            data_status=status,
            value={
                **parsed,
                "trend": None,
                "notes": "年报销售模式/渠道结构表解析",
            },
            method="channel_mix_regex",
            quality="direct_parser" if status == "Known" else "parser_proxy",
            category="cheap_extract_parser",
            confidence=0.82 if status == "Known" else 0.64,
            evidence_sources=_ev("L9.disclosure.annual_report", ar_row),
        )
    business_row = _runtime_get(conn, [info.ts_code], "L1.company.main_business")
    qa_row = _runtime_get(conn, [info.ts_code], "L9.disclosure.qa_recent")
    proxy_text = f"{info.industry_id}\n{_runtime_text(business_row)}\n{_runtime_text(qa_row)}\n{text[:2000]}"
    proxy = _channel_mix_proxy_from_business_text(proxy_text)
    if proxy:
        evidence = []
        if business_row:
            evidence.append(_ev("L1.company.main_business", business_row)[0])
        if qa_row:
            evidence.append(_ev("L9.disclosure.qa_recent", qa_row)[0])
        if ar_row:
            evidence.append(_ev("L9.disclosure.annual_report", ar_row)[0])
        return _candidate(
            data_status="Proxy",
            value=proxy,
            method="channel_mix_business_proxy",
            quality="business_model_proxy",
            category="cheap_extract_parser",
            confidence=0.58,
            evidence_sources=evidence,
        )
    if not text:
        return _candidate(
            data_status="Unknown",
            method="channel_mix_regex",
            quality="source_missing",
            category="cheap_extract_parser",
            reason="missing annual report sections and business proxy did not match",
        )
    if re.search(r"(销售模式|销售渠道).{0,30}(均为|全部|全部采用)直销", text):
        return _candidate(
            data_status="Known",
            value={
                "direct_pct": 100.0,
                "distributor_pct": 0.0,
                "ecommerce_pct": 0.0,
                "others_pct": 0.0,
                "trend": None,
                "notes": "年报文本披露销售模式以直销为主",
            },
            method="channel_mix_regex",
            quality="direct_parser",
            category="cheap_extract_parser",
            confidence=0.78,
            evidence_sources=_ev("L9.disclosure.annual_report", ar_row),
        )
    if re.search(r"(销售模式|销售渠道).{0,40}主要(采用|为|通过).{0,10}直销", text):
        return _candidate(
            data_status="Proxy",
            value={
                "direct_pct": None,
                "distributor_pct": None,
                "ecommerce_pct": None,
                "others_pct": None,
                "trend": None,
                "notes": "dominant_channel=direct；年报文本显示以直销为主，但未披露可加总百分比",
            },
            method="channel_mix_regex",
            quality="text_proxy",
            category="cheap_extract_parser",
            confidence=0.58,
            evidence_sources=_ev("L9.disclosure.annual_report", ar_row),
        )
    if re.search(r"(销售模式|销售渠道).{0,40}主要(采用|为|通过).{0,10}(经销|分销|代理)", text):
        return _candidate(
            data_status="Proxy",
            value={
                "direct_pct": None,
                "distributor_pct": None,
                "ecommerce_pct": None,
                "others_pct": None,
                "trend": None,
                "notes": "dominant_channel=distributor；年报文本显示以经销/分销为主，但未披露可加总百分比",
            },
            method="channel_mix_regex",
            quality="text_proxy",
            category="cheap_extract_parser",
            confidence=0.58,
            evidence_sources=_ev("L9.disclosure.annual_report", ar_row),
        )
    return _candidate(
        data_status="Unknown",
        method="channel_mix_regex",
        quality="no_direct_channel_mix",
        category="cheap_extract_parser",
        reason="no direct direct/distributor/ecommerce split found",
        evidence_sources=_ev("L9.disclosure.annual_report", ar_row),
    )


def _parse_channel_mix_from_text(text: str) -> dict[str, float] | None:
    """Parse annual-report sales-mode/channel rows into the L3.channel.mix shape."""
    if not text:
        return None
    direct = distributor = ecommerce = others = 0.0
    current_dim: str | None = None
    for raw in text.replace("\r", "\n").splitlines():
        line = raw.strip()
        if any(k in line for k in ("按销售模式", "分销售模式", "按销售渠道", "分销售渠道")):
            current_dim = "sales_mode"
            continue
        if any(k in line for k in ("按产品", "分产品", "按地区", "分地区", "按行业", "分行业")):
            current_dim = None
            continue
        if current_dim != "sales_mode" or any(k in line for k in ("合计", "小计", "总计", "营业收入")):
            continue
        m = re.match(r"^(.{2,30}?)\s+[\d,]+\.?\d*\s+([\d.]+)%", line)
        if not m:
            continue
        name = m.group(1).strip("、 ·")
        pct = _floatish(m.group(2))
        if pct is None or pct <= 0 or pct > 100:
            continue
        if any(k in name for k in ("直销", "直营", "自营")):
            direct += pct
        elif any(k in name for k in ("经销", "分销", "代理", "加盟", "渠道")):
            distributor += pct
        elif any(k in name for k in ("电商", "线上", "网络", "互联网")):
            ecommerce += pct
        else:
            others += pct
    total = direct + distributor + ecommerce + others
    if not (60 <= total <= 120):
        return None
    if total > 105:
        direct, distributor, ecommerce, others = [x * 100.0 / total for x in (direct, distributor, ecommerce, others)]
    return {
        "direct_pct": round(direct, 2),
        "distributor_pct": round(distributor, 2),
        "ecommerce_pct": round(ecommerce, 2),
        "others_pct": round(others, 2),
    }


def _channel_mix_proxy_from_business_text(text: str) -> dict[str, Any] | None:
    if not text.strip():
        return None
    lowered = text.casefold()
    if any(k in text for k in ("人寿保险", "健康保险", "意外伤害保险", "保险业务", "再保险")):
        return {
            "direct_pct": None,
            "distributor_pct": None,
            "ecommerce_pct": None,
            "others_pct": None,
            "trend": None,
            "notes": "dominant_channel=insurance_agent_direct_service；保险业务以代理/直营网点/客户服务体系为主，非商品分销口径；未披露占比",
        }
    if any(k in text for k in ("证券经纪", "财富管理", "营业部", "分公司", "银行", "贷款", "存款", "结算", "金融服务", "分销网络")):
        return {
            "direct_pct": None,
            "distributor_pct": None,
            "ecommerce_pct": None,
            "others_pct": None,
            "trend": None,
            "notes": "dominant_channel=branch_and_direct_service；金融服务渠道以分支机构/客户服务为主，非商品分销口径；未披露占比",
        }
    telecom_markers = (
        "电信", "基础通信", "通信网络", "数字信息基础设施", "物联网业务", "智慧城市", "智慧沃家",
        "大联接", "大计算", "大数据", "大应用", "大安全", "全球客户服务体系",
    )
    if any(k in text for k in telecom_markers):
        return {
            "direct_pct": None,
            "distributor_pct": None,
            "ecommerce_pct": None,
            "others_pct": None,
            "trend": None,
            "notes": "dominant_channel=telecom_direct_and_service_network；运营商业务通过线上/线下服务网络触达客户，不适合传统直销/经销/电商拆分；未披露占比",
        }
    if any(k in text for k in ("酒店", "订房渠道", "会员", "OTA")):
        return {
            "direct_pct": None,
            "distributor_pct": None,
            "ecommerce_pct": None,
            "others_pct": None,
            "trend": None,
            "notes": "dominant_channel=mixed_hotel_booking；酒店存在会员/订房/OTA等混合渠道，但本地资料未披露可加总占比",
        }
    auto_markers = ("汽车新车销售", "二手车经销", "汽车零配件批发", "汽车零配件零售", "整车", "商贸与出行")
    if any(k in text for k in auto_markers):
        return {
            "direct_pct": None,
            "distributor_pct": None,
            "ecommerce_pct": None,
            "others_pct": None,
            "trend": None,
            "notes": "dominant_channel=auto_dealer_and_direct_sales；汽车整车/零部件业务包含经销、批零和集团直销链条；本地资料未披露可加总占比",
        }
    shipping_markers = ("航次租船", "定期租船", "COA", "市场联营体", "POOL", "油品运输", "化学品运输", "液货运输")
    if any(k.casefold() in lowered for k in shipping_markers):
        return {
            "direct_pct": None,
            "distributor_pct": None,
            "ecommerce_pct": None,
            "others_pct": None,
            "trend": None,
            "notes": "dominant_channel=shipping_contract_service；航运业务以租船、COA和联营体等合同/服务模式为主，电商与传统经销不适用；未披露占比",
        }
    b2b_markers = (
        "B2B", "客户订单", "项目", "解决方案", "设备", "模组", "模块", "PCB", "电池系统",
        "储能系统", "电子级", "玻璃纤维", "硬质合金", "深加工", "生产和销售", "研发、生产",
        "以销定产", "订单生产", "服务全球", "企业客户", "封装", "封测", "晶圆", "芯片",
        "原料药", "CDMO", "生物大分子", "肝素", "货物及技术进出口",
    )
    if any(k.casefold() in lowered for k in b2b_markers):
        return {
            "direct_pct": None,
            "distributor_pct": None,
            "ecommerce_pct": 0.0,
            "others_pct": None,
            "trend": None,
            "notes": "dominant_channel=b2b_direct_or_project；B2B/项目制/客户订单型业务，电商渠道不适用；直销/经销精确占比未披露",
        }
    if any(k in text for k in ("互联网游戏", "网络广告", "搜索引擎", "增值服务", "短剧平台", "AIGC")):
        return {
            "direct_pct": None,
            "distributor_pct": None,
            "ecommerce_pct": None,
            "others_pct": None,
            "trend": None,
            "notes": "dominant_channel=online_platform；互联网平台/数字服务业务不适合传统直销/经销/电商拆分；未披露占比",
        }
    return None


def _event_candidate(dp_id: str, info: OverlayInfo, conn: sqlite3.Connection, scope: Mapping[str, Any]) -> dict[str, Any]:
    deps = (scope.get(dp_id) or {}).get("source_dependencies") or []
    rows = [(dep, _runtime_get(conn, _source_ts_codes(info), dep)) for dep in deps]
    text = "\n".join(_runtime_text(row) for _, row in rows if row is not None)
    if not rows or not any(row for _, row in rows):
        return _candidate(
            data_status="Unknown",
            method="event_keyword_screen",
            quality="source_missing",
            category="event_policy",
            reason="missing event dependencies",
        )
    hits = _event_keyword_hits(dp_id, text)
    evidence = [_ev(dep, row)[0] for dep, row in rows if row is not None]
    if hits:
        return _candidate(
            data_status="Unknown",
            value={"keyword_hits": hits[:8], "screening_status": "review_required"},
            method="event_keyword_screen",
            quality="review_required",
            category="event_policy_gated",
            confidence=0.35,
            evidence_sources=evidence,
            reason="keyword hit requires LLM/human gate before Known",
        )
    return _candidate(
        data_status="Inactive",
        value={"score": 0.0, "event_state": "none_observed", "keyword_hits": []},
        method="event_keyword_screen",
        quality="deterministic_no_hit",
        category="event_policy",
        confidence=0.72,
        evidence_sources=evidence,
    )


def _peer_market_share_candidate(dp_id: str, peer: Mapping[str, Any]) -> dict[str, Any]:
    if peer.get("revenue_rank") is None:
        return _candidate(
            data_status="Unknown",
            method="peer_revenue_rank",
            quality="source_missing",
            category="formula_proxy",
            reason="missing peer revenue rank",
        )
    share = peer.get("revenue_share_pct")
    rank = peer.get("revenue_rank")
    peer_count = peer.get("revenue_peer_count")
    return _candidate(
        data_status="Proxy",
        value={
            "rank": rank,
            "share_pct": round(float(share), 4) if share is not None else None,
            "market_size_unit": "peer_runtime_revenue_sum",
            "peers": [],
            "trend": "mixed",
            "source_year": "latest_runtime",
            "notes": "行业内收入排名/份额代理，不是外部口径市占率",
        },
        method="peer_revenue_rank",
        quality="proxy",
        category="formula_proxy",
        confidence=0.62,
        evidence_sources=[{"kind": "local_dp_id", "dp_id": "L5.is.revenue", "source": "runtime"}],
    )


def _ratio_candidate(
    *,
    dp_id: str,
    info: OverlayInfo,
    conn: sqlite3.Connection,
    numerator_dp: str,
    denominator_dp: str,
    method: str,
    category: str = "formula_proxy",
    lower_is_better: bool = True,
    scale: float = 0.25,
) -> dict[str, Any]:
    num_row = _runtime_get(conn, _source_ts_codes(info), numerator_dp)
    den_row = _runtime_get(conn, _source_ts_codes(info), denominator_dp)
    num = _scalar(num_row.value) if num_row else None
    den = _scalar(den_row.value) if den_row else None
    if num is None or den in (None, 0):
        return _candidate(
            data_status="Unknown",
            method=method,
            quality="source_missing",
            category=category,
            reason=f"missing {numerator_dp}/{denominator_dp}",
        )
    ratio = float(num) / float(den)
    magnitude = _clip01(abs(ratio) / scale)
    score = -magnitude if lower_is_better else magnitude
    return _candidate(
        data_status="Proxy",
        value={"ratio": ratio, "score": score, "notes": f"{numerator_dp}/{denominator_dp} proxy"},
        method=method,
        quality="formula_proxy",
        category=category,
        confidence=0.62,
        evidence_sources=[_ev(numerator_dp, num_row)[0], _ev(denominator_dp, den_row)[0]],
    )


def _segment_rows(row: RuntimeRow | None, metric_key: str) -> list[dict[str, Any]]:
    if row is None or not isinstance(row.value, Mapping):
        return []
    segments = row.value.get("segments")
    if not isinstance(segments, list):
        return []
    out: list[dict[str, Any]] = []
    for raw in segments:
        if not isinstance(raw, Mapping):
            continue
        item = str(raw.get("item") or raw.get("name") or "").strip()
        metric = _floatish(raw.get(metric_key))
        if not item or metric is None:
            continue
        out.append(
            {
                "item": item,
                metric_key: round(metric, 4),
                "period": raw.get("period") or row.value.get("period"),
            }
        )
    out.sort(key=lambda r: float(r.get(metric_key) or 0.0), reverse=True)
    return out


def _segment_revenue_candidate(dp_id: str, info: OverlayInfo, conn: sqlite3.Connection) -> dict[str, Any]:
    row = _runtime_available(conn, info, "L2.segment.revenue_share")
    segments = _segment_rows(row, "revenue_pct")
    if not segments:
        return _candidate(
            data_status="Unknown",
            method="segment_revenue_share_runtime",
            quality="source_missing",
            category="parser_formula_first",
            reason="missing L2.segment.revenue_share",
        )
    top = segments[0]["revenue_pct"]
    concentration = "high" if top >= 70 else "medium" if top >= 40 else "diversified"
    if dp_id == "L2.segment.industry_exposure":
        value = {
            "exposures": [
                {"industry_id": s["item"], "weight_pct": s["revenue_pct"]}
                for s in segments[:8]
            ],
            "cyclical_sensitivity": concentration,
            "notes": "fina_mainbz业务分部收入占比映射为行业/业务暴露候选",
        }
    elif dp_id == "L2.segment.cash_contrib":
        value = {
            "segments": [
                {
                    "name": s["item"],
                    "revenue_pct": s["revenue_pct"],
                    "gross_margin_pct": None,
                    "cash_contrib_pct": s["revenue_pct"],
                }
                for s in segments[:8]
            ],
            "notes": "分部收入占比作为现金贡献代理；真实现金贡献需分部现金流披露",
        }
    else:
        value = {
            "segments": segments[:8],
            "top_segment_pct": top,
            "concentration": concentration,
        }
    return _candidate(
        data_status="Proxy",
        value=value,
        method="segment_revenue_share_runtime",
        quality="structured_proxy",
        category="parser_formula_first",
        confidence=0.68,
        evidence_sources=[_ev("L2.segment.revenue_share", row)[0]],
    )


def _segment_profit_share_candidate(info: OverlayInfo, conn: sqlite3.Connection) -> dict[str, Any]:
    rev_row = _runtime_available(conn, info, "L2.segment.revenue_share")
    gm_row = _runtime_available(conn, info, "L2.segment.gross_margin")
    revenue = _segment_rows(rev_row, "revenue_pct")
    margins = _segment_rows(gm_row, "gross_margin_pct")
    gm_by_item = {str(s["item"]): float(s["gross_margin_pct"]) for s in margins}
    profit_items: list[dict[str, Any]] = []
    for seg in revenue:
        gm = gm_by_item.get(str(seg["item"]))
        if gm is None:
            continue
        gross_profit_index = max(float(seg["revenue_pct"]) * gm, 0.0)
        profit_items.append(
            {
                "item": seg["item"],
                "revenue_pct": seg["revenue_pct"],
                "gross_margin_pct": gm,
                "gross_profit_index": gross_profit_index,
                "period": seg.get("period"),
            }
        )
    total = sum(float(x["gross_profit_index"]) for x in profit_items)
    if total <= 0:
        return _candidate(
            data_status="Unknown",
            method="segment_profit_share_runtime",
            quality="source_missing",
            category="parser_formula_first",
            reason="missing comparable segment revenue/gross margin",
        )
    for item in profit_items:
        item["gross_profit_share_pct"] = round(100.0 * float(item.pop("gross_profit_index")) / total, 4)
    profit_items.sort(key=lambda r: float(r.get("gross_profit_share_pct") or 0.0), reverse=True)
    return _candidate(
        data_status="Proxy",
        value={
            "segments": profit_items[:8],
            "top_profit_share_pct": profit_items[0]["gross_profit_share_pct"],
            "notes": "分部收入占比×毛利率推算毛利贡献，不等同净利润贡献",
        },
        method="segment_profit_share_runtime",
        quality="structured_proxy",
        category="parser_formula_first",
        confidence=0.66,
        evidence_sources=[_ev("L2.segment.revenue_share", rev_row)[0], _ev("L2.segment.gross_margin", gm_row)[0]],
    )


def _product_margin_mix_candidate(info: OverlayInfo, conn: sqlite3.Connection) -> dict[str, Any]:
    gm_row = _runtime_available(conn, info, "L2.segment.gross_margin")
    margins = _segment_rows(gm_row, "gross_margin_pct")
    if not margins:
        return _candidate(
            data_status="Unknown",
            method="segment_gross_margin_runtime",
            quality="source_missing",
            category="parser_formula_first",
            reason="missing L2.segment.gross_margin",
        )
    return _candidate(
        data_status="Known",
        value={
            "product_margin_split": [
                {"product": s["item"], "gross_margin_pct": s["gross_margin_pct"]}
                for s in margins[:8]
            ],
            "gross_margin_pct": margins[0]["gross_margin_pct"],
            "margin_tier": "high" if float(margins[0]["gross_margin_pct"]) >= 40 else "mid" if float(margins[0]["gross_margin_pct"]) >= 20 else "low",
            "notes": "fina_mainbz分部毛利率直接映射为产品/业务毛利结构",
        },
        method="segment_gross_margin_runtime",
        quality="structured_parser",
        category="parser_formula_first",
        confidence=0.8,
        evidence_sources=[_ev("L2.segment.gross_margin", gm_row)[0]],
    )


def _company_level_opex_candidate(info: OverlayInfo, conn: sqlite3.Connection) -> dict[str, Any]:
    sga_row = _runtime_available(conn, info, "L5.is.sga_rd")
    if sga_row and isinstance(sga_row.value, Mapping) and sga_row.value.get("sga_rd_ratio_revenue") is not None:
        ratio = float(sga_row.value["sga_rd_ratio_revenue"])
        return _candidate(
            data_status="Proxy",
            value={
                "opex_ratio": ratio,
                "score": -_clip01(ratio / 0.35),
                "notes": "公司层面SGA+R&D/revenue代理分部opex压力",
            },
            method="company_opex_ratio_runtime",
            quality="formula_proxy",
            category="formula_proxy",
            confidence=0.62,
            evidence_sources=[_ev("L5.is.sga_rd", sga_row)[0]],
        )
    return _ratio_candidate(
        dp_id="L2.segment.opex_ratio",
        info=info,
        conn=conn,
        numerator_dp="L5.is.sga_rd",
        denominator_dp="L5.is.revenue",
        method="company_opex_ratio_runtime",
    )


def _fulfillment_cost_candidate(info: OverlayInfo, conn: sqlite3.Connection) -> dict[str, Any]:
    sga_row = _runtime_available(conn, info, "L5.is.sga_rd")
    gross_row = _runtime_available(conn, info, "L5.is.gross_margin")
    sga_ratio = None
    if sga_row and isinstance(sga_row.value, Mapping):
        sga_ratio = _floatish(sga_row.value.get("sga_rd_ratio_revenue"))
    gm = _scalar(gross_row.value) if gross_row else None
    if sga_ratio is None and gm is None:
        return _candidate(
            data_status="Unknown",
            method="fulfillment_cost_formula",
            quality="source_missing",
            category="formula_proxy",
            reason="missing SGA/R&D ratio and gross margin",
        )
    margin_pressure = 0.0
    if gm is not None:
        margin_pressure = _clip01((0.25 - float(gm)) / 0.25) if gm <= 1 else _clip01((25.0 - float(gm)) / 25.0)
    sga_pressure = _clip01(float(sga_ratio or 0.0) / 0.35)
    score = -_clip01(0.6 * sga_pressure + 0.4 * margin_pressure)
    return _candidate(
        data_status="Proxy",
        value={
            "sga_rd_ratio_revenue": sga_ratio,
            "gross_margin": gm,
            "score": score,
            "notes": "SGA/R&D费用率与毛利压力代理履约/交付成本",
        },
        method="fulfillment_cost_formula",
        quality="formula_proxy",
        category="formula_proxy",
        confidence=0.58,
        evidence_sources=[
            src for src in [
                _ev("L5.is.sga_rd", sga_row)[0] if sga_row else None,
                _ev("L5.is.gross_margin", gross_row)[0] if gross_row else None,
            ] if src
        ],
    )


def _region_related_candidate(
    dp_id: str,
    info: OverlayInfo,
    conn: sqlite3.Connection,
    region_candidate: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    region_row = _runtime_available(conn, info, "L3.region.domestic_overseas")
    domestic = overseas = None
    evidence: list[dict[str, Any]] = []
    if region_candidate and isinstance(region_candidate.get("value"), Mapping):
        domestic = _floatish(region_candidate["value"].get("domestic_pct"))
        overseas = _floatish(region_candidate["value"].get("overseas_pct"))
        raw_evidence = region_candidate.get("evidence_sources")
        if isinstance(raw_evidence, list):
            evidence = [src for src in raw_evidence if isinstance(src, Mapping)]
    if region_row and isinstance(region_row.value, Mapping):
        domestic = _floatish(region_row.value.get("domestic_pct"))
        overseas = _floatish(region_row.value.get("overseas_pct"))
        evidence = [_ev("L3.region.domestic_overseas", region_row)[0]]
    if domestic is None and overseas is None and dp_id == "L3.region.fx_geo":
        fx_row = _runtime_get(conn, _source_ts_codes(info), "L9.macro.fx")
        if fx_row:
            fx_change = _scalar(fx_row.value)
            score = 0.0 if fx_change is None or abs(float(fx_change)) < 1.0 else _clip01(abs(float(fx_change)) / 10.0)
            return _candidate(
                data_status="Proxy",
                value={
                    "overseas_pct": None,
                    "domestic_pct": None,
                    "fx_exposure_score": round(score, 4),
                    "macro_fx_present": True,
                    "notes": "区域收入占比缺失；仅用本地宏观汇率变动生成低置信度汇率风险辅助，不替代区域结构。",
                },
                method="macro_fx_only",
                quality="macro_proxy",
                category="parser_formula_first",
                confidence=0.5,
                evidence_sources=_ev("L9.macro.fx", fx_row),
            )
    if domestic is None and overseas is None:
        return _candidate(
            data_status="Unknown",
            method="region_mix_runtime",
            quality="source_missing",
            category="parser_formula_first",
            reason="missing L3.region.domestic_overseas runtime value",
        )
    if overseas is None and domestic is not None:
        overseas = max(0.0, 100.0 - domestic)
    if domestic is None and overseas is not None:
        domestic = max(0.0, 100.0 - overseas)
    value: dict[str, Any]
    if dp_id == "L3.channel.overseas":
        value = {
            "overseas_revenue_pct": overseas,
            "key_markets": [],
            "localization_stage": "unknown",
            "notes": "海外渠道用境内/境外收入结构代理",
        }
    elif dp_id == "L3.region.fx_geo":
        fx_row = _runtime_get(conn, _source_ts_codes(info), "L9.macro.fx")
        value = {
            "overseas_pct": overseas,
            "domestic_pct": domestic,
            "fx_exposure_score": _clip01(float(overseas or 0.0) / 100.0),
            "macro_fx_present": bool(fx_row),
            "notes": "海外收入占比代理汇率/地缘暴露",
        }
    else:
        value = {
            "tier1_pct": None,
            "tier2_pct": None,
            "tier3_pct": domestic,
            "overseas_pct": overseas,
            "notes": "仅有境内/境外结构；城市层级需要更细地区表",
        }
    return _candidate(
        data_status="Proxy",
        value=value,
        method="region_mix_runtime",
        quality="structured_proxy",
        category="parser_formula_first",
        confidence=0.62,
        evidence_sources=evidence or [{"kind": "local_dp_id", "dp_id": "L3.region.domestic_overseas", "source": "script_fill"}],
    )


def _formula_candidate(dp_id: str, info: OverlayInfo, conn: sqlite3.Connection, peer: Mapping[str, Any]) -> dict[str, Any]:
    revenue_row = _runtime_get(conn, _source_ts_codes(info), "L5.is.revenue")
    growth_row = _runtime_get(conn, _source_ts_codes(info), "L5.is.revenue_growth")
    gross_row = _runtime_get(conn, _source_ts_codes(info), "L5.is.gross_margin")
    sga_row = _runtime_get(conn, _source_ts_codes(info), "L5.is.sga_rd")
    capex_row = _runtime_get(conn, _source_ts_codes(info), "L5.cf.capex")
    ppe_row = _runtime_get(conn, _source_ts_codes(info), "L5.bs.goodwill_ppe")
    arap_row = _runtime_get(conn, _source_ts_codes(info), "L5.bs.ar_ap")
    revisions_row = _runtime_get(conn, _source_ts_codes(info), "L5.fcst.revisions")
    eps_row = _runtime_get(conn, _source_ts_codes(info), "L5.fcst.eps_cf")

    if dp_id == "L3.product.portfolio":
        return _product_portfolio_from_business_candidate(info, conn)

    if dp_id in {"L1.position.market_share", "L4.share.market"}:
        return _peer_market_share_candidate(dp_id, peer)

    if dp_id in {"L3.channel.cost", "L4.cost.cac_production", "L4.eff.store_labor"}:
        if sga_row and isinstance(sga_row.value, Mapping) and sga_row.value.get("sga_rd_ratio_revenue") is not None:
            ratio = float(sga_row.value["sga_rd_ratio_revenue"])
            if dp_id == "L4.cost.cac_production":
                value = {
                    "cac_or_unit_cost": ratio,
                    "trend": "proxy",
                    "drivers": ["SGA+R&D/revenue"],
                    "notes": "SGA+R&D/revenue代理获客/生产单位成本压力",
                }
            elif dp_id == "L4.eff.store_labor":
                value = {
                    "yoy_pct": None,
                    "trend": "proxy",
                    "notes": f"SGA+R&D/revenue={ratio:.4f}，作为门店/人工效率压力代理",
                }
            else:
                value = {"ratio": ratio, "score": -_clip01(ratio / 0.25), "notes": "SGA+R&D/revenue proxy"}
            return _candidate(
                data_status="Proxy",
                value=value,
                method="sga_revenue_ratio",
                quality="formula_proxy",
                category="formula_proxy",
                confidence=0.65,
                evidence_sources=_ev("L5.is.sga_rd", sga_row),
            )
        return _ratio_candidate(
            dp_id=dp_id,
            info=info,
            conn=conn,
            numerator_dp="L5.is.sga_rd",
            denominator_dp="L5.is.revenue",
            method="sga_revenue_ratio",
        )

    if dp_id == "L3.channel.efficiency":
        if sga_row and isinstance(sga_row.value, Mapping) and sga_row.value.get("sga_rd_ratio_revenue") is not None:
            ratio = float(sga_row.value["sga_rd_ratio_revenue"])
            return _candidate(
                data_status="Proxy",
                value={"sga_rd_ratio_revenue": ratio, "score": 1 - _clip01(ratio / 0.25)},
                method="channel_efficiency_formula",
                quality="formula_proxy",
                category="formula_proxy",
                confidence=0.62,
                evidence_sources=_ev("L5.is.sga_rd", sga_row),
            )

    if dp_id in {"L4.cost.rent_energy_logistics", "L4.price.discount", "L4.price.pricing_power", "L4.price.elasticity"}:
        business_text, business_evidence = _local_text_and_evidence(
            conn,
            info,
            ("L1.company.main_business", "L9.disclosure.annual_report"),
        )
        if dp_id == "L4.cost.rent_energy_logistics" and _is_financial_service(info, business_text):
            return _candidate(
                data_status="N/A",
                value={
                    "rent_yoy_pct": None,
                    "energy_yoy_pct": None,
                    "logistics_yoy_pct": None,
                    "trend": None,
                    "evidence_summary": "本地业务文本显示公司属于金融服务/券商等轻资产金融业务，租金、能源、物流不是核心经营成本指标。",
                    "notes": "行业适用性规则：金融服务默认不适用，除非年报明确披露为核心经营项。",
                },
                method="industry_applicability_matrix",
                quality="not_applicable",
                category="industry_applicability",
                confidence=0.7,
                evidence_sources=business_evidence,
            )
        financial_signal = _financial_price_signal(info, conn)
        if dp_id == "L4.price.discount" and financial_signal:
            pattern = str(financial_signal["pattern"])
            return _candidate(
                data_status="Known",
                value={
                    "avg_discount_pct": None,
                    "trend": financial_signal["trend"],
                    "season_high": None,
                    "notes": f"本地文本命中“{pattern}”，金融服务费率/融资融券利率存在价格压力；未披露平均折扣率。",
                },
                method="financial_price_signal_text",
                quality="direct_text_signal",
                category="parser_formula_first",
                confidence=0.48,
                evidence_sources=financial_signal["evidence_sources"],
            )
        if dp_id == "L4.price.pricing_power" and financial_signal:
            pattern = str(financial_signal["pattern"])
            high_margin_segments = financial_signal.get("high_margin_segments") or []
            evidence_summary = f"本地文本命中“{pattern}”，表明费率/利率受市场约束。"
            if high_margin_segments:
                evidence_summary += f" 高毛利业务线包括 {', '.join(str(x['name']) for x in high_margin_segments)}。"
            return _candidate(
                data_status="Known",
                value={
                    "strength": "moderate",
                    "recent_price_adjustment": pattern,
                    "customer_pushback": None,
                    "evidence_summary": evidence_summary,
                    "notes": "金融服务定价权受市场利率、监管和客户议价共同约束；不因局部高毛利直接判强。",
                },
                method="financial_price_signal_text",
                quality="direct_text_signal",
                category="parser_formula_first",
                confidence=0.5,
                evidence_sources=financial_signal["evidence_sources"],
            )
        gm = _scalar(gross_row.value) if gross_row else None
        if gm is None:
            return _candidate(
                data_status="Unknown",
                method="gross_margin_proxy",
                quality="source_missing",
                category="formula_proxy",
                reason="missing gross margin",
            )
        # gross margin is usually ratio 0..1. Lower margin means more pressure.
        pressure = _clip01((0.25 - float(gm)) / 0.25) if gm <= 1 else _clip01((25.0 - float(gm)) / 25.0)
        positive = _clip01((float(gm) - 0.25) / 0.35) if gm <= 1 else _clip01((float(gm) - 25.0) / 35.0)
        score = positive if dp_id == "L4.price.pricing_power" else -pressure
        if dp_id == "L4.price.discount":
            value = {
                "avg_discount_pct": None,
                "trend": "proxy",
                "season_high": None,
                "notes": f"gross_margin={gm}; 毛利压力代理折扣强度，score={score:.4f}",
            }
        elif dp_id == "L4.price.elasticity":
            value = {
                "elasticity": None,
                "estimation_method": "gross_margin_proxy",
                "notes": f"gross_margin={gm}; 当前无价格/销量弹性直接披露",
            }
        elif dp_id == "L4.price.pricing_power":
            value = {
                "strength": "strong" if score >= 0.6 else "medium" if score >= 0.25 else "weak",
                "recent_price_adjustment": None,
                "customer_pushback": None,
                "notes": f"gross_margin={gm}; 毛利率代理定价权",
            }
        else:
            value = {
                "trend": "proxy",
                "notes": f"gross_margin={gm}; 毛利压力代理租金/能源/物流成本压力，score={score:.4f}",
            }
        return _candidate(
            data_status="Proxy",
            value=value,
            method="gross_margin_proxy",
            quality="weak_proxy",
            category="formula_proxy",
            confidence=0.52,
            evidence_sources=_ev("L5.is.gross_margin", gross_row),
        )

    if dp_id in {"L4.eff.capacity_utilization", "L3.delivery.capacity_supply"}:
        capex = _scalar(capex_row.value) if capex_row else None
        ppe_value = None
        if ppe_row and isinstance(ppe_row.value, Mapping):
            ppe_value = _floatish(ppe_row.value.get("fix_assets_ppe"))
        if capex is None or not ppe_value:
            return _candidate(
                data_status="Unknown",
                method="capex_ppe_proxy",
                quality="source_missing",
                category="formula_proxy",
                reason="missing capex or PPE",
            )
        capex_ppe = float(capex) / float(ppe_value)
        if dp_id == "L4.eff.capacity_utilization":
            value = {
                "utilization_pct": None,
                "trend": "proxy",
                "bottleneck": None,
                "notes": f"capex/PPE={capex_ppe:.4f}，作为产能投入代理，不是直接利用率",
            }
        else:
            value = {
                "supplier_concentration": "unknown",
                "capacity_utilization_pct": None,
                "bottleneck": None,
                "notes": f"capex/PPE={capex_ppe:.4f}，作为产能/供应扩张代理",
            }
        return _candidate(
            data_status="Proxy",
            value=value,
            method="capex_ppe_proxy",
            quality="weak_proxy",
            category="formula_proxy",
            confidence=0.5,
            evidence_sources=[_ev("L5.cf.capex", capex_row)[0], _ev("L5.bs.goodwill_ppe", ppe_row)[0]],
        )

    if dp_id in {"L4.price.asp_aov_arpu", "L4.volume.orders", "L4.volume.sales", "L4.volume.shipments", "L4.volume.users", "L4.share.substitution"}:
        growth = _scalar(growth_row.value) if growth_row else peer.get("revenue_growth")
        if growth is None:
            return _candidate(
                data_status="Unknown",
                method="revenue_growth_proxy",
                quality="source_missing",
                category="formula_proxy",
                reason="missing revenue growth",
            )
        if dp_id == "L4.price.asp_aov_arpu":
            value = {
                "metric_kind": "revenue_growth_proxy",
                "value": None,
                "yoy_pct": growth,
                "trend": "up" if float(growth) > 0 else "down" if float(growth) < 0 else "flat",
                "notes": "收入增速代理ASP/AOV/ARPU变化，缺少直接单价/用户数",
            }
        else:
            value = {"yoy_pct": growth, "score": _signed_clip(float(growth), 50.0), "notes": "revenue growth proxy"}
        return _candidate(
            data_status="Proxy",
            value=value,
            method="revenue_growth_proxy",
            quality="weak_proxy",
            category="formula_proxy",
            confidence=0.5,
            evidence_sources=_ev("L5.is.revenue_growth", growth_row),
        )

    if dp_id == "L5.fcst.beat_probability":
        rev = _scalar(revisions_row.value) if revisions_row else None
        eps = _scalar(eps_row.value) if eps_row else None
        if rev is None and eps is None:
            return _candidate(
                data_status="Unknown",
                method="forecast_revision_formula",
                quality="source_missing",
                category="formula_proxy",
                reason="missing forecast revisions and EPS consensus",
            )
        revision_score = _signed_clip(float(rev or 0.0), 30.0)
        probability = _clip01(0.5 + 0.25 * revision_score)
        return _candidate(
            data_status="Proxy",
            value={"probability": probability, "score": revision_score, "revision_pct": rev, "eps_avg": eps},
            method="forecast_revision_formula",
            quality="formula_proxy",
            category="formula_proxy",
            confidence=0.68 if rev is not None else 0.5,
            evidence_sources=[
                src
                for src in [_ev("L5.fcst.revisions", revisions_row)[0] if revisions_row else None, _ev("L5.fcst.eps_cf", eps_row)[0] if eps_row else None]
                if src
            ],
        )

    if dp_id in {"L3.customer.solvency"}:
        if arap_row and isinstance(arap_row.value, Mapping):
            ar = _floatish(arap_row.value.get("accounts_receivable"))
            ap = _floatish(arap_row.value.get("accounts_payable"))
            revenue = _scalar(revenue_row.value) if revenue_row else None
            if ar is not None and revenue:
                ratio = ar / float(revenue)
                return _candidate(
                    data_status="Proxy",
                    value={
                        "top_customers_solvency": [],
                        "ar_concentration_risk": "high" if ratio >= 0.6 else "medium" if ratio >= 0.3 else "low",
                        "notes": f"AR/revenue={ratio:.4f}; AP={ap}; 应收占收入代理客户偿付压力",
                    },
                    method="ar_revenue_proxy",
                    quality="formula_proxy",
                    category="formula_proxy",
                    confidence=0.6,
                    evidence_sources=[_ev("L5.bs.ar_ap", arap_row)[0], _ev("L5.is.revenue", revenue_row)[0] if revenue_row else {}],
                )

    if dp_id in {"L2.segment.industry_exposure", "L2.segment.cash_contrib"}:
        return _segment_revenue_candidate(dp_id, info, conn)

    if dp_id == "L2.segment.profit_share":
        return _segment_profit_share_candidate(info, conn)

    if dp_id == "L2.segment.opex_ratio":
        return _company_level_opex_candidate(info, conn)

    if dp_id == "L3.product.margin_mix":
        return _product_margin_mix_candidate(info, conn)

    if dp_id == "L3.delivery.fulfillment_cost":
        return _fulfillment_cost_candidate(info, conn)

    if dp_id == "L3.region.domestic_overseas":
        return _domestic_overseas_from_business_candidate(info, conn)

    if dp_id in {"L3.channel.overseas", "L3.region.fx_geo", "L3.region.tier_mix"}:
        return _region_related_candidate(dp_id, info, conn)

    if dp_id in {"L2.segment.cash_contrib", "L2.segment.opex_ratio", "L2.segment.profit_share", "L2.segment.industry_exposure", "L3.product.margin_mix", "L3.customer.segment_mix", "L3.region.tier_mix", "L3.channel.overseas", "L3.region.fx_geo", "L3.delivery.fulfillment_cost"}:
        # These are parser/proxy-ready in principle, but this first harness only
        # has a direct implementation when script_fill or simple formulas cover
        # the needed evidence. Keep them explicit instead of fabricating Known.
        source_dp = "L9.disclosure.annual_report" if dp_id.startswith(("L2.", "L3.product", "L3.customer", "L3.region", "L3.channel")) else "L5.is.sga_rd"
        row = _runtime_get(conn, _source_ts_codes(info), source_dp)
        if row:
            return _candidate(
                data_status="Unknown",
                method="parser_todo_source_present",
                quality="parser_not_implemented",
                category="parser_formula_first",
                confidence=0.0,
                evidence_sources=_ev(source_dp, row),
                reason="source present but field-specific parser not implemented in this harness yet",
            )

    return _candidate(
        data_status="Unknown",
        method="no_non_llm_extractor",
        quality="not_implemented",
        category="unclassified",
        reason="no local extractor implemented",
    )


def _candidate_for(
    dp_id: str,
    info: OverlayInfo,
    conn: sqlite3.Connection,
    scope: Mapping[str, Any],
    roles: Mapping[str, Mapping[str, Any]],
    peer: Mapping[str, Any],
    script_fill: Mapping[str, dict[str, Any]],
) -> dict[str, Any]:
    if dp_id in script_fill:
        return script_fill[dp_id]
    if dp_id in CHEAP_EXTRACT_FIELDS:
        if dp_id == "L1.position.growth_rank":
            return _growth_rank_candidate(info, peer)
        if dp_id == "L3.channel.mix":
            return _channel_mix_candidate(info, conn)
        return _tag_candidate(dp_id, info, conn)
    if (scope.get(dp_id) or {}).get("model_tier") == "cheap_classify":
        if dp_id in {"L8.industry.demand_supply", "L8.industry.price_war"}:
            row = _runtime_get(conn, _source_ts_codes(info), dp_id)
            if row and _available(row.data_status):
                return _candidate(
                    data_status=row.data_status,
                    value=row.value,
                    method="existing_runtime_or_derive",
                    quality="runtime_derived",
                    category="strict_no_llm_now",
                    confidence=0.8,
                    evidence_sources=_ev(dp_id, row),
                )
        return _event_candidate(dp_id, info, conn, scope)
    if dp_id in WEB_ANALYSIS_FIELDS:
        return _candidate(
            data_status="Unknown",
            method="external_source_required",
            quality="requires_connector",
            category="web_or_external",
            reason="web_analysis field requires external source connector before non-LLM extraction",
        )
    if dp_id in KEEP_LLM_LOCAL_FIELDS:
        return _candidate(
            data_status="Unknown",
            method="semantic_review_required",
            quality="requires_llm_or_human",
            category="keep_llm_for_now",
            reason="local deterministic evidence is insufficient for high-confidence semantic value",
        )
    if dp_id in {"L8.gov.fraud_control", "L8.gov.litigation"}:
        return _event_candidate(dp_id, info, conn, scope)
    if dp_id in {"L3.channel.overseas", "L3.region.fx_geo", "L3.region.tier_mix"} and "L3.region.domestic_overseas" in script_fill:
        return _region_related_candidate(dp_id, info, conn, script_fill.get("L3.region.domestic_overseas"))
    if dp_id in FORMULA_FIRST_FIELDS or dp_id in STRICT_NO_LLM_NOW:
        return _formula_candidate(dp_id, info, conn, peer)
    return _candidate(
        data_status="Unknown",
        method="no_non_llm_extractor",
        quality="not_implemented",
        category="unclassified",
        reason=f"tier={(scope.get(dp_id) or {}).get('model_tier')} not mapped",
    )


def _canonical(value: Any) -> str:
    try:
        return json.dumps(_json_safe(value), ensure_ascii=False, sort_keys=True)
    except TypeError:
        return str(value)


def _compare(baseline: Mapping[str, Any], candidate: Mapping[str, Any]) -> dict[str, Any]:
    b_status = baseline.get("data_status")
    c_status = candidate.get("data_status")
    b_avail = _available(b_status)
    c_avail = _available(c_status)
    b_value = baseline.get("value")
    c_value = candidate.get("value")
    b_scalar = _scalar(b_value)
    c_scalar = _scalar(c_value)
    exact = _canonical(b_value) == _canonical(c_value)
    scalar_delta = None
    scalar_close = None
    if b_scalar is not None and c_scalar is not None:
        scalar_delta = c_scalar - b_scalar
        scalar_close = abs(scalar_delta) <= max(0.05, 0.15 * max(abs(b_scalar), 1.0))
    if b_avail and c_avail:
        bucket = "both_available"
        if b_status == c_status and (exact or scalar_close):
            bucket = "status_and_value_close"
        elif b_status == c_status:
            bucket = "status_match_value_differs"
    elif b_avail and not c_avail:
        bucket = "non_llm_missing_llm_available"
    elif not b_avail and c_avail:
        bucket = "non_llm_found_baseline_missing"
    else:
        bucket = "both_missing"
    if candidate.get("quality") in {"review_required", "requires_llm_or_human", "requires_connector"}:
        bucket = f"{bucket}:gated"
    return {
        "baseline_available": b_avail,
        "candidate_available": c_avail,
        "status_agreement": b_status == c_status,
        "exact_value_match": exact,
        "baseline_scalar": b_scalar,
        "candidate_scalar": c_scalar,
        "scalar_delta": scalar_delta,
        "scalar_close": scalar_close,
        "comparison_bucket": bucket,
    }


def _candidate_schema_errors(dp_id: str, candidate: Mapping[str, Any]) -> list[str]:
    status = str(candidate.get("data_status") or "")
    if status not in {"Known", "Proxy", "LowMateriality"}:
        return []
    value = candidate.get("value")
    if value is None:
        return []
    return schema_validator.validate_value(dp_id, value)


def build_report(
    *,
    root: Path,
    db_path: Path,
    sample_size: int,
    include_cheap_extract: bool,
) -> dict[str, Any]:
    started = time.time()
    scope = _llm_scope(root, include_cheap_extract=include_cheap_extract)
    noncheap_scope = _llm_scope(root, include_cheap_extract=False)
    roles = _field_roles(root)
    infos = _overlay_infos(root)
    selected = _select_samples(infos, scope, sample_size=sample_size)

    conn = sqlite3.connect(db_path)
    peer_map = _peer_stats(conn, infos)

    rows: list[dict[str, Any]] = []
    for info in selected:
        nodes = _nodes_by_dp(info.path)
        script_candidates = _script_fill_candidates(info, db_path)
        for dp_id, entry in scope.items():
            node = nodes.get(dp_id) or {}
            baseline = {
                "data_status": node.get("data_status", "Unknown"),
                "value": node.get("value"),
                "confidence": node.get("confidence"),
                "evidence_sources": node.get("evidence_sources") or [],
            }
            candidate = _candidate_for(
                dp_id,
                info,
                conn,
                scope,
                roles,
                peer_map.get(info.ts_code, {}),
                script_candidates,
            )
            comparison = _compare(baseline, candidate)
            schema_errors = _candidate_schema_errors(dp_id, candidate)
            role = roles.get(dp_id) or {}
            rows.append(
                {
                    "ts_code": info.ts_code,
                    "name": info.name,
                    "industry_id": info.industry_id,
                    "overlay_path": str(info.path.relative_to(root)),
                    "dp_id": dp_id,
                    "model_tier": entry.get("model_tier"),
                    "route": entry.get("route"),
                    "score_target": role.get("score_target"),
                    "participates_in_score": bool(role.get("participates_in_score")),
                    "baseline": baseline,
                    "candidate": candidate,
                    "candidate_schema": {
                        "valid": not schema_errors,
                        "errors": schema_errors,
                    },
                    "comparison": comparison,
                }
            )
    conn.close()

    summary = _summarize(rows, scope, noncheap_scope, selected)
    return {
        "generated_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "elapsed_s": round(time.time() - started, 3),
        "inputs": {
            "db_path": str(db_path.relative_to(root)) if db_path.is_relative_to(root) else str(db_path),
            "include_cheap_extract": include_cheap_extract,
            "sample_size": sample_size,
            "baseline_definition": "current stock overlay values; no fresh LLM call",
            "non_llm_definition": "local parser/formula/event-screen candidates only; read-only",
        },
        "scope": {
            "field_count": len(scope),
            "tier_counts": dict(Counter(entry.get("model_tier") for entry in scope.values())),
            "noncheap_field_count": len(noncheap_scope),
            "noncheap_tier_counts": dict(Counter(entry.get("model_tier") for entry in noncheap_scope.values())),
        },
        "sample": [
            {
                "ts_code": info.ts_code,
                "name": info.name,
                "industry_id": info.industry_id,
                "overlay_path": str(info.path.relative_to(root)),
            }
            for info in selected
        ],
        "summary": summary,
        "rows": _json_safe(rows),
    }


def _summarize(
    rows: list[dict[str, Any]],
    scope: Mapping[str, Any],
    noncheap_scope: Mapping[str, Any],
    selected: list[OverlayInfo],
) -> dict[str, Any]:
    bucket_counts = Counter(row["comparison"]["comparison_bucket"] for row in rows)
    candidate_category_counts = Counter(row["candidate"]["category"] for row in rows)
    method_counts = Counter(row["candidate"]["method"] for row in rows)
    tier_counts = Counter(row["model_tier"] for row in rows)
    baseline_available = sum(1 for row in rows if row["comparison"]["baseline_available"])
    candidate_available = sum(1 for row in rows if row["comparison"]["candidate_available"])
    candidate_schema_checked = sum(
        1
        for row in rows
        if row["comparison"]["candidate_available"]
        and row.get("candidate_schema", {}).get("errors") is not None
    )
    candidate_schema_invalid = sum(
        1
        for row in rows
        if row["comparison"]["candidate_available"]
        and row.get("candidate_schema", {}).get("valid") is False
    )
    score_rows = [row for row in rows if row["participates_in_score"]]
    score_candidate_available = sum(1 for row in score_rows if row["comparison"]["candidate_available"])
    score_baseline_available = sum(1 for row in score_rows if row["comparison"]["baseline_available"])
    score_candidate_schema_invalid = sum(
        1
        for row in score_rows
        if row["comparison"]["candidate_available"]
        and row.get("candidate_schema", {}).get("valid") is False
    )

    by_field: dict[str, dict[str, Any]] = {}
    for dp_id in sorted(scope):
        fr = [row for row in rows if row["dp_id"] == dp_id]
        by_field[dp_id] = {
            "model_tier": (scope.get(dp_id) or {}).get("model_tier"),
            "participates_in_score": any(row["participates_in_score"] for row in fr),
            "baseline_available_count": sum(1 for row in fr if row["comparison"]["baseline_available"]),
            "candidate_available_count": sum(1 for row in fr if row["comparison"]["candidate_available"]),
            "status_and_value_close_count": sum(1 for row in fr if row["comparison"]["comparison_bucket"] == "status_and_value_close"),
            "non_llm_missing_llm_available_count": sum(
                1 for row in fr if row["comparison"]["comparison_bucket"].startswith("non_llm_missing_llm_available")
            ),
            "candidate_categories": dict(Counter(row["candidate"]["category"] for row in fr)),
            "candidate_methods": dict(Counter(row["candidate"]["method"] for row in fr)),
            "candidate_schema_invalid_count": sum(
                1
                for row in fr
                if row["comparison"]["candidate_available"]
                and row.get("candidate_schema", {}).get("valid") is False
            ),
            "candidate_schema_errors": dict(
                Counter(
                    err
                    for row in fr
                    if row["comparison"]["candidate_available"]
                    for err in (row.get("candidate_schema") or {}).get("errors", [])
                )
            ),
        }

    semantic_or_external_gate_fields = [
        dp_id
        for dp_id, item in by_field.items()
        if any(cat in item["candidate_categories"] for cat in ("keep_llm_for_now", "web_or_external"))
    ]
    not_reproduced_fields = [
        dp_id
        for dp_id, item in by_field.items()
        if item["candidate_available_count"] == 0
    ]
    event_review_gate_fields = [
        dp_id
        for dp_id in not_reproduced_fields
        if "event_policy_gated" in by_field[dp_id]["candidate_categories"]
    ]
    extractor_gap_fields = [
        dp_id
        for dp_id in not_reproduced_fields
        if dp_id not in semantic_or_external_gate_fields
        and dp_id not in event_review_gate_fields
    ]
    non_llm_first_fields = [
        dp_id for dp_id, item in by_field.items() if item["candidate_available_count"] > 0
    ]

    return {
        "stock_count": len(selected),
        "field_count": len(scope),
        "row_count": len(rows),
        "baseline_available_count": baseline_available,
        "candidate_available_count": candidate_available,
        "candidate_available_rate": round(candidate_available / len(rows), 4) if rows else None,
        "candidate_schema_checked_count": candidate_schema_checked,
        "candidate_schema_invalid_count": candidate_schema_invalid,
        "candidate_schema_valid_rate": round((candidate_schema_checked - candidate_schema_invalid) / candidate_schema_checked, 4)
        if candidate_schema_checked
        else None,
        "score_row_count": len(score_rows),
        "score_baseline_available_count": score_baseline_available,
        "score_candidate_available_count": score_candidate_available,
        "score_candidate_available_rate": round(score_candidate_available / len(score_rows), 4) if score_rows else None,
        "score_candidate_schema_invalid_count": score_candidate_schema_invalid,
        "comparison_bucket_counts": dict(bucket_counts),
        "candidate_category_counts": dict(candidate_category_counts),
        "candidate_method_counts": dict(method_counts),
        "tier_row_counts": dict(tier_counts),
        "noncheap_field_count": len(noncheap_scope),
        "non_llm_first_field_count": len(non_llm_first_fields),
        "not_reproduced_field_count": len(not_reproduced_fields),
        "extractor_gap_field_count": len(extractor_gap_fields),
        "event_review_gate_field_count": len(event_review_gate_fields),
        "semantic_or_external_gate_field_count": len(semantic_or_external_gate_fields),
        "non_llm_first_fields": non_llm_first_fields,
        "not_reproduced_fields": not_reproduced_fields,
        "extractor_gap_fields": extractor_gap_fields,
        "event_review_gate_fields": event_review_gate_fields,
        "semantic_or_external_gate_fields": semantic_or_external_gate_fields,
        "by_field": by_field,
    }


def render_markdown(report: Mapping[str, Any]) -> str:
    summary = report["summary"]
    scope = report["scope"]
    lines = [
        "# A-share LLM vs non-LLM extractor comparison",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- Baseline: `{report['inputs']['baseline_definition']}`",
        f"- Non-LLM: `{report['inputs']['non_llm_definition']}`",
        f"- Stocks: `{summary['stock_count']}`",
        f"- Fields: `{scope['field_count']}` total; non-cheap-extract `{scope['noncheap_field_count']}`",
        f"- Tier counts: `{scope['tier_counts']}`",
        "",
        "## Topline",
        "",
        f"- Baseline available cells: `{summary['baseline_available_count']}/{summary['row_count']}`",
        f"- Non-LLM candidate available cells: `{summary['candidate_available_count']}/{summary['row_count']}` (`{summary['candidate_available_rate']}`)",
        f"- Non-LLM candidate schema-valid cells: `{summary['candidate_schema_checked_count'] - summary['candidate_schema_invalid_count']}/{summary['candidate_schema_checked_count']}` (`{summary['candidate_schema_valid_rate']}`)",
        f"- Score-field non-LLM candidate available cells: `{summary['score_candidate_available_count']}/{summary['score_row_count']}` (`{summary['score_candidate_available_rate']}`)",
        f"- Score-field schema-invalid candidate cells: `{summary['score_candidate_schema_invalid_count']}`",
        f"- Fields with at least one non-LLM candidate in this sample: `{summary['non_llm_first_field_count']}`",
        f"- Fields not reproduced by this harness yet: `{summary['not_reproduced_field_count']}`",
        f"- Of those, extractor/parser gaps: `{summary['extractor_gap_field_count']}`",
        f"- Of those, event-review gates: `{summary['event_review_gate_field_count']}`",
        f"- Semantic or external-source gated fields: `{summary['semantic_or_external_gate_field_count']}`",
        "",
        "## Sample",
        "",
        "| ts_code | name | industry |",
        "|---|---|---|",
    ]
    for item in report.get("sample") or []:
        lines.append(f"| `{item['ts_code']}` | {item.get('name') or ''} | `{item['industry_id']}` |")

    lines.extend([
        "",
        "## Comparison Buckets",
        "",
        "| bucket | cells |",
        "|---|---:|",
    ])
    for bucket, count in sorted(summary["comparison_bucket_counts"].items(), key=lambda x: (-x[1], x[0])):
        lines.append(f"| `{bucket}` | {count} |")

    lines.extend([
        "",
        "## Candidate Categories",
        "",
        "| category | cells |",
        "|---|---:|",
    ])
    for category, count in sorted(summary["candidate_category_counts"].items(), key=lambda x: (-x[1], x[0])):
        lines.append(f"| `{category}` | {count} |")

    lines.extend([
        "",
        "## Field Summary",
        "",
        "| dp_id | tier | score | baseline avail | non-LLM avail | close | missing vs baseline | top methods |",
        "|---|---|---:|---:|---:|---:|---:|---|",
    ])
    for dp_id, item in summary["by_field"].items():
        methods = ", ".join(
            f"{method}:{count}"
            for method, count in sorted(item["candidate_methods"].items(), key=lambda x: (-x[1], x[0]))[:3]
        )
        lines.append(
            "| "
            f"`{dp_id}` | `{item['model_tier']}` | `{item['participates_in_score']}` | "
            f"{item['baseline_available_count']} | {item['candidate_available_count']} | "
            f"{item['status_and_value_close_count']} | {item['non_llm_missing_llm_available_count']} | "
            f"{methods} |"
        )

    lines.extend([
        "",
        "## Interpretation",
        "",
        "- `status_and_value_close` is strong evidence that the local candidate matches the current overlay baseline.",
        "- `non_llm_missing_llm_available` means the current harness cannot reproduce a baseline value; it is not yet proof that LLM is mandatory.",
        "- `*:gated` means deterministic logic can screen or package evidence, but Known writes still need LLM/human or connector review.",
        "- Web-analysis fields are treated as connector gaps, not prompt-quality gaps.",
    ])
    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--db-path", type=Path, default=ROOT / "runtime" / "hot.sqlite")
    parser.add_argument("--sample-size", type=int, default=10)
    parser.add_argument("--json-output", type=Path, default=DEFAULT_JSON_OUTPUT)
    parser.add_argument("--md-output", type=Path, default=DEFAULT_MD_OUTPUT)
    parser.add_argument(
        "--exclude-cheap-extract",
        action="store_true",
        help="Restrict scope to cheap_classify/analysis/web_analysis (76 fields).",
    )
    parser.add_argument(
        "--omit-rows",
        action="store_true",
        help="Omit per-stock/per-field rows from the JSON artifact; summary and field aggregates remain.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_report(
        root=args.root.resolve(),
        db_path=args.db_path.resolve(),
        sample_size=args.sample_size,
        include_cheap_extract=not args.exclude_cheap_extract,
    )
    if args.omit_rows:
        report["rows_omitted"] = True
        report["rows"] = []
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    args.md_output.write_text(render_markdown(report), encoding="utf-8")
    print(f"wrote {args.json_output}")
    print(f"wrote {args.md_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
