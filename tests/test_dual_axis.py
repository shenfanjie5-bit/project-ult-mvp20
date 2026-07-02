"""RD-A dual-axis (parallel v2) — matrix semantics + snapshot/eval plumbing."""
from __future__ import annotations

import pytest

from mvp20.scoring import (
    MERIT_BAND, TIMING_BAND, TIMING_DEEP_NEGATIVE, dual_axis_signal)


def test_matrix_core_semantics():
    # the RD-A failure mode: strong merit + poor timing must NOT be AVOID
    assert dual_axis_signal(0.5, -0.3) == "HOLD"
    assert dual_axis_signal(0.5, -0.6) == "WATCH"   # deep-negative timing degrades
    assert dual_axis_signal(0.5, 0.5) == "BUY"
    assert dual_axis_signal(0.5, 0.0) == "HOLD"
    # weak merit
    assert dual_axis_signal(-0.5, -0.5) == "AVOID"
    assert dual_axis_signal(-0.5, 0.5) == "WATCH"   # 差公司好时机 → 不追
    # neutral merit
    assert dual_axis_signal(0.0, 0.5) == "HOLD"
    assert dual_axis_signal(0.0, -0.5) == "WATCH"
    # a strong-merit name can NEVER be AVOID, anywhere on the timing axis
    for t in (-2.0, -1.0, -0.51, -0.2, 0.0, 0.3, 1.0):
        assert dual_axis_signal(MERIT_BAND + 0.01, t) != "AVOID"


def test_matrix_band_edges():
    eps = 1e-9
    assert dual_axis_signal(MERIT_BAND + eps, TIMING_BAND + eps) == "BUY"
    assert dual_axis_signal(MERIT_BAND - eps, TIMING_BAND + eps) == "HOLD"
    assert dual_axis_signal(MERIT_BAND + eps, TIMING_DEEP_NEGATIVE - eps) == "WATCH"
    assert dual_axis_signal(-MERIT_BAND - eps, -TIMING_BAND - eps) == "AVOID"


def test_score_company_emits_dual_axis():
    """merit + timing must exactly decompose the core unweighted base, and the
    v2 signal must ride along — without touching v1 fields."""

    from mvp20.scoring import score_company

    overlay = {
        "ts_code": "000001.SZ",
        "industry_id": "TEST",
        "company_layer": {"nodes": []},
    }
    res = score_company(stock_overlay=overlay, aggregated_nodes={},
                        coverage_report={}, realtime_data={})
    assert "merit" in res and "timing" in res and "trading_signal_v2" in res
    core_base = res["core_final_score"]["base_score"]
    assert res["merit"] + res["timing"] == pytest.approx(core_base, abs=1e-9)
    assert res["trading_signal_v2"] in ("BUY", "HOLD", "WATCH", "AVOID")
    assert res["trading_signal"] in ("BUY", "HOLD", "WATCH", "AVOID")  # v1 intact


def test_snapshot_persists_v2_and_eval_compares(tmp_path):
    from mvp20 import pnl_loop
    from tests.test_pnl_loop import (
        SESSIONS, _closes_fn_factory, _mk_universe, _score_fn_factory)

    db = tmp_path / "pnl.sqlite"
    uni = _mk_universe(120)
    base = _score_fn_factory(uni)

    def with_v2(ts):
        r = base(ts)
        # v2 inverts v1's BUY/AVOID for a visible comparison
        r["merit"] = -float(r["base_score"])
        r["timing"] = 0.0
        r["signal_v2"] = {"BUY": "AVOID", "AVOID": "BUY"}.get(
            r["trading_signal"], "HOLD")
        return r

    pnl_loop.snapshot_scores(SESSIONS[0], uni, with_v2, db_path=db)
    bd, rows = pnl_loop.latest_snapshot(db)
    assert bd == SESSIONS[0]
    one = next(iter(rows.values()))
    assert "signal_v2" in one and "merit" in one

    pnl_loop.fill_returns(SESSIONS, _closes_fn_factory(uni), db_path=db,
                          horizons=(5,))
    pnl_loop.evaluate(db_path=db, horizons=(5,))
    m = pnl_loop.read_eval(db, horizon=5)[0]
    assert "signal_buckets_v2" in m
    # v1's BUY beats its AVOID (score-linked alpha); v2 inverted -> opposite
    assert m["buy_minus_avoid"] > 0
    assert m["buy_minus_avoid_v2"] < 0


