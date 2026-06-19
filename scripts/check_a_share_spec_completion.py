#!/usr/bin/env python3
"""A-share spec-field completion audit.

This report answers a narrower question than the global spec-drift checker:
for the checked-in A-share universe, which of the canonical spec dp_ids are
already handled by the hot SQLite layer and/or compiled stock overlays.
It is a handled/completion audit; use ``audit_a_share_score_trace.py`` when
you need proof that valid information becomes a numeric signal and reaches
``final_score``.

Inputs:
1. config/data_point_roles.yaml — the canonical spec dp_ids.
2. runtime/hot.sqlite realtime_current — hard data / derived emits.
3. runtime/hot.sqlite company_node_instance — compiled overlay authoring state.
4. docs/data_sources/coverage_audit.md — optional labels for human-readable
   report rows.

Output:
docs/audit/a_share_spec_completion.md + .json
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

A_SHARE_SUFFIXES = (".SH", ".SZ", ".BJ")
SQLITE_HANDLED_STATUSES = {"Known", "Proxy", "Inactive", "Optionality"}
OVERLAY_HANDLED_STATUSES = {"Known", "Inactive", "Optionality", "LowMateriality"}


def is_a_share(ts_code: str | None) -> bool:
    if not ts_code:
        return False
    return str(ts_code).upper().endswith(A_SHARE_SUFFIXES)


def layer_of(dp_id: str) -> str:
    return dp_id.split(".", 1)[0] if "." in dp_id else dp_id


def layer_sort_key(layer: str) -> tuple[int, str]:
    match = re.fullmatch(r"L(\d+)", layer)
    if match:
        return int(match.group(1)), layer
    return 999, layer


def is_mock_source(source: str | None) -> bool:
    return str(source or "").lower().startswith("mock:")


def load_spec(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    data_points = payload.get("data_points") or {}
    return {str(k): dict(v or {}) for k, v in data_points.items()}


def load_coverage_labels(path: Path) -> dict[str, dict[str, str]]:
    """Parse coverage_audit.md section 7 table for labels and source summary."""

    if not path.exists():
        return {}
    labels: dict[str, dict[str, str]] = {}
    in_section = False
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("## 7."):
            in_section = True
            continue
        if in_section and line.startswith("## "):
            break
        if not in_section or not line.startswith("| `"):
            continue
        cols = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cols) < 9:
            continue
        dp_match = re.fullmatch(r"`([^`]+)`", cols[0])
        if not dp_match:
            continue
        labels[dp_match.group(1)] = {
            "layer": cols[1],
            "label": cols[2],
            "coverage_summary": cols[8],
        }
    return labels


def _fetch_rows(db_path: Path, sql: str) -> list[sqlite3.Row]:
    if not db_path.exists():
        return []
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        return conn.execute(sql).fetchall()
    except sqlite3.Error:
        return []
    finally:
        conn.close()


def load_a_share_universe(db_path: Path) -> list[str]:
    """Return A-share ts_codes known to hot.sqlite.

    Use the union of realtime rows, overlay manifest, and compiled overlay
    nodes so sentinel-only market/industry rows still fan out through every
    checked-in A-share constituent.
    """

    rows = _fetch_rows(
        db_path,
        """
        SELECT DISTINCT ts_code
        FROM (
            SELECT ts_code FROM realtime_current
            UNION
            SELECT ts_code FROM overlay_manifest
            UNION
            SELECT ts_code FROM company_node_instance
        )
        WHERE ts_code LIKE '%.SH'
           OR ts_code LIKE '%.SZ'
           OR ts_code LIKE '%.BJ'
        ORDER BY ts_code
        """,
    )
    return [str(r["ts_code"]) for r in rows]


def load_a_share_realtime(db_path: Path) -> list[sqlite3.Row]:
    return _fetch_rows(
        db_path,
        """
        SELECT ts_code, dp_id, data_status, source
        FROM realtime_current
        WHERE ts_code LIKE '%.SH'
           OR ts_code LIKE '%.SZ'
           OR ts_code LIKE '%.BJ'
        """,
    )


def collect_effective_realtime(
    db_path: Path,
    ts_codes: list[str],
    spec_dps: set[str],
) -> tuple[dict[str, dict[str, Any]], Counter[str]]:
    """Collect per-stock effective snapshots using storage merge semantics."""

    if not db_path.exists():
        return {}, Counter()

    try:
        from mvp20.storage import read_hot_snapshot
    except Exception:  # noqa: BLE001 - audit should degrade to direct SQL.
        return {}, Counter()

    by_dp: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "ts_codes": set(),
            "real_ts_codes": set(),
            "origins": set(),
            "real_origins": set(),
            "statuses": set(),
            "real_statuses": set(),
            "sources": set(),
            "real_sources": set(),
            "entries": 0,
            "real_entries": 0,
        }
    )
    status_counts: Counter[str] = Counter()
    for ts_code in ts_codes:
        snapshot = read_hot_snapshot(db_path, ts_code)
        for dp_id, entry in (snapshot or {}).items():
            if dp_id not in spec_dps:
                continue
            status = str((entry or {}).get("data_status"))
            source = str((entry or {}).get("source"))
            origin = str((entry or {}).get("_origin_ts_code") or ts_code)
            status_counts[status] += 1
            bucket = by_dp[dp_id]
            bucket["ts_codes"].add(ts_code)
            bucket["origins"].add(origin)
            bucket["statuses"].add(status)
            bucket["sources"].add(source)
            bucket["entries"] += 1
            if not is_mock_source(source):
                bucket["real_ts_codes"].add(ts_code)
                bucket["real_origins"].add(origin)
                bucket["real_statuses"].add(status)
                bucket["real_sources"].add(source)
                bucket["real_entries"] += 1
    return by_dp, status_counts


def load_a_share_overlay_nodes(db_path: Path) -> list[sqlite3.Row]:
    return _fetch_rows(
        db_path,
        """
        SELECT ts_code, industry_id, dp_id, data_status
        FROM company_node_instance
        WHERE dp_id IS NOT NULL
          AND (
            ts_code LIKE '%.SH'
            OR ts_code LIKE '%.SZ'
            OR ts_code LIKE '%.BJ'
          )
        """,
    )


def _dp_detail(
    dp_id: str,
    spec_entry: dict[str, Any],
    labels: dict[str, dict[str, str]],
) -> dict[str, Any]:
    label = labels.get(dp_id) or {}
    return {
        "dp_id": dp_id,
        "layer": label.get("layer") or layer_of(dp_id),
        "label": label.get("label") or "",
        "source_status": spec_entry.get("source_status"),
        "coverage_summary": label.get("coverage_summary") or "",
    }


def build_completion_report(
    *,
    spec: dict[str, dict[str, Any]],
    db_path: Path,
    labels: dict[str, dict[str, str]] | None = None,
) -> dict[str, Any]:
    labels = labels or {}
    spec_dps = set(spec)
    a_share_ts_codes = load_a_share_universe(db_path)
    realtime_rows = load_a_share_realtime(db_path)
    overlay_rows = load_a_share_overlay_nodes(db_path)
    effective_by_dp, effective_status_counts = collect_effective_realtime(
        db_path,
        a_share_ts_codes,
        spec_dps,
    )

    realtime_ts_codes = {str(r["ts_code"]) for r in realtime_rows}
    realtime_by_status = Counter(str(r["data_status"]) for r in realtime_rows)
    realtime_by_dp: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"ts_codes": set(), "statuses": set(), "sources": set(), "rows": 0}
    )
    hard_handled: set[str] = set()
    hard_real_handled: set[str] = set()
    hard_emitted: set[str] = set()
    for row in realtime_rows:
        dp_id = str(row["dp_id"])
        if dp_id not in spec_dps:
            continue
        hard_emitted.add(dp_id)
        bucket = realtime_by_dp[dp_id]
        bucket["ts_codes"].add(str(row["ts_code"]))
        bucket["statuses"].add(str(row["data_status"]))
        bucket["sources"].add(str(row["source"]))
        bucket["rows"] += 1
        if str(row["data_status"]) in SQLITE_HANDLED_STATUSES:
            hard_handled.add(dp_id)
            if not is_mock_source(str(row["source"])):
                hard_real_handled.add(dp_id)

    overlay_pairs = {(str(r["ts_code"]), str(r["industry_id"])) for r in overlay_rows}
    overlay_by_status = Counter(str(r["data_status"]) for r in overlay_rows)
    overlay_by_dp: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"ts_codes": set(), "industry_pairs": set(), "statuses": set(), "rows": 0}
    )
    overlay_present: set[str] = set()
    overlay_handled: set[str] = set()
    for row in overlay_rows:
        dp_id = str(row["dp_id"])
        if dp_id not in spec_dps:
            continue
        overlay_present.add(dp_id)
        bucket = overlay_by_dp[dp_id]
        ts_code = str(row["ts_code"])
        industry_id = str(row["industry_id"])
        bucket["ts_codes"].add(ts_code)
        bucket["industry_pairs"].add((ts_code, industry_id))
        bucket["statuses"].add(str(row["data_status"]))
        bucket["rows"] += 1
        if str(row["data_status"]) in OVERLAY_HANDLED_STATUSES:
            overlay_handled.add(dp_id)

    effective_handled = {
        dp_id for dp_id, bucket in effective_by_dp.items()
        if bucket["statuses"] & SQLITE_HANDLED_STATUSES
    }
    effective_real_handled = {
        dp_id for dp_id, bucket in effective_by_dp.items()
        if bucket["real_statuses"] & SQLITE_HANDLED_STATUSES
    }
    effective_mock_only = effective_handled - effective_real_handled
    combined_direct = hard_handled | overlay_handled
    combined = effective_real_handled | overlay_handled
    gaps = spec_dps - combined

    by_layer: dict[str, dict[str, Any]] = {}
    for dp_id in sorted(spec_dps):
        layer = layer_of(dp_id)
        row = by_layer.setdefault(
            layer,
            {
                "total": 0,
                "hard_handled": 0,
                "hard_real_handled": 0,
                "effective_real_handled": 0,
                "overlay_handled": 0,
                "combined_handled": 0,
                "gap": 0,
            },
        )
        row["total"] += 1
        if dp_id in hard_handled:
            row["hard_handled"] += 1
        if dp_id in hard_real_handled:
            row["hard_real_handled"] += 1
        if dp_id in effective_real_handled:
            row["effective_real_handled"] += 1
        if dp_id in overlay_handled:
            row["overlay_handled"] += 1
        if dp_id in combined:
            row["combined_handled"] += 1
        else:
            row["gap"] += 1

    def details(dp_ids: set[str] | list[str]) -> list[dict[str, Any]]:
        out = []
        for dp_id in sorted(dp_ids):
            item = _dp_detail(dp_id, spec[dp_id], labels)
            if dp_id in realtime_by_dp:
                rt = realtime_by_dp[dp_id]
                item["a_realtime_ts_count"] = len(rt["ts_codes"])
                item["a_realtime_statuses"] = sorted(rt["statuses"])
                item["a_realtime_sources"] = sorted(rt["sources"])
            if dp_id in effective_by_dp:
                eff = effective_by_dp[dp_id]
                item["a_effective_ts_count"] = len(eff["ts_codes"])
                item["a_effective_real_ts_count"] = len(eff["real_ts_codes"])
                item["a_effective_origins"] = sorted(eff["origins"])
                item["a_effective_statuses"] = sorted(eff["statuses"])
                item["a_effective_sources"] = sorted(eff["sources"])
                item["a_effective_real_sources"] = sorted(eff["real_sources"])
            if dp_id in overlay_by_dp:
                ov = overlay_by_dp[dp_id]
                item["a_overlay_ts_count"] = len(ov["ts_codes"])
                item["a_overlay_pair_count"] = len(ov["industry_pairs"])
                item["a_overlay_statuses"] = sorted(ov["statuses"])
            out.append(item)
        return out

    premium_but_a_hard = {
        dp for dp, entry in spec.items()
        if entry.get("source_status") == "$" and dp in effective_real_handled
    }
    missing_but_a_hard = {
        dp for dp, entry in spec.items()
        if entry.get("source_status") == "missing" and dp in effective_real_handled
    }
    missing_but_a_overlay = {
        dp for dp, entry in spec.items()
        if entry.get("source_status") == "missing"
        and dp not in effective_real_handled
        and dp in overlay_handled
    }
    full_but_absent_on_a = {
        dp for dp, entry in spec.items()
        if entry.get("source_status") == "✓" and dp not in combined
    }

    source_status_counts = Counter(str(v.get("source_status")) for v in spec.values())
    spec_total = len(spec_dps)
    return {
        "generated_at": dt.date.today().isoformat(),
        "market": "A-share",
        "db_path": str(db_path),
        "spec_total": spec_total,
        "source_status_counts": dict(sorted(source_status_counts.items())),
        "a_share_realtime": {
            "rows": len(realtime_rows),
            "ts_codes": len(realtime_ts_codes),
            "spec_dp_emitted": len(hard_emitted),
            "spec_dp_handled": len(hard_handled),
            "spec_dp_real_handled": len(hard_real_handled),
            "handled_pct": _pct(len(hard_handled), spec_total),
            "real_handled_pct": _pct(len(hard_real_handled), spec_total),
            "data_status_counts": dict(sorted(realtime_by_status.items())),
        },
        "a_share_effective_realtime": {
            "ts_codes": len(a_share_ts_codes),
            "spec_dp_handled_including_mock": len(effective_handled),
            "spec_dp_real_handled": len(effective_real_handled),
            "spec_dp_mock_only": len(effective_mock_only),
            "handled_including_mock_pct": _pct(len(effective_handled), spec_total),
            "real_handled_pct": _pct(len(effective_real_handled), spec_total),
            "snapshot_entry_count": sum(b["entries"] for b in effective_by_dp.values()),
            "real_snapshot_entry_count": sum(b["real_entries"] for b in effective_by_dp.values()),
            "data_status_counts": dict(sorted(effective_status_counts.items())),
        },
        "a_share_overlay": {
            "rows": len(overlay_rows),
            "ts_industry_pairs": len(overlay_pairs),
            "spec_dp_present": len(overlay_present),
            "spec_dp_handled": len(overlay_handled),
            "handled_pct": _pct(len(overlay_handled), spec_total),
            "data_status_counts": dict(sorted(overlay_by_status.items())),
        },
        "combined_direct_sqlite_overlay": {
            "spec_dp_handled": len(combined_direct),
            "completion_pct": _pct(len(combined_direct), spec_total),
            "gap_count": spec_total - len(combined_direct),
        },
        "combined": {
            "spec_dp_handled": len(combined),
            "completion_pct": _pct(len(combined), spec_total),
            "gap_count": len(gaps),
            "basis": "effective realtime snapshots excluding mock sources + compiled overlays",
        },
        "by_layer": {
            layer: {
                **row,
                "combined_pct": _pct(row["combined_handled"], row["total"]),
            }
            for layer, row in sorted(by_layer.items(), key=lambda item: layer_sort_key(item[0]))
        },
        "flags": {
            "premium_but_a_share_hard_data": details(premium_but_a_hard),
            "missing_but_a_share_hard_data": details(missing_but_a_hard),
            "missing_but_a_share_overlay_handled": details(missing_but_a_overlay),
            "full_source_status_but_absent_on_a_share": details(full_but_absent_on_a),
            "mock_only_effective_realtime": details(effective_mock_only),
        },
        "gaps": details(gaps),
        "hard_handled_dp_ids": sorted(hard_handled),
        "hard_real_handled_dp_ids": sorted(hard_real_handled),
        "effective_handled_including_mock_dp_ids": sorted(effective_handled),
        "effective_real_handled_dp_ids": sorted(effective_real_handled),
        "effective_mock_only_dp_ids": sorted(effective_mock_only),
        "overlay_handled_dp_ids": sorted(overlay_handled),
        "combined_handled_dp_ids": sorted(combined),
    }


def _pct(num: int, den: int) -> float:
    if den <= 0:
        return 0.0
    return round(num / den, 4)


def render_markdown(report: dict[str, Any]) -> str:
    rt = report["a_share_realtime"]
    eff = report["a_share_effective_realtime"]
    ov = report["a_share_overlay"]
    combined = report["combined"]
    direct_combined = report["combined_direct_sqlite_overlay"]

    lines = [
        "# A-share spec field completion",
        "",
        f"Generated by `scripts/check_a_share_spec_completion.py` on {report['generated_at']}.",
        "",
        "## Summary",
        "",
        "| scope | handled spec dp_ids | denominator | pct | notes |",
        "|---|---:|---:|---:|---|",
        (
            f"| SQLite hard/derived A-share rows | {rt['spec_dp_handled']} | "
            f"{report['spec_total']} | {rt['handled_pct']:.1%} | "
            f"direct rows only; {rt['spec_dp_real_handled']} real-source dp_ids after mock exclusion |"
        ),
        (
            f"| Effective runtime snapshots, real sources | {eff['spec_dp_real_handled']} | "
            f"{report['spec_total']} | {eff['real_handled_pct']:.1%} | "
            f"{eff['ts_codes']} A-share ts_codes with MARKET/INDUSTRY sentinels; "
            f"{eff['spec_dp_mock_only']} mock-only dp_ids excluded |"
        ),
        (
            f"| Compiled A-share overlays | {ov['spec_dp_handled']} | "
            f"{report['spec_total']} | {ov['handled_pct']:.1%} | "
                f"{ov['ts_industry_pairs']} ts_code-industry pairs, {ov['rows']} nodes |"
        ),
        (
            f"| Direct SQL + overlays (legacy diagnostic) | {direct_combined['spec_dp_handled']} | "
            f"{report['spec_total']} | {direct_combined['completion_pct']:.1%} | "
            "kept for drift comparison; does not fan out sentinels |"
        ),
        (
            f"| Combined real A-share handled fields | {combined['spec_dp_handled']} | "
            f"{report['spec_total']} | {combined['completion_pct']:.1%} | "
            f"{combined['gap_count']} spec dp_ids still not handled by real runtime or overlay |"
        ),
        "",
        "Handled means: SQLite status in `Known/Proxy/Inactive/Optionality`, or "
        "compiled overlay status in `Known/Inactive/Optionality/LowMateriality`.",
        "The headline combined row uses `read_hot_snapshot`, so `MARKET:CN` and "
        "`INDUSTRY:*` sentinel rows are counted exactly as runtime consumers see them.",
        "Rows whose source starts with `mock:` are listed separately and excluded "
        "from the real-source numerator.",
        "",
        "## By Layer",
        "",
        "| layer | total | direct hard | direct real | effective real | overlay | combined | gap | combined pct |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for layer, row in report["by_layer"].items():
        lines.append(
            f"| {layer} | {row['total']} | {row['hard_handled']} | "
            f"{row['hard_real_handled']} | {row['effective_real_handled']} | "
            f"{row['overlay_handled']} | {row['combined_handled']} | "
            f"{row['gap']} | {row['combined_pct']:.1%} |"
        )

    lines.extend(
        [
            "",
            "## Spec Label Follow-Ups",
            "",
            "| check | count | meaning |",
            "|---|---:|---|",
            (
                "| `$` but A-share hard data exists | "
                f"{len(report['flags']['premium_but_a_share_hard_data'])} | "
                "The global premium label is too coarse for A-share; Tushare/AKShare already handles these. |"
            ),
            (
                "| `missing` but A-share hard data exists | "
                f"{len(report['flags']['missing_but_a_share_hard_data'])} | "
                "A-share has rows, but mock/Inactive sources may need review before source_status promotion. |"
            ),
            (
                "| `missing` but A-share overlay handles it | "
                f"{len(report['flags']['missing_but_a_share_overlay_handled'])} | "
                "Not hard-source coverage; treated as LLM/human overlay completion. |"
            ),
            (
                "| mock-only effective runtime rows | "
                f"{len(report['flags']['mock_only_effective_realtime'])} | "
                "Runtime can expose these fields, but current checked-in data still uses mock sources. |"
            ),
            (
                "| `✓` but absent on A-share | "
                f"{len(report['flags']['full_source_status_but_absent_on_a_share'])} | "
                "Spec says full source coverage, but A-share snapshot/overlay does not currently expose it. |"
            ),
            "",
        ]
    )

    _append_detail_table(
        lines,
        "### `$` but A-share hard data exists",
        report["flags"]["premium_but_a_share_hard_data"],
        max_rows=50,
    )
    _append_detail_table(
        lines,
        "### `missing` but A-share hard data exists",
        report["flags"]["missing_but_a_share_hard_data"],
        max_rows=50,
    )
    _append_detail_table(
        lines,
        "### Mock-only effective runtime rows",
        report["flags"]["mock_only_effective_realtime"],
        max_rows=50,
    )
    _append_detail_table(
        lines,
        "### `✓` but absent on A-share",
        report["flags"]["full_source_status_but_absent_on_a_share"],
        max_rows=50,
    )
    _append_detail_table(
        lines,
        "## Remaining A-share Gaps",
        report["gaps"],
        max_rows=120,
    )

    return "\n".join(lines) + "\n"


def _append_detail_table(
    lines: list[str],
    title: str,
    rows: list[dict[str, Any]],
    *,
    max_rows: int,
) -> None:
    lines.extend([title, "", "| dp_id | layer | label | source_status | A-share evidence |", "|---|---|---|---|---|"])
    for row in rows[:max_rows]:
        evidence: list[str] = []
        if row.get("a_realtime_ts_count"):
            sources = _format_values(row.get("a_realtime_sources") or [])
            statuses = _format_values(row.get("a_realtime_statuses") or [])
            evidence.append(f"direct SQL {row['a_realtime_ts_count']} ts_codes ({statuses}; {sources})")
        if row.get("a_effective_ts_count"):
            sources = _format_values(
                row.get("a_effective_real_sources") or row.get("a_effective_sources") or []
            )
            statuses = _format_values(row.get("a_effective_statuses") or [])
            origins = _format_values(row.get("a_effective_origins") or [])
            evidence.append(
                f"effective {row['a_effective_ts_count']} ts_codes "
                f"({statuses}; {sources}; origin {origins})"
            )
        if row.get("a_overlay_pair_count"):
            statuses = _format_values(row.get("a_overlay_statuses") or [])
            evidence.append(f"overlay {row['a_overlay_pair_count']} pairs ({statuses})")
        lines.append(
            f"| `{row['dp_id']}` | {row['layer']} | {row.get('label') or ''} | "
            f"{row.get('source_status') or ''} | {'; '.join(evidence) or '-'} |"
        )
    if len(rows) > max_rows:
        lines.append(f"| ... | | | | +{len(rows) - max_rows} more |")
    if not rows:
        lines.append("| - | - | - | - | - |")
    lines.append("")


def _format_values(values: list[str], *, max_items: int = 6) -> str:
    text_values = [str(v) for v in values]
    if len(text_values) <= max_items:
        return ", ".join(text_values)
    shown = ", ".join(text_values[:max_items])
    return f"{shown}, +{len(text_values) - max_items} more"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", type=Path, default=ROOT / "config/data_point_roles.yaml")
    parser.add_argument("--db", type=Path, default=ROOT / "runtime/hot.sqlite")
    parser.add_argument(
        "--coverage-audit",
        type=Path,
        default=ROOT / "docs/data_sources/coverage_audit.md",
    )
    parser.add_argument(
        "--output-md",
        type=Path,
        default=ROOT / "docs/audit/a_share_spec_completion.md",
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        default=ROOT / "docs/audit/a_share_spec_completion.json",
    )
    parser.add_argument("--no-write", action="store_true")
    args = parser.parse_args(argv)

    spec = load_spec(args.spec)
    labels = load_coverage_labels(args.coverage_audit)
    report = build_completion_report(spec=spec, db_path=args.db, labels=labels)
    md = render_markdown(report)

    if not args.no_write:
        args.output_md.parent.mkdir(parents=True, exist_ok=True)
        args.output_md.write_text(md, encoding="utf-8")
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(
            json.dumps(report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    print(
        json.dumps(
            {
                "ok": True,
                "spec_total": report["spec_total"],
                "a_share_hard_handled": report["a_share_realtime"]["spec_dp_handled"],
                "a_share_effective_real_handled": report["a_share_effective_realtime"]["spec_dp_real_handled"],
                "a_share_effective_mock_only": report["a_share_effective_realtime"]["spec_dp_mock_only"],
                "a_share_overlay_handled": report["a_share_overlay"]["spec_dp_handled"],
                "a_share_combined_handled": report["combined"]["spec_dp_handled"],
                "a_share_completion_pct": report["combined"]["completion_pct"],
                "a_share_gap_count": report["combined"]["gap_count"],
                "output_md": str(args.output_md),
                "output_json": str(args.output_json),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
