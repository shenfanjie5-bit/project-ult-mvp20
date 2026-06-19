#!/usr/bin/env python3
"""Verify intentional A-share score-conversion suppression rows.

The score-conversion remediation queue separates fields that should remain
governed, deduplicated, or data-only from formula-policy rows. This audit
checks those rows against the current field-closure evidence and lightweight
runtime signal probes so reviewers can distinguish intentional suppression from
missing implementation.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Mapping, Sequence


ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mvp20.aggregator import _realtime_signal  # noqa: E402


AUDIT_DIR = ROOT / "docs/audit"
DEFAULT_REMEDIATION_PATH = (
    AUDIT_DIR / "a_share_score_conversion_remediation_queue_2026-06-19.json"
)
DEFAULT_FIELD_CLOSURE_PATH = AUDIT_DIR / "a_share_score_field_closure_2026-06-19.json"
DEFAULT_JSON_OUTPUT = (
    AUDIT_DIR / "a_share_governance_suppression_verification_2026-06-19.json"
)
DEFAULT_MD_OUTPUT = (
    AUDIT_DIR / "a_share_governance_suppression_verification_2026-06-19.md"
)


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


def _sample_payload(row: Mapping[str, Any] | None) -> tuple[str | None, Any]:
    if not row:
        return None, None
    for sample in row.get("sample_values") or []:
        if not isinstance(sample, Mapping):
            continue
        return str(sample.get("ts_code") or "") or None, sample.get("value")
    return None, None


def _json_safe(value: Any) -> Any:
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, Mapping):
        return {str(key): _json_safe(val) for key, val in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    return value


def _signal_probe(
    *,
    dp_id: str,
    score_target: str,
    ts_code: str | None,
    payload: Any,
    with_peer_context: bool,
) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {
            "payload_available": False,
            "signal": None,
            "signal_ready": False,
            "with_peer_context": with_peer_context,
        }
    peer_context = None
    if with_peer_context:
        peer_context = {"_val_pe_pool_of": {ts_code or "000001.SZ": "AUDIT_POOL"}}
    signal = _realtime_signal(
        dp_id,
        payload,
        score_target,
        ts_code=ts_code or "000001.SZ",
        peer_context=peer_context,
    )
    return {
        "payload_available": True,
        "signal": _json_safe(signal),
        "signal_ready": signal is not None,
        "with_peer_context": with_peer_context,
    }


def _replacement_path(
    remediation_row: Mapping[str, Any],
    *,
    closure_by_dp: Mapping[str, Mapping[str, Any]],
    remediation_by_dp: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    replacement_dp_id = remediation_row.get("replacement_dp_id")
    canonical_dp_id = remediation_row.get("canonical_dp_id")
    target_dp_id = replacement_dp_id or canonical_dp_id
    target = closure_by_dp.get(str(target_dp_id), {}) if target_dp_id else {}
    transitive_dp_id = None
    transitive = {}
    if target_dp_id and target.get("closure_status") != "closed_reaches_final_score":
        linked_remediation = remediation_by_dp.get(str(target_dp_id), {})
        transitive_dp_id = linked_remediation.get("replacement_dp_id") or linked_remediation.get(
            "canonical_dp_id"
        )
        if transitive_dp_id:
            transitive = closure_by_dp.get(str(transitive_dp_id), {})

    target_ready = target.get("closure_status") == "closed_reaches_final_score"
    transitive_ready = transitive.get("closure_status") == "closed_reaches_final_score"
    return {
        "replacement_dp_id": replacement_dp_id,
        "canonical_dp_id": canonical_dp_id,
        "target_dp_id": target_dp_id,
        "target_closure_status": target.get("closure_status"),
        "target_score_target": target.get("score_target"),
        "target_runtime_valid_real_ts_count": int(
            target.get("runtime_valid_real_ts_count") or 0
        ),
        "target_effective_score_path_ts_count": int(
            target.get("effective_score_path_ts_count") or 0
        ),
        "target_path_ready": target_ready,
        "transitive_dp_id": transitive_dp_id,
        "transitive_closure_status": transitive.get("closure_status"),
        "transitive_score_target": transitive.get("score_target"),
        "transitive_runtime_valid_real_ts_count": int(
            transitive.get("runtime_valid_real_ts_count") or 0
        ),
        "transitive_effective_score_path_ts_count": int(
            transitive.get("effective_score_path_ts_count") or 0
        ),
        "transitive_path_ready": transitive_ready,
        "replacement_or_canonical_ready": target_ready or transitive_ready,
    }


def _verification_status(
    *,
    row: Mapping[str, Any],
    path: Mapping[str, Any],
    direct_probe: Mapping[str, Any],
    peer_probe: Mapping[str, Any],
) -> str:
    subtype = str(row.get("intent_subtype") or "")
    if subtype == "peer_context_suppressed":
        if path.get("replacement_or_canonical_ready") and not peer_probe.get("signal_ready"):
            return "suppressed_with_replacement_ready"
        return "peer_suppression_requires_review"
    if subtype == "derived_replacement":
        if path.get("replacement_or_canonical_ready") and not direct_probe.get("signal_ready"):
            return "derived_replacement_ready"
        return "derived_replacement_requires_review"
    if subtype == "duplicate_evidence":
        if path.get("target_path_ready"):
            return "duplicate_with_canonical_ready"
        if path.get("transitive_path_ready"):
            return "duplicate_with_transitive_replacement_ready"
        return "duplicate_requires_canonical_review"
    if subtype == "data_only_no_safe_signal":
        if not direct_probe.get("signal_ready"):
            return "data_only_suppression_verified"
        return "data_only_probe_not_suppressed"
    return "manual_review_required"


def build_report(*, remediation_path: Path, field_closure_path: Path) -> dict[str, Any]:
    remediation = _load_json(remediation_path)
    field_closure = _load_json(field_closure_path)
    closure_by_dp = _rows_by_dp(field_closure.get("rows"))
    remediation_by_dp = _rows_by_dp(remediation.get("rows"))

    rows: list[dict[str, Any]] = []
    for source_row in remediation.get("rows") or []:
        if not isinstance(source_row, Mapping):
            continue
        if source_row.get("remediation_class") != "intentional_governance_or_duplicate":
            continue
        dp_id = str(source_row.get("dp_id") or "")
        score_target = str(source_row.get("score_target") or "")
        closure_row = closure_by_dp.get(dp_id, {})
        ts_code, payload = _sample_payload(closure_row)
        direct_probe = _signal_probe(
            dp_id=dp_id,
            score_target=score_target,
            ts_code=ts_code,
            payload=payload,
            with_peer_context=False,
        )
        peer_probe = _signal_probe(
            dp_id=dp_id,
            score_target=score_target,
            ts_code=ts_code,
            payload=payload,
            with_peer_context=True,
        )
        path = _replacement_path(
            source_row,
            closure_by_dp=closure_by_dp,
            remediation_by_dp=remediation_by_dp,
        )
        status = _verification_status(
            row=source_row,
            path=path,
            direct_probe=direct_probe,
            peer_probe=peer_probe,
        )
        rows.append(
            {
                "dp_id": dp_id,
                "score_target": score_target,
                "intent_subtype": source_row.get("intent_subtype"),
                "route": source_row.get("route"),
                "runtime_valid_real_ts_count": int(
                    source_row.get("runtime_valid_real_ts_count") or 0
                ),
                "runtime_source_categories": source_row.get("runtime_source_categories") or {},
                "replacement_path": path,
                "direct_signal_probe": direct_probe,
                "peer_context_signal_probe": peer_probe,
                "verification_status": status,
                "suppression_verified": status
                in {
                    "suppressed_with_replacement_ready",
                    "derived_replacement_ready",
                    "duplicate_with_canonical_ready",
                    "duplicate_with_transitive_replacement_ready",
                    "data_only_suppression_verified",
                },
                "repair_hint": source_row.get("repair_hint"),
                "safe_to_upsert_without_review": False,
                "production_write_allowed": False,
            }
        )

    rows.sort(key=lambda row: (row["intent_subtype"] or "", row["dp_id"]))
    by_subtype = Counter(str(row["intent_subtype"] or "") for row in rows)
    by_status = Counter(row["verification_status"] for row in rows)
    replacement_ready_count = sum(
        1 for row in rows if row["replacement_path"].get("replacement_or_canonical_ready")
    )
    direct_suppressed_count = sum(
        1 for row in rows if not row["direct_signal_probe"].get("signal_ready")
    )
    peer_context_suppressed_count = sum(
        1
        for row in rows
        if row["intent_subtype"] == "peer_context_suppressed"
        and not row["peer_context_signal_probe"].get("signal_ready")
    )
    suppression_verified_count = sum(1 for row in rows if row["suppression_verified"])

    return {
        "generated_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "inputs": {
            "remediation_path": _portable_path(remediation_path),
            "field_closure_path": _portable_path(field_closure_path),
            "dockcase_scan": "not_performed",
        },
        "summary": {
            "governance_suppression_packet_count": len(rows),
            "suppression_verified_count": suppression_verified_count,
            "replacement_or_canonical_ready_count": replacement_ready_count,
            "direct_signal_suppressed_count": direct_suppressed_count,
            "peer_context_suppressed_count": peer_context_suppressed_count,
            "requires_governance_review_count": len(rows) - suppression_verified_count,
            "safe_to_upsert_without_review_count": 0,
            "production_write_allowed_count": 0,
            "intent_subtype_counts": dict(sorted(by_subtype.items())),
            "verification_status_counts": dict(sorted(by_status.items())),
            "score_mutation": "none; this audit is read-only and does not alter realtime_current",
        },
        "rows": _json_safe(rows),
    }


def _md_table_row(values: Sequence[Any]) -> str:
    return "| " + " | ".join(str(value) for value in values) + " |"


def render_markdown(report: Mapping[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# A-share governance suppression verification",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- Governance/suppression packets: `{summary['governance_suppression_packet_count']}`",
        f"- Suppression verified: `{summary['suppression_verified_count']}`",
        f"- Replacement/canonical ready: `{summary['replacement_or_canonical_ready_count']}`",
        f"- Direct signal suppressed: `{summary['direct_signal_suppressed_count']}`",
        f"- Peer-context suppressed: `{summary['peer_context_suppressed_count']}`",
        f"- Requires governance review: `{summary['requires_governance_review_count']}`",
        f"- Production writes allowed: `{summary['production_write_allowed_count']}`",
        f"- Score mutation: `{summary['score_mutation']}`",
        "",
        "## Verification Status",
        "",
        "| status | count |",
        "|---|---:|",
    ]
    for status, count in summary["verification_status_counts"].items():
        lines.append(_md_table_row([f"`{status}`", count]))
    lines.extend(
        [
            "",
            "## Rows",
            "",
            "| subtype | dp_id | target | valid ts_codes | replacement/canonical | status |",
            "|---|---|---|---:|---|---|",
        ]
    )
    for row in report["rows"]:
        path = row["replacement_path"]
        replacement = path.get("target_dp_id") or ""
        if path.get("transitive_dp_id"):
            replacement = f"{replacement} -> {path['transitive_dp_id']}"
        lines.append(
            _md_table_row(
                [
                    f"`{row['intent_subtype']}`",
                    f"`{row['dp_id']}`",
                    f"`{row['score_target']}`",
                    row["runtime_valid_real_ts_count"],
                    f"`{replacement}`" if replacement else "",
                    f"`{row['verification_status']}`",
                ]
            )
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- These rows are intentionally not auto-scored by their raw payloads.",
            "- Replacement/canonical-ready rows should be reviewed through their scoring path rather than duplicated.",
            "- Data-only rows remain available as evidence but need sign semantics or a safer replacement before scoring.",
            "",
        ]
    )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--remediation-path", type=Path, default=DEFAULT_REMEDIATION_PATH)
    parser.add_argument("--field-closure-path", type=Path, default=DEFAULT_FIELD_CLOSURE_PATH)
    parser.add_argument("--json-output", type=Path, default=DEFAULT_JSON_OUTPUT)
    parser.add_argument("--md-output", type=Path, default=DEFAULT_MD_OUTPUT)
    parser.add_argument("--no-write", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_report(
        remediation_path=args.remediation_path,
        field_closure_path=args.field_closure_path,
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
