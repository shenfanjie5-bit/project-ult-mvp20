#!/usr/bin/env python3
"""Confirm source scope for the P1 L0.demand.penetration candidate.

The report checks whether the highest-priority penetration value candidate has
the expected source file, raw percent token, domestic/A-share scope words, and
market-share denominator context. It does not select a value or create a Known
draft.
"""

from __future__ import annotations

import argparse
import datetime as dt
import html.parser
import json
import re
import sys
import time
from pathlib import Path
from typing import Any, Mapping

_BOOTSTRAP_ROOT = Path(__file__).resolve().parent.parent
if str(_BOOTSTRAP_ROOT) not in sys.path:
    sys.path.insert(0, str(_BOOTSTRAP_ROOT))


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PRIORITY_PATH = (
    ROOT / "docs/audit/a_share_unknown_penetration_value_priority_2026-06-19.json"
)
DEFAULT_MARKET_DATA_ROOT = Path("/Volumes/dockcase2tb/market_data")
DEFAULT_JSON_OUTPUT = (
    ROOT
    / "docs/audit/a_share_unknown_penetration_p1_source_confirmation_2026-06-19.json"
)
DEFAULT_MD_OUTPUT = (
    ROOT
    / "docs/audit/a_share_unknown_penetration_p1_source_confirmation_2026-06-19.md"
)


