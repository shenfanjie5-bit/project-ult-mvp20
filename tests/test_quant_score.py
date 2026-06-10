"""Hermetic tests for mvp20.quant_score (two-layer quant shadow output)."""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pytest

from mvp20 import quant_score as qs


def _fake_params() -> dict:
    k = 10
    mag_bins = [{"n": 1000, "p_up": 0.5, "mean": 0.02 + 0.001 * i,
                 "mean_up": 0.08, "mean_down": -0.05,
                 "q10": -0.1, "q25": -0.04, "q50": 0.015, "q75": 0.07, "q90": 0.18}
                for i in range(k)]
    prob_bins = [{"n": 1000, "p_up": 0.45 + 0.008 * i, "mean": 0.0} for i in range(k)]
    return {
        "version": 1, "built_at": "2026-06-10 00:00:00",
        "liquid_frac": 0.70, "k_bins": k,
        "magnitude": {
            "features": ["sue", "npq_yoy"], "method": "ew_signed",
            "signs": {"sue": 1, "npq_yoy": 1}, "horizon_days": 20,
            "uni_mean": 0.0245, "bins": mag_bins, "oos": {},
        },
        "probability": {
            "features": ["ivol_60", "max5", "turnover_20", "ep_ttm", "cpt_heat5"],
            "method": "ic_weighted_frozen",
            "weights": {"ivol_60": -0.043, "max5": -0.044,
                        "turnover_20": -0.039, "ep_ttm": 0.034,
                        "cpt_heat5": -0.029},
            "theme_feature": {"name": "cpt_heat5"},
            "horizon_days": 10, "target": "P(beat median)",
            "base_rate": 0.4965, "top_bin_shrink": 0.5,
            "bins": prob_bins, "oos": {},
        },
        "caveats": ["c1", "c2"],
    }


def _fake_cross_section(n=400, seed=7):
    rng = np.random.default_rng(seed)
    codes = [f"{i:06d}.SZ" for i in range(1, n + 1)]
    feat_names = ["sue", "npq_yoy", "ivol_60", "max5", "turnover_20", "ep_ttm",
                  "cpt_heat5"]
    feat = rng.normal(size=(n, len(feat_names)))
    feat[:, 6] = np.abs(feat[:, 6])  # heat is non-negative
    lnmv = rng.normal(15.0, 1.2, size=n)
    industry = rng.integers(0, 8, size=n).astype(np.int32)
    return codes, feat, feat_names, lnmv, industry


def test_neutralize_shapes_and_rank_properties():
    codes, feat, names, lnmv, ind = _fake_cross_section()
    Z = qs.neutralize_cross_section(feat, lnmv, ind)
    assert Z.shape == feat.shape
    col = Z[np.isfinite(Z[:, 0]), 0]
    # rank-z: mean ~0, var ~1 (uniform scaled), bounded
    assert abs(col.mean()) < 0.05
    assert 0.8 < col.std() < 1.2
    assert np.abs(col).max() < math.sqrt(12) / 2 + 0.01


def test_build_rows_contract(tmp_path):
    params = _fake_params()
    codes, feat, names, lnmv, ind = _fake_cross_section()
    rows = qs.build_rows(codes, feat, names, lnmv, ind, params)
    assert len(rows) == len(codes)
    valid = [r for r in rows.values() if r.get("validated")]
    gated = [r for r in rows.values() if not r.get("validated")]
    # ~70% liquid gate
    assert 0.6 < len(valid) / len(codes) < 0.8
    assert all("liquid" in r["reason"] or "coverage" in r["reason"] for r in gated)
    r = valid[0]
    # honesty contract: NO absolute P(up); both layers present with horizons
    assert "p_up" not in json.dumps(r)
    assert r["mag"]["horizon_days"] == 20 and r["prob"]["horizon_days"] == 10
    assert r["mag"]["q10"] < r["mag"]["exp_excess"] < r["mag"]["q90"]
    assert abs(r["prob"]["p_beat_median"] - (r["prob"]["base_rate"]
               + r["prob"]["tilt_pp"] / 100.0)) < 2e-3


def test_top_bin_shrink_applied():
    params = _fake_params()
    codes, feat, names, lnmv, ind = _fake_cross_section()
    rows = qs.build_rows(codes, feat, names, lnmv, ind, params)
    base = params["probability"]["base_rate"]
    raw_top = params["probability"]["bins"][-1]["p_up"]            # 0.522
    shrunk = base + 0.5 * (raw_top - base)
    p_values = {r["prob"]["p_beat_median"] for r in rows.values() if r.get("validated")}
    assert round(shrunk, 3) in p_values
    assert round(raw_top, 3) not in p_values  # raw extreme never emitted


