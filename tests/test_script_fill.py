"""Hermetic tests for the deterministic script-fill parsers (no DB / no network)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.script_fill import (  # noqa: E402
    _is_domestic,
    _native,
    _parse_customer_concentration,
    _parse_revenue_structure,
    parse_buyback_dividend,
    parse_earnings_guidance,
    parse_insider_sell,
    parse_management_change,
)


def test_is_domestic_variants():
    for d in ("中国大陆", "境内", "内销", "国内", "中国"):
        assert _is_domestic(d)
    for o in ("境外", "海外", "国外", "外销", "中国港澳台地区", "亚洲（不含中国）"):
        assert not _is_domestic(o)


def test_parse_revenue_structure_huafen_style():
    # 000063 style: 一、按行业划分 / 二、按业务划分 / 三、按地区划分
    text = (
        "营业收入构成\n一、按行业划分\n计算机、通信和其他 133,895.5 100%\n合计 133,895.5 100%\n"
        "二、按业务划分\n运营商网络 62,857.0 46.94%\n政企业务 37,222.1 27.80%\n消费者业务 33,816.4 25.26%\n合计 133,895.5 100%\n"
        "三、按地区划分\n中国 89,734.1 67.02%\n境外 44,161.4 32.98%\n"
    )
    products, region = _parse_revenue_structure(text)
    names = {p["name"] for p in products}
    assert {"运营商网络", "政企业务", "消费者业务"} <= names      # 分产品 preferred over 分行业
    assert region and abs(region["domestic_pct"] - 67.02) < 0.1


def test_parse_revenue_structure_fenchanpin_style_and_stops_at_subtable():
    # 300394 style: 分地区 then a 分销售模式 / 对主要收入来源地 sub-table that must NOT leak in
    text = (
        "分产品\n光有源器件 5,000 58.06%\n光无源器件 3,400 40.37%\n其他 200 1.57%\n"
        "分地区\n内销 1,324 25.65%\n外销 3,838 74.35%\n"
        "对主要收入来源地的销售情况\n广东 900 60.0%\n江苏 600 40.0%\n"
    )
    products, region = _parse_revenue_structure(text)
    assert {"光有源器件", "光无源器件"} <= {p["name"] for p in products}
    # region stops once 内销+外销 reach ~100; the city sub-table is ignored
    assert region and abs(region["domestic_pct"] - 25.65) < 0.1


def test_parse_revenue_structure_rejects_number_names():
    text = "分产品\n数据通讯 14,656,300,288 77.36%\n智能汽车 3,044,579,100 16.07%\n"
    products, _ = _parse_revenue_structure(text)
    names = {p["name"] for p in products}
    assert "数据通讯" in names and "智能汽车" in names           # leaked figures stripped
    assert not any(any(c.isdigit() for c in n[:6]) for n in names if "3C" not in n)


def test_parse_revenue_structure_insane_block_discarded():
    # a block that doesn't sum to ~100 is discarded (avoids garbage)
    text = "分地区\n某区 10 10.0%\n另区 5 5.0%\n"  # sums to 15% → not a real breakdown
    _, region = _parse_revenue_structure(text)
    assert region is None


def test_parse_customer_concentration():
    text = "前五名客户合计的销售金额为60,084.6百万元，占本集团销售总额的44.87%。前五名供应商合计的采购金额占采购总额的19.53%。"
    c = _parse_customer_concentration(text)
    assert c and abs(c["top5_customer_pct"] - 44.87) < 0.1
    assert abs(c["top5_supplier_pct"] - 19.53) < 0.1


def test_native_coerces_numpy_and_nan():
    import math
    out = _native({"a": [{"b": 1.0}], "c": float("nan")})
    assert out["a"][0]["b"] == 1.0 and out["c"] is None
    assert not isinstance(out["c"], float) or out["c"] is None


# ── Track-B structured catalyst/risk parsers (hermetic, mock records) ────────

def test_buyback_dividend_prefers_implemented_and_is_positive():
    # latest by end_date is a 预案 (not yet implemented); parser must pick the
    # latest *实施* record and report a positive expectation_gap signal.
    out = parse_buyback_dividend([
        {"div_proc": "预案", "end_date": "20251231", "cash_div": 5.0},
        {"div_proc": "实施", "end_date": "20241231", "cash_div": 0.3,
         "stk_div": 0.0, "ann_date": "20250401"},
    ])
    assert out is not None
    assert out["data_status"] == "Known"
    assert out["direction"] == "positive"
    assert out["value"]["div_proc"] == "实施"
    # a 0.3元/股 dividend is a moderate (not saturated) positive signal
    assert 0.0 < out["value"]["score"] < 0.5
    assert out["evidence_sources"][0]["dp_id"] == "dividend"


def test_buyback_dividend_none_when_no_cash_or_stock():
    assert parse_buyback_dividend([]) is None
    assert parse_buyback_dividend([
        {"div_proc": "实施", "end_date": "20241231", "cash_div": 0.0, "stk_div": 0.0},
    ]) is None


def test_earnings_guidance_direction_by_type():
    up = parse_earnings_guidance([
        {"type": "预增", "end_date": "20251231",
         "p_change_min": 80, "p_change_max": 120},
    ])
    assert up and up["direction"] == "positive"
    assert 0.5 < up["value"]["score"] <= 1.0       # +100% avg → strong positive

    down = parse_earnings_guidance([
        {"type": "预减", "end_date": "20251231",
         "p_change_min": -60, "p_change_max": -40},
    ])
    assert down and down["direction"] == "negative"  # 预减 LOWERS expectation_gap
    assert down["value"]["score"] > 0                # magnitude is positive; sign via direction

    # 扭亏 is a positive surprise even with no clean p_change band
    turn = parse_earnings_guidance([
        {"type": "扭亏", "end_date": "20251231",
         "p_change_min": None, "p_change_max": None},
    ])
    assert turn and turn["direction"] == "positive"
    assert turn["value"]["score"] >= 0.15            # floored so a real call isn't ~0


def test_earnings_guidance_unknown_type_skipped():
    # 续盈 with no magnitude / unrecognized type → no clean direction → None
    assert parse_earnings_guidance([
        {"type": "不确定", "end_date": "20251231",
         "p_change_min": None, "p_change_max": None},
    ]) is None


def test_insider_sell_window_and_direction():
    out = parse_insider_sell([
        {"in_de": "DE", "change_ratio": 2.5, "ann_date": "20260301"},
        {"in_de": "IN", "change_ratio": 1.0, "ann_date": "20260201"},
        {"in_de": "DE", "change_ratio": 9.9, "ann_date": "20200101"},  # out of 1y window
    ], asof="20260606")
    assert out is not None
    assert out["direction"] == "negative"            # feeds risk_discount
    assert out["value"]["decrease_count"] == 1       # the 2020 row is excluded
    assert abs(out["value"]["net_decrease_pct"] - 2.5) < 1e-6
    assert out["value"]["score"] > 0


def test_insider_sell_none_when_only_increases():
    assert parse_insider_sell([
        {"in_de": "IN", "change_ratio": 3.0, "ann_date": "20260301"},
    ], asof="20260606") is None
    assert parse_insider_sell([], asof="20260606") is None


def test_management_change_departures_weighted():
    out = parse_management_change([
        {"name": "张三", "title": "董事长", "end_date": "20260101", "ann_date": "20260105"},
        {"name": "李四", "title": "独立董事", "begin_date": "20200101", "ann_date": "20200105"},  # 入职, not departure
        {"name": "王五", "title": "财务总监", "end_date": "20190101", "ann_date": "20190105"},  # out of window
    ], asof="20260606")
    assert out is not None
    assert out["direction"] == "negative"
    assert out["value"]["departure_count"] == 1      # only 张三 departed in window
    assert out["value"]["weighted_departures"] == 1.5  # 董事长 is a key title (×1.5)
    assert "张三" in out["value"]["people"]


def test_management_change_none_when_no_departures():
    # only 入职 (begin_date, no end_date) → no departure event
    assert parse_management_change([
        {"name": "赵六", "title": "总经理", "begin_date": "20260101", "ann_date": "20260105"},
    ], asof="20260606") is None
    assert parse_management_change([], asof="20260606") is None
