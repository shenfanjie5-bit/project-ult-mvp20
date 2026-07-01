#!/usr/bin/env python3
"""Audit A-share stock overlay LLM target scope.

This is a read-only preflight for Codex/LLM fill runs. It uses the same
governance and refresh predicate as ``scripts/codex_prompt_gen.py`` but
classifies why each governed stock-overlay node would be filled or skipped.

The default is conservative for already-filled content: ``Known`` and
event-driven ``Inactive`` nodes whose only refresh reason is a missing legacy
``source_fingerprint_at_fill`` baseline are preserved for audit instead of
being re-prompted just to establish a baseline. ``Unknown`` nodes previously
filled as ``missing_reason: no_local_evidence`` are also preserved when their
source fingerprint is unchanged.
"""

from __future__ import annotations

import argparse
import datetime as dt
import importlib.util
import json
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mvp20.fingerprint import compute_dependency_fingerprint  # noqa: E402

PROMPT_GEN_PATH = ROOT / "scripts" / "codex_prompt_gen.py"
_SPEC = importlib.util.spec_from_file_location("codex_prompt_gen", PROMPT_GEN_PATH)
assert _SPEC is not None and _SPEC.loader is not None
codex_prompt_gen = importlib.util.module_from_spec(_SPEC)
sys.modules["codex_prompt_gen"] = codex_prompt_gen
_SPEC.loader.exec_module(codex_prompt_gen)

AUDIT_DIR = ROOT / "docs" / "audit"
DEFAULT_JSON_OUTPUT = AUDIT_DIR / f"{dt.date.today().isoformat()}_a_share_llm_target_scope.json"
DEFAULT_MD_OUTPUT = AUDIT_DIR / f"{dt.date.today().isoformat()}_a_share_llm_target_scope.md"
A_SHARE_SUFFIXES = (".SH", ".SZ", ".BJ")
YAML_LOADER = getattr(yaml, "CSafeLoader", yaml.SafeLoader)


def _is_a_share_overlay(path: Path) -> bool:
    return path.name.removesuffix(".yaml").endswith(A_SHARE_SUFFIXES)


def _stock_overlay_paths(root: Path) -> list[Path]:
    return sorted(
        path
        for path in (root / "config" / "stock_overlays").glob("*/*.yaml")
        if _is_a_share_overlay(path)
    )


def _skip_layer(dp_id: str, *, include_l0: bool) -> bool:
    return (not include_l0) and dp_id.startswith("L0.")


def _fillable_reason(node: dict[str, Any], reason: str | None) -> str:
    status = node.get("data_status")
    if reason:
        return reason
    if status == "Unknown":
        return "unknown"
    if status == "Optionality":
        return "empty_optionality"
    return f"fillable_status_{status}"


def _portable(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT))
    except ValueError:
        return str(path)


def _parse_scalar(raw: str) -> Any:
    value = raw.strip()
    if value in {"", "null", "Null", "NULL", "~"}:
        return None
    if (value.startswith("'") and value.endswith("'")) or (
        value.startswith('"') and value.endswith('"')
    ):
        return value[1:-1]
    return value


def _node_blocks(path: Path) -> list[list[str]]:
    blocks: list[list[str]] = []
    current: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("- node_id:"):
            if current:
                blocks.append(current)
            current = [line]
        elif current:
            current.append(line)
    if current:
        blocks.append(current)
    return blocks


def _parse_value_from_block(block: list[str]) -> Any:
    for index, line in enumerate(block):
        if not line.startswith("  value:"):
            continue
        suffix = line.split(":", 1)[1].strip()
        if suffix:
            return _parse_scalar(suffix)
        value_lines: list[str] = []
        for next_line in block[index + 1 :]:
            if next_line.startswith("    ") or not next_line.strip():
                value_lines.append(next_line)
                continue
            break
        if not value_lines:
            return None
        try:
            parsed = yaml.load(
                "value:\n" + "\n".join(value_lines),
                Loader=YAML_LOADER,
            )
        except yaml.YAMLError:
            return {"_parse_error": True}
        if isinstance(parsed, dict):
            return parsed.get("value")
        return None
    return None


