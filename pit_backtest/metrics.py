"""Evaluation metrics for the PIT backtest — numpy only (no scipy dependency).

Every metric operates on the cross-section of stocks for one
``(base_date, horizon)``. The headline predictor is ``base_score`` (the
market-adjusted, thresholded scalar). All functions tolerate NaN / None by
dropping incomplete pairs and report the surviving ``n``.

Small-sample reality (n≈116, 3 base dates, overlapping universe): IC standard
errors are large. These metrics are a leakage / sanity audit, NOT a proof of
alpha — callers must surface CIs and the low-power caveat.
"""

from __future__ import annotations

import math
from typing import Sequence

import numpy as np

_RNG_SEED = 20260605  # fixed for reproducibility


def _clean_pairs(x: Sequence, y: Sequence) -> tuple[np.ndarray, np.ndarray]:
    xa = np.asarray(x, dtype=float)
    ya = np.asarray(y, dtype=float)
    m = np.isfinite(xa) & np.isfinite(ya)
    return xa[m], ya[m]


def _rankdata(a: np.ndarray) -> np.ndarray:
    """Average ranks (ties → mean rank), like scipy.stats.rankdata."""

    a = np.asarray(a, dtype=float)
    n = a.size
    if n == 0:
        return np.array([], dtype=float)
    order = np.argsort(a, kind="mergesort")
    ranks = np.empty(n, dtype=float)
    sa = a[order]
    i = 0
    while i < n:
        j = i
        while j + 1 < n and sa[j + 1] == sa[i]:
            j += 1
        avg = (i + j) / 2.0 + 1.0  # ranks are 1-based
        ranks[order[i : j + 1]] = avg
        i = j + 1
    return ranks


def _pearson(x: np.ndarray, y: np.ndarray) -> float:
    if x.size < 2:
        return float("nan")
    xc = x - x.mean()
    yc = y - y.mean()
    denom = math.sqrt(float((xc * xc).sum()) * float((yc * yc).sum()))
    if denom == 0:
        return float("nan")
    return float((xc * yc).sum() / denom)


def _student_t_sf(t: float, df: int) -> float:
    """Two-sided survival function 2*P(T>|t|) via the regularized incomplete
    beta function (numpy/math only). Used for the rank-IC p-value."""

    if df <= 0 or not math.isfinite(t):
        return float("nan")
    x = df / (df + t * t)
    return _betainc(df / 2.0, 0.5, x)


def _betainc(a: float, b: float, x: float) -> float:
    """Regularized incomplete beta I_x(a,b) via continued fraction (Lentz)."""

    if x <= 0:
        return 0.0
    if x >= 1:
        return 1.0
    lbeta = math.lgamma(a) + math.lgamma(b) - math.lgamma(a + b)
    front = math.exp(math.log(x) * a + math.log(1 - x) * b - lbeta) / a
    # continued fraction
    f, c, d = 1.0, 1.0, 0.0
    for i in range(0, 300):
        m = i // 2
        if i == 0:
            num = 1.0
        elif i % 2 == 0:
            num = (m * (b - m) * x) / ((a + 2 * m - 1) * (a + 2 * m))
        else:
            num = -((a + m) * (a + b + m) * x) / ((a + 2 * m) * (a + 2 * m + 1))
        d = 1.0 + num * d
        if abs(d) < 1e-30:
            d = 1e-30
        d = 1.0 / d
        c = 1.0 + num / c
        if abs(c) < 1e-30:
            c = 1e-30
        f *= d * c
        if abs(1.0 - d * c) < 1e-10:
            break
    return front * (f - 1.0)


def rank_ic(scores: Sequence, rets: Sequence) -> dict:
    """Spearman rank-IC = Pearson on average-ranks. Returns {ic, p, n}."""

    x, y = _clean_pairs(scores, rets)
    n = int(x.size)
    if n < 5:
        return {"ic": float("nan"), "p": float("nan"), "n": n}
    ic = _pearson(_rankdata(x), _rankdata(y))
    if not math.isfinite(ic) or abs(ic) >= 1.0:
        return {"ic": ic, "p": float("nan"), "n": n}
    t = ic * math.sqrt((n - 2) / (1 - ic * ic))
    return {"ic": ic, "p": _student_t_sf(t, n - 2), "n": n}


def fisher_ci(ic: float, n: int, z: float = 1.96) -> tuple[float, float]:
    """Fisher-z 95% CI for a correlation."""

    if not math.isfinite(ic) or n < 4 or abs(ic) >= 1:
        return (float("nan"), float("nan"))
    zr = math.atanh(ic)
    se = 1.0 / math.sqrt(n - 3)
    return (math.tanh(zr - z * se), math.tanh(zr + z * se))


