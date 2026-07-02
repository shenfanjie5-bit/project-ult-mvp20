"""Hermetic tests for the two Tushare data sources wired in this change:

  1. fx_daily (RMB / cross-border FX) → ``L7.env.fx`` + ``L9.macro.fx``
     MARKET:CN sentinels, emitted by ``_emit_fx_cnh`` (folded into
     ``fetch_macro_china_batch``).
  2. 龙虎榜 institutional flow (top_list + top_inst) → enriched
     ``L9.capital.inst_buy_sell`` per-stock payload, computed by
     ``_compute_inst_buy_sell_payload`` and emitted from
     ``_fetch_a_share_capital_events``.

Every payload is also pushed through ``mvp20.aggregator`` (the real
consumer) to prove the emitted ``score`` / ``direction`` keys actually
produce a non-zero, correctly-signed leaf magnitude. No live Tushare HTTP
is touched — a tiny ``_StubDF`` / ``_StubPro`` stands in for ``pro.*``.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from mvp20 import aggregator as agg
from mvp20.sources import tushare_source as ts


# ---------------------------------------------------------------------------
# Tiny DataFrame / pro stubs (records-based; quack like the calls we make).
# ---------------------------------------------------------------------------


class _StubDF:
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


class _StubPro:
    """fx_daily + top_list + top_inst dispatcher.

    ``fx_data`` maps symbol → list[dict] (or Exception). ``top_list_data`` /
    ``top_inst_data`` map trade_date → list[dict] (or Exception); a record's
    ``trade_date`` is matched against the requested date.
    """

    def __init__(self, *, fx_data=None, top_list_data=None, top_inst_data=None):
        self._fx = fx_data or {}
        self._tl = top_list_data or {}
        self._ti = top_inst_data or {}
        self.fx_calls: list[str] = []
        self.top_list_calls: list[str] = []
        self.top_inst_calls: list[str] = []

    def fx_daily(self, ts_code=None, fields=None):
        self.fx_calls.append(ts_code)
        v = self._fx.get(ts_code)
        if isinstance(v, Exception):
            raise v
        return _StubDF(v or [])

    def top_list(self, trade_date=None, fields=None):
        self.top_list_calls.append(trade_date)
        v = self._tl.get(trade_date)
        if isinstance(v, Exception):
            raise v
        return _StubDF(v or [])

    def top_inst(self, trade_date=None, fields=None):
        self.top_inst_calls.append(trade_date)
        v = self._ti.get(trade_date)
        if isinstance(v, Exception):
            raise v
        return _StubDF(v or [])


_NOW = 1_700_000_000


def _fx_series(symbol: str, closes: list[float]) -> list[dict[str, Any]]:
    """Build fx_daily records; ``closes[0]`` is the OLDEST, last is latest.

    trade_date is assigned ascending so the producer's
    ``sort_values(trade_date, ascending=False)`` puts the last close first.
    """

    recs = []
    for i, c in enumerate(closes):
        recs.append({
            "ts_code": symbol,
            "trade_date": f"202604{10 + i:02d}",
            "bid_close": c,
            "ask_close": c,
        })
    return recs


# ===========================================================================
# 1. fx_daily → L7.env.fx + L9.macro.fx
# ===========================================================================


def test_fx_supported_dp_ids() -> None:
    assert {"L7.env.fx", "L9.macro.fx"}.issubset(ts.SUPPORTED_DP_IDS)


def test_fx_rmb_appreciation_positive_l7_known_neutral_l9() -> None:
    # USDCNH falls 7.25 → 7.10 over the window → RMB appreciates → L7 positive
    # regime tilt; L9 (depreciation risk) is a measured Known-neutral no-risk row.
    pro = _StubPro(fx_data={
        "USDCNH.FXCM": _fx_series("USDCNH.FXCM",
                                  [7.25, 7.22, 7.18, 7.14, 7.10]),
    })
    rows = ts._emit_fx_cnh(pro, _NOW)
    by_dp = {r[1]: r for r in rows}

    assert set(by_dp) == {"L7.env.fx", "L9.macro.fx"}

    ts_code, dp, val, status, conf, source, t = by_dp["L7.env.fx"]
    assert ts_code == "MARKET:CN"
    assert status == "Known"
    assert source == "tushare:fx_daily"
    assert t == _NOW
    p7 = json.loads(val)
    assert p7["direction"] == "positive"          # RMB strengthening
    assert p7["rmb_appreciation_pct"] > 0
    assert p7["usdcnh_change_pct"] < 0
    assert p7["symbol"] == "USDCNH.FXCM"
    assert 0.0 < p7["score"] <= 1.0
    # Real consumer: positive leaf magnitude with +1 direction sign.
    assert agg._to_scalar(p7) == pytest.approx(p7["score"], abs=1e-9)
    assert agg._direction_sign(p7["direction"]) == 1.0

    # L9 risk does NOT fire on appreciation → Known-neutral.
    _, _, val9, status9, _, _, _ = by_dp["L9.macro.fx"]
    assert status9 == "Known"
    p9 = json.loads(val9)
    assert p9["direction"] == "neutral"
    assert p9["risk_event"] is False
    assert p9["score"] == 0.0
    assert agg._direction_sign(p9["direction"]) == 0.0


def test_fx_rmb_depreciation_fires_l9_risk_negative() -> None:
    # USDCNH rises 7.10 → 7.25 (≈+2.1% > 1.0% threshold) → RMB depreciates.
    pro = _StubPro(fx_data={
        "USDCNH.FXCM": _fx_series("USDCNH.FXCM",
                                  [7.10, 7.13, 7.17, 7.20, 7.25]),
    })
    rows = ts._emit_fx_cnh(pro, _NOW)
    by_dp = {r[1]: r for r in rows}

    p7 = json.loads(by_dp["L7.env.fx"][2])
    assert p7["direction"] == "negative"          # risk-off tilt
    assert p7["usdcnh_change_pct"] > 0
    assert agg._direction_sign(p7["direction"]) == -1.0

    _, _, val9, status9, _, _, _ = by_dp["L9.macro.fx"]
    assert status9 == "Known"                     # risk event fires
    p9 = json.loads(val9)
    assert p9["direction"] == "negative"
    assert p9["risk_event"] is True
    assert p9["score"] > 0.0
    assert p9["threshold_pct"] == ts._FX_RISK_THRESHOLD_PCT
    assert agg._direction_sign(p9["direction"]) == -1.0


def test_fx_symbol_fallback_when_primary_empty() -> None:
    # USDCNH.FXCM empty → fall back to USDCNY.CFETS.
    pro = _StubPro(fx_data={
        "USDCNH.FXCM": [],
        "USDCNY.CFETS": _fx_series("USDCNY.CFETS",
                                   [7.10, 7.15, 7.20, 7.25, 7.28]),
    })
    rows = ts._emit_fx_cnh(pro, _NOW)
    assert len(rows) == 2
    p7 = json.loads(rows[0][2])
    assert p7["symbol"] == "USDCNY.CFETS"
    # Both candidate symbols were probed in priority order.
    assert pro.fx_calls[:2] == ["USDCNH.FXCM", "USDCNY.CFETS"]


def test_fx_no_data_returns_empty_no_fabrication() -> None:
    # Every symbol empty → no rows (macro dispatcher logs it; field stays
    # Unknown rather than a fabricated tilt).
    pro = _StubPro(fx_data={})
    assert ts._emit_fx_cnh(pro, _NOW) == []


def test_fx_single_row_cannot_compute_returns_empty() -> None:
    pro = _StubPro(fx_data={
        "USDCNH.FXCM": _fx_series("USDCNH.FXCM", [7.20]),
    })
    assert ts._emit_fx_cnh(pro, _NOW) == []


def test_fx_endpoint_exception_is_isolated() -> None:
    # fx_daily raising on every symbol is swallowed per-symbol → empty.
    boom = RuntimeError("抱歉，您没有访问该接口的权限")
    pro = _StubPro(fx_data={
        "USDCNH.FXCM": boom,
        "USDCNY.CFETS": boom,
        "USDCNY.FXCM": boom,
    })
    assert ts._emit_fx_cnh(pro, _NOW) == []


# ===========================================================================
# 2. 龙虎榜 → L9.capital.inst_buy_sell (+ L7.flow.institutional alias)
# ===========================================================================


def test_inst_payload_net_buy_from_top_inst_seats() -> None:
    # Institutional seats: buy 8e8, sell 1e8 → net +7e8 on 2e11 流通市值.
    list_records = [
        {"ts_code": "600036.SH", "trade_date": "20260512",
         "reason": "日涨幅偏离值7%", "net_amount": 1.5, "pct_change": 7.1,
         "float_values": 2.0e11, "l_buy": 9.0, "l_sell": 2.0},
    ]
    inst_records = [
        {"ts_code": "600036.SH", "side": "0", "buy": 3.0e8, "sell": 1.0e8},
        {"ts_code": "600036.SH", "side": "0", "buy": 5.0e8, "sell": 0.0},
    ]
    p = ts._compute_inst_buy_sell_payload(list_records, inst_records,
                                          "20260512")
    # Legacy keys preserved verbatim (alias test + other consumers rely on it).
    assert p["on_top_list"] is True
    assert p["trade_date"] == "20260512"
    assert p["entries"][0]["pct_change"] == 7.1
    # Institutional aggregation.
    assert p["inst_buy"] == 8.0e8
    assert p["inst_sell"] == 1.0e8
    assert p["inst_net_buy"] == 7.0e8
    assert p["inst_seat_count"] == 2
    assert p["net_buy_source"] == "top_inst"
    assert p["normalized_by"] == "float_values"
    # Scorable: positive net buy → positive leaf with non-zero magnitude.
    assert p["direction"] == "positive"
    assert 0.0 < p["score"] <= 1.0
    assert agg._to_scalar(p) == pytest.approx(p["score"], abs=1e-9)
    assert agg._direction_sign(p["direction"]) == 1.0


def test_inst_payload_net_sell_fallback_to_net_amount() -> None:
    # No top_inst seats → fall back to top_list net_amount (万元 → 元).
    # Negative net_amount → institutional net sell → negative leaf.
    list_records = [
        {"ts_code": "002594.SZ", "trade_date": "20260512",
         "reason": "连续三个交易日内跌幅偏离值达20%", "net_amount": -8000.0,
         "pct_change": -9.9, "float_values": 1.0e11},
    ]
    p = ts._compute_inst_buy_sell_payload(list_records, [], "20260512")
    assert p["net_buy_source"] == "top_list_net_amount"
    assert p["inst_seat_count"] == 0
    assert p["inst_net_buy"] == -8000.0 * 1e4    # 万元 → 元
    assert p["direction"] == "negative"
    assert p["score"] > 0.0
    assert agg._direction_sign(p["direction"]) == -1.0


def test_inst_payload_missing_float_values_uses_fixed_scale() -> None:
    list_records = [
        {"ts_code": "300750.SZ", "trade_date": "20260512",
         "reason": "x", "net_amount": 6000.0, "pct_change": 3.0},  # no float_values
    ]
    p = ts._compute_inst_buy_sell_payload(list_records, [], "20260512")
    assert p["float_values"] is None
    assert p["normalized_by"] == "fixed_5000w"
    assert p["direction"] == "positive"
    assert p["score"] > 0.0


def test_capital_events_emits_enriched_inst_rows() -> None:
    # Drive the trade-date-wide fetcher. margin_detail / block_trade endpoints
    # are absent on the stub → their loops swallow AttributeError and skip;
    # we only assert on the inst_buy_sell rows.
    td = ts._previous_n_days(0)
    pro = _StubPro(
        top_list_data={td: [
            {"ts_code": "600036.SH", "trade_date": td, "reason": "涨幅7%",
             "net_amount": 2.0, "pct_change": 7.0, "float_values": 1.5e11},
            {"ts_code": "600036.SH", "trade_date": td, "reason": "换手率20%",
             "net_amount": 1.0, "pct_change": 7.0, "float_values": 1.5e11},
        ]},
        top_inst_data={td: [
            {"ts_code": "600036.SH", "side": "0", "buy": 6.0e8, "sell": 1.0e8},
        ]},
    )
    rows = ts._fetch_a_share_capital_events(pro, {"600036.SH"}, _NOW)
    inst_rows = [r for r in rows if r[1] == "L9.capital.inst_buy_sell"]
    assert len(inst_rows) == 1
    ts_code, dp, val, status, conf, source, t = inst_rows[0]
    assert ts_code == "600036.SH"
    assert status == "Known"
    assert conf == 0.85
    assert source == "tushare:top_list+top_inst"
    p = json.loads(val)
    # Two reasons grouped into one row.
    assert len(p["entries"]) == 2
    assert p["inst_net_buy"] == 5.0e8           # 6e8 buy − 1e8 sell
    assert p["direction"] == "positive"
    assert p["score"] > 0.0


def test_capital_events_top_inst_permission_error_falls_back() -> None:
    # top_inst permission-locked → helper uses net_amount fallback, still
    # produces a signed row (not silently dropped).
    td = ts._previous_n_days(0)
    pro = _StubPro(
        top_list_data={td: [
            {"ts_code": "601318.SH", "trade_date": td, "reason": "机构净卖出",
             "net_amount": -5000.0, "pct_change": -5.0, "float_values": 2.0e11},
        ]},
        top_inst_data={td: RuntimeError("权限不足")},
    )
    rows = ts._fetch_a_share_capital_events(pro, {"601318.SH"}, _NOW)
    inst_rows = [r for r in rows if r[1] == "L9.capital.inst_buy_sell"]
    assert len(inst_rows) == 1
    p = json.loads(inst_rows[0][2])
    assert p["net_buy_source"] == "top_list_net_amount"
    assert p["direction"] == "negative"
    assert p["score"] > 0.0


def test_inst_buy_sell_alias_inherits_scorable_keys() -> None:
    # The X1 alias L9.capital.inst_buy_sell → L7.flow.institutional copies the
    # payload verbatim, so the new score/direction keys flow to the spec
    # multiplier dp_id too (fixing its previous zero-signal payload).
    list_records = [
        {"ts_code": "600036.SH", "trade_date": "20260512", "reason": "x",
         "net_amount": 3.0, "pct_change": 7.1, "float_values": 1.0e11},
    ]
    inst_records = [
        {"ts_code": "600036.SH", "side": "0", "buy": 4.0e8, "sell": 1.0e8},
    ]
    payload = ts._compute_inst_buy_sell_payload(list_records, inst_records,
                                                "20260512")
    legacy_row = (
        "600036.SH", "L9.capital.inst_buy_sell",
        json.dumps(payload, ensure_ascii=False),
        "Known", 0.85, "tushare:top_list+top_inst", _NOW,
    )
    rows = [legacy_row]
    ts._emit_spec_aliases(rows)

    aliases = [r for r in rows if r[1] == "L7.flow.institutional"]
    assert len(aliases) == 1
    p = json.loads(aliases[0][2])
    assert p["direction"] == "positive"
    assert p["score"] > 0.0
    assert agg._to_scalar(p) > 0.0
    assert agg._direction_sign(p["direction"]) == 1.0
