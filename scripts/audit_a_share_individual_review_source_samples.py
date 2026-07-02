#!/usr/bin/env python3
"""Check source evidence for individual A-share approval review packets.

This report covers approval packets that are intentionally excluded from bulk
approval: structured proxy semantics and policy/non-fundamental score targets.
It verifies traceability and emits blank reviewer templates, but never creates
approvals or writes runtime values.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import time
from pathlib import Path
from typing import Any, Mapping

_BOOTSTRAP_ROOT = Path(__file__).resolve().parent.parent
if str(_BOOTSTRAP_ROOT) not in sys.path:
    sys.path.insert(0, str(_BOOTSTRAP_ROOT))


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_APPROVAL_PATH = ROOT / "docs/audit/a_share_approval_review_packets_2026-06-19.json"
DEFAULT_RISK_PATH = ROOT / "docs/audit/a_share_approval_packet_risk_review_2026-06-19.json"
DEFAULT_EVENT_SOURCE_PATH = (
    ROOT / "docs/audit/a_share_event_approval_source_samples_2026-06-19.json"
)
DEFAULT_JSON_OUTPUT = (
    ROOT / "docs/audit/a_share_individual_review_source_samples_2026-06-19.json"
)
DEFAULT_MD_OUTPUT = (
    ROOT / "docs/audit/a_share_individual_review_source_samples_2026-06-19.md"
)

INDIVIDUAL_RISK_CLASSES = {
    "individual_structured_review_required",
    "individual_policy_review_required",
}


def _portable_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(ROOT))
    except ValueError:
        return str(path)


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _rows_by_dp(payload: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for row in payload.get("rows") or []:
        if not isinstance(row, Mapping):
            continue
        dp_id = str(row.get("dp_id") or "")
        if dp_id:
            rows[dp_id] = dict(row)
    return rows


def _repo_path(repo_root: Path, value: Any) -> Path:
    path = Path(str(value or ""))
    if path.is_absolute():
        return path
    return repo_root / path


def _doc_ref_status(repo_root: Path, evidence_refs: list[Any]) -> tuple[int, list[str]]:
    existing = 0
    missing: list[str] = []
    for ref in evidence_refs:
        ref_text = str(ref)
        if not ref_text.startswith("docs/"):
            continue
        if _repo_path(repo_root, ref_text).exists():
            existing += 1
        else:
            missing.append(ref_text)
    return existing, missing


def _runtime_dependency_status(
    source_dependencies: list[Any], evidence_refs: list[Any]
) -> tuple[int, list[str]]:
    refs = {str(ref) for ref in evidence_refs}
    missing: list[str] = []
    matched = 0
    for dep in source_dependencies:
        expected = f"runtime:realtime_current:{dep}"
        if expected in refs:
            matched += 1
        else:
            missing.append(str(dep))
    return matched, missing


def _source_payload_matches_candidate(
    *, source_row: Mapping[str, Any], candidate: Mapping[str, Any]
) -> bool:
    payload = source_row.get("draft_payload")
    if not isinstance(payload, Mapping):
        return False
    checks = (
        payload.get("value_json") == candidate.get("value_json"),
        payload.get("confidence") == candidate.get("confidence"),
        payload.get("evidence_refs") == candidate.get("evidence_refs"),
        payload.get("rationale") == candidate.get("rationale"),
        payload.get("target_dp_id") == candidate.get("dp_id"),
        payload.get("data_status") == candidate.get("data_status"),
        payload.get("score_target") == candidate.get("score_target"),
    )
    return all(checks)


def _approval_template_blank_and_valid(template: Mapping[str, Any]) -> bool:
    return bool(
        template.get("approval_id") == ""
        and template.get("approval_status") == ""
        and template.get("approval_scope") == "runtime_write"
        and template.get("reviewer") == ""
        and template.get("approved_at") == ""
        and template.get("risk_acknowledged") is False
        and template.get("template_status") == "review_fill_required"
    )


def _sample_examples(candidate: Mapping[str, Any]) -> list[dict[str, Any]]:
    value_json = candidate.get("value_json")
    if not isinstance(value_json, Mapping):
        return []
    components = value_json.get("components")
    if not isinstance(components, Mapping):
        return []
    examples = components.get("evidence_examples")
    if not isinstance(examples, list):
        return []
    return [dict(example) for example in examples if isinstance(example, Mapping)]


def _text_sample_ready(candidate: Mapping[str, Any]) -> bool:
    if candidate.get("source_kind") != "local_structured_text_policy_pilot":
        return True
    for example in _sample_examples(candidate):
        if example.get("keyword_hits") and example.get("question") and example.get("answer"):
            return True
    return False


def _review_scope(candidate: Mapping[str, Any], risk_class: str) -> str:
    source_kind = str(candidate.get("source_kind") or "")
    if risk_class == "individual_structured_review_required":
        return "structured_proxy_semantic_review"
    if source_kind == "manual_policy_pilot":
        return "manual_policy_score_target_review"
    if source_kind == "event_text_policy_pilot":
        return "event_score_target_policy_review"
    return "individual_policy_score_target_review"


def _individual_review_template(
    candidate: Mapping[str, Any], risk_class: str
) -> dict[str, Any]:
    return {
        "template_status": "review_fill_required",
        "review_scope": _review_scope(candidate, risk_class),
        "risk_class": risk_class,
        "dp_id": candidate.get("dp_id"),
        "score_target": candidate.get("score_target"),
        "source_kind": candidate.get("source_kind"),
        "payload_sha256": candidate.get("payload_sha256"),
        "reviewer": "",
        "reviewed_at": "",
        "source_payload_verified": False,
        "runtime_dependencies_verified": False,
        "proxy_semantics_accepted": False,
        "formula_or_policy_mapping_accepted": False,
        "score_target_accepted": False,
        "score_direction_accepted": False,
        "score_magnitude_accepted": False,
        "risk_acknowledged": False,
        "approval_allowed": False,
        "production_write_allowed": False,
    }


def _template_errors(
    template: Mapping[str, Any], candidate: Mapping[str, Any], risk_class: str
) -> list[str]:
    expected = {
        "template_status": "review_fill_required",
        "review_scope": _review_scope(candidate, risk_class),
        "risk_class": risk_class,
        "dp_id": candidate.get("dp_id"),
        "score_target": candidate.get("score_target"),
        "source_kind": candidate.get("source_kind"),
        "payload_sha256": candidate.get("payload_sha256"),
        "reviewer": "",
        "reviewed_at": "",
        "source_payload_verified": False,
        "runtime_dependencies_verified": False,
        "proxy_semantics_accepted": False,
        "formula_or_policy_mapping_accepted": False,
        "score_target_accepted": False,
        "score_direction_accepted": False,
        "score_magnitude_accepted": False,
        "risk_acknowledged": False,
        "approval_allowed": False,
        "production_write_allowed": False,
    }
    errors: list[str] = []
    for key, expected_value in expected.items():
        if template.get(key) != expected_value:
            errors.append(f"{key} expected {expected_value!r}, got {template.get(key)!r}")
    return errors


def _source_report_summary_key(source_kind: Any) -> str:
    return {
        "local_structured_policy_pilot": "local_structured",
        "local_structured_text_policy_pilot": "local_structured_text",
        "local_single_dependency_policy_pilot": "local_single_dependency",
        "manual_policy_pilot": "manual_policy",
        "event_text_policy_pilot": "event_text",
    }.get(str(source_kind), "other")


def _candidate_route_refs(evidence_refs: list[Any]) -> list[str]:
    return sorted(str(ref) for ref in evidence_refs if str(ref).startswith("candidate_route:"))


def _candidate_row(
    *,
    repo_root: Path,
    candidate: Mapping[str, Any],
    risk_row: Mapping[str, Any],
    event_source_row: Mapping[str, Any],
) -> dict[str, Any]:
    dp_id = str(candidate.get("dp_id") or "")
    risk_class = str(risk_row.get("risk_class") or "")
    source_report = _repo_path(repo_root, candidate.get("source_report"))
    source_payload = _load_json(source_report)
    source_row = _rows_by_dp(source_payload).get(dp_id, {})
    evidence_refs = list(candidate.get("evidence_refs") or [])
    source_dependencies = list(candidate.get("source_dependencies") or [])
    doc_ref_existing_count, missing_doc_refs = _doc_ref_status(repo_root, evidence_refs)
    runtime_ref_count, missing_runtime_dependencies = _runtime_dependency_status(
        source_dependencies, evidence_refs
    )
    source_payload_matches = _source_payload_matches_candidate(
        source_row=source_row,
        candidate=candidate,
    )
    contract_validation = source_row.get("contract_validation")
    contract_validation = contract_validation if isinstance(contract_validation, Mapping) else {}
    bridge_validation = source_row.get("bridge_validation")
    bridge_validation = bridge_validation if isinstance(bridge_validation, Mapping) else {}
    approval_template = candidate.get("approval_record_template")
    approval_template = approval_template if isinstance(approval_template, Mapping) else {}
    sample_examples = _sample_examples(candidate)
    source_kind = str(candidate.get("source_kind") or "")
    route_refs = _candidate_route_refs(evidence_refs)
    event_source_row_found = bool(event_source_row) if source_kind == "event_text_policy_pilot" else False
    event_source_packet_complete = (
        bool(event_source_row.get("reviewer_packet_complete"))
        if source_kind == "event_text_policy_pilot"
        else True
    )
    template = _individual_review_template(candidate, risk_class)
    template_validation_errors = _template_errors(template, candidate, risk_class)
    template_valid = not template_validation_errors
    text_sample_ready = _text_sample_ready(candidate)
    source_report_exists = source_report.exists()
    source_row_found = bool(source_row)
    source_contract_valid = bool(contract_validation.get("contract_valid"))
    source_bridge_ready = bool(bridge_validation.get("final_score_target_ready"))
    approval_template_blank_valid = bool(
        candidate.get("approval_record_template_contract_valid")
        and _approval_template_blank_and_valid(approval_template)
    )
    evidence_refs_complete = not missing_doc_refs and not missing_runtime_dependencies
    reviewer_packet_complete = bool(
        source_report_exists
        and source_row_found
        and source_payload_matches
        and source_contract_valid
        and source_bridge_ready
        and evidence_refs_complete
        and approval_template_blank_valid
        and text_sample_ready
        and event_source_packet_complete
        and template_valid
    )
    return {
        "dp_id": dp_id,
        "risk_class": risk_class,
        "risk_reasons": list(risk_row.get("risk_reasons") or []),
        "source_kind": candidate.get("source_kind"),
        "source_report_group": _source_report_summary_key(candidate.get("source_kind")),
        "score_target": candidate.get("score_target"),
        "source_report": candidate.get("source_report"),
        "source_report_exists": source_report_exists,
        "source_report_row_found": source_row_found,
        "source_draft_status": source_row.get("draft_status"),
        "source_payload_matches_candidate": source_payload_matches,
        "source_contract_valid": source_contract_valid,
        "source_bridge_final_score_ready": source_bridge_ready,
        "source_dependencies": source_dependencies,
        "runtime_dependency_ref_count": runtime_ref_count,
        "missing_runtime_dependency_refs": missing_runtime_dependencies,
        "doc_evidence_ref_count": doc_ref_existing_count,
        "missing_doc_evidence_refs": missing_doc_refs,
        "candidate_route_refs": route_refs,
        "approval_record_template_blank_contract_valid": approval_template_blank_valid,
        "text_sample_evidence_count": len(sample_examples),
        "text_sample_evidence_ready": text_sample_ready,
        "text_sample_evidence_preview": [
            {
                "ts_code": example.get("ts_code"),
                "date": example.get("date"),
                "keyword_hits": example.get("keyword_hits") or [],
            }
            for example in sample_examples[:3]
        ],
        "event_source_sample_row_found": event_source_row_found,
        "event_source_sample_reviewer_packet_complete": event_source_packet_complete,
        "individual_review_template": template,
        "individual_review_template_contract_valid": template_valid,
        "individual_review_template_validation_errors": template_validation_errors,
        "individual_review_template_blank_pending": template_valid,
        "reviewer_packet_complete": reviewer_packet_complete,
        "auto_approval_allowed": False,
        "runtime_write_allowed": False,
        "production_write_allowed": False,
    }


def build_report(
    *,
    approval_path: Path,
    risk_path: Path,
    event_source_path: Path,
    repo_root: Path = ROOT,
) -> dict[str, Any]:
    started = time.time()
    approvals = _load_json(approval_path)
    risks = _rows_by_dp(_load_json(risk_path))
    event_source_rows = _rows_by_dp(_load_json(event_source_path))
    rows = []
    for candidate in approvals.get("rows") or []:
        if not isinstance(candidate, Mapping):
            continue
        risk_row = risks.get(str(candidate.get("dp_id") or ""), {})
        risk_class = str(risk_row.get("risk_class") or "")
        if risk_class not in INDIVIDUAL_RISK_CLASSES:
            continue
        rows.append(
            _candidate_row(
                repo_root=repo_root,
                candidate=candidate,
                risk_row=risk_row,
                event_source_row=event_source_rows.get(str(candidate.get("dp_id") or ""), {}),
            )
        )
    rows.sort(key=lambda row: (str(row.get("risk_class") or ""), str(row.get("dp_id") or "")))
    source_kind_counts: dict[str, int] = {}
    score_target_counts: dict[str, int] = {}
    for row in rows:
        source_kind = str(row.get("source_kind") or "")
        score_target = str(row.get("score_target") or "")
        source_kind_counts[source_kind] = source_kind_counts.get(source_kind, 0) + 1
        score_target_counts[score_target] = score_target_counts.get(score_target, 0) + 1
    summary = {
        "individual_review_source_sample_count": len(rows),
        "individual_structured_review_required_count": sum(
            1 for row in rows if row["risk_class"] == "individual_structured_review_required"
        ),
        "individual_policy_review_required_count": sum(
            1 for row in rows if row["risk_class"] == "individual_policy_review_required"
        ),
        "manual_policy_review_count": sum(
            1 for row in rows if row["source_kind"] == "manual_policy_pilot"
        ),
        "event_policy_review_count": sum(
            1 for row in rows if row["source_kind"] == "event_text_policy_pilot"
        ),
        "structured_proxy_review_count": sum(
            1
            for row in rows
            if row["source_kind"]
            in {
                "local_structured_policy_pilot",
                "local_structured_text_policy_pilot",
            }
        ),
        "source_kind_counts": dict(sorted(source_kind_counts.items())),
        "score_target_counts": dict(sorted(score_target_counts.items())),
        "source_report_exists_count": sum(1 for row in rows if row["source_report_exists"]),
        "source_report_row_found_count": sum(1 for row in rows if row["source_report_row_found"]),
        "source_payload_matches_candidate_count": sum(
            1 for row in rows if row["source_payload_matches_candidate"]
        ),
        "source_contract_valid_count": sum(1 for row in rows if row["source_contract_valid"]),
        "source_bridge_final_score_ready_count": sum(
            1 for row in rows if row["source_bridge_final_score_ready"]
        ),
        "evidence_refs_complete_count": sum(
            1
            for row in rows
            if not row["missing_doc_evidence_refs"]
            and not row["missing_runtime_dependency_refs"]
        ),
        "approval_record_template_blank_contract_valid_count": sum(
            1 for row in rows if row["approval_record_template_blank_contract_valid"]
        ),
        "text_sample_evidence_ready_count": sum(
            1
            for row in rows
            if row["source_kind"] == "local_structured_text_policy_pilot"
            and row["text_sample_evidence_ready"]
        ),
        "event_source_sample_row_found_count": sum(
            1 for row in rows if row["event_source_sample_row_found"]
        ),
        "event_source_sample_reviewer_packet_complete_count": sum(
            1
            for row in rows
            if row["source_kind"] == "event_text_policy_pilot"
            and row["event_source_sample_reviewer_packet_complete"]
        ),
        "individual_review_template_count": len(rows),
        "individual_review_template_contract_valid_count": sum(
            1 for row in rows if row["individual_review_template_contract_valid"]
        ),
        "individual_review_template_contract_invalid_count": sum(
            1 for row in rows if not row["individual_review_template_contract_valid"]
        ),
        "individual_review_template_blank_pending_count": sum(
            1 for row in rows if row["individual_review_template_blank_pending"]
        ),
        "reviewer_packet_complete_count": sum(
            1 for row in rows if row["reviewer_packet_complete"]
        ),
        "auto_approval_allowed_count": 0,
        "runtime_write_allowed_count": 0,
        "production_write_allowed_count": 0,
        "score_mutation": "none; source-sample audit is read-only and does not alter realtime_current",
    }
    return {
        "generated_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "elapsed_s": round(time.time() - started, 3),
        "inputs": {
            "approval_path": _portable_path(approval_path),
            "risk_path": _portable_path(risk_path),
            "event_source_path": _portable_path(event_source_path),
            "repo_root": str(repo_root),
        },
        "summary": summary,
        "rows": rows,
    }


def render_markdown(report: Mapping[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# A-share individual-review source-sample audit",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- Individual review packets checked: `{summary['individual_review_source_sample_count']}`",
        f"- Structured proxy reviews required: `{summary['individual_structured_review_required_count']}`",
        f"- Policy reviews required: `{summary['individual_policy_review_required_count']}`",
        f"- Source payloads match candidates: `{summary['source_payload_matches_candidate_count']}`",
        f"- Evidence refs complete: `{summary['evidence_refs_complete_count']}`",
        f"- Text sample evidence ready: `{summary['text_sample_evidence_ready_count']}`",
        f"- Event source-sample packets complete: `{summary['event_source_sample_reviewer_packet_complete_count']}`",
        f"- Individual review templates: `{summary['individual_review_template_count']}`",
        f"- Individual review template contracts valid: `{summary['individual_review_template_contract_valid_count']}`",
        f"- Individual review templates blank/pending: `{summary['individual_review_template_blank_pending_count']}`",
        f"- Reviewer packets complete: `{summary['reviewer_packet_complete_count']}`",
        f"- Auto approvals allowed: `{summary['auto_approval_allowed_count']}`",
        f"- Runtime writes allowed: `{summary['runtime_write_allowed_count']}`",
        f"- Production writes allowed: `{summary['production_write_allowed_count']}`",
        f"- Score mutation: `{summary['score_mutation']}`",
        "",
        "## Candidate Evidence Matrix",
        "",
        "| dp_id | risk | source | target | source match | evidence refs | review template | reviewer packet |",
        "|---|---|---|---|---:|---:|---:|---:|",
    ]
    for row in report["rows"]:
        lines.append(
            "| "
            f"`{row.get('dp_id')}` | "
            f"`{row.get('risk_class')}` | "
            f"`{row.get('source_kind')}` | "
            f"`{row.get('score_target')}` | "
            f"{'yes' if row.get('source_payload_matches_candidate') else 'no'} | "
            f"{'yes' if not row.get('missing_doc_evidence_refs') and not row.get('missing_runtime_dependency_refs') else 'no'} | "
            f"{'yes' if row.get('individual_review_template_contract_valid') else 'no'} | "
            f"{'yes' if row.get('reviewer_packet_complete') else 'no'} |"
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- Complete individual reviewer packets still are not approvals.",
            "- Structured proxy, manual policy, non-fundamental score-target, and event risk-discount semantics remain reviewer decisions.",
            "- Runtime writes remain blocked until approval records and individual review decisions are filled with matching payload hashes.",
            "",
        ]
    )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--approval-path", type=Path, default=DEFAULT_APPROVAL_PATH)
    parser.add_argument("--risk-path", type=Path, default=DEFAULT_RISK_PATH)
    parser.add_argument("--event-source-path", type=Path, default=DEFAULT_EVENT_SOURCE_PATH)
    parser.add_argument("--json-output", type=Path, default=DEFAULT_JSON_OUTPUT)
    parser.add_argument("--md-output", type=Path, default=DEFAULT_MD_OUTPUT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_report(
        approval_path=args.approval_path,
        risk_path=args.risk_path,
        event_source_path=args.event_source_path,
    )
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    args.md_output.write_text(render_markdown(report), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
