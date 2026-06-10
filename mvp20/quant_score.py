"""涨幅预测分数 (two-layer quant score) — production shadow output.

Capability gaps G2/G3/G6: attaches the RESEARCH-VALIDATED two-layer model
(magnitude = earnings-surprise PEAD at +20d; probability = low-vol/low-turnover
/cheap P(beat median) tilt at +10d) as a PARALLEL output. It never touches
base_score — fusing the layers (or fusing into base_score) was adversarially
falsified (tail-anti-alignment, REPORT_PROB.md §5.4).

Pattern mirrors ``event_coefficient.py`` (honesty contract) + ``peer_context``
(offline batch artifact, <10ms request-path load):

  research (factor_research/model/export_params.py, monthly)
      -> config/quant_score_params.json        FROZEN calibration
  offline builder (scripts/build_quant_scores.py, nightly after data refresh)
      -> runtime/quant_score/A_share.json      per-stock blocks
  request path (server.handle_score)
      -> load_artifact() + lookup()            attach ``quant`` block

Honesty contract (enforced here, ride-along to the UI):
  * validated:true ONLY inside the liquid top-70% cross-section; outside the
    gate the block says validated:false with the reason.
  * NO absolute P(up) — only P(beat same-day liquid median) = base_rate ± tilt
    (absolute up-probability is market-dominated; OOS base rate 0.12..0.97).
  * the extreme high-P bin's tilt is shrunk (verified under-delivery).
  * artifacts carry ``asof``; the server marks blocks stale after
    ``STALE_AFTER_DAYS`` so old features never masquerade as fresh signal.

The numeric recipe (winsorize -> z -> residualize on [1, ln_mv, industry] ->
rank-z, NaN->0 after ranking, min coverage 0.5) is a 1:1 port of the audited
``factor_research/model/harness.py`` neutralization — kept dependency-free
here because mvp20 must not import from factor_research/ (the builder script
may; request path must not).
"""
from __future__ import annotations

import json
import math
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping, Sequence

PARAMS_PATH = Path("config/quant_score_params.json")
ARTIFACT_DIR = Path("runtime/quant_score")
STALE_AFTER_DAYS = 10
MIN_FEATURE_COV = 0.5

# ---------------------------------------------------------------------------
# params + artifact I/O
# ---------------------------------------------------------------------------

_params_cache: dict[str, Any] = {}
_artifact_cache: dict[str, Any] = {}


def load_params(path: Path | None = None) -> dict | None:
    p = Path(path or PARAMS_PATH)
    if not p.exists():
        return None
    key = str(p)
    mtime = p.stat().st_mtime
    hit = _params_cache.get(key)
    if hit and hit[0] == mtime:
        return hit[1]
    data = json.loads(p.read_text())
    _params_cache[key] = (mtime, data)
    return data


def artifact_path(market: str = "A_share", root: Path | None = None) -> Path:
    return Path(root or ARTIFACT_DIR) / f"{market}.json"


def load_artifact(market: str = "A_share", root: Path | None = None) -> dict | None:
    p = artifact_path(market, root)
    if not p.exists():
        return None
    key = str(p)
    mtime = p.stat().st_mtime
    hit = _artifact_cache.get(key)
    if hit and hit[0] == mtime:
        return hit[1]
    data = json.loads(p.read_text())
    _artifact_cache[key] = (mtime, data)
    return data


def is_stale(artifact: Mapping[str, Any], today: str | None = None) -> bool:
    asof = str(artifact.get("asof") or "")
    if len(asof) != 8:
        return True
    today = today or datetime.now().strftime("%Y%m%d")
    try:
        d0 = datetime.strptime(asof, "%Y%m%d")
        d1 = datetime.strptime(today, "%Y%m%d")
    except ValueError:
        return True
    return (d1 - d0).days > STALE_AFTER_DAYS


def lookup(ts_code: str, market: str = "A_share", root: Path | None = None,
           today: str | None = None) -> dict:
    """Request-path accessor: the per-stock quant block, or an honest
    ``available:false`` envelope. Never raises."""

    try:
        art = load_artifact(market, root)
    except Exception:  # noqa: BLE001
        art = None
    if not art:
        return {"available": False,
                "reason": "quant artifact not built (scripts/build_quant_scores.py)"}
    row = (art.get("rows") or {}).get(ts_code)
    if row is None:
        return {"available": False, "asof": art.get("asof"),
                "reason": "ts_code not in scored cross-section"}
    out = dict(row)
    out["available"] = True
    out["asof"] = art.get("asof")
    out["params_built_at"] = art.get("params_built_at")
    out["stale"] = is_stale(art, today)
    if out["stale"]:
        out["validated"] = False
        out["reason"] = f"artifact asof {art.get('asof')} older than {STALE_AFTER_DAYS}d"
    out["caveats"] = art.get("caveats") or []
    return out


