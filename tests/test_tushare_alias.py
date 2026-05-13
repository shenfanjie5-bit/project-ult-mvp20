"""Tests for the X1 spec-alignment dual-emit alias helper in
``mvp20.sources.tushare_source``.

We exercise ``_alias_emit`` + ``_emit_spec_aliases`` directly with hand-built
legacy 7-tuple rows. No Tushare HTTP is involved so the suite stays
hermetic. The point is to lock down:

  * Legacy rows survive untouched (existing consumers keep working).
  * Spec dp_ids appear with the right (ts_code, status, confidence,
    updated_at) tuple inherited from the legacy row.
  * The source string is tagged ``...|alias→<spec_dp_id>`` so the
    freshness panel can distinguish the alias path from the legacy emit.
  * Payload transforms reshape semantics where needed (increase→signed
    insider_sell with positive ``net_change_pct``, decrease→negative,
    aggregate signal→signed pass-through).
  * ``L9.capital.inst_buy_sell`` → ``L7.flow.institutional`` and
    ``L9.company.mgmt_litigation`` → ``L8.gov.management_change``
    pass payload verbatim (no transform).
"""

from __future__ import annotations

import json

from mvp20.sources import tushare_source


def _make_legacy_row(
    ts_code: str,
    dp_id: str,
    payload: dict,
    status: str = "Known",
    conf: float = 0.85,
    source: str = "tushare:stk_holdertrade",
    ts: int = 1700000000,
) -> tuple:
    return (
        ts_code, dp_id,
        json.dumps(payload, ensure_ascii=False),
        status, conf, source, ts,
    )


# ---------------------------------------------------------------------------
# 1. major_holder_increase → L8.gov.insider_sell (positive magnitude)
# ---------------------------------------------------------------------------


def test_alias_major_holder_increase_to_insider_sell_emits_positive_signed() -> None:
    rows = [
        _make_legacy_row("600519.SH", "L9.event.major_holder_increase", {
            "count": 2,
            "total_pct": 1.85,
            "latest_date": "20260420",
            "lookback_days": 90,
        }),
    ]
    tushare_source._emit_spec_aliases(rows)

    # legacy row preserved
    legacy = [r for r in rows if r[1] == "L9.event.major_holder_increase"]
    assert len(legacy) == 1
    assert legacy[0][0] == "600519.SH"

    aliases = [r for r in rows if r[1] == "L8.gov.insider_sell"]
    assert len(aliases) == 1
    ts_code, dp_id, val, status, conf, source, ts = aliases[0]
    assert ts_code == "600519.SH"
    assert status == "Known"
    assert conf == 0.85           # inherited
    assert ts == 1700000000       # inherited
    assert source.endswith("|alias→L8.gov.insider_sell")
    payload = json.loads(val)
    # increase = buy signal; net_change_pct should be positive 1.85
    assert payload["net_change_pct"] == 1.85
    assert payload["direction"] == "increase"
    assert payload["count"] == 2
    assert payload["_from_legacy"] == "L9.event.major_holder_increase"


# ---------------------------------------------------------------------------
# 2. major_holder_decrease → L8.gov.insider_sell (negative magnitude)
# ---------------------------------------------------------------------------


def test_alias_major_holder_decrease_to_insider_sell_emits_negative_signed() -> None:
    rows = [
        _make_legacy_row("000001.SZ", "L9.event.major_holder_decrease", {
            "count": 3,
            "total_pct": 2.40,     # Tushare reports magnitude (positive)
            "latest_date": "20260315",
            "lookback_days": 90,
        }),
    ]
    tushare_source._emit_spec_aliases(rows)

    aliases = [r for r in rows if r[1] == "L8.gov.insider_sell"]
    assert len(aliases) == 1
    payload = json.loads(aliases[0][2])
    # decrease = insider selling; net_change_pct should be negative -2.40
    assert payload["net_change_pct"] == -2.40
    assert payload["direction"] == "decrease"
    assert payload["count"] == 3
    assert payload["_from_legacy"] == "L9.event.major_holder_decrease"


# ---------------------------------------------------------------------------
# 3. holder_trade_signal → L8.gov.insider_sell (signed aggregate)
# ---------------------------------------------------------------------------


