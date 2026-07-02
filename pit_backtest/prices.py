"""Adjusted-price primitives for the PIT backtest.

tushare ``daily`` is *unadjusted*. We apply ``adj_factor`` to get **hfq**
(back-adjusted) closes. For a *return ratio* hfq vs qfq is irrelevant as long
as the convention is consistent across both endpoints of the ratio — we use
hfq everywhere (closes and the run_up look-back) so split/dividend events
never distort a ratio.

Two access shapes:
  * ``hfq_close_history`` / ``daily_basic_history`` — per-stock series ending at
    an as-of date (feeds run_up / crowdedness / historical_quantile in the
    collector). Strictly ``trade_date <= asof``.
  * ``cross_section_hfq_close`` — adjusted close for the whole market on one
    trading date (feeds forward-return labels in the harness). Batched: one
    ``daily`` + one ``adj_factor`` call per date for all stocks.

Forward-return labels are computed from these and are NEVER fed back into any
feature (asserted by the leakage audit).
"""

from __future__ import annotations

from typing import Mapping


def _to_date_map(df, key: str, value: str) -> dict[str, float]:
    if df is None or len(df) == 0:
        return {}
    out: dict[str, float] = {}
    for k, v in zip(df[key].tolist(), df[value].tolist()):
        if v is None:
            continue
        try:
            out[str(k)] = float(v)
        except (TypeError, ValueError):
            continue
    return out


def hfq_close_history(pro, ts_code: str, start: str, asof: str) -> list[dict]:
    """Per-stock hfq close history in ``[start, asof]``, ascending by date.

    Returns ``[{trade_date, close_raw, hfq_close}]``. ``hfq_close = close *
    adj_factor``. Guarantees every ``trade_date <= asof`` (PIT).
    """

    d = pro.daily(
        ts_code=ts_code, start_date=start, end_date=asof,
        fields="ts_code,trade_date,close",
    )
    a = pro.adj_factor(ts_code=ts_code, start_date=start, end_date=asof)
    closes = _to_date_map(d, "trade_date", "close")
    factors = _to_date_map(a, "trade_date", "adj_factor")
    rows: list[dict] = []
    for td in sorted(closes):
        if td > asof:  # defensive PIT guard
            continue
        af = factors.get(td)
        rows.append(
            {
                "trade_date": td,
                "close_raw": closes[td],
                "hfq_close": closes[td] * af if af is not None else None,
            }
        )
    return rows


def daily_basic_history(
    pro, ts_code: str, start: str, asof: str,
    *, fields: str = "ts_code,trade_date,pe_ttm,pb,turnover_rate",
) -> list[dict]:
    """Per-stock daily_basic history in ``[start, asof]`` ascending by date.

    daily_basic pe_ttm/pb/turnover_rate are already split-adjusted by tushare,
    so no adj_factor is needed here. Guarantees ``trade_date <= asof``.
    """

    df = pro.daily_basic(ts_code=ts_code, start_date=start, end_date=asof, fields=fields)
    if df is None or len(df) == 0:
        return []
    cols = [c for c in df.columns if c != "ts_code"]
    recs = df[cols].to_dict("records")
    recs = [r for r in recs if str(r.get("trade_date", "")) <= asof]
    recs.sort(key=lambda r: str(r.get("trade_date", "")))
    return recs


def cross_section_hfq_close(pro, trade_date: str) -> dict[str, float]:
    """hfq-adjusted close for the whole market on ``trade_date``.

    ``{ts_code: hfq_close}``. One ``daily`` + one ``adj_factor`` call. Used for
    forward-return labels (a stock absent here was suspended that session).
    """

    d = pro.daily(trade_date=trade_date, fields="ts_code,trade_date,close")
    a = pro.adj_factor(trade_date=trade_date)
    if d is None or len(d) == 0:
        return {}
    closes = {str(t): c for t, c in zip(d["ts_code"].tolist(), d["close"].tolist())}
    factors = (
        {str(t): f for t, f in zip(a["ts_code"].tolist(), a["adj_factor"].tolist())}
        if a is not None and len(a)
        else {}
    )
    out: dict[str, float] = {}
    for ts, close in closes.items():
        af = factors.get(ts)
        if close is None or af is None:
            continue
        try:
            out[ts] = float(close) * float(af)
        except (TypeError, ValueError):
            continue
    return out


def forward_return(base_close: float | None, end_close: float | None) -> float | None:
    """Simple pct change on (consistently adjusted) close: ``end/base - 1``."""

    if base_close is None or end_close is None:
        return None
    if base_close == 0:
        return None
    return end_close / base_close - 1.0


def adjusted_close_at(
    cross_sections: Mapping[str, Mapping[str, float]],
    open_days: list[str],
    ts_code: str,
    target_date: str,
    *,
    max_walk: int = 5,
) -> tuple[float | None, str | None, str]:
    """Adjusted close for ``ts_code`` at ``target_date``, walking forward over
    suspensions up to ``max_walk`` trading days.

    ``cross_sections`` maps ``trade_date -> {ts_code -> hfq_close}`` (only needs
    to contain the dates we might land on). Returns ``(close, used_date,
    status)`` where status ∈ {OK, WALKED, NO_PRICE}.
    """

    if target_date in cross_sections and ts_code in cross_sections[target_date]:
        return cross_sections[target_date][ts_code], target_date, "OK"
    # walk forward through subsequent open sessions
    future = [d for d in open_days if d >= target_date]
    for i, d in enumerate(future[: max_walk + 1]):
        sec = cross_sections.get(d)
        if sec and ts_code in sec:
            status = "OK" if d == target_date else "WALKED"
            return sec[ts_code], d, status
    return None, None, "NO_PRICE"
