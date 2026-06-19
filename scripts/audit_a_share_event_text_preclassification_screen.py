#!/usr/bin/env python3
"""Conservatively pre-screen A-share event-text classification inputs.

This audit is read-only. It applies deterministic keyword screens to the
title-level event-text packets so reviewers can see which rows have only broad
theme hits, which have A-share transmission hints, and why none of them can be
promoted to Known without governed review.
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
DEFAULT_CLASSIFICATION_INPUTS_PATH = (
    ROOT / "docs/audit/a_share_event_text_classification_inputs_2026-06-19.json"
)
DEFAULT_JSON_OUTPUT = (
    ROOT / "docs/audit/a_share_event_text_preclassification_screen_2026-06-19.json"
)
DEFAULT_MD_OUTPUT = (
    ROOT / "docs/audit/a_share_event_text_preclassification_screen_2026-06-19.md"
)


TARGET_KEYWORDS: dict[str, tuple[str, ...]] = {
    "L0.compete.new_entrant": ("新进入", "进入者", "准入", "门槛", "竞争者"),
    "L0.compete.price_war": ("价格战", "降价", "促销", "打折", "价格下调"),
    "L0.compete.share_concentration": ("市占率", "份额", "集中度", "龙头", "并购", "整合"),
    "L0.policy.access_license": ("牌照", "许可", "准入", "审批", "配额", "资质"),
    "L0.policy.regulation": ("监管", "新规", "整改", "禁止", "处罚", "合规", "制裁"),
    "L0.policy.subsidy": ("补贴", "退坡", "扶持", "贴息", "优惠"),
    "L0.policy.tax_trade": ("关税", "税", "出口管制", "贸易限制", "制裁", "汇率", "人民币"),
    "L0.tech.ai_automation": ("AI", "人工智能", "自动化", "机器人", "智能化"),
    "L0.tech.breakthrough": ("突破", "创新", "量产", "商业化", "里程碑", "新技术"),
    "L0.tech.substitute_tech": ("替代", "取代", "颠覆", "新技术"),
    "L8.shock.black_swan": (
        "黑天鹅",
        "枪击",
        "核电站",
        "战争",
        "袭击",
        "霍尔木兹",
        "冲突",
        "受损",
    ),
    "L8.shock.supply_break": (
        "供应中断",
        "停产",
        "断供",
        "物流",
        "航运",
        "霍尔木兹",
        "短缺",
        "封锁",
    ),
}

A_SHARE_TRANSMISSION_KEYWORDS: tuple[str, ...] = (
    "A股",
    "A50",
    "中国A50",
    "沪深",
    "上市公司",
    "行业",
    "板块",
    "产业链",
    "供应链",
    "出口",
    "进口",
    "人民币",
    "期货",
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


def _keyword_hits(text: str, keywords: tuple[str, ...]) -> list[str]:
    folded_text = text.casefold()
    return [keyword for keyword in keywords if keyword.casefold() in folded_text]


def _unique_titles(row: Mapping[str, Any]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    titles: list[dict[str, Any]] = []
    for item in row.get("headline_inputs") or []:
        if not isinstance(item, Mapping):
            continue
        title = str(item.get("title") or "")
        if not title or title in seen:
            continue
        seen.add(title)
        titles.append(dict(item))
    return titles


def _screening_status(target_hits: set[str], transmission_hits: set[str]) -> str:
    if not target_hits:
        return "screened_no_target_keyword_hit"
    if not transmission_hits:
        return "screened_target_keyword_hit_without_a_share_transmission"
    return "screened_target_and_transmission_keyword_hit_requires_review"


def _screen_row(row: Mapping[str, Any]) -> dict[str, Any]:
    dp_id = str(row.get("dp_id") or "")
    target_keywords = TARGET_KEYWORDS.get(dp_id, ())
    matched_headlines: list[dict[str, Any]] = []
    target_hits: set[str] = set()
    transmission_hits: set[str] = set()
    for headline in _unique_titles(row):
        title = str(headline.get("title") or "")
        headline_target_hits = _keyword_hits(title, target_keywords)
        headline_transmission_hits = _keyword_hits(title, A_SHARE_TRANSMISSION_KEYWORDS)
        if not headline_target_hits and not headline_transmission_hits:
            continue
        target_hits.update(headline_target_hits)
        transmission_hits.update(headline_transmission_hits)
        matched_headlines.append(
            {
                "title": title,
                "time": headline.get("time"),
                "url": headline.get("url"),
                "source": headline.get("source"),
                "dependency_dp_id": headline.get("dependency_dp_id"),
                "target_keyword_hits": headline_target_hits,
                "a_share_transmission_keyword_hits": headline_transmission_hits,
            }
        )
    status = _screening_status(target_hits, transmission_hits)
    title_level_only = bool(row.get("title_level_input_ready")) and not bool(
        row.get("full_article_text_available")
    )
    return {
        "dp_id": dp_id,
        "score_target": row.get("score_target"),
        "source_dependencies": row.get("source_dependencies") or [],
        "classification_status": row.get("classification_status"),
        "headline_input_count": int(row.get("headline_input_count") or 0),
        "unique_headline_count": int(row.get("unique_headline_count") or 0),
        "full_article_text_available": bool(row.get("full_article_text_available")),
        "title_level_only": title_level_only,
        "target_keywords": list(target_keywords),
        "matched_target_keywords": sorted(target_hits),
        "matched_a_share_transmission_keywords": sorted(transmission_hits),
        "matched_headlines": matched_headlines,
        "matched_headline_count": len(matched_headlines),
        "screening_status": status,
        "preclassification_decision": {
            "data_status": "Unknown",
            "event_match": "unknown",
            "direction": "unknown",
            "magnitude": None,
            "a_share_transmission": "unknown",
            "direct_known_candidate_allowed": False,
            "reason": (
                "deterministic keyword hits are title-level hints only; a reviewer "
                "or classifier must verify target concept, direction, magnitude, "
                "and A-share transmission before a Known packet can be emitted"
            ),
        },
        "blocked_reason": row.get("blocked_reason"),
        "required_policy": row.get("required_policy"),
        "review_status": "review_required",
        "safe_to_upsert_without_review": False,
        "runtime_write_allowed": False,
        "production_write_allowed": False,
    }


def build_report(*, classification_inputs_path: Path) -> dict[str, Any]:
    started = time.time()
    inputs = _load_json(classification_inputs_path)
    rows = [
        _screen_row(row)
        for row in inputs.get("rows") or []
        if isinstance(row, Mapping)
    ]
    rows.sort(key=lambda item: str(item.get("dp_id") or ""))
    status_counts = Counter(str(row.get("screening_status") or "") for row in rows)
    target_keyword_counts = Counter(
        keyword
        for row in rows
        for keyword in row.get("matched_target_keywords") or []
    )
    transmission_keyword_counts = Counter(
        keyword
        for row in rows
        for keyword in row.get("matched_a_share_transmission_keywords") or []
    )
    return {
        "generated_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "elapsed_s": round(time.time() - started, 3),
        "inputs": {
            "classification_inputs_path": _portable_path(classification_inputs_path),
        },
        "summary": {
            "preclassification_packet_count": len(rows),
            "packets_screened_count": len(rows),
            "title_level_only_count": sum(1 for row in rows if row.get("title_level_only")),
            "target_keyword_hit_packet_count": sum(
                1 for row in rows if row.get("matched_target_keywords")
            ),
            "a_share_transmission_hit_packet_count": sum(
                1 for row in rows if row.get("matched_a_share_transmission_keywords")
            ),
            "target_and_transmission_hit_packet_count": sum(
                1
                for row in rows
                if row.get("matched_target_keywords")
                and row.get("matched_a_share_transmission_keywords")
            ),
            "direct_known_candidate_count": 0,
            "classified_known_count": 0,
            "review_required_count": len(rows),
            "safe_to_upsert_without_review_count": 0,
            "runtime_write_allowed_count": 0,
            "production_write_allowed_count": 0,
            "screening_status_counts": dict(sorted(status_counts.items())),
            "target_keyword_counts": dict(sorted(target_keyword_counts.items())),
            "a_share_transmission_keyword_counts": dict(
                sorted(transmission_keyword_counts.items())
            ),
            "score_mutation": "none; this audit is read-only and does not alter realtime_current",
        },
        "rows": rows,
    }


def render_markdown(report: Mapping[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# A-share event-text preclassification screen",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- Preclassification packets: `{summary['preclassification_packet_count']}`",
        f"- Packets screened: `{summary['packets_screened_count']}`",
        f"- Title-level only packets: `{summary['title_level_only_count']}`",
        f"- Target keyword-hit packets: `{summary['target_keyword_hit_packet_count']}`",
        f"- A-share transmission keyword-hit packets: `{summary['a_share_transmission_hit_packet_count']}`",
        f"- Target + transmission keyword-hit packets: `{summary['target_and_transmission_hit_packet_count']}`",
        f"- Direct Known candidates allowed: `{summary['direct_known_candidate_count']}`",
        f"- Production writes allowed: `{summary['production_write_allowed_count']}`",
        f"- Score mutation: `{summary['score_mutation']}`",
        "",
        "## Rows",
        "",
        "| dp_id | target | screen status | target hits | A-share hits | matched headlines |",
        "|---|---|---|---:|---:|---:|",
    ]
    for row in report["rows"]:
        lines.append(
            "| "
            f"`{row['dp_id']}` | "
            f"`{row.get('score_target', '-')}` | "
            f"`{row.get('screening_status', '-')}` | "
            f"{len(row.get('matched_target_keywords') or [])} | "
            f"{len(row.get('matched_a_share_transmission_keywords') or [])} | "
            f"{row.get('matched_headline_count', 0)} |"
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- This is a deterministic screen, not a classifier.",
            "- Keyword hits are title-level hints and do not prove event concept, direction, magnitude, or A-share transmission.",
            "- All packets remain `Unknown`, `review_required`, and blocked from runtime or production writes.",
            "",
        ]
    )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--classification-inputs-path",
        type=Path,
        default=DEFAULT_CLASSIFICATION_INPUTS_PATH,
    )
    parser.add_argument("--json-output", type=Path, default=DEFAULT_JSON_OUTPUT)
    parser.add_argument("--md-output", type=Path, default=DEFAULT_MD_OUTPUT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_report(classification_inputs_path=args.classification_inputs_path)
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    args.md_output.write_text(render_markdown(report), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
