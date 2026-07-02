#!/usr/bin/env python3
"""Screen local market documents for A-share Unknown acquisition candidates.

This read-only audit executes the DOCKCASE market-document portion of the
Unknown acquisition backlog. It keeps review candidates and rejected examples
separate so noisy local evidence cannot become a score-affecting value.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Mapping

_BOOTSTRAP_ROOT = Path(__file__).resolve().parent.parent
if str(_BOOTSTRAP_ROOT) not in sys.path:
    sys.path.insert(0, str(_BOOTSTRAP_ROOT))

from scripts.audit_a_share_event_text_market_doc_evidence import (  # noqa: E402
    DIRECT_TRANSMISSION_KEYWORDS,
    TARGET_KEYWORDS,
    _doc_record,
    _hits,
    _iter_html_files,
    _sentences_with_hits,
)
from scripts.audit_a_share_unknown_acquisition_backlog import (  # noqa: E402
    ROOT,
    _load_json,
    _portable_path,
)


DEFAULT_BACKLOG_PATH = (
    ROOT / "docs/audit/a_share_unknown_acquisition_backlog_2026-06-19.json"
)
DEFAULT_MARKET_ROOT = Path("/Volumes/dockcase2tb/market_data")
DEFAULT_JSON_OUTPUT = (
    ROOT / "docs/audit/a_share_unknown_market_doc_acquisition_candidates_2026-06-19.json"
)
DEFAULT_MD_OUTPUT = (
    ROOT / "docs/audit/a_share_unknown_market_doc_acquisition_candidates_2026-06-19.md"
)

EVENT_DP_IDS = {"L0.compete.new_entrant", "L0.tech.substitute_tech"}
AS_DIRECT_TERMS = (
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
NEW_ENTRANT_REJECT_TERMS = (
    "打新",
    "IPO",
    "网下配售",
    "基石投资",
    "科技创新公司债券",
    "选股",
    "股市",
    "市盈率",
)
NEW_ENTRANT_REVIEW_TERMS = (
    "合资",
    "成立",
    "新公司",
    "新厂商",
    "跨界",
    "入局",
    "建设",
    "项目",
    "投产",
    "扩产",
)
SUBSTITUTE_RISK_TERMS = (
    "冲击",
    "威胁",
    "风险",
    "担忧",
    "被替代",
    "取代",
    "颠覆",
    "淘汰",
    "挤压",
    "压力",
    "竞争加剧",
    "份额流失",
    "不利",
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
    "关税",
    "特朗普",
    "斯洛伐克",
    "管道",
    "石油",
    "最高法院",
    "违法征收",
)
BOILERPLATE_REJECT_TERMS = (
    "A股公告速递",
    "互动平台精选",
    "打开APP",
    "查看原文",
)


def _event_tasks(backlog: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for row in backlog.get("rows") or []:
        if not isinstance(row, Mapping):
            continue
        if row.get("dp_id") not in EVENT_DP_IDS:
            continue
        if row.get("acquisition_track") != "dockcase_market_doc_deep_search":
            continue
        rows.append(dict(row))
    rows.sort(key=lambda row: str(row.get("dp_id") or ""))
    return rows


def _window_candidates(
    *,
    text: str,
    target_keywords: Iterable[str],
    window_before: int = 180,
    window_after: int = 300,
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for keyword in target_keywords:
        pos = text.find(keyword)
        while pos >= 0:
            excerpt = text[max(0, pos - window_before) : pos + window_after]
            direct_hits = _hits(excerpt, DIRECT_TRANSMISSION_KEYWORDS)
            if direct_hits:
                candidates.append(
                    {
                        "target_hit": keyword,
                        "direct_transmission_hits": direct_hits,
                        "excerpt": excerpt[:420],
                    }
                )
            pos = text.find(keyword, pos + 1)
    return candidates


def _doc_base(doc: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "path": doc.get("path"),
        "market_relative_path": doc.get("market_relative_path"),
        "title": doc.get("title"),
    }


def _new_entrant_candidate(
    doc: Mapping[str, Any],
    window_candidate: Mapping[str, Any],
) -> dict[str, Any]:
    text = f"{doc.get('title') or ''} {window_candidate.get('excerpt') or ''}"
    reject_hits = _hits(text, NEW_ENTRANT_REJECT_TERMS)
    review_hits = _hits(text, NEW_ENTRANT_REVIEW_TERMS)
    if reject_hits:
        classification = "rejected_context"
        reason = f"reject_terms:{','.join(reject_hits)}"
    elif review_hits:
        classification = "review_candidate"
        reason = f"review_terms:{','.join(review_hits)}"
    else:
        classification = "weak_window_candidate"
        reason = "target_and_transmission_are_nearby_but_business_entry_context_is_weak"
    return {
        **_doc_base(doc),
        "classification": classification,
        "reason": reason,
        "target_hits": [window_candidate.get("target_hit")],
        "direct_transmission_hits": window_candidate.get("direct_transmission_hits") or [],
        "excerpt": window_candidate.get("excerpt"),
    }


def _substitute_candidate(
    doc: Mapping[str, Any],
    same_sentence_hit: Mapping[str, Any],
) -> dict[str, Any]:
    sentence = str(same_sentence_hit.get("excerpt") or "")
    context = f"{doc.get('title') or ''} {sentence}"
    reject_hits = _hits(context, SUBSTITUTE_REJECT_TERMS)
    boilerplate_hits = _hits(sentence, BOILERPLATE_REJECT_TERMS)
    risk_hits = _hits(sentence, SUBSTITUTE_RISK_TERMS)
    as_hits = _hits(sentence, AS_DIRECT_TERMS)
    if reject_hits:
        classification = "rejected_false_positive"
        reason = f"reject_terms:{','.join(reject_hits)}"
    elif boilerplate_hits and len(sentence) < 160:
        classification = "rejected_boilerplate_or_tag"
        reason = f"boilerplate_terms:{','.join(boilerplate_hits)}"
    elif risk_hits and as_hits:
        classification = "clean_risk_review_candidate"
        reason = f"risk_terms:{','.join(risk_hits)}"
    else:
        classification = "weak_same_sentence_candidate"
        reason = "same_sentence_target_and_transmission_without_clean_substitution_risk"
    return {
        **_doc_base(doc),
        "classification": classification,
        "reason": reason,
        "target_hits": same_sentence_hit.get("target_hits") or [],
        "direct_transmission_hits": same_sentence_hit.get("direct_transmission_hits") or [],
        "excerpt": sentence,
    }


def _append_limited(target: list[dict[str, Any]], item: dict[str, Any], limit: int) -> None:
    if len(target) < limit:
        target.append(item)


def build_report(
    *,
    backlog_path: Path,
    market_root: Path,
    retained_examples_per_dp: int = 8,
) -> dict[str, Any]:
    started = time.time()
    backlog = _load_json(backlog_path)
    event_tasks = _event_tasks(backlog)
    by_dp: dict[str, dict[str, Any]] = {
        str(task["dp_id"]): {
            "dp_id": task["dp_id"],
            "task_id": task.get("task_id"),
            "score_target": task.get("score_target"),
            "acquisition_track": task.get("acquisition_track"),
            "source_priority": task.get("source_priority"),
            "target_keywords": list(TARGET_KEYWORDS.get(str(task["dp_id"]), ())),
            "candidate_document_count": 0,
            "review_candidate_count": 0,
            "weak_candidate_count": 0,
            "rejected_candidate_count": 0,
            "candidate_examples": [],
            "rejected_examples": [],
            "candidate_status": "not_scanned",
            "known_draft_sufficient": False,
            "review_required": True,
            "safe_to_upsert_without_review": False,
            "production_write_allowed": False,
        }
        for task in event_tasks
    }

    html_files = list(_iter_html_files(market_root))
    read_error_count = 0
    for path in html_files:
        try:
            doc = _doc_record(path, market_root)
        except Exception:  # noqa: BLE001
            read_error_count += 1
            continue
        text = str(doc.get("text") or "")
        if not text:
            continue

        new_row = by_dp.get("L0.compete.new_entrant")
        if new_row:
            doc_candidates = [
                _new_entrant_candidate(doc, candidate)
                for candidate in _window_candidates(
                    text=text,
                    target_keywords=TARGET_KEYWORDS["L0.compete.new_entrant"],
                )
            ]
            if doc_candidates:
                new_row["candidate_document_count"] += 1
            for candidate in doc_candidates:
                if candidate["classification"] == "review_candidate":
                    new_row["review_candidate_count"] += 1
                    _append_limited(
                        new_row["candidate_examples"],
                        candidate,
                        retained_examples_per_dp,
                    )
                elif candidate["classification"].startswith("rejected"):
                    new_row["rejected_candidate_count"] += 1
                    _append_limited(
                        new_row["rejected_examples"],
                        candidate,
                        retained_examples_per_dp,
                    )
                else:
                    new_row["weak_candidate_count"] += 1
                    _append_limited(
                        new_row["candidate_examples"],
                        candidate,
                        retained_examples_per_dp,
                    )

        sub_row = by_dp.get("L0.tech.substitute_tech")
        if sub_row:
            sentence_hits = _sentences_with_hits(
                text,
                TARGET_KEYWORDS["L0.tech.substitute_tech"],
            )
            if sentence_hits:
                sub_row["candidate_document_count"] += 1
            for hit in sentence_hits:
                candidate = _substitute_candidate(doc, hit)
                if candidate["classification"] == "clean_risk_review_candidate":
                    sub_row["review_candidate_count"] += 1
                    _append_limited(
                        sub_row["candidate_examples"],
                        candidate,
                        retained_examples_per_dp,
                    )
                elif candidate["classification"].startswith("rejected"):
                    sub_row["rejected_candidate_count"] += 1
                    _append_limited(
                        sub_row["rejected_examples"],
                        candidate,
                        retained_examples_per_dp,
                    )
                else:
                    sub_row["weak_candidate_count"] += 1
                    _append_limited(
                        sub_row["candidate_examples"],
                        candidate,
                        retained_examples_per_dp,
                    )

    for row in by_dp.values():
        if row["dp_id"] == "L0.tech.substitute_tech":
            if row["review_candidate_count"] >= 2:
                row["candidate_status"] = "clean_risk_review_candidates_found"
            elif row["review_candidate_count"] > 0:
                row["candidate_status"] = "insufficient_clean_risk_review_candidates"
            else:
                row["candidate_status"] = "external_clean_risk_source_required"
        elif row["dp_id"] == "L0.compete.new_entrant":
            if row["review_candidate_count"] > 0:
                row["candidate_status"] = "local_window_review_candidates_found"
            else:
                row["candidate_status"] = "external_direct_entry_source_required"

    rows = sorted(by_dp.values(), key=lambda row: str(row["dp_id"]))
    status_counts = Counter(str(row["candidate_status"]) for row in rows)
    review_candidate_rows = sum(1 for row in rows if row["review_candidate_count"] > 0)
    known_draft_sufficient_rows = 0
    return {
        "generated_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "elapsed_s": round(time.time() - started, 3),
        "inputs": {
            "backlog_path": _portable_path(backlog_path),
            "market_root": str(market_root),
        },
        "summary": {
            "market_doc_acquisition_task_count": len(rows),
            "market_html_files_scanned": len(html_files),
            "market_html_read_error_count": read_error_count,
            "rows_with_review_candidates_count": review_candidate_rows,
            "new_entrant_window_candidate_count": int(
                by_dp.get("L0.compete.new_entrant", {}).get("candidate_document_count")
                or 0
            ),
            "new_entrant_review_candidate_count": int(
                by_dp.get("L0.compete.new_entrant", {}).get("review_candidate_count")
                or 0
            ),
            "substitute_same_sentence_candidate_count": int(
                by_dp.get("L0.tech.substitute_tech", {}).get("candidate_document_count")
                or 0
            ),
            "substitute_clean_risk_review_candidate_count": int(
                by_dp.get("L0.tech.substitute_tech", {}).get("review_candidate_count")
                or 0
            ),
            "weak_candidate_count": sum(row["weak_candidate_count"] for row in rows),
            "rejected_candidate_count": sum(
                row["rejected_candidate_count"] for row in rows
            ),
            "known_draft_sufficient_count": known_draft_sufficient_rows,
            "review_required_count": len(rows),
            "safe_to_upsert_without_review_count": 0,
            "production_write_allowed_count": 0,
            "candidate_status_counts": dict(sorted(status_counts.items())),
            "score_mutation": "none; this audit is read-only and does not alter realtime_current",
        },
        "rows": rows,
    }


def render_markdown(report: Mapping[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# A-share Unknown market-doc acquisition candidates",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- Market-doc acquisition tasks: `{summary['market_doc_acquisition_task_count']}`",
        f"- Market HTML files scanned: `{summary['market_html_files_scanned']}`",
        f"- Market HTML read errors: `{summary['market_html_read_error_count']}`",
        f"- Rows with review candidates: `{summary['rows_with_review_candidates_count']}`",
        f"- New-entrant window candidate documents: `{summary['new_entrant_window_candidate_count']}`",
        f"- New-entrant review candidates: `{summary['new_entrant_review_candidate_count']}`",
        f"- Substitute same-sentence candidate documents: `{summary['substitute_same_sentence_candidate_count']}`",
        f"- Substitute clean-risk review candidates: `{summary['substitute_clean_risk_review_candidate_count']}`",
        f"- Weak candidates: `{summary['weak_candidate_count']}`",
        f"- Rejected candidates: `{summary['rejected_candidate_count']}`",
        f"- Known-draft sufficient rows: `{summary['known_draft_sufficient_count']}`",
        f"- Production writes allowed: `{summary['production_write_allowed_count']}`",
        f"- Score mutation: `{summary['score_mutation']}`",
        "",
        "## Rows",
        "",
        "| dp_id | status | review candidates | weak candidates | rejected candidates | production write |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for row in report["rows"]:
        lines.append(
            "| "
            f"`{row['dp_id']}` | "
            f"`{row['candidate_status']}` | "
            f"{row['review_candidate_count']} | "
            f"{row['weak_candidate_count']} | "
            f"{row['rejected_candidate_count']} | "
            f"{'yes' if row['production_write_allowed'] else 'no'} |"
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- These are acquisition candidates, not scoreable Known values.",
            "- Rejected examples remain in the report to document false-positive classes.",
            "- Runtime and production writes remain disabled.",
            "",
        ]
    )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backlog-path", type=Path, default=DEFAULT_BACKLOG_PATH)
    parser.add_argument("--market-root", type=Path, default=DEFAULT_MARKET_ROOT)
    parser.add_argument("--retained-examples-per-dp", type=int, default=8)
    parser.add_argument("--json-output", type=Path, default=DEFAULT_JSON_OUTPUT)
    parser.add_argument("--md-output", type=Path, default=DEFAULT_MD_OUTPUT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_report(
        backlog_path=args.backlog_path,
        market_root=args.market_root,
        retained_examples_per_dp=args.retained_examples_per_dp,
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