def test_artifact_roundtrip_and_lookup(tmp_path):
    params = _fake_params()
    codes, feat, names, lnmv, ind = _fake_cross_section()
    art = qs.build_artifact("20260610", codes, feat, names, lnmv, ind, params)
    assert art["n_rows"] == len(codes) and art["n_validated"] > 0
    qs.save_artifact(art, root=tmp_path)
    got = qs.lookup(codes[0], root=tmp_path, today="20260612")
    assert got["available"] is True
    assert got["stale"] is False
    assert got["asof"] == "20260610"
    assert got["caveats"] == ["c1", "c2"]
    missing = qs.lookup("999999.SZ", root=tmp_path, today="20260612")
    assert missing["available"] is False


def test_staleness_degrades_validated(tmp_path):
    params = _fake_params()
    codes, feat, names, lnmv, ind = _fake_cross_section()
    art = qs.build_artifact("20260501", codes, feat, names, lnmv, ind, params)
    qs.save_artifact(art, root=tmp_path)
    # pick a validated row
    ts = next(t for t, r in art["rows"].items() if r.get("validated"))
    got = qs.lookup(ts, root=tmp_path, today="20260610")  # 40 days later
    assert got["stale"] is True
    assert got["validated"] is False
    assert "older than" in got["reason"]


def test_lookup_no_artifact_is_honest(tmp_path):
    got = qs.lookup("000001.SZ", root=tmp_path / "void")
    assert got["available"] is False
    assert "not built" in got["reason"]


def test_server_quant_block_best_effort(monkeypatch, tmp_path):
    from mvp20 import server

    # no artifact -> honest false, never raises
    monkeypatch.setattr(qs, "ARTIFACT_DIR", tmp_path / "void")
    block = server._quant_block("000001.SZ")
    assert block["available"] is False
    # non-A-share short-circuits
    block_us = server._quant_block("AAPL")
    assert block_us["available"] is False and "A-share" in block_us["reason"]


def test_golden_parity_with_research_stack():
    """Golden pin: the production neutralization+binning must stay bit-equal to
    the audited research stack (factor_research harness/caliblib) on a shared
    synthetic fixture. The parity skeptic verified this on the real panel; this
    test keeps it true forever. Skips if the research modules can't import."""

    pytest.importorskip("factor_research.model.harness")
    import numpy as np
    from factor_research.model import harness as H
    from factor_research.model.caliblib import score_bins

    rng = np.random.default_rng(20260610)
    n, f = 600, 6
    feat = rng.normal(size=(1, n, f)).astype(np.float64)
    feat[0, rng.integers(0, n, 40), rng.integers(0, f, 40)] = np.nan
    lnmv = rng.normal(15.0, 1.0, size=(1, n))
    industry = rng.integers(0, 6, size=n).astype(np.int32)

    z = {"feat": feat, "ln_mv": lnmv, "industry": industry}
    Z_research = H.neutralize(z, None, cache=False)[0]
    Z_prod = qs.neutralize_cross_section(feat[0], lnmv[0], industry)
    both = np.isfinite(Z_research) & np.isfinite(Z_prod)
    assert np.isnan(Z_research).sum() == np.isnan(Z_prod).sum()
    assert np.allclose(Z_research[both], Z_prod[both], atol=1e-9)

    # binning parity on a composite score
    score = np.where(np.isfinite(Z_prod).mean(1) >= 0.5,
                     np.nan_to_num(Z_prod, nan=0.0) @ np.array([1, 1, -1, -1, -1, 1.0]),
                     np.nan)
    ok_mv = np.isfinite(lnmv[0])
    thr = np.percentile(lnmv[0][ok_mv], 30)
    mask = ok_mv & (lnmv[0] >= thr)
    b_research = score_bins(score, mask, 10)
    b_prod = qs._bin_of(score, mask, 10)
    assert (b_research == b_prod).all()


