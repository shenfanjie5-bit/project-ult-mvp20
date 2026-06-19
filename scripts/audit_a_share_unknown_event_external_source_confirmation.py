#!/usr/bin/env python3
"""Package external-source confirmation candidates for event Unknown rows.

Local DOCKCASE market documents did not contain high-quality confirmation for
the remaining two low-confidence event leads. This audit records externally
reviewed public-source candidates and keeps them as review inputs only. It
never creates Known values, approval records, or score writes.
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

from scripts.audit_a_share_unknown_acquisition_backlog import (  # noqa: E402
    ROOT,
    _load_json,
    _portable_path,
)


DEFAULT_PRIMARY_CONFIRMATION_PATH = (
    ROOT / "docs/audit/a_share_unknown_event_primary_source_confirmation_2026-06-19.json"
)
DEFAULT_JSON_OUTPUT = (
    ROOT / "docs/audit/a_share_unknown_event_external_source_confirmation_2026-06-19.json"
)
DEFAULT_MD_OUTPUT = (
    ROOT / "docs/audit/a_share_unknown_event_external_source_confirmation_2026-06-19.md"
)


EXTERNAL_SOURCE_CARDS: dict[str, list[dict[str, Any]]] = {
    "L0.compete.new_entrant": [
        {
            "source_id": "chnfund_ai_chip_change_2026_03_24",
            "title": "AI芯片大变局",
            "publisher": "中国基金报 / 英华价值研究院",
            "url": "https://www.chnfund.com/article/AR8d11415a-f9d7-009b-25e2-3a20303c8abb",
            "source_quality": "high_quality_secondary_analysis",
            "source_status": "external_confirmation_candidate",
            "evidence_summary": (
                "Reports that Alibaba T-Head/internet-major AI chip companies are rising, "
                "changing the China AI-chip competitive landscape and challenging third-party "
                "AI-chip companies represented by Cambricon; also gives A-share/Cambricon "
                "price and revenue context."
            ),
            "review_need": "review event fit, direct A-share transmission, direction, and bounded magnitude",
        },
        {
            "source_id": "gz_kjj_idc_ai_chip_shipments_2026",
            "title": "2025年国产AI芯片出货约165万张占市场41%",
            "publisher": "广州市科学技术局",
            "url": "https://kjj.gz.gov.cn/xydt/content/post_10771935.html",
            "source_quality": "official_repost_of_market_data",
            "source_status": "external_supporting_context",
            "evidence_summary": (
                "Cites IDC-style shipment data showing Alibaba T-Head ahead of Cambricon "
                "among domestic AI-chip vendors; supports competitive context but does not "
                "by itself provide a reviewed score value."
            ),
            "review_need": "use only as supporting market-share context unless paired with reviewed transmission",
        },
        {
            "source_id": "cls_alibaba_chip_response_2025_09_01",
            "title": "事关AI芯片！阿里发声：支持国产为真 大规模采购寒武纪不实",
            "publisher": "科创板日报 / 财联社",
            "url": "https://www.cls.cn/detail/2132741",
            "source_quality": "high_quality_newswire_with_company_response",
            "source_status": "external_supporting_context",
            "evidence_summary": (
                "Records Alibaba's response that a large Cambricon purchase rumor was untrue "
                "and notes Alibaba's self-developed chip exploration; supports supply-chain "
                "and competitor context but not a standalone Known value."
            ),
            "review_need": "supporting source only; does not set direction or magnitude",
        },
    ],
    "L0.tech.substitute_tech": [
        {
            "source_id": "inspur_2024_annual_report_tech_update_risk",
            "title": "浪潮电子信息产业股份有限公司2024年年度报告全文",
            "publisher": "浪潮信息 / 东方财富公告 PDF",
            "url": "https://pdf.dfcfw.com/pdf/H2_AN202503281648797582_1.pdf",
            "source_quality": "primary_company_filing",
            "source_status": "external_confirmation_candidate",
            "evidence_summary": (
                "Company filing discloses technology-update innovation risk: if R&D and "
                "new proprietary products do not keep pace with market demand, competitive "
                "advantage may weaken and customer-loss risk may rise."
            ),
            "review_need": "review whether generic technology-update risk can satisfy substitute-tech scoring policy",
        },
        {
            "source_id": "tmtpost_inspur_margin_tech_risk_2024",
            "title": "浪潮信息营收新高背后，毛利率下滑至7.6%",
            "publisher": "钛媒体",
            "url": "https://www.tmtpost.com/7223439.html",
            "source_quality": "high_quality_secondary_reporting",
            "source_status": "external_supporting_context",
            "evidence_summary": (
                "Summarizes the company's technology-update risk disclosure and margin "
                "pressure; supports risk context but does not directly select a score value."
            ),
            "review_need": "supporting context for source review",
        },
        {
            "source_id": "sina_inspur_2025_profit_margin_2026_04_10",
            "title": "浪潮信息2025年报深度解析",
            "publisher": "新浪财经 / 全球财说",
            "url": "https://finance.sina.com.cn/stock/stockzmt/2026-04-10/doc-inhtztir5038382.shtml",
            "source_quality": "secondary_financial_analysis",
            "source_status": "external_supporting_context",
            "evidence_summary": (
                "Describes Inspur Information as an A-share AI-computing bellwether with "
                "high revenue growth but low margins, supporting margin-pressure context."
            ),
            "review_need": "supporting context only; not a substitute-technology confirmation by itself",
        },
    ],
}


CLASSIFIER_INPUT_POLICIES: dict[str, dict[str, Any]] = {
    "L0.compete.new_entrant": {
        "event_concept": "new_entrant_competitive_pressure",
        "target_universe": "A-share AI-chip / accelerator incumbents",
        "required_labels": [
            "event_fit",
            "direct_a_share_transmission",
            "direction",
            "magnitude",
            "time_window",
            "bounded_value_json",
        ],
        "guardrails": [
            "do not treat broad AI-chip competition as direct A-share pressure without a company/industry transmission link",
            "do not infer score magnitude from share price movement alone",
            "separate entrant pressure from customer purchase rumors and ordinary market-share context",
        ],
    },
    "L0.tech.substitute_tech": {
        "event_concept": "substitute_technology_risk",
        "target_universe": "A-share AI-computing hardware and server supply-chain issuers",
        "required_labels": [
            "event_fit",
            "substitution_mechanism",
            "direct_a_share_transmission",
            "direction",
            "magnitude",
            "bounded_value_json",
        ],
        "guardrails": [
            "do not treat generic technology-update risk as substitute-tech evidence without a substitution mechanism",
            "do not convert margin pressure into substitute-tech score without a reviewed causal link",
            "separate issuer-specific filing risk from broad industry commentary",
        ],
    },
}


def _primary_rows(report: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in report.get("rows") or []:
        if isinstance(row, Mapping) and row.get("dp_id") in EXTERNAL_SOURCE_CARDS:
            rows.append(dict(row))
    return rows


def _classifier_input_candidate(dp_id: str, cards: list[dict[str, Any]]) -> dict[str, Any] | None:
    confirmation_cards = [
        card
        for card in cards
        if card.get("source_status") == "external_confirmation_candidate"
    ]
    if not confirmation_cards:
        return None
    supporting_cards = [
        card
        for card in cards
        if card.get("source_status") == "external_supporting_context"
    ]
    policy = CLASSIFIER_INPUT_POLICIES.get(dp_id, {})
    return {
        "available": True,
        "dp_id": dp_id,
        "event_concept": policy.get("event_concept"),
        "target_universe": policy.get("target_universe"),
        "primary_source_ids": [str(card.get("source_id") or "") for card in confirmation_cards],
        "supporting_source_ids": [str(card.get("source_id") or "") for card in supporting_cards],
        "required_labels": list(policy.get("required_labels") or []),
        "guardrails": list(policy.get("guardrails") or []),
        "classifier_input_ready": False,
        "missing_before_classifier_ready": [
            "reviewed_event_fit",
            "reviewed_direct_a_share_transmission",
            "reviewed_direction",
            "reviewed_magnitude",
            "bounded_value_json",
        ],
        "direct_known_draft_ready": False,
        "review_required": True,
        "score_mutation": "none",
    }


def _classifier_input_validation_errors(
    candidate: Mapping[str, Any] | None,
    cards: list[dict[str, Any]],
) -> list[str]:
    if candidate is None:
        return ["classifier_input_candidate missing"]
    errors: list[str] = []
    card_ids = {str(card.get("source_id") or "") for card in cards}
    primary_ids = [str(item) for item in candidate.get("primary_source_ids") or []]
    supporting_ids = [
        str(item) for item in candidate.get("supporting_source_ids") or []
    ]
    required_labels = [
        str(item) for item in candidate.get("required_labels") or []
    ]
    guardrails = [str(item) for item in candidate.get("guardrails") or []]
    if not candidate.get("event_concept"):
        errors.append("event_concept is required")
    if not candidate.get("target_universe"):
        errors.append("target_universe is required")
    if not primary_ids:
        errors.append("at least one primary_source_id is required")
    for source_id in primary_ids + supporting_ids:
        if source_id not in card_ids:
            errors.append(f"source_id {source_id!r} is not present in source cards")
    if len(required_labels) < 5:
        errors.append("at least five required labels are required")
    if len(guardrails) < 2:
        errors.append("at least two guardrails are required")
    if candidate.get("classifier_input_ready") is not False:
        errors.append("classifier_input_ready must remain false")
    if candidate.get("direct_known_draft_ready") is not False:
        errors.append("direct_known_draft_ready must remain false")
    if candidate.get("review_required") is not True:
        errors.append("review_required must be true")
    return errors


def _classifier_review_template(
    *,
    packet_id: str,
    dp_id: str,
    candidate: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    if candidate is None:
        return None
    return {
        "template_status": "review_fill_required",
        "packet_id": packet_id,
        "dp_id": dp_id,
        "review_scope": "event_classifier_input",
        "reviewer": "",
        "reviewed_at": "",
        "event_concept": candidate.get("event_concept"),
        "primary_source_ids": list(candidate.get("primary_source_ids") or []),
        "required_labels": list(candidate.get("required_labels") or []),
        "event_fit_accepted": False,
        "direct_a_share_transmission_accepted": False,
        "direction_accepted": False,
        "magnitude_accepted": False,
        "bounded_value_json_accepted": False,
        "guardrails_acknowledged": False,
        "known_draft_allowed": False,
        "classifier_ready_allowed": False,
        "production_write_allowed": False,
    }


def _classifier_review_template_errors(
    template: Mapping[str, Any] | None,
    *,
    packet_id: str,
    dp_id: str,
    candidate: Mapping[str, Any] | None,
) -> list[str]:
    if candidate is None:
        return []
    if template is None:
        return ["classifier_review_template missing"]
    errors: list[str] = []
    if template.get("template_status") != "review_fill_required":
        errors.append("template_status must be review_fill_required")
    if template.get("packet_id") != packet_id:
        errors.append("template packet_id must match packet")
    if template.get("dp_id") != dp_id:
        errors.append("template dp_id must match packet")
    if template.get("review_scope") != "event_classifier_input":
        errors.append("review_scope must be event_classifier_input")
    if template.get("reviewer") != "":
        errors.append("reviewer must be blank")
    if template.get("reviewed_at") != "":
        errors.append("reviewed_at must be blank")
    if template.get("event_concept") != candidate.get("event_concept"):
        errors.append("event_concept must match classifier candidate")
    if template.get("primary_source_ids") != candidate.get("primary_source_ids"):
        errors.append("primary_source_ids must match classifier candidate")
    if template.get("required_labels") != candidate.get("required_labels"):
        errors.append("required_labels must match classifier candidate")
    for key in (
        "event_fit_accepted",
        "direct_a_share_transmission_accepted",
        "direction_accepted",
        "magnitude_accepted",
        "bounded_value_json_accepted",
        "guardrails_acknowledged",
        "known_draft_allowed",
        "classifier_ready_allowed",
        "production_write_allowed",
    ):
        if template.get(key) is not False:
            errors.append(f"{key} must be false in blank template")
    return errors


def _packet(row: Mapping[str, Any]) -> dict[str, Any]:
    dp_id = str(row.get("dp_id") or "")
    cards = EXTERNAL_SOURCE_CARDS.get(dp_id, [])
    status_counts = Counter(str(card["source_status"]) for card in cards)
    confirmation_candidates = status_counts.get("external_confirmation_candidate", 0)
    classifier_input_candidate = _classifier_input_candidate(dp_id, cards)
    classifier_input_validation_errors = (
        _classifier_input_validation_errors(classifier_input_candidate, cards)
        if classifier_input_candidate
        else []
    )
    packet_id = str(row.get("packet_id") or "")
    classifier_review_template = _classifier_review_template(
        packet_id=packet_id,
        dp_id=dp_id,
        candidate=classifier_input_candidate,
    )
    classifier_review_template_validation_errors = (
        _classifier_review_template_errors(
            classifier_review_template,
            packet_id=packet_id,
            dp_id=dp_id,
            candidate=classifier_input_candidate,
        )
        if classifier_input_candidate
        else []
    )
    packet = {
        "packet_id": packet_id,
        "dp_id": dp_id,
        "score_target": row.get("score_target"),
        "data_status": "Unknown",
        "local_confirmation_status": row.get("local_confirmation_status"),
        "external_source_status": (
            "external_confirmation_candidates_found"
            if confirmation_candidates
            else "external_supporting_context_only"
        ),
        "external_source_card_count": len(cards),
        "external_confirmation_candidate_count": confirmation_candidates,
        "external_supporting_context_count": status_counts.get(
            "external_supporting_context", 0
        ),
        "source_quality_counts": dict(
            sorted(Counter(str(card["source_quality"]) for card in cards).items())
        ),
        "external_source_cards": cards,
        "classifier_input_candidate_available": bool(classifier_input_candidate),
        "classifier_input_candidate": classifier_input_candidate,
        "classifier_input_candidate_contract_valid": (
            bool(classifier_input_candidate) and not classifier_input_validation_errors
        ),
        "classifier_input_candidate_validation_errors": classifier_input_validation_errors,
        "classifier_review_template": classifier_review_template,
        "classifier_review_template_contract_valid": (
            bool(classifier_review_template)
            and not classifier_review_template_validation_errors
        ),
        "classifier_review_template_validation_errors": (
            classifier_review_template_validation_errors
        ),
        "required_next_evidence": [
            "review source quality and event-policy fit",
            "review direct A-share transmission and direction",
            "define bounded magnitude/value_json before Known conversion",
            "send any Known/NotApplicable packet through approval gate",
        ],
        "classifier_ready": False,
        "known_draft_sufficient": False,
        "approval_ready": False,
        "safe_to_upsert_without_review": False,
        "runtime_write_allowed": False,
        "production_write_allowed": False,
        "score_mutation": "none",
    }
    errors = _validation_errors(packet)
    return {
        **packet,
        "external_confirmation_contract_valid": not errors,
        "external_confirmation_validation_errors": errors,
    }


def _validation_errors(packet: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    if not packet.get("packet_id"):
        errors.append("packet_id is required")
    if not packet.get("dp_id"):
        errors.append("dp_id is required")
    if packet.get("data_status") != "Unknown":
        errors.append("data_status must remain Unknown")
    if packet.get("classifier_ready") is not False:
        errors.append("classifier_ready must be false")
    if packet.get("known_draft_sufficient") is not False:
        errors.append("known_draft_sufficient must be false")
    if packet.get("approval_ready") is not False:
        errors.append("approval_ready must be false")
    if packet.get("safe_to_upsert_without_review") is not False:
        errors.append("safe_to_upsert_without_review must be false")
    if packet.get("runtime_write_allowed") is not False:
        errors.append("runtime_write_allowed must be false")
    if packet.get("production_write_allowed") is not False:
        errors.append("production_write_allowed must be false")
    if packet.get("classifier_input_candidate_available"):
        candidate = packet.get("classifier_input_candidate")
        if not isinstance(candidate, Mapping):
            errors.append("classifier_input_candidate must be present when available")
        elif candidate.get("classifier_input_ready") is not False:
            errors.append("classifier_input_candidate must not be classifier-ready")
        errors.extend(
            str(item)
            for item in packet.get("classifier_input_candidate_validation_errors") or []
        )
        if packet.get("classifier_review_template_contract_valid") is not True:
            errors.append("classifier_review_template contract must be valid")
        errors.extend(
            str(item)
            for item in packet.get("classifier_review_template_validation_errors") or []
        )
    cards = packet.get("external_source_cards")
    if not isinstance(cards, list) or not cards:
        errors.append("external_source_cards are required")
    return errors


def build_report(*, primary_confirmation_path: Path) -> dict[str, Any]:
    started = time.time()
    rows = [_packet(row) for row in _primary_rows(_load_json(primary_confirmation_path))]
    rows.sort(key=lambda row: str(row["packet_id"]))
    status_counts = Counter(str(row["external_source_status"]) for row in rows)
    return {
        "generated_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "elapsed_s": round(time.time() - started, 3),
        "inputs": {
            "primary_confirmation_path": _portable_path(primary_confirmation_path),
        },
        "summary": {
            "external_confirmation_packet_count": len(rows),
            "external_source_card_count": sum(
                int(row["external_source_card_count"]) for row in rows
            ),
            "external_confirmation_candidate_count": sum(
                int(row["external_confirmation_candidate_count"]) for row in rows
            ),
            "external_supporting_context_count": sum(
                int(row["external_supporting_context_count"]) for row in rows
            ),
            "rows_with_external_confirmation_candidate_count": status_counts.get(
                "external_confirmation_candidates_found", 0
            ),
            "rows_with_external_supporting_context_only_count": status_counts.get(
                "external_supporting_context_only", 0
            ),
            "classifier_input_candidate_count": sum(
                1 for row in rows if row["classifier_input_candidate_available"]
            ),
            "classifier_input_candidate_contract_valid_count": sum(
                1
                for row in rows
                if row["classifier_input_candidate_contract_valid"]
            ),
            "classifier_input_candidate_contract_invalid_count": sum(
                1
                for row in rows
                if row["classifier_input_candidate_available"]
                and not row["classifier_input_candidate_contract_valid"]
            ),
            "classifier_input_candidate_ready_count": 0,
            "classifier_input_review_required_count": sum(
                1
                for row in rows
                if (
                    isinstance(row.get("classifier_input_candidate"), Mapping)
                    and row["classifier_input_candidate"].get("review_required")
                )
            ),
            "classifier_input_primary_source_covered_count": sum(
                1
                for row in rows
                if (
                    isinstance(row.get("classifier_input_candidate"), Mapping)
                    and row["classifier_input_candidate"].get("primary_source_ids")
                )
            ),
            "classifier_input_required_label_count": sum(
                len(row["classifier_input_candidate"].get("required_labels") or [])
                for row in rows
                if isinstance(row.get("classifier_input_candidate"), Mapping)
            ),
            "classifier_input_guardrail_count": sum(
                len(row["classifier_input_candidate"].get("guardrails") or [])
                for row in rows
                if isinstance(row.get("classifier_input_candidate"), Mapping)
            ),
            "classifier_review_template_count": sum(
                1 for row in rows if row.get("classifier_review_template")
            ),
            "classifier_review_template_contract_valid_count": sum(
                1
                for row in rows
                if row.get("classifier_review_template_contract_valid")
            ),
            "classifier_review_template_contract_invalid_count": sum(
                1
                for row in rows
                if row.get("classifier_review_template")
                and not row.get("classifier_review_template_contract_valid")
            ),
            "classifier_review_template_blank_pending_count": sum(
                1
                for row in rows
                if (
                    isinstance(row.get("classifier_review_template"), Mapping)
                    and row["classifier_review_template"].get("template_status")
                    == "review_fill_required"
                    and row["classifier_review_template"].get("reviewer") == ""
                    and row["classifier_review_template"].get("reviewed_at") == ""
                )
            ),
            "classifier_review_template_input_ready_count": 0,
            "classifier_ready_count": 0,
            "known_draft_sufficient_count": 0,
            "approval_ready_count": 0,
            "external_confirmation_contract_valid_count": sum(
                1 for row in rows if row["external_confirmation_contract_valid"]
            ),
            "external_confirmation_contract_invalid_count": sum(
                1 for row in rows if not row["external_confirmation_contract_valid"]
            ),
            "runtime_write_allowed_count": 0,
            "production_write_allowed_count": 0,
            "external_source_status_counts": dict(sorted(status_counts.items())),
            "score_mutation": "none; this audit is read-only and does not alter realtime_current",
        },
        "rows": rows,
    }


def render_markdown(report: Mapping[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# A-share event Unknown external-source confirmation",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- External confirmation packets: `{summary['external_confirmation_packet_count']}`",
        f"- External source cards: `{summary['external_source_card_count']}`",
        f"- External confirmation candidates: `{summary['external_confirmation_candidate_count']}`",
        f"- External supporting-context cards: `{summary['external_supporting_context_count']}`",
        f"- Rows with external confirmation candidates: `{summary['rows_with_external_confirmation_candidate_count']}`",
        f"- Rows with external supporting context only: `{summary['rows_with_external_supporting_context_only_count']}`",
        f"- Classifier input candidates: `{summary['classifier_input_candidate_count']}`",
        f"- Classifier input candidate contracts valid: `{summary['classifier_input_candidate_contract_valid_count']}`",
        f"- Classifier input candidate contracts invalid: `{summary['classifier_input_candidate_contract_invalid_count']}`",
        f"- Classifier input candidates ready: `{summary['classifier_input_candidate_ready_count']}`",
        f"- Classifier input review required: `{summary['classifier_input_review_required_count']}`",
        f"- Classifier input primary sources covered: `{summary['classifier_input_primary_source_covered_count']}`",
        f"- Classifier input required labels: `{summary['classifier_input_required_label_count']}`",
        f"- Classifier input guardrails: `{summary['classifier_input_guardrail_count']}`",
        f"- Classifier review templates: `{summary['classifier_review_template_count']}`",
        f"- Classifier review template contracts valid: `{summary['classifier_review_template_contract_valid_count']}`",
        f"- Classifier review template contracts invalid: `{summary['classifier_review_template_contract_invalid_count']}`",
        f"- Classifier review templates blank pending: `{summary['classifier_review_template_blank_pending_count']}`",
        f"- Classifier review template inputs ready: `{summary['classifier_review_template_input_ready_count']}`",
        f"- Classifier-ready rows: `{summary['classifier_ready_count']}`",
        f"- Known-draft sufficient rows: `{summary['known_draft_sufficient_count']}`",
        f"- Approval-ready rows: `{summary['approval_ready_count']}`",
        f"- Production writes allowed: `{summary['production_write_allowed_count']}`",
        f"- Score mutation: `{summary['score_mutation']}`",
        "",
        "## Rows",
        "",
        "| packet | dp_id | status | cards | confirmation candidates | classifier input | input contract | review template | supporting context | contract | production write |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in report["rows"]:
        lines.append(
            "| "
            f"`{row['packet_id']}` | "
            f"`{row['dp_id']}` | "
            f"`{row['external_source_status']}` | "
            f"{row['external_source_card_count']} | "
            f"{row['external_confirmation_candidate_count']} | "
            f"{'yes' if row.get('classifier_input_candidate_available') else 'no'} | "
            f"{'yes' if row.get('classifier_input_candidate_contract_valid') else 'no'} | "
            f"{'yes' if row.get('classifier_review_template_contract_valid') else 'no'} | "
            f"{row['external_supporting_context_count']} | "
            f"{'yes' if row.get('external_confirmation_contract_valid') else 'no'} | "
            f"{'yes' if row.get('production_write_allowed') else 'no'} |"
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- External confirmation candidates are review inputs only.",
            "- Classifier input candidates package source IDs, required labels, and guardrails for review, but remain not classifier-ready.",
            "- Blank classifier review templates are review convenience only and are not confirmation records.",
            "- A reviewer still needs to confirm event fit, direct A-share transmission, direction, and bounded magnitude.",
            "- This audit creates no Known values, no approvals, and no runtime writes.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--primary-confirmation-path",
        type=Path,
        default=DEFAULT_PRIMARY_CONFIRMATION_PATH,
    )
    parser.add_argument("--json-output", type=Path, default=DEFAULT_JSON_OUTPUT)
    parser.add_argument("--md-output", type=Path, default=DEFAULT_MD_OUTPUT)
    args = parser.parse_args()

    report = build_report(primary_confirmation_path=args.primary_confirmation_path)
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    args.md_output.write_text(render_markdown(report), encoding="utf-8")


if __name__ == "__main__":
    main()
