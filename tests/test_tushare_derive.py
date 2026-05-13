"""Tests for the X3b derived A-share fundamentals in
``mvp20.sources.tushare_source``.

All Tushare HTTP calls are stubbed via fake DataFrames so the suite stays
hermetic. We exercise the seven dp_ids added in X3b:

  * L4.cost.labor      — cashflow.c_paid_to_for_empl / revenue + YoY
  * L4.cost.raw_material — (oper_cost − labor) / revenue + cogs_yoy
  * L4.eff.turnover    — DIO / DSO / DPO from balancesheet + income
  * L4.eff.cycle       — CCC = DIO + DSO − DPO
  * L8.fin.cash_ar     — OCF/NI + AR yoy → WARN/ERROR alert
  * L8.fin.debt_pressure — interest_debt / EBITDA → WARN/ERROR
  * L8.op.inventory_glut — inventory yoy vs turnover yoy → WARN/ERROR
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from mvp20.sources import tushare_source


# ---------------------------------------------------------------------------
# Tiny DataFrame stub — quacks like pandas.DataFrame for the calls X3b makes.
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

    @property
    def columns(self):
        cols: set[str] = set()
        for r in self._rows:
            cols.update(r.keys())
        return cols


class _StubPro:
    """Per-endpoint dispatcher; supports DataFrame, Exception, or callable."""

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

    def fina_indicator(self, **kw):  return self._dispatch("fina_indicator", **kw)
    def balancesheet(self, **kw):    return self._dispatch("balancesheet", **kw)
    def cashflow(self, **kw):        return self._dispatch("cashflow", **kw)
    def income(self, **kw):          return self._dispatch("income", **kw)


@pytest.fixture(autouse=True)
def _clear_caches():
    """Wipe X3b per-stock caches between tests."""

    tushare_source._FINA_CACHE.clear()
    tushare_source._BALANCESHEET_CACHE.clear()
    tushare_source._CASHFLOW_CACHE.clear()
    tushare_source._INCOME_CACHE.clear()
    yield
    tushare_source._FINA_CACHE.clear()
    tushare_source._BALANCESHEET_CACHE.clear()
    tushare_source._CASHFLOW_CACHE.clear()
    tushare_source._INCOME_CACHE.clear()


# ---------------------------------------------------------------------------
# SUPPORTED_DP_IDS contract
# ---------------------------------------------------------------------------


def test_supported_dp_ids_includes_seven_x3b_derive() -> None:
    expected = {
        "L4.cost.labor", "L4.cost.raw_material",
        "L4.eff.turnover", "L4.eff.cycle",
        "L8.fin.cash_ar", "L8.fin.debt_pressure",
        "L8.op.inventory_glut",
    }
    assert expected.issubset(tushare_source.SUPPORTED_DP_IDS)


# ---------------------------------------------------------------------------
# Helpers — exercise the derive functions directly (no pro stub needed).
# ---------------------------------------------------------------------------


def _income_records(period: str, rev: float, cogs: float, ni: float | None = None):
    """Build a single income record dict."""

    return [{"end_date": period, "total_revenue": rev,
             "oper_cost": cogs, "n_income": ni}]


def _cashflow_records(period: str, ocf: float, labor: float):
    return [{"end_date": period, "n_cashflow_act": ocf,
             "c_paid_to_for_empl": labor, "update_flag": "1"}]


def _balancesheet_records(period: str, **fields):
    rec = {"end_date": period}
    rec.update(fields)
    return [rec]


def _fina_records(period: str, **fields):
    rec = {"end_date": period}
    rec.update(fields)
    return [rec]


# ---------------------------------------------------------------------------
# _derive_labor_cost: L4.cost.labor
# ---------------------------------------------------------------------------


def test_derive_labor_cost_known_when_full_data() -> None:
    inc = _income_records("20260331", rev=129_000_000_000.0, cogs=97_000_000_000.0)
    cf = _cashflow_records("20260331", ocf=33_000_000_000.0,
                           labor=9_700_000_000.0)
    payload, status = tushare_source._derive_labor_cost(inc, cf)
    assert status == "Known"
    # 9.7B / 129B = 7.52%
    assert abs(payload["labor_cost_pct"] - 7.5194) < 0.01
    assert payload["latest_period"] == "20260331"


def test_derive_labor_cost_yoy_change_computed() -> None:
    inc = [
        {"end_date": "20260331", "total_revenue": 100.0, "oper_cost": 70.0},
        {"end_date": "20250331", "total_revenue": 80.0, "oper_cost": 56.0},
    ]
    cf = [
        {"end_date": "20260331", "c_paid_to_for_empl": 8.0,
         "n_cashflow_act": 20.0, "update_flag": "1"},
        {"end_date": "20250331", "c_paid_to_for_empl": 5.0,
         "n_cashflow_act": 15.0, "update_flag": "1"},
    ]
    payload, status = tushare_source._derive_labor_cost(inc, cf)
    assert status == "Known"
    # current 8/100 = 8% vs prior 5/80 = 6.25%; yoy = +1.75 pct
    assert abs(payload["labor_cost_pct"] - 8.0) < 0.01
    assert abs(payload["labor_cost_yoy_pct"] - 1.75) < 0.01


def test_derive_labor_cost_inactive_when_data_missing() -> None:
    payload, status = tushare_source._derive_labor_cost([], [])
    assert status == "Inactive"
    payload, status = tushare_source._derive_labor_cost(
        _income_records("20260331", rev=100, cogs=70), [],
    )
    assert status == "Inactive"


# ---------------------------------------------------------------------------
# _derive_raw_material: L4.cost.raw_material
# ---------------------------------------------------------------------------


def test_derive_raw_material_known_with_yoy() -> None:
    inc = [
        {"end_date": "20260331", "total_revenue": 100.0, "oper_cost": 70.0},
        {"end_date": "20250331", "total_revenue": 80.0, "oper_cost": 50.0},
    ]
    cf = [
        {"end_date": "20260331", "c_paid_to_for_empl": 5.0,
         "n_cashflow_act": 20.0, "update_flag": "1"},
    ]
    payload, status = tushare_source._derive_raw_material(inc, cf, "LC0")
    assert status == "Known"
    # (70 - 5) / 100 = 65%
    assert abs(payload["raw_material_cost_pct"] - 65.0) < 0.01
    # cogs yoy = (70 - 50) / 50 = 40%
    assert abs(payload["cogs_yoy_pct"] - 40.0) < 0.01
    assert payload["primary_commodity"] == "LC0"
    assert payload["labor_adjusted"] is True


def test_derive_raw_material_inactive_when_no_income() -> None:
    payload, status = tushare_source._derive_raw_material([], [], None)
    assert status == "Inactive"


def test_derive_raw_material_handles_missing_labor() -> None:
    inc = _income_records("20260331", rev=100.0, cogs=70.0)
    payload, status = tushare_source._derive_raw_material(inc, [], None)
    assert status == "Known"
    # No labor → raw_material = full cogs = 70%
    assert abs(payload["raw_material_cost_pct"] - 70.0) < 0.01
    assert payload["labor_adjusted"] is False


# ---------------------------------------------------------------------------
# _derive_turnover: L4.eff.turnover
# ---------------------------------------------------------------------------


def test_derive_turnover_emits_dio_dso_dpo() -> None:
    # Q1 (90 days) example:
    # revenue=100, cogs=70, inv=35, ar=20, ap=14
    # DIO = 35/70 * 90 = 45 days
    # DSO = 20/100 * 90 = 18 days
    # DPO = 14/70 * 90 = 18 days
    inc = _income_records("20260331", rev=100.0, cogs=70.0)
    bs = _balancesheet_records("20260331", inventories=35.0,
                                accounts_receiv=20.0, accounts_pay=14.0)
    payload, status = tushare_source._derive_turnover(inc, bs)
    assert status == "Known"
    assert abs(payload["inventory_turnover_days"] - 45.0) < 0.01
    assert abs(payload["ar_turnover_days"] - 18.0) < 0.01
    assert abs(payload["ap_turnover_days"] - 18.0) < 0.01
    assert payload["period_days_basis"] == 90


def test_derive_turnover_inactive_when_no_balance() -> None:
    inc = _income_records("20260331", rev=100.0, cogs=70.0)
    payload, status = tushare_source._derive_turnover(inc, [])
    assert status == "Inactive"


# ---------------------------------------------------------------------------
# _derive_cycle: L4.eff.cycle (CCC = DIO + DSO - DPO)
# ---------------------------------------------------------------------------


def test_derive_cycle_math_correct() -> None:
    # Same numbers as turnover test: 45 + 18 - 18 = 45 days
    payload, status = tushare_source._derive_cycle({
        "inventory_turnover_days": 45.0,
        "ar_turnover_days": 18.0,
        "ap_turnover_days": 18.0,
        "latest_period": "20260331",
    }, "Known")
    assert status == "Known"
    assert abs(payload["ccc_days"] - 45.0) < 0.01
    assert payload["dio"] == 45.0
    assert payload["dso"] == 18.0
    assert payload["dpo"] == 18.0


def test_derive_cycle_inactive_when_turnover_inactive() -> None:
    payload, status = tushare_source._derive_cycle({}, "Inactive")
    assert status == "Inactive"


def test_derive_cycle_inactive_when_incomplete_components() -> None:
    payload, status = tushare_source._derive_cycle({
        "inventory_turnover_days": 45.0,
        "ar_turnover_days": None,  # missing AR
        "ap_turnover_days": 18.0,
        "latest_period": "20260331",
    }, "Known")
    assert status == "Inactive"


# ---------------------------------------------------------------------------
# _derive_cash_ar: L8.fin.cash_ar — alert_severity tests
# ---------------------------------------------------------------------------


def test_derive_cash_ar_warn_when_ocf_to_ni_below_threshold() -> None:
    # OCF/NI = 5/10 = 0.5 → ERROR (below 0.5 threshold)
    # Use 0.7 → WARN
    inc = [{"end_date": "20260331", "total_revenue": 100.0,
            "oper_cost": 70.0, "n_income": 10.0}]
    cf = [{"end_date": "20260331", "n_cashflow_act": 7.0,
           "c_paid_to_for_empl": 5.0, "update_flag": "1"}]
    bs = _balancesheet_records("20260331", accounts_receiv=20.0)
    payload, status = tushare_source._derive_cash_ar(inc, cf, bs)
    assert status == "Known"
    assert payload["alert_severity"] == "WARN"
    assert abs(payload["ocf_to_ni"] - 0.7) < 0.01


def test_derive_cash_ar_error_when_ocf_to_ni_very_low() -> None:
    inc = [{"end_date": "20260331", "total_revenue": 100.0,
            "oper_cost": 70.0, "n_income": 10.0}]
    cf = [{"end_date": "20260331", "n_cashflow_act": 3.0,  # ratio 0.3
           "c_paid_to_for_empl": 1.0, "update_flag": "1"}]
    bs = _balancesheet_records("20260331", accounts_receiv=20.0)
    payload, status = tushare_source._derive_cash_ar(inc, cf, bs)
    assert status == "Known"
    assert payload["alert_severity"] == "ERROR"


def test_derive_cash_ar_error_when_ar_yoy_explodes() -> None:
    inc = [{"end_date": "20260331", "total_revenue": 100.0,
            "oper_cost": 70.0, "n_income": 10.0}]
    cf = [{"end_date": "20260331", "n_cashflow_act": 9.0,
           "c_paid_to_for_empl": 1.0, "update_flag": "1"}]
    bs = [
        {"end_date": "20260331", "accounts_receiv": 80.0},
        {"end_date": "20250331", "accounts_receiv": 40.0},  # +100% YoY
    ]
    payload, status = tushare_source._derive_cash_ar(inc, cf, bs)
    assert status == "Known"
    assert payload["alert_severity"] == "ERROR"
    assert abs(payload["ar_yoy_pct"] - 100.0) < 0.01


def test_derive_cash_ar_inactive_when_no_alert() -> None:
    # OCF/NI = 1.0, AR yoy = 5% → no alert
    inc = [{"end_date": "20260331", "total_revenue": 100.0,
            "oper_cost": 70.0, "n_income": 10.0}]
    cf = [{"end_date": "20260331", "n_cashflow_act": 10.0,
           "c_paid_to_for_empl": 1.0, "update_flag": "1"}]
    bs = [
        {"end_date": "20260331", "accounts_receiv": 42.0},
        {"end_date": "20250331", "accounts_receiv": 40.0},  # +5% YoY
    ]
    payload, status = tushare_source._derive_cash_ar(inc, cf, bs)
    assert status == "Inactive"
    assert payload["alert_severity"] is None
    # Data is still present even when not alerting
    assert payload["ocf_to_ni"] == 1.0


def test_derive_cash_ar_inactive_when_no_data() -> None:
    payload, status = tushare_source._derive_cash_ar([], [], [])
    assert status == "Inactive"


# ---------------------------------------------------------------------------
# _derive_debt_pressure: L8.fin.debt_pressure
# ---------------------------------------------------------------------------


def test_derive_debt_pressure_warn_when_above_2_5() -> None:
    # interest_debt = 30, ebitda = 10 → ratio = 3.0 → WARN
    bs = _balancesheet_records("20260331", lt_borr=20.0, st_borr=5.0,
                                bond_payable=5.0)
    fina = _fina_records("20260331", ebitda=10.0, debt_to_assets=45.0)
    payload, status = tushare_source._derive_debt_pressure(bs, fina)
    assert status == "Known"
    assert payload["alert_severity"] == "WARN"
    assert abs(payload["interest_debt_to_ebitda"] - 3.0) < 0.01


def test_derive_debt_pressure_error_when_above_4() -> None:
    bs = _balancesheet_records("20260331", lt_borr=40.0, st_borr=10.0,
                                bond_payable=10.0)
    fina = _fina_records("20260331", ebitda=10.0, debt_to_assets=80.0)
    payload, status = tushare_source._derive_debt_pressure(bs, fina)
    assert status == "Known"
    assert payload["alert_severity"] == "ERROR"
    assert abs(payload["interest_debt_to_ebitda"] - 6.0) < 0.01


def test_derive_debt_pressure_inactive_when_low_ratio() -> None:
    bs = _balancesheet_records("20260331", lt_borr=5.0, st_borr=2.0,
                                bond_payable=1.0)
    fina = _fina_records("20260331", ebitda=10.0, debt_to_assets=30.0)
    payload, status = tushare_source._derive_debt_pressure(bs, fina)
    assert status == "Inactive"
    assert payload["alert_severity"] is None


def test_derive_debt_pressure_inactive_when_ebitda_missing() -> None:
    bs = _balancesheet_records("20260331", lt_borr=10.0, st_borr=5.0)
    fina = _fina_records("20260331", ebitda=None, debt_to_assets=45.0)
    payload, status = tushare_source._derive_debt_pressure(bs, fina)
    assert status == "Inactive"


def test_derive_debt_pressure_falls_back_to_prior_period_ebitda() -> None:
    """Tushare often returns NaN EBITDA on the latest quarterly until the
    full-year filing arrives. The fetcher should walk back through prior
    periods until it finds a non-null EBITDA so the ratio stays computable.
    """

    bs = _balancesheet_records("20260331", lt_borr=20.0, st_borr=5.0,
                                bond_payable=5.0)
    fina = [
        # Latest quarter has NaN EBITDA (Tushare schema quirk)
        {"end_date": "20260331", "ebitda": None, "debt_to_assets": 45.0},
        # Prior year-end carries the real value
        {"end_date": "20251231", "ebitda": 10.0, "debt_to_assets": 44.0},
    ]
    payload, status = tushare_source._derive_debt_pressure(bs, fina)
    assert status == "Known"
    assert payload["alert_severity"] == "WARN"
    # 30/10 = 3.0
    assert abs(payload["interest_debt_to_ebitda"] - 3.0) < 0.01
    assert payload["ebitda_period"] == "20251231"
    assert payload["latest_period"] == "20260331"


# ---------------------------------------------------------------------------
# _derive_inventory_glut: L8.op.inventory_glut
# ---------------------------------------------------------------------------


def test_derive_inventory_glut_error_when_inventory_up_turnover_down_hard() -> None:
    # inv yoy +20%, turn_days +12% (slower turnover, change = -12%)
    bs = [
        {"end_date": "20260331", "inventories": 120.0},
        {"end_date": "20250331", "inventories": 100.0},
    ]
    fina = [
        {"end_date": "20260331", "turn_days": 168.0},
        {"end_date": "20250331", "turn_days": 150.0},
    ]
    inc = _income_records("20260331", rev=100, cogs=70)
    payload, status = tushare_source._derive_inventory_glut(bs, fina, inc)
    assert status == "Known"
    assert payload["alert_severity"] == "ERROR"
    assert abs(payload["inventory_yoy_pct"] - 20.0) < 0.01
    assert abs(payload["turnover_yoy_pct_change"] - (-12.0)) < 0.01


def test_derive_inventory_glut_warn_when_thresholds_just_above() -> None:
    # inv yoy +10% (above 8%), turn_days +6% (change = -6%)
    bs = [
        {"end_date": "20260331", "inventories": 110.0},
        {"end_date": "20250331", "inventories": 100.0},
    ]
    fina = [
        {"end_date": "20260331", "turn_days": 159.0},
        {"end_date": "20250331", "turn_days": 150.0},
    ]
    inc = _income_records("20260331", rev=100, cogs=70)
    payload, status = tushare_source._derive_inventory_glut(bs, fina, inc)
    assert status == "Known"
    assert payload["alert_severity"] == "WARN"


def test_derive_inventory_glut_inactive_when_no_signal() -> None:
    # Inventory flat, turnover unchanged
    bs = [
        {"end_date": "20260331", "inventories": 100.0},
        {"end_date": "20250331", "inventories": 100.0},
    ]
    fina = [
        {"end_date": "20260331", "turn_days": 150.0},
        {"end_date": "20250331", "turn_days": 150.0},
    ]
    inc = _income_records("20260331", rev=100, cogs=70)
    payload, status = tushare_source._derive_inventory_glut(bs, fina, inc)
    assert status == "Inactive"
    assert payload["alert_severity"] is None


def test_derive_inventory_glut_inactive_when_no_balancesheet() -> None:
    payload, status = tushare_source._derive_inventory_glut([], [], [])
    assert status == "Inactive"


# ---------------------------------------------------------------------------
# _fetch_a_share_derived_metrics — integration: 7 dp_ids per stock.
# ---------------------------------------------------------------------------


def _make_full_pro(period: str = "20260331"):
    """Build a _StubPro that returns enough data to derive all 7 dp_ids
    in the Known state with WARN/ERROR alerts where appropriate.

    Numbers chosen so:
      * L4.cost.labor: labor_cost_pct = 10%
      * L4.eff.turnover: DIO=45d, DSO=18d, DPO=18d
      * L4.eff.cycle: CCC = 45
      * L8.fin.cash_ar: OCF/NI = 0.7 → WARN (because < 0.8)
      * L8.fin.debt_pressure: ratio = 3.0 → WARN
      * L8.op.inventory_glut: inv yoy +20%, turn -12% → ERROR
    """

    yoy = tushare_source._yoy_period(period)
    income = _StubDF([
        {"ts_code": "300750.SZ", "end_date": period,
         "total_revenue": 100.0, "oper_cost": 70.0, "n_income": 10.0},
        {"ts_code": "300750.SZ", "end_date": yoy,
         "total_revenue": 80.0, "oper_cost": 50.0, "n_income": 9.0},
    ])
    cashflow = _StubDF([
        {"ts_code": "300750.SZ", "end_date": period,
         "n_cashflow_act": 7.0, "c_paid_to_for_empl": 10.0,
         "update_flag": "1"},
        {"ts_code": "300750.SZ", "end_date": yoy,
         "n_cashflow_act": 6.0, "c_paid_to_for_empl": 7.5,
         "update_flag": "1"},
    ])
    balance = _StubDF([
        {"ts_code": "300750.SZ", "end_date": period,
         "inventories": 120.0, "accounts_receiv": 20.0, "accounts_pay": 14.0,
         "lt_borr": 20.0, "st_borr": 5.0, "bond_payable": 5.0,
         "total_assets": 200.0, "total_liab": 90.0},
        {"ts_code": "300750.SZ", "end_date": yoy,
         "inventories": 100.0, "accounts_receiv": 18.0, "accounts_pay": 13.0,
         "lt_borr": 19.0, "st_borr": 4.0, "bond_payable": 4.0,
         "total_assets": 180.0, "total_liab": 80.0},
    ])
    fina = _StubDF([
        {"ts_code": "300750.SZ", "end_date": period,
         "ebitda": 10.0, "debt_to_assets": 45.0,
         "turn_days": 168.0,  # +12% vs 150 → turnover_change = -12%
         "ar_turn": 6.0, "assets_turn": 0.5,
         "interestdebt": 30.0},
        {"ts_code": "300750.SZ", "end_date": yoy,
         "ebitda": 9.0, "debt_to_assets": 44.0,
         "turn_days": 150.0,
         "ar_turn": 5.5, "assets_turn": 0.48,
         "interestdebt": 27.0},
    ])
    return _StubPro(income=income, cashflow=cashflow,
                    balancesheet=balance, fina_indicator=fina)


def test_fetch_a_share_derived_metrics_emits_seven_dp_ids_per_stock() -> None:
    pro = _make_full_pro()
    rows = tushare_source._fetch_a_share_derived_metrics(
        pro, ["300750.SZ"], {"300750.SZ": "STORAGE_GRID"}, now=1700000000,
    )
    assert len(rows) == 7
    dp_ids = sorted(r[1] for r in rows)
    assert dp_ids == sorted([
        "L4.cost.labor", "L4.cost.raw_material",
        "L4.eff.turnover", "L4.eff.cycle",
        "L8.fin.cash_ar", "L8.fin.debt_pressure",
        "L8.op.inventory_glut",
    ])
    # All 7-tuples are well-formed
    for r in rows:
        assert len(r) == 7
        ts_code, dp_id, value_json, status, conf, source, ts = r
        assert ts_code == "300750.SZ"
        assert source.startswith("tushare:")
        json.loads(value_json)
        assert status in {"Known", "Inactive"}
        assert ts == 1700000000


def test_fetch_a_share_derived_metrics_alert_severity_triggers() -> None:
    pro = _make_full_pro()
    rows = tushare_source._fetch_a_share_derived_metrics(
        pro, ["300750.SZ"], {"300750.SZ": "STORAGE_GRID"}, now=1700000000,
    )
    by_dp = {r[1]: r for r in rows}
    # cash_ar: OCF=7, NI=10 → 0.7 → WARN
    cash_ar = json.loads(by_dp["L8.fin.cash_ar"][2])
    assert cash_ar["alert_severity"] == "WARN"
    assert by_dp["L8.fin.cash_ar"][3] == "Known"

    # debt_pressure: (20+5+5)/10 = 3.0 → WARN
    dp = json.loads(by_dp["L8.fin.debt_pressure"][2])
    assert dp["alert_severity"] == "WARN"
    assert by_dp["L8.fin.debt_pressure"][3] == "Known"

    # inventory_glut: inv yoy +20%, turn_change -12% → ERROR
    glut = json.loads(by_dp["L8.op.inventory_glut"][2])
    assert glut["alert_severity"] == "ERROR"
    assert by_dp["L8.op.inventory_glut"][3] == "Known"


def test_fetch_a_share_derived_metrics_ccc_math_correct() -> None:
    pro = _make_full_pro()
    rows = tushare_source._fetch_a_share_derived_metrics(
        pro, ["300750.SZ"], {"300750.SZ": "STORAGE_GRID"}, now=1700000000,
    )
    by_dp = {r[1]: r for r in rows}
    # rev=100, cogs=70, inv=120, ar=20, ap=14, Q1 90d basis:
    #   DIO = 120/70 * 90 = 154.286
    #   DSO = 20/100 * 90 = 18
    #   DPO = 14/70 * 90 = 18
    #   CCC = 154.286 + 18 - 18 = 154.286
    turnover = json.loads(by_dp["L4.eff.turnover"][2])
    cycle = json.loads(by_dp["L4.eff.cycle"][2])
    assert abs(turnover["inventory_turnover_days"] - 154.29) < 0.02
    assert abs(turnover["ar_turnover_days"] - 18.0) < 0.01
    assert abs(turnover["ap_turnover_days"] - 18.0) < 0.01
    # CCC math
    assert abs(cycle["ccc_days"]
               - (turnover["inventory_turnover_days"]
                  + turnover["ar_turnover_days"]
                  - turnover["ap_turnover_days"])) < 0.01


def test_fetch_a_share_derived_metrics_inactive_when_data_missing() -> None:
    # All four endpoints return empty DataFrames → all 7 dp_ids Inactive
    pro = _StubPro(
        income=_StubDF([]), cashflow=_StubDF([]),
        balancesheet=_StubDF([]), fina_indicator=_StubDF([]),
    )
    rows = tushare_source._fetch_a_share_derived_metrics(
        pro, ["300750.SZ"], {"300750.SZ": None}, now=1700000000,
    )
    assert len(rows) == 7
    for r in rows:
        assert r[3] == "Inactive"
        assert r[4] == 0.0  # confidence


def test_fetch_a_share_derived_metrics_skips_non_a_share() -> None:
    """NVDA.US / 09988.HK / etc must be silently skipped."""

    pro = _make_full_pro()
    rows = tushare_source._fetch_a_share_derived_metrics(
        pro, ["NVDA.US", "09988.HK"], {}, now=1700000000,
    )
    assert rows == []


def test_fetch_a_share_derived_metrics_isolates_endpoint_failures() -> None:
    """One endpoint failing (e.g. fina permission denied) only drops the
    dp_ids that depend on it; the others still emit Known/Inactive."""

    yoy = tushare_source._yoy_period("20260331")
    income = _StubDF([
        {"ts_code": "300750.SZ", "end_date": "20260331",
         "total_revenue": 100.0, "oper_cost": 70.0, "n_income": 10.0},
        {"ts_code": "300750.SZ", "end_date": yoy,
         "total_revenue": 80.0, "oper_cost": 50.0, "n_income": 9.0},
    ])
    cashflow = _StubDF([
        {"ts_code": "300750.SZ", "end_date": "20260331",
         "n_cashflow_act": 7.0, "c_paid_to_for_empl": 10.0,
         "update_flag": "1"},
    ])
    balance = _StubDF([
        {"ts_code": "300750.SZ", "end_date": "20260331",
         "inventories": 120.0, "accounts_receiv": 20.0, "accounts_pay": 14.0,
         "lt_borr": 20.0, "st_borr": 5.0, "bond_payable": 5.0},
    ])
    # fina_indicator raises — debt_pressure + inventory_glut downgrade
    pro = _StubPro(
        income=income, cashflow=cashflow, balancesheet=balance,
        fina_indicator=RuntimeError("permission denied"),
    )
    rows = tushare_source._fetch_a_share_derived_metrics(
        pro, ["300750.SZ"], {"300750.SZ": None}, now=1700000000,
    )
    assert len(rows) == 7
    by_dp = {r[1]: r for r in rows}
    # Labor / raw_material / turnover / cycle / cash_ar should still emit
    # something (Known where possible)
    assert by_dp["L4.cost.labor"][3] == "Known"
    assert by_dp["L4.cost.raw_material"][3] == "Known"
    assert by_dp["L4.eff.turnover"][3] == "Known"
    assert by_dp["L4.eff.cycle"][3] == "Known"
    # debt_pressure has no EBITDA available → Inactive
    assert by_dp["L8.fin.debt_pressure"][3] == "Inactive"


def test_fetch_a_share_derived_metrics_caches_within_ttl() -> None:
    """Second call within 5 min hits cache, not Tushare."""

    pro = _make_full_pro()
    tushare_source._fetch_a_share_derived_metrics(
        pro, ["300750.SZ"], {"300750.SZ": "STORAGE_GRID"}, now=1700000000,
    )
    calls_after_first = dict(pro.call_counts)
    tushare_source._fetch_a_share_derived_metrics(
        pro, ["300750.SZ"], {"300750.SZ": "STORAGE_GRID"}, now=1700000000 + 60,
    )
    # No additional calls
    assert pro.call_counts == calls_after_first


# ---------------------------------------------------------------------------
# Helper: _industry_primary_commodity reads the YAML mapping.
# ---------------------------------------------------------------------------


def test_industry_primary_commodity_storage_grid() -> None:
    # STORAGE_GRID first symbol is LC0 (碳酸锂)
    sym = tushare_source._industry_primary_commodity("STORAGE_GRID")
    assert sym == "LC0"


def test_industry_primary_commodity_unmapped_returns_none() -> None:
    # HK_CN_INTERNET maps to ~ (null) in the YAML
    sym = tushare_source._industry_primary_commodity("HK_CN_INTERNET")
    assert sym is None
    # Bogus industry name → None
    assert tushare_source._industry_primary_commodity("NOT_A_REAL_INDUSTRY") is None
    # Empty/None
    assert tushare_source._industry_primary_commodity(None) is None


# ---------------------------------------------------------------------------
# _yoy_period and _period_days helpers.
# ---------------------------------------------------------------------------


def test_yoy_period_subtracts_one_year() -> None:
    assert tushare_source._yoy_period("20260331") == "20250331"
    assert tushare_source._yoy_period("20251231") == "20241231"


def test_yoy_period_handles_invalid_input() -> None:
    assert tushare_source._yoy_period("") == ""
    assert tushare_source._yoy_period("bad") == ""


def test_period_days_quarterly_lookup() -> None:
    assert tushare_source._period_days("20260331") == 90
    assert tushare_source._period_days("20260630") == 180
    assert tushare_source._period_days("20260930") == 270
    assert tushare_source._period_days("20261231") == 360
