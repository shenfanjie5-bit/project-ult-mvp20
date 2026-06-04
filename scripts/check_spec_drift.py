#!/usr/bin/env python3
"""Detect drift between spec / governance / SQLite / overlay yaml.

3 sources of truth that should be consistent:
1. config/data_point_roles.yaml — 250 dp_ids + source_status declarations
2. config/llm_field_governance.yaml — 111 LLM-routed dp_ids + governance fields
3. runtime/hot.sqlite + config/stock_overlays/**.yaml — actual emit/fill state

Checks:
A. spec source_status='missing' but SQLite has emit -> outdated label
B. spec source_status='✓' but SQLite never emitted -> unimplemented promise
C. spec source_status='$' but SQLite has emit -> premium-no-longer-locked
D. governance dp_id but not in spec 250 -> orphan governance entry
E. spec bucket vs governance route mismatch (TODO: needs bucket inference)
F. data_point_roles count of missing (X) vs coverage_audit md §4 (Y) drift
G. SQLite emit but dp_id not in spec 250 (legacy naming)

Output: docs/audit/spec_drift_report_v1.md + JSON
Exit code: nonzero if more than 10 drifts (CI signal).
"""
from __future__ import annotations

import datetime
import glob
import json
import re
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent


def load_spec(root: Path = ROOT) -> dict:
    return yaml.safe_load((root / "config/data_point_roles.yaml").read_text()) or {}


def load_governance(root: Path = ROOT) -> dict:
    return yaml.safe_load((root / "config/llm_field_governance.yaml").read_text()) or {}


def load_sqlite_dps(root: Path = ROOT) -> set[str]:
    db = root / "runtime/hot.sqlite"
    if not db.exists():
        return set()
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        rows = conn.execute(
            "SELECT DISTINCT dp_id FROM realtime_current"
        ).fetchall()
        return {r[0] for r in rows if r[0]}
    except sqlite3.Error:
        return set()
    finally:
        conn.close()


def load_overlay_dps(root: Path = ROOT) -> set[str]:
    """Distinct dp_ids with Known/Optionality across all stock + industry overlays."""
    dps: set[str] = set()
    patterns = [
        str(root / "config/stock_overlays/*.yaml"),
        str(root / "config/stock_overlays/*/*.yaml"),
        str(root / "config/industry_overlays/*.yaml"),
    ]
    for pattern in patterns:
        for f in glob.glob(pattern):
            try:
                y = yaml.safe_load(Path(f).read_text()) or {}
                for n in y.get("nodes") or []:
                    if n.get("data_status") in ("Known", "Optionality"):
                        dp = n.get("dp_id")
                        if dp:
                            dps.add(dp)
            except Exception:
                continue
    return dps


def count_audit_md_missing(root: Path = ROOT) -> int | None:
    """Parse docs/data_sources/coverage_audit.md §4 to count missing dp_ids."""
    md_path = root / "docs/data_sources/coverage_audit.md"
    if not md_path.exists():
        return None
    md = md_path.read_text()
    # Section 4 starts with "## 4." and ends at next "## " heading at the
    # same level.
    sec4_match = re.search(r"## 4\..*?(?=^## \d+\.)", md, re.DOTALL | re.MULTILINE)
    if not sec4_match:
        return None
    rows = re.findall(
        r"^\|\s*`(L\d+\.[a-z_]+\.[a-z_]+)`",
        sec4_match.group(0),
        re.MULTILINE,
    )
    return len(rows)