def test_signal_evidence_abstain_floor():
    """G8: a signal off a thin evidence base carries abstain=True; the signal
    string itself is untouched (display-layer contract)."""

    from mvp20.scoring import SIGNAL_EVIDENCE_FLOOR, score_company

    overlay = {"ts_code": "000001.SZ", "industry_id": "TEST",
               "company_layer": {"nodes": []}}
    res = score_company(stock_overlay=overlay, aggregated_nodes={},
                        coverage_report={}, realtime_data={})
    ev = res["signal_evidence"]
    assert ev["n_known_fields"] == 0 and ev["n_realtime_nodes"] == 0
    assert ev["abstain"] is True
    assert ev["floor"] == SIGNAL_EVIDENCE_FLOOR
    assert res["trading_signal"] in ("BUY", "HOLD", "WATCH", "AVOID")  # untouched


def test_nan_axes_hold_not_avoid():
    nan = float("nan")
    assert dual_axis_signal(nan, -0.5) == "HOLD"
    assert dual_axis_signal(0.5, nan) == "HOLD"
    assert dual_axis_signal(nan, nan) == "HOLD"


def test_market_risk_charges_timing_not_merit():
    """Review fix: an L8.val/L8.cap (market-type) risk node must depress the
    TIMING axis; an L8.fin (company-type) node must depress MERIT. Decomposition
    M+T == core base must hold either way."""

    from mvp20.scoring import score_company

    overlay = {"ts_code": "000001.SZ", "industry_id": "TEST",
               "company_layer": {"nodes": []}}

    def risk_node(nid):
        return {nid: {"score": -0.8, "score_target": "risk_discount",
                      "confidence": 1.0, "participates_in_score": True,
                      "direction": "negative"}}

    mkt = score_company(stock_overlay=overlay,
                        aggregated_nodes=risk_node("000001.SZ:L8.val.overvalued:rt"),
                        coverage_report={}, realtime_data={})
    com = score_company(stock_overlay=overlay,
                        aggregated_nodes=risk_node("000001.SZ:L8.fin.cash_ar:rt"),
                        coverage_report={}, realtime_data={})
    # market-type: timing takes the hit, merit untouched relative to company-type
    assert mkt["timing"] < com["timing"]
    assert mkt["merit"] > com["merit"]
    for res in (mkt, com):
        assert res["merit"] + res["timing"] == pytest.approx(
            res["core_final_score"]["base_score"], abs=1e-9)


def test_scores_v2_schema_migration(tmp_path):
    """An existing pnl.sqlite with the pre-scored_at scores_v2 table must be
    migrated by _init (CREATE IF NOT EXISTS alone won't add columns)."""

    import sqlite3
    from mvp20 import pnl_loop

    db = tmp_path / "pnl.sqlite"
    with sqlite3.connect(str(db)) as c:
        c.execute("CREATE TABLE scores_v2 (ts_code TEXT, base_date TEXT,"
                  " merit REAL, timing REAL, signal_v2 TEXT,"
                  " PRIMARY KEY (ts_code, base_date))")
    pnl_loop._init(db)
    pnl_loop._put_scores_v2(
        [{"ts_code": "000001.SZ", "base_date": "20260610",
          "merit": 0.1, "timing": 0.2, "signal_v2": "HOLD"}], db)
    with sqlite3.connect(str(db)) as c:
        row = c.execute("SELECT signal_v2, scored_at FROM scores_v2").fetchone()
    assert row[0] == "HOLD" and row[1] is not None