def _iter_overlay_nodes(path: Path) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for block in _node_blocks(path):
        node: dict[str, Any] = {}
        for line in block:
            if line.startswith("  dp_id: "):
                node["dp_id"] = line.split(": ", 1)[1].strip()
            elif line.startswith("  data_status: "):
                node["data_status"] = _parse_scalar(line.split(": ", 1)[1])
            elif line.startswith("  missing_reason:"):
                node["missing_reason"] = _parse_scalar(line.split(":", 1)[1])
            elif line.startswith("  source_fingerprint_at_fill:"):
                node["source_fingerprint_at_fill"] = _parse_scalar(
                    line.split(":", 1)[1]
                )
        if node.get("data_status") == "Optionality":
            node["value"] = _parse_value_from_block(block)
        if node.get("dp_id"):
            out.append(node)
    return out


def _overlay_header(path: Path) -> dict[str, str]:
    header: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines()[:30]:
        if line.startswith("ts_code: "):
            header["ts_code"] = line.split(": ", 1)[1].strip()
        elif line.startswith("industry_id: "):
            header["industry_id"] = line.split(": ", 1)[1].strip()
        elif line.startswith("name: "):
            header["name"] = line.split(": ", 1)[1].strip()
    return header


def _optionality_filled(value: Any) -> bool:
    if not isinstance(value, dict) or value is None:
        return False
    has_current = value.get("current_contribution") not in (None, "", {}, [])
    has_future = value.get("future_option_value") not in (None, "", {}, [])
    return bool(has_current or has_future)


def _cached_refresh_reason(
    *,
    ts_code: str,
    node: dict[str, Any],
    entry: dict[str, Any],
    db_path: Path,
    fingerprint_cache: dict[tuple[str, tuple[str, ...]], str | None],
) -> tuple[bool, str]:
    trigger = entry.get("refresh_trigger", "static_picture")
    if trigger == "static_picture":
        return False, "static_picture"
    if trigger == "explicit_refresh":
        return False, "explicit_refresh_only"
    deps = tuple(entry.get("source_dependencies") or [])
    if not deps:
        return False, "no_source_dependencies"
    key = (ts_code, deps)
    if key not in fingerprint_cache:
        fingerprint_cache[key] = compute_dependency_fingerprint(
            ts_code, list(deps), db_path
        )
    current_fp = fingerprint_cache[key]
    if current_fp is None:
        return False, "no_source_data"
    stored_fp = node.get("source_fingerprint_at_fill")
    if stored_fp is None:
        return True, "fingerprint_baseline_missing"
    if current_fp != stored_fp:
        return True, f"source_changed_{trigger}"
    return False, "fingerprint_unchanged"


def _classify_node(
    *,
    ts_code: str,
    node: dict[str, Any],
    entry: dict[str, Any],
    db_path: Path,
    event_driven_dp_ids: frozenset[str],
    refresh_baseline_missing: bool,
    preserve_unknown_no_local_evidence: bool,
    fingerprint_cache: dict[tuple[str, tuple[str, ...]], str | None],
) -> tuple[bool, str | None]:
    dp_id = str(node.get("dp_id") or "")
    status = node.get("data_status")
    if status == "Unknown":
        if (
            preserve_unknown_no_local_evidence
            and node.get("missing_reason") == "no_local_evidence"
        ):
            need_refresh, reason = _cached_refresh_reason(
                ts_code=ts_code,
                node=node,
                entry=entry,
                db_path=db_path,
                fingerprint_cache=fingerprint_cache,
            )
            if need_refresh:
                return True, f"refresh:{reason}"
            return False, f"preserved_unknown_no_local_evidence:{reason}"
        return True, None
    if status == "Optionality":
        if not _optionality_filled(node.get("value")):
            return True, None
        return False, "optionality_already_filled"
    if status == "Inactive":
        is_event_driven = (
            entry.get("refresh_trigger") == "event_driven"
            or dp_id in event_driven_dp_ids
        )
        if not is_event_driven:
            return False, "inactive_static"
        need_refresh, reason = _cached_refresh_reason(
            ts_code=ts_code,
            node=node,
            entry=entry,
            db_path=db_path,
            fingerprint_cache=fingerprint_cache,
        )
        if need_refresh:
            if reason == "fingerprint_baseline_missing" and not refresh_baseline_missing:
                return False, "inactive_event_baseline_missing_preserved"
            return True, f"refresh:{reason}"
        return False, f"inactive_event_no_change:{reason}"
    if status == "Known":
        need_refresh, reason = _cached_refresh_reason(
            ts_code=ts_code,
            node=node,
            entry=entry,
            db_path=db_path,
            fingerprint_cache=fingerprint_cache,
        )
        if need_refresh:
            if reason == "fingerprint_baseline_missing" and not refresh_baseline_missing:
                return False, "preserved_known:fingerprint_baseline_missing"
            return True, f"refresh:{reason}"
        return False, f"preserved_known:{reason}"
    if status == "N/A":
        return False, "preserved_n/a"
    return False, f"unknown_status_{status}"


