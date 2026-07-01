#!/usr/bin/env python3
"""Materialize validated A-share non-LLM-first fields into stock overlays.

The script reuses ``scripts/compare_llm_vs_non_llm_extractors.py`` as the
candidate source of truth. It is intentionally conservative:

* only fields listed in ``summary.non_llm_first_fields`` are considered;
* only schema-valid available candidates are written;
* ``N/A`` and event ``Inactive`` status-induced invariants are applied;
* every run writes JSON/Markdown audit artifacts with completeness and a
  deterministic sample correctness check.
"""

from __future__ import annotations

import argparse
import copy
import datetime as dt
import hashlib
import json
import math
import sqlite3
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Mapping

import yaml

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mvp20 import schema_validator  # noqa: E402
from mvp20.fingerprint import compute_dependency_fingerprint  # noqa: E402
from scripts import compare_llm_vs_non_llm_extractors as cmp  # noqa: E402


TODAY = dt.date.today().isoformat()
DEFAULT_JSON_OUTPUT = ROOT / "docs" / "audit" / f"{TODAY}_a_share_non_llm_materialization.json"
DEFAULT_MD_OUTPUT = ROOT / "docs" / "audit" / f"{TODAY}_a_share_non_llm_materialization.md"
YAML_LOADER = getattr(yaml, "CSafeLoader", yaml.SafeLoader)
YAML_DUMPER = getattr(yaml, "CSafeDumper", yaml.SafeDumper)
FORMULA_TEXT = (
    "Direction × Event Strength × Transmission Strength × Company Exposure × "
    "Business Share × Profit Sensitivity × Confidence × Time Factor × Surprise × "
    "Funding Amplifier - Priced-in Discount - Risk Discount"
)


def _load_yaml(path: Path) -> dict[str, Any]:
    payload = yaml.load(path.read_text(encoding="utf-8"), Loader=YAML_LOADER)
    return payload if isinstance(payload, dict) else {}


def _write_yaml(path: Path, payload: Mapping[str, Any]) -> None:
    text = yaml.dump(
        dict(payload),
        Dumper=YAML_DUMPER,
        allow_unicode=True,
        sort_keys=False,
        width=10000,
    )
    text = text.replace(
        "formula: Direction × Event Strength × Transmission Strength × Company Exposure × Business Share × Profit Sensitivity ×\n"
        "      Confidence × Time Factor × Surprise × Funding Amplifier - Priced-in Discount - Risk Discount",
        f"formula: {FORMULA_TEXT}",
    )
    path.write_text(text, encoding="utf-8")


def _json_safe(value: Any) -> Any:
    if isinstance(value, (dt.date, dt.datetime)):
        return value.isoformat()
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, Mapping):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_safe(v) for v in value]
    if isinstance(value, tuple):
        return [_json_safe(v) for v in value]
    if isinstance(value, set):
        return sorted(_json_safe(v) for v in value)
    return value


