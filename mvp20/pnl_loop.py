"""Production P&L feedback loop (capability gap G1).

Closes the loop the capability audit found missing: production scores are
snapshotted daily, joined T+5/10/20 trading days later against realized hfq
returns, and rolled into per-date + rolling evaluation metrics that
``/api/backtest`` serves. Until this module, scores were never compared to
realized forward returns anywhere in the runtime — every threshold and weight
was calibrated blind.

Store: ``runtime/backtest/pnl.sqlite`` — same schema as the PIT backtest
(``pit_backtest.store``: scores / returns / manifest, INSERT OR REPLACE
idempotent resume) plus an ``eval_metrics`` table. Kept SEPARATE from
``backtest.sqlite`` so the historical PIT experiment is never polluted by
production snapshots.

Design: pure logic with injectable callables (``score_fn``, ``closes_fn``,
``sessions``) so tests run hermetic — no tushare, no hot.sqlite. Production
wiring lives in ``scripts/run_pnl_loop.py``.

De-rate contract (defined UP FRONT, before any data is seen, to prevent
post-hoc rationalization): a channel is flagged ``de_rated`` for a horizon
when, over the trailing ``DERATE_WINDOW`` matured snapshot dates, the
bootstrap 95% CI of the top-quintile excess return sits entirely below zero.
The flag is informational (served via the API); it never mutates scores.
"""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

from pit_backtest import metrics as pmetrics
from pit_backtest import store as pstore

DEFAULT_DB = Path("runtime/backtest/pnl.sqlite")
HORIZONS = (5, 10, 20)

#: trailing matured dates per horizon used for the rolling summary + de-rate.
DERATE_WINDOW = 12
#: minimum matured dates before the de-rate rule may fire at all (small-n
#: bootstrap CIs are too noisy to act on).
DERATE_MIN_DATES = 8

_EVAL_SCHEMA = """
CREATE TABLE IF NOT EXISTS eval_metrics (
    base_date TEXT NOT NULL,
    horizon_d INTEGER NOT NULL,
    metrics_json TEXT NOT NULL,
    computed_at INTEGER NOT NULL,
    PRIMARY KEY (base_date, horizon_d)
);
"""


def _init(db_path: Path) -> None:
    pstore.init(db_path)
    with sqlite3.connect(str(db_path)) as c:
        c.executescript(_EVAL_SCHEMA)


# ---------------------------------------------------------------------------
# universe + production score adapter
# ---------------------------------------------------------------------------


def list_universe(overlays_dir: Path) -> list[str]:
    """All onboarded ts_codes = stock-overlay YAML stems under any industry."""

    return sorted(
        {p.stem for p in Path(overlays_dir).glob("*/*.yaml") if "." in p.stem}
    )


def production_score_fn(cfg) -> Callable[[str], dict | None]:
    """Wrap ``server.handle_score`` into ``ts_code -> scores-row | None``.

    Uses the exact request path the UI sees (overlay + aggregator + realtime
    bridge + peer context), so the loop measures what users are shown — not a
    re-implementation that could drift (the H-4 lesson).
    """

    from mvp20.server import handle_score

    def _score(ts_code: str) -> dict | None:
        status, envelope = handle_score(cfg, {"ts_code": [ts_code]})
        if status != 200:
            return None
        data = envelope.get("data") or {}
        final = data.get("final_score") or {}
        return {
            "ts_code": ts_code,
            "base_score": final.get("base_score"),
            "core_base_score": (data.get("core_final_score") or {}).get("base_score"),
            "short_total": data.get("short_total"),
            "medium_total": data.get("medium_total"),
            "long_total": data.get("long_total"),
            "trading_signal": data.get("trading_signal"),
            "mode": data.get("mode_code") or data.get("mode"),
        }

    return _score


# ---------------------------------------------------------------------------
# step 1 — daily snapshot
# ---------------------------------------------------------------------------


