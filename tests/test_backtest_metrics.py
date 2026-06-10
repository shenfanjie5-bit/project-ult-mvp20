"""Metrics tests (numpy-only, offline)."""

import math

from pit_backtest import metrics


def test_rankdata_ties():
    r = metrics._rankdata([10.0, 10.0, 20.0])
    assert list(r) == [1.5, 1.5, 3.0]


def test_rank_ic_perfect_monotonic():
    x = list(range(20))
    y = [v * 3 + 1 for v in x]
    out = metrics.rank_ic(x, y)
    assert abs(out["ic"] - 1.0) < 1e-9
    assert out["n"] == 20
    # p is degenerate (nan) at perfect correlation by design — real data never hits 1.0


def test_rank_ic_pvalue_significant_near_perfect():
    x = list(range(20))
    y = [v * 3 + 1 for v in x]
    y[0], y[1] = y[1], y[0]  # one swap -> ic just under 1.0, p path exercised
    out = metrics.rank_ic(x, y)
    assert out["ic"] > 0.99
    assert out["p"] < 0.01


def test_rank_ic_perfect_anti():
    x = list(range(20))
    y = [-v for v in x]
    assert abs(metrics.rank_ic(x, y)["ic"] + 1.0) < 1e-9


def test_rank_ic_too_few():
    assert math.isnan(metrics.rank_ic([1, 2], [3, 4])["ic"])


def test_rank_ic_drops_nan_pairs():
    x = [1, 2, 3, 4, 5, float("nan")]
    y = [1, 2, 3, 4, 5, 10]
    out = metrics.rank_ic(x, y)
    assert out["n"] == 5 and abs(out["ic"] - 1.0) < 1e-9


def test_quantile_groups_monotonic_spread():
    xs = list(range(50))
    ys = [v * 1.0 for v in xs]  # higher score -> higher return
    q = metrics.quantile_groups(xs, ys, k=5)
    assert q["top_minus_bottom"] > 0
    assert q["groups"][-1]["mean_ret"] > q["groups"][0]["mean_ret"]


def test_signal_buckets_basic():
    sig = ["BUY", "BUY", "AVOID", "AVOID", "HOLD"]
    ret = [0.1, 0.2, -0.1, -0.2, 0.0]
    out = metrics.signal_buckets(sig, ret)
    assert out["buckets"]["BUY"]["n"] == 2
    assert abs(out["buckets"]["BUY"]["mean_ret"] - 0.15) < 1e-9
    assert out["buckets"]["BUY"]["hit_rate"] == 1.0
    assert abs(out["long_short_BUY_minus_AVOID"] - (0.15 - (-0.15))) < 1e-9


def test_fisher_ci_brackets_ic():
    lo, hi = metrics.fisher_ci(0.3, 100)
    assert lo < 0.3 < hi


def test_aggregate_ic_across_windows():
    agg = metrics.aggregate_ic_across_windows([0.1, 0.2, 0.3])
    assert abs(agg["mean_ic"] - 0.2) < 1e-9
    assert agg["n_windows"] == 3


def test_bootstrap_mean_ci_runs():
    out = metrics.bootstrap_mean_ci([0.1, 0.2, -0.1, 0.05, 0.0], n_boot=500)
    assert out["n"] == 5
    assert out["boot_ci"][0] <= out["mean"] <= out["boot_ci"][1]
