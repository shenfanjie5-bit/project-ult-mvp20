"""Trading-day calendar resolution for the PIT backtest.

The production code only uses ``trade_cal`` in a liveness probe and otherwise
counts *calendar* days (``_previous_n_days``). The backtest needs exact
*trading* days, so we resolve base dates against ``pro.trade_cal`` here.

All dates are ``YYYYMMDD`` strings (tushare convention). ``T0`` is the last
open session on or before ``today``; ``T-N`` is N trading sessions before T0.
"""

from __future__ import annotations

from typing import Iterable, Mapping


def _ashare_today() -> str:
    """Today's date in the Asia/Shanghai timezone as ``YYYYMMDD``.

    A-shares trade on CST; anchoring on UTC could pick the wrong calendar day
    near midnight. Falls back to naive local time if zoneinfo is unavailable.
    """

    from datetime import datetime, timezone, timedelta

    try:
        from zoneinfo import ZoneInfo

        now = datetime.now(ZoneInfo("Asia/Shanghai"))
    except Exception:  # noqa: BLE001 — zoneinfo/tzdata missing
        now = datetime.now(timezone(timedelta(hours=8)))
    return now.strftime("%Y%m%d")


def open_sessions(
    pro,
    end_date: str,
    *,
    lookback_days: int = 420,
    exchange: str = "SSE",
) -> list[str]:
    """Return ascending list of open ``YYYYMMDD`` sessions up to ``end_date``.

    ``lookback_days`` calendar days back from ``end_date`` (420 ≈ 280 trading
    days, enough for T-90 plus slack). One ``trade_cal`` API call.
    """

    from datetime import datetime, timedelta

    end_dt = datetime.strptime(end_date, "%Y%m%d")
    start = (end_dt - timedelta(days=lookback_days)).strftime("%Y%m%d")
    df = pro.trade_cal(
        exchange=exchange, start_date=start, end_date=end_date, is_open="1"
    )
    if df is None or len(df) == 0:
        raise RuntimeError(
            f"trade_cal returned no open sessions in [{start}, {end_date}]"
        )
    days = sorted(str(d) for d in df["cal_date"].tolist())
    return days


def resolve_base_dates(
    pro,
    today: str | None = None,
    offsets: Iterable[int] = (30, 60, 90),
    *,
    exchange: str = "SSE",
) -> dict[int, str]:
    """Resolve ``{0: T0, 30: T-30, 60: T-60, 90: T-90}`` as trading days.

    ``today`` defaults to the Asia/Shanghai current date. ``T0`` = last open
    session on or before ``today``. Each ``T-N`` = N sessions before T0.
    Raises if the calendar doesn't reach back far enough.
    """

    today = today or _ashare_today()
    offsets = sorted(set(int(o) for o in offsets))
    max_off = max(offsets) if offsets else 0
    # need max_off sessions before T0 → pull enough calendar days
    lookback = max(420, int(max_off * 2.2) + 60)
    days = open_sessions(pro, today, lookback_days=lookback, exchange=exchange)

    le_today = [d for d in days if d <= today]
    if not le_today:
        raise RuntimeError(f"no open session on/before today={today}")
    t0 = le_today[-1]
    idx = days.index(t0)
    out: dict[int, str] = {0: t0}
    for off in offsets:
        if idx - off < 0:
            raise RuntimeError(
                f"calendar reaches {len(days)} sessions; cannot offset {off} before {t0}"
            )
        out[off] = days[idx - off]
    return out


def next_session_on_or_after(pro_or_days, date: str, *, max_walk: int = 6,
                             exchange: str = "SSE") -> str | None:
    """First open session >= ``date`` (walking forward up to ``max_walk``).

    ``pro_or_days`` may be a tushare ``pro`` client or a precomputed ascending
    list of open ``YYYYMMDD`` sessions (cheaper when looping). Returns None if
    none found within the window.
    """

    if isinstance(pro_or_days, (list, tuple)):
        for d in pro_or_days:
            if d >= date:
                return d
        return None

    from datetime import datetime, timedelta

    start = date
    end = (datetime.strptime(date, "%Y%m%d") + timedelta(days=max_walk * 3 + 10)).strftime(
        "%Y%m%d"
    )
    df = pro_or_days.trade_cal(
        exchange=exchange, start_date=start, end_date=end, is_open="1"
    )
    if df is None or len(df) == 0:
        return None
    days = sorted(str(d) for d in df["cal_date"].tolist())
    return days[0] if days else None


def forward_horizon_pairs(base: Mapping[int, str]) -> list[dict]:
    """The 6 (base_date, end_date, horizon_d) label pairs, all ending <= T0.

    From base dates T-90/T-60/T-30 and T0:
      T-90->T-60(+30) T-90->T-30(+60) T-90->T0(+90)
      T-60->T-30(+30) T-60->T0(+60)   T-30->T0(+30)
    ``horizon_d`` is the trading-day span (offset difference).
    """

    pairs: list[dict] = []
    offs = sorted(o for o in base if o != 0)  # e.g. [30,60,90]
    starts = offs + []  # base offsets that are start points
    # all (start_off, end_off) with start_off > end_off (more days ago -> fewer)
    cand = sorted(set(offs) | {0})
    for s in sorted(offs, reverse=True):
        for e in cand:
            if e < s:
                pairs.append(
                    {
                        "base_off": s,
                        "end_off": e,
                        "base_date": base[s],
                        "end_date": base[e],
                        "horizon_d": s - e,
                    }
                )
    return pairs
