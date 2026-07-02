#!/usr/bin/env python3
"""Draft review-only values for A-share event-text candidates.

The ``event_text_classification_required`` rows have material market/event
dependency coverage. When a local market-document review packet has conservative
same-sentence target/transmission evidence and this script has a bounded policy
for the target dp_id, it emits a Known review draft. Ambiguous or unprofiled
packets stay review-gated Unknown.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
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
    _candidate_rows_by_dp,
    _bridge_validation,
    _deps,
    _evidence_refs,
    _load_json,
    _portable_path,
    _round,
    _validate_payload,
)


DEFAULT_JSON_OUTPUT = ROOT / "docs/audit/a_share_event_text_policy_drafts_2026-06-19.json"
DEFAULT_MD_OUTPUT = ROOT / "docs/audit/a_share_event_text_policy_drafts_2026-06-19.md"
DEFAULT_MARKET_DOC_REVIEW_PACKETS_PATH = (
    ROOT / "docs/audit/a_share_event_text_market_doc_review_packets_2026-06-19.json"
)


REVIEW_PROFILES: dict[str, dict[str, Any]] = {
    "L0.compete.price_war": {
        "score": -0.25,
        "confidence": 0.46,
        "drivers": ["market_doc:price_war", "L9.industry.compete_risk"],
        "classification": "competitive_price_pressure",
        "minimum_examples": 2,
        "rationale": (
            "Local market-document snippets directly tie price-war or promotion "
            "language to export/supply-chain/A-share transmission. The bounded "
            "negative draft reflects margin and competitive-pressure risk."
        ),
    },
    "L0.compete.share_concentration": {
        "score": 0.22,
        "confidence": 0.44,
        "drivers": ["market_doc:share_concentration", "L9.industry.compete_risk"],
        "classification": "leader_share_or_consolidation",
        "minimum_examples": 3,
        "rationale": (
            "Local snippets contain market-share, consolidation, or leader-share "
            "evidence with A-share/company/industry transmission. The positive "
            "draft treats concentration as a potential leader-quality signal."
        ),
    },
    "L0.policy.access_license": {
        "score": -0.2,
        "confidence": 0.43,
        "drivers": ["market_doc:access_license", "L9.industry.policy_change"],
        "classification": "license_or_access_tightening",
        "minimum_examples": 3,
        "rationale": (
            "Local snippets directly mention licensing, export credentials, "
            "approval, or qualification constraints with listed-company/export "
            "transmission. The draft is negative because tighter access raises "
            "execution or eligibility risk."
        ),
    },
    "L0.policy.regulation": {
        "score": -0.12,
        "confidence": 0.41,
        "drivers": ["market_doc:regulation", "L9.industry.policy_change", "L9.media.report"],
        "classification": "regulatory_or_compliance_event",
        "minimum_examples": 3,
        "rationale": (
            "Local snippets contain regulation, inquiry, sanction, or compliance "
            "language with direct industry, listed-company, or supply-chain "
            "transmission. The bounded negative draft treats unreviewed "
            "regulatory events as mild execution/compliance risk and remains "
            "review-only because individual events can be supportive or adverse."
        ),
    },
    "L0.policy.subsidy": {
        "score": -0.1,
        "confidence": 0.4,
        "drivers": ["market_doc:subsidy", "L9.industry.policy_change", "L9.media.report"],
        "classification": "subsidy_or_countervailing_policy",
        "minimum_examples": 3,
        "rationale": (
            "Local snippets tie subsidy, anti-subsidy, or policy-support terms "
            "to export, import, industry, or listed-company transmission. The "
            "bounded negative draft is conservative because retained examples "
            "include trade-remedy and subsidy-offset contexts; reviewers must "
            "confirm whether the final direction is support or friction."
        ),
    },
    "L0.policy.tax_trade": {
        "score": -0.18,
        "confidence": 0.42,
        "drivers": ["market_doc:tax_trade", "L9.industry.policy_change", "L9.macro.fx"],
        "classification": "tariff_or_trade_friction",
        "minimum_examples": 3,
        "rationale": (
            "Local snippets directly tie tariff, trade-remedy, import/export, "
            "or trade-friction language to real economy transmission. The "
            "bounded negative draft reflects export-margin and demand-friction "
            "risk, while remaining review-only because impact differs by sector."
        ),
    },
    "L0.tech.ai_automation": {
        "score": 0.28,
        "confidence": 0.45,
        "drivers": ["market_doc:ai_automation", "L9.media.report"],
        "classification": "ai_automation_demand_or_productivity",
        "minimum_examples": 3,
        "rationale": (
            "Local snippets connect AI, compute, or automation demand to A-share "
            "concept boards, domestic supply chains, or export demand. The draft "
            "is a bounded positive technology-adoption signal."
        ),
    },
    "L0.tech.breakthrough": {
        "score": 0.24,
        "confidence": 0.44,
        "drivers": ["market_doc:breakthrough", "L9.media.report", "L9.industry.compete_risk"],
        "classification": "technology_breakthrough_or_commercialization",
        "minimum_examples": 3,
        "rationale": (
            "Local snippets connect breakthrough, commercialization, volume "
            "production, or major technical progress language to A-share, "
            "industry, export, or supply-chain transmission. The bounded "
            "positive draft reflects potential demand, productivity, or "
            "competitive-position upside while remaining review-only."
        ),
    },
    "L0.tech.substitute_tech": {
        "score": -0.18,
        "confidence": 0.39,
        "drivers": ["market_doc:substitute_tech", "L9.media.report", "L9.industry.compete_risk"],
        "classification": "substitute_technology_displacement_risk",
        "minimum_examples": 2,
        "rationale": (
            "Local snippets must show an alternative technology displacing or "
            "threatening the target A-share industry/company. Import-substitution "
            "opportunity headlines and foreign macro substitutions are excluded "
            "because this slot is a negative substitute-technology risk factor."
        ),
    },
    "L8.shock.black_swan": {
        "score": 0.55,
        "confidence": 0.48,
        "drivers": ["market_doc:black_swan", "L9.media.report"],
        "classification": "geopolitical_or_black_swan_supply_risk",
        "minimum_examples": 3,
        "rationale": (
            "Local snippets identify severe geopolitical/shipping/oil-facility "
            "events with export or supply-chain transmission. The bounded score "
            "is a risk-discount magnitude and remains review-only."
        ),
    },
    "L8.shock.supply_break": {
        "score": 0.45,
        "confidence": 0.47,
        "drivers": ["market_doc:supply_break", "L9.media.report"],
        "classification": "supply_chain_or_input_disruption",
        "minimum_examples": 3,
        "rationale": (
            "Local snippets directly mention production halts, supply interruption, "
            "or input shortages with A-share/industry/import/export transmission. "
            "The bounded score is a risk-discount magnitude."
        ),
    },
}


SUBSTITUTE_TECH_RISK_TERMS = (
    "替代风险",
    "被替代",
    "被取代",
    "替代品",
    "替代技术",
    "取代传统",
    "技术路线变化",
    "颠覆",
    "冲击",
)
SUBSTITUTE_TECH_DIRECT_TERMS = (
    "A股",
    "上市公司",
    "个股",
    "板块",
    "产业链",
    "供应链",
    "公司",
    "行业",
)
SUBSTITUTE_TECH_OPPORTUNITY_TERMS = (
    "国产替代",
    "进口替代",
    "替代进口",
    "替代进口设备",
    "替代国外",
    "替代海外",
    "规模化替代进口",
)
SUBSTITUTE_TECH_FALSE_CONTEXT_TERMS = (
    "特朗普",
    "最高法院",
    "行政令",
    "关税",
    "斯洛伐克",
    "乌克兰",
    "友谊",
    "输油管道",
    "管道",
    "石油",
    "原油",
    "沙特",
    "霍尔木兹",
    "摩根士丹利",
    "美股",
    "Atlassian",
    "Microsoft",
    "微软",
    "财捷",
)


def _event_rows(readiness: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in readiness.get("rows") or []:
        if isinstance(row, dict) and row.get("route_bucket") == "event_text_classification_required":
            rows.append(row)
    return rows


def _load_optional_json(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {}
    return _load_json(path)


def _rows_by_dp(report: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for row in report.get("rows") or []:
        if not isinstance(row, Mapping):
            continue
        dp_id = str(row.get("dp_id") or "")
        if dp_id:
            rows[dp_id] = dict(row)
    return rows


def _unknown_payload(
    *,
    dp_id: str,
    score_target: str,
    blocked_reason: str,
    required_policy: str,
    evidence_refs: list[str],
    rationale: str,
    draft_status: str = "unknown_event_text_classification_required",
    value_json_extra: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    value_json = {
        "review_required": True,
        "blocked_reason": blocked_reason,
        "required_policy": required_policy,
    }
    if value_json_extra:
        value_json.update(dict(value_json_extra))
    return {
        "target_dp_id": dp_id,
        "score_target": score_target,
        "data_status": "Unknown",
        "bridge_entry_data_status": "Unknown",
        "value_json": value_json,
        "confidence": _round(0.0),
        "evidence_refs": evidence_refs,
        "rationale": rationale,
        "review_status": "review_required",
        "safe_to_upsert_without_review": False,
        "draft_kind": "event_text_policy_pilot",
        "draft_status": draft_status,
        "pilot_only": True,
        "production_write_allowed": False,
    }


def _market_doc_refs(packet: Mapping[str, Any]) -> list[str]:
    refs = ["docs/audit/a_share_event_text_market_doc_review_packets_2026-06-19.json"]
    for example in packet.get("candidate_examples") or []:
        if not isinstance(example, Mapping):
            continue
        rel = example.get("market_relative_path") or example.get("path")
        if isinstance(rel, str) and rel.strip():
            refs.append(f"dockcase:{rel}")
    return list(dict.fromkeys(refs))


def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
    return any(term in text for term in terms)


def _example_text(example: Mapping[str, Any]) -> str:
    parts: list[str] = []
    for key in ("title", "excerpt"):
        value = example.get(key)
        if isinstance(value, str):
            parts.append(value)
    for hit in example.get("same_sentence_hits") or []:
        if isinstance(hit, Mapping):
            excerpt = hit.get("excerpt")
            if isinstance(excerpt, str):
                parts.append(excerpt)
    return "\n".join(parts)


def _substitute_tech_clean_examples(examples: Any) -> list[dict[str, Any]]:
    if not isinstance(examples, list):
        return []
    clean: list[dict[str, Any]] = []
    for example in examples:
        if not isinstance(example, Mapping):
            continue
        text = _example_text(example)
        if not text:
            continue
        if _contains_any(text, SUBSTITUTE_TECH_FALSE_CONTEXT_TERMS):
            continue
        if _contains_any(text, SUBSTITUTE_TECH_OPPORTUNITY_TERMS):
            continue
        if not _contains_any(text, SUBSTITUTE_TECH_RISK_TERMS):
            continue
        if not _contains_any(text, SUBSTITUTE_TECH_DIRECT_TERMS):
            continue
        same_sentence_hits = example.get("same_sentence_hits") or []
        if not isinstance(same_sentence_hits, list) or not same_sentence_hits:
            continue
        clean.append(dict(example))
    return clean


def _packet_with_examples(
    packet: Mapping[str, Any],
    examples: list[dict[str, Any]],
) -> dict[str, Any]:
    return {**dict(packet), "candidate_examples": examples}


def _known_payload(
    *,
    dp_id: str,
    score_target: str,
    candidate_row: Mapping[str, Any],
    market_doc_packet: Mapping[str, Any],
    profile: Mapping[str, Any],
) -> dict[str, Any]:
    deps = _deps(candidate_row)
    examples = market_doc_packet.get("candidate_examples") or []
    example_count = len(examples) if isinstance(examples, list) else 0
    same_sentence_count = 0
    target_hits: set[str] = set()
    direct_hits: set[str] = set()
    if isinstance(examples, list):
        for example in examples:
            if not isinstance(example, Mapping):
                continue
            same_sentence_count += len(example.get("same_sentence_hits") or [])
            target_hits.update(str(hit) for hit in (example.get("target_hits") or []))
            direct_hits.update(
                str(hit) for hit in (example.get("direct_transmission_hits") or [])
            )
    refs = _evidence_refs(candidate_row, deps) + _market_doc_refs(market_doc_packet)
    score = float(profile["score"])
    return {
        "target_dp_id": dp_id,
        "score_target": score_target,
        "data_status": "Known",
        "bridge_entry_data_status": "Known",
        "value_json": {
            "score": _round(score),
            "drivers": list(profile["drivers"]),
            "components": {
                "classification": profile["classification"],
                "market_doc_examples": example_count,
                "same_sentence_evidence_count": same_sentence_count,
                "target_hits": sorted(target_hits),
                "direct_transmission_hits": sorted(direct_hits),
                "score_mapping": "bounded review-only score in [-1, 1]",
            },
        },
        "confidence": _round(float(profile["confidence"])),
        "evidence_refs": list(dict.fromkeys(refs)),
        "rationale": str(profile["rationale"]),
        "review_status": "review_required",
        "safe_to_upsert_without_review": False,
        "draft_kind": "event_text_policy_pilot",
        "draft_status": "draft_known_market_doc_review_required",
        "pilot_only": True,
        "production_write_allowed": False,
    }


def _policy_for(dp_id: str) -> tuple[str, str]:
    policies = {
        "L0.compete.new_entrant": (
            "event_text_requires_new_entrant_classification",
            "needs direct evidence of new entrants, substitute entrants, or entry barriers changing for the target industry",
        ),
        "L0.compete.price_war": (
            "event_text_requires_price_war_classification",
            "needs direct evidence of price cuts, price-war language, promotion pressure, or competitive margin compression",
        ),
        "L0.compete.share_concentration": (
            "event_text_requires_share_concentration_classification",
            "needs direct evidence of market-share shifts, concentration changes, consolidation, or leader share gains/losses",
        ),
        "L0.policy.access_license": (
            "event_text_requires_access_license_classification",
            "needs direct evidence of license, access, approval, quota, or market-entry rule changes",
        ),
        "L0.policy.regulation": (
            "event_text_requires_regulation_classification",
            "needs direct evidence of regulatory tightening/loosening and a reviewed direction for affected A-share industries",
        ),
        "L0.policy.subsidy": (
            "event_text_requires_subsidy_classification",
            "needs direct evidence of subsidy creation, removal, expansion, reduction, or eligibility changes",
        ),
        "L0.policy.tax_trade": (
            "event_text_requires_tax_trade_classification",
            "needs direct evidence of tax, tariff, trade restriction, sanction, export-control, or FX-linked trade impact",
        ),
        "L0.tech.ai_automation": (
            "event_text_requires_ai_automation_classification",
            "needs direct evidence that AI or automation adoption changes productivity, cost, demand, or competition",
        ),
        "L0.tech.breakthrough": (
            "event_text_requires_breakthrough_classification",
            "needs direct evidence of technical breakthrough, validated product performance, or commercialization milestone",
        ),
        "L0.tech.substitute_tech": (
            "event_text_requires_substitute_tech_classification",
            "needs direct evidence of substitution risk or displacement by an alternative technology",
        ),
        "L8.shock.black_swan": (
            "event_text_requires_black_swan_classification",
            "needs direct evidence that a headline is a severe low-frequency shock with reviewed A-share transmission path",
        ),
        "L8.shock.supply_break": (
            "event_text_requires_supply_break_classification",
            "needs direct evidence of supply-chain interruption, logistics disruption, input shortage, or production halt",
        ),
    }
    return policies.get(
        dp_id,
        (
            "unsupported_event_text_policy",
            "no conservative event-text policy is defined for this dp_id",
        ),
    )


def _draft_payload(
    readiness_row: Mapping[str, Any],
    candidate_row: Mapping[str, Any] | None,
    market_doc_packet: Mapping[str, Any] | None,
) -> dict[str, Any]:
    dp_id = str(readiness_row.get("dp_id") or "")
    score_target = str(readiness_row.get("score_target") or "")
    if candidate_row is None:
        return _unknown_payload(
            dp_id=dp_id,
            score_target=score_target,
            blocked_reason="missing_candidate_evidence",
            required_policy="matching candidate-evidence row is required before event-text classification",
            evidence_refs=["docs/audit/a_share_non_manual_candidate_readiness_2026-06-19.json"],
            rationale="No matching candidate-evidence row exists; keep Unknown.",
            draft_status="unknown_missing_candidate_evidence",
        )
    deps = _deps(candidate_row)
    if isinstance(market_doc_packet, Mapping):
        status = str(market_doc_packet.get("classification_packet_status") or "")
        profile = REVIEW_PROFILES.get(dp_id)
        examples = market_doc_packet.get("candidate_examples") or []
        example_count = len(examples) if isinstance(examples, list) else 0
        if status == "market_doc_review_ready" and dp_id == "L0.tech.substitute_tech":
            profile = REVIEW_PROFILES[dp_id]
            clean_examples = _substitute_tech_clean_examples(examples)
            minimum_examples = int(profile.get("minimum_examples") or 1)
            if len(clean_examples) >= minimum_examples:
                return _known_payload(
                    dp_id=dp_id,
                    score_target=score_target,
                    candidate_row=candidate_row,
                    market_doc_packet=_packet_with_examples(
                        market_doc_packet, clean_examples
                    ),
                    profile=profile,
                )
            return _unknown_payload(
                dp_id=dp_id,
                score_target=score_target,
                blocked_reason="market_doc_clean_substitution_risk_evidence_required",
                required_policy=(
                    "needs at least two same-sentence examples where an "
                    "alternative technology displaces or threatens an A-share "
                    "company, industry, board, or supply chain; exclude domestic "
                    "import-substitution opportunity, foreign macro substitution, "
                    "trade-law replacement, and broad non-A-share market commentary"
                ),
                evidence_refs=_evidence_refs(candidate_row, deps)
                + _market_doc_refs(market_doc_packet),
                rationale=(
                    "The market-doc packet has substitution keywords, but the "
                    "retained examples do not clear the substitute-technology "
                    "risk filter. Keeping the field Unknown avoids treating "
                    "国产替代 opportunity headlines or overseas macro/news "
                    "substitution as a negative A-share risk factor."
                ),
                draft_status="unknown_market_doc_clean_evidence_required",
                value_json_extra={
                    "retained_market_doc_examples": example_count,
                    "clean_substitution_risk_examples": len(clean_examples),
                },
            )
        if (
            status == "market_doc_review_ready"
            and profile is not None
            and example_count >= int(profile.get("minimum_examples") or 1)
        ):
            return _known_payload(
                dp_id=dp_id,
                score_target=score_target,
                candidate_row=candidate_row,
                market_doc_packet=market_doc_packet,
                profile=profile,
            )
        if status != "market_doc_review_ready":
            blocked_reason = str(
                market_doc_packet.get("blocked_reason")
                or "market_doc_packet_not_review_ready"
            )
            required_policy = "; ".join(
                str(item)
                for item in (market_doc_packet.get("required_evidence") or [])
                if str(item).strip()
            ) or "market-doc packet must provide same-sentence target and direct transmission evidence"
            return _unknown_payload(
                dp_id=dp_id,
                score_target=score_target,
                blocked_reason=blocked_reason,
                required_policy=required_policy,
                evidence_refs=_evidence_refs(candidate_row, deps)
                + _market_doc_refs(market_doc_packet),
                rationale=(
                    "The local market-document packet is not ready for a "
                    "bounded Known draft; keep Unknown until the missing "
                    "target/transmission evidence is supplied."
                ),
                draft_status="unknown_market_doc_evidence_required",
            )
        if profile is None:
            return _unknown_payload(
                dp_id=dp_id,
                score_target=score_target,
                blocked_reason="market_doc_review_policy_not_defined",
                required_policy=(
                    "same-sentence evidence exists, but this dp_id still needs "
                    "a reviewed score-direction and magnitude policy"
                ),
                evidence_refs=_evidence_refs(candidate_row, deps)
                + _market_doc_refs(market_doc_packet),
                rationale=(
                    "The packet has local market-document evidence, but the "
                    "direction/magnitude mapping is ambiguous or unprofiled; "
                    "keep Unknown instead of fabricating a score."
                ),
                draft_status="unknown_market_doc_policy_required",
            )
        return _unknown_payload(
            dp_id=dp_id,
            score_target=score_target,
            blocked_reason="market_doc_review_examples_insufficient",
            required_policy=(
                "more retained same-sentence examples are required before a "
                "bounded Known review draft can be emitted"
            ),
            evidence_refs=_evidence_refs(candidate_row, deps)
            + _market_doc_refs(market_doc_packet),
            rationale=(
                "The packet has a conservative profile but too few retained "
                "examples for this dp_id's evidence floor; keep Unknown."
            ),
            draft_status="unknown_market_doc_examples_insufficient",
        )
    blocked_reason, required_policy = _policy_for(dp_id)
    return _unknown_payload(
        dp_id=dp_id,
        score_target=score_target,
        blocked_reason=blocked_reason,
        required_policy=required_policy,
        evidence_refs=_evidence_refs(candidate_row, deps),
        rationale=(
            "Market/event dependency rows and headline text are present, but the "
            "headlines have not been classified into this target event concept, "
            "direction, magnitude, and A-share transmission path; keep Unknown."
        ),
    )


def build_report(
    readiness_path: Path,
    candidate_path: Path,
    market_doc_review_packets_path: Path | None = None,
) -> dict[str, Any]:
    started = time.time()
    readiness = _load_json(readiness_path)
    candidate = _load_json(candidate_path)
    market_doc_packets = _rows_by_dp(_load_optional_json(market_doc_review_packets_path))
    candidate_rows = _candidate_rows_by_dp(candidate)
    rows: list[dict[str, Any]] = []
    for readiness_row in _event_rows(readiness):
        dp_id = str(readiness_row.get("dp_id") or "")
        score_target = str(readiness_row.get("score_target") or "")
        candidate_row = candidate_rows.get(dp_id)
        payload = _draft_payload(readiness_row, candidate_row, market_doc_packets.get(dp_id))
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
        "market_doc_review_packets_path": (
            _portable_path(market_doc_review_packets_path)
            if market_doc_review_packets_path
            else None
        ),
        "summary": {
            "event_text_task_count": len(rows),
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
            "market_doc_known_review_draft_count": sum(
                1
                for row in rows
                if row.get("draft_status") == "draft_known_market_doc_review_required"
            ),
            "market_doc_unknown_policy_required_count": sum(
                1
                for row in rows
                if row.get("draft_status") == "unknown_market_doc_policy_required"
            ),
            "market_doc_unknown_evidence_required_count": sum(
                1
                for row in rows
                if row.get("draft_status") == "unknown_market_doc_evidence_required"
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
        "# A-share event-text policy drafts",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- Event-text tasks: `{summary['event_text_task_count']}`",
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
            "- Market-document Known drafts are review-only score suggestions backed by retained local snippets.",
            "- Ambiguous, noisy, or unprofiled packets stay Unknown instead of fabricating a score.",
            "- Production score-affecting writes remain disabled.",
            "",
        ]
    )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--readiness-path", type=Path, default=DEFAULT_READINESS_PATH)
    parser.add_argument("--candidate-path", type=Path, default=DEFAULT_CANDIDATE_PATH)
    parser.add_argument(
        "--market-doc-review-packets-path",
        type=Path,
        default=DEFAULT_MARKET_DOC_REVIEW_PACKETS_PATH,
    )
    parser.add_argument("--json-output", type=Path, default=DEFAULT_JSON_OUTPUT)
    parser.add_argument("--md-output", type=Path, default=DEFAULT_MD_OUTPUT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_report(
        args.readiness_path,
        args.candidate_path,
        args.market_doc_review_packets_path,
    )
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.md_output.write_text(render_markdown(report), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