def detect_drifts(
    spec: dict,
    governance: dict,
    sqlite_dps: set[str],
    overlay_dps: set[str],
    audit_missing: int | None,
) -> list[dict]:
    """Return a list of drift records given snapshots of the 4 sources."""
    drifts: list[dict] = []
    spec_dps_map = spec.get("data_points", {}) or {}
    spec_dps = set(spec_dps_map.keys())
    gov_dps = set((governance.get("data_points", {}) or {}).keys())

    # A. spec source_status='missing' but SQLite emit
    for dp, entry in spec_dps_map.items():
        if entry.get("source_status") == "missing" and dp in sqlite_dps:
            drifts.append(
                {
                    "type": "outdated_missing_label",
                    "dp_id": dp,
                    "spec_says": "missing",
                    "actual": "SQLite has emit",
                    "action": "update spec source_status to ✓ or ○",
                }
            )

    # B. spec '✓' (multi/single full) but never emit and not in overlays
    for dp, entry in spec_dps_map.items():
        st = entry.get("source_status", "")
        if st == "✓" and dp not in sqlite_dps and dp not in overlay_dps:
            drifts.append(
                {
                    "type": "unimplemented_promise",
                    "dp_id": dp,
                    "spec_says": "✓ full",
                    "actual": "not in SQLite or overlay",
                    "action": "wire fetcher or downgrade source_status",
                }
            )

    # C. spec '$ premium' but SQLite emit
    for dp, entry in spec_dps_map.items():
        if entry.get("source_status") == "$" and dp in sqlite_dps:
            drifts.append(
                {
                    "type": "premium_unlocked",
                    "dp_id": dp,
                    "spec_says": "$ premium",
                    "actual": "SQLite has emit (no premium needed)",
                    "action": "update spec source_status (remove $)",
                }
            )

    # D. governance but not in spec 250
    for dp in sorted(gov_dps - spec_dps):
        drifts.append(
            {
                "type": "orphan_governance",
                "dp_id": dp,
                "spec_says": "not in spec 250",
                "actual": "in governance.yaml",
                "action": "remove from governance or add to spec",
            }
        )

    # E. spec bucket vs governance route mismatch — TODO (needs bucket
    # inference from field_role + source_status; intentionally skipped).

    # F. count drift: spec missing count vs audit md §4 count
    spec_missing = sum(
        1
        for e in spec_dps_map.values()
        if e.get("source_status") == "missing"
    )
    if audit_missing is not None and spec_missing != audit_missing:
        drifts.append(
            {
                "type": "count_drift",
                "dp_id": "(global)",
                "spec_says": f"data_point_roles.yaml: {spec_missing} missing",
                "actual": f"coverage_audit.md §4: {audit_missing} missing",
                "action": "sync one source to the other",
            }
        )

    # G. SQLite emit but dp_id not in spec 250 (legacy / self-namespace)
    legacy = sorted(sqlite_dps - spec_dps)
    for dp in legacy:
        drifts.append(
            {
                "type": "legacy_naming",
                "dp_id": dp,
                "spec_says": "not in spec 250",
                "actual": "SQLite has emit (likely mvp20 self-namespace)",
                "action": "add to spec or alias to canonical dp_id",
            }
        )

    return drifts


def render_report(drifts: list[dict]) -> str:
    by_type: dict[str, list[dict]] = defaultdict(list)
    for d in drifts:
        by_type[d["type"]].append(d)

    md: list[str] = ["# Spec drift report v1", ""]
    md.append(
        f"Generated by `scripts/check_spec_drift.py` on "
        f"{datetime.date.today().isoformat()}"
    )
    md.append("")
    md.append(f"**Total drift items**: {len(drifts)}")
    md.append("")
    md.append("## By type")
    md.append("")
    md.append("| type | count |")
    md.append("|---|---|")
    for t in sorted(by_type.keys()):
        md.append(f"| {t} | {len(by_type[t])} |")
    md.append("")

    for t, items in sorted(by_type.items()):
        md.append(f"## {t} ({len(items)})")
        md.append("")
        md.append("| dp_id | spec says | actual | action |")
        md.append("|---|---|---|---|")
        for d in items[:30]:
            md.append(
                f"| `{d['dp_id']}` | {d['spec_says']} | "
                f"{d['actual']} | {d['action']} |"
            )
        if len(items) > 30:
            md.append(f"| ... | (+{len(items)-30} more) | | |")
        md.append("")

    return "\n".join(md)


def main(argv: list[str] | None = None) -> int:
    spec = load_spec()
    governance = load_governance()
    sqlite_dps = load_sqlite_dps()
    overlay_dps = load_overlay_dps()
    audit_missing = count_audit_md_missing()

    drifts = detect_drifts(spec, governance, sqlite_dps, overlay_dps, audit_missing)

    md = render_report(drifts)

    output_md = ROOT / "docs/audit/spec_drift_report_v1.md"
    output_md.parent.mkdir(parents=True, exist_ok=True)
    output_md.write_text(md, encoding="utf-8")

    output_json = ROOT / "docs/audit/spec_drift_report_v1.json"
    output_json.write_text(
        json.dumps({"drifts": drifts}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(
        f"wrote {output_md.relative_to(ROOT)} ({len(drifts)} drift items)"
    )
    print(f"wrote {output_json.relative_to(ROOT)}")

    # Summary to stdout
    print("\n--- summary ---")
    by_type: dict[str, int] = defaultdict(int)
    for d in drifts:
        by_type[d["type"]] += 1
    for t in sorted(by_type.keys()):
        print(f"  {t}: {by_type[t]}")

    # Exit nonzero if more than 10 drifts (CI signal)
    return 1 if len(drifts) > 10 else 0


if __name__ == "__main__":
    sys.exit(main())