def build_report(
    *,
    root: Path,
    model_tier: str,
    include_l0: bool,
    refresh_baseline_missing: bool,
    preserve_unknown_no_local_evidence: bool,
    top_n: int,
) -> dict[str, Any]:
    started = time.time()
    governance = codex_prompt_gen.load_governance(root / "config" / "llm_field_governance.yaml")
    gov_points = governance.get("data_points") or {}
    db_path = root / "runtime" / "hot.sqlite"
    triggers = codex_prompt_gen._event_driven_dp_ids()
    fingerprint_cache: dict[tuple[str, tuple[str, ...]], str | None] = {}

    status_counts: Counter[str] = Counter()
    tier_counts: Counter[str] = Counter()
    route_counts: Counter[str] = Counter()
    fillable_reason_counts: Counter[str] = Counter()
    skip_reason_counts: Counter[str] = Counter()
    fillable_status_counts: Counter[str] = Counter()
    fillable_tier_counts: Counter[str] = Counter()
    skip_tier_counts: Counter[str] = Counter()
    per_overlay: list[dict[str, Any]] = []
    examples_by_reason: dict[str, list[dict[str, Any]]] = defaultdict(list)

    paths = _stock_overlay_paths(root)
    governed_node_instances = 0
    fillable_total = 0
    skipped_total = 0

    for path in paths:
        header = _overlay_header(path)
        ts_code = str(header.get("ts_code") or path.name.removesuffix(".yaml"))
        industry_id = str(header.get("industry_id") or path.parent.name)
        name = str(header.get("name") or "")
        overlay_counts: Counter[str] = Counter()
        overlay_fillable: list[dict[str, Any]] = []

        for node in _iter_overlay_nodes(path):
            if not isinstance(node, dict):
                continue
            dp_id = str(node.get("dp_id") or "")
            if _skip_layer(dp_id, include_l0=include_l0):
                continue
            entry = gov_points.get(dp_id)
            if not entry:
                continue
            route = entry.get("route")
            tier = entry.get("model_tier") or "unknown"
            if route not in ("llm_close", "llm_web"):
                continue
            if model_tier != "all" and tier != model_tier:
                continue

            governed_node_instances += 1
            status = str(node.get("data_status"))
            status_counts[status] += 1
            tier_counts[tier] += 1
            route_counts[str(route)] += 1

            ok, reason = _classify_node(
                ts_code=ts_code,
                node=node,
                entry=entry,
                db_path=db_path,
                event_driven_dp_ids=triggers,
                refresh_baseline_missing=refresh_baseline_missing,
                preserve_unknown_no_local_evidence=preserve_unknown_no_local_evidence,
                fingerprint_cache=fingerprint_cache,
            )
            if ok:
                fillable_total += 1
                label = _fillable_reason(node, reason)
                fillable_reason_counts[label] += 1
                fillable_status_counts[status] += 1
                fillable_tier_counts[tier] += 1
                overlay_counts[f"fillable:{label}"] += 1
                row = {
                    "overlay_path": _portable(path),
                    "industry_id": industry_id,
                    "ts_code": ts_code,
                    "name": name,
                    "dp_id": dp_id,
                    "model_tier": tier,
                    "data_status": status,
                    "refresh_trigger": entry.get("refresh_trigger"),
                    "reason": label,
                }
                overlay_fillable.append(row)
                if len(examples_by_reason[label]) < top_n:
                    examples_by_reason[label].append(row)
            else:
                skipped_total += 1
                label = reason or "skipped"
                skip_reason_counts[label] += 1
                skip_tier_counts[tier] += 1
                overlay_counts[f"skip:{label}"] += 1
                if len(examples_by_reason[label]) < top_n:
                    examples_by_reason[label].append(
                        {
                            "overlay_path": _portable(path),
                            "industry_id": industry_id,
                            "ts_code": ts_code,
                            "name": name,
                            "dp_id": dp_id,
                            "model_tier": tier,
                            "data_status": status,
                            "refresh_trigger": entry.get("refresh_trigger"),
                            "reason": label,
                        }
                    )

        if overlay_fillable:
            per_overlay.append(
                {
                    "overlay_path": _portable(path),
                    "industry_id": industry_id,
                    "ts_code": ts_code,
                    "name": name,
                    "fillable_count": len(overlay_fillable),
                    "fillable_by_reason": {
                        key.removeprefix("fillable:"): value
                        for key, value in sorted(overlay_counts.items())
                        if key.startswith("fillable:")
                    },
                    "fillable_nodes": overlay_fillable[:top_n],
                }
            )

    per_overlay.sort(key=lambda row: (-int(row["fillable_count"]), row["overlay_path"]))
    return {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "script": _portable(Path(__file__)),
        "config": {
            "root": str(root),
            "model_tier": model_tier,
            "include_l0": include_l0,
            "refresh_baseline_missing": refresh_baseline_missing,
            "preserve_unknown_no_local_evidence": preserve_unknown_no_local_evidence,
            "db_path": _portable(db_path),
        },
        "summary": {
            "a_share_overlay_files": len(paths),
            "governance_dp_ids": len(gov_points),
            "governed_node_instances": governed_node_instances,
            "fillable_total": fillable_total,
            "skipped_total": skipped_total,
            "duration_seconds": round(time.time() - started, 3),
        },
        "counts": {
            "status_counts": dict(status_counts),
            "tier_counts": dict(tier_counts),
            "route_counts": dict(route_counts),
            "fillable_by_reason": dict(fillable_reason_counts),
            "fillable_by_status": dict(fillable_status_counts),
            "fillable_by_tier": dict(fillable_tier_counts),
            "skipped_by_reason": dict(skip_reason_counts),
            "skipped_by_tier": dict(skip_tier_counts),
        },
        "top_overlays_by_fillable": per_overlay[:top_n],
        "examples_by_reason": {
            reason: rows for reason, rows in sorted(examples_by_reason.items())
        },
    }


