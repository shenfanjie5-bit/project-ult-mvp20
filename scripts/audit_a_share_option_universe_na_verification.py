#!/usr/bin/env python3
"""Verify A-share option/IV fields require a listed-option universe or N/A.

The remediation queue identifies A-share option/IV fields with no current
numeric input. This audit verifies that the current project has no broad
A-share per-stock option-chain source wired, that the existing option-chain
implementation is HK/US-scoped, and that A-share rows must stay Unknown,
Unavailable, or NotApplicable unless a legitimate listed-option universe or
licensed mapping exists.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
from collections import Counter
from pathlib import Path
from typing import Any, Mapping, Sequence


ROOT = Path(__file__).resolve().parent.parent
AUDIT_DIR = ROOT / "docs/audit"
DEFAULT_REMEDIATION_PATH = (
    AUDIT_DIR / "a_share_score_conversion_remediation_queue_2026-06-19.json"
)
DEFAULT_FIELD_CLOSURE_PATH = AUDIT_DIR / "a_share_score_field_closure_2026-06-19.json"
DEFAULT_JSON_OUTPUT = AUDIT_DIR / "a_share_option_universe_na_verification_2026-06-19.json"
DEFAULT_MD_OUTPUT = AUDIT_DIR / "a_share_option_universe_na_verification_2026-06-19.md"
DEFAULT_COLLECTOR_PATH = ROOT / "scripts/collector.py"
DEFAULT_FUTU_SOURCE_PATH = ROOT / "mvp20/sources/futu_source.py"

OPTION_DP_IDS = {
    "L6.priced.iv",
    "L7.trade.iv",
    "L7.trade.options_cp",
}


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _portable_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(ROOT))
    except ValueError:
        return str(path)


def _rows_by_dp(rows: Any) -> dict[str, Mapping[str, Any]]:
    out: dict[str, Mapping[str, Any]] = {}
    if not isinstance(rows, list):
        return out
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        dp_id = str(row.get("dp_id") or "")
        if dp_id:
            out[dp_id] = row
    return out


def _read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def _code_evidence(*, collector_path: Path, futu_source_path: Path) -> dict[str, Any]:
    collector_text = _read_text(collector_path)
    futu_text = _read_text(futu_source_path)
    option_dp_ids = ["L7.trade.iv", "L7.trade.options_cp", "L6.priced.iv"]
    hk_us_target_filter = 'target = [c for c in constituents if (c.get("ts_code") or "").endswith((".HK", ".US"))]'
    return {
        "collector_path": _portable_path(collector_path),
        "collector_options_excluded": (
            "Options-related dp_ids" in collector_text
            and "intentionally excluded" in collector_text
        ),
        "futu_source_path": _portable_path(futu_source_path),
        "futu_option_fields_present": all(dp_id in futu_text for dp_id in option_dp_ids),
        "futu_hk_us_filter_count": futu_text.count(hk_us_target_filter),
        "futu_hk_us_filter_present": futu_text.count(hk_us_target_filter) >= len(option_dp_ids),
    }


def _contract_errors(row: Mapping[str, Any], code_evidence: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    if row.get("remediation_class") != "missing_or_not_applicable_source":
        errors.append("remediation_class must be missing_or_not_applicable_source")
    if row.get("source_data_state") != "not_applicable_or_unlicensed":
        errors.append("source_data_state must be not_applicable_or_unlicensed")
    if row.get("closure_status") != "no_valid_a_share_target_data":
        errors.append("closure_status must be no_valid_a_share_target_data")
    if row.get("runtime_valid_real_ts_count") != 0:
        errors.append("runtime_valid_real_ts_count must be zero")
    if row.get("runtime_numeric_signal_ts_count") != 0:
        errors.append("runtime_numeric_signal_ts_count must be zero")
    if row.get("effective_score_path_ts_count") != 0:
        errors.append("effective_score_path_ts_count must be zero")
    if row.get("known_value_allowed_now") is not False:
        errors.append("known_value_allowed_now must be false")
    if row.get("safe_to_upsert_without_review") is not False:
        errors.append("safe_to_upsert_without_review must be false")
    if row.get("production_write_allowed") is not False:
        errors.append("production_write_allowed must be false")
    if not code_evidence.get("collector_options_excluded"):
        errors.append("collector options exclusion evidence is missing")
    if not code_evidence.get("futu_hk_us_filter_present"):
        errors.append("Futu HK/US filter evidence is missing")
    return errors


def _policy_for_dp(dp_id: str) -> dict[str, Any]:
    if dp_id == "L7.trade.options_cp":
        return {
            "required_source": "real option-chain call/put volume or open-interest data for a legitimate listed-option universe",
            "forbidden_proxies": [
                "stock turnover",
                "stock sentiment",
                "index call/put ratio without explicit mapping",
            ],
            "acceptable_current_resolution": "keep Unknown/Unavailable or emit reviewed NotApplicable for non-listed-option A-share rows",
        }
    return {
        "required_source": "real implied volatility from a listed option chain or licensed IV surface mapped to the specific underlying",
        "forbidden_proxies": [
            "stock realized volatility",
            "turnover",
            "sentiment",
            "index IV without explicit mapping",
        ],
        "acceptable_current_resolution": "keep Unknown/Unavailable or emit reviewed NotApplicable for non-listed-option A-share rows",
    }


def build_report(
    *,
    remediation_path: Path,
    field_closure_path: Path,
    collector_path: Path,
    futu_source_path: Path,
) -> dict[str, Any]:
    remediation = _load_json(remediation_path)
    field_closure = _load_json(field_closure_path)
    closure_by_dp = _rows_by_dp(field_closure.get("rows"))
    code_evidence = _code_evidence(
        collector_path=collector_path,
        futu_source_path=futu_source_path,
    )

    rows: list[dict[str, Any]] = []
    for remediation_row in remediation.get("rows") or []:
        if not isinstance(remediation_row, Mapping):
            continue
        dp_id = str(remediation_row.get("dp_id") or "")
        if dp_id not in OPTION_DP_IDS:
            continue
        closure_row = closure_by_dp.get(dp_id, {})
        row = {
            "dp_id": dp_id,
            "score_target": remediation_row.get("score_target"),
            "remediation_class": remediation_row.get("remediation_class"),
            "conversion_path_status": remediation_row.get("conversion_path_status"),
            "source_data_state": remediation_row.get("source_data_state"),
            "route": remediation_row.get("route"),
            "intent_subtype": remediation_row.get("intent_subtype"),
            "closure_status": closure_row.get("closure_status"),
            "runtime_valid_real_ts_count": int(
                closure_row.get("runtime_valid_real_ts_count") or 0
            ),
            "runtime_numeric_signal_ts_count": int(
                closure_row.get("runtime_numeric_signal_ts_count") or 0
            ),
            "effective_score_path_ts_count": int(
                closure_row.get("effective_score_path_ts_count") or 0
            ),
            "sample_values_count": len(closure_row.get("sample_values") or []),
            "source_categories": closure_row.get("runtime_source_categories") or {},
            "known_value_allowed_now": False,
            "na_or_unavailable_allowed_after_review": True,
            "source_universe_required": True,
            "policy": _policy_for_dp(dp_id),
            "evidence_refs": [
                "docs/audit/a_share_score_conversion_remediation_queue_2026-06-19.json",
                "docs/audit/a_share_score_field_closure_2026-06-19.json",
                "scripts/collector.py",
                "mvp20/sources/futu_source.py",
                "docs/audit/a_share_p1_structured_gap_sources_2026-06-18.md",
                "docs/audit/a_share_web_paid_gap_plan.md",
            ],
            "safe_to_upsert_without_review": False,
            "production_write_allowed": False,
        }
        errors = _contract_errors(row, code_evidence)
        row["verification_contract_valid"] = not errors
        row["verification_errors"] = errors
        rows.append(row)

    rows.sort(key=lambda row: row["dp_id"])
    by_target = Counter(str(row.get("score_target") or "") for row in rows)
    contract_valid_count = sum(1 for row in rows if row["verification_contract_valid"])
    no_current_input_count = sum(
        1
        for row in rows
        if row["runtime_valid_real_ts_count"] == 0
        and row["runtime_numeric_signal_ts_count"] == 0
        and row["effective_score_path_ts_count"] == 0
    )
    known_allowed_count = sum(1 for row in rows if row["known_value_allowed_now"])

    return {
        "generated_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "inputs": {
            "remediation_path": _portable_path(remediation_path),
            "field_closure_path": _portable_path(field_closure_path),
            "collector_path": _portable_path(collector_path),
            "futu_source_path": _portable_path(futu_source_path),
            "dockcase_scan": "not_performed",
        },
        "summary": {
            "option_universe_packet_count": len(rows),
            "no_current_a_share_input_count": no_current_input_count,
            "listed_option_universe_required_count": len(rows),
            "na_or_unavailable_allowed_after_review_count": len(rows),
            "known_value_allowed_now_count": known_allowed_count,
            "verification_contract_valid_count": contract_valid_count,
            "verification_contract_invalid_count": len(rows) - contract_valid_count,
            "safe_to_upsert_without_review_count": 0,
            "production_write_allowed_count": 0,
            "score_target_counts": dict(sorted(by_target.items())),
            "code_evidence": code_evidence,
            "score_mutation": "none; this audit is read-only and does not alter realtime_current",
        },
        "rows": rows,
    }


def _md_table_row(values: Sequence[Any]) -> str:
    return "| " + " | ".join(str(value) for value in values) + " |"


def render_markdown(report: Mapping[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# A-share option-universe / N/A verification",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- Option-universe packets: `{summary['option_universe_packet_count']}`",
        f"- No current A-share input: `{summary['no_current_a_share_input_count']}`",
        f"- Listed-option universe required: `{summary['listed_option_universe_required_count']}`",
        f"- N/A or Unavailable allowed after review: `{summary['na_or_unavailable_allowed_after_review_count']}`",
        f"- Known value allowed now: `{summary['known_value_allowed_now_count']}`",
        f"- Verification contracts valid: `{summary['verification_contract_valid_count']}`",
        f"- Production writes allowed: `{summary['production_write_allowed_count']}`",
        f"- Score mutation: `{summary['score_mutation']}`",
        "",
        "## Code Evidence",
        "",
        "| evidence | value |",
        "|---|---|",
    ]
    for key, value in summary["code_evidence"].items():
        lines.append(_md_table_row([f"`{key}`", f"`{value}`"]))
    lines.extend(
        [
            "",
            "## Packets",
            "",
            "| dp_id | target | closure | valid ts_codes | required source | known allowed now |",
            "|---|---|---|---:|---|---|",
        ]
    )
    for row in report["rows"]:
        lines.append(
            _md_table_row(
                [
                    f"`{row['dp_id']}`",
                    f"`{row['score_target']}`",
                    f"`{row['closure_status']}`",
                    row["runtime_valid_real_ts_count"],
                    row["policy"]["required_source"],
                    row["known_value_allowed_now"],
                ]
            )
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- These fields must not be filled from stock turnover, sentiment, realized volatility, or broad index option data without explicit mapping.",
            "- A future implementation can emit Known rows only for a legitimate listed-option universe or licensed underlying mapping.",
            "- For ordinary A-share rows outside that universe, the safe resolution is reviewed NotApplicable/Unavailable rather than a fabricated numeric score.",
            "",
        ]
    )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--remediation-path", type=Path, default=DEFAULT_REMEDIATION_PATH)
    parser.add_argument("--field-closure-path", type=Path, default=DEFAULT_FIELD_CLOSURE_PATH)
    parser.add_argument("--collector-path", type=Path, default=DEFAULT_COLLECTOR_PATH)
    parser.add_argument("--futu-source-path", type=Path, default=DEFAULT_FUTU_SOURCE_PATH)
    parser.add_argument("--json-output", type=Path, default=DEFAULT_JSON_OUTPUT)
    parser.add_argument("--md-output", type=Path, default=DEFAULT_MD_OUTPUT)
    parser.add_argument("--no-write", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_report(
        remediation_path=args.remediation_path,
        field_closure_path=args.field_closure_path,
        collector_path=args.collector_path,
        futu_source_path=args.futu_source_path,
    )
    if not args.no_write:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        args.md_output.write_text(render_markdown(report), encoding="utf-8")
    print(json.dumps({"ok": True, **report["summary"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
