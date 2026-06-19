#!/usr/bin/env python3
"""Adjudicate retained market-doc candidates for event Unknown A-share fields.

The upstream market-doc acquisition audit intentionally keeps broad review
candidates.  This report applies a conservative semantic screen to the retained
examples for the two event Unknown rows so weak local evidence cannot be
mistaken for scoreable Known values.

It is read-only and never writes runtime score data.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import time
from collections import Counter
from pathlib import Path
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CANDIDATE_PATH = (
    ROOT / "docs/audit/a_share_unknown_market_doc_acquisition_candidates_2026-06-19.json"
)
DEFAULT_CLOSURE_PATH = ROOT / "docs/audit/a_share_unknown_closure_matrix_2026-06-19.json"
DEFAULT_JSON_OUTPUT = (
    ROOT / "docs/audit/a_share_unknown_event_evidence_adjudication_2026-06-19.json"
)
DEFAULT_MD_OUTPUT = (
    ROOT / "docs/audit/a_share_unknown_event_evidence_adjudication_2026-06-19.md"
)


NEW_ENTRANT_INCUMBENT_TERMS = (
    "公告称",
    "公司拟",
    "公司以",
    "以自有资金",
    "控股股东",
    "纳入公司合并报表",
    "新公司为主体建设",
    "进一步提升",
    "项目",
)
NEW_ENTRANT_EXTERNAL_TERMS = (
    "跨界进入",
    "外部厂商",
    "新进入者",
    "竞争对手",
    "抢占份额",
    "进入该市场",
)
SUBSTITUTE_FOREIGN_OR_MACRO_TERMS = (
    "斯洛伐克",
    "乌克兰",
    "特朗普",
    "美国总统",
    "韩国",
    "阿联酋",
    "沙特",
    "霍尔木兹",
    "印度",
    "俄油",
    "美股",
    "摩根士丹利",
    "英伟达",
    "美光",
    "全球能源供应链",
)
SUBSTITUTE_OPPORTUNITY_TERMS = (
    "国产替代",
    "进口替代",
    "替代进口",
    "机会",
    "机遇",
    "受益",
    "创造机遇",
    "替代空间",
    "高景气",
    "规模化替代进口设备",
)
SUBSTITUTE_NEGATIVE_RISK_TERMS = (
    "被替代风险",
    "颠覆性冲击",
    "替代技术",
    "威胁",
    "份额流失",
    "挤压",
    "淘汰",
)
ASHARE_DIRECT_TERMS = (
    "A股",
    "上市公司",
    "板块",
    "个股",
    "产业链",
    "供应链",
)


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _portable_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(ROOT))
    except ValueError:
        return str(path)


def _hits(text: str, terms: tuple[str, ...]) -> list[str]:
    return [term for term in terms if term in text]


def _rows_by_dp(payload: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    rows: dict[str, Mapping[str, Any]] = {}
    for row in payload.get("rows") or []:
        if isinstance(row, Mapping) and row.get("dp_id"):
            rows[str(row["dp_id"])] = row
    return rows


def _adjudicate_new_entrant(candidate: Mapping[str, Any]) -> dict[str, Any]:
    text = f"{candidate.get('title') or ''} {candidate.get('excerpt') or ''}"
    external_hits = _hits(text, NEW_ENTRANT_EXTERNAL_TERMS)
    incumbent_hits = _hits(text, NEW_ENTRANT_INCUMBENT_TERMS)
    direct_hits = _hits(text, ASHARE_DIRECT_TERMS)
    if external_hits and direct_hits and not incumbent_hits:
        verdict = "accepted_for_review"
        reason = "external_new_entrant_with_direct_a_share_transmission"
    elif incumbent_hits:
        verdict = "rejected_incumbent_expansion"
        reason = "listed_company_subsidiary_joint_venture_or_capacity_project_not_external_new_entrant"
    else:
        verdict = "ambiguous_new_entrant_context"
        reason = "new_company_language_without_external_competitive_entry_evidence"
    return {
        "title": candidate.get("title"),
        "market_relative_path": candidate.get("market_relative_path"),
        "source_classification": candidate.get("classification"),
        "adjudication_verdict": verdict,
        "adjudication_reason": reason,
        "direct_a_share_hits": direct_hits,
        "reject_or_context_hits": incumbent_hits,
        "excerpt": candidate.get("excerpt"),
    }


def _adjudicate_substitute(candidate: Mapping[str, Any]) -> dict[str, Any]:
    text = f"{candidate.get('title') or ''} {candidate.get('excerpt') or ''}"
    direct_hits = _hits(text, ASHARE_DIRECT_TERMS)
    foreign_hits = _hits(text, SUBSTITUTE_FOREIGN_OR_MACRO_TERMS)
    opportunity_hits = _hits(text, SUBSTITUTE_OPPORTUNITY_TERMS)
    risk_hits = _hits(text, SUBSTITUTE_NEGATIVE_RISK_TERMS)
    if risk_hits and direct_hits and not foreign_hits and not opportunity_hits:
        verdict = "accepted_for_review"
        reason = "negative_substitution_risk_with_direct_a_share_or_industry_transmission"
    elif foreign_hits:
        verdict = "rejected_foreign_or_macro_context"
        reason = "foreign_macro_or_non_a_share_market_context_not_a_share_substitution_risk"
    elif opportunity_hits:
        verdict = "rejected_opportunity_or_import_substitution"
        reason = "domestic_import_substitution_or_opportunity_language_not_negative_substitute_risk"
    else:
        verdict = "ambiguous_substitution_context"
        reason = "substitution_keyword_without_clean_negative_a_share_threat"
    return {
        "title": candidate.get("title"),
        "market_relative_path": candidate.get("market_relative_path"),
        "source_classification": candidate.get("classification"),
        "adjudication_verdict": verdict,
        "adjudication_reason": reason,
        "direct_a_share_hits": direct_hits,
        "reject_or_context_hits": foreign_hits + opportunity_hits,
        "risk_hits": risk_hits,
        "excerpt": candidate.get("excerpt"),
    }


def _required_next_evidence(dp_id: str) -> list[str]:
    if dp_id == "L0.compete.new_entrant":
        return [
            "external entrant or cross-industry player entering the relevant market",
            "same-source causal transmission to A-share company, sector, supply chain, or margin/share pressure",
            "reviewed direction, magnitude, and bounded value_json.score in [-1, 1]",
        ]
    return [
        "negative substitute technology risk, not import-substitution opportunity",
        "direct A-share company, sector, board, supply-chain, or margin/share pressure transmission",
        "at least two clean examples or one primary-source high-conviction example",
        "reviewed direction, magnitude, and bounded value_json.score in [-1, 1]",
    ]


def _row(
    candidate_row: Mapping[str, Any],
    closure_row: Mapping[str, Any] | None,
) -> dict[str, Any]:
    dp_id = str(candidate_row.get("dp_id") or "")
    candidates = [
        c for c in candidate_row.get("candidate_examples") or [] if isinstance(c, Mapping)
    ]
    if dp_id == "L0.compete.new_entrant":
        adjudicated = [_adjudicate_new_entrant(candidate) for candidate in candidates]
    else:
        adjudicated = [_adjudicate_substitute(candidate) for candidate in candidates]
    accepted = [
        candidate
        for candidate in adjudicated
        if candidate["adjudication_verdict"] == "accepted_for_review"
    ]
    verdict_counts = Counter(str(candidate["adjudication_verdict"]) for candidate in adjudicated)
    status = (
        "candidate_semantically_ready_for_classifier"
        if accepted
        else "no_clean_known_candidate_after_adjudication"
    )
    return {
        "dp_id": dp_id,
        "score_target": candidate_row.get("score_target")
        or (closure_row or {}).get("score_target"),
        "source_candidate_status": candidate_row.get("candidate_status"),
        "source_review_candidate_count": candidate_row.get("review_candidate_count"),
        "retained_candidate_count": len(candidates),
        "adjudicated_candidate_count": len(adjudicated),
        "accepted_candidate_count": len(accepted),
        "rejected_or_ambiguous_candidate_count": len(adjudicated) - len(accepted),
        "adjudication_status": status,
        "adjudication_verdict_counts": dict(sorted(verdict_counts.items())),
        "data_status": "Unknown",
        "known_draft_sufficient": False,
        "auto_known_ready": False,
        "approval_ready": False,
        "runtime_write_allowed": False,
        "production_write_allowed": False,
        "current_blocked_reason": (closure_row or {}).get("blocked_reason"),
        "required_next_evidence": _required_next_evidence(dp_id),
        "adjudicated_examples": adjudicated,
        "score_mutation": "none",
    }


def _validation_errors(row: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    if row.get("data_status") != "Unknown":
        errors.append("data_status must stay Unknown")
    if row.get("known_draft_sufficient") is not False:
        errors.append("known_draft_sufficient must be false")
    if row.get("auto_known_ready") is not False:
        errors.append("auto_known_ready must be false")
    if row.get("approval_ready") is not False:
        errors.append("approval_ready must be false")
    if row.get("runtime_write_allowed") is not False:
        errors.append("runtime_write_allowed must be false")
    if row.get("production_write_allowed") is not False:
        errors.append("production_write_allowed must be false")
    if not row.get("required_next_evidence"):
        errors.append("required_next_evidence is required")
    return errors


def build_report(*, candidate_path: Path, closure_path: Path) -> dict[str, Any]:
    started = time.time()
    candidate_report = _load_json(candidate_path)
    closure_rows = _rows_by_dp(_load_json(closure_path))
    rows = [
        _row(candidate_row, closure_rows.get(str(candidate_row.get("dp_id") or "")))
        for candidate_row in candidate_report.get("rows") or []
        if isinstance(candidate_row, Mapping)
        and str(candidate_row.get("dp_id") or "")
        in {"L0.compete.new_entrant", "L0.tech.substitute_tech"}
    ]
    rows.sort(key=lambda row: str(row["dp_id"]))
    for row in rows:
        errors = _validation_errors(row)
        row["adjudication_contract_valid"] = not errors
        row["adjudication_validation_errors"] = errors
    verdict_counts: Counter[str] = Counter()
    for row in rows:
        verdict_counts.update(row["adjudication_verdict_counts"])
    return {
        "generated_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "elapsed_s": round(time.time() - started, 3),
        "inputs": {
            "candidate_path": _portable_path(candidate_path),
            "closure_path": _portable_path(closure_path),
        },
        "summary": {
            "event_unknown_adjudication_row_count": len(rows),
            "candidate_examples_reviewed_count": sum(
                int(row["adjudicated_candidate_count"]) for row in rows
            ),
            "accepted_candidate_count": sum(int(row["accepted_candidate_count"]) for row in rows),
            "rejected_or_ambiguous_candidate_count": sum(
                int(row["rejected_or_ambiguous_candidate_count"]) for row in rows
            ),
            "remaining_unknown_count": sum(1 for row in rows if row["data_status"] == "Unknown"),
            "known_draft_sufficient_count": 0,
            "auto_known_ready_count": 0,
            "approval_ready_count": 0,
            "adjudication_contract_valid_count": sum(
                1 for row in rows if row["adjudication_contract_valid"]
            ),
            "adjudication_contract_invalid_count": sum(
                1 for row in rows if not row["adjudication_contract_valid"]
            ),
            "runtime_write_allowed_count": 0,
            "production_write_allowed_count": 0,
            "adjudication_verdict_counts": dict(sorted(verdict_counts.items())),
            "score_mutation": "none; this audit is read-only and does not alter realtime_current",
        },
        "rows": rows,
    }


def render_markdown(report: Mapping[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# A-share Unknown event evidence adjudication",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- Event Unknown rows adjudicated: `{summary['event_unknown_adjudication_row_count']}`",
        f"- Candidate examples reviewed: `{summary['candidate_examples_reviewed_count']}`",
        f"- Accepted candidates: `{summary['accepted_candidate_count']}`",
        f"- Rejected or ambiguous candidates: `{summary['rejected_or_ambiguous_candidate_count']}`",
        f"- Remaining Unknown rows: `{summary['remaining_unknown_count']}`",
        f"- Known-draft sufficient rows: `{summary['known_draft_sufficient_count']}`",
        f"- Auto Known-ready rows: `{summary['auto_known_ready_count']}`",
        f"- Approval-ready rows: `{summary['approval_ready_count']}`",
        f"- Contracts valid: `{summary['adjudication_contract_valid_count']}`",
        f"- Contracts invalid: `{summary['adjudication_contract_invalid_count']}`",
        f"- Production writes allowed: `{summary['production_write_allowed_count']}`",
        f"- Score mutation: `{summary['score_mutation']}`",
        "",
        "## Rows",
        "",
        "| dp_id | retained | accepted | rejected/ambiguous | status | production write |",
        "|---|---:|---:|---:|---|---:|",
    ]
    for row in report["rows"]:
        lines.append(
            "| "
            f"`{row['dp_id']}` | "
            f"{row['retained_candidate_count']} | "
            f"{row['accepted_candidate_count']} | "
            f"{row['rejected_or_ambiguous_candidate_count']} | "
            f"`{row['adjudication_status']}` | "
            f"{'yes' if row['production_write_allowed'] else 'no'} |"
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- This adjudicates retained local candidates only; it does not create Known values.",
            "- Accepted candidates would still require reviewer classification, bounded value generation, and approval.",
            "- With zero accepted candidates, both rows remain Unknown and require stronger primary/source evidence.",
            "",
        ]
    )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate-path", type=Path, default=DEFAULT_CANDIDATE_PATH)
    parser.add_argument("--closure-path", type=Path, default=DEFAULT_CLOSURE_PATH)
    parser.add_argument("--json-output", type=Path, default=DEFAULT_JSON_OUTPUT)
    parser.add_argument("--md-output", type=Path, default=DEFAULT_MD_OUTPUT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_report(candidate_path=args.candidate_path, closure_path=args.closure_path)
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    args.md_output.write_text(render_markdown(report), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