# ---------------------------------------------------------------------------
# neutralization — 1:1 port of harness._winsor_z/_rank_z/neutralize (audited)
# ---------------------------------------------------------------------------


def _winsor_z(v: "np.ndarray", lo: float = 1, hi: float = 99) -> "np.ndarray":
    import numpy as np
    out = np.full_like(v, np.nan, dtype=np.float64)
    ok = np.isfinite(v)
    if ok.sum() < 10:
        return out
    x = v[ok].astype(np.float64)
    a, b = np.percentile(x, [lo, hi])
    x = np.clip(x, a, b)
    mu, sd = x.mean(), x.std(ddof=1)
    if sd <= 0:
        return out
    out[ok] = (x - mu) / sd
    return out


def _rank_z(v: "np.ndarray") -> "np.ndarray":
    import numpy as np
    out = np.full_like(v, np.nan, dtype=np.float64)
    ok = np.isfinite(v)
    nz = int(ok.sum())
    if nz < 10:
        return out
    x = v[ok]
    order = np.argsort(np.argsort(x))
    u = (order + 1.0) / (nz + 1.0)
    out[ok] = (u - 0.5) * math.sqrt(12.0)
    return out


def neutralize_cross_section(feat: "np.ndarray", lnmv: "np.ndarray",
                             industry: "np.ndarray") -> "np.ndarray":
    """feat [N,F] one date -> neutralized rank-z [N,F]."""
    import numpy as np
    N, F = feat.shape
    ind_u = sorted({int(i) for i in industry if i >= 0})
    Dind = np.zeros((N, len(ind_u)))
    for k, code in enumerate(ind_u):
        Dind[:, k] = (industry == code).astype(float)
    Z = np.full((N, F), np.nan)
    for fi in range(F):
        v = _winsor_z(feat[:, fi].astype(np.float64))
        ok = np.isfinite(v) & np.isfinite(lnmv)
        if ok.sum() < 20:
            Z[:, fi] = _rank_z(v)
            continue
        di = Dind[ok]
        di = di[:, di.sum(0) > 0]
        X = np.column_stack([np.ones(int(ok.sum())), lnmv[ok], di])
        y = v[ok]
        try:
            beta, *_ = np.linalg.lstsq(X, y, rcond=None)
            resid = y - X @ beta
        except Exception:  # noqa: BLE001
            resid = y - y.mean()
        rv = np.full(N, np.nan)
        rv[ok] = resid
        Z[:, fi] = _rank_z(rv)
    return Z


# ---------------------------------------------------------------------------
# scoring (builder-side; pure numpy + frozen params)
# ---------------------------------------------------------------------------


