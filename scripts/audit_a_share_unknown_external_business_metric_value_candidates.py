#!/usr/bin/env python3
"""Adjudicate P0 external business-metric policy drafts for value candidates.

The policy-draft audit keeps P0 packets Unknown because a reviewer still needs
to select a value, approve bounds, and approve the formula policy.  This audit
adds a stricter, read-only value-candidate screen so dates, stock moves,
foreign-market snippets, and broad forecasts are not mistaken for scoreable
A-share business metrics.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import time
from collections import Counter
from pathlib import Path
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_POLICY_DRAFT_PATH = (
    ROOT / "docs/audit/a_share_unknown_external_business_metric_policy_drafts_2026-06-19.json"
)
DEFAULT_JSON_OUTPUT = (
    ROOT
    / "docs/audit/a_share_unknown_external_business_metric_value_candidates_2026-06-19.json"
)
DEFAULT_MD_OUTPUT = (
    ROOT
    / "docs/audit/a_share_unknown_external_business_metric_value_candidates_2026-06-19.md"
)

DATE_RE = re.compile(r"^\d{1,4}(?:年|月|日|季度|Q[1-4])$")
PERCENT_RE = re.compile(r"^-?\d+(?:\.\d+)?%$")
MONEY_RE = re.compile(r"^-?\d+(?:\.\d+)?(?:亿|万亿|万元|亿元)$")
MULTIPLE_RE = re.compile(r"^-?\d+(?:\.\d+)?倍$")
ASHARE_CODE_RE = re.compile(r"[（(](?:00|30|60|68)\d{4}[)）]")

FOREIGN_SCOPE_TERMS = (
    "欧盟",
    "欧洲",
    "英国",
    "欧洲自由贸易联盟",
    "特斯拉",
    "韩国",
    "美国",
    "港股",
    "HK",
)
NON_A_SHARE_COMPANY_TERMS = ("京东", "五一视界", "智谱AI", "02513.HK")
FORECAST_TERMS = ("预计", "假设", "未来", "2030年", "2029年", "复合年均增长", "CAGR")
STOCK_MOVE_TERMS = ("涨幅", "涨超", "一度涨近", "上市首日")
TARGET_METRIC_TERMS = (
    "市场份额",
    "市占率",
    "覆盖率",
    "渗透率",
    "占比",
)
FREQUENCY_TERMS = ("频率", "复购", "使用频次", "日活", "月活", "活跃使用")


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


def _token_rejection_reason(token: str, text: str, dp_id: str) -> str | None:
    if DATE_RE.match(token):
        return "date_or_period_token"
    if MONEY_RE.match(token):
        return "monetary_token"
    if MULTIPLE_RE.match(token):
        return "growth_multiple_token"
    if PERCENT_RE.match(token) and _hits(text, STOCK_MOVE_TERMS):
        return "stock_price_move_context"
    if dp_id == "L0.demand.frequency" and not _hits(text, FREQUENCY_TERMS):
        return "not_frequency_or_cadence_metric"
    if PERCENT_RE.match(token):
        return None
    return "unsupported_numeric_token"


def _scope_verdict(text: str) -> tuple[str, list[str]]:
    foreign_hits = _hits(text, FOREIGN_SCOPE_TERMS)
    non_a_share_hits = _hits(text, NON_A_SHARE_COMPANY_TERMS)
    forecast_hits = _hits(text, FORECAST_TERMS)
    target_hits = _hits(text, TARGET_METRIC_TERMS)
    has_a_share_code = bool(ASHARE_CODE_RE.search(text))
    has_a_share_context = has_a_share_code or "A股" in text or "上市公司" in text
    hits = sorted(set(foreign_hits + non_a_share_hits + forecast_hits + target_hits))
    if foreign_hits:
        return "reject_foreign_or_non_a_share_scope", hits
    if non_a_share_hits and not has_a_share_code:
        return "reject_non_a_share_company_scope", hits
    if forecast_hits and not has_a_share_code:
        return "review_forecast_or_assumption_scope", hits
    if target_hits and has_a_share_context:
        return "review_a_share_or_domestic_scope", hits
    if target_hits:
        return "review_domestic_or_industry_scope", hits
    return "ambiguous_scope", hits


def _row_status(
    *,
    dp_id: str,
    value_candidates: list[dict[str, Any]],
    scope_verdict: str,
) -> str:
    if not value_candidates:
        return "no_scoreable_numeric_candidate"
    if scope_verdict.startswith("reject_"):
        return "scope_rejected"
    if scope_verdict == "ambiguous_scope":
        return "scope_ambiguous"
    return "value_candidate_shortlist_review_required"


def _validation_errors(row: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    if not row.get("value_candidate_adjudication_id"):
        errors.append("value_candidate_adjudication_id is required")
    if row.get("data_status") != "Unknown":
        errors.append("data_status must remain Unknown")
    if row.get("metric_inputs_ready") is not False:
        errors.append("metric_inputs_ready must remain false")
    if row.get("known_draft_sufficient") is not False:
        errors.append("known_draft_sufficient must remain false")
    if row.get("review_status") != "review_required":
        errors.append("review_status must be review_required")
    if row.get("runtime_write_allowed") is not False:
        errors.append("runtime_write_allowed must be false")
    if row.get("production_write_allowed") is not False:
        errors.append("production_write_allowed must be false")
    if not row.get("missing_before_known"):
        errors.append("missing_before_known is required")
    return errors


def _adjudicate(row: Mapping[str, Any]) -> dict[str, Any]:
    dp_id = str(row.get("dp_id") or "")
    text = " ".join(str(row.get(key) or "") for key in ("title", "excerpt"))
    tokens = [str(token) for token in row.get("numeric_hits") or []]
    value_candidates: list[dict[str, Any]] = []
    rejected_tokens: list[dict[str, Any]] = []
    for token in tokens:
        reason = _token_rejection_reason(token, text, dp_id)
        if reason:
            rejected_tokens.append({"token": token, "reason": reason})
        else:
            value_candidates.append({"token": token, "unit": "percent"})
    scope_verdict, scope_hits = _scope_verdict(text)
    status = _row_status(
        dp_id=dp_id,
        value_candidates=value_candidates,
        scope_verdict=scope_verdict,
    )
    packet = {
        "value_candidate_adjudication_id": row.get("policy_draft_id"),
        "policy_draft_id": row.get("policy_draft_id"),
        "source_packet_id": row.get("source_packet_id"),
        "dp_id": dp_id,
        "score_target": row.get("score_target"),
        "data_status": "Unknown",
        "candidate_classification": row.get("candidate_classification"),
        "numeric_hits": tokens,
        "value_candidate_tokens": value_candidates,
        "rejected_numeric_tokens": rejected_tokens,
        "source_scope_verdict": scope_verdict,
        "source_scope_hits": scope_hits,
        "adjudication_status": status,
        "title": row.get("title"),
        "market_relative_path": row.get("market_relative_path"),
        "excerpt": row.get("excerpt"),
        "missing_before_known": [
            "reviewed_source_scope",
            "reviewed_numeric_value",
            "reviewed_bounds",
            "reviewed_formula_policy",
            "approval_record",
        ],
        "metric_inputs_ready": False,
        "known_draft_sufficient": False,
        "review_status": "review_required",
        "safe_to_upsert_without_review": False,
        "runtime_write_allowed": False,
        "production_write_allowed": False,
        "score_mutation": "none",
    }
    errors = _validation_errors(packet)
    return {
        **packet,
        "value_candidate_contract_valid": not errors,
        "value_candidate_validation_errors": errors,
    }


def build_report(*, policy_draft_path: Path) -> dict[str, Any]:
    started = time.time()
    source = _load_json(policy_draft_path)
    source_rows = [row for row in source.get("rows") or [] if isinstance(row, Mapping)]
    rows = [_adjudicate(row) for row in source_rows]
    rows.sort(
        key=lambda row: (
            str(row.get("dp_id") or ""),
            str(row.get("source_scope_verdict") or ""),
            str(row.get("market_relative_path") or ""),
        )
    )
    status_counts = Counter(str(row["adjudication_status"]) for row in rows)
    scope_counts = Counter(str(row["source_scope_verdict"]) for row in rows)
    by_dp = Counter(str(row.get("dp_id") or "") for row in rows)
    shortlist = [
        row
        for row in rows
        if row["adjudication_status"] == "value_candidate_shortlist_review_required"
    ]
    return {
        "generated_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "elapsed_s": round(time.time() - started, 3),
        "inputs": {"policy_draft_path": _portable_path(policy_draft_path)},
        "summary": {
            "policy_draft_packet_count": len(source_rows),
            "value_candidate_adjudication_row_count": len(rows),
            "rows_with_value_candidate_tokens_count": sum(
                1 for row in rows if row["value_candidate_tokens"]
            ),
            "value_candidate_token_count": sum(
                len(row["value_candidate_tokens"]) for row in rows
            ),
            "rejected_numeric_token_count": sum(
                len(row["rejected_numeric_tokens"]) for row in rows
            ),
            "shortlist_review_required_count": len(shortlist),
            "scope_rejected_count": status_counts.get("scope_rejected", 0),
            "scope_ambiguous_count": status_counts.get("scope_ambiguous", 0),
            "no_scoreable_numeric_candidate_count": status_counts.get(
                "no_scoreable_numeric_candidate", 0
            ),
            "metric_inputs_ready_count": 0,
            "known_draft_sufficient_count": 0,
            "approved_runtime_write_count": 0,
            "runtime_write_allowed_count": 0,
            "production_write_allowed_count": 0,
            "value_candidate_contract_valid_count": sum(
                1 for row in rows if row["value_candidate_contract_valid"]
            ),
            "value_candidate_contract_invalid_count": sum(
                1 for row in rows if not row["value_candidate_contract_valid"]
            ),
            "adjudication_status_counts": dict(sorted(status_counts.items())),
            "source_scope_verdict_counts": dict(sorted(scope_counts.items())),
            "row_counts_by_dp_id": dict(sorted(by_dp.items())),
            "score_mutation": "none; this audit is read-only and does not alter realtime_current",
        },
        "rows": rows,
    }


def render_markdown(report: Mapping[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# A-share Unknown external business metric value candidates",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- Policy draft packets: `{summary['policy_draft_packet_count']}`",
        f"- Rows adjudicated: `{summary['value_candidate_adjudication_row_count']}`",
        f"- Rows with value-candidate tokens: `{summary['rows_with_value_candidate_tokens_count']}`",
        f"- Value-candidate tokens: `{summary['value_candidate_token_count']}`",
        f"- Rejected numeric tokens: `{summary['rejected_numeric_token_count']}`",
        f"- Shortlist review required: `{summary['shortlist_review_required_count']}`",
        f"- Metric inputs ready: `{summary['metric_inputs_ready_count']}`",
        f"- Known-draft sufficient: `{summary['known_draft_sufficient_count']}`",
        f"- Production writes allowed: `{summary['production_write_allowed_count']}`",
        f"- Score mutation: `{summary['score_mutation']}`",
        "",
        "## Status Counts",
        "",
        "| status | count |",
        "|---|---:|",
    ]
    for status, count in summary["adjudication_status_counts"].items():
        lines.append(f"| `{status}` | {count} |")
    lines.extend(["", "## Rows", "", "| dp_id | status | value tokens | scope |", "|---|---|---:|---|"])
    for row in report["rows"]:
        lines.append(
            "| "
            f"`{row['dp_id']}` | "
            f"`{row['adjudication_status']}` | "
            f"{len(row['value_candidate_tokens'])} | "
            f"`{row['source_scope_verdict']}` |"
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- Shortlisted rows still require source-scope, value, bounds, formula-policy, and approval review.",
            "- Rejected or ambiguous rows remain Unknown and should not be treated as valid score information.",
            "- This audit does not create Known values and does not write runtime scores.",
            "",
        ]
    )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--policy-draft-path", type=Path, default=DEFAULT_POLICY_DRAFT_PATH)
    parser.add_argument("--json-output", type=Path, default=DEFAULT_JSON_OUTPUT)
    parser.add_argument("--md-output", type=Path, default=DEFAULT_MD_OUTPUT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_report(policy_draft_path=args.policy_draft_path)
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    args.md_output.write_text(render_markdown(report), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