def snapshot_scores(
    asof: str,
    universe: Sequence[str],
    score_fn: Callable[[str], dict | None],
    *,
    db_path: Path = DEFAULT_DB,
    resume: bool = True,
    progress: Callable[[int, int, str], None] | None = None,
) -> dict:
    """Score ``universe`` as of today and persist under ``base_date=asof``.

    ``asof`` must be the current open session (the caller resolves it via the
    trade calendar); scoring uses live hot.sqlite state, so back-dating would
    be dishonest — this function refuses to overwrite an existing FULL
    snapshot unless ``resume`` finds it incomplete.
    """

    _init(db_path)
    already = pstore.scored_base_dates(db_path).get(asof, 0)
    if resume and already >= len(universe):
        return {"asof": asof, "scored": 0, "skipped": already, "status": "complete"}

    done: set[str] = set()
    if resume and already:
        with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as c:
            done = {
                r[0]
                for r in c.execute(
                    "SELECT ts_code FROM scores WHERE base_date=?", (asof,)
                )
            }

    rows: list[dict] = []
    failed = 0
    todo = [ts for ts in universe if ts not in done]
    for i, ts in enumerate(todo):
        if progress and i % 100 == 0:
            progress(i, len(todo), ts)
        row = score_fn(ts)
        if row is None:
            failed += 1
            continue
        row["base_date"] = asof
        rows.append(row)
        if len(rows) >= 200:  # flush in batches so a crash resumes cheaply
            pstore.put_scores(rows, db_path)
            rows = []
    pstore.put_scores(rows, db_path)
    scored = len(todo) - failed
    return {"asof": asof, "scored": scored, "failed": failed,
            "skipped": len(done), "status": "ok"}


# ---------------------------------------------------------------------------
# step 2 — fill matured forward returns
# ---------------------------------------------------------------------------


def matured_pairs(
    snapshot_dates: Iterable[str],
    sessions: Sequence[str],
    horizons: Sequence[int] = HORIZONS,
) -> list[tuple[str, str, int]]:
    """``(base_date, end_date, horizon)`` for every snapshot whose T+h session
    already closed. ``sessions`` is the ascending open-session list whose last
    element is the latest CLOSED session (caller guarantees this — run the
    loop after market close)."""

    idx = {d: i for i, d in enumerate(sessions)}
    out: list[tuple[str, str, int]] = []
    for b in sorted(set(snapshot_dates)):
        i = idx.get(b)
        if i is None:
            continue
        for h in horizons:
            j = i + int(h)
            if j < len(sessions):
                out.append((b, sessions[j], int(h)))
    return out


def fill_returns(
    sessions: Sequence[str],
    closes_fn: Callable[[str], Mapping[str, float]],
    *,
    db_path: Path = DEFAULT_DB,
    horizons: Sequence[int] = HORIZONS,
) -> dict:
    """Compute hfq forward returns for every matured (snapshot, horizon) not
    yet in the ``returns`` table. ``closes_fn(trade_date) -> {ts_code: close}``
    (production: ``pit_backtest.prices.cross_section_hfq_close``)."""

    _init(db_path)
    snap_dates = list(pstore.scored_base_dates(db_path))
    pairs = matured_pairs(snap_dates, sessions, horizons)

    with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as c:
        have = {
            (r[0], r[1])
            for r in c.execute("SELECT DISTINCT base_date, end_date FROM returns")
        }
    todo = [(b, e, h) for (b, e, h) in pairs if (b, e) not in have]
    if not todo:
        return {"filled": 0, "pairs_done": len(pairs), "status": "up_to_date"}

    closes_cache: dict[str, Mapping[str, float]] = {}

    def closes(d: str) -> Mapping[str, float]:
        if d not in closes_cache:
            closes_cache[d] = closes_fn(d) or {}
        return closes_cache[d]

    filled = 0
    for b, e, h in todo:
        with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as c:
            codes = [
                r[0]
                for r in c.execute(
                    "SELECT ts_code FROM scores WHERE base_date=?", (b,)
                )
            ]
        cb, ce = closes(b), closes(e)
        rows = []
        for ts in codes:
            p0, p1 = cb.get(ts), ce.get(ts)
            ok = (
                p0 is not None and p1 is not None
                and p0 == p0 and p1 == p1 and p0 > 0  # NaN-safe
            )
            rows.append({
                "ts_code": ts, "base_date": b, "end_date": e, "horizon_d": h,
                "close_base": p0, "close_end": p1,
                "used_base_date": b, "used_end_date": e,
                "fwd_ret": (p1 / p0 - 1.0) if ok else None,
                "status": "ok" if ok else "missing_close",
            })
        filled += pstore.put_returns(rows, db_path)
    return {"filled": filled, "pairs_new": len(todo),
            "pairs_done": len(pairs), "status": "ok"}


# ---------------------------------------------------------------------------
# step 3 — evaluate
# ---------------------------------------------------------------------------


