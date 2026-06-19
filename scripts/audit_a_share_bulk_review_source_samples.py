#!/usr/bin/env python3
"""Check source evidence for A-share bulk-review approval candidates.

This report is reviewer support only. It verifies that the bulk/borderline
approval candidates can be traced back to their source draft reports and
evidence references, but it never creates approvals or writes runtime values.
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
DEFAULT_BULK_PATH = ROOT / "docs/audit/a_share_bulk_review_approval_candidates_2026-06-19.json"
DEFAULT_JSON_OUTPUT = ROOT / "docs/audit/a_share_bulk_review_source_samples_2026-06-19.json"
DEFAULT_MD_OUTPUT = ROOT / "docs/audit/a_share_bulk_review_source_samples_2026-06-19.md"


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


def _approval_draft_blank_and_valid(draft: Mapping[str, Any]) -> bool:
    return bool(
        draft.get("approval_id") == ""
        and draft.get("approval_status") == ""
        and draft.get("approval_scope") == "runtime_write"
        and draft.get("reviewer") == ""
        and draft.get("approved_at") == ""
        and draft.get("risk_acknowledged") is False
        and draft.get("template_status") == "review_fill_required"
    )


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


def _sample_ready(candidate: Mapping[str, Any]) -> bool:
    if not candidate.get("requires_sample_check"):
        return True
    for example in _sample_examples(candidate):
        if example.get("keyword_hits") and example.get("question") and example.get("answer"):
            return True
    return False


def _candidate_row(repo_root: Path, candidate: Mapping[str, Any]) -> dict[str, Any]:
    dp_id = str(candidate.get("dp_id") or "")
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
    draft = candidate.get("approval_record_draft")
    draft = draft if isinstance(draft, Mapping) else {}
    sample_examples = _sample_examples(candidate)
    sample_ready = _sample_ready(candidate)
    contract_validation = source_row.get("contract_validation")
    contract_validation = contract_validation if isinstance(contract_validation, Mapping) else {}
    bridge_validation = source_row.get("bridge_validation")
    bridge_validation = bridge_validation if isinstance(bridge_validation, Mapping) else {}
    source_row_found = bool(source_row)
    source_report_exists = source_report.exists()
    source_contract_valid = bool(contract_validation.get("contract_valid"))
    source_bridge_ready = bool(bridge_validation.get("final_score_target_ready"))
    approval_draft_blank_valid = bool(
        candidate.get("approval_record_draft_contract_valid")
        and _approval_draft_blank_and_valid(draft)
    )
    evidence_refs_complete = not missing_doc_refs and not missing_runtime_dependencies
    reviewer_packet_complete = bool(
        source_report_exists
        and source_row_found
        and source_payload_matches
        and source_contract_valid
        and source_bridge_ready
        and evidence_refs_complete
        and approval_draft_blank_valid
        and sample_ready
    )
    return {
        "dp_id": dp_id,
        "risk_class": candidate.get("risk_class"),
        "source_kind": candidate.get("source_kind"),
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
        "approval_record_draft_blank_contract_valid": approval_draft_blank_valid,
        "requires_sample_check": bool(candidate.get("requires_sample_check")),
        "sample_evidence_count": len(sample_examples),
        "sample_evidence_ready": sample_ready,
        "sample_evidence_preview": [
            {
                "ts_code": example.get("ts_code"),
                "date": example.get("date"),
                "keyword_hits": example.get("keyword_hits") or [],
            }
            for example in sample_examples[:3]
        ],
        "reviewer_packet_complete": reviewer_packet_complete,
        "auto_approval_allowed": False,
        "runtime_write_allowed": False,
        "production_write_allowed": False,
    }


def build_report(*, bulk_path: Path, repo_root: Path = ROOT) -> dict[str, Any]:
    started = time.time()
    bulk = _load_json(bulk_path)
    rows = [
        _candidate_row(repo_root, row)
        for row in bulk.get("rows") or []
        if isinstance(row, Mapping)
    ]
    rows.sort(
        key=lambda row: (
            1 if row.get("requires_sample_check") else 0,
            str(row.get("dp_id") or ""),
        )
    )
    summary = {
        "candidate_count": len(rows),
        "strict_bulk_candidate_count": sum(
            1 for row in rows if row.get("risk_class") == "bulk_structured_review_candidate"
        ),
        "borderline_sample_check_candidate_count": sum(
            1
            for row in rows
            if row.get("risk_class") == "borderline_structured_text_review_candidate"
        ),
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
        "approval_record_draft_blank_contract_valid_count": sum(
            1 for row in rows if row["approval_record_draft_blank_contract_valid"]
        ),
        "borderline_sample_evidence_ready_count": sum(
            1
            for row in rows
            if row["requires_sample_check"] and row["sample_evidence_ready"]
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
            "bulk_path": _portable_path(bulk_path),
            "repo_root": str(repo_root),
        },
        "summary": summary,
        "rows": rows,
    }


def render_markdown(report: Mapping[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# A-share bulk-review source-sample audit",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- Candidates checked: `{summary['candidate_count']}`",
        f"- Strict bulk candidates: `{summary['strict_bulk_candidate_count']}`",
        f"- Borderline sample-check candidates: `{summary['borderline_sample_check_candidate_count']}`",
        f"- Source reports found: `{summary['source_report_exists_count']}`",
        f"- Source rows found: `{summary['source_report_row_found_count']}`",
        f"- Source payloads match candidates: `{summary['source_payload_matches_candidate_count']}`",
        f"- Evidence refs complete: `{summary['evidence_refs_complete_count']}`",
        f"- Blank approval drafts valid: `{summary['approval_record_draft_blank_contract_valid_count']}`",
        f"- Borderline sample evidence ready: `{summary['borderline_sample_evidence_ready_count']}`",
        f"- Reviewer packets complete: `{summary['reviewer_packet_complete_count']}`",
        f"- Auto approvals allowed: `{summary['auto_approval_allowed_count']}`",
        f"- Runtime writes allowed: `{summary['runtime_write_allowed_count']}`",
        f"- Production writes allowed: `{summary['production_write_allowed_count']}`",
        f"- Score mutation: `{summary['score_mutation']}`",
        "",
        "## Candidate Evidence Matrix",
        "",
        "| dp_id | risk | source row | payload match | deps refs | sample ready | reviewer packet |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for row in report["rows"]:
        dependency_total = len(row.get("source_dependencies") or [])
        dependency_refs = f"{row.get('runtime_dependency_ref_count')}/{dependency_total}"
        lines.append(
            "| "
            f"`{row.get('dp_id')}` | "
            f"`{row.get('risk_class')}` | "
            f"{'yes' if row.get('source_report_row_found') else 'no'} | "
            f"{'yes' if row.get('source_payload_matches_candidate') else 'no'} | "
            f"{dependency_refs} | "
            f"{'yes' if row.get('sample_evidence_ready') else 'no'} | "
            f"{'yes' if row.get('reviewer_packet_complete') else 'no'} |"
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- Complete reviewer packets still are not approvals.",
            "- The audit only verifies traceability from approval candidates back to source reports, runtime dependency references, and sample evidence.",
            "- Runtime writes remain blocked until a reviewer fills approval records with matching payload hashes and risk acknowledgement.",
            "",
        ]
    )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bulk-path", type=Path, default=DEFAULT_BULK_PATH)
    parser.add_argument("--json-output", type=Path, default=DEFAULT_JSON_OUTPUT)
    parser.add_argument("--md-output", type=Path, default=DEFAULT_MD_OUTPUT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_report(bulk_path=args.bulk_path)
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    args.md_output.write_text(render_markdown(report), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