def write_markdown(report: dict[str, Any], path: Path) -> None:
    summary = report["summary"]
    counts = report["counts"]
    lines: list[str] = [
        "# A-share LLM target-scope audit",
        "",
        f"- Generated at: `{report['generated_at']}`",
        f"- A-share overlay files: `{summary['a_share_overlay_files']}`",
        f"- Governed node instances: `{summary['governed_node_instances']}`",
        f"- Fillable under current policy: `{summary['fillable_total']}`",
        f"- Skipped under current policy: `{summary['skipped_total']}`",
        f"- Preserve legacy baseline-missing refresh: `{not report['config']['refresh_baseline_missing']}`",
        f"- Preserve no-local-evidence Unknown: `{report['config']['preserve_unknown_no_local_evidence']}`",
        "",
        "## Fillable by reason",
        "",
    ]
    for reason, count in sorted(counts["fillable_by_reason"].items(), key=lambda kv: (-kv[1], kv[0])):
        lines.append(f"- `{reason}`: {count}")
    lines.extend(["", "## Skipped by reason", ""])
    for reason, count in sorted(counts["skipped_by_reason"].items(), key=lambda kv: (-kv[1], kv[0])):
        lines.append(f"- `{reason}`: {count}")
    lines.extend(["", "## Top overlays by fillable count", ""])
    for row in report["top_overlays_by_fillable"][:20]:
        lines.append(
            f"- `{row['overlay_path']}` `{row['ts_code']}` {row['name']}: "
            f"{row['fillable_count']}"
        )
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-tier", default="all", choices=codex_prompt_gen.MODEL_TIER_CHOICES)
    parser.add_argument("--include-l0", action="store_true")
    parser.add_argument(
        "--refresh-baseline-missing",
        action="store_true",
        help="Treat missing source_fingerprint_at_fill as a refresh, matching legacy prompt-gen defaults.",
    )
    parser.add_argument(
        "--refill-unknown-no-local-evidence",
        dest="preserve_unknown_no_local_evidence",
        action="store_false",
        default=True,
        help=(
            "Treat Unknown + missing_reason=no_local_evidence as fillable "
            "even when the source fingerprint is unchanged. By default the "
            "audit preserves these already-audited no-evidence cases."
        ),
    )
    parser.add_argument("--json-output", type=Path, default=DEFAULT_JSON_OUTPUT)
    parser.add_argument("--md-output", type=Path, default=DEFAULT_MD_OUTPUT)
    parser.add_argument("--top-n", type=int, default=50)
    args = parser.parse_args()

    report = build_report(
        root=ROOT,
        model_tier=args.model_tier,
        include_l0=args.include_l0,
        refresh_baseline_missing=args.refresh_baseline_missing,
        preserve_unknown_no_local_evidence=args.preserve_unknown_no_local_evidence,
        top_n=max(1, args.top_n),
    )
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    write_markdown(report, args.md_output)
    print(f"wrote {args.json_output}")
    print(f"wrote {args.md_output}")
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