def _eval_one(db_path: Path, base_date: str, horizon: int) -> dict | None:
    with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as c:
        rows = c.execute(
            """SELECT s.base_score, s.trading_signal, r.fwd_ret
               FROM scores s JOIN returns r
                 ON r.ts_code = s.ts_code AND r.base_date = s.base_date
               WHERE s.base_date=? AND r.horizon_d=? AND r.status='ok'
                 AND r.fwd_ret IS NOT NULL""",
            (base_date, horizon),
        ).fetchall()
    rows = [r for r in rows if r[0] is not None]
    if len(rows) < 50:
        return None
    scores = [r[0] for r in rows]
    signals = [r[1] or "NONE" for r in rows]
    rets = [r[2] for r in rows]
    ic = pmetrics.rank_ic(scores, rets)
    quint = pmetrics.quantile_groups(scores, rets, 5)
    buckets = pmetrics.signal_buckets(signals, rets)
    uni_mean = sum(rets) / len(rets)
    top = quint["groups"][-1]["mean_ret"] if quint.get("groups") else None
    return {
        "base_date": base_date, "horizon_d": horizon, "n": len(rows),
        "rank_ic": ic["ic"], "rank_ic_p": ic["p"],
        "q5_q1": quint.get("top_minus_bottom"),
        "top_quintile_mean": top,
        "uni_mean": uni_mean,
        "top_excess": (top - uni_mean) if top is not None else None,
        "signal_buckets": {
            k: {"n": v["n"], "mean_ret": v["mean_ret"], "hit_rate": v["hit_rate"]}
            for k, v in buckets["buckets"].items()
        },
        "buy_minus_avoid": buckets["long_short_BUY_minus_AVOID"],
        "signal_monotone": buckets["monotone"],
    }


def evaluate(
    db_path: Path = DEFAULT_DB,
    horizons: Sequence[int] = HORIZONS,
    *,
    derate_window: int = DERATE_WINDOW,
) -> dict:
    """(Re)compute per-(date,horizon) metrics for every matured snapshot and
    the rolling summary + de-rate flags. Idempotent."""

    _init(db_path)
    with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as c:
        matured = c.execute(
            "SELECT DISTINCT base_date, horizon_d FROM returns WHERE status='ok'"
        ).fetchall()

    now = int(time.time())
    written = 0
    for base_date, h in sorted(matured):
        m = _eval_one(db_path, base_date, int(h))
        if m is None:
            continue
        with sqlite3.connect(str(db_path), isolation_level=None) as c:
            c.execute(
                "INSERT OR REPLACE INTO eval_metrics"
                " (base_date, horizon_d, metrics_json, computed_at)"
                " VALUES (?,?,?,?)",
                (base_date, int(h), json.dumps(m), now),
            )
        written += 1

    rolling: dict[str, Any] = {}
    for h in horizons:
        ms = read_eval(db_path, horizon=h)
        ms = sorted(ms, key=lambda m: m["base_date"])[-derate_window:]
        ics = [m["rank_ic"] for m in ms if m.get("rank_ic") is not None]
        tops = [m["top_excess"] for m in ms if m.get("top_excess") is not None]
        if not ics:
            continue
        ic_agg = pmetrics.bootstrap_mean_ci(ics, n_boot=2000)
        top_agg = pmetrics.bootstrap_mean_ci(tops, n_boot=2000)
        de_rated = (
            len(tops) >= DERATE_MIN_DATES
            and top_agg["boot_ci"][1] == top_agg["boot_ci"][1]  # not NaN
            and top_agg["boot_ci"][1] < 0.0
        )
        rolling[str(h)] = {
            "n_dates": len(ms),
            "window": derate_window,
            "rank_ic_mean": ic_agg["mean"], "rank_ic_ci": list(ic_agg["boot_ci"]),
            "rank_ic_pos_pct": (
                sum(1.0 for x in ics if x > 0) / len(ics) if ics else None
            ),
            "top_excess_mean": top_agg["mean"],
            "top_excess_ci": list(top_agg["boot_ci"]),
            "de_rated": bool(de_rated),
            "de_rate_rule": (
                f"trailing {derate_window} matured dates; flag when bootstrap 95% CI"
                f" of top-quintile excess < 0 (min {DERATE_MIN_DATES} dates)"
            ),
        }
    pstore.set_manifest("rolling_summary", {"computed_at": now, "horizons": rolling},
                        db_path)
    return {"eval_written": written, "rolling": rolling}


def read_eval(db_path: Path | None = None, horizon: int | None = None) -> list[dict]:
    db_path = db_path or DEFAULT_DB  # resolved at call time so tests/ops can repoint
    if not Path(db_path).exists():
        return []
    q = "SELECT metrics_json FROM eval_metrics"
    args: tuple = ()
    if horizon is not None:
        q += " WHERE horizon_d=?"
        args = (int(horizon),)
    try:
        with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as c:
            return [json.loads(r[0]) for r in c.execute(q, args)]
    except sqlite3.OperationalError:
        return []


def rolling_summary(db_path: Path | None = None) -> dict | None:
    return pstore.get_manifest("rolling_summary", db_path or DEFAULT_DB)
