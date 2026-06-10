"""Resumable results store for the PIT backtest (isolated sqlite).

``runtime/backtest/backtest.sqlite`` holds the scoring sweep and forward-return
labels so metrics can be recomputed without re-scoring. INSERT OR REPLACE keyed
on the natural keys → idempotent resume.
"""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any, Iterable, Mapping

DEFAULT_DB = Path("runtime/backtest/backtest.sqlite")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS scores (
    ts_code TEXT NOT NULL,
    base_date TEXT NOT NULL,
    base_score REAL,
    core_base_score REAL,
    short_total REAL,
    medium_total REAL,
    long_total REAL,
    trading_signal TEXT,
    mode TEXT,
    industry_contrib REAL,
    scored_at INTEGER,
    PRIMARY KEY (ts_code, base_date)
);
CREATE TABLE IF NOT EXISTS returns (
    ts_code TEXT NOT NULL,
    base_date TEXT NOT NULL,
    end_date TEXT NOT NULL,
    horizon_d INTEGER,
    close_base REAL,
    close_end REAL,
    used_base_date TEXT,
    used_end_date TEXT,
    fwd_ret REAL,
    status TEXT,
    PRIMARY KEY (ts_code, base_date, end_date)
);
CREATE TABLE IF NOT EXISTS manifest (
    key TEXT PRIMARY KEY,
    value_json TEXT
);
"""


def init(db_path: Path = DEFAULT_DB) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(db_path)) as c:
        c.executescript(_SCHEMA)


def put_scores(rows: Iterable[Mapping[str, Any]], db_path: Path = DEFAULT_DB) -> int:
    init(db_path)
    now = int(time.time())
    payload = [
        (r["ts_code"], r["base_date"], r.get("base_score"), r.get("core_base_score"),
         r.get("short_total"), r.get("medium_total"), r.get("long_total"),
         r.get("trading_signal"), r.get("mode"), r.get("industry_contrib"), now)
        for r in rows
    ]
    if not payload:
        return 0
    with sqlite3.connect(str(db_path), isolation_level=None) as c:
        c.executemany(
            """INSERT OR REPLACE INTO scores
               (ts_code, base_date, base_score, core_base_score, short_total,
                medium_total, long_total, trading_signal, mode, industry_contrib, scored_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            payload,
        )
    return len(payload)


def put_returns(rows: Iterable[Mapping[str, Any]], db_path: Path = DEFAULT_DB) -> int:
    init(db_path)
    payload = [
        (r["ts_code"], r["base_date"], r["end_date"], r.get("horizon_d"),
         r.get("close_base"), r.get("close_end"), r.get("used_base_date"),
         r.get("used_end_date"), r.get("fwd_ret"), r.get("status"))
        for r in rows
    ]
    if not payload:
        return 0
    with sqlite3.connect(str(db_path), isolation_level=None) as c:
        c.executemany(
            """INSERT OR REPLACE INTO returns
               (ts_code, base_date, end_date, horizon_d, close_base, close_end,
                used_base_date, used_end_date, fwd_ret, status)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            payload,
        )
    return len(payload)


def scored_base_dates(db_path: Path = DEFAULT_DB) -> dict[str, int]:
    if not Path(db_path).exists():
        return {}
    with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as c:
        rows = c.execute("SELECT base_date, COUNT(*) FROM scores GROUP BY base_date").fetchall()
    return {r[0]: r[1] for r in rows}


def read_scores(db_path: Path = DEFAULT_DB) -> list[dict]:
    if not Path(db_path).exists():
        return []
    with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as c:
        c.row_factory = sqlite3.Row
        return [dict(r) for r in c.execute("SELECT * FROM scores")]


def read_returns(db_path: Path = DEFAULT_DB) -> list[dict]:
    if not Path(db_path).exists():
        return []
    with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as c:
        c.row_factory = sqlite3.Row
        return [dict(r) for r in c.execute("SELECT * FROM returns")]


def set_manifest(key: str, value: Any, db_path: Path = DEFAULT_DB) -> None:
    init(db_path)
    with sqlite3.connect(str(db_path), isolation_level=None) as c:
        c.execute("INSERT OR REPLACE INTO manifest (key, value_json) VALUES (?,?)",
                  (key, json.dumps(value)))


def get_manifest(key: str, db_path: Path = DEFAULT_DB) -> Any:
    if not Path(db_path).exists():
        return None
    with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as c:
        r = c.execute("SELECT value_json FROM manifest WHERE key=?", (key,)).fetchone()
    return json.loads(r[0]) if r else None
