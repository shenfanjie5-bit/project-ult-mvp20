#!/usr/bin/env python3
"""Draft review-only values for local structured-text A-share candidates.

The ``local_structured_text_llm_required`` rows combine structured financial
signals with IR/QA text. The current evidence proves that candidate inputs and
bridge shape are ready. This audit emits narrow Known review drafts only when
the QA snippets contain direct channel/service or pricing-pressure evidence;
otherwise it keeps the row review-gated Unknown instead of inventing
deterministic business direction.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sqlite3
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any, Mapping

_BOOTSTRAP_ROOT = Path(__file__).resolve().parent.parent
if str(_BOOTSTRAP_ROOT) not in sys.path:
    sys.path.insert(0, str(_BOOTSTRAP_ROOT))

from scripts.audit_a_share_local_single_dependency_policy_drafts import (
    DEFAULT_CANDIDATE_PATH,
    DEFAULT_READINESS_PATH,
    ROOT,
    _bridge_validation,
    _candidate_rows_by_dp,
    _deps,
    _evidence_refs,
    _load_json,
    _portable_path,
    _round,
    _validate_payload,
)


DEFAULT_JSON_OUTPUT = ROOT / "docs/audit/a_share_local_structured_text_policy_drafts_2026-06-19.json"
DEFAULT_MD_OUTPUT = ROOT / "docs/audit/a_share_local_structured_text_policy_drafts_2026-06-19.md"
DEFAULT_RUNTIME_DB_PATH = ROOT / "runtime/hot.sqlite"

CHANNEL_SERVICE_KEYWORDS = (
    "渠道",
    "服务网络",
    "售后",
    "交付",
    "配送",
    "运营",
    "批量运营",
    "批量配套",
    "配套销售",
    "客户支持",
    "应用场景",
)

DISCOUNT_PRICE_PRESSURE_KEYWORDS = (
    "产品价格下降",
    "价格下降",
    "价格回落",
    "毛利率下降",
    "降价",
    "价格战",
    "价格竞争",
    "竞争环境激烈",
    "医院采购预算缩减",
    "医保持续深化改革",
    "集采",
    "让利",
    "返点",
    "促销",
    "折扣",
)

DISCOUNT_STRONG_PRESSURE_KEYWORDS = (
    "产品价格下降",
    "价格下降",
    "毛利率下降",
    "降价",
    "价格战",
    "价格竞争",
    "竞争环境激烈",
    "医院采购预算缩减",
    "医保持续深化改革",
    "集采",
    "让利",
    "返点",
)

DISCOUNT_CONTEXT_EXCLUSIONS = (
    "股东专属",
    "住宿专属折扣",
    "股东的住宿",
    "权益礼遇",
    "贷款优惠",
    "上游原材料价格回落",
    "原材料价格回落",
    "成本端改善",
    "生产成本下降",
    "毛利率较上年提升",
)

DISCOUNT_ONLY_TERMS = {"折扣", "促销"}

USER_COUNT_STRONG_KEYWORDS = (
    "客户数",
    "客户数量",
    "用户数",
    "用户数量",
    "用户规模",
    "活跃用户",
    "注册用户",
    "会员数",
    "会员数量",
    "订单量",
    "订单数",
    "订单数量",
    "在手订单",
    "新签订单",
    "新增订单",
    "批量订单",
    "出货量",
    "交付量",
    "销量",
    "累计交付",
    "累计销量",
    "装机量",
    "累计装机",
    "保有量",
    "批量配套",
    "批量运营",
    "新客户拓展",
)

USER_COUNT_DEMAND_TERMS = (
    "客户",
    "用户",
    "订单",
    "会员",
    "出货",
    "交付",
    "销量",
    "装机",
    "保有",
    "批量配套",
    "批量运营",
)

USER_COUNT_SHAREHOLDER_EXCLUSIONS = (
    "股东",
    "股东户数",
    "股东人数",
    "股东总数",
    "A股股东",
    "H股股东",
    "登记股东",
    "持股证明",
    "持股",
    "户数",
)

USER_COUNT_NON_DEMAND_EXCLUSIONS = (
    "投资者",
    "应收账款",
    "回款",
    "信用政策",
    "客户资金",
    "客户保证金",
)

USER_COUNT_POSITIVE_TERMS = (
    "增长",
    "提升",
    "增加",
    "突破",
    "充足",
    "饱满",
    "顺利",
    "起量",
    "批量",
    "多家",
    "加速",
    "上量",
    "贡献稳定增长",
    "持续提升",
    "新签",
    "拓展",
)

USER_COUNT_NEGATIVE_TERMS = (
    "下降",
    "下滑",
    "减少",
    "不及预期",
    "趋于保守",
    "暂无",
    "未形成",
    "没有订单",
)

USER_COUNT_NEUTRAL_TERMS = (
    "持平",
    "正常",
)


def _text_rows(readiness: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in readiness.get("rows") or []:
        if isinstance(row, dict) and row.get("route_bucket") == "local_structured_text_llm_required":
            rows.append(row)
    return rows


def _payload_envelope(
    *,
    dp_id: str,
    score_target: str,
    blocked_reason: str,
    required_policy: str,
    evidence_refs: list[str],
    rationale: str,
    draft_status: str = "unknown_text_classification_required",
) -> dict[str, Any]:
    return {
        "target_dp_id": dp_id,
        "score_target": score_target,
        "data_status": "Unknown",
        "bridge_entry_data_status": "Unknown",
        "value_json": {
            "review_required": True,
            "blocked_reason": blocked_reason,
            "required_policy": required_policy,
        },
        "confidence": _round(0.0),
        "evidence_refs": evidence_refs,
        "rationale": rationale,
        "review_status": "review_required",
        "safe_to_upsert_without_review": False,
        "draft_kind": "local_structured_text_policy_pilot",
        "draft_status": draft_status,
        "pilot_only": True,
        "production_write_allowed": False,
    }


def _known(
    *,
    dp_id: str,
    score_target: str,
    score: float,
    drivers: list[str],
    components: dict[str, Any],
    confidence: float,
    evidence_refs: list[str],
    rationale: str,
) -> dict[str, Any]:
    return {
        "target_dp_id": dp_id,
        "score_target": score_target,
        "data_status": "Known",
        "bridge_entry_data_status": "Known",
        "value_json": {
            "score": _round(max(-1.0, min(1.0, score))),
            "drivers": drivers,
            "components": components,
        },
        "confidence": _round(max(0.0, min(1.0, confidence))),
        "evidence_refs": evidence_refs,
        "rationale": rationale,
        "review_status": "review_required",
        "safe_to_upsert_without_review": False,
        "draft_kind": "local_structured_text_policy_pilot",
        "draft_status": "draft_known_qa_channel_service_review_required",
        "pilot_only": True,
        "production_write_allowed": False,
    }


def _qa_snippets(deps: Mapping[str, Mapping[str, Any]]) -> list[dict[str, Any]]:
    dep = deps.get("L9.disclosure.qa_recent")
    if not isinstance(dep, Mapping):
        return []
    snippets: list[dict[str, Any]] = []
    for sample in dep.get("sample_rows") or []:
        if not isinstance(sample, Mapping):
            continue
        compact = sample.get("value_json_compact")
        if not isinstance(compact, Mapping):
            continue
        for item in compact.get("top_qa") or []:
            if not isinstance(item, Mapping):
                continue
            question = str(item.get("question") or "")
            answer = str(item.get("answer") or "")
            if not question and not answer:
                continue
            snippets.append(
                {
                    "ts_code": sample.get("ts_code"),
                    "date": item.get("date"),
                    "question": question,
                    "answer": answer,
                    "text": f"{question} {answer}".strip(),
                }
            )
    return snippets


def _runtime_qa_snippets(runtime_db_path: Path = DEFAULT_RUNTIME_DB_PATH) -> list[dict[str, Any]]:
    if not runtime_db_path.exists():
        return []
    snippets: list[dict[str, Any]] = []
    with sqlite3.connect(runtime_db_path) as conn:
        rows = conn.execute(
            """
            SELECT ts_code, value_json
            FROM realtime_current
            WHERE dp_id = 'L9.disclosure.qa_recent'
              AND data_status = 'Known'
            """
        ).fetchall()
    for ts_code, value_json in rows:
        try:
            compact = json.loads(value_json)
        except (TypeError, json.JSONDecodeError):
            continue
        if not isinstance(compact, Mapping):
            continue
        for item in compact.get("top_qa") or []:
            if not isinstance(item, Mapping):
                continue
            question = str(item.get("question") or "")
            answer = str(item.get("answer") or "")
            if not question and not answer:
                continue
            snippets.append(
                {
                    "ts_code": ts_code,
                    "date": item.get("date"),
                    "question": question,
                    "answer": answer,
                    "text": f"{question} {answer}".strip(),
                }
            )
    return snippets


def _matched_snippets(snippets: list[dict[str, Any]], keywords: tuple[str, ...]) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    for snippet in snippets:
        text = str(snippet.get("text") or "")
        hits = [keyword for keyword in keywords if keyword in text]
        if not hits:
            continue
        matches.append(
            {
                "ts_code": snippet.get("ts_code"),
                "date": snippet.get("date"),
                "keyword_hits": hits,
                "question": snippet.get("question"),
                "answer": snippet.get("answer"),
            }
        )
    return matches


def _discount_pressure_snippets(snippets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    for snippet in snippets:
        answer = str(snippet.get("answer") or "")
        if not answer:
            continue
        answer_hits = [keyword for keyword in DISCOUNT_PRICE_PRESSURE_KEYWORDS if keyword in answer]
        if not answer_hits:
            continue
        excluded_contexts = [
            phrase for phrase in DISCOUNT_CONTEXT_EXCLUSIONS if phrase in answer
        ]
        strong_hits = [
            keyword for keyword in DISCOUNT_STRONG_PRESSURE_KEYWORDS if keyword in answer
        ]
        if not strong_hits:
            continue
        pressure_hits = [
            keyword
            for keyword in answer_hits
            if keyword not in DISCOUNT_ONLY_TERMS or not excluded_contexts
        ]
        if not pressure_hits:
            continue
        matches.append(
            {
                "ts_code": snippet.get("ts_code"),
                "date": snippet.get("date"),
                "keyword_hits": sorted(set(pressure_hits)),
                "excluded_contexts": excluded_contexts,
                "question": snippet.get("question"),
                "answer": snippet.get("answer"),
            }
        )
    return matches


def _dedupe_snippets(snippets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str, str, str]] = set()
    unique: list[dict[str, Any]] = []
    for snippet in snippets:
        key = (
            str(snippet.get("ts_code") or ""),
            str(snippet.get("date") or ""),
            str(snippet.get("question") or ""),
            str(snippet.get("answer") or ""),
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(snippet)
    return unique


def _user_count_demand_snippets(snippets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    for snippet in snippets:
        answer = str(snippet.get("answer") or "")
        if not answer:
            continue
        strong_hits = [
            keyword for keyword in USER_COUNT_STRONG_KEYWORDS if keyword in answer
        ]
        demand_hits = [
            keyword for keyword in USER_COUNT_DEMAND_TERMS if keyword in answer
        ]
        if not strong_hits or not demand_hits:
            continue
        shareholder_exclusions = [
            phrase for phrase in USER_COUNT_SHAREHOLDER_EXCLUSIONS if phrase in answer
        ]
        non_demand_exclusions = [
            phrase for phrase in USER_COUNT_NON_DEMAND_EXCLUSIONS if phrase in answer
        ]
        if shareholder_exclusions or (
            non_demand_exclusions
            and not any(term in answer for term in ("订单", "销量", "出货", "装机"))
        ):
            continue
        positive_hits = [
            phrase for phrase in USER_COUNT_POSITIVE_TERMS if phrase in answer
        ]
        negative_hits = [
            phrase for phrase in USER_COUNT_NEGATIVE_TERMS if phrase in answer
        ]
        neutral_hits = [
            phrase for phrase in USER_COUNT_NEUTRAL_TERMS if phrase in answer
        ]
        matches.append(
            {
                "ts_code": snippet.get("ts_code"),
                "date": snippet.get("date"),
                "keyword_hits": sorted(set(strong_hits)),
                "demand_terms": sorted(set(demand_hits)),
                "positive_terms": sorted(set(positive_hits)),
                "negative_terms": sorted(set(negative_hits)),
                "neutral_terms": sorted(set(neutral_hits)),
                "question": snippet.get("question"),
                "answer": snippet.get("answer"),
            }
        )
    return matches


def _policy_for(dp_id: str) -> tuple[str, str]:
    policies = {
        "L0.demand.user_count": (
            "qa_recent_requires_customer_user_extraction",
            "user-count demand needs customer/user/order-volume extraction; shareholder-count Q&A must not be treated as customer demand",
        ),
        "L0.price.discount": (
            "qa_recent_requires_discount_or_pricing_pressure_extraction",
            "discount pressure needs direct pricing/discount commentary or reviewed gross-margin decomposition",
        ),
        "L0.supply.channel_service": (
            "qa_recent_requires_channel_service_extraction",
            "channel/service supply needs direct channel capacity, service network, delivery, or support-quality evidence",
        ),
    }
    return policies.get(
        dp_id,
        (
            "unsupported_structured_text_policy",
            "no conservative structured-text policy is defined for this dp_id",
        ),
    )


def _draft_payload(
    readiness_row: Mapping[str, Any],
    candidate_row: Mapping[str, Any] | None,
    runtime_qa_snippets: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    dp_id = str(readiness_row.get("dp_id") or "")
    score_target = str(readiness_row.get("score_target") or "")
    if candidate_row is None:
        return _payload_envelope(
            dp_id=dp_id,
            score_target=score_target,
            blocked_reason="missing_candidate_evidence",
            required_policy="matching candidate-evidence row is required before structured-text classification",
            evidence_refs=["docs/audit/a_share_non_manual_candidate_readiness_2026-06-19.json"],
            rationale="No matching candidate-evidence row exists; keep Unknown.",
            draft_status="unknown_missing_candidate_evidence",
            )
    deps = _deps(candidate_row)
    if dp_id == "L0.demand.user_count":
        snippets = _dedupe_snippets(_qa_snippets(deps) + list(runtime_qa_snippets or []))
        matches = _user_count_demand_snippets(snippets)
        if matches:
            positive_count = sum(1 for match in matches if match.get("positive_terms"))
            negative_count = sum(1 for match in matches if match.get("negative_terms"))
            neutral_count = sum(1 for match in matches if match.get("neutral_terms"))
            base_score = min(0.22, 0.08 + 0.025 * min(len(matches), 5))
            polarity_adjustment = min(0.08, 0.015 * positive_count) - min(
                0.08, 0.02 * negative_count
            )
            score = max(-0.18, min(0.28, base_score + polarity_adjustment))
            return _known(
                dp_id=dp_id,
                score_target=score_target,
                score=score,
                drivers=["L9.disclosure.qa_recent", "L5.is.revenue"],
                components={
                    "qa_user_count_demand_match_count": len(matches),
                    "positive_match_count": positive_count,
                    "negative_match_count": negative_count,
                    "neutral_match_count": neutral_count,
                    "matched_keywords": sorted(
                        {
                            keyword
                            for match in matches
                            for keyword in match.get("keyword_hits", [])
                        }
                    ),
                    "demand_terms": sorted(
                        {
                            keyword
                            for match in matches
                            for keyword in match.get("demand_terms", [])
                        }
                    ),
                    "excluded_contexts": sorted(
                        set(USER_COUNT_SHAREHOLDER_EXCLUSIONS)
                        | set(USER_COUNT_NON_DEMAND_EXCLUSIONS)
                    ),
                    "score_mapping": (
                        "bounded review-only demand score from answer-side "
                        "customer/user/order/volume evidence; shareholder and "
                        "investor-count contexts are excluded"
                    ),
                    "evidence_examples": matches[:5],
                },
                confidence=0.37,
                evidence_refs=_evidence_refs(candidate_row, deps),
                rationale=(
                    "QA/IR company answers contain direct customer, user, order, "
                    "shipment, sales-volume, installed-base, or batch-operation "
                    "evidence after excluding shareholder-count contexts. This "
                    "emits a bounded review-only user-count demand draft while "
                    "retaining approval gates."
                ),
            ) | {"draft_status": "draft_known_qa_user_count_review_required"}
    if dp_id == "L0.price.discount":
        snippets = _qa_snippets(deps) + list(runtime_qa_snippets or [])
        matches = _discount_pressure_snippets(snippets)
        if matches:
            gross_margin_values: list[float] = []
            gross_margin_dep = deps.get("L5.is.gross_margin")
            if isinstance(gross_margin_dep, Mapping):
                for sample in gross_margin_dep.get("sample_rows") or []:
                    if not isinstance(sample, Mapping):
                        continue
                    compact = sample.get("value_json_compact")
                    if not isinstance(compact, Mapping):
                        continue
                    value = compact.get("scalar")
                    if isinstance(value, (int, float)) and not isinstance(value, bool):
                        gross_margin_values.append(float(value))
            avg_gross_margin = (
                sum(gross_margin_values) / len(gross_margin_values)
                if gross_margin_values
                else 0.25
            )
            margin_pressure = max(0.0, min(0.08, (0.25 - avg_gross_margin) / 2.0))
            evidence_pressure = min(0.24, 0.12 + 0.04 * min(len(matches), 3))
            score = -max(0.0, min(1.0, evidence_pressure + margin_pressure))
            return _known(
                dp_id=dp_id,
                score_target=score_target,
                score=score,
                drivers=["L9.disclosure.qa_recent", "L5.is.gross_margin"],
                components={
                    "qa_discount_pressure_match_count": len(matches),
                    "matched_keywords": sorted(
                        {
                            keyword
                            for match in matches
                            for keyword in match.get("keyword_hits", [])
                        }
                    ),
                    "excluded_contexts_seen": sorted(
                        {
                            context
                            for match in matches
                            for context in match.get("excluded_contexts", [])
                        }
                    ),
                    "sample_avg_gross_margin": _round(avg_gross_margin),
                    "score_mapping": (
                        "bounded negative fundamental score from company-answer "
                        "pricing-pressure evidence plus low-margin context"
                    ),
                    "evidence_examples": matches[:3],
                },
                confidence=0.38,
                evidence_refs=_evidence_refs(candidate_row, deps),
                rationale=(
                    "QA/IR company answers contain direct pricing-pressure or "
                    "product-price-decline evidence. This emits a bounded negative "
                    "review-only discount draft while retaining approval gates."
                ),
            ) | {"draft_status": "draft_known_qa_discount_pressure_review_required"}
    if dp_id == "L0.supply.channel_service":
        snippets = _qa_snippets(deps)
        matches = _matched_snippets(snippets, CHANNEL_SERVICE_KEYWORDS)
        if matches:
            sga_values: list[float] = []
            sga_dep = deps.get("L5.is.sga_rd")
            if isinstance(sga_dep, Mapping):
                for sample in sga_dep.get("sample_rows") or []:
                    if not isinstance(sample, Mapping):
                        continue
                    compact = sample.get("value_json_compact")
                    if not isinstance(compact, Mapping):
                        continue
                    value = compact.get("sga_rd_ratio_revenue")
                    if isinstance(value, (int, float)) and not isinstance(value, bool):
                        sga_values.append(float(value))
            avg_sga = sum(sga_values) / len(sga_values) if sga_values else 0.18
            cost_drag = max(-0.12, min(0.12, (0.18 - avg_sga) / 1.5))
            evidence_score = min(0.22, 0.08 + 0.04 * min(len(matches), 3))
            score = max(-1.0, min(1.0, evidence_score + cost_drag))
            return _known(
                dp_id=dp_id,
                score_target=score_target,
                score=score,
                drivers=["L9.disclosure.qa_recent", "L5.is.sga_rd"],
                components={
                    "qa_channel_service_match_count": len(matches),
                    "matched_keywords": sorted(
                        {
                            keyword
                            for match in matches
                            for keyword in match.get("keyword_hits", [])
                        }
                    ),
                    "sample_avg_sga_rd_ratio_revenue": _round(avg_sga),
                    "score_mapping": "bounded QA channel/service evidence plus SGA/R&D burden adjustment",
                    "evidence_examples": matches[:3],
                },
                confidence=0.36,
                evidence_refs=_evidence_refs(candidate_row, deps),
                rationale=(
                    "QA/IR text contains direct channel, application, batch-sales, "
                    "operation, or service evidence, so this pilot emits a bounded "
                    "review-only channel/service draft while retaining approval gates."
                ),
            )
    blocked_reason, required_policy = _policy_for(dp_id)
    return _payload_envelope(
        dp_id=dp_id,
        score_target=score_target,
        blocked_reason=blocked_reason,
        required_policy=required_policy,
        evidence_refs=_evidence_refs(candidate_row, deps),
        rationale=(
            "Structured financial evidence is present and QA/IR text is available, "
            "but the text has not been classified into the target business concept; keep Unknown."
        ),
    )


def build_report(readiness_path: Path, candidate_path: Path) -> dict[str, Any]:
    started = time.time()
    readiness = _load_json(readiness_path)
    candidate = _load_json(candidate_path)
    candidate_rows = _candidate_rows_by_dp(candidate)
    runtime_lookup_enabled = candidate_path.resolve() == DEFAULT_CANDIDATE_PATH.resolve()
    runtime_qa_snippets = (
        _runtime_qa_snippets() if runtime_lookup_enabled else []
    )
    rows: list[dict[str, Any]] = []
    for readiness_row in _text_rows(readiness):
        dp_id = str(readiness_row.get("dp_id") or "")
        score_target = str(readiness_row.get("score_target") or "")
        candidate_row = candidate_rows.get(dp_id)
        payload = _draft_payload(readiness_row, candidate_row, runtime_qa_snippets)
        contract = _validate_payload(dp_id, score_target, payload)
        bridge = (
            _bridge_validation(dp_id, score_target, payload)
            if payload.get("data_status") == "Known"
            else {}
        )
        rows.append(
            {
                "dp_id": dp_id,
                "score_target": score_target,
                "source_dependencies": candidate_row.get("source_dependencies") if candidate_row else [],
                "route_bucket": readiness_row.get("route_bucket"),
                "dependency_readiness": readiness_row.get("dependency_readiness"),
                "draft_status": payload.get("draft_status"),
                "draft_payload": payload,
                "contract_validation": contract,
                "bridge_validation": bridge,
                "production_write_allowed": False,
            }
        )

    draft_status_counts = Counter(row["draft_status"] for row in rows)
    invalid_rows = [row for row in rows if not row["contract_validation"]["contract_valid"]]
    known_rows = [row for row in rows if row["draft_payload"].get("data_status") == "Known"]
    return {
        "generated_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "elapsed_s": round(time.time() - started, 3),
        "readiness_path": _portable_path(readiness_path),
        "candidate_path": _portable_path(candidate_path),
        "runtime_qa_lookup_enabled": runtime_lookup_enabled,
        "runtime_qa_snippet_count": len(runtime_qa_snippets),
        "summary": {
            "local_structured_text_task_count": len(rows),
            "draft_known_count": len(known_rows),
            "draft_unknown_count": len(rows) - len(known_rows),
            "draft_contract_valid_count": sum(1 for row in rows if row["contract_validation"]["contract_valid"]),
            "draft_contract_invalid_count": len(invalid_rows),
            "draft_contract_invalid_dp_ids": [row["dp_id"] for row in invalid_rows],
            "bridge_validated_known_count": sum(
                1
                for row in known_rows
                if row["bridge_validation"].get("final_score_target_ready")
            ),
            "bridge_blocked_known_count": sum(
                1
                for row in known_rows
                if not row["bridge_validation"].get("final_score_target_ready")
            ),
            "qa_discount_pressure_known_draft_count": sum(
                1
                for row in rows
                if row.get("draft_status")
                == "draft_known_qa_discount_pressure_review_required"
            ),
            "qa_user_count_known_draft_count": sum(
                1
                for row in rows
                if row.get("draft_status")
                == "draft_known_qa_user_count_review_required"
            ),
            "qa_channel_service_known_draft_count": sum(
                1
                for row in rows
                if row.get("draft_status")
                == "draft_known_qa_channel_service_review_required"
            ),
            "review_required_count": len(rows),
            "safe_to_upsert_without_review_count": 0,
            "production_write_allowed_count": 0,
            "draft_status_counts": dict(sorted(draft_status_counts.items())),
            "score_mutation": "none; this audit is read-only and does not alter realtime_current",
        },
        "rows": rows,
    }


def render_markdown(report: Mapping[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# A-share local structured-text policy drafts",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- Local structured-text tasks: `{summary['local_structured_text_task_count']}`",
        f"- Draft Known review packets: `{summary['draft_known_count']}`",
        f"- Draft Unknown packets: `{summary['draft_unknown_count']}`",
        f"- Draft contracts valid: `{summary['draft_contract_valid_count']}`",
        f"- Draft contracts invalid: `{summary['draft_contract_invalid_count']}`",
        f"- Known drafts bridge-validated: `{summary['bridge_validated_known_count']}`",
        f"- Safe to upsert without review: `{summary['safe_to_upsert_without_review_count']}`",
        f"- Production writes allowed: `{summary['production_write_allowed_count']}`",
        f"- Score mutation: `{summary['score_mutation']}`",
        "",
        "## Draft Status Counts",
        "",
        "| Status | Count |",
        "|---|---:|",
    ]
    for status, count in summary["draft_status_counts"].items():
        lines.append(f"| `{status}` | {count} |")

    lines.extend(
        [
            "",
            "## Rows",
            "",
            "| dp_id | target | draft status | data status | contract | confidence | value |",
            "|---|---|---|---|---:|---:|---|",
        ]
    )
    for row in report["rows"]:
        payload = row["draft_payload"]
        lines.append(
            "| "
            f"`{row['dp_id']}` | "
            f"`{row['score_target']}` | "
            f"`{row['draft_status']}` | "
            f"`{payload['data_status']}` | "
            f"{'yes' if row['contract_validation'].get('contract_valid') else 'no'} | "
            f"{payload['confidence']} | "
            f"`{json.dumps(payload['value_json'], ensure_ascii=False, sort_keys=True)}` |"
        )

    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- This pilot keeps structured-text candidates Unknown until QA/IR text is classified into the target business concept.",
            "- Shareholder-count or generic investor-relations Q&A must not be treated as customer/user/channel/discount evidence without review.",
            "- Production score-affecting writes remain disabled.",
            "",
        ]
    )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--readiness-path", type=Path, default=DEFAULT_READINESS_PATH)
    parser.add_argument("--candidate-path", type=Path, default=DEFAULT_CANDIDATE_PATH)
    parser.add_argument("--json-output", type=Path, default=DEFAULT_JSON_OUTPUT)
    parser.add_argument("--md-output", type=Path, default=DEFAULT_MD_OUTPUT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_report(args.readiness_path, args.candidate_path)
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.md_output.write_text(render_markdown(report), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
