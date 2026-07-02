#!/usr/bin/env python3
"""Strict source gate for event-text Unknown A-share fields.

The broad market-document scans keep many weak candidates for review. This
gate reruns a narrower local HTML scan for the two still-Unknown event fields
and only retains snippets that satisfy a direct event + direct A-share
transmission pattern. It is read-only and never creates Known values.
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

from scripts.audit_a_share_event_text_market_doc_evidence import (  # noqa: E402
    DIRECT_TRANSMISSION_KEYWORDS,
    TARGET_KEYWORDS,
    _doc_record,
    _hits,
    _iter_html_files,
)
from scripts.audit_a_share_unknown_acquisition_backlog import (  # noqa: E402
    ROOT,
    _load_json,
    _portable_path,
)


DEFAULT_BACKLOG_PATH = (
    ROOT / "docs/audit/a_share_unknown_acquisition_backlog_2026-06-19.json"
)
DEFAULT_ADJUDICATION_PATH = (
    ROOT / "docs/audit/a_share_unknown_event_evidence_adjudication_2026-06-19.json"
)
DEFAULT_MARKET_ROOT = Path("/Volumes/dockcase2tb/market_data")
DEFAULT_JSON_OUTPUT = (
    ROOT / "docs/audit/a_share_unknown_event_strict_source_gate_2026-06-19.json"
)
DEFAULT_MD_OUTPUT = (
    ROOT / "docs/audit/a_share_unknown_event_strict_source_gate_2026-06-19.md"
)

EVENT_DP_IDS = ("L0.compete.new_entrant", "L0.tech.substitute_tech")
ASHARE_TERMS = (
    "A股",
    "A股公司",
    "上市公司",
    "个股",
    "板块",
    "概念股",
    "产业链",
    "供应链",
    "创业板",
    "沪深",
)
NEW_ENTRANT_STRICT_TERMS = (
    "新进入者",
    "外部厂商",
    "外部玩家",
    "竞争对手",
    "跨界进入",
    "跨界入局",
    "抢占份额",
    "进入该市场",
    "进入这一市场",
)
NEW_ENTRANT_REJECT_TERMS = (
    "公告称",
    "公司拟",
    "公司以",
    "以自有资金",
    "控股股东",
    "纳入公司合并报表",
    "新公司为主体建设",
    "子公司",
    "合资成立",
    "打新",
    "IPO",
    "网下配售",
    "基石投资",
)
SUBSTITUTE_STRICT_TERMS = (
    "被替代风险",
    "替代技术",
    "替代威胁",
    "颠覆性冲击",
    "份额流失",
    "挤压",
    "淘汰",
    "取代风险",
    "替代风险",
)
SUBSTITUTE_REJECT_TERMS = (
    "国产替代",
    "进口替代",
    "替代进口",
    "进口设备",
    "替代方案",
    "以取代",
    "取代被",
    "机会",
    "机遇",
    "利好",
    "受益",
    "特朗普",
    "斯洛伐克",
    "乌克兰",
    "韩国",
    "阿联酋",
    "沙特",
    "霍尔木兹",
    "印度",
    "俄油",
    "美股",
    "英伟达",
    "美光",
)


def _event_tasks(backlog: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    tasks: dict[str, dict[str, Any]] = {}
    for row in backlog.get("rows") or []:
        if not isinstance(row, Mapping):
            continue
        dp_id = str(row.get("dp_id") or "")
        if dp_id in EVENT_DP_IDS:
            tasks[dp_id] = dict(row)
    return tasks


def _adjudication_rows(adjudication: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for row in adjudication.get("rows") or []:
        if not isinstance(row, Mapping):
            continue
        dp_id = str(row.get("dp_id") or "")
        if dp_id:
            rows[dp_id] = dict(row)
    return rows


def _sentence_candidates(text: str) -> list[str]:
    # Local HTML extracts are already compact; line/sentence punctuation gives
    # enough windows for a strict source gate without another parser.
    chunks: list[str] = []
    for raw in text.replace("！", "。").replace("？", "。").split("。"):
        chunk = raw.strip()
        if chunk:
            chunks.append(chunk[:420])
    return chunks


def _candidate_base(doc: Mapping[str, Any], sentence: str) -> dict[str, Any]:
    return {
        "path": doc.get("path"),
        "market_relative_path": doc.get("market_relative_path"),
        "title": doc.get("title"),
        "excerpt": sentence,
    }


def _classify_new_entrant(doc: Mapping[str, Any], sentence: str) -> dict[str, Any] | None:
    text = f"{doc.get('title') or ''} {sentence}"
    strict_hits = _hits(text, NEW_ENTRANT_STRICT_TERMS)
    direct_hits = sorted(set(_hits(text, ASHARE_TERMS) + _hits(text, DIRECT_TRANSMISSION_KEYWORDS)))
    if not strict_hits or not direct_hits:
        return None
    reject_hits = _hits(text, NEW_ENTRANT_REJECT_TERMS)
    return {
        **_candidate_base(doc, sentence),
        "strict_hits": strict_hits,
        "direct_transmission_hits": direct_hits,
        "reject_hits": reject_hits,
        "strict_gate_verdict": (
            "strict_rejected_context" if reject_hits else "strict_review_candidate"
        ),
        "strict_gate_reason": (
            f"reject_terms:{','.join(reject_hits)}"
            if reject_hits
            else "external_new_entrant_with_direct_a_share_transmission"
        ),
    }


def _classify_substitute(doc: Mapping[str, Any], sentence: str) -> dict[str, Any] | None:
    text = f"{doc.get('title') or ''} {sentence}"
    strict_hits = _hits(text, SUBSTITUTE_STRICT_TERMS)
    direct_hits = sorted(set(_hits(text, ASHARE_TERMS) + _hits(text, DIRECT_TRANSMISSION_KEYWORDS)))
    if not strict_hits or not direct_hits:
        return None
    reject_hits = _hits(text, SUBSTITUTE_REJECT_TERMS)
    return {
        **_candidate_base(doc, sentence),
        "strict_hits": strict_hits,
        "direct_transmission_hits": direct_hits,
        "reject_hits": reject_hits,
        "strict_gate_verdict": (
            "strict_rejected_context" if reject_hits else "strict_review_candidate"
        ),
        "strict_gate_reason": (
            f"reject_terms:{','.join(reject_hits)}"
            if reject_hits
            else "negative_substitution_risk_with_direct_a_share_transmission"
        ),
    }


def _required_next_evidence(dp_id: str) -> list[str]:
    if dp_id == "L0.compete.new_entrant":
        return [
            "external entrant or cross-industry player, not incumbent expansion",
            "same sentence/paragraph direct A-share company, sector, supply-chain, or margin/share pressure transmission",
            "reviewed direction and bounded magnitude",
        ]
    return [
        "negative substitute technology risk, not import-substitution opportunity",
        "direct A-share company, sector, board, supply-chain, or margin/share pressure transmission",
        "at least two clean examples or one high-conviction primary-source example",
    ]


def build_report(
    *,
    backlog_path: Path,
    adjudication_path: Path,
    market_root: Path,
    retained_examples_per_dp: int = 12,
) -> dict[str, Any]:
    started = time.time()
    tasks = _event_tasks(_load_json(backlog_path))
    adjudication_rows = _adjudication_rows(_load_json(adjudication_path))
    candidates_by_dp: dict[str, list[dict[str, Any]]] = {dp_id: [] for dp_id in EVENT_DP_IDS}
    seen_candidate_keys: set[tuple[str, str, str, str]] = set()
    read_error_count = 0
    scanned = 0
    for path in _iter_html_files(market_root):
        try:
            doc = _doc_record(path, market_root)
        except OSError:
            read_error_count += 1
            continue
        scanned += 1
        text = f"{doc.get('title') or ''} {doc.get('text') or ''}"
        for sentence in _sentence_candidates(text):
            new_entrant = _classify_new_entrant(doc, sentence)
            if new_entrant is not None:
                key = (
                    "L0.compete.new_entrant",
                    str(new_entrant.get("market_relative_path") or ""),
                    str(new_entrant.get("strict_gate_verdict") or ""),
                )
                if key not in seen_candidate_keys:
                    seen_candidate_keys.add(key)
                    candidates_by_dp["L0.compete.new_entrant"].append(new_entrant)
            substitute = _classify_substitute(doc, sentence)
            if substitute is not None:
                key = (
                    "L0.tech.substitute_tech",
                    str(substitute.get("market_relative_path") or ""),
                    str(substitute.get("strict_gate_verdict") or ""),
                )
                if key not in seen_candidate_keys:
                    seen_candidate_keys.add(key)
                    candidates_by_dp["L0.tech.substitute_tech"].append(substitute)

    rows: list[dict[str, Any]] = []
    for dp_id in EVENT_DP_IDS:
        candidates = candidates_by_dp[dp_id]
        verdict_counts = Counter(str(candidate["strict_gate_verdict"]) for candidate in candidates)
        review_candidates = [
            candidate
            for candidate in candidates
            if candidate["strict_gate_verdict"] == "strict_review_candidate"
        ]
        row = {
            "dp_id": dp_id,
            "score_target": (tasks.get(dp_id) or {}).get("score_target")
            or (adjudication_rows.get(dp_id) or {}).get("score_target"),
            "strict_candidate_count": len(candidates),
            "strict_review_candidate_count": len(review_candidates),
            "strict_rejected_count": len(candidates) - len(review_candidates),
            "strict_gate_status": (
                "strict_review_candidates_found"
                if review_candidates
                else "no_strict_source_candidate"
            ),
            "prior_adjudication_status": (adjudication_rows.get(dp_id) or {}).get(
                "adjudication_status"
            ),
            "prior_accepted_candidate_count": (adjudication_rows.get(dp_id) or {}).get(
                "accepted_candidate_count"
            ),
            "required_next_evidence": _required_next_evidence(dp_id),
            "candidate_examples": candidates[:retained_examples_per_dp],
            "data_status": "Unknown",
            "classifier_ready": False,
            "known_draft_sufficient": False,
            "approval_ready": False,
            "safe_to_upsert_without_review": False,
            "runtime_write_allowed": False,
            "production_write_allowed": False,
            "strict_gate_contract_valid": True,
            "strict_gate_validation_errors": [],
            "strict_gate_verdict_counts": dict(sorted(verdict_counts.items())),
        }
        rows.append(row)
    rows.sort(key=lambda row: row["dp_id"])
    status_counts = Counter(str(row["strict_gate_status"]) for row in rows)
    return {
        "generated_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "elapsed_s": round(time.time() - started, 3),
        "inputs": {
            "backlog_path": _portable_path(backlog_path),
            "adjudication_path": _portable_path(adjudication_path),
            "market_root": _portable_path(market_root),
        },
        "summary": {
            "event_strict_gate_row_count": len(rows),
            "market_html_files_scanned": scanned,
            "market_html_read_error_count": read_error_count,
            "strict_candidate_count": sum(int(row["strict_candidate_count"]) for row in rows),
            "strict_review_candidate_count": sum(
                int(row["strict_review_candidate_count"]) for row in rows
            ),
            "strict_rejected_count": sum(int(row["strict_rejected_count"]) for row in rows),
            "rows_with_strict_review_candidates_count": status_counts.get(
                "strict_review_candidates_found", 0
            ),
            "rows_without_strict_source_candidate_count": status_counts.get(
                "no_strict_source_candidate", 0
            ),
            "classifier_ready_count": 0,
            "known_draft_sufficient_count": 0,
            "approval_ready_count": 0,
            "strict_gate_contract_valid_count": sum(
                1 for row in rows if row["strict_gate_contract_valid"]
            ),
            "strict_gate_contract_invalid_count": sum(
                1 for row in rows if not row["strict_gate_contract_valid"]
            ),
            "runtime_write_allowed_count": 0,
            "production_write_allowed_count": 0,
            "strict_gate_status_counts": dict(sorted(status_counts.items())),
            "score_mutation": "none; this audit is read-only and does not alter realtime_current",
        },
        "rows": rows,
    }


def render_markdown(report: Mapping[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# A-share event Unknown strict source gate",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- Rows: `{summary['event_strict_gate_row_count']}`",
        f"- Market HTML files scanned: `{summary['market_html_files_scanned']}`",
        f"- Strict candidates: `{summary['strict_candidate_count']}`",
        f"- Strict review candidates: `{summary['strict_review_candidate_count']}`",
        f"- Rows with strict review candidates: `{summary['rows_with_strict_review_candidates_count']}`",
        f"- Rows without strict source candidate: `{summary['rows_without_strict_source_candidate_count']}`",
        f"- Classifier-ready rows: `{summary['classifier_ready_count']}`",
        f"- Known-draft sufficient: `{summary['known_draft_sufficient_count']}`",
        f"- Production writes allowed: `{summary['production_write_allowed_count']}`",
        f"- Score mutation: `{summary['score_mutation']}`",
        "",
        "## Rows",
        "",
        "| dp_id | status | strict candidates | strict review candidates | required next evidence |",
        "|---|---|---:|---:|---|",
    ]
    for row in report["rows"]:
        lines.append(
            "| {dp_id} | {status} | {candidates} | {review} | {required} |".format(
                dp_id=row["dp_id"],
                status=row["strict_gate_status"],
                candidates=row["strict_candidate_count"],
                review=row["strict_review_candidate_count"],
                required=", ".join(row.get("required_next_evidence") or []),
            )
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- Strict source candidates are still classifier inputs, not Known values.",
            "- A row remains Unknown unless strict source evidence is reviewed, direction/magnitude are bounded, and approval records are created.",
            "- This audit creates no runtime writes and does not mutate final scores.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backlog-path", type=Path, default=DEFAULT_BACKLOG_PATH)
    parser.add_argument("--adjudication-path", type=Path, default=DEFAULT_ADJUDICATION_PATH)
    parser.add_argument("--market-root", type=Path, default=DEFAULT_MARKET_ROOT)
    parser.add_argument("--json-output", type=Path, default=DEFAULT_JSON_OUTPUT)
    parser.add_argument("--md-output", type=Path, default=DEFAULT_MD_OUTPUT)
    args = parser.parse_args()

    report = build_report(
        backlog_path=args.backlog_path,
        adjudication_path=args.adjudication_path,
        market_root=args.market_root,
    )
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    args.md_output.write_text(render_markdown(report), encoding="utf-8")


if __name__ == "__main__":
    main()
