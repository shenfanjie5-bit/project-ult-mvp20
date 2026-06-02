"""Tests for Tushare report_rc forecast/spec dp_id emits."""

from __future__ import annotations

import json
from typing import Any

import pytest

from mvp20.sources import tushare_source


class _StubDF:
    def __init__(self, records: list[dict[str, Any]]):
        self._rows = list(records)

    def __len__(self) -> int:
        return len(self._rows)

    def to_dict(self, orient: str = "records") -> list[dict[str, Any]]:
        assert orient == "records"
        return [dict(r) for r in self._rows]


class _StubPro:
    def __init__(self, **endpoint_data):
        self._data = endpoint_data
        self.call_counts: dict[str, int] = {k: 0 for k in endpoint_data}

    def _dispatch(self, name: str, **kwargs):
        self.call_counts[name] = self.call_counts.get(name, 0) + 1
        v = self._data.get(name)
        if isinstance(v, Exception):
            raise v
        if callable(v):
            return v(**kwargs)
        return v

    def report_rc(self, **kw):
        return self._dispatch("report_rc", **kw)


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tushare_source.time, "sleep", lambda *_: None)


def test_supported_dp_ids_includes_report_rc_spec_forecasts() -> None:
    expected = {
        "L5.fcst.revenue_margin",
        "L5.fcst.eps_cf",
        "L5.fcst.revisions",
    }
    assert expected.issubset(tushare_source.SUPPORTED_DP_IDS)


def test_fetch_report_rc_emits_sell_side_and_fcst_rows() -> None:
    today = tushare_source._today_yyyymmdd()
    two_days_ago = tushare_source._previous_n_days(2)
    forty_days_ago = tushare_source._previous_n_days(40)
    pro = _StubPro(report_rc=_StubDF([
        {"report_date": today, "org_name": "Broker A",
         "author_name": "Analyst A", "report_title": "Update",
         "rating": "Buy", "quarter": "2026Q4", "eps": 2.0,
         "op_rt": 110_000.0, "op_pr": 22_000.0, "np": 16_500.0},
        {"report_date": two_days_ago, "org_name": "Broker B",
         "author_name": "Analyst B", "report_title": "Preview",
         "rating": "Buy", "quarter": "2026Q4", "eps": 1.8,
         "op_rt": 100_000.0, "op_pr": 18_000.0, "np": 14_000.0},
        {"report_date": forty_days_ago, "org_name": "Broker C",
         "author_name": "Analyst C", "report_title": "Older",
         "rating": "Hold", "quarter": "2026Q4", "eps": 1.4,
         "op_rt": 90_000.0, "op_pr": 13_500.0, "np": 10_800.0},
    ]))

    rows = tushare_source._fetch_a_share_report_rc(
        pro, ["300750.SZ"], now=1700000000,
    )
    by_dp = {r[1]: r for r in rows}

    assert {
        "L5.surprise.sell_side",
        "L5.fcst.revenue_margin",
        "L5.fcst.eps_cf",
        "L5.fcst.revisions",
    }.issubset(by_dp)
    assert by_dp["L5.fcst.revenue_margin"][3] == "Known"
    revenue = json.loads(by_dp["L5.fcst.revenue_margin"][2])
    assert revenue["revenue_avg"] == pytest.approx(1_000_000_000.0)
    assert revenue["operating_margin"] == pytest.approx(0.1783333333)
    assert revenue["net_margin"] == pytest.approx(0.1376666667)
    assert revenue["num_analysts"] == 3

    eps = json.loads(by_dp["L5.fcst.eps_cf"][2])
    assert eps["eps_avg"] == pytest.approx((2.0 + 1.8 + 1.4) / 3)
    assert eps["eps_low"] == 1.4
    assert eps["eps_high"] == 2.0
    assert eps["cashflow_available"] is False

    revisions = json.loads(by_dp["L5.fcst.revisions"][2])
    assert revisions["direction"] == "up"
    assert revisions["recent_eps_avg"] == pytest.approx(1.9)
    assert revisions["older_eps_avg"] == pytest.approx(1.4)


def test_fetch_report_rc_empty_emits_inactive_fcst_rows() -> None:
    pro = _StubPro(report_rc=_StubDF([]))
    rows = tushare_source._fetch_a_share_report_rc(
        pro, ["300750.SZ"], now=1700000000,
    )
    by_dp = {r[1]: r for r in rows}
    for dp_id in (
        "L5.surprise.sell_side",
        "L5.fcst.revenue_margin",
        "L5.fcst.eps_cf",
        "L5.fcst.revisions",
    ):
        assert dp_id in by_dp
        assert by_dp[dp_id][3] == "Inactive"


def test_fetch_report_rc_permission_error_emits_inactive_rows() -> None:
    pro = _StubPro(report_rc=RuntimeError("permission denied"))
    rows = tushare_source._fetch_a_share_report_rc(
        pro, ["300750.SZ"], now=1700000000,
    )

    by_dp = {r[1]: r for r in rows}
    for dp_id in (
        "L5.surprise.sell_side",
        "L5.fcst.revenue_margin",
        "L5.fcst.eps_cf",
        "L5.fcst.revisions",
    ):
        assert dp_id in by_dp
        assert by_dp[dp_id][3] == "Inactive"
        assert by_dp[dp_id][5] == "tushare:report_rc"
    payload = json.loads(by_dp["L5.surprise.sell_side"][2])
    assert payload["reason"] == "report_rc permission unavailable"
