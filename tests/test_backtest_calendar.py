"""Calendar resolution tests with a fake trade_cal (offline)."""

from datetime import datetime, timedelta

import pandas as pd

from pit_backtest import calendar as cal


class FakePro:
    """trade_cal that treats every weekday as an open session (no holidays)."""

    def trade_cal(self, exchange, start_date, end_date, is_open):
        s = datetime.strptime(start_date, "%Y%m%d")
        e = datetime.strptime(end_date, "%Y%m%d")
        days = []
        d = s
        while d <= e:
            if d.weekday() < 5:  # Mon-Fri
                days.append(d.strftime("%Y%m%d"))
            d += timedelta(days=1)
        return pd.DataFrame({"cal_date": days})


def test_resolve_base_dates_ordering_and_offsets():
    base = cal.resolve_base_dates(FakePro(), today="20260605", offsets=(30, 60, 90))
    assert set(base) == {0, 30, 60, 90}
    # strictly increasing dates as offset shrinks
    assert base[90] < base[60] < base[30] < base[0]
    assert base[0] <= "20260605"


def test_resolve_offset_is_trading_days():
    fp = FakePro()
    days = cal.open_sessions(fp, "20260605", lookback_days=420)
    base = cal.resolve_base_dates(fp, today="20260605", offsets=(30,))
    i0 = days.index(base[0])
    assert days[i0 - 30] == base[30]


def test_t0_is_last_open_on_or_before_today():
    # 2026-06-06 is a Saturday in this fake -> T0 should fall back to Friday 06-05
    base = cal.resolve_base_dates(FakePro(), today="20260606", offsets=(30,))
    assert base[0] == "20260605"


def test_forward_horizon_pairs():
    base = {0: "T0", 30: "T30", 60: "T60", 90: "T90"}
    pairs = cal.forward_horizon_pairs(base)
    spans = sorted((p["base_off"], p["end_off"], p["horizon_d"]) for p in pairs)
    assert (30, 0, 30) in spans
    assert (90, 0, 90) in spans
    assert (90, 60, 30) in spans
    assert len(pairs) == 6  # 3 starts x respective ends


def test_next_session_walk_with_day_list():
    days = ["20260116", "20260119", "20260120"]
    assert cal.next_session_on_or_after(days, "20260117") == "20260119"
    assert cal.next_session_on_or_after(days, "20260116") == "20260116"
