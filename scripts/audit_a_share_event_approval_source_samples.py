#!/usr/bin/env python3
"""Check DOCKCASE source evidence for A-share event approval packets.

This report is reviewer support only. It traces event-text approval packets
back to their policy draft rows, market-document review packets, local repo
evidence, runtime dependency refs, and DOCKCASE news files. It never creates
approvals and never writes runtime values.
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

from scripts.audit_a_share_event_text_market_doc_evidence import (  # noqa: E402
    _clean_html_text,
    _html_title,
    _primary_article_text,
)


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_APPROVAL_PATH = ROOT / "docs/audit/a_share_approval_review_packets_2026-06-19.json"
DEFAULT_RISK_PATH = ROOT / "docs/audit/a_share_approval_packet_risk_review_2026-06-19.json"
DEFAULT_MARKET_REVIEW_PATH = (
    ROOT / "docs/audit/a_share_event_text_market_doc_review_packets_2026-06-19.json"
)
DEFAULT_MARKET_ROOT = Path("/Volumes/dockcase2tb/market_data")
DEFAULT_JSON_OUTPUT = (
    ROOT / "docs/audit/a_share_event_approval_source_samples_2026-06-19.json"
)
DEFAULT_MD_OUTPUT = (
    ROOT / "docs/audit/a_share_event_approval_source_samples_2026-06-19.md"
)


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


def _dockcase_path(market_root: Path, ref: str) -> Path:
    rel = ref.removeprefix("dockcase:")
    return market_root / rel


def _hits(text: str, keywords: list[Any]) -> list[str]:
    return sorted({str(keyword) for keyword in keywords if str(keyword) and str(keyword) in text})


def _first_excerpt(text: str, keywords: list[Any], *, width: int = 160) -> str:
    positions = [text.find(str(keyword)) for keyword in keywords if str(keyword) in text]
    positions = [position for position in positions if position >= 0]
    if not positions:
        return text[:width]
    start = max(0, min(positions) - width // 3)
    return text[start : start + width]


def _dockcase_ref_status(
    *,
    market_root: Path,
    evidence_refs: list[Any],
    target_hits: list[Any],
    direct_transmission_hits: list[Any],
) -> tuple[list[dict[str, Any]], list[str], list[str]]:
    docs: list[dict[str, Any]] = []
    missing: list[str] = []
    read_errors: list[str] = []
    for ref in evidence_refs:
        ref_text = str(ref)
        if not ref_text.startswith("dockcase:"):
            continue
        path = _dockcase_path(market_root, ref_text)
        exists = path.exists()
        title = ""
        text_chars = 0
        doc_target_hits: list[str] = []
        doc_direct_hits: list[str] = []
        excerpt = ""
        read_error = ""
        if exists:
            try:
                raw = path.read_text(encoding="utf-8", errors="replace")
                article = _primary_article_text(_clean_html_text(raw))
                title = _html_title(raw)
                text_chars = len(article)
                doc_target_hits = _hits(article, target_hits)
                doc_direct_hits = _hits(article, direct_transmission_hits)
                excerpt = _first_excerpt(article, doc_target_hits + doc_direct_hits)
            except OSError as exc:
                read_error = str(exc)
                read_errors.append(ref_text)
        else:
            missing.append(ref_text)
        docs.append(
            {
                "ref": ref_text,
                "path": str(path),
                "exists": exists,
                "readable": exists and not read_error,
                "read_error": read_error,
                "title": title,
                "text_chars": text_chars,
                "target_hits": doc_target_hits,
                "direct_transmission_hits": doc_direct_hits,
                "target_and_direct_hit": bool(doc_target_hits and doc_direct_hits),
                "excerpt": excerpt,
            }
        )
    return docs, missing, read_errors


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


def _event_evidence_review_template(candidate: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "template_status": "review_fill_required",
        "review_scope": "event_text_market_doc_evidence",
        "dp_id": candidate.get("dp_id"),
        "score_target": candidate.get("score_target"),
        "payload_sha256": candidate.get("payload_sha256"),
        "reviewer": "",
        "reviewed_at": "",
        "source_docs_verified": False,
        "target_event_accepted": False,
        "direct_transmission_accepted": False,
        "score_direction_accepted": False,
        "score_magnitude_accepted": False,
        "risk_acknowledged": False,
        "approval_allowed": False,
        "production_write_allowed": False,
    }


def _event_template_errors(template: Mapping[str, Any], candidate: Mapping[str, Any]) -> list[str]:
    expected = {
        "template_status": "review_fill_required",
        "review_scope": "event_text_market_doc_evidence",
        "dp_id": candidate.get("dp_id"),
        "score_target": candidate.get("score_target"),
        "payload_sha256": candidate.get("payload_sha256"),
        "reviewer": "",
        "reviewed_at": "",
        "source_docs_verified": False,
        "target_event_accepted": False,
        "direct_transmission_accepted": False,
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


def _market_review_refs(
    market_review_row: Mapping[str, Any],
) -> set[str]:
    refs: set[str] = set()
    for example in market_review_row.get("candidate_examples") or []:
        if not isinstance(example, Mapping):
            continue
        rel = example.get("market_relative_path")
        if rel:
            refs.add(f"dockcase:{rel}")
    return refs


def _components(candidate: Mapping[str, Any]) -> Mapping[str, Any]:
    value_json = candidate.get("value_json")
    if not isinstance(value_json, Mapping):
        return {}
    components = value_json.get("components")
    return components if isinstance(components, Mapping) else {}


def _candidate_row(
    *,
    repo_root: Path,
    market_root: Path,
    candidate: Mapping[str, Any],
    risk_row: Mapping[str, Any],
    market_review_row: Mapping[str, Any],
) -> dict[str, Any]:
    dp_id = str(candidate.get("dp_id") or "")
    evidence_refs = list(candidate.get("evidence_refs") or [])
    source_dependencies = list(candidate.get("source_dependencies") or [])
    source_report = _repo_path(repo_root, candidate.get("source_report"))
    source_payload = _load_json(source_report)
    source_row = _rows_by_dp(source_payload).get(dp_id, {})
    components = _components(candidate)
    target_hits = list(components.get("target_hits") or [])
    direct_transmission_hits = list(components.get("direct_transmission_hits") or [])

    doc_ref_existing_count, missing_doc_refs = _doc_ref_status(repo_root, evidence_refs)
    runtime_ref_count, missing_runtime_dependencies = _runtime_dependency_status(
        source_dependencies, evidence_refs
    )
    dockcase_docs, missing_dockcase_refs, dockcase_read_errors = _dockcase_ref_status(
        market_root=market_root,
        evidence_refs=evidence_refs,
        target_hits=target_hits,
        direct_transmission_hits=direct_transmission_hits,
    )
    dockcase_ref_count = len(dockcase_docs)
    dockcase_file_exists_count = sum(1 for doc in dockcase_docs if doc["exists"])
    dockcase_file_readable_count = sum(1 for doc in dockcase_docs if doc["readable"])
    dockcase_target_hit_count = sum(1 for doc in dockcase_docs if doc["target_hits"])
    dockcase_direct_hit_count = sum(
        1 for doc in dockcase_docs if doc["direct_transmission_hits"]
    )
    dockcase_target_and_direct_count = sum(
        1 for doc in dockcase_docs if doc["target_and_direct_hit"]
    )

    market_review_packet_found = bool(market_review_row)
    market_review_refs = _market_review_refs(market_review_row)
    packet_dockcase_refs = {str(ref) for ref in evidence_refs if str(ref).startswith("dockcase:")}
    missing_market_review_refs = sorted(packet_dockcase_refs - market_review_refs)
    market_review_contract_valid = bool(market_review_row.get("packet_contract_valid"))
    market_review_refs_complete = bool(
        packet_dockcase_refs and not missing_market_review_refs
    )

    contract_validation = source_row.get("contract_validation")
    contract_validation = contract_validation if isinstance(contract_validation, Mapping) else {}
    bridge_validation = source_row.get("bridge_validation")
    bridge_validation = bridge_validation if isinstance(bridge_validation, Mapping) else {}
    source_report_exists = source_report.exists()
    source_row_found = bool(source_row)
    source_payload_matches = _source_payload_matches_candidate(
        source_row=source_row,
        candidate=candidate,
    )
    source_contract_valid = bool(contract_validation.get("contract_valid"))
    source_bridge_ready = bool(bridge_validation.get("final_score_target_ready"))
    approval_template = candidate.get("approval_record_template")
    approval_template = approval_template if isinstance(approval_template, Mapping) else {}
    approval_template_blank_valid = bool(
        candidate.get("approval_record_template_contract_valid")
        and _approval_template_blank_and_valid(approval_template)
    )
    review_template = _event_evidence_review_template(candidate)
    template_errors = _event_template_errors(review_template, candidate)
    event_template_valid = not template_errors
    repo_doc_refs_complete = not missing_doc_refs
    runtime_refs_complete = not missing_runtime_dependencies
    dockcase_refs_exist = dockcase_ref_count > 0 and dockcase_file_exists_count == dockcase_ref_count
    dockcase_refs_readable = (
        dockcase_ref_count > 0 and dockcase_file_readable_count == dockcase_ref_count
    )
    dockcase_keyword_evidence_ready = dockcase_target_and_direct_count > 0
    reviewer_packet_complete = bool(
        source_report_exists
        and source_row_found
        and source_payload_matches
        and source_contract_valid
        and source_bridge_ready
        and repo_doc_refs_complete
        and runtime_refs_complete
        and market_review_packet_found
        and market_review_contract_valid
        and market_review_refs_complete
        and dockcase_refs_exist
        and dockcase_refs_readable
        and dockcase_keyword_evidence_ready
        and approval_template_blank_valid
        and event_template_valid
    )
    return {
        "dp_id": dp_id,
        "score_target": candidate.get("score_target"),
        "risk_class": risk_row.get("risk_class"),
        "risk_reasons": list(risk_row.get("risk_reasons") or []),
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
        "market_doc_review_packet_found": market_review_packet_found,
        "market_doc_review_packet_contract_valid": market_review_contract_valid,
        "market_doc_review_refs_complete": market_review_refs_complete,
        "missing_market_doc_review_refs": missing_market_review_refs,
        "dockcase_ref_count": dockcase_ref_count,
        "dockcase_file_exists_count": dockcase_file_exists_count,
        "dockcase_file_readable_count": dockcase_file_readable_count,
        "missing_dockcase_refs": missing_dockcase_refs,
        "dockcase_read_error_refs": dockcase_read_errors,
        "dockcase_doc_target_hit_count": dockcase_target_hit_count,
        "dockcase_doc_direct_transmission_hit_count": dockcase_direct_hit_count,
        "dockcase_doc_target_and_direct_hit_count": dockcase_target_and_direct_count,
        "dockcase_keyword_evidence_ready": dockcase_keyword_evidence_ready,
        "dockcase_evidence_preview": [
            {
                "ref": doc["ref"],
                "title": doc["title"],
                "target_hits": doc["target_hits"],
                "direct_transmission_hits": doc["direct_transmission_hits"],
            }
            for doc in dockcase_docs[:3]
        ],
        "market_doc_examples": components.get("market_doc_examples"),
        "same_sentence_evidence_count": components.get("same_sentence_evidence_count"),
        "target_hits": target_hits,
        "direct_transmission_hits": direct_transmission_hits,
        "approval_record_template_blank_contract_valid": approval_template_blank_valid,
        "event_evidence_review_template": review_template,
        "event_evidence_review_template_contract_valid": event_template_valid,
        "event_evidence_review_template_validation_errors": template_errors,
        "event_evidence_review_template_blank_pending": event_template_valid,
        "reviewer_packet_complete": reviewer_packet_complete,
        "auto_approval_allowed": False,
        "runtime_write_allowed": False,
        "production_write_allowed": False,
    }


def build_report(
    *,
    approval_path: Path,
    risk_path: Path,
    market_review_path: Path,
    market_root: Path = DEFAULT_MARKET_ROOT,
    repo_root: Path = ROOT,
) -> dict[str, Any]:
    started = time.time()
    approvals = _load_json(approval_path)
    risks = _rows_by_dp(_load_json(risk_path))
    market_reviews = _rows_by_dp(_load_json(market_review_path))
    rows = [
        _candidate_row(
            repo_root=repo_root,
            market_root=market_root,
            candidate=row,
            risk_row=risks.get(str(row.get("dp_id") or ""), {}),
            market_review_row=market_reviews.get(str(row.get("dp_id") or ""), {}),
        )
        for row in approvals.get("rows") or []
        if isinstance(row, Mapping) and row.get("source_kind") == "event_text_policy_pilot"
    ]
    rows.sort(key=lambda row: str(row.get("dp_id") or ""))
    summary = {
        "event_approval_source_sample_count": len(rows),
        "event_text_approval_packet_count": len(rows),
        "individual_event_evidence_review_required_count": sum(
            1
            for row in rows
            if row.get("risk_class") == "individual_event_evidence_review_required"
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
        "repo_doc_evidence_refs_complete_count": sum(
            1 for row in rows if not row["missing_doc_evidence_refs"]
        ),
        "runtime_dependency_ref_complete_count": sum(
            1 for row in rows if not row["missing_runtime_dependency_refs"]
        ),
        "market_doc_review_packet_found_count": sum(
            1 for row in rows if row["market_doc_review_packet_found"]
        ),
        "market_doc_review_packet_contract_valid_count": sum(
            1 for row in rows if row["market_doc_review_packet_contract_valid"]
        ),
        "market_doc_review_refs_complete_count": sum(
            1 for row in rows if row["market_doc_review_refs_complete"]
        ),
        "dockcase_ref_count": sum(int(row["dockcase_ref_count"]) for row in rows),
        "dockcase_file_exists_count": sum(
            int(row["dockcase_file_exists_count"]) for row in rows
        ),
        "dockcase_file_readable_count": sum(
            int(row["dockcase_file_readable_count"]) for row in rows
        ),
        "dockcase_file_missing_count": sum(len(row["missing_dockcase_refs"]) for row in rows),
        "dockcase_file_read_error_count": sum(
            len(row["dockcase_read_error_refs"]) for row in rows
        ),
        "dockcase_keyword_evidence_ready_count": sum(
            1 for row in rows if row["dockcase_keyword_evidence_ready"]
        ),
        "approval_record_template_blank_contract_valid_count": sum(
            1 for row in rows if row["approval_record_template_blank_contract_valid"]
        ),
        "event_evidence_review_template_count": len(rows),
        "event_evidence_review_template_contract_valid_count": sum(
            1 for row in rows if row["event_evidence_review_template_contract_valid"]
        ),
        "event_evidence_review_template_contract_invalid_count": sum(
            1 for row in rows if not row["event_evidence_review_template_contract_valid"]
        ),
        "event_evidence_review_template_blank_pending_count": sum(
            1 for row in rows if row["event_evidence_review_template_blank_pending"]
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
            "market_review_path": _portable_path(market_review_path),
            "market_root": str(market_root),
            "repo_root": str(repo_root),
        },
        "summary": summary,
        "rows": rows,
    }


def render_markdown(report: Mapping[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# A-share event approval source-sample audit",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- Event approval packets checked: `{summary['event_text_approval_packet_count']}`",
        f"- Individual event-evidence reviews required: `{summary['individual_event_evidence_review_required_count']}`",
        f"- Source payloads match candidates: `{summary['source_payload_matches_candidate_count']}`",
        f"- Market-doc review packets found: `{summary['market_doc_review_packet_found_count']}`",
        f"- Market-doc review refs complete: `{summary['market_doc_review_refs_complete_count']}`",
        f"- DOCKCASE refs: `{summary['dockcase_ref_count']}`",
        f"- DOCKCASE files found: `{summary['dockcase_file_exists_count']}`",
        f"- DOCKCASE files readable: `{summary['dockcase_file_readable_count']}`",
        f"- DOCKCASE keyword evidence ready rows: `{summary['dockcase_keyword_evidence_ready_count']}`",
        f"- Event evidence review templates: `{summary['event_evidence_review_template_count']}`",
        f"- Event evidence template contracts valid: `{summary['event_evidence_review_template_contract_valid_count']}`",
        f"- Event evidence templates blank/pending: `{summary['event_evidence_review_template_blank_pending_count']}`",
        f"- Reviewer packets complete: `{summary['reviewer_packet_complete_count']}`",
        f"- Auto approvals allowed: `{summary['auto_approval_allowed_count']}`",
        f"- Runtime writes allowed: `{summary['runtime_write_allowed_count']}`",
        f"- Production writes allowed: `{summary['production_write_allowed_count']}`",
        f"- Score mutation: `{summary['score_mutation']}`",
        "",
        "## Candidate Evidence Matrix",
        "",
        "| dp_id | risk | source match | market packet | dockcase refs | keyword evidence | review template | reviewer packet |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in report["rows"]:
        dockcase_refs = f"{row.get('dockcase_file_readable_count')}/{row.get('dockcase_ref_count')}"
        lines.append(
            "| "
            f"`{row.get('dp_id')}` | "
            f"`{row.get('risk_class')}` | "
            f"{'yes' if row.get('source_payload_matches_candidate') else 'no'} | "
            f"{'yes' if row.get('market_doc_review_packet_found') else 'no'} | "
            f"{dockcase_refs} | "
            f"{'yes' if row.get('dockcase_keyword_evidence_ready') else 'no'} | "
            f"{'yes' if row.get('event_evidence_review_template_contract_valid') else 'no'} | "
            f"{'yes' if row.get('reviewer_packet_complete') else 'no'} |"
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- Complete event reviewer packets still are not approvals.",
            "- The audit verifies local traceability from approval packets to source drafts, market-doc review packets, runtime dependency refs, and DOCKCASE news files.",
            "- Runtime writes remain blocked until a reviewer fills approval records and event-evidence review decisions with matching payload hashes.",
            "",
        ]
    )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--approval-path", type=Path, default=DEFAULT_APPROVAL_PATH)
    parser.add_argument("--risk-path", type=Path, default=DEFAULT_RISK_PATH)
    parser.add_argument("--market-review-path", type=Path, default=DEFAULT_MARKET_REVIEW_PATH)
    parser.add_argument("--market-root", type=Path, default=DEFAULT_MARKET_ROOT)
    parser.add_argument("--json-output", type=Path, default=DEFAULT_JSON_OUTPUT)
    parser.add_argument("--md-output", type=Path, default=DEFAULT_MD_OUTPUT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_report(
        approval_path=args.approval_path,
        risk_path=args.risk_path,
        market_review_path=args.market_review_path,
        market_root=args.market_root,
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