def test_alias_holder_trade_signal_to_insider_sell_preserves_sign() -> None:
    rows = [
        _make_legacy_row("300750.SZ", "L9.event.holder_trade_signal", {
            "count_90d": 5,
            "latest_ann_date": "20260501",
            "net_change_pct": -0.75,    # Tushare aggregate: signed already
            "increases": 1,
            "decreases": 4,
            "actions": [],
            "lookback_days": 90,
        }),
    ]
    tushare_source._emit_spec_aliases(rows)

    aliases = [r for r in rows if r[1] == "L8.gov.insider_sell"]
    # 3 legacy → insider_sell alias triggers (increase / decrease / signal)
    # but only the signal exists in this rows list — exactly 1 alias.
    assert len(aliases) == 1
    payload = json.loads(aliases[0][2])
    assert payload["net_change_pct"] == -0.75   # sign preserved
    assert payload["direction"] == "aggregate"
    assert payload["count_90d"] == 5
    assert payload["increases"] == 1
    assert payload["decreases"] == 4
    assert payload["_from_legacy"] == "L9.event.holder_trade_signal"


# ---------------------------------------------------------------------------
# 4. inst_buy_sell → L7.flow.institutional (payload verbatim, conf inherited)
# ---------------------------------------------------------------------------


def test_alias_inst_buy_sell_to_flow_institutional_verbatim() -> None:
    rows = [
        _make_legacy_row(
            "600036.SH", "L9.capital.inst_buy_sell",
            {
                "on_top_list": True,
                "entries": [{"reason": "日跌幅偏离值-7%", "net_amount": 1.5,
                             "pct_change": -7.1}],
                "trade_date": "20260512",
            },
            status="Known",
            conf=0.85,
            source="tushare:top_list",
            ts=1700000001,
        ),
    ]
    tushare_source._emit_spec_aliases(rows)

    aliases = [r for r in rows if r[1] == "L7.flow.institutional"]
    assert len(aliases) == 1
    ts_code, dp_id, val, status, conf, source, ts = aliases[0]
    assert ts_code == "600036.SH"
    assert status == "Known"
    assert conf == 0.85           # inherited
    assert ts == 1700000001       # inherited
    assert source.endswith("|alias→L7.flow.institutional")
    payload = json.loads(val)
    # Verbatim: same on_top_list, same entries, same trade_date
    assert payload["on_top_list"] is True
    assert payload["trade_date"] == "20260512"
    assert payload["entries"][0]["pct_change"] == -7.1


# ---------------------------------------------------------------------------
# 5. mgmt_litigation → L8.gov.management_change (payload verbatim)
# ---------------------------------------------------------------------------


def test_alias_mgmt_litigation_to_management_change_verbatim() -> None:
    rows = [
        _make_legacy_row(
            "002594.SZ", "L9.company.mgmt_litigation",
            {
                "events": [{"type": "高管变动", "ann_date": "20260420",
                            "person": "陈某", "title": "副总经理"}],
                "count_90d": 1,
                "lookback_days": 90,
            },
            status="Known",
            conf=0.8,
            source="tushare:stk_managers",
            ts=1700000002,
        ),
    ]
    tushare_source._emit_spec_aliases(rows)

    legacy = [r for r in rows if r[1] == "L9.company.mgmt_litigation"]
    assert len(legacy) == 1     # legacy survives

    aliases = [r for r in rows if r[1] == "L8.gov.management_change"]
    assert len(aliases) == 1
    ts_code, dp_id, val, status, conf, source, ts = aliases[0]
    assert ts_code == "002594.SZ"
    assert status == "Known"
    assert conf == 0.8
    assert ts == 1700000002
    assert source.endswith("|alias→L8.gov.management_change")
    payload = json.loads(val)
    assert payload["events"][0]["title"] == "副总经理"
    assert payload["count_90d"] == 1


# ---------------------------------------------------------------------------
# Bonus: verify legacy rows are NOT mutated and SUPPORTED_DP_IDS covers the
# 3 new spec aliases (compatibility contract for collector.py).
# ---------------------------------------------------------------------------


def test_legacy_row_is_not_mutated_by_alias_emit() -> None:
    legacy = _make_legacy_row("600519.SH", "L9.event.major_holder_increase",
                              {"total_pct": 1.0, "count": 1})
    rows = [legacy]
    tushare_source._emit_spec_aliases(rows)
    # The original tuple stays bit-identical
    assert rows[0] is legacy
    assert rows[0][1] == "L9.event.major_holder_increase"


def test_supported_dp_ids_covers_x1_spec_aliases() -> None:
    expected = {
        "L8.gov.insider_sell",
        "L7.flow.institutional",
        "L8.gov.management_change",
    }
    assert expected.issubset(tushare_source.SUPPORTED_DP_IDS), (
        f"Missing X1 spec aliases in SUPPORTED_DP_IDS: "
        f"{expected - tushare_source.SUPPORTED_DP_IDS}"
    )
