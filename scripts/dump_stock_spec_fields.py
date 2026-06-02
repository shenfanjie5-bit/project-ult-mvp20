#!/usr/bin/env python3
"""Per-stock complete spec-field view.

For ONE ts_code, render all 250 canonical spec dp_ids
(``config/data_point_roles.yaml``) annotated with:

* spec role: ``score_target`` / ``participates_in_score`` / ``field_role`` /
  ``neutral_value``.
* runtime state (``read_hot_snapshot`` — same sentinel fan-out the scorer
  sees): value preview, ``data_status``, ``source``, ``confidence``, and the
  origin ts_code (self vs ``INDUSTRY:*`` / ``MARKET:*`` sentinel).
* compiled overlay state (``company_node_instance``): ``data_status`` +
  ``materiality``.
* a single classification bucket per dp_id, mirroring the original A-share
  review taxonomy:

  - ``real_self``       real non-mock hard/derived row for THIS ts_code
  - ``real_sentinel``   real non-mock row inherited from INDUSTRY/MARKET
  - ``overlay``         filled only via compiled overlay (Known/Inactive)
  - ``mock_only``       runtime row whose source starts with ``mock:``
  - ``inactive``        data_status Inactive (event-driven, no live event)
  - ``unknown``         Unknown / N/A / absent everywhere

* ``in_score``: participates_in_score AND backed by a usable (real or overlay
  Known) value — i.e. actually able to move ``core_final_score`` /
  ``final_score``.

Usage::

    python scripts/dump_stock_spec_fields.py --ts-code 000977.SZ
    python scripts/dump_stock_spec_fields.py --ts-code 000977.SZ \
        --out-md docs/audit/spec_fields_000977.md
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from mvp20.storage import read_hot_snapshot  # noqa: E402

SPEC_PATH = ROOT / "config" / "data_point_roles.yaml"
HOT_DB_PATH = ROOT / "runtime" / "hot.sqlite"


def layer_of(dp_id: str) -> str:
    return dp_id.split(".", 1)[0] if "." in dp_id else dp_id


def layer_sort_key(layer: str) -> tuple[int, str]:
    m = re.fullmatch(r"L(\d+)", layer)
    return (int(m.group(1)), layer) if m else (999, layer)


def is_mock(source: str | None) -> bool:
    return str(source or "").lower().startswith("mock:")


def load_spec() -> dict[str, dict]:
    payload = yaml.safe_load(SPEC_PATH.read_text(encoding="utf-8")) or {}
    dp = payload.get("data_points") or {}
    return {str(k): dict(v or {}) for k, v in dp.items()}


def load_overlay_state(db_path: Path, ts_code: str) -> dict[str, dict]:
    """dp_id -> {data_status, materiality} from compiled company_node_instance."""
    if not db_path.exists():
        return {}
    out: dict[str, dict] = {}
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        rows = conn.execute(
            """
            SELECT dp_id, data_status, materiality
              FROM company_node_instance
             WHERE ts_code = ?
            """,
            (ts_code,),
        ).fetchall()
    except sqlite3.OperationalError:
        rows = []
    finally:
        conn.close()
    for dp_id, status, materiality in rows:
        # Prefer the most "filled" status if a dp_id appears on >1 node.
        prior = out.get(dp_id)
        rank = {"Known": 3, "Inactive": 2, "LowMateriality": 1}.get(str(status), 0)
        if prior is None or rank > prior["_rank"]:
            out[dp_id] = {
                "data_status": status,
                "materiality": materiality,
                "_rank": rank,
            }
    for v in out.values():
        v.pop("_rank", None)
    return out


def preview_value(value: Any, width: int = 48) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        s = json.dumps(value, ensure_ascii=False)
    else:
        s = str(value)
    s = s.replace("\n", " ").replace("|", "/")
    return s if len(s) <= width else s[: width - 1] + "…"


def classify(spec: dict, rt: dict | None, ov: dict | None, ts_code: str) -> str:
    rt_status = (rt or {}).get("data_status")
    rt_src = (rt or {}).get("source")
    origin = (rt or {}).get("_origin_ts_code")
    ov_status = (ov or {}).get("data_status")

    if rt is not None and is_mock(rt_src):
        # mock row — only counts as mock if nothing real/overlay backs it
        if ov_status == "Known":
            return "overlay"
        return "mock_only"

    if rt is not None and rt_status in {"Known", "Proxy"}:
        return "real_self" if origin == ts_code else "real_sentinel"

    if ov_status == "Known":
        return "overlay"

    if rt_status == "Inactive" or ov_status == "Inactive":
        return "inactive"

    if rt is not None and rt_status in {"Optionality"}:
        return "overlay"

    return "unknown"


REAL_BUCKETS = {"real_self", "real_sentinel"}
USABLE_BUCKETS = {"real_self", "real_sentinel", "overlay"}


def build_rows(ts_code: str, db_path: Path) -> list[dict]:
    spec = load_spec()
    snap = read_hot_snapshot(db_path, ts_code)  # sentinel-merged, as scorer sees
    overlay = load_overlay_state(db_path, ts_code)

    rows: list[dict] = []
    for dp_id, role in spec.items():
        rt = snap.get(dp_id)
        ov = overlay.get(dp_id)
        bucket = classify(role, rt, ov, ts_code)
        participates = bool(role.get("participates_in_score"))
        in_score = participates and bucket in USABLE_BUCKETS
        rows.append(
            {
                "dp_id": dp_id,
                "layer": layer_of(dp_id),
                "score_target": role.get("score_target") or role.get("derived_target") or "",
                "participates": participates,
                "field_role": role.get("field_role") or "",
                "neutral_value": role.get("neutral_value"),
                "rt_status": (rt or {}).get("data_status"),
                "rt_source": (rt or {}).get("source"),
                "rt_origin": (rt or {}).get("_origin_ts_code"),
                "rt_conf": (rt or {}).get("confidence"),
                "rt_value": preview_value((rt or {}).get("value")) if rt else "",
                "ov_status": (ov or {}).get("data_status"),
                "ov_materiality": (ov or {}).get("materiality"),
                "bucket": bucket,
                "in_score": in_score,
            }
        )
    rows.sort(key=lambda r: (layer_sort_key(r["layer"]), r["dp_id"]))
    return rows


def render_md(ts_code: str, rows: list[dict]) -> str:
    total = len(rows)
    bucket_ct = Counter(r["bucket"] for r in rows)
    in_score_ct = sum(1 for r in rows if r["in_score"])
    participates_ct = sum(1 for r in rows if r["participates"])
    real_ct = sum(1 for r in rows if r["bucket"] in REAL_BUCKETS)
    usable_ct = sum(1 for r in rows if r["bucket"] in USABLE_BUCKETS)

    out: list[str] = []
    out.append(f"# Complete spec fields — {ts_code}")
    out.append("")
    out.append(
        f"All **{total}** canonical spec dp_ids (`config/data_point_roles.yaml`), "
        f"as the scorer sees them for `{ts_code}` via `read_hot_snapshot` "
        "(sentinel-merged) + compiled overlay (`company_node_instance`)."
    )
    out.append("")
    out.append("## Summary")
    out.append("")
    out.append("| metric | count | of 250 |")
    out.append("|---|---:|---:|")
    out.append(f"| usable (real or overlay-Known) | {usable_ct} | {usable_ct/total*100:.1f}% |")
    out.append(f"| &nbsp;&nbsp;real source (self) | {bucket_ct.get('real_self',0)} | {bucket_ct.get('real_self',0)/total*100:.1f}% |")
    out.append(f"| &nbsp;&nbsp;real source (sentinel L0/macro) | {bucket_ct.get('real_sentinel',0)} | {bucket_ct.get('real_sentinel',0)/total*100:.1f}% |")
    out.append(f"| &nbsp;&nbsp;overlay-only (LLM/authored) | {bucket_ct.get('overlay',0)} | {bucket_ct.get('overlay',0)/total*100:.1f}% |")
    out.append(f"| inactive (event-driven, idle) | {bucket_ct.get('inactive',0)} | {bucket_ct.get('inactive',0)/total*100:.1f}% |")
    out.append(f"| mock-only | {bucket_ct.get('mock_only',0)} | {bucket_ct.get('mock_only',0)/total*100:.1f}% |")
    out.append(f"| unknown / N/A / absent | {bucket_ct.get('unknown',0)} | {bucket_ct.get('unknown',0)/total*100:.1f}% |")
    out.append(f"| **participates_in_score (spec)** | {participates_ct} | {participates_ct/total*100:.1f}% |")
    out.append(f"| **effectively in-score (usable + participates)** | {in_score_ct} | {in_score_ct/total*100:.1f}% |")
    out.append("")

    # Per-layer rollup
    out.append("## By layer")
    out.append("")
    out.append("| layer | total | real_self | real_sentinel | overlay | inactive | mock | unknown | in_score |")
    out.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|")
    layers = sorted({r["layer"] for r in rows}, key=layer_sort_key)
    for L in layers:
        lr = [r for r in rows if r["layer"] == L]
        c = Counter(r["bucket"] for r in lr)
        out.append(
            f"| {L} | {len(lr)} | {c.get('real_self',0)} | {c.get('real_sentinel',0)} | "
            f"{c.get('overlay',0)} | {c.get('inactive',0)} | {c.get('mock_only',0)} | "
            f"{c.get('unknown',0)} | {sum(1 for r in lr if r['in_score'])} |"
        )
    out.append("")

    # Full detail table
    out.append("## All 250 dp_ids")
    out.append("")
    out.append(
        "| dp_id | bucket | in_score | participates | score_target | "
        "rt_status | source | origin | overlay | value |"
    )
    out.append("|---|---|:--:|:--:|---|---|---|---|---|---|")
    for r in rows:
        origin = r["rt_origin"] or ""
        if origin == ts_code:
            origin = "self"
        elif origin.startswith("INDUSTRY:"):
            origin = "IND"
        elif origin.startswith("MARKET:"):
            origin = "MKT"
        ov = r["ov_status"] or ""
        out.append(
            f"| `{r['dp_id']}` | {r['bucket']} | "
            f"{'✓' if r['in_score'] else '·'} | {'✓' if r['participates'] else '·'} | "
            f"{r['score_target']} | {r['rt_status'] or ''} | {r['rt_source'] or ''} | "
            f"{origin} | {ov} | {r['rt_value']} |"
        )
    out.append("")
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ts-code", required=True)
    ap.add_argument("--db", type=Path, default=HOT_DB_PATH)
    ap.add_argument("--out-md", type=Path, default=None)
    ap.add_argument("--only", choices=["summary", "full"], default="full")
    args = ap.parse_args()

    rows = build_rows(args.ts_code, args.db)
    md = render_md(args.ts_code, rows)
    if args.out_md:
        args.out_md.parent.mkdir(parents=True, exist_ok=True)
        args.out_md.write_text(md, encoding="utf-8")
        print(f"wrote {args.out_md}")
    if args.only == "summary":
        # print only through the "By layer" section
        head = md.split("## All 250 dp_ids")[0]
        print(head)
    else:
        print(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
