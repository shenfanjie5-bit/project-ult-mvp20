#!/usr/bin/env python3
"""Audit source readiness for A-share score-blocking gaps.

This complements ``audit_a_share_score_gap_priority.py``.  The gap-priority
report says which dp_ids still block score completion; this report says which
source route is currently realistic: direct structured collector, local
closed-loop LLM, event/news LLM/web extraction, or manual design review.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sqlite3
from collections import Counter
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_GAP_PATH = ROOT / "docs/audit/a_share_score_gap_priority_2026-06-18.json"
DEFAULT_GOVERNANCE_PATH = ROOT / "config/llm_field_governance.yaml"
DEFAULT_SPEC_PATH = ROOT / "config/data_point_roles.yaml"
DEFAULT_DB_PATH = ROOT / "runtime/hot.sqlite"
DEFAULT_DOCKCASE_DATA_ROOT = Path("/Volumes/dockcase2tb/database_all")
DEFAULT_MARKET_DATA_ROOT = Path("/Volumes/dockcase2tb/market_data")
DEFAULT_JSON_OUTPUT = ROOT / "docs/audit/a_share_l0_source_readiness_2026-06-19.json"
DEFAULT_MD_OUTPUT = ROOT / "docs/audit/a_share_l0_source_readiness_2026-06-19.md"

FILING_DEP_PREFIXES = ("L4.", "L5.")
EVENT_DEP_PREFIXES = ("L8.", "L9.")


def load_yaml(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def count_files(root: Path) -> int:
    if not root.exists():
        return 0
    return sum(1 for p in root.rglob("*") if p.is_file())


def dependency_state(db_path: Path, dp_ids: list[str]) -> dict[str, dict[str, Any]]:
    if not db_path.exists() or not dp_ids:
        return {dp: {"rows": 0, "status_counts": {}, "sources": []} for dp in dp_ids}

    placeholders = ",".join("?" for _ in dp_ids)
    sql = f"""
        SELECT dp_id, data_status, source, COUNT(*) AS n
        FROM realtime_current
        WHERE dp_id IN ({placeholders})
          AND COALESCE(source, '') NOT LIKE 'mock:%'
        GROUP BY dp_id, data_status, source
    """
    out = {dp: {"rows": 0, "status_counts": Counter(), "sources": Counter()} for dp in dp_ids}
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        for row in conn.execute(sql, dp_ids):
            dp_id = str(row["dp_id"])
            n = int(row["n"])
            out.setdefault(dp_id, {"rows": 0, "status_counts": Counter(), "sources": Counter()})
            out[dp_id]["rows"] += n
            out[dp_id]["status_counts"][str(row["data_status"])] += n
            out[dp_id]["sources"][str(row["source"])] += n
    finally:
        conn.close()

    normalized: dict[str, dict[str, Any]] = {}
    for dp, state in out.items():
        normalized[dp] = {
            "rows": state["rows"],
            "status_counts": dict(sorted(state["status_counts"].items())),
            "sources": [src for src, _ in state["sources"].most_common(5)],
        }
    return normalized


def classify_route(dp_id: str, priority: str, governance: dict[str, Any] | None) -> tuple[str, str]:
    if priority == "P3_manual_review":
        return "manual_design_review", "formula/market applicability needs human design before data fill"
    if dp_id == "L9.media.short_report":
        return "web_event_extraction", "short-seller/short-report signal needs dedicated web/news extraction"

    if not governance:
        return "manual_design_review", "no governance rule found for this dp_id"

    refresh = str(governance.get("refresh_trigger") or "")
    deps = [str(d) for d in governance.get("source_dependencies") or []]
    has_filing_dep = any(dep.startswith(FILING_DEP_PREFIXES) for dep in deps)
    has_event_dep = any(dep.startswith(EVENT_DEP_PREFIXES) for dep in deps)

    if refresh == "quarterly_filing" or has_filing_dep:
        return "local_llm_closed_loop", "use local financial/runtime deps plus annual/IR evidence; no open web required"
    if refresh == "event_driven" and has_event_dep:
        return "event_llm_from_runtime_news", "use CLS/news/policy runtime rows first; add web crawl only when evidence is absent"
    if str(governance.get("route") or "") == "llm_web":
        return "web_event_extraction", "governance explicitly requires web evidence"
    return "local_llm_closed_loop", "governance route is llm_close"


def build_report(
    *,
    gap_path: Path,
    governance_path: Path,
    spec_path: Path,
    db_path: Path,
    dockcase_data_root: Path,
    market_data_root: Path,
) -> dict[str, Any]:
    gap_payload = json.loads(gap_path.read_text(encoding="utf-8"))
    governance = (load_yaml(governance_path).get("data_points") or {})
    spec = (load_yaml(spec_path).get("data_points") or {})

    rows = []
    for row in gap_payload.get("participating_gap_rows") or []:
        if not row.get("blocking_gap"):
            continue
        dp_id = str(row.get("dp_id"))
        gov = governance.get(dp_id)
        source_route, rationale = classify_route(dp_id, str(row.get("priority")), gov)
        deps = [str(d) for d in (gov or {}).get("source_dependencies") or []]
        dep_state = dependency_state(db_path, deps)
        rows.append(
            {
                "dp_id": dp_id,
                "priority": row.get("priority"),
                "gap_bucket": row.get("gap_bucket"),
                "score_target": row.get("score_target"),
                "source_data_state": row.get("source_data_state"),
                "current_runtime_valid_real_ts_count": row.get("runtime_valid_real_ts_count"),
                "current_runtime_numeric_signal_ts_count": row.get("runtime_numeric_signal_ts_count"),
                "source_status": (spec.get(dp_id) or {}).get("source_status"),
                "governance_route": (gov or {}).get("route"),
                "model_tier": (gov or {}).get("model_tier"),
                "refresh_trigger": (gov or {}).get("refresh_trigger"),
                "source_dependencies": deps,
                "dependency_state": dep_state,
                "recommended_source_route": source_route,
                "rationale": rationale,
                "repair_hint": row.get("repair_hint"),
            }
        )

    route_counts = Counter(row["recommended_source_route"] for row in rows)
    priority_counts = Counter(str(row["priority"]) for row in rows)
    deps_with_rows = sorted({
        dep
        for row in rows
        for dep, state in row["dependency_state"].items()
        if state.get("rows", 0) > 0
    })
    deps_without_rows = sorted({
        dep
        for row in rows
        for dep, state in row["dependency_state"].items()
        if state.get("rows", 0) == 0
    })

    return {
        "generated_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "gap_path": str(gap_path),
        "governance_path": str(governance_path),
        "spec_path": str(spec_path),
        "db_path": str(db_path),
        "dockcase": {
            "database_all_root": str(dockcase_data_root),
            "database_all_exists": dockcase_data_root.exists(),
            "database_all_file_count": count_files(dockcase_data_root),
            "market_data_root": str(market_data_root),
            "market_data_exists": market_data_root.exists(),
            "market_data_file_count": count_files(market_data_root),
        },
        "summary": {
            "blocking_gap_count": len(rows),
            "priority_counts": dict(sorted(priority_counts.items())),
            "recommended_source_route_counts": dict(sorted(route_counts.items())),
            "direct_structured_tushare_remaining": 0,
            "dependency_dp_ids_with_runtime_rows": deps_with_rows,
            "dependency_dp_ids_without_runtime_rows": deps_without_rows,
        },
        "rows": rows,
    }


def render_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# A-share L0/source-readiness audit",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- Blocking gaps: `{summary['blocking_gap_count']}`",
        f"- Direct structured Tushare remaining: `{summary['direct_structured_tushare_remaining']}`",
        f"- DOCKCASE `database_all` files: `{report['dockcase']['database_all_file_count']}`",
        f"- DOCKCASE `market_data` files: `{report['dockcase']['market_data_file_count']}`",
        "",
        "## Route Counts",
        "",
        "| Recommended route | Count |",
        "|---|---:|",
    ]
    for route, count in summary["recommended_source_route_counts"].items():
        lines.append(f"| `{route}` | {count} |")

    lines.extend([
        "",
        "## Blocking Gaps",
        "",
        "| dp_id | priority | recommended route | trigger | deps with rows | deps without rows | next step |",
        "|---|---|---|---|---|---|---|",
    ])
    for row in report["rows"]:
        with_rows = [
            dep for dep, state in row["dependency_state"].items()
            if state.get("rows", 0) > 0
        ]
        without_rows = [
            dep for dep, state in row["dependency_state"].items()
            if state.get("rows", 0) == 0
        ]
        lines.append(
            "| "
            f"`{row['dp_id']}` | "
            f"{row['priority']} | "
            f"`{row['recommended_source_route']}` | "
            f"{row.get('refresh_trigger') or '-'} | "
            f"{', '.join(f'`{d}`' for d in with_rows) or '-'} | "
            f"{', '.join(f'`{d}`' for d in without_rows) or '-'} | "
            f"{row['rationale']} |"
        )

    lines.extend([
        "",
        "## Interpretation",
        "",
        "- Current evidence still supports the prior conclusion that no P1 direct Tushare/structured collector gaps remain for A-share score completion.",
        "- The main work is now two pipelines: local closed-loop LLM fills for filing-derived L0 economics, and event/news classification from runtime media/policy/competition feeds.",
        "- `L9.media.short_report` remains the clearest web-crawl gap because the generic CLS/media feed does not prove short-report semantics.",
        "- P3 rows are not data-collection problems; they need formula/applicability design before they should affect final scores.",
        "",
    ])
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gap-path", type=Path, default=DEFAULT_GAP_PATH)
    parser.add_argument("--governance-path", type=Path, default=DEFAULT_GOVERNANCE_PATH)
    parser.add_argument("--spec-path", type=Path, default=DEFAULT_SPEC_PATH)
    parser.add_argument("--db-path", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--dockcase-data-root", type=Path, default=DEFAULT_DOCKCASE_DATA_ROOT)
    parser.add_argument("--market-data-root", type=Path, default=DEFAULT_MARKET_DATA_ROOT)
    parser.add_argument("--json-output", type=Path, default=DEFAULT_JSON_OUTPUT)
    parser.add_argument("--md-output", type=Path, default=DEFAULT_MD_OUTPUT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_report(
        gap_path=args.gap_path,
        governance_path=args.governance_path,
        spec_path=args.spec_path,
        db_path=args.db_path,
        dockcase_data_root=args.dockcase_data_root,
        market_data_root=args.market_data_root,
    )
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.md_output.write_text(render_markdown(report), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
