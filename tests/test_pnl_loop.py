"""Hermetic tests for the production P&L feedback loop (mvp20.pnl_loop).

No network, no hot.sqlite: score_fn / closes_fn / sessions are injected.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from mvp20 import pnl_loop
from pit_backtest import store as pstore

# 12 ascending fake sessions
SESSIONS = [f"202601{d:02d}" for d in range(2, 14)]


def _mk_universe(n=120):
    return [f"{i:06d}.SZ" for i in range(1, n + 1)]


def _score_fn_factory(universe):
    """Deterministic scores: stock i gets base_score = i/n - 0.5 (monotone),
    signal BUY for the top quarter, AVOID for the bottom quarter."""

    n = len(universe)
    rank = {ts: i for i, ts in enumerate(universe)}

    def score(ts):
        i = rank[ts]
        s = i / (n - 1) - 0.5
        sig = "BUY" if i >= 3 * n // 4 else ("AVOID" if i < n // 4 else "HOLD")
        return {
            "ts_code": ts, "base_score": s, "core_base_score": s,
            "short_total": s, "medium_total": s, "long_total": s,
            "trading_signal": sig, "mode": "trend",
        }

    return score


def _closes_fn_factory(universe, drift_per_session=0.01, score_alpha=0.02):
    """Synthetic close paths: every stock starts at 10.0 and compounds
    drift + (score-linked alpha) per session — so higher-scored stocks
    genuinely outperform and metrics must come out positive."""

    n = len(universe)
    rank = {ts: i for i, ts in enumerate(universe)}
    sess_idx = {d: k for k, d in enumerate(SESSIONS)}

    def closes(date):
        k = sess_idx[date]
        out = {}
        for ts in universe:
            edge = (rank[ts] / (n - 1) - 0.5) * score_alpha
            out[ts] = 10.0 * (1.0 + drift_per_session + edge) ** k
        return out

    return closes


@pytest.fixture()
def db(tmp_path) -> Path:
    return tmp_path / "pnl.sqlite"


def test_snapshot_resume_and_counts(db):
    uni = _mk_universe(60)
    score_fn = _score_fn_factory(uni)
    r1 = pnl_loop.snapshot_scores(SESSIONS[0], uni, score_fn, db_path=db)
    assert r1["scored"] == 60 and r1["failed"] == 0
    # resume: full snapshot present -> skip
    r2 = pnl_loop.snapshot_scores(SESSIONS[0], uni, score_fn, db_path=db)
    assert r2["status"] == "complete" and r2["scored"] == 0
    assert pstore.scored_base_dates(db)[SESSIONS[0]] == 60


def test_snapshot_partial_resume(db):
    uni = _mk_universe(40)
    score_fn = _score_fn_factory(uni)
    flaky_calls = {"n": 0}

    def flaky(ts):
        flaky_calls["n"] += 1
        if uni.index(ts) >= 20:
            return None  # simulate failures for back half
        return score_fn(ts)

    r1 = pnl_loop.snapshot_scores(SESSIONS[0], uni, flaky, db_path=db)
    assert r1["scored"] == 20 and r1["failed"] == 20
    # second run with healthy fn only scores the missing 20
    r2 = pnl_loop.snapshot_scores(SESSIONS[0], uni, score_fn, db_path=db)
    assert r2["scored"] == 20 and r2["skipped"] == 20


def test_matured_pairs_gating():
    snaps = [SESSIONS[0], SESSIONS[5], SESSIONS[11], "20991231"]
    pairs = pnl_loop.matured_pairs(snaps, SESSIONS, horizons=(5, 10))
    # SESSIONS[0]: idx 0 -> h5 matures at idx5, h10 at idx10 (both < 12) ✓✓
    # SESSIONS[5]: h5 matures at idx10 ✓, h10 would be idx15 ✗
    # SESSIONS[11] (last): nothing matured; unknown date ignored
    assert (SESSIONS[0], SESSIONS[5], 5) in pairs
    assert (SESSIONS[0], SESSIONS[10], 10) in pairs
    assert (SESSIONS[5], SESSIONS[10], 5) in pairs
    assert all(b != SESSIONS[11] for b, _, _ in pairs)
    assert all(b != "20991231" for b, _, _ in pairs)
    assert len(pairs) == 3


def test_fill_returns_and_math(db):
    uni = _mk_universe(80)
    pnl_loop.snapshot_scores(SESSIONS[0], uni, _score_fn_factory(uni), db_path=db)
    closes_fn = _closes_fn_factory(uni)
    r = pnl_loop.fill_returns(SESSIONS, closes_fn, db_path=db, horizons=(5, 10))
    assert r["status"] == "ok" and r["filled"] == 160  # 80 stocks x 2 horizons
    # spot-check the math for one stock
    rows = pstore.read_returns(db)
    one = next(x for x in rows if x["horizon_d"] == 5 and x["ts_code"] == uni[-1])
    expect = closes_fn(SESSIONS[5])[uni[-1]] / closes_fn(SESSIONS[0])[uni[-1]] - 1.0
    assert one["status"] == "ok"
    assert abs(one["fwd_ret"] - expect) < 1e-12
    # idempotent: second call fills nothing
    r2 = pnl_loop.fill_returns(SESSIONS, closes_fn, db_path=db, horizons=(5, 10))
    assert r2["status"] == "up_to_date" and r2["filled"] == 0


def test_fill_returns_missing_close_status(db):
    uni = _mk_universe(60)
    pnl_loop.snapshot_scores(SESSIONS[0], uni, _score_fn_factory(uni), db_path=db)
    base_closes = _closes_fn_factory(uni)

    def gappy(date):
        out = dict(base_closes(date))
        out.pop(uni[0], None)  # stock 0 suspended at every date
        return out

    pnl_loop.fill_returns(SESSIONS, gappy, db_path=db, horizons=(5,))
    rows = pstore.read_returns(db)
    bad = [x for x in rows if x["ts_code"] == uni[0]]
    assert bad and all(x["status"] == "missing_close" and x["fwd_ret"] is None
                       for x in bad)


def test_evaluate_metrics_and_signal_buckets(db):
    uni = _mk_universe(120)
    pnl_loop.snapshot_scores(SESSIONS[0], uni, _score_fn_factory(uni), db_path=db)
    pnl_loop.fill_returns(SESSIONS, _closes_fn_factory(uni), db_path=db,
                          horizons=(5, 10))
    out = pnl_loop.evaluate(db_path=db, horizons=(5, 10))
    assert out["eval_written"] == 2
    ms = pnl_loop.read_eval(db, horizon=5)
    assert len(ms) == 1
    m = ms[0]
    # score-linked alpha was built into the closes: metrics must be positive
    assert m["rank_ic"] > 0.9            # monotone by construction
    assert m["q5_q1"] > 0
    assert m["top_excess"] > 0
    assert m["signal_buckets"]["BUY"]["mean_ret"] > m["signal_buckets"]["AVOID"]["mean_ret"]
    assert m["buy_minus_avoid"] > 0
    assert m["n"] == 120


def test_evaluate_skips_thin_cross_sections(db):
    uni = _mk_universe(30)  # < 50 joined rows -> no eval row
    pnl_loop.snapshot_scores(SESSIONS[0], uni, _score_fn_factory(uni), db_path=db)
    pnl_loop.fill_returns(SESSIONS, _closes_fn_factory(uni), db_path=db,
                          horizons=(5,))
    out = pnl_loop.evaluate(db_path=db, horizons=(5,))
    assert out["eval_written"] == 0
    assert pnl_loop.read_eval(db) == []


def test_derate_flag_fires_on_negative_top_excess(db):
    """Universe where HIGH score -> LOW return; with >=DERATE_MIN_DATES matured
    dates the rolling CI must sit below 0 and flag de_rated."""

    uni = _mk_universe(100)
    score_fn = _score_fn_factory(uni)
    # 9 snapshot dates, each maturing at h=1 within SESSIONS
    closes_fn = _closes_fn_factory(uni, score_alpha=-0.05)  # inverted alpha
    for d in SESSIONS[:9]:
        pnl_loop.snapshot_scores(d, uni, score_fn, db_path=db)
    pnl_loop.fill_returns(SESSIONS, closes_fn, db_path=db, horizons=(1,))
    out = pnl_loop.evaluate(db_path=db, horizons=(1,))
    roll = out["rolling"]["1"]
    assert roll["n_dates"] >= pnl_loop.DERATE_MIN_DATES
    assert roll["top_excess_mean"] < 0
    assert roll["de_rated"] is True
    # and the positive-alpha twin must NOT de-rate
    db2 = db.parent / "pnl2.sqlite"
    closes_pos = _closes_fn_factory(uni, score_alpha=0.05)
    for d in SESSIONS[:9]:
        pnl_loop.snapshot_scores(d, uni, score_fn, db_path=db2)
    pnl_loop.fill_returns(SESSIONS, closes_pos, db_path=db2, horizons=(1,))
    out2 = pnl_loop.evaluate(db_path=db2, horizons=(1,))
    assert out2["rolling"]["1"]["de_rated"] is False


def test_server_handler_serves_eval(db, monkeypatch):
    uni = _mk_universe(80)
    pnl_loop.snapshot_scores(SESSIONS[0], uni, _score_fn_factory(uni), db_path=db)
    pnl_loop.fill_returns(SESSIONS, _closes_fn_factory(uni), db_path=db,
                          horizons=(5, 10))
    pnl_loop.evaluate(db_path=db, horizons=(5, 10))

    monkeypatch.setattr(pnl_loop, "DEFAULT_DB", db)
    from mvp20.server import ServerConfig, handle_pnl_backtests

    status, env = handle_pnl_backtests(ServerConfig(), {})
    assert status == 200
    data = env["data"]
    assert data["total"] == 2
    assert data["rolling_summary"]["horizons"]
    # horizon filter
    status, env = handle_pnl_backtests(ServerConfig(), {"horizon": ["5"]})
    assert status == 200
    assert all(r["horizon_d"] == 5 for r in env["data"]["backtests"])
    # bad horizon -> 400
    status, _ = handle_pnl_backtests(ServerConfig(), {"horizon": ["abc"]})
    assert status == 400


def test_server_handler_empty_db_is_honest(tmp_path, monkeypatch):
    from mvp20 import pnl_loop as pl
    monkeypatch.setattr(pl, "DEFAULT_DB", tmp_path / "nope.sqlite")
    from mvp20.server import ServerConfig, handle_pnl_backtests

    status, env = handle_pnl_backtests(ServerConfig(), {})
    assert status == 200
    assert env["data"]["backtests"] == [] and env["data"]["total"] == 0
    assert env["data"]["rolling_summary"] is None