def _bin_of(score: "np.ndarray", eligible: "np.ndarray", k: int) -> "np.ndarray":
    """equal-count score-rank bins over the eligible cross-section (-1 outside)."""
    import numpy as np
    out = np.full(score.shape, -1, dtype=np.int32)
    ok = np.isfinite(score) & eligible
    n = int(ok.sum())
    if n < k * 3:
        return out
    r = np.argsort(np.argsort(score[ok]))
    out[ok] = np.minimum((r * k) // n, k - 1)
    return out


def build_rows(codes: Sequence[str], feat: "np.ndarray", feat_names: Sequence[str],
               lnmv: "np.ndarray", industry: "np.ndarray",
               params: Mapping[str, Any]) -> dict[str, dict]:
    """Score one cross-section through the frozen calibration.

    ``feat`` [N,F] raw features named ``feat_names`` (must cover the union of
    magnitude+probability features), ``lnmv`` log market cap (raw, for the
    liquid gate AND the neutralizer), ``industry`` int codes (-1 unknown).
    """
    import numpy as np

    k = int(params["k_bins"])
    liquid_frac = float(params["liquid_frac"])
    mag_p, prob_p = params["magnitude"], params["probability"]
    name_idx = {f: i for i, f in enumerate(feat_names)}
    for f in list(mag_p["features"]) + list(prob_p["features"]):
        if f not in name_idx:
            raise ValueError(f"feature {f!r} missing from builder output")

    Z = neutralize_cross_section(feat, lnmv, industry)

    # liquid gate: largest liquid_frac by raw market cap among finite rows
    ok_mv = np.isfinite(lnmv)
    eligible = np.zeros(len(codes), bool)
    if ok_mv.sum() >= 50:
        thr = np.percentile(lnmv[ok_mv], 100 * (1 - liquid_frac))
        eligible = ok_mv & (lnmv >= thr)

    def composite(features: Sequence[str], weights: Mapping[str, float]) -> "np.ndarray":
        idx = [name_idx[f] for f in features]
        sub = Z[:, idx]
        cov = np.isfinite(sub).mean(axis=1)
        Xi = np.where(np.isfinite(sub), sub, 0.0)
        w = np.array([weights[f] for f in features])
        s = Xi @ w
        s[cov < MIN_FEATURE_COV] = np.nan
        return s

    mag_score = composite(mag_p["features"],
                          {f: float(s) for f, s in mag_p["signs"].items()})
    prob_score = composite(prob_p["features"], prob_p["weights"])

    mb = _bin_of(mag_score, eligible, k)
    pb = _bin_of(prob_score, eligible, k)

    # magnitude percentile within the eligible cross-section
    pct = np.full(len(codes), np.nan)
    okm = np.isfinite(mag_score) & eligible
    if okm.sum() > 10:
        r = np.argsort(np.argsort(mag_score[okm]))
        pct[okm] = 100.0 * r / (okm.sum() - 1)

    uni_mean = float(mag_p["uni_mean"])
    base_rate = float(prob_p["base_rate"])
    shrink = float(prob_p.get("top_bin_shrink", 1.0))
    rows: dict[str, dict] = {}
    for j, ts in enumerate(codes):
        if not eligible[j]:
            if np.isfinite(lnmv[j]):
                rows[ts] = {
                    "validated": False,
                    "reason": "outside liquid top-%d%% gate (model unvalidated there)"
                              % round(liquid_frac * 100),
                }
            continue
        if mb[j] < 0 or pb[j] < 0:
            rows[ts] = {"validated": False, "reason": "insufficient feature coverage"}
            continue
        m = mag_p["bins"][int(mb[j])]
        p = prob_p["bins"][int(pb[j])]
        p_beat = float(p["p_up"])
        if int(pb[j]) == k - 1:  # verified under-delivery of the extreme bin
            p_beat = base_rate + shrink * (p_beat - base_rate)
        rows[ts] = {
            "validated": True,
            "mag": {
                "score_pct": round(float(pct[j]), 1),
                "horizon_days": int(mag_p["horizon_days"]),
                "exp_excess": round(float(m["mean"]) - uni_mean, 4),
                "q10": round(float(m["q10"]), 4),
                "q90": round(float(m["q90"]), 4),
                "mean_if_up": round(float(m["mean_up"]), 4),
            },
            "prob": {
                "horizon_days": int(prob_p["horizon_days"]),
                "p_beat_median": round(p_beat, 3),
                "tilt_pp": round(100.0 * (p_beat - base_rate), 1),
                "base_rate": round(base_rate, 3),
            },
        }
    return rows


def build_artifact(asof: str, codes: Sequence[str], feat: "np.ndarray",
                   feat_names: Sequence[str], lnmv: "np.ndarray",
                   industry: "np.ndarray", params: Mapping[str, Any] | None = None,
                   ) -> dict:
    params = params or load_params()
    if params is None:
        raise RuntimeError(f"frozen params missing: {PARAMS_PATH}")
    rows = build_rows(codes, feat, feat_names, lnmv, industry, params)
    n_valid = sum(1 for r in rows.values() if r.get("validated"))
    return {
        "market": "A_share",
        "asof": asof,
        "built_at": int(time.time()),
        "params_version": params.get("version"),
        "params_built_at": params.get("built_at"),
        "n_rows": len(rows),
        "n_validated": n_valid,
        "caveats": params.get("caveats") or [],
        "rows": rows,
    }


def save_artifact(artifact: Mapping[str, Any], market: str = "A_share",
                  root: Path | None = None) -> Path:
    p = artifact_path(market, root)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(artifact, ensure_ascii=False))
    tmp.replace(p)  # atomic so the request path never reads a torn file
    return p
