#!/usr/bin/env python3
"""Track B forward-collection: archive free-text news with publish timestamps.

`realtime_current` is a HOT UPSERT snapshot (current value only) — there is no
historical news archive, so Track B (free-text news → LLM sentiment → signed
coefficient) CANNOT be backtested. This script starts the only thing that makes
it validatable: an append-only, point-in-time archive. Run it daily (cron); each
run appends headlines it hasn't seen before. After ~6–7 weeks of accrual the
archive can be fed through the same eventlib abnormal-CAR + kill criteria as
Track A (see docs/audit/event_impact_FINAL_2026-06-09.md §4).

Read-only on the hot DB; writes ONLY runtime/trackB_archive.sqlite. Idempotent:
re-running the same day inserts nothing new (UNIQUE on ts_code+title_hash).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import time
from pathlib import Path

_DEFAULT_HOT = Path("runtime/hot.sqlite")
_DEFAULT_ARCHIVE = Path("runtime/trackB_archive.sqlite")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS news_archive (
  id               INTEGER PRIMARY KEY AUTOINCREMENT,
  ts_code          TEXT NOT NULL,
  dp_id            TEXT NOT NULL,
  title            TEXT NOT NULL,
  title_hash       TEXT NOT NULL,
  publish_time     TEXT,
  publish_epoch    INTEGER,
  url              TEXT,
  source           TEXT,
  is_cross_echo    INTEGER NOT NULL DEFAULT 0,  -- title already seen for another ts_code
  first_seen_epoch INTEGER NOT NULL             -- when WE archived it (collection time)
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_news_code_hash ON news_archive(ts_code, title_hash);
CREATE INDEX IF NOT EXISTS ix_news_epoch ON news_archive(publish_epoch);
CREATE INDEX IF NOT EXISTS ix_news_hash ON news_archive(title_hash);
"""

_PARSE_FORMATS = ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%Y%m%d")


def _parse_epoch(s: str | None) -> int | None:
    from datetime import datetime
    if not s or not isinstance(s, str):
        return None
    for fmt in _PARSE_FORMATS:
        try:
            return int(datetime.strptime(s[:19], fmt).timestamp())
        except ValueError:
            continue
    return None


def _title_hash(title: str) -> str:
    return hashlib.sha1(title.encode("utf-8")).hexdigest()[:16]


def _read_headlines(hot_db: Path) -> list[dict]:
    """Pull current news headlines from realtime_current (read-only)."""
    conn = sqlite3.connect(f"file:{hot_db}?mode=ro", uri=True)
    try:
        rows = conn.execute(
            """
            SELECT ts_code, dp_id, value_json FROM realtime_current
             WHERE data_status = 'Known'
               AND ((ts_code = 'MARKET:CN' AND dp_id = 'L9.media.report')
                 OR dp_id = 'L9.event.intraday_news')
            """
        ).fetchall()
    finally:
        conn.close()
    out: list[dict] = []
    for ts_code, dp_id, val_json in rows:
        try:
            payload = json.loads(val_json)
        except (TypeError, ValueError):
            continue
        if not isinstance(payload, dict):
            continue
        for h in payload.get("top_headlines") or []:
            if not isinstance(h, dict):
                continue
            title = (h.get("title") or "").strip()
            if not title:
                continue
            raw_ts = h.get("time") or h.get("publish_time")
            out.append({
                "ts_code": ts_code, "dp_id": dp_id, "title": title,
                "title_hash": _title_hash(title),
                "publish_time": raw_ts if isinstance(raw_ts, str) else None,
                "publish_epoch": _parse_epoch(raw_ts),
                "url": h.get("url"), "source": h.get("source"),
            })
    return out


def collect(hot_db: Path = _DEFAULT_HOT, archive_db: Path = _DEFAULT_ARCHIVE,
            *, now_epoch: int | None = None) -> dict:
    """Append unseen headlines into the archive. Returns counters."""
    now_epoch = int(time.time()) if now_epoch is None else now_epoch
    items = _read_headlines(hot_db)
    archive_db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(archive_db)
    try:
        conn.executescript(_SCHEMA)
        inserted = echoes = 0
        for it in items:
            # cross-echo: same title already archived under a DIFFERENT ts_code.
            other = conn.execute(
                "SELECT 1 FROM news_archive WHERE title_hash = ? AND ts_code != ? LIMIT 1",
                (it["title_hash"], it["ts_code"]),
            ).fetchone()
            is_echo = 1 if other else 0
            cur = conn.execute(
                """INSERT OR IGNORE INTO news_archive
                   (ts_code, dp_id, title, title_hash, publish_time, publish_epoch,
                    url, source, is_cross_echo, first_seen_epoch)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (it["ts_code"], it["dp_id"], it["title"], it["title_hash"],
                 it["publish_time"], it["publish_epoch"], it["url"], it["source"],
                 is_echo, now_epoch),
            )
            if cur.rowcount:
                inserted += 1
                echoes += is_echo
        conn.commit()
        total = conn.execute("SELECT COUNT(*) FROM news_archive").fetchone()[0]
    finally:
        conn.close()
    return {"scanned": len(items), "inserted": inserted,
            "cross_echo": echoes, "total": total}


def main() -> int:
    ap = argparse.ArgumentParser(description="Track B forward news archiver")
    ap.add_argument("--hot-db", type=Path, default=_DEFAULT_HOT)
    ap.add_argument("--archive-db", type=Path, default=_DEFAULT_ARCHIVE)
    args = ap.parse_args()
    if not args.hot_db.exists():
        print(f"[trackB] hot db not found: {args.hot_db}")
        return 1
    r = collect(args.hot_db, args.archive_db)
    print(f"[trackB] scanned={r['scanned']} inserted={r['inserted']} "
          f"cross_echo={r['cross_echo']} total_archived={r['total']} "
          f"→ {args.archive_db}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
