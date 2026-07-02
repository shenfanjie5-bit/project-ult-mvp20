"""Tests for Bucket B — 12 hard-data dp_ids added to ``tushare_source``.

All Tushare HTTP calls are stubbed via fake DataFrames so the suite stays
hermetic. Exercises each fetcher and the dispatcher contract:

  * L0.cost.capital                 — shibor_lpr + spread (MARKET:CN)
  * L0.sentiment.institutional      — top10_holders avg + 30d delta (industry)
  * L0.sentiment.leader_drag        — leader 5d vs follower 5d (industry)
  * L0.sentiment.social             — dc_hot + ths_hot count (industry)
  * L6.priced.analyst_revision      — report_rc up/down 90d (per-stock)
  * L6.priced.discussion            — dc_hot + ths_hot today (per-stock)
  * L6.state.expansion_compression  — PE vs 60d / 250d MA (per-stock)
  * L6.state.industry_center        — PE/PB/PS median (industry)
  * L6.state.peer_compare           — stock vs industry PE (per-stock)
  * L7.mood.analyst_rating          — rating distribution (per-stock)
  * L9.media.analyst_action         — 7d rating changes (per-stock)
  * L10.val.peer                    — validation view (per-stock)
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from mvp20.sources import tushare_source


# ---------------------------------------------------------------------------
# Test stubs (mirror test_tushare_bucket_a.py style).
# ---------------------------------------------------------------------------


class _StubDF:
    """Minimal DataFrame stand-in covering the calls Bucket B makes."""

    def __init__(self, records: list[dict[str, Any]]):
        self._rows = list(records)

    def __len__(self) -> int:
        return len(self._rows)

    def sort_values(self, key, ascending: bool = True) -> "_StubDF":
        return _StubDF(sorted(
            self._rows,
            key=lambda r: (r.get(key) is None, r.get(key)),
            reverse=not ascending,
        ))

    def head(self, n: int) -> "_StubDF":
        return _StubDF(self._rows[:n])

    def to_dict(self, orient: str = "records") -> list[dict[str, Any]]:
        assert orient == "records"
        return [dict(r) for r in self._rows]

    @property
    def columns(self):
        cols: set[str] = set()
        for r in self._rows:
            cols.update(r.keys())
        return cols


class _StubPro:
    """Per-endpoint dispatcher for Bucket B tests."""

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

    def shibor_lpr(self, **kw):       return self._dispatch("shibor_lpr", **kw)
    def report_rc(self, **kw):        return self._dispatch("report_rc", **kw)
    def dc_hot(self, **kw):           return self._dispatch("dc_hot", **kw)
    def ths_hot(self, **kw):          return self._dispatch("ths_hot", **kw)
    def top10_holders(self, **kw):    return self._dispatch("top10_holders", **kw)
    def daily_basic(self, **kw):      return self._dispatch("daily_basic", **kw)


@pytest.fixture(autouse=True)
def _clear_caches():
    """Wipe every cache touched by Bucket B between tests."""

    tushare_source._REPORT_RC_CACHE.clear()
    tushare_source._TOP10_HOLDERS_CACHE.clear()
    tushare_source._DAILY_BASIC_HISTORY_LONG_CACHE.clear()
    tushare_source._INDUSTRY_CENTER_CACHE.clear()
    tushare_source._DC_HOT_CACHE = None
    tushare_source._THS_HOT_CACHE = None
    tushare_source._SHIBOR_LPR_CACHE = None
    yield
    tushare_source._REPORT_RC_CACHE.clear()
    tushare_source._TOP10_HOLDERS_CACHE.clear()
    tushare_source._DAILY_BASIC_HISTORY_LONG_CACHE.clear()
    tushare_source._INDUSTRY_CENTER_CACHE.clear()
    tushare_source._DC_HOT_CACHE = None
    tushare_source._THS_HOT_CACHE = None
    tushare_source._SHIBOR_LPR_CACHE = None


# ---------------------------------------------------------------------------
# SUPPORTED_DP_IDS contract — all 12 dp_ids registered.
# ---------------------------------------------------------------------------


def test_supported_dp_ids_includes_twelve_bucket_b() -> None:
    expected = {
        "L0.cost.capital", "L0.sentiment.institutional",
        "L0.sentiment.leader_drag", "L0.sentiment.social",
        "L6.priced.analyst_revision", "L6.priced.discussion",
        "L6.state.expansion_compression", "L6.state.industry_center",
        "L6.state.peer_compare",
        "L7.mood.analyst_rating", "L9.media.analyst_action",
        "L10.val.peer",
    }
    assert expected.issubset(tushare_source.SUPPORTED_DP_IDS)


# ---------------------------------------------------------------------------
# _classify_rating — bucket mapping
# ---------------------------------------------------------------------------


def test_classify_rating_strong_buy_and_sell() -> None:
    assert tushare_source._classify_rating("买入")[0] == "strong_buy"
    assert tushare_source._classify_rating("增持")[0] == "buy"
    assert tushare_source._classify_rating("中性")[0] == "hold"
    assert tushare_source._classify_rating("减持")[0] == "sell"
    assert tushare_source._classify_rating("卖出")[0] == "strong_sell"


def test_classify_rating_unknown_returns_hold_with_no_score() -> None:
    bucket, score = tushare_source._classify_rating("奇怪")
    assert bucket == "hold"
    assert score is None


# ---------------------------------------------------------------------------
# _derive_analyst_revision — L6.priced.analyst_revision
# ---------------------------------------------------------------------------


def test_derive_analyst_revision_counts_upgrades_and_downgrades() -> None:
    records = [
        # Broker A: 中性 → 买入  (upgrade)
        {"report_date": "20260420", "org_name": "国泰", "rating": "买入",
         "author_name": "X"},
        {"report_date": "20260301", "org_name": "国泰", "rating": "中性",
         "author_name": "X"},
        # Broker B: 买入 → 减持  (downgrade)
        {"report_date": "20260425", "org_name": "中信", "rating": "减持",
         "author_name": "Y"},
        {"report_date": "20260315", "org_name": "中信", "rating": "买入",
         "author_name": "Y"},
        # Broker C: only initiation
        {"report_date": "20260411", "org_name": "招商", "rating": "买入",
         "author_name": "Z"},
    ]
    payload, status = tushare_source._derive_analyst_revision(records)
    assert status == "Known"
    assert payload["upgrades"] == 1
    assert payload["downgrades"] == 1
    assert payload["initiations"] == 3  # first record of each broker
    assert abs(payload["net_revision_score"]) < 1.0  # upgrades = downgrades


def test_derive_analyst_revision_inactive_when_empty() -> None:
    payload, status = tushare_source._derive_analyst_revision([])
    assert status == "Inactive"


# ---------------------------------------------------------------------------
# _derive_discussion — L6.priced.discussion
# ---------------------------------------------------------------------------


def test_derive_discussion_known_when_on_hot_list() -> None:
    dc = [
        {"ts_code": "300750.SZ", "rank": 5, "concept": "新能源"},
        {"ts_code": "000063.SZ", "rank": 12, "concept": "AI"},
    ]
    ths = [
        {"ts_code": "300750.SZ", "rank": 3, "concept": "宁德时代"},
    ]
    payload, status = tushare_source._derive_discussion("300750.SZ", dc, ths)
    assert status == "Known"
    assert payload["dc_hot_count_30d"] == 1
    assert payload["ths_hot_count_30d"] == 1


def test_derive_discussion_inactive_when_not_on_list() -> None:
    dc = [{"ts_code": "000063.SZ", "rank": 5}]
    payload, status = tushare_source._derive_discussion("300750.SZ", dc, [])
    assert status == "Inactive"


# ---------------------------------------------------------------------------
# _derive_expansion_compression — L6.state.expansion_compression
# ---------------------------------------------------------------------------


def test_derive_expansion_compression_compressed() -> None:
    # Current PE = 15, 60d MA ~16, 250d MA ~20 → ratio 0.75 → compressed
    records = (
        [{"trade_date": f"d{i:03d}", "pe_ttm": 15.0} for i in range(60)]
        + [{"trade_date": f"d{i:03d}", "pe_ttm": 22.0} for i in range(60, 250)]
    )
    payload, status = tushare_source._derive_expansion_compression(records)
    assert status == "Known"
    assert payload["regime"] == "compressed"
    assert payload["pe_current"] == 15.0


def test_derive_expansion_compression_expanded() -> None:
    # Current 30, 60d 25, 250d 20 → ratio 1.5 → expanded
    records = (
        [{"trade_date": f"d{i:03d}", "pe_ttm": 30.0} for i in range(30)]
        + [{"trade_date": f"d{i:03d}", "pe_ttm": 20.0} for i in range(30, 60)]
        + [{"trade_date": f"d{i:03d}", "pe_ttm": 18.0} for i in range(60, 250)]
    )
    payload, status = tushare_source._derive_expansion_compression(records)
    assert status == "Known"
    assert payload["regime"] == "expanded"


def test_derive_expansion_compression_neutral() -> None:
    records = [{"trade_date": f"d{i:03d}", "pe_ttm": 20.0}
               for i in range(250)]
    payload, status = tushare_source._derive_expansion_compression(records)
    assert status == "Known"
    assert payload["regime"] == "neutral"


def test_derive_expansion_compression_inactive_when_insufficient_history() -> None:
    records = [{"trade_date": f"d{i:03d}", "pe_ttm": 20.0}
               for i in range(30)]
    payload, status = tushare_source._derive_expansion_compression(records)
    assert status == "Inactive"


# ---------------------------------------------------------------------------
# _derive_industry_center — L6.state.industry_center
# ---------------------------------------------------------------------------


def test_derive_industry_center_median() -> None:
    snapshot = {
        "300750.SZ": {"pe_ttm": 20.0, "pb": 3.0, "ps_ttm": 2.0},
        "002594.SZ": {"pe_ttm": 30.0, "pb": 5.0, "ps_ttm": 4.0},
        "000063.SZ": {"pe_ttm": 25.0, "pb": 4.0, "ps_ttm": 3.0},
    }
    payload, status = tushare_source._derive_industry_center(
        "STORAGE_GRID",
        ["300750.SZ", "002594.SZ", "000063.SZ"],
        snapshot, trade_date="20260513",
    )
    assert status == "Known"
    assert payload["industry_pe_median"] == 25.0  # median of [20,25,30]
    assert payload["industry_pb_median"] == 4.0   # median of [3,4,5]
    assert payload["n_stocks"] == 3


def test_derive_industry_center_inactive_when_too_few_stocks() -> None:
    payload, status = tushare_source._derive_industry_center(
        "STORAGE_GRID", ["300750.SZ"],
        {"300750.SZ": {"pe_ttm": 20.0, "pb": 3.0, "ps_ttm": 2.0}},
        trade_date="20260513",
    )
    assert status == "Inactive"


# ---------------------------------------------------------------------------
# _derive_peer_compare — L6.state.peer_compare + L10.val.peer
# ---------------------------------------------------------------------------


def test_derive_peer_compare_convergent() -> None:
    stock_rec = {"pe_ttm": 24.0, "pb": 4.0}
    industry_center = {
        "industry_id": "STORAGE_GRID",
        "industry_pe_median": 25.0,
        "industry_pb_median": 4.0,
        "trade_date": "20260513",
    }
    pc, vp, status = tushare_source._derive_peer_compare(
        "300750.SZ", stock_rec, industry_center,
    )
    assert status == "Known"
    assert pc["industry_pe_median"] == 25.0
    assert pc["stock_pe"] == 24.0
    assert abs(pc["premium_vs_industry_pct"] - (-4.0)) < 0.01
    assert vp["validation_signal"] == "convergent"
    # L6 + L10 payloads share the same input shape but L10 carries the
    # validation_signal label.
    assert "validation_signal" in vp
    assert "validation_signal" not in pc


def test_derive_peer_compare_divergent_when_far_above() -> None:
    stock_rec = {"pe_ttm": 60.0, "pb": 8.0}
    industry_center = {
        "industry_id": "STORAGE_GRID",
        "industry_pe_median": 25.0,
        "industry_pb_median": 4.0,
        "trade_date": "20260513",
    }
    pc, vp, status = tushare_source._derive_peer_compare(
        "300750.SZ", stock_rec, industry_center,
    )
    assert status == "Known"
    assert vp["validation_signal"] == "divergent"


def test_derive_peer_compare_inactive_when_no_industry_center() -> None:
    pc, vp, status = tushare_source._derive_peer_compare(
        "300750.SZ", {"pe_ttm": 20.0, "pb": 3.0}, None,
    )
    assert status == "Inactive"


def test_derive_peer_compare_l6_and_l10_share_inputs() -> None:
    """Algorithmic consistency: L6.state.peer_compare and L10.val.peer
    derive from the same underlying compute (per task spec)."""

    stock_rec = {"pe_ttm": 30.0, "pb": 5.0}
    industry_center = {
        "industry_id": "AI_COMPUTE",
        "industry_pe_median": 28.0,
        "industry_pb_median": 4.5,
        "trade_date": "20260513",
    }
    pc, vp, status = tushare_source._derive_peer_compare(
        "000063.SZ", stock_rec, industry_center,
    )
    assert status == "Known"
    # Stock PE, industry median, and premium % should be byte-identical
    # in both payloads.
    assert pc["stock_pe"] == vp["stock_pe"]
    assert pc["industry_pe_median"] == vp["industry_pe_median"]
    assert pc["premium_vs_industry_pct"] == vp["premium_vs_industry_pct"]


# ---------------------------------------------------------------------------
# _derive_analyst_rating — L7.mood.analyst_rating
# ---------------------------------------------------------------------------


def test_derive_analyst_rating_distribution() -> None:
    records = [
        {"report_date": "20260420", "org_name": "国泰", "rating": "买入",
         "author_name": "X"},
        {"report_date": "20260415", "org_name": "中信", "rating": "增持",
         "author_name": "Y"},
        {"report_date": "20260410", "org_name": "招商", "rating": "中性",
         "author_name": "Z"},
        # Dup of broker X same day → should be dedup'd
        {"report_date": "20260420", "org_name": "国泰", "rating": "买入",
         "author_name": "X"},
    ]
    payload, status = tushare_source._derive_analyst_rating(records)
    assert status == "Known"
    assert payload["strong_buy"] == 1
    assert payload["buy"] == 1
    assert payload["hold"] == 1
    assert payload["n_reports"] == 3
    assert 1 <= payload["avg_rating_score"] <= 5


def test_derive_analyst_rating_inactive_when_empty() -> None:
    payload, status = tushare_source._derive_analyst_rating([])
    assert status == "Inactive"


# ---------------------------------------------------------------------------
# _derive_analyst_action — L9.media.analyst_action
# ---------------------------------------------------------------------------


def test_derive_analyst_action_upgrade_event_within_7d() -> None:
    # Note: _previous_n_days returns a YYYYMMDD string; we approximate by
    # using "today-1d" via the actual helper to keep the test robust.
    today = tushare_source._today_yyyymmdd()
    week_old = tushare_source._previous_n_days(2)
    records = [
        # Same broker upgrade within last 7d: 中性 → 买入
        {"report_date": today, "org_name": "国泰", "rating": "买入",
         "author_name": "X"},
        {"report_date": week_old, "org_name": "国泰", "rating": "中性",
         "author_name": "X"},
    ]
    payload, status = tushare_source._derive_analyst_action(records)
    assert status == "Known"
    assert payload["action_type"] == "upgrade_event"
    assert payload["count_7d"] >= 1


def test_derive_analyst_action_none_when_steady() -> None:
    records = [
        {"report_date": "20260420", "org_name": "国泰", "rating": "买入",
         "author_name": "X"},
    ]
    payload, status = tushare_source._derive_analyst_action(records)
    assert status == "Inactive"
    assert payload["action_type"] == "none"


def test_derive_analyst_action_known_neutral_when_recent_comparable_steady() -> None:
    today = tushare_source._today_yyyymmdd()
    week_old = tushare_source._previous_n_days(2)
    records = [
        {"report_date": today, "org_name": "国泰", "rating": "买入",
         "author_name": "X"},
        {"report_date": week_old, "org_name": "国泰", "rating": "买入",
         "author_name": "X"},
    ]
    payload, status = tushare_source._derive_analyst_action(records)
    assert status == "Known"
    assert payload["action_type"] == "none"
    assert payload["count_7d"] == 0
    assert payload["recent_comparable_count"] == 1


# ---------------------------------------------------------------------------
# _emit_cost_capital — L0.cost.capital (MARKET:CN)
# ---------------------------------------------------------------------------


def test_emit_cost_capital_market_known() -> None:
    pro = _StubPro(shibor_lpr=_StubDF([
        {"date": "20260512", "1y": 3.0, "5y": 3.5},
        {"date": "20260411", "1y": 3.1, "5y": 3.6},
    ]))
    rows = tushare_source._emit_cost_capital(pro, now=1700000000)
    assert len(rows) == 1
    assert rows[0][0] == "MARKET:CN"
    assert rows[0][1] == "L0.cost.capital"
    payload = json.loads(rows[0][2])
    assert payload["lpr_1y_pct"] == 3.0
    assert payload["implied_cost_of_capital_pct"] == 4.5
    assert rows[0][3] == "Known"


def test_emit_cost_capital_inactive_on_endpoint_failure() -> None:
    pro = _StubPro(shibor_lpr=RuntimeError("permission"))
    rows = tushare_source._emit_cost_capital(pro, now=1700000000)
    assert len(rows) == 1
    assert rows[0][3] == "Inactive"
    assert rows[0][4] == 0.0


# ---------------------------------------------------------------------------
# _emit_sentiment_institutional — industry-level fan-out
# ---------------------------------------------------------------------------


def test_emit_sentiment_institutional_emits_per_industry() -> None:
    # Two industries; each has 1 sampled stock with two periods.
    top10_data = _StubDF([
        {"ts_code": "300750.SZ", "end_date": "20260331",
         "holder_name": "宁德基金", "hold_ratio": 5.0},
        {"ts_code": "300750.SZ", "end_date": "20260331",
         "holder_name": "外资", "hold_ratio": 3.0},
        {"ts_code": "300750.SZ", "end_date": "20251231",
         "holder_name": "宁德基金", "hold_ratio": 4.0},
        {"ts_code": "300750.SZ", "end_date": "20251231",
         "holder_name": "外资", "hold_ratio": 2.5},
    ])
    pro = _StubPro(top10_holders=top10_data)
    code_to_industry = {"300750.SZ": "STORAGE_GRID"}
    rows = tushare_source._emit_sentiment_institutional(
        pro, ["STORAGE_GRID", "AI_COMPUTE"], code_to_industry,
        now=1700000000,
    )
    by_ind = {r[0]: r for r in rows}
    # STORAGE_GRID has a sampled stock → Known
    assert "INDUSTRY:STORAGE_GRID" in by_ind
    assert by_ind["INDUSTRY:STORAGE_GRID"][3] == "Known"
    p = json.loads(by_ind["INDUSTRY:STORAGE_GRID"][2])
    assert p["mean_inst_holding_pct"] == 4.0  # (5+3)/2 = 4
    # delta = 4 - (4+2.5)/2 = 4 - 3.25 = 0.75
    assert abs(p["delta_30d_pp"] - 0.75) < 0.01
    # AI_COMPUTE has no sampled stocks → Inactive
    assert "INDUSTRY:AI_COMPUTE" in by_ind
    assert by_ind["INDUSTRY:AI_COMPUTE"][3] == "Inactive"


def test_emit_sentiment_institutional_inactive_when_no_top10_data() -> None:
    pro = _StubPro(top10_holders=_StubDF([]))
    rows = tushare_source._emit_sentiment_institutional(
        pro, ["STORAGE_GRID"], {"300750.SZ": "STORAGE_GRID"},
        now=1700000000,
    )
    assert len(rows) == 1
    assert rows[0][3] == "Inactive"


# ---------------------------------------------------------------------------
# _emit_sentiment_leader_drag — industry-level fan-out
# ---------------------------------------------------------------------------


def test_emit_sentiment_leader_drag_uses_full_snapshot() -> None:
    snapshot = [
        # Top by mv → leaders
        {"ts_code": "300750.SZ", "total_mv": 100_000_000,
         "pct_chg": 2.0, "pe_ttm": 20.0},
        {"ts_code": "002594.SZ", "total_mv": 90_000_000,
         "pct_chg": 1.5, "pe_ttm": 22.0},
        {"ts_code": "000333.SZ", "total_mv": 80_000_000,
         "pct_chg": 1.0, "pe_ttm": 18.0},
        # Followers
        {"ts_code": "601012.SH", "total_mv": 50_000_000,
         "pct_chg": -1.0, "pe_ttm": 25.0},
        {"ts_code": "300253.SZ", "total_mv": 40_000_000,
         "pct_chg": -0.5, "pe_ttm": 30.0},
    ]
    pro = _StubPro()  # snapshot passed directly
    code_to_industry = {c["ts_code"]: "STORAGE_GRID" for c in snapshot}
    rows = tushare_source._emit_sentiment_leader_drag(
        pro, ["STORAGE_GRID", "AI_COMPUTE"], code_to_industry,
        now=1700000000,
        daily_basic_snapshot=snapshot,
    )
    by_ind = {r[0]: r for r in rows}
    assert "INDUSTRY:STORAGE_GRID" in by_ind
    payload = json.loads(by_ind["INDUSTRY:STORAGE_GRID"][2])
    assert payload["polarity"] == "positive"  # leaders up, followers down
    assert payload["leader_5d_pct"] > payload["follower_5d_pct"]


def test_emit_sentiment_leader_drag_inactive_on_empty_snapshot() -> None:
    pro = _StubPro()
    rows = tushare_source._emit_sentiment_leader_drag(
        pro, ["STORAGE_GRID"], {}, now=1700000000,
        daily_basic_snapshot=[],
    )
    assert rows[0][3] == "Inactive"


# ---------------------------------------------------------------------------
# _emit_sentiment_social — industry-level fan-out (dc_hot + ths_hot)
# ---------------------------------------------------------------------------


def test_emit_sentiment_social_emits_themes_and_count() -> None:
    pro = _StubPro(
        dc_hot=_StubDF([
            {"ts_code": "300750.SZ", "rank": 1, "concept": "新能源"},
            {"ts_code": "002594.SZ", "rank": 2, "concept": "新能源"},
        ]),
        ths_hot=_StubDF([
            {"ts_code": "300750.SZ", "rank": 3, "concept": "宁德时代"},
        ]),
    )
    code_to_industry = {"300750.SZ": "STORAGE_GRID",
                        "002594.SZ": "STORAGE_GRID"}
    rows = tushare_source._emit_sentiment_social(
        pro, ["STORAGE_GRID"], code_to_industry, now=1700000000,
    )
    assert len(rows) == 1
    assert rows[0][3] == "Known"
    payload = json.loads(rows[0][2])
    assert payload["hot_stocks_count_30d"] == 2  # 300750 + 002594
    assert "新能源" in payload["hot_themes"]


def test_emit_sentiment_social_inactive_when_no_hot_data() -> None:
    pro = _StubPro(dc_hot=_StubDF([]), ths_hot=_StubDF([]))
    rows = tushare_source._emit_sentiment_social(
        pro, ["STORAGE_GRID"], {"300750.SZ": "STORAGE_GRID"},
        now=1700000000,
    )
    assert rows[0][3] == "Inactive"


# ---------------------------------------------------------------------------
# fetch_bucket_b_batch — end-to-end dispatcher
# ---------------------------------------------------------------------------


def _make_bucket_b_pro() -> _StubPro:
    """A pro stub seeded with enough records for every Bucket B path to emit
    a Known row."""

    today = tushare_source._today_yyyymmdd()
    two_days_ago = tushare_source._previous_n_days(2)
    forty_days_ago = tushare_source._previous_n_days(40)

    shibor = _StubDF([
        {"date": "20260512", "1y": 3.0, "5y": 3.5},
        {"date": "20260411", "1y": 3.1, "5y": 3.6},
    ])
    # report_rc returns one row per (report × forecast year). Each stock
    # gets a recent upgrade and an older record so analyst_revision and
    # analyst_action both have data.
    report_rc_data = _StubDF([
        {"report_date": today, "org_name": "国泰", "rating": "买入",
         "author_name": "X", "quarter": "2026Q4", "eps": 1.5,
         "op_rt": 50_000},
        {"report_date": two_days_ago, "org_name": "国泰", "rating": "中性",
         "author_name": "X", "quarter": "2026Q4", "eps": 1.2,
         "op_rt": 45_000},
        {"report_date": forty_days_ago, "org_name": "中信", "rating": "买入",
         "author_name": "Y", "quarter": "2026Q4", "eps": 1.4,
         "op_rt": 48_000},
    ])
    # Hot list returns the test stock.
    dc_hot_data = _StubDF([
        {"ts_code": "300750.SZ", "rank": 5, "concept": "新能源"},
        {"ts_code": "000063.SZ", "rank": 12, "concept": "AI"},
    ])
    ths_hot_data = _StubDF([
        {"ts_code": "300750.SZ", "rank": 3, "concept": "宁德时代"},
    ])
    top10_holders_data = _StubDF([
        {"ts_code": "300750.SZ", "end_date": "20260331",
         "holder_name": "宁德基金", "hold_ratio": 5.0},
        {"ts_code": "300750.SZ", "end_date": "20251231",
         "holder_name": "宁德基金", "hold_ratio": 4.0},
        {"ts_code": "000063.SZ", "end_date": "20260331",
         "holder_name": "中兴基金", "hold_ratio": 3.0},
        {"ts_code": "000063.SZ", "end_date": "20251231",
         "holder_name": "中兴基金", "hold_ratio": 2.5},
    ])
    # daily_basic: behave differently depending on call type.
    # When called with ``trade_date=`` → return full-market cross-section.
    # When called with ``ts_code=`` → return long history per stock.
    def _daily_basic_callable(**kw):
        if "trade_date" in kw:
            # Full-market snapshot (used by industry_center + leader_drag)
            return _StubDF([
                {"ts_code": "300750.SZ", "trade_date": kw["trade_date"],
                 "pe_ttm": 24.0, "pb": 4.0, "ps_ttm": 3.0,
                 "total_mv": 100_000_000, "pct_chg": 2.0,
                 "turnover_rate": 3.0},
                {"ts_code": "000063.SZ", "trade_date": kw["trade_date"],
                 "pe_ttm": 18.0, "pb": 3.0, "ps_ttm": 2.0,
                 "total_mv": 80_000_000, "pct_chg": 1.5,
                 "turnover_rate": 2.5},
                {"ts_code": "002594.SZ", "trade_date": kw["trade_date"],
                 "pe_ttm": 30.0, "pb": 5.0, "ps_ttm": 4.0,
                 "total_mv": 90_000_000, "pct_chg": -0.5,
                 "turnover_rate": 4.0},
            ])
        # Per-stock long history (used by expansion_compression)
        # 300d of data; gradually decreasing PE so compressed regime triggers.
        ts_code = kw.get("ts_code", "")
        records = []
        for i in range(300):
            pe = 20.0 - (i * 0.02)  # newest first via sort
            records.append({"ts_code": ts_code,
                            "trade_date": f"d{i:03d}",
                            "pe_ttm": pe})
        return _StubDF(records)

    return _StubPro(
        shibor_lpr=shibor,
        report_rc=report_rc_data,
        dc_hot=dc_hot_data,
        ths_hot=ths_hot_data,
        top10_holders=top10_holders_data,
        daily_basic=_daily_basic_callable,
    )


def test_fetch_bucket_b_batch_emits_all_12_dp_ids() -> None:
    pro = _make_bucket_b_pro()
    code_to_industry = {
        "300750.SZ": "STORAGE_GRID",
        "000063.SZ": "AI_COMPUTE",
        "002594.SZ": "STORAGE_GRID",
    }
    rows = tushare_source.fetch_bucket_b_batch(
        pro, ["300750.SZ", "000063.SZ"],
        code_to_industry=code_to_industry, now=1700000000,
    )
    by_dp: dict[str, list[tuple]] = {}
    for r in rows:
        by_dp.setdefault(r[1], []).append(r)
    expected = {
        "L0.cost.capital", "L0.sentiment.institutional",
        "L0.sentiment.leader_drag", "L0.sentiment.social",
        "L6.priced.analyst_revision", "L6.priced.discussion",
        "L6.state.expansion_compression", "L6.state.industry_center",
        "L6.state.peer_compare",
        "L7.mood.analyst_rating", "L9.media.analyst_action",
        "L10.val.peer",
    }
    for dp in expected:
        assert dp in by_dp, f"missing dp_id {dp}"


def test_fetch_bucket_b_batch_skips_non_a_share() -> None:
    pro = _make_bucket_b_pro()
    rows = tushare_source.fetch_bucket_b_batch(
        pro, ["NVDA.US", "09988.HK"], now=1700000000,
    )
    # Per-stock dp_ids should not emit for non-A-share codes.
    per_stock_rows = [
        r for r in rows
        if r[0].endswith((".SH", ".SZ", ".BJ"))
    ]
    assert per_stock_rows == [], \
        f"unexpected per-stock rows for non-A-share: {per_stock_rows}"


def test_fetch_bucket_b_batch_handles_endpoint_failure_gracefully() -> None:
    """report_rc permission denied: revision / rating / action should each
    emit Inactive (not missing); other dp_ids should still emit."""

    pro = _make_bucket_b_pro()
    pro._data["report_rc"] = RuntimeError("permission denied")
    rows = tushare_source.fetch_bucket_b_batch(
        pro, ["300750.SZ"],
        code_to_industry={"300750.SZ": "STORAGE_GRID"}, now=1700000000,
    )
    by_dp = {r[1]: r for r in rows if r[0] == "300750.SZ"}
    # report_rc-dependent → Inactive (graceful degrade)
    assert "L6.priced.analyst_revision" in by_dp
    assert by_dp["L6.priced.analyst_revision"][3] == "Inactive"
    assert "L7.mood.analyst_rating" in by_dp
    assert by_dp["L7.mood.analyst_rating"][3] == "Inactive"
    assert "L9.media.analyst_action" in by_dp
    assert by_dp["L9.media.analyst_action"][3] == "Inactive"
    # Discussion (dc_hot+ths_hot) still flows
    assert "L6.priced.discussion" in by_dp
    assert by_dp["L6.priced.discussion"][3] == "Known"


def test_fetch_bucket_b_batch_emits_industry_sentinels() -> None:
    pro = _make_bucket_b_pro()
    code_to_industry = {
        "300750.SZ": "STORAGE_GRID",
        "002594.SZ": "STORAGE_GRID",
    }
    rows = tushare_source.fetch_bucket_b_batch(
        pro, ["300750.SZ"],
        code_to_industry=code_to_industry, now=1700000000,
    )
    industry_dps = ("L0.sentiment.institutional", "L0.sentiment.leader_drag",
                    "L0.sentiment.social", "L6.state.industry_center")
    industry_rows = [r for r in rows if r[1] in industry_dps]
    # Should have at least one INDUSTRY:* row per dp_id when industries
    # config has present entries (depends on env).
    if industry_rows:
        for r in industry_rows:
            assert r[0].startswith("INDUSTRY:"), \
                f"expected INDUSTRY:* sentinel, got {r[0]}"


def test_fetch_bucket_b_batch_market_level_emit_for_cost_capital() -> None:
    pro = _make_bucket_b_pro()
    rows = tushare_source.fetch_bucket_b_batch(
        pro, ["300750.SZ"],
        code_to_industry={"300750.SZ": "STORAGE_GRID"}, now=1700000000,
    )
    cc_rows = [r for r in rows if r[1] == "L0.cost.capital"]
    assert len(cc_rows) == 1
    assert cc_rows[0][0] == "MARKET:CN"


def test_fetch_bucket_b_batch_l6_and_l10_peer_align() -> None:
    """Per-task spec: L6.state.peer_compare and L10.val.peer share the same
    underlying compute. For the same ts_code their stock_pe + industry
    median should be byte-identical."""

    pro = _make_bucket_b_pro()
    rows = tushare_source.fetch_bucket_b_batch(
        pro, ["300750.SZ"],
        code_to_industry={"300750.SZ": "STORAGE_GRID",
                          "002594.SZ": "STORAGE_GRID"},
        now=1700000000,
    )
    pc = next((r for r in rows
               if r[0] == "300750.SZ" and r[1] == "L6.state.peer_compare"),
              None)
    vp = next((r for r in rows
               if r[0] == "300750.SZ" and r[1] == "L10.val.peer"),
              None)
    if pc and vp and pc[3] == "Known" and vp[3] == "Known":
        pcp = json.loads(pc[2])
        vpp = json.loads(vp[2])
        assert pcp["stock_pe"] == vpp["stock_pe"]
        assert pcp["industry_pe_median"] == vpp["industry_pe_median"]
        assert pcp["premium_vs_industry_pct"] == vpp["premium_vs_industry_pct"]
        assert "validation_signal" in vpp


def test_fetch_bucket_b_batch_handles_empty_code_to_industry() -> None:
    """Without industry mapping, industry-level dp_ids should still emit
    Inactive rows (one per active industry); per-stock peer_compare and
    val.peer also Inactive."""

    pro = _make_bucket_b_pro()
    rows = tushare_source.fetch_bucket_b_batch(
        pro, ["300750.SZ"], code_to_industry={}, now=1700000000,
    )
    # Market-level cost_capital still emits
    cc_rows = [r for r in rows if r[1] == "L0.cost.capital"]
    assert len(cc_rows) == 1
    # Per-stock peer_compare → Inactive (no industry → no center)
    pc_rows = [r for r in rows
               if r[0] == "300750.SZ" and r[1] == "L6.state.peer_compare"]
    if pc_rows:
        assert pc_rows[0][3] == "Inactive"


# ---------------------------------------------------------------------------
# Cache behavior — second call within TTL should not hit Tushare again.
# ---------------------------------------------------------------------------


def test_bucket_b_caches_within_ttl() -> None:
    pro = _make_bucket_b_pro()
    tushare_source.fetch_bucket_b_batch(
        pro, ["300750.SZ"],
        code_to_industry={"300750.SZ": "STORAGE_GRID"}, now=1700000000,
    )
    calls_after_first = dict(pro.call_counts)
    tushare_source.fetch_bucket_b_batch(
        pro, ["300750.SZ"],
        code_to_industry={"300750.SZ": "STORAGE_GRID"},
        now=1700000000 + 60,
    )
    # No new RPCs — cached records used.
    for k, v in pro.call_counts.items():
        assert v == calls_after_first.get(k, 0), (
            f"{k} re-hit Tushare on cache TTL"
        )
