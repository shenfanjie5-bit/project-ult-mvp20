#!/usr/bin/env python3
"""Recompute the REAL base_score at extra historical base dates (ISOLATED, read-only project).

Reuses the pit_backtest pipeline (collector -> derive -> peer_context -> score) but
redirects ALL outputs under factor_research/pit_extra/ via the pipeline `root=` arg and
an isolated results sqlite. NOTHING is written to runtime/backtest/.

Usage:
  .venv/bin/python factor_research/run_realbase.py <asof>           # one base date
  .venv/bin/python factor_research/run_realbase.py --analyze        # build IC table + OOS

Data: DockCase cache (DOCKCASE_CACHE=1) serves by-symbol financials; date-range/
cross-section price calls hit live tushare (token from .env).
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
import sys
import time
from pathlib import Path

os.environ.setdefault("DOCKCASE_CACHE", "1")
sys.path.insert(0, os.getcwd())

from pit_backtest import collector, pipeline, prices, calendar as cal, universe  # noqa: E402

ROOT = Path("factor_research/pit_extra")
RESULTS_DB = ROOT / "realbase.sqlite"
UNIVERSE_JSON = ROOT / "universe_sample.json"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS scores (
    ts_code TEXT NOT NULL, base_date TEXT NOT NULL,
    base_score REAL, core_base_score REAL, short_total REAL,
    medium_total REAL, long_total REAL, trading_signal TEXT, mode TEXT,
    industry_contrib REAL, scored_at INTEGER,
    PRIMARY KEY (ts_code, base_date)
);
CREATE TABLE IF NOT EXISTS manifest (key TEXT PRIMARY KEY, value_json TEXT);
"""


def _db():
    RESULTS_DB.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(RESULTS_DB))
    con.executescript(_SCHEMA)
    return con


def load_universe() -> list[str]:
    return json.loads(UNIVERSE_JSON.read_text())


def put_scores(rows: list[dict], asof: str) -> int:
    con = _db()
    now = int(time.time())
    payload = [
        (r["ts_code"], r["base_date"], r.get("base_score"), r.get("core_base_score"),
         r.get("short_total"), r.get("medium_total"), r.get("long_total"),
         r.get("trading_signal"), r.get("mode"), r.get("industry_contrib"), now)
        for r in rows
    ]
    if payload:
        con.executemany(
            """INSERT OR REPLACE INTO scores
               (ts_code, base_date, base_score, core_base_score, short_total,
                medium_total, long_total, trading_signal, mode, industry_contrib, scored_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            payload,
        )
        con.commit()
    con.close()
    return len(payload)


def scored_count(asof: str) -> int:
    if not RESULTS_DB.exists():
        return 0
    con = sqlite3.connect(f"file:{RESULTS_DB}?mode=ro", uri=True)
    try:
        r = con.execute("SELECT COUNT(*) FROM scores WHERE base_date=?", (asof,)).fetchone()
        return r[0] if r else 0
    except sqlite3.OperationalError:
        return 0
    finally:
        con.close()


def run_one(asof: str) -> dict:
    log = logging.getLogger("run_realbase")
    codes = load_universe()
    ind_of = universe.primary_industry_map()
    log.info("base %s | universe n=%d", asof, len(codes))

    if scored_count(asof) >= len(codes) * 0.9:
        log.info("base %s already scored (%d) — skip", asof, scored_count(asof))
        return {"asof": asof, "skipped": True}

    pro = collector.get_pro()
    t0 = time.time()

    def _p(i, n, ts):
        if i % 25 == 0:
            log.info("  collect %s: %d/%d (%.0fs)", asof, i, n, time.time() - t0)

    db_path, stats = pipeline.build_pit_for_asof(
        asof, codes, ind_of, root=ROOT, resume=True, pro=pro, progress=_p
    )
    t_build = time.time() - t0
    log.info("collect+derive+peer %s: %.0fs stats=%s", asof, t_build, stats)

    t0 = time.time()
    rows = pipeline.score_universe_asof(asof, codes, db_path)
    n = put_scores(rows, asof)
    log.info("scored %s: %d rows in %.0fs", asof, n, time.time() - t0)
    return {"asof": asof, "build_s": round(t_build, 1), "scored": n, "stats": stats}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                        datefmt="%H:%M:%S")
    arg = sys.argv[1] if len(sys.argv) > 1 else ""
    if arg and not arg.startswith("--"):
        print(json.dumps(run_one(arg)))
    else:
        print("usage: run_realbase.py <YYYYMMDD>")
