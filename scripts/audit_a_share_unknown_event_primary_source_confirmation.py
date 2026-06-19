#!/usr/bin/env python3
"""Check whether low-confidence event leads have local high-quality confirmation.

The previous strict-review audit leaves two community/forum leads requiring
primary-source confirmation. This audit scans the local DOCKCASE market-document
corpus for non-community confirmation candidates. It does not use the results to
create Known values; it only records whether a local high-quality source is
available or whether the row still needs external/primary evidence.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any, Mapping, Sequence

_BOOTSTRAP_ROOT = Path(__file__).resolve().parent.parent
if str(_BOOTSTRAP_ROOT) not in sys.path:
    sys.path.insert(0, str(_BOOTSTRAP_ROOT))

from scripts.audit_a_share_event_text_market_doc_evidence import (  # noqa: E402
    _doc_record,
    _hits,
    _iter_html_files,
)
from scripts.audit_a_share_unknown_acquisition_backlog import (  # noqa: E402
    ROOT,
    _load_json,
    _portable_path,
)


DEFAULT_STRICT_REVIEW_PATH = (
    ROOT / "docs/audit/a_share_unknown_event_strict_review_packets_2026-06-19.json"
)
DEFAULT_MARKET_ROOT = Path("/Volumes/dockcase2tb/market_data")
DEFAULT_JSON_OUTPUT = (
    ROOT / "docs/audit/a_share_unknown_event_primary_source_confirmation_2026-06-19.json"
)
DEFAULT_MD_OUTPUT = (
    ROOT / "docs/audit/a_share_unknown_event_primary_source_confirmation_2026-06-19.md"
)


LOW_CONFIDENCE_MARKERS = ("eastmoney_guba", "股吧", "财富号")
SOURCE_QUALITY_BY_PATH = (
    ("cls_flash", "secondary_newswire"),
    ("ths_news", "secondary_news"),
)

RULES: dict[str, dict[str, tuple[str, ...]]] = {
    "L0.compete.new_entrant": {
        "topic_terms": (
            "平头哥",
            "阿里平头哥",
            "真武",
            "阿里云AI算力",
            "算力卡",
        ),
        "subject_terms": (
            "寒武纪",
            "688256",
            "AI芯片",
            "国产AI芯片",
            "A股",
            "产业链",
        ),
        "event_terms": (
            "竞争对手",
            "竞争",
            "崛起",
            "抢占",
            "进入",
            "份额",
            "订单",
            "挤压",
        ),
    },
    "L0.tech.substitute_tech": {
        "topic_terms": (
            "阿里倚天",
            "自研服务器",
            "客户自研",
            "AI技术迭代",
            "产品同质化",
            "价格战",
        ),
        "subject_terms": (
            "浪潮信息",
            "000977",
            "AI服务器",
            "服务器",
            "产业链",
        ),
        "event_terms": (
            "挤压利润",
            "利润空间窄",
            "削弱现有能力",
            "份额流失",
            "替代",
            "取代",
            "护城河",
        ),
    },
}


def _source_quality(doc: Mapping[str, Any]) -> str:
    text = f"{doc.get('market_relative_path') or ''} {doc.get('title') or ''}"
    if any(marker in text for marker in LOW_CONFIDENCE_MARKERS):
        return "excluded_low_confidence_community_source"
    for path_marker, quality in SOURCE_QUALITY_BY_PATH:
        if path_marker in text:
            return quality
    return "unreviewed_source"


def _sentence_windows(text: str) -> list[str]:
    windows: list[str] = []
    normalized = text.replace("！", "。").replace("？", "。").replace("\n", "。")
    for raw in normalized.split("。"):
        window = raw.strip()
        if window:
            windows.append(window[:520])
    return windows


def _match_window(dp_id: str, doc: Mapping[str, Any], window: str) -> dict[str, Any] | None:
    quality = _source_quality(doc)
    if quality == "excluded_low_confidence_community_source":
        return None
    rule = RULES[dp_id]
    text = f"{doc.get('title') or ''} {window}"
    topic_hits = _hits(text, rule["topic_terms"])
    if not topic_hits:
        return None
    subject_hits = _hits(text, rule["subject_terms"])
    event_hits = _hits(text, rule["event_terms"])
    if subject_hits and event_hits:
        status = "local_high_quality_confirmation_candidate"
        reason = "topic_subject_and_event_terms_in_non_community_source"
    else:
        status = "local_supporting_context_only"
        reason = "topic_seen_but_missing_subject_or_event_terms"
    return {
        "path": doc.get("path"),
        "market_relative_path": doc.get("market_relative_path"),
        "title": doc.get("title"),
        "excerpt": window,
        "source_quality": quality,
        "confirmation_status": status,
        "confirmation_reason": reason,
        "topic_hits": topic_hits,
        "subject_hits": subject_hits,
        "event_hits": event_hits,
    }


def _packets_requiring_confirmation(report: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in report.get("rows") or []:
        if not isinstance(row, Mapping):
            continue
        if row.get("strict_candidate_status") != "requires_primary_source_confirmation":
            continue
        dp_id = str(row.get("dp_id") or "")
        if dp_id in RULES:
            rows.append(dict(row))
    return rows


def _dedupe(candidates: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str]] = set()
    deduped: list[dict[str, Any]] = []
    for candidate in candidates:
        key = (
            str(candidate.get("market_relative_path") or ""),
            str(candidate.get("confirmation_status") or ""),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(dict(candidate))
    return deduped


def _row_status(confirmation_count: int, supporting_count: int) -> str:
    if confirmation_count > 0:
        return "local_high_quality_confirmation_candidates_found"
    if supporting_count > 0:
        return "local_supporting_context_only"
    return "no_local_high_quality_confirmation_candidate"


def build_report(
    *,
    strict_review_path: Path,
    market_root: Path,
    retained_examples_per_packet: int = 8,
) -> dict[str, Any]:
    started = time.time()
    packets = _packets_requiring_confirmation(_load_json(strict_review_path))
    by_dp: dict[str, list[dict[str, Any]]] = {str(packet["dp_id"]): [] for packet in packets}
    scanned = 0
    read_errors = 0
    for path in _iter_html_files(market_root):
        try:
            doc = _doc_record(path, market_root)
        except OSError:
            read_errors += 1
            continue
        scanned += 1
        text = f"{doc.get('title') or ''} {doc.get('text') or ''}"
        for dp_id in by_dp:
            for window in _sentence_windows(text):
                candidate = _match_window(dp_id, doc, window)
                if candidate is not None:
                    by_dp[dp_id].append(candidate)
    rows: list[dict[str, Any]] = []
    for packet in packets:
        dp_id = str(packet["dp_id"])
        candidates = _dedupe(by_dp.get(dp_id, []))
        confirmation_candidates = [
            candidate
            for candidate in candidates
            if candidate["confirmation_status"] == "local_high_quality_confirmation_candidate"
        ]
        supporting_context = [
            candidate
            for candidate in candidates
            if candidate["confirmation_status"] == "local_supporting_context_only"
        ]
        status = _row_status(len(confirmation_candidates), len(supporting_context))
        row = {
            "packet_id": packet.get("packet_id"),
            "dp_id": dp_id,
            "score_target": packet.get("score_target"),
            "original_low_confidence_candidate": packet.get("candidate"),
            "local_confirmation_status": status,
            "local_candidate_count": len(candidates),
            "local_high_quality_confirmation_candidate_count": len(
                confirmation_candidates
            ),
            "local_supporting_context_only_count": len(supporting_context),
            "candidate_examples": candidates[:retained_examples_per_packet],
            "required_next_evidence": (
                [
                    "review local high-quality confirmation candidates for source quality, event fit, direct transmission, direction, and magnitude",
                    "create classifier/approval packet only after confirmation review",
                ]
                if confirmation_candidates
                else [
                    "external or primary source confirmation still required",
                    "keep row Unknown until source quality and direct transmission are reviewed",
                ]
            ),
            "data_status": "Unknown",
            "classifier_ready": False,
            "known_draft_sufficient": False,
            "approval_ready": False,
            "safe_to_upsert_without_review": False,
            "runtime_write_allowed": False,
            "production_write_allowed": False,
            "confirmation_contract_valid": True,
            "confirmation_validation_errors": [],
        }
        rows.append(row)
    status_counts = Counter(str(row["local_confirmation_status"]) for row in rows)
    return {
        "generated_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "elapsed_s": round(time.time() - started, 3),
        "inputs": {
            "strict_review_path": _portable_path(strict_review_path),
            "market_root": _portable_path(market_root),
        },
        "summary": {
            "primary_confirmation_packet_count": len(rows),
            "market_html_files_scanned": scanned,
            "market_html_read_error_count": read_errors,
            "local_candidate_count": sum(int(row["local_candidate_count"]) for row in rows),
            "local_high_quality_confirmation_candidate_count": sum(
                int(row["local_high_quality_confirmation_candidate_count"])
                for row in rows
            ),
            "local_supporting_context_only_count": sum(
                int(row["local_supporting_context_only_count"]) for row in rows
            ),
            "rows_with_local_confirmation_candidate_count": status_counts.get(
                "local_high_quality_confirmation_candidates_found", 0
            ),
            "rows_with_supporting_context_only_count": status_counts.get(
                "local_supporting_context_only", 0
            ),
            "rows_without_local_confirmation_candidate_count": status_counts.get(
                "no_local_high_quality_confirmation_candidate", 0
            ),
            "classifier_ready_count": 0,
            "known_draft_sufficient_count": 0,
            "approval_ready_count": 0,
            "confirmation_contract_valid_count": sum(
                1 for row in rows if row["confirmation_contract_valid"]
            ),
            "confirmation_contract_invalid_count": sum(
                1 for row in rows if not row["confirmation_contract_valid"]
            ),
            "runtime_write_allowed_count": 0,
            "production_write_allowed_count": 0,
            "local_confirmation_status_counts": dict(sorted(status_counts.items())),
            "score_mutation": "none; this audit is read-only and does not alter realtime_current",
        },
        "rows": rows,
    }


def render_markdown(report: Mapping[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# A-share event Unknown primary-source confirmation",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- Packets requiring confirmation: `{summary['primary_confirmation_packet_count']}`",
        f"- Market HTML files scanned: `{summary['market_html_files_scanned']}`",
        f"- Read errors: `{summary['market_html_read_error_count']}`",
        f"- Local candidates: `{summary['local_candidate_count']}`",
        f"- Local high-quality confirmation candidates: `{summary['local_high_quality_confirmation_candidate_count']}`",
        f"- Local supporting-context-only candidates: `{summary['local_supporting_context_only_count']}`",
        f"- Rows with local confirmation candidates: `{summary['rows_with_local_confirmation_candidate_count']}`",
        f"- Rows with supporting context only: `{summary['rows_with_supporting_context_only_count']}`",
        f"- Rows without local confirmation candidates: `{summary['rows_without_local_confirmation_candidate_count']}`",
        f"- Classifier-ready rows: `{summary['classifier_ready_count']}`",
        f"- Known-draft sufficient rows: `{summary['known_draft_sufficient_count']}`",
        f"- Approval-ready rows: `{summary['approval_ready_count']}`",
        f"- Production writes allowed: `{summary['production_write_allowed_count']}`",
        f"- Score mutation: `{summary['score_mutation']}`",
        "",
        "## Rows",
        "",
        "| packet | dp_id | status | local candidates | confirmation candidates | supporting only | contract | production write |",
        "|---|---|---|---:|---:|---:|---:|---:|",
    ]
    for row in report["rows"]:
        lines.append(
            "| "
            f"`{row['packet_id']}` | "
            f"`{row['dp_id']}` | "
            f"`{row['local_confirmation_status']}` | "
            f"{row['local_candidate_count']} | "
            f"{row['local_high_quality_confirmation_candidate_count']} | "
            f"{row['local_supporting_context_only_count']} | "
            f"{'yes' if row.get('confirmation_contract_valid') else 'no'} | "
            f"{'yes' if row.get('production_write_allowed') else 'no'} |"
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- Local high-quality confirmation candidates are still review inputs, not Known values.",
            "- Supporting-context-only candidates are insufficient for score conversion.",
            "- Rows without confirmation candidates still require external or primary-source acquisition.",
            "- This audit creates no runtime writes and does not mutate final scores.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--strict-review-path", type=Path, default=DEFAULT_STRICT_REVIEW_PATH)
    parser.add_argument("--market-root", type=Path, default=DEFAULT_MARKET_ROOT)
    parser.add_argument("--json-output", type=Path, default=DEFAULT_JSON_OUTPUT)
    parser.add_argument("--md-output", type=Path, default=DEFAULT_MD_OUTPUT)
    args = parser.parse_args()

    report = build_report(strict_review_path=args.strict_review_path, market_root=args.market_root)
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    args.md_output.write_text(render_markdown(report), encoding="utf-8")


if __name__ == "__main__":
    main()