def test_score_endpoint_carries_quant_block(tmp_path, monkeypatch):
    """/score envelope must carry the quant block when an artifact exists, and
    still return 200 when the artifact is absent."""

    params = _fake_params()
    codes, feat, names, lnmv, ind = _fake_cross_section()
    art = qs.build_artifact("20260610", codes, feat, names, lnmv, ind, params)
    qs.save_artifact(art, root=tmp_path)
    monkeypatch.setattr(qs, "ARTIFACT_DIR", tmp_path)

    from mvp20 import server

    block = server._quant_block(codes[0])
    assert block["available"] is True
    assert "mag" in block or block.get("validated") is False
    # absent artifact -> degrade, never raise
    monkeypatch.setattr(qs, "ARTIFACT_DIR", tmp_path / "absent")
    block2 = server._quant_block(codes[0])
    assert block2["available"] is False


def test_theme_block_present_and_overheat_decile():
    params = _fake_params()
    codes, feat, names, lnmv, ind = _fake_cross_section()
    rows = qs.build_rows(codes, feat, names, lnmv, ind, params)
    themed = [r for r in rows.values() if r.get("validated") and "theme" in r]
    assert themed, "theme block missing despite finite heat column"
    hot = [r for r in themed if r["theme"]["overheat"]]
    frac = len(hot) / len(themed)
    assert 0.05 < frac < 0.15  # ~top decile flagged
    assert all(r["theme"]["heat_pct"] >= 90.0 for r in hot)


def test_theme_block_absent_when_column_nan():
    params = _fake_params()
    codes, feat, names, lnmv, ind = _fake_cross_section()
    feat = feat.copy()
    feat[:, names.index("cpt_heat5")] = np.nan  # stale 打板 archive
    rows = qs.build_rows(codes, feat, names, lnmv, ind, params)
    valid = [r for r in rows.values() if r.get("validated")]
    assert valid, "rows must still validate on the remaining 4 prob features"
    assert all("theme" not in r for r in valid)


def test_ranking_handler_joins_snapshot_and_quant(tmp_path, monkeypatch):
    from mvp20 import pnl_loop, server

    # quant artifact
    params = _fake_params()
    codes, feat, names, lnmv, ind = _fake_cross_section(n=200)
    art = qs.build_artifact("20260610", codes, feat, names, lnmv, ind, params)
    qs.save_artifact(art, root=tmp_path)
    monkeypatch.setattr(qs, "ARTIFACT_DIR", tmp_path)

    # snapshot db (base_score monotone in index; top quarter BUY)
    db = tmp_path / "pnl.sqlite"
    monkeypatch.setattr(pnl_loop, "DEFAULT_DB", db)
    from pit_backtest import store as pstore
    rows = [{"ts_code": ts, "base_date": "20260610",
             "base_score": i / 100.0, "trading_signal": "BUY" if i > 150 else "HOLD",
             "short_total": 0, "medium_total": 0, "long_total": 0, "mode": "x"}
            for i, ts in enumerate(codes)]
    pstore.put_scores(rows, db)

    status, env = server.handle_ranking(server.ServerConfig(), {})
    assert status == 200
    d = env["data"]
    assert d["asof_snapshot"] == "20260610" and d["asof_quant"] == "20260610"
    assert d["total"] == 200 and len(d["rows"]) == 50
    # default sort: quant_mag desc — validated rows first, descending pct
    top = d["rows"][0]
    assert top["quant_validated"] and top["quant"]["mag_score_pct"] > 99
    # base_score percentile present and consistent
    assert d["rows"][0]["base_score_pct"] is not None
    # sort by base_score: highest base first
    status, env = server.handle_ranking(server.ServerConfig(), {"sort": ["base_score"]})
    assert env["data"]["rows"][0]["base_score"] == max(r["base_score"] for r in rows)
    # signal filter
    status, env = server.handle_ranking(server.ServerConfig(), {"signal": ["BUY"]})
    assert all(r["trading_signal"] == "BUY" for r in env["data"]["rows"])
    # bad sort -> 400
    status, _ = server.handle_ranking(server.ServerConfig(), {"sort": ["bogus"]})
    assert status == 400


def test_ranking_handler_empty_is_honest(tmp_path, monkeypatch):
    from mvp20 import pnl_loop, server
    monkeypatch.setattr(pnl_loop, "DEFAULT_DB", tmp_path / "none.sqlite")
    monkeypatch.setattr(qs, "ARTIFACT_DIR", tmp_path / "void")
    status, env = server.handle_ranking(server.ServerConfig(), {})
    assert status == 200
    assert env["data"]["rows"] == [] and env["data"]["total"] == 0
