"""Track B forward-collection archiver: idempotency + cross-echo flagging."""
from __future__ import annotations

import importlib.util
import sqlite3
import time
from pathlib import Path

from mvp20.storage import upsert_realtime


def _load():
    spec = importlib.util.spec_from_file_location(
        "collect_trackb_news", Path("scripts/collect_trackb_news.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _seed_hot(hot_db):
    now = int(time.time())
    upsert_realtime(hot_db, [
        ("600000.SH", "L9.event.intraday_news",
         {"top_headlines": [
             {"title": "甲公司中标大单", "time": "2026-06-09 09:30:00", "url": "u1", "source": "EM"},
             {"title": "大盘震荡走低", "time": "2026-06-09 10:00:00", "url": "u2", "source": "EM"},
         ]}, "Known", 0.6, "akshare:em_news", now),
        ("000001.SZ", "L9.event.intraday_news",
         {"top_headlines": [
             {"title": "大盘震荡走低", "time": "2026-06-09 10:00:00", "url": "u3", "source": "EM"},
             {"title": "乙公司回购股份", "time": "2026-06-09 11:00:00", "url": "u4", "source": "EM"},
         ]}, "Known", 0.6, "akshare:em_news", now),
    ])


def test_archive_is_idempotent(tmp_path):
    mod = _load()
    hot, arch = tmp_path / "hot.sqlite", tmp_path / "trackB.sqlite"
    _seed_hot(hot)
    r1 = mod.collect(hot, arch, now_epoch=1000)
    assert r1["inserted"] == 4 and r1["total"] == 4
    r2 = mod.collect(hot, arch, now_epoch=2000)        # re-run same snapshot
    assert r2["inserted"] == 0 and r2["total"] == 4    # nothing duplicated


def test_cross_echo_flagged(tmp_path):
    mod = _load()
    hot, arch = tmp_path / "hot.sqlite", tmp_path / "trackB.sqlite"
    _seed_hot(hot)
    mod.collect(hot, arch, now_epoch=1000)
    con = sqlite3.connect(arch)
    try:
        # "大盘震荡走低" is echoed across two stocks → exactly one flagged echo.
        echo = con.execute(
            "SELECT COUNT(*) FROM news_archive WHERE is_cross_echo = 1").fetchone()[0]
        stock_specific = con.execute(
            "SELECT COUNT(*) FROM news_archive WHERE is_cross_echo = 0").fetchone()[0]
    finally:
        con.close()
    assert echo == 1
    assert stock_specific == 3


def test_publish_epoch_parsed(tmp_path):
    mod = _load()
    hot, arch = tmp_path / "hot.sqlite", tmp_path / "trackB.sqlite"
    _seed_hot(hot)
    mod.collect(hot, arch, now_epoch=1000)
    con = sqlite3.connect(arch)
    try:
        nulls = con.execute(
            "SELECT COUNT(*) FROM news_archive WHERE publish_epoch IS NULL").fetchone()[0]
    finally:
        con.close()
    assert nulls == 0   # all "2026-06-09 HH:MM:SS" timestamps parsed