def _canonical(value: Any) -> str:
    return json.dumps(_json_safe(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _short_hash(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()[:16]


def _latest_target_source(root: Path) -> Path:
    candidates = sorted((root / "docs" / "audit").glob("*_a_share_all_stock_llm_vs_non_llm_extractors_summary.json"))
    if candidates:
        return candidates[-1]
    fallback = root / "docs" / "audit" / "2026-06-23_a_share_all_stock_llm_vs_non_llm_extractors_summary.json"
    return fallback


def _load_target_fields(path: Path) -> list[str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    fields = payload.get("summary", {}).get("non_llm_first_fields") or []
    if not isinstance(fields, list) or not fields:
        raise RuntimeError(f"no summary.non_llm_first_fields in {path}")
    return [str(field) for field in fields]


def _available(status: Any) -> bool:
    return cmp._available(status)


def _writeable_unavailable(status: Any) -> bool:
    return str(status or "") in {"Unknown", "Unavailable"}


def _quality_from_confidence(confidence: Any) -> str:
    try:
        value = float(confidence)
    except (TypeError, ValueError):
        value = 0.0
    if value >= 0.75:
        return "high"
    if value >= 0.5:
        return "medium"
    return "low"


def _candidate_fingerprint(
    *,
    ts_code: str,
    dp_id: str,
    candidate: Mapping[str, Any],
    governance_entry: Mapping[str, Any],
    db_path: Path,
) -> str | None:
    deps = list(governance_entry.get("source_dependencies") or [])
    fp = compute_dependency_fingerprint(ts_code, deps, db_path) if deps else None
    if fp:
        return fp
    return _short_hash({
        "dp_id": dp_id,
        "status": candidate.get("data_status"),
        "value": candidate.get("value"),
        "evidence_sources": candidate.get("evidence_sources") or [],
    })


def _candidate_period(candidate: Mapping[str, Any]) -> str | None:
    for ev in candidate.get("evidence_sources") or []:
        if not isinstance(ev, Mapping):
            continue
        excerpt = str(ev.get("excerpt") or "")
        for token in ("2026Q1", "2025", "2024", "2023"):
            if token in excerpt:
                return token
        source = str(ev.get("source") or "")
        if "2025" in source:
            return "2025"
    return None


def _status_patch(
    *,
    node: Mapping[str, Any],
    dp_id: str,
    ts_code: str,
    candidate: Mapping[str, Any],
    governance_entry: Mapping[str, Any],
    db_path: Path,
    now_iso: str,
) -> dict[str, Any]:
    status = str(candidate.get("data_status") or "Unknown")
    reason = candidate.get("reason")
    if status == "N/A":
        missing_reason = reason or "not_applicable"
    elif status in {"Unknown", "Unavailable"}:
        missing_reason = reason or "candidate_unavailable"
    else:
        missing_reason = None
    patch: dict[str, Any] = {
        "status": status,
        "data_status": status,
        "value": candidate.get("value"),
        "confidence": candidate.get("confidence"),
        "evidence_quality": _quality_from_confidence(candidate.get("confidence")),
        "evidence_sources": list(candidate.get("evidence_sources") or []),
        "missing_reason": missing_reason,
        "source_fingerprint_at_fill": _candidate_fingerprint(
            ts_code=ts_code,
            dp_id=dp_id,
            candidate=candidate,
            governance_entry=governance_entry,
            db_path=db_path,
        ),
        "last_filled_period": _candidate_period(candidate),
        "last_event_id": _short_hash(candidate.get("evidence_sources") or candidate.get("value")),
        "last_updated": now_iso,
    }

    if not node.get("data_source"):
        patch["data_source"] = "llm_derived"
    if status == "N/A":
        patch["missing_policy"] = "not_applicable_remove"
        patch["active_weight"] = 0.0
        patch["strength"] = 0.0
    elif status == "Inactive":
        patch["active_weight"] = 0.0
        patch["strength"] = 0.0
        patch["missing_reason"] = None
    elif status not in {"Unknown", "Unavailable"}:
        patch["missing_reason"] = None
    return _json_safe(patch)


def _apply_patch_to_node(node: dict[str, Any], patch: Mapping[str, Any]) -> None:
    for key, value in patch.items():
        node[key] = value


def _validate_patched_node(node: Mapping[str, Any], patch: Mapping[str, Any]) -> list[str]:
    merged = copy.deepcopy(dict(node))
    for key, value in patch.items():
        merged[key] = value
    return schema_validator.validate_overlay_node(merged, strict=True)


def _build_candidates_for_info(
    *,
    info: cmp.OverlayInfo,
    conn: sqlite3.Connection,
    db_path: Path,
    scope: Mapping[str, Any],
    roles: Mapping[str, Mapping[str, Any]],
    peer: Mapping[str, Any],
    target_fields: list[str],
) -> dict[str, dict[str, Any]]:
    script_candidates = cmp._script_fill_candidates(info, db_path)
    return {
        dp_id: cmp._candidate_for(
            dp_id,
            info,
            conn,
            scope,
            roles,
            peer,
            script_candidates,
        )
        for dp_id in target_fields
    }


def materialize(args: argparse.Namespace) -> dict[str, Any]:
    started = time.time()
    root = args.root.resolve()
    db_path = args.db_path.resolve()
    target_source = args.target_field_source.resolve() if args.target_field_source else _latest_target_source(root)
    target_fields = _load_target_fields(target_source)
    target_set = set(target_fields)
    scope = cmp._llm_scope(root, include_cheap_extract=True)
    governance = cmp._load_yaml(root / "config" / "llm_field_governance.yaml").get("data_points") or {}
    roles = cmp._field_roles(root)
    infos = cmp._overlay_infos(root)
    if args.stocks:
        wanted = set(args.stocks)
        infos = [info for info in infos if info.ts_code in wanted]
    if args.limit:
        infos = infos[: args.limit]
    peer_map = cmp._peer_stats(sqlite3.connect(db_path), infos)

    now_iso = dt.datetime.now().astimezone().isoformat(timespec="seconds")
    conn = sqlite3.connect(db_path)

    records: list[dict[str, Any]] = []
    sample_pool: list[dict[str, Any]] = []
    overlay_written = 0

    try:
        for idx, info in enumerate(infos, start=1):
            overlay = _load_yaml(info.path)
            nodes = overlay.get("nodes") or []
            nodes_by_dp = {str(node.get("dp_id")): node for node in nodes if isinstance(node, dict) and node.get("dp_id")}
            candidates = _build_candidates_for_info(
                info=info,
                conn=conn,
                db_path=db_path,
                scope=scope,
                roles=roles,
                peer=peer_map.get(info.ts_code, {}),
                target_fields=target_fields,
            )
            changed = False
            for dp_id in target_fields:
                node = nodes_by_dp.get(dp_id)
                candidate = candidates.get(dp_id) or {}
                record = {
                    "ts_code": info.ts_code,
                    "name": info.name,
                    "industry_id": info.industry_id,
                    "overlay_path": str(info.path.relative_to(root)),
                    "dp_id": dp_id,
                    "previous_status": node.get("data_status") if node else None,
                    "candidate_status": candidate.get("data_status"),
                    "candidate_method": candidate.get("method"),
                    "candidate_quality": candidate.get("quality"),
                    "candidate_reason": candidate.get("reason"),
                    "action": "skipped",
                    "schema_errors": [],
                    "reason": None,
                }
                if node is None:
                    record["reason"] = "target node missing from overlay"
                elif dp_id not in target_set:
                    record["reason"] = "not a target field"
                elif not _available(candidate.get("data_status")) and not (
                    args.write_unavailable and _writeable_unavailable(candidate.get("data_status"))
                ):
                    record["reason"] = candidate.get("reason") or "candidate unavailable"
                else:
                    schema_errors = [] if not _available(candidate.get("data_status")) else cmp._candidate_schema_errors(dp_id, candidate)
                    if schema_errors:
                        record["reason"] = "candidate schema invalid"
                        record["schema_errors"] = schema_errors
                    else:
                        patch = _status_patch(
                            node=node,
                            dp_id=dp_id,
                            ts_code=info.ts_code,
                            candidate=candidate,
                            governance_entry=governance.get(dp_id) or {},
                            db_path=db_path,
                            now_iso=now_iso,
                        )
                        overlay_errors = _validate_patched_node(node, patch)
                        if overlay_errors:
                            record["reason"] = "patched node schema invalid"
                            record["schema_errors"] = overlay_errors
                        else:
                            before = {key: node.get(key) for key in patch}
                            after = dict(patch)
                            if _canonical(before) == _canonical(after):
                                record["action"] = "already_current"
                            else:
                                record["action"] = "would_update" if args.dry_run else "updated"
                                if not args.dry_run:
                                    _apply_patch_to_node(node, patch)
                                    changed = True
                            record["source_fingerprint_at_fill"] = patch.get("source_fingerprint_at_fill")
                            sample_pool.append({
                                "ts_code": info.ts_code,
                                "dp_id": dp_id,
                                "candidate": _json_safe(candidate),
                                "expected_patch": _json_safe(patch),
                                "overlay_path": str(info.path.relative_to(root)),
                            })
                records.append(record)

            if changed:
                _write_yaml(info.path, overlay)
                overlay_written += 1
            if args.progress_every and idx % args.progress_every == 0:
                print(f"processed {idx}/{len(infos)} overlays", file=sys.stderr)
    finally:
        conn.close()

    sample_size = max(1, math.ceil(len(sample_pool) * float(args.sample_rate))) if sample_pool else 0
    sample = sorted(sample_pool, key=lambda item: _short_hash([item["ts_code"], item["dp_id"]]))[:sample_size]
    sample_results: list[dict[str, Any]] = []
    for item in sample:
        info_path = root / item["overlay_path"]
        node = cmp._nodes_by_dp(info_path).get(item["dp_id"]) if info_path.exists() and not args.dry_run else {}
        expected = item["expected_patch"]
        checks = {
            "status_match": True if args.dry_run else node.get("data_status") == expected.get("data_status"),
            "value_match": True if args.dry_run else _canonical(node.get("value")) == _canonical(expected.get("value")),
            "evidence_match": True if args.dry_run else _canonical(node.get("evidence_sources") or []) == _canonical(expected.get("evidence_sources") or []),
            "fingerprint_match": True if args.dry_run else node.get("source_fingerprint_at_fill") == expected.get("source_fingerprint_at_fill"),
            "schema_valid": True if args.dry_run else not schema_validator.validate_overlay_node(node, strict=True),
        }
        sample_results.append({
            "ts_code": item["ts_code"],
            "dp_id": item["dp_id"],
            "overlay_path": item["overlay_path"],
            "checks": checks,
            "passed": all(checks.values()),
        })

    action_counts = Counter(record["action"] for record in records)
    reason_counts = Counter(str(record.get("reason")) for record in records if record.get("reason"))
    unavailable_reason_counts = Counter(
        str(record.get("candidate_reason") or "candidate unavailable")
        for record in records
        if not _available(record.get("candidate_status"))
    )
    status_counts = Counter(str(record.get("candidate_status")) for record in records)
    records_by_field: dict[str, Counter[str]] = defaultdict(Counter)
    for record in records:
        records_by_field[record["dp_id"]][record["action"]] += 1
    summary = {
        "stock_count": len(infos),
        "target_field_count": len(target_fields),
        "target_cell_count": len(infos) * len(target_fields),
        "overlay_written_count": overlay_written,
        "action_counts": dict(action_counts),
        "candidate_status_counts": dict(status_counts),
        "skip_reason_counts": dict(reason_counts),
        "candidate_unavailable_reason_counts": dict(unavailable_reason_counts),
        "candidate_available_count": sum(1 for r in records if _available(r.get("candidate_status"))),
        "candidate_unavailable_count": sum(1 for r in records if not _available(r.get("candidate_status"))),
        "schema_invalid_count": sum(1 for r in records if r.get("schema_errors")),
        "sample_rate": float(args.sample_rate),
        "sample_size": sample_size,
        "sample_passed_count": sum(1 for item in sample_results if item["passed"]),
        "sample_failed_count": sum(1 for item in sample_results if not item["passed"]),
        "elapsed_s": round(time.time() - started, 3),
    }
    return {
        "generated_at": now_iso,
        "dry_run": bool(args.dry_run),
        "inputs": {
            "root": str(root),
            "db_path": str(db_path),
            "target_field_source": str(target_source),
            "stocks": list(args.stocks or []),
            "limit": args.limit,
            "write_unavailable": bool(args.write_unavailable),
        },
        "summary": summary,
        "target_fields": target_fields,
        "by_field_action_counts": {field: dict(counter) for field, counter in sorted(records_by_field.items())},
        "sample_results": sample_results,
        "records": records if args.include_records else [],
    }


def _render_md(report: Mapping[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# A-share non-LLM materialization audit",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- Dry run: `{report['dry_run']}`",
        f"- Stocks: `{summary['stock_count']}`",
        f"- Target fields: `{summary['target_field_count']}`",
        f"- Target cells: `{summary['target_cell_count']}`",
        f"- Candidate available: `{summary['candidate_available_count']}`",
        f"- Candidate unavailable: `{summary['candidate_unavailable_count']}`",
        f"- Write unavailable: `{report['inputs'].get('write_unavailable')}`",
        f"- Schema invalid: `{summary['schema_invalid_count']}`",
        f"- Overlays written: `{summary['overlay_written_count']}`",
        f"- Sample: `{summary['sample_passed_count']}/{summary['sample_size']}` passed",
        "",
        "## Actions",
        "",
        "| action | count |",
        "|---|---:|",
    ]
    for action, count in sorted(summary["action_counts"].items(), key=lambda item: (-item[1], item[0])):
        lines.append(f"| `{action}` | {count} |")
    lines.extend(["", "## Skip Reasons", ""])
    if summary["skip_reason_counts"]:
        lines.extend(["| reason | count |", "|---|---:|"])
        for reason, count in sorted(summary["skip_reason_counts"].items(), key=lambda item: (-item[1], item[0]))[:30]:
            lines.append(f"| `{reason}` | {count} |")
    else:
        lines.append("None.")
    lines.extend(["", "## Candidate Unavailable Reasons", "", "| reason | count |", "|---|---:|"])
    for reason, count in sorted(summary.get("candidate_unavailable_reason_counts", {}).items(), key=lambda item: (-item[1], item[0]))[:30]:
        lines.append(f"| `{reason}` | {count} |")
    lines.extend(["", "## Field Actions", "", "| dp_id | actions |", "|---|---|"])
    for dp_id, counts in report["by_field_action_counts"].items():
        lines.append(f"| `{dp_id}` | `{json.dumps(counts, ensure_ascii=False, sort_keys=True)}` |")
    failed = [item for item in report["sample_results"] if not item["passed"]]
    lines.extend(["", "## 2% Sample Correctness", ""])
    if failed:
        lines.extend(["| ts_code | dp_id | checks |", "|---|---|---|"])
        for item in failed[:50]:
            lines.append(
                f"| `{item['ts_code']}` | `{item['dp_id']}` | "
                f"`{json.dumps(item['checks'], ensure_ascii=False, sort_keys=True)}` |"
            )
    else:
        lines.append("All sampled cells passed status/value/evidence/fingerprint/schema checks.")
    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--db-path", type=Path, default=ROOT / "runtime" / "hot.sqlite")
    parser.add_argument("--target-field-source", type=Path)
    parser.add_argument("--output-json", type=Path, default=DEFAULT_JSON_OUTPUT)
    parser.add_argument("--output-md", type=Path, default=DEFAULT_MD_OUTPUT)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--sample-rate", type=float, default=0.02)
    parser.add_argument("--progress-every", type=int, default=100)
    parser.add_argument("--include-records", action="store_true")
    parser.add_argument(
        "--write-unavailable",
        action="store_true",
        help="Write Unknown/Unavailable candidates with missing_reason instead of skipping them.",
    )
    parser.add_argument("--stocks", nargs="*", default=[])
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = materialize(args)
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.output_md.write_text(_render_md(report), encoding="utf-8")
    print(f"wrote {args.output_json}")
    print(f"wrote {args.output_md}")
    print(json.dumps(report["summary"], ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