def quantile_groups(scores: Sequence, rets: Sequence, k: int = 5) -> dict:
    """Cut the cross-section into ``k`` equal-count score groups (Q1=lowest).

    Returns per-group mean/std/SE/count and the top-minus-bottom spread + SE.
    """

    x, y = _clean_pairs(scores, rets)
    n = int(x.size)
    if n < k * 2:
        # not enough for k groups; degrade
        k = max(2, n // 5) if n >= 6 else 2
    order = np.argsort(x, kind="mergesort")
    groups = np.array_split(order, k)
    out_groups = []
    for gi, idx in enumerate(groups):
        gy = y[idx]
        m = float(gy.mean()) if gy.size else float("nan")
        sd = float(gy.std(ddof=1)) if gy.size > 1 else float("nan")
        se = sd / math.sqrt(gy.size) if gy.size > 1 else float("nan")
        out_groups.append(
            {"group": gi + 1, "n": int(gy.size), "mean_ret": m, "std": sd, "se": se}
        )
    top, bot = out_groups[-1], out_groups[0]
    spread = top["mean_ret"] - bot["mean_ret"]
    se_spread = float("nan")
    if math.isfinite(top["se"]) and math.isfinite(bot["se"]):
        se_spread = math.sqrt(top["se"] ** 2 + bot["se"] ** 2)
    return {
        "k": k,
        "n": n,
        "groups": out_groups,
        "top_minus_bottom": spread,
        "se": se_spread,
        "ci": (
            (spread - 1.96 * se_spread, spread + 1.96 * se_spread)
            if math.isfinite(se_spread)
            else (float("nan"), float("nan"))
        ),
    }


_SIGNAL_ORDER = ["BUY", "HOLD", "WATCH", "AVOID"]


def signal_buckets(signals: Sequence[str], rets: Sequence) -> dict:
    """Per-signal count / mean fwd-ret / hit-rate (% positive) / SE, plus the
    BUY−AVOID long-short spread with a permutation p-value and a monotonicity
    flag (BUY≥HOLD≥WATCH≥AVOID)."""

    sig = np.asarray(list(signals), dtype=object)
    ret = np.asarray(rets, dtype=float)
    m = np.isfinite(ret)
    sig, ret = sig[m], ret[m]
    buckets: dict[str, dict] = {}
    for s in _SIGNAL_ORDER:
        gy = ret[sig == s]
        if gy.size:
            mean = float(gy.mean())
            sd = float(gy.std(ddof=1)) if gy.size > 1 else float("nan")
            se = sd / math.sqrt(gy.size) if gy.size > 1 else float("nan")
            hit = float((gy > 0).mean())
        else:
            mean = sd = se = hit = float("nan")
        buckets[s] = {"n": int(gy.size), "mean_ret": mean, "hit_rate": hit, "se": se}

    means = [buckets[s]["mean_ret"] for s in _SIGNAL_ORDER]
    finite_means = [(s, buckets[s]["mean_ret"]) for s in _SIGNAL_ORDER if buckets[s]["n"] > 0]
    monotone = all(
        finite_means[i][1] >= finite_means[i + 1][1] for i in range(len(finite_means) - 1)
    ) if len(finite_means) >= 2 else None

    buy, avoid = ret[sig == "BUY"], ret[sig == "AVOID"]
    ls = float("nan")
    perm_p = float("nan")
    if buy.size and avoid.size:
        ls = float(buy.mean() - avoid.mean())
        perm_p = _perm_test_diff(buy, avoid, ls)
    return {
        "buckets": buckets,
        "long_short_BUY_minus_AVOID": ls,
        "perm_p": perm_p,
        "monotone": monotone,
    }


def _perm_test_diff(a: np.ndarray, b: np.ndarray, observed: float, n_perm: int = 10000) -> float:
    rng = np.random.default_rng(_RNG_SEED)
    pooled = np.concatenate([a, b])
    na = a.size
    count = 0
    obs = abs(observed)
    for _ in range(n_perm):
        rng.shuffle(pooled)
        diff = pooled[:na].mean() - pooled[na:].mean()
        if abs(diff) >= obs:
            count += 1
    return (count + 1) / (n_perm + 1)


def bootstrap_mean_ci(values: Sequence, n_boot: int = 10000, z: float = 1.96) -> dict:
    """Bootstrap + normal mean CI for a 1-D sample. Returns {mean, se, ci, boot_ci, n}."""

    v = np.asarray(values, dtype=float)
    v = v[np.isfinite(v)]
    n = int(v.size)
    if n == 0:
        return {"mean": float("nan"), "se": float("nan"), "ci": (float("nan"),) * 2,
                "boot_ci": (float("nan"),) * 2, "n": 0}
    mean = float(v.mean())
    se = float(v.std(ddof=1) / math.sqrt(n)) if n > 1 else float("nan")
    ci = (mean - z * se, mean + z * se) if math.isfinite(se) else (float("nan"),) * 2
    rng = np.random.default_rng(_RNG_SEED)
    if n > 1:
        boots = np.array([rng.choice(v, size=n, replace=True).mean() for _ in range(n_boot)])
        boot_ci = (float(np.percentile(boots, 2.5)), float(np.percentile(boots, 97.5)))
    else:
        boot_ci = (float("nan"),) * 2
    return {"mean": mean, "se": se, "ci": ci, "boot_ci": boot_ci, "n": n}


def aggregate_ic_across_windows(ic_values: Sequence[float]) -> dict:
    """Mean ± std of per-window ICs (NOT a stacked-frame IC — windows reuse the
    same universe so stacking would fake independence)."""

    v = np.asarray([x for x in ic_values if x is not None and math.isfinite(x)], dtype=float)
    if v.size == 0:
        return {"mean_ic": float("nan"), "std_ic": float("nan"), "n_windows": 0}
    return {
        "mean_ic": float(v.mean()),
        "std_ic": float(v.std(ddof=1)) if v.size > 1 else float("nan"),
        "n_windows": int(v.size),
    }
