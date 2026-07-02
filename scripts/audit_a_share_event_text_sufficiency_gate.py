#!/usr/bin/env python3
"""Gate A-share event-text preclassification by evidence sufficiency.

This audit is read-only. It separates broad market transmission hints such as
China A50 futures from target-specific event evidence, and keeps title-level
event-text rows out of Known review packets unless the same headline carries
both target evidence and a usable A-share transmission hint.
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


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PRECLASSIFICATION_PATH = (
    ROOT / "docs/audit/a_share_event_text_preclassification_screen_2026-06-19.json"
)
DEFAULT_JSON_OUTPUT = ROOT / "docs/audit/a_share_event_text_sufficiency_gate_2026-06-19.json"
DEFAULT_MD_OUTPUT = ROOT / "docs/audit/a_share_event_text_sufficiency_gate_2026-06-19.md"

BROAD_MARKET_TRANSMISSION_KEYWORDS = {"A50", "中国A50", "期货"}


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


def _headline_kind(headline: Mapping[str, Any]) -> dict[str, Any]:
    target_hits = [
        str(item)
        for item in headline.get("target_keyword_hits") or []
        if str(item)
    ]
    transmission_hits = [
        str(item)
        for item in headline.get("a_share_transmission_keyword_hits") or []
        if str(item)
    ]
    broad_hits = [
        keyword
        for keyword in transmission_hits
        if keyword in BROAD_MARKET_TRANSMISSION_KEYWORDS
    ]
    direct_hits = [
        keyword
        for keyword in transmission_hits
        if keyword not in BROAD_MARKET_TRANSMISSION_KEYWORDS
    ]
    return {
        "title": headline.get("title"),
        "time": headline.get("time"),
        "url": headline.get("url"),
        "source": headline.get("source"),
        "dependency_dp_id": headline.get("dependency_dp_id"),
        "target_keyword_hits": target_hits,
        "a_share_transmission_keyword_hits": transmission_hits,
        "broad_market_transmission_hits": broad_hits,
        "direct_transmission_hits": direct_hits,
        "has_target_hit": bool(target_hits),
        "has_direct_transmission_hit": bool(direct_hits),
        "has_broad_market_transmission_hit": bool(broad_hits),
        "same_headline_target_and_direct_transmission": bool(target_hits and direct_hits),
        "same_headline_target_and_any_transmission": bool(target_hits and transmission_hits),
    }


def _sufficiency_status(
    *,
    target_headline_count: int,
    direct_same_headline_count: int,
    any_same_headline_count: int,
    direct_transmission_packet: bool,
    broad_market_only_packet: bool,
    full_article_text_available: bool,
) -> str:
    if not target_headline_count:
        return "insufficient_no_target_event_evidence"
    if direct_same_headline_count:
        if full_article_text_available:
            return "candidate_full_text_review_required"
        return "candidate_same_headline_direct_transmission_needs_full_text"
    if any_same_headline_count:
        return "insufficient_same_headline_broad_market_only"
    if direct_transmission_packet:
        return "insufficient_separate_headlines_no_direct_link"
    if broad_market_only_packet:
        return "insufficient_target_hit_with_broad_market_only_transmission"
    return "insufficient_target_hit_missing_a_share_transmission"


def _gate_row(row: Mapping[str, Any]) -> dict[str, Any]:
    headline_assessments = [
        _headline_kind(headline)
        for headline in row.get("matched_headlines") or []
        if isinstance(headline, Mapping)
    ]
    target_headline_count = sum(1 for item in headline_assessments if item["has_target_hit"])
    direct_same_headline_count = sum(
        1
        for item in headline_assessments
        if item["same_headline_target_and_direct_transmission"]
    )
    any_same_headline_count = sum(
        1
        for item in headline_assessments
        if item["same_headline_target_and_any_transmission"]
    )
    direct_transmission_packet = any(
        item["has_direct_transmission_hit"] for item in headline_assessments
    )
    broad_market_packet = any(
        item["has_broad_market_transmission_hit"] for item in headline_assessments
    )
    broad_market_only_packet = broad_market_packet and not direct_transmission_packet
    status = _sufficiency_status(
        target_headline_count=target_headline_count,
        direct_same_headline_count=direct_same_headline_count,
        any_same_headline_count=any_same_headline_count,
        direct_transmission_packet=direct_transmission_packet,
        broad_market_only_packet=broad_market_only_packet,
        full_article_text_available=bool(row.get("full_article_text_available")),
    )
    title_sufficient = status in {
        "candidate_full_text_review_required",
        "candidate_same_headline_direct_transmission_needs_full_text",
    }
    return {
        "dp_id": row.get("dp_id"),
        "score_target": row.get("score_target"),
        "preclassification_screening_status": row.get("screening_status"),
        "source_dependencies": row.get("source_dependencies") or [],
        "headline_input_count": int(row.get("headline_input_count") or 0),
        "unique_headline_count": int(row.get("unique_headline_count") or 0),
        "full_article_text_available": bool(row.get("full_article_text_available")),
        "title_level_only": bool(row.get("title_level_only")),
        "target_headline_count": target_headline_count,
        "same_headline_target_and_direct_transmission_count": direct_same_headline_count,
        "same_headline_target_and_any_transmission_count": any_same_headline_count,
        "direct_transmission_packet": direct_transmission_packet,
        "broad_market_transmission_packet": broad_market_packet,
        "broad_market_only_transmission_packet": broad_market_only_packet,
        "headline_assessments": headline_assessments,
        "sufficiency_status": status,
        "title_signal_sufficient_for_classifier": title_sufficient,
        "known_candidate_allowed": False,
        "review_status": "review_required",
        "safe_to_upsert_without_review": False,
        "runtime_write_allowed": False,
        "production_write_allowed": False,
        "gate_reason": (
            "title-level evidence must directly connect target event evidence "
            "to A-share, industry, entity, supply-chain, trade, FX, or policy "
            "transmission before a classifier can propose a Known review packet"
        ),
    }


def build_report(*, preclassification_path: Path) -> dict[str, Any]:
    started = time.time()
    preclassification = _load_json(preclassification_path)
    rows = [
        _gate_row(row)
        for row in preclassification.get("rows") or []
        if isinstance(row, Mapping)
    ]
    rows.sort(key=lambda item: str(item.get("dp_id") or ""))
    status_counts = Counter(str(row.get("sufficiency_status") or "") for row in rows)
    return {
        "generated_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "elapsed_s": round(time.time() - started, 3),
        "inputs": {
            "preclassification_path": _portable_path(preclassification_path),
        },
        "summary": {
            "sufficiency_packet_count": len(rows),
            "title_level_only_count": sum(1 for row in rows if row.get("title_level_only")),
            "target_headline_packet_count": sum(
                1 for row in rows if int(row.get("target_headline_count") or 0) > 0
            ),
            "broad_market_only_transmission_packet_count": sum(
                1 for row in rows if row.get("broad_market_only_transmission_packet")
            ),
            "same_headline_target_and_any_transmission_packet_count": sum(
                1
                for row in rows
                if int(row.get("same_headline_target_and_any_transmission_count") or 0) > 0
            ),
            "same_headline_target_and_direct_transmission_packet_count": sum(
                1
                for row in rows
                if int(row.get("same_headline_target_and_direct_transmission_count") or 0) > 0
            ),
            "title_signal_sufficient_for_classifier_count": sum(
                1 for row in rows if row.get("title_signal_sufficient_for_classifier")
            ),
            "known_candidate_allowed_count": 0,
            "review_required_count": len(rows),
            "safe_to_upsert_without_review_count": 0,
            "runtime_write_allowed_count": 0,
            "production_write_allowed_count": 0,
            "sufficiency_status_counts": dict(sorted(status_counts.items())),
            "score_mutation": "none; this audit is read-only and does not alter realtime_current",
        },
        "rows": rows,
    }


def render_markdown(report: Mapping[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# A-share event-text sufficiency gate",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- Sufficiency packets: `{summary['sufficiency_packet_count']}`",
        f"- Target-headline packets: `{summary['target_headline_packet_count']}`",
        f"- Broad-market-only transmission packets: `{summary['broad_market_only_transmission_packet_count']}`",
        f"- Same-headline target + any transmission packets: `{summary['same_headline_target_and_any_transmission_packet_count']}`",
        f"- Same-headline target + direct transmission packets: `{summary['same_headline_target_and_direct_transmission_packet_count']}`",
        f"- Title-signal sufficient for classifier: `{summary['title_signal_sufficient_for_classifier_count']}`",
        f"- Known candidates allowed: `{summary['known_candidate_allowed_count']}`",
        f"- Production writes allowed: `{summary['production_write_allowed_count']}`",
        f"- Score mutation: `{summary['score_mutation']}`",
        "",
        "## Rows",
        "",
        "| dp_id | target | sufficiency status | target headlines | same headline direct | broad-market only | classifier-ready title signal |",
        "|---|---|---|---:|---:|---:|---:|",
    ]
    for row in report["rows"]:
        lines.append(
            "| "
            f"`{row['dp_id']}` | "
            f"`{row.get('score_target', '-')}` | "
            f"`{row.get('sufficiency_status', '-')}` | "
            f"{row.get('target_headline_count', 0)} | "
            f"{row.get('same_headline_target_and_direct_transmission_count', 0)} | "
            f"{'yes' if row.get('broad_market_only_transmission_packet') else 'no'} | "
            f"{'yes' if row.get('title_signal_sufficient_for_classifier') else 'no'} |"
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- A broad China A50/futures headline is market context, not target-specific transmission.",
            "- Separate target and market headlines inside one packet do not establish a direct A-share event path.",
            "- All rows remain blocked from Known candidate generation and runtime writes until stronger evidence exists.",
            "",
        ]
    )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--preclassification-path",
        type=Path,
        default=DEFAULT_PRECLASSIFICATION_PATH,
    )
    parser.add_argument("--json-output", type=Path, default=DEFAULT_JSON_OUTPUT)
    parser.add_argument("--md-output", type=Path, default=DEFAULT_MD_OUTPUT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_report(preclassification_path=args.preclassification_path)
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    args.md_output.write_text(render_markdown(report), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
