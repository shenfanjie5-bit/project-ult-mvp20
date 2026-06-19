#!/usr/bin/env python3
"""Scan local market documents for external business-metric Unknown candidates.

This read-only audit executes the market-document portion of the external/text
business-metric acquisition track. It searches local DOCKCASE news HTML for
frequency, penetration, and replacement-demand snippets that may be useful for
human review, while keeping all rows Unknown and write-disabled.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
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
    SENTENCE_SPLIT_RE,
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
DEFAULT_MARKET_ROOT = Path("/Volumes/dockcase2tb/market_data")
DEFAULT_JSON_OUTPUT = (
    ROOT
    / "docs/audit/a_share_unknown_external_business_metric_market_doc_candidates_2026-06-19.json"
)
DEFAULT_MD_OUTPUT = (
    ROOT
    / "docs/audit/a_share_unknown_external_business_metric_market_doc_candidates_2026-06-19.md"
)

BUSINESS_METRIC_DP_IDS = {
    "L0.demand.frequency",
    "L0.demand.penetration",
    "L0.demand.replacement",
}

TARGET_KEYWORDS: dict[str, tuple[str, ...]] = {
    "L0.demand.frequency": (
        "复购",
        "复购率",
        "购买频次",
        "消费频次",
        "使用频率",
        "使用频次",
        "交易频次",
        "订单频次",
        "下单频次",
        "活跃频次",
    ),
    "L0.demand.penetration": (
        "渗透率",
        "普及率",
        "覆盖率",
        "市场份额",
        "市场占有率",
        "市占率",
        "装机率",
    ),
    "L0.demand.replacement": (
        "换新",
        "以旧换新",
        "更新周期",
        "更换周期",
        "替换周期",
        "置换",
        "报废",
        "存量替换",
        "设备更新",
        "更新需求",
        "替换需求",
        "换机",
    ),
}

SUPPORT_KEYWORDS: dict[str, tuple[str, ...]] = {
    "L0.demand.frequency": (
        "用户",
        "客户",
        "订单",
        "交易",
        "消费",
        "活跃",
        "留存",
        "会员",
        "客单",
    ),
    "L0.demand.penetration": (
        "市场",
        "行业",
        "用户",
        "客户",
        "销量",
        "装机",
        "保有量",
        "空间",
        "规模",
    ),
    "L0.demand.replacement": (
        "存量",
        "保有量",
        "周期",
        "寿命",
        "旧",
        "折旧",
        "报废",
        "设备",
        "家电",
        "汽车",
        "手机",
    ),
}

SCOPE_KEYWORDS = (
    "行业",
    "市场",
    "公司",
    "企业",
    "品牌",
    "产品",
    "客户",
    "用户",
    "销量",
    "订单",
    "营收",
    "收入",
)
REJECT_TERMS = (
    "股吧",
    "网友",
    "评论",
    "研报摘要",
    "打开APP",
    "查看原文",
    "广告",
    "免责声明",
)
NUMERIC_RE = re.compile(
    r"\d+(?:\.\d+)?\s*(?:%|％|pct|个?百分点|倍|次|万|亿|个月|月|年)"
)


def _metric_tasks(backlog: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for row in backlog.get("rows") or []:
        if not isinstance(row, Mapping):
            continue
        if row.get("dp_id") not in BUSINESS_METRIC_DP_IDS:
            continue
        if row.get("acquisition_track") != "external_or_text_business_metric":
            continue
        rows.append(dict(row))
    rows.sort(key=lambda row: str(row.get("dp_id") or ""))
    return rows


def _numeric_hits(text: str) -> list[str]:
    return sorted({match.group(0).strip() for match in NUMERIC_RE.finditer(text)})


def _doc_base(doc: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "path": doc.get("path"),
        "market_relative_path": doc.get("market_relative_path"),
        "title": doc.get("title"),
    }


def _append_limited(target: list[dict[str, Any]], item: dict[str, Any], limit: int) -> None:
    if len(target) < limit:
        target.append(item)


def _sentence_candidates(
    *,
    dp_id: str,
    text: str,
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for sentence in SENTENCE_SPLIT_RE.split(text):
        sentence = sentence.strip()
        if not sentence:
            continue
        target_hits = _hits(sentence, TARGET_KEYWORDS[dp_id])
        if not target_hits:
            continue
        candidates.append(
            {
                "target_hits": target_hits,
                "support_hits": _hits(sentence, SUPPORT_KEYWORDS[dp_id]),
                "scope_hits": _hits(sentence, SCOPE_KEYWORDS),
                "direct_transmission_hits": _hits(sentence, DIRECT_TRANSMISSION_KEYWORDS),
                "numeric_hits": _numeric_hits(sentence),
                "reject_hits": _hits(sentence, REJECT_TERMS),
                "excerpt": sentence[:360],
            }
        )
    return candidates


def _classify_candidate(
    *,
    dp_id: str,
    doc: Mapping[str, Any],
    candidate: Mapping[str, Any],
) -> dict[str, Any]:
    reject_hits = candidate.get("reject_hits") or []
    support_hits = candidate.get("support_hits") or []
    scope_hits = candidate.get("scope_hits") or []
    direct_hits = candidate.get("direct_transmission_hits") or []
    numeric_hits = candidate.get("numeric_hits") or []
    has_business_scope = bool(scope_hits or direct_hits)
    if reject_hits:
        classification = "rejected_false_positive"
        reason = f"reject_terms:{','.join(reject_hits)}"
    elif support_hits and has_business_scope and numeric_hits:
        classification = "numeric_review_candidate"
        reason = "target_support_scope_and_numeric_evidence"
    elif support_hits and has_business_scope:
        classification = "textual_review_candidate"
        reason = "target_support_and_scope_evidence_without_numeric_value"
    else:
        classification = "weak_metric_context"
        reason = "target_keyword_without_complete_business_scope"
    return {
        **_doc_base(doc),
        "dp_id": dp_id,
        "classification": classification,
        "reason": reason,
        "target_hits": candidate.get("target_hits") or [],
        "support_hits": support_hits,
        "scope_hits": scope_hits,
        "direct_transmission_hits": direct_hits,
        "numeric_hits": numeric_hits,
        "excerpt": candidate.get("excerpt"),
    }


def _candidate_status(dp_id: str, review_count: int) -> str:
    if review_count <= 0:
        if dp_id == "L0.demand.frequency":
            return "external_cadence_source_required"
        if dp_id == "L0.demand.penetration":
            return "external_market_denominator_required"
        return "external_lifecycle_replacement_source_required"
    if dp_id == "L0.demand.frequency":
        return "local_cadence_review_candidates_found"
    if dp_id == "L0.demand.penetration":
        return "local_penetration_review_candidates_found"
    return "local_replacement_review_candidates_found"


def build_report(
    *,
    backlog_path: Path,
    market_root: Path,
    retained_examples_per_dp: int = 200,
) -> dict[str, Any]:
    started = time.time()
    backlog = _load_json(backlog_path)
    tasks = _metric_tasks(backlog)
    by_dp: dict[str, dict[str, Any]] = {
        str(task["dp_id"]): {
            "dp_id": task["dp_id"],
            "task_id": task.get("task_id"),
            "score_target": task.get("score_target"),
            "data_status": "Unknown",
            "acquisition_track": task.get("acquisition_track"),
            "source_priority": task.get("source_priority"),
            "target_keywords": list(TARGET_KEYWORDS[str(task["dp_id"])]),
            "support_keywords": list(SUPPORT_KEYWORDS[str(task["dp_id"])]),
            "candidate_document_count": 0,
            "review_candidate_count": 0,
            "numeric_review_candidate_count": 0,
            "textual_review_candidate_count": 0,
            "weak_candidate_count": 0,
            "rejected_candidate_count": 0,
            "candidate_examples": [],
            "rejected_examples": [],
            "candidate_status": "not_scanned",
            "known_draft_sufficient": False,
            "metric_inputs_ready": False,
            "review_required": True,
            "safe_to_upsert_without_review": False,
            "runtime_write_allowed": False,
            "production_write_allowed": False,
        }
        for task in tasks
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
        for dp_id, row in by_dp.items():
            classified = [
                _classify_candidate(dp_id=dp_id, doc=doc, candidate=candidate)
                for candidate in _sentence_candidates(dp_id=dp_id, text=text)
            ]
            if classified:
                row["candidate_document_count"] += 1
            for candidate in classified:
                classification = str(candidate["classification"])
                if classification == "numeric_review_candidate":
                    row["review_candidate_count"] += 1
                    row["numeric_review_candidate_count"] += 1
                    _append_limited(
                        row["candidate_examples"],
                        candidate,
                        retained_examples_per_dp,
                    )
                elif classification == "textual_review_candidate":
                    row["review_candidate_count"] += 1
                    row["textual_review_candidate_count"] += 1
                    _append_limited(
                        row["candidate_examples"],
                        candidate,
                        retained_examples_per_dp,
                    )
                elif classification.startswith("rejected"):
                    row["rejected_candidate_count"] += 1
                    _append_limited(
                        row["rejected_examples"],
                        candidate,
                        retained_examples_per_dp,
                    )
                else:
                    row["weak_candidate_count"] += 1
                    _append_limited(
                        row["candidate_examples"],
                        candidate,
                        retained_examples_per_dp,
                    )

    rows = sorted(by_dp.values(), key=lambda row: str(row["dp_id"]))
    for row in rows:
        row["candidate_status"] = _candidate_status(
            str(row["dp_id"]),
            int(row["review_candidate_count"]),
        )
        row["packet_contract_valid"] = (
            row["data_status"] == "Unknown"
            and row["metric_inputs_ready"] is False
            and row["runtime_write_allowed"] is False
            and row["production_write_allowed"] is False
        )
        row["packet_validation_errors"] = (
            []
            if row["packet_contract_valid"]
            else ["candidate rows must remain Unknown and write-disabled"]
        )

    status_counts = Counter(str(row["candidate_status"]) for row in rows)
    rows_with_review_candidates = sum(1 for row in rows if row["review_candidate_count"] > 0)
    return {
        "generated_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "elapsed_s": round(time.time() - started, 3),
        "inputs": {
            "backlog_path": _portable_path(backlog_path),
            "market_root": str(market_root),
        },
        "summary": {
            "business_metric_market_doc_task_count": len(rows),
            "market_html_files_scanned": len(html_files),
            "market_html_read_error_count": read_error_count,
            "rows_with_review_candidates_count": rows_with_review_candidates,
            "candidate_document_count": sum(
                int(row["candidate_document_count"]) for row in rows
            ),
            "review_candidate_count": sum(int(row["review_candidate_count"]) for row in rows),
            "numeric_review_candidate_count": sum(
                int(row["numeric_review_candidate_count"]) for row in rows
            ),
            "textual_review_candidate_count": sum(
                int(row["textual_review_candidate_count"]) for row in rows
            ),
            "weak_candidate_count": sum(int(row["weak_candidate_count"]) for row in rows),
            "rejected_candidate_count": sum(
                int(row["rejected_candidate_count"]) for row in rows
            ),
            "known_draft_sufficient_count": 0,
            "metric_inputs_ready_count": 0,
            "ready_for_approval_count": 0,
            "packet_contract_valid_count": sum(
                1 for row in rows if row["packet_contract_valid"]
            ),
            "packet_contract_invalid_count": sum(
                1 for row in rows if not row["packet_contract_valid"]
            ),
            "runtime_write_allowed_count": 0,
            "production_write_allowed_count": 0,
            "candidate_status_counts": dict(sorted(status_counts.items())),
            "score_mutation": "none; this audit is read-only and does not alter realtime_current",
        },
        "rows": rows,
    }


def render_markdown(report: Mapping[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# A-share Unknown external business metric market-doc candidates",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- Business metric market-doc tasks: `{summary['business_metric_market_doc_task_count']}`",
        f"- Market HTML files scanned: `{summary['market_html_files_scanned']}`",
        f"- Market HTML read errors: `{summary['market_html_read_error_count']}`",
        f"- Rows with review candidates: `{summary['rows_with_review_candidates_count']}`",
        f"- Candidate documents: `{summary['candidate_document_count']}`",
        f"- Review candidates: `{summary['review_candidate_count']}`",
        f"- Numeric review candidates: `{summary['numeric_review_candidate_count']}`",
        f"- Textual review candidates: `{summary['textual_review_candidate_count']}`",
        f"- Weak candidates: `{summary['weak_candidate_count']}`",
        f"- Rejected candidates: `{summary['rejected_candidate_count']}`",
        f"- Known-draft sufficient rows: `{summary['known_draft_sufficient_count']}`",
        f"- Metric inputs ready: `{summary['metric_inputs_ready_count']}`",
        f"- Production writes allowed: `{summary['production_write_allowed_count']}`",
        f"- Score mutation: `{summary['score_mutation']}`",
        "",
        "## Rows",
        "",
        "| dp_id | status | review candidates | numeric | weak | rejected | production write |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for row in report["rows"]:
        lines.append(
            "| "
            f"`{row['dp_id']}` | "
            f"`{row['candidate_status']}` | "
            f"{row['review_candidate_count']} | "
            f"{row['numeric_review_candidate_count']} | "
            f"{row['weak_candidate_count']} | "
            f"{row['rejected_candidate_count']} | "
            f"{'yes' if row['production_write_allowed'] else 'no'} |"
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- Candidate snippets are reviewer input, not scoreable Known values.",
            "- Numeric snippets still need source scope, denominator, bounds, and formula policy review.",
            "- Runtime and production writes remain disabled.",
            "",
        ]
    )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backlog-path", type=Path, default=DEFAULT_BACKLOG_PATH)
    parser.add_argument("--market-root", type=Path, default=DEFAULT_MARKET_ROOT)
    parser.add_argument("--retained-examples-per-dp", type=int, default=200)
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
