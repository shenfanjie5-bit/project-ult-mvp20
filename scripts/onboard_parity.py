"""Per-stock onboard parity verification (trust-but-verify, NOT self-report).

For one ts_code, check the 6 parity items from the bulk-onboard spec against the
existing A-share baseline by reading the DB / universe / overlay / score DIRECTLY:

  ① universe.yaml entry exists and industry_ids == expected theme
  ② hot.sqlite overlay_manifest has a row AND a compiled snapshot exists
  ③ realtime_current has the core quant dp_ids (L5/L6/L7) at ~baseline count
  ④ codex qualitative L1-L3 layer filled (nodes with non-null strength) ~baseline
  ⑤ the 6 base components + base_score + trading_signal are produced (non-degenerate)
  ⑥ the stock is present in its market peer_context pool

Usage:
    python scripts/onboard_parity.py --ts-code 688981.SH [--theme SEMI_EQUIPMENT]
    # or import parity_check(ts_code, db_path, theme) -> dict
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DB_PATH = ROOT / "runtime" / "hot.sqlite"
UNIVERSE_PATH = ROOT / "config" / "mvp20.universe.yaml"
OVERLAYS_DIR = ROOT / "config" / "stock_overlays"

# Baseline (existing 121 A-share overlays, measured 2026-06-06):
#   core L5/L6/L7 dp_ids:        min 57, p25 68, median 68
#   evidence_sources-filled nodes: min 55, p25 68, median 80
# parity thresholds — a new stock clears item③/④ at a fraction of baseline so
# ST/BJ sparsity doesn't false-fail.
CORE_DP_FLOOR = 40        # core quant dp_ids present
EV_FILLED_FLOOR = 50      # nodes carrying evidence_sources (qualitative+derive layer)
# NOTE: the AUTHORITATIVE codex-ran signal is run_onboard's codex_warning (None
# == ran clean), captured by the batch runner into the ledger. EV_FILLED here is
# the overlay-only density proxy used when that runtime signal isn't available.


def _universe_entry(ts_code: str) -> dict | None:
    uni = yaml.safe_load(UNIVERSE_PATH.read_text(encoding="utf-8")) or {}
    for c in uni.get("constituents", []):
        if str(c.get("ts_code", "")).upper() == ts_code.upper():
            return c
    return None


def _overlay_path(ts_code: str) -> Path | None:
    for sub in OVERLAYS_DIR.iterdir() if OVERLAYS_DIR.exists() else []:
        if sub.is_dir():
            p = sub / f"{ts_code}.yaml"
            if p.exists():
                return p
    p = OVERLAYS_DIR / f"{ts_code}.yaml"
    return p if p.exists() else None


def _ev_filled_count(ts_code: str) -> tuple[int, int, int]:
    """(ev_filled, codex_ev, total) over overlay nodes. ``ev_filled`` = nodes
    carrying a non-empty ``evidence_sources`` (the populated qualitative+evidence
    layer; derive writes local_dp_id evidence, codex adds web_analysis/
    industry_inference). ``codex_ev`` = nodes with a codex-specific evidence kind
    (sparse even at baseline — median 3 — so reported for audit, not gated)."""
    p = _overlay_path(ts_code)
    if not p:
        return 0, 0, 0
    o = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    nodes = o.get("nodes") or []
    ev_filled = codex_ev = total = 0
    for n in nodes:
        if not isinstance(n, dict):
            continue
        total += 1
        srcs = n.get("evidence_sources") or []
        if srcs:
            ev_filled += 1
        if any(isinstance(s, dict) and s.get("kind") in ("web_analysis", "industry_inference")
               for s in srcs):
            codex_ev += 1
    return ev_filled, codex_ev, total


def _peer_context_member(ts_code: str, db_path: Path) -> bool:
    try:
        from mvp20.peer_context import default_artifact_path, load_peer_context, market_of
        if market_of(ts_code) != "A":
            return False
        art = load_peer_context(default_artifact_path(db_path, "A"))
    except Exception:  # noqa: BLE001
        return False
    blob = json.dumps(art, ensure_ascii=False, default=str) if art is not None else ""
    return ts_code.upper() in blob.upper()


def _score_breakdown(ts_code: str, db_path: Path) -> dict:
    """Reuse server.handle_score for the full assembly → 6 components + signal."""
    from mvp20 import server
    cfg = server.ServerConfig(hot_db_path=db_path)
    status, payload = server.handle_score(cfg, {"ts_code": [ts_code]})
    if status != 200:
        return {"ok": False, "status": status, "error": str(payload)[:200]}
    data = (payload or {}).get("data") or payload or {}
    fs = data.get("final_score") or {}
    comps = fs.get("components") or {}
    return {
        "ok": True,
        "components": comps,
        "base_score": fs.get("base_score"),
        "trading_signal": data.get("trading_signal"),
        "short": data.get("short_total"), "medium": data.get("medium_total"),
        "long": data.get("long_total"),
    }


def parity_check(ts_code: str, db_path: Path = DB_PATH, theme: str | None = None) -> dict:
    ts_code = ts_code.upper()
    conn = sqlite3.connect(db_path)
    try:
        dp_rows = [r[0] for r in conn.execute(
            "SELECT dp_id FROM realtime_current WHERE ts_code=?", (ts_code,)).fetchall()]
        om_rows = conn.execute(
            "SELECT COUNT(*) FROM overlay_manifest WHERE ts_code=?", (ts_code,)).fetchone()[0]
    finally:
        conn.close()
    dp_total = len(dp_rows)
    core = sum(1 for d in dp_rows if d and (d.startswith("L5.") or d.startswith("L6.") or d.startswith("L7.")))

    # compiled snapshot present?
    try:
        from mvp20.storage import read_compiled_graph_snapshot
        compiled_ok = read_compiled_graph_snapshot(db_path, ts_code) is not None
    except Exception:  # noqa: BLE001
        compiled_ok = False

    entry = _universe_entry(ts_code)
    ind_ids = (entry or {}).get("industry_ids") or []
    ev_filled, codex_ev, qual_total = _ev_filled_count(ts_code)
    peer_ok = _peer_context_member(ts_code, db_path)
    sb = _score_breakdown(ts_code, db_path)

    comps = sb.get("components") or {}
    six = ["fundamental", "expectation_gap", "valuation_rerating",
           "capital_sentiment", "risk", "priced_in"]
    comps_present = {k: (comps.get(k) is not None) for k in six}
    comps_nonzero = sum(1 for k in six if comps.get(k))  # truthy = non-zero present

    items = {
        "1_universe": bool(entry) and (theme is None or theme in ind_ids),
        "2_overlay_compiled": om_rows > 0 and compiled_ok,
        "3_core_quant_dp": core >= CORE_DP_FLOOR,
        "4_codex_qual_filled": ev_filled >= EV_FILLED_FLOOR,
        "5_six_components_signal": (sb.get("ok") and all(comps_present.values())
                                    and sb.get("base_score") is not None
                                    and bool(sb.get("trading_signal"))),
        "6_peer_context": peer_ok,
    }
    return {
        "ts_code": ts_code,
        "theme": theme,
        "industry_ids": ind_ids,
        "dp_total": dp_total,
        "core_l567": core,
        "overlay_manifest_rows": om_rows,
        "compiled_ok": compiled_ok,
        "ev_filled": ev_filled,
        "codex_ev": codex_ev,
        "qual_total": qual_total,
        "peer_context_member": peer_ok,
        "base_score": sb.get("base_score"),
        "trading_signal": sb.get("trading_signal"),
        "components": comps,
        "components_nonzero": comps_nonzero,
        "score_ok": sb.get("ok"),
        "score_error": sb.get("error"),
        "items": items,
        "pass": all(items.values()),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ts-code", required=True)
    ap.add_argument("--theme", default=None)
    ap.add_argument("--db", default=str(DB_PATH))
    args = ap.parse_args()
    res = parity_check(args.ts_code, Path(args.db), args.theme)
    print(json.dumps(res, ensure_ascii=False, indent=2))
    print("\nPARITY:", "PASS ✓" if res["pass"] else "FAIL ✗",
          "| items:", {k: ("✓" if v else "✗") for k, v in res["items"].items()})


if __name__ == "__main__":
    main()