class _TextExtractor(html.parser.HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        text = data.strip()
        if text:
            self.parts.append(text)

    def text(self) -> str:
        return " ".join(self.parts)


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


def _extract_text(path: Path) -> tuple[str, str | None]:
    if not path.exists():
        return "", "source file is missing"
    try:
        html = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return "", f"source file read failed: {exc}"
    parser = _TextExtractor()
    parser.feed(html)
    return re.sub(r"\s+", " ", parser.text()).strip(), None


def _contains_any(text: str, terms: list[str]) -> bool:
    return any(term in text for term in terms)


def _confirmation_row(row: Mapping[str, Any], *, market_data_root: Path) -> dict[str, Any]:
    rel = str(row.get("market_relative_path") or "")
    source_path = market_data_root / rel
    text, read_error = _extract_text(source_path)
    values = [
        value
        for value in row.get("candidate_values") or []
        if isinstance(value, Mapping)
    ]
    raw_tokens = [str(value.get("raw_token") or "") for value in values]
    checks = {
        "source_file_found": read_error is None,
        "raw_value_token_present": any(token and token in text for token in raw_tokens),
        "source_attribution_present": _contains_any(text, ["华泰证券"]),
        "domain_terms_present": _contains_any(text, ["电子气体"]),
        "domestic_scope_present": _contains_any(text, ["我国", "国内"]),
        "listed_company_scope_present": _contains_any(text, ["上市公司"]),
        "market_share_context_present": _contains_any(text, ["市场份额", "市占率"]),
        "market_denominator_present": _contains_any(text, ["国内市场规模", "市场规模"]),
    }
    required = [
        "source_file_found",
        "raw_value_token_present",
        "source_attribution_present",
        "domain_terms_present",
        "domestic_scope_present",
        "listed_company_scope_present",
        "market_share_context_present",
        "market_denominator_present",
    ]
    confirmed = all(checks[name] for name in required)
    snippet = ""
    if text:
        match = re.search(r"2024年.{0,120}?40%", text)
        if match:
            snippet = match.group(0)
        else:
            token = raw_tokens[0] if raw_tokens else ""
            index = text.find(token)
            if index >= 0:
                start = max(0, index - 80)
                end = min(len(text), index + 120)
                snippet = text[start:end]
            else:
                snippet = text[:240]
    return {
        "dp_id": row.get("dp_id"),
        "value_review_packet_id": row.get("value_review_packet_id"),
        "priority_bucket": row.get("priority_bucket"),
        "source_quality": row.get("source_quality"),
        "title": row.get("title"),
        "market_relative_path": rel,
        "source_path": str(source_path),
        "read_error": read_error,
        "raw_tokens": raw_tokens,
        "confirmation_checks": checks,
        "source_scope_confirmed": confirmed,
        "confirmed_scope": (
            "domestic listed-company electronic-gas market-share numerator over domestic market-size denominator"
            if confirmed
            else None
        ),
        "source_excerpt": row.get("excerpt"),
        "source_file_snippet": snippet,
        "selected_raw_value": None,
        "selected_value_json": None,
        "known_draft_sufficient": False,
        "approval_ready": False,
        "runtime_write_allowed": False,
        "production_write_allowed": False,
        "missing_before_known": [
            "reviewed_numeric_value_selection",
            "reviewed_bounds",
            "reviewed_formula_policy",
            "issuer_or_industry_applicability_review",
            "approval_record",
        ],
    }


def build_report(*, priority_path: Path, market_data_root: Path) -> dict[str, Any]:
    started = time.time()
    priority = _load_json(priority_path)
    rows = [
        _confirmation_row(row, market_data_root=market_data_root)
        for row in priority.get("rows") or []
        if isinstance(row, Mapping)
        and row.get("priority_bucket") == "P1_preferred_source_scope_review"
    ]
    return {
        "generated_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "elapsed_s": round(time.time() - started, 3),
        "inputs": {
            "priority_path": _portable_path(priority_path),
            "market_data_root": str(market_data_root),
        },
        "summary": {
            "p1_candidate_count": len(rows),
            "source_file_found_count": sum(
                1 for row in rows if row["confirmation_checks"]["source_file_found"]
            ),
            "raw_value_token_confirmed_count": sum(
                1
                for row in rows
                if row["confirmation_checks"]["raw_value_token_present"]
            ),
            "source_scope_confirmed_count": sum(
                1 for row in rows if row["source_scope_confirmed"]
            ),
            "selected_raw_value_count": 0,
            "selected_value_json_count": 0,
            "known_draft_sufficient_count": 0,
            "approval_ready_count": 0,
            "runtime_write_allowed_count": 0,
            "production_write_allowed_count": 0,
            "score_mutation": "none; source confirmation only and no realtime_current mutation",
        },
        "rows": rows,
    }


def render_markdown(report: Mapping[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# A-share Unknown penetration P1 source confirmation",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- P1 candidates: `{summary['p1_candidate_count']}`",
        f"- Source files found: `{summary['source_file_found_count']}`",
        f"- Raw value tokens confirmed: `{summary['raw_value_token_confirmed_count']}`",
        f"- Source scope confirmed: `{summary['source_scope_confirmed_count']}`",
        f"- Selected raw values: `{summary['selected_raw_value_count']}`",
        f"- Known-draft sufficient: `{summary['known_draft_sufficient_count']}`",
        f"- Runtime writes allowed: `{summary['runtime_write_allowed_count']}`",
        f"- Production writes allowed: `{summary['production_write_allowed_count']}`",
        f"- Score mutation: `{summary['score_mutation']}`",
        "",
        "## Rows",
        "",
        "| dp_id | title | raw tokens | scope confirmed | missing before Known |",
        "|---|---|---|---:|---|",
    ]
    for row in report["rows"]:
        title = str(row.get("title") or "").replace("|", "\\|")
        missing = ", ".join(row.get("missing_before_known") or [])
        lines.append(
            "| "
            f"`{row.get('dp_id')}` | "
            f"{title} | "
            f"`{', '.join(row.get('raw_tokens') or [])}` | "
            f"{'yes' if row.get('source_scope_confirmed') else 'no'} | "
            f"{missing} |"
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- Source-scope confirmation is not value selection.",
            "- The 40% token is still a review candidate until value selection, bounds, formula policy, issuer/industry applicability, and approval are completed.",
            "- This report creates no Known draft and writes no runtime data.",
            "",
        ]
    )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--priority-path", type=Path, default=DEFAULT_PRIORITY_PATH)
    parser.add_argument("--market-data-root", type=Path, default=DEFAULT_MARKET_DATA_ROOT)
    parser.add_argument("--json-output", type=Path, default=DEFAULT_JSON_OUTPUT)
    parser.add_argument("--md-output", type=Path, default=DEFAULT_MD_OUTPUT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_report(
        priority_path=args.priority_path,
        market_data_root=args.market_data_root,
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
