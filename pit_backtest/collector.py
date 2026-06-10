"""Isolated point-in-time collector.

Calls tushare ``pro`` directly with explicit as-of dates, applies the
``f_ann_date / ann_date <= asof`` visibility filter (the #1 leak the production
fetchers omit), qfq-adjusts prices, and writes payloads that are byte-compatible
with what the production emitters write — so the *reused* aggregator + scoring
engine reads them identically. The production (leaky) fetchers are NEVER called.

Every formula here is a faithful replica of ``mvp20/sources/tushare_source.py``
(documented in docs/audit/production_lookahead_findings.md). Frozen for the
backtest: industry/macro L0 sentinels and history-less sentiment dp_ids are not
emitted at all.

Writes to an isolated ``runtime/backtest/pit_<asof>.sqlite`` via the reused
``storage.upsert_realtime`` — never the live ``runtime/hot.sqlite``.
"""

from __future__ import annotations

import json
import logging
import math
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from mvp20 import storage
from mvp20.derive import (
    derive_crowdedness,
    derive_historical_quantile,
    derive_overvalued,
    derive_run_up,
)
from pit_backtest import prices as pit_prices

log = logging.getLogger("pit_backtest.collector")

# --- sleep between RPCs to respect tushare rate limits -----------------------
_RPC_SLEEP_S = 0.10


# ---------------------------------------------------------------------------
# helpers (faithful copies of tushare_source private helpers)
# ---------------------------------------------------------------------------

def _safe(d: Mapping, key: str):
    v = d.get(key)
    if v is None or (isinstance(v, float) and v != v):
        return None
    return v


def _safe_num(v) -> float | None:
    if v is None or v == "":
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if f != f:
        return None
    return f


def _yoy_period(end_date: str) -> str:
    if not end_date or len(end_date) < 8:
        return ""
    try:
        year = int(end_date[:4])
    except ValueError:
        return ""
    return f"{year - 1}{end_date[4:]}"


def _find_record(records: Sequence[Mapping], end_date: str) -> Mapping | None:
    for r in records:
        if r.get("end_date") == end_date:
            return r
    return None


def _period_days(period: str | None) -> int:
    if not period or len(period) < 8:
        return 360
    mmdd = period[4:8]
    if mmdd.startswith("03"):
        return 90
    if mmdd.startswith("06"):
        return 180
    if mmdd.startswith("09"):
        return 270
    return 360


def _avg(vals: Sequence[float]) -> float | None:
    clean = [float(v) for v in vals if v is not None]
    return sum(clean) / len(clean) if clean else None


def _moving_average(values: Sequence, window: int) -> float | None:
    clean = [float(v) for v in values if v is not None][:window]
    if len(clean) < max(2, window // 2):
        return None
    return sum(clean) / len(clean)


def _round(v, n=4):
    return round(v, n) if v is not None else None


def asof_epoch(asof: str) -> int:
    """Unix ts for the as-of session close (15:00 CST). Uniform stamp for all
    PIT rows so freshness is internally consistent and never references wall
    clock."""

    dt = datetime.strptime(asof, "%Y%m%d").replace(
        hour=15, minute=0, tzinfo=timezone(timedelta(hours=8))
    )
    return int(dt.timestamp())


def _cal_back(asof: str, days: int) -> str:
    return (datetime.strptime(asof, "%Y%m%d") - timedelta(days=days)).strftime("%Y%m%d")


# ---------------------------------------------------------------------------
# Visibility filtering — the PIT leak fix
# ---------------------------------------------------------------------------

def _visibility(rec: Mapping) -> str | None:
    """Date a filing became public: f_ann_date preferred, else ann_date."""

    for k in ("f_ann_date", "ann_date"):
        v = rec.get(k)
        if v:
            return str(v)
    return None


def _visible_records(df, asof: str) -> list[dict]:
    """DataFrame -> list of dicts with visibility-date <= asof (PIT filter).

    Rows with no visibility date are DROPPED (cannot prove they were knowable).
    """

    if df is None or len(df) == 0:
        return []
    recs = df.to_dict("records")
    out = []
    for r in recs:
        vis = _visibility(r)
        if vis is not None and vis <= asof:
            out.append(r)
    return out


def _dedup_by_period(records: list[dict], metric_key: str) -> tuple[list[dict], dict]:
    """Replicate the emitter dedup: one row per end_date, preferring non-null
    ``metric_key`` then update_flag=='1' then latest visibility. Returns
    (records_sorted_desc, by_period)."""

    by_period: dict[str, dict] = {}
    for r in records:
        ed = r.get("end_date")
        if not ed:
            continue
        cur = by_period.get(ed)
        if cur is None:
            by_period[ed] = r
            continue
        cur_has = _safe(cur, metric_key) is not None
        new_has = _safe(r, metric_key) is not None
        if new_has and not cur_has:
            by_period[ed] = r
        elif new_has == cur_has:
            # prefer update_flag=='1', then later visibility
            if str(r.get("update_flag")) == "1" and str(cur.get("update_flag")) != "1":
                by_period[ed] = r
            elif (_visibility(r) or "") > (_visibility(cur) or ""):
                by_period[ed] = r
    ordered = [by_period[ed] for ed in sorted(by_period, reverse=True)]
    return ordered, by_period


# ---------------------------------------------------------------------------
# Raw asof fetchers (direct pro calls + visibility filter)
# ---------------------------------------------------------------------------

_INCOME_FIELDS = ("ts_code,end_date,f_ann_date,ann_date,update_flag,total_revenue,"
                  "operate_profit,n_income,basic_eps,oper_cost,sell_exp,admin_exp,rd_exp")
_BS_FIELDS = ("ts_code,end_date,f_ann_date,ann_date,money_cap,total_liab,total_assets,"
              "lt_borr,st_borr,bond_payable,inventories,accounts_receiv,accounts_pay,"
              "goodwill,fix_assets")
_CF_FIELDS = ("ts_code,end_date,f_ann_date,ann_date,update_flag,n_cashflow_act,"
              "n_cashflow_inv_act,n_cash_flows_fnc_act,free_cashflow,"
              "c_pay_acq_const_fiolta,c_pay_dist_dpcp_int_exp,c_pay_acq_treasury_stock")
_FINA_FIELDS = ("ts_code,end_date,ann_date,roe,roa,netprofit_margin,grossprofit_margin,"
                "debt_to_assets,assets_turn,q_sales_yoy,dt_netprofit_yoy,q_ocf_to_sales,"
                "working_capital,bps,eps,cfps,or_yoy,tr_yoy,netprofit_yoy,"
                "turn_days,inv_turn,interestdebt,ebitda")

# fina_indicator -> dp_id (col, dp_id, unit) — verbatim _FINA_FIELD_MAP
_FINA_FIELD_MAP = (
    ("roe", "L5.fina.roe", "ratio_pct"),
    ("roa", "L5.fina.roa", "ratio_pct"),
    ("netprofit_margin", "L5.fina.net_margin", "ratio_pct"),
    ("grossprofit_margin", "L5.fina.gross_margin", "ratio_pct"),
    ("debt_to_assets", "L5.fina.debt_ratio", "ratio_pct"),
    ("assets_turn", "L5.fina.asset_turnover", "ratio"),
    ("q_sales_yoy", "L5.fina.revenue_yoy_q", "ratio_pct"),
    ("dt_netprofit_yoy", "L5.fina.profit_yoy_q", "ratio_pct"),
    ("q_ocf_to_sales", "L5.fina.ocf_quality", "ratio_pct"),
    ("working_capital", "L5.fina.working_capital", "CNY"),
    ("bps", "L5.fina.bps", "CNY_per_share"),
    ("eps", "L5.fina.eps", "CNY_per_share"),
    ("cfps", "L5.fina.cfps", "CNY_per_share"),
    ("or_yoy", "L5.fina.revenue_yoy", "ratio_pct"),
    ("tr_yoy", "L5.fina.total_revenue_yoy", "ratio_pct"),
    ("netprofit_yoy", "L5.fina.net_profit_yoy", "ratio_pct"),
)


def _rpc(fn, **kw):
    time.sleep(_RPC_SLEEP_S)
    try:
        return fn(**kw)
    except Exception as e:  # noqa: BLE001
        log.warning("rpc %s failed: %s", getattr(fn, "__name__", "?"), str(e)[:120])
        return None


def fetch_statements(pro, ts: str, asof: str) -> dict[str, list[dict]]:
    """All four financial statements, multi-period, visibility-filtered <= asof.

    Returns {"income":[...], "balancesheet":[...], "cashflow":[...],
    "fina":[...]} each a list of dicts sorted by end_date desc (latest first).
    """

    inc = _visible_records(_rpc(pro.income, ts_code=ts, limit=16, fields=_INCOME_FIELDS), asof)
    bs = _visible_records(_rpc(pro.balancesheet, ts_code=ts, limit=12, fields=_BS_FIELDS), asof)
    cf = _visible_records(_rpc(pro.cashflow, ts_code=ts, limit=12, fields=_CF_FIELDS), asof)
    fina = _visible_records(_rpc(pro.fina_indicator, ts_code=ts, fields=_FINA_FIELDS), asof)
    inc, _ = _dedup_by_period(inc, "total_revenue")
    cf, _ = _dedup_by_period(cf, "free_cashflow")
    bs, _ = _dedup_by_period(bs, "total_assets")
    fina, _ = _dedup_by_period(fina, "roe")
    return {"income": inc, "balancesheet": bs, "cashflow": cf, "fina": fina}


# ---------------------------------------------------------------------------
# Emitters — return (dp_id, payload, status, confidence, source)
# ---------------------------------------------------------------------------

EmitRow = tuple[str, dict, str, float, str]


def emit_fina_indicator(fina: list[dict]) -> list[EmitRow]:
    if not fina:
        return []
    latest = fina[0]
    period = str(latest.get("end_date"))
    rows: list[EmitRow] = []
    for col, dp_id, unit in _FINA_FIELD_MAP:
        v = _safe_num(latest.get(col))
        if v is None:
            continue
        rows.append((dp_id, {"value": v, "period": period, "currency": "CNY", "unit": unit},
                     "Known", 0.85, "tushare:fina_indicator"))
    return rows


def emit_income(income: list[dict]) -> list[EmitRow]:
    if not income:
        return []
    records = income
    rec = records[0]
    period = rec.get("end_date")
    rev = _safe(rec, "total_revenue")
    oper_cost = _safe(rec, "oper_cost")
    op_profit = _safe(rec, "operate_profit")
    net_profit = _safe(rec, "n_income")
    eps = _safe(rec, "basic_eps")
    sell_exp = _safe(rec, "sell_exp") or 0
    admin_exp = _safe(rec, "admin_exp") or 0
    rd_exp = _safe(rec, "rd_exp") or 0
    rows: list[EmitRow] = []
    if rev is not None:
        rows.append(("L5.is.revenue", {"scalar": float(rev), "unit": "元", "period": period},
                     "Known", 0.85, "tushare:income"))
        if oper_cost is not None:
            gross = rev - oper_cost
            rows.append(("L5.is.gross_profit", {"scalar": float(gross), "unit": "元", "period": period},
                         "Known", 0.8, "tushare:income.derived"))
            rows.append(("L5.is.gross_margin",
                         {"scalar": gross / rev if rev else None, "unit": "ratio", "period": period},
                         "Known", 0.8, "tushare:income.derived"))
    if op_profit is not None:
        rows.append(("L5.is.operating_profit", {"scalar": float(op_profit), "unit": "元", "period": period},
                     "Known", 0.85, "tushare:income"))
    if net_profit is not None:
        rows.append(("L5.is.net_profit", {"scalar": float(net_profit), "unit": "元", "period": period},
                     "Known", 0.85, "tushare:income"))
    if eps is not None:
        rows.append(("L5.is.eps", {"scalar": float(eps), "unit": "元/股", "period": period},
                     "Known", 0.85, "tushare:income"))
    if rev and (op_profit is not None or net_profit is not None):
        rows.append(("L5.is.margins",
                     {"operating": op_profit / rev if op_profit is not None else None,
                      "net": net_profit / rev if net_profit is not None else None,
                      "period": period}, "Known", 0.8, "tushare:income.derived"))
    if sell_exp or admin_exp or rd_exp:
        rows.append(("L5.is.sga_rd",
                     {"sga_total": float(sell_exp + admin_exp),
                      "sell_exp": float(sell_exp), "admin_exp": float(admin_exp),
                      "rd_exp": float(rd_exp),
                      "sga_rd_ratio_revenue": ((sell_exp + admin_exp + rd_exp) / rev) if rev else None,
                      "unit": "元", "period": period}, "Known", 0.85, "tushare:income"))
    # revenue_growth (yoy vs same-period prior year; qoq vs records[1])
    yoy_rec = _find_record(records, _yoy_period(str(period or "")))
    yoy_rev = _safe(yoy_rec, "total_revenue") if yoy_rec else None
    if rev is not None and yoy_rev and yoy_rev != 0:
        yoy_pct = (rev - yoy_rev) / yoy_rev * 100.0
        prev_rev = _safe(records[1], "total_revenue") if len(records) > 1 else None
        qoq_pct = ((rev - prev_rev) / prev_rev * 100.0) if prev_rev else None
        rows.append(("L5.is.revenue_growth",
                     {"yoy_pct": yoy_pct, "qoq_pct": qoq_pct, "current_period": period,
                      "yoy_compare_period": yoy_rec.get("end_date")},
                     "Known", 0.8, "tushare:income.derived"))
    return rows


def _compute_ttm_fcf(by_period: dict, periods_desc: list[str]) -> float | None:
    if not periods_desc:
        return None
    latest = periods_desc[0]
    latest_fcf = _safe(by_period[latest], "free_cashflow")
    if latest.endswith("1231"):
        return float(latest_fcf) if latest_fcf is not None else None
    if latest_fcf is None:
        return None
    latest_year = int(latest[:4])
    latest_mmdd = latest[4:]
    prior_fy = f"{latest_year - 1}1231"
    prior_q = f"{latest_year - 1}{latest_mmdd}"
    prior_fy_fcf = _safe(by_period.get(prior_fy) or {}, "free_cashflow")
    prior_q_fcf = _safe(by_period.get(prior_q) or {}, "free_cashflow")
    if prior_fy_fcf is None or prior_q_fcf is None:
        return float(latest_fcf)
    return float(latest_fcf) + float(prior_fy_fcf) - float(prior_q_fcf)


def emit_cashflow(cashflow: list[dict], total_mv_wanyuan: float | None) -> list[EmitRow]:
    if not cashflow:
        return []
    by_period = {r["end_date"]: r for r in cashflow if r.get("end_date")}
    periods_desc = sorted(by_period, reverse=True)
    period = periods_desc[0]
    rec = by_period[period]
    ocf = _safe(rec, "n_cashflow_act")
    fcf = _safe(rec, "free_cashflow")
    capex = _safe(rec, "c_pay_acq_const_fiolta")
    icf = _safe(rec, "n_cashflow_inv_act")
    fncf = _safe(rec, "n_cash_flows_fnc_act")
    div_paid = _safe(rec, "c_pay_dist_dpcp_int_exp")
    buyback = _safe(rec, "c_pay_acq_treasury_stock")
    rows: list[EmitRow] = []
    for dp_id, val in (("L5.cf.ocf", ocf), ("L5.cf.fcf", fcf), ("L5.cf.capex", capex)):
        if val is not None:
            rows.append((dp_id, {"scalar": float(val), "unit": "元", "period": period},
                         "Known", 0.85, "tushare:cashflow"))
    if icf is not None or fncf is not None:
        rows.append(("L5.cf.icf_fcf",
                     {"investing_cf": float(icf) if icf is not None else None,
                      "financing_cf": float(fncf) if fncf is not None else None,
                      "unit": "元", "period": period}, "Known", 0.85, "tushare:cashflow"))
    if div_paid is not None or buyback is not None:
        rows.append(("L5.cf.buyback_dividend",
                     {"dividend_paid": float(div_paid) if div_paid is not None else None,
                      "buyback_paid": float(buyback) if buyback is not None else None,
                      "unit": "元", "period": period}, "Known", 0.85, "tushare:cashflow"))
    # L6.mult.mcap_fcf
    fcf_ttm = _compute_ttm_fcf(by_period, periods_desc)
    if fcf_ttm is not None and fcf_ttm != 0 and total_mv_wanyuan is not None:
        mcap_yuan = float(total_mv_wanyuan) * 10_000.0
        rows.append(("L6.mult.mcap_fcf",
                     {"scalar": mcap_yuan / float(fcf_ttm), "unit": "ratio", "ttm": True,
                      "fcf_period_end": period, "fcf_ttm_cny": float(fcf_ttm),
                      "mcap_cny": mcap_yuan}, "Known", 0.7, "tushare:daily_basic+cashflow"))
    return rows


def emit_balancesheet(bs_records: list[dict]) -> list[EmitRow]:
    if not bs_records:
        return []
    rec = bs_records[0]
    period = rec.get("end_date")
    cash = _safe(rec, "money_cap")
    lt_borr = _safe(rec, "lt_borr") or 0
    st_borr = _safe(rec, "st_borr") or 0
    total_liab = _safe(rec, "total_liab")
    total_assets = _safe(rec, "total_assets")
    inventory = _safe(rec, "inventories")
    accounts_receiv = _safe(rec, "accounts_receiv")
    accounts_pay = _safe(rec, "accounts_pay")
    goodwill = _safe(rec, "goodwill")
    fix_assets = _safe(rec, "fix_assets")
    debt = lt_borr + st_borr
    rows: list[EmitRow] = []
    if cash is not None or debt:
        rows.append(("L5.bs.cash_debt",
                     {"cash": cash, "debt": debt, "net": (cash or 0) - debt, "period": period},
                     "Known", 0.85, "tushare:balancesheet"))
    if total_assets and total_liab is not None:
        rows.append(("L5.bs.leverage", {"leverage_ratio": total_liab / total_assets, "period": period},
                     "Known", 0.85, "tushare:balancesheet.derived"))
    if inventory is not None:
        rows.append(("L5.bs.inventory",
                     {"scalar": float(inventory),
                      "inventory_to_assets": (inventory / total_assets) if total_assets else None,
                      "unit": "元", "period": period}, "Known", 0.85, "tushare:balancesheet"))
    if accounts_receiv is not None or accounts_pay is not None:
        rows.append(("L5.bs.ar_ap",
                     {"accounts_receivable": float(accounts_receiv) if accounts_receiv is not None else None,
                      "accounts_payable": float(accounts_pay) if accounts_pay is not None else None,
                      "net_working_capital_change_proxy": ((accounts_receiv or 0) - (accounts_pay or 0)),
                      "unit": "元", "period": period}, "Known", 0.85, "tushare:balancesheet"))
    goodwill_eff = goodwill if goodwill is not None else (0.0 if total_assets else None)
    if goodwill_eff is not None or fix_assets is not None:
        rows.append(("L5.bs.goodwill_ppe",
                     {"goodwill": float(goodwill_eff) if goodwill_eff is not None else None,
                      "fix_assets_ppe": float(fix_assets) if fix_assets is not None else None,
                      "goodwill_to_assets": (goodwill_eff / total_assets) if (goodwill_eff is not None and total_assets) else None,
                      "unit": "元", "period": period,
                      "goodwill_imputed_zero": goodwill is None and total_assets is not None},
                     "Known", 0.85, "tushare:balancesheet"))
    return rows


def emit_derived_metrics(stmts: dict[str, list[dict]]) -> list[EmitRow]:
    """L4.eff.turnover/cycle + L8.fin.cash_ar/debt_pressure + L8.op.inventory_glut."""

    income = stmts["income"]
    bs = stmts["balancesheet"]
    cf = stmts["cashflow"]
    fina = stmts["fina"]
    rows: list[EmitRow] = []
    if not income or not bs:
        return rows

    # L4.eff.turnover
    inc0 = income[0]
    period = inc0.get("end_date")
    bsp = _find_record(bs, period or "") or bs[0]
    rev = _safe(inc0, "total_revenue")
    cogs = _safe(inc0, "oper_cost")
    inv = _safe(bsp, "inventories")
    ar = _safe(bsp, "accounts_receiv")
    ap = _safe(bsp, "accounts_pay")
    days = _period_days(period)
    dio = (inv / cogs) * days if inv is not None and cogs else None
    dso = (ar / rev) * days if ar is not None and rev else None
    dpo = (ap / cogs) * days if ap is not None and cogs else None
    turnover_known = (rev and cogs and days) and any(x is not None for x in (dio, dso, dpo))
    if turnover_known:
        rows.append(("L4.eff.turnover",
                     {"inventory_turnover_days": _round(dio, 2), "ar_turnover_days": _round(dso, 2),
                      "ap_turnover_days": _round(dpo, 2), "latest_period": period,
                      "period_days_basis": days}, "Known", 0.7, "tushare:balancesheet+income.derived"))
        if dio is not None and dso is not None and dpo is not None:
            ccc = dio + dso - dpo
            rows.append(("L4.eff.cycle",
                         {"ccc_days": _round(ccc, 2), "dio": _round(dio, 2), "dso": _round(dso, 2),
                          "dpo": _round(dpo, 2), "latest_period": period},
                         "Known", 0.7, "tushare:balancesheet+income.derived"))

    # L8.fin.cash_ar
    cfp = _find_record(cf, period or "") or (cf[0] if cf else None)
    ni = _safe(inc0, "n_income")
    ocf = _safe(cfp, "n_cashflow_act") if cfp else None
    ocf_to_ni = float(ocf) / float(ni) if (ni and ni != 0 and ocf is not None) else None
    cur_ar = _safe(bsp, "accounts_receiv")
    prior_bs = _find_record(bs, _yoy_period(period or ""))
    prior_ar = _safe(prior_bs, "accounts_receiv") if prior_bs else None
    ar_yoy_pct = ((cur_ar - prior_ar) / prior_ar * 100.0) if (cur_ar is not None and prior_ar and prior_ar != 0) else None
    if ocf_to_ni is not None or ar_yoy_pct is not None:
        warn = (ocf_to_ni is not None and ocf_to_ni < 0.8) or (ar_yoy_pct is not None and ar_yoy_pct > 20.0)
        err = (ocf_to_ni is not None and ocf_to_ni < 0.5) or (ar_yoy_pct is not None and ar_yoy_pct > 50.0)
        sev = "ERROR" if err else ("WARN" if warn else None)
        rows.append(("L8.fin.cash_ar",
                     {"ocf_to_ni": _round(ocf_to_ni), "ar_yoy_pct": _round(ar_yoy_pct),
                      "alert_severity": sev, "latest_period": period},
                     "Known" if sev else "Inactive", 0.75 if sev else 0.0,
                     "tushare:cashflow+income+balancesheet.derived"))

    # L8.fin.debt_pressure
    if bs and fina:
        bs0 = bs[0]
        bperiod = bs0.get("end_date")
        finap = _find_record(fina, bperiod or "") or fina[0]
        lt = _safe(bs0, "lt_borr") or 0
        st = _safe(bs0, "st_borr") or 0
        bond = _safe(bs0, "bond_payable") or 0
        interest_debt = float(lt) + float(st) + float(bond)
        ebitda = _safe(finap, "ebitda")
        debt_ratio = _safe(finap, "debt_to_assets")
        ebitda_period = bperiod
        if (not ebitda or ebitda == 0) and len(fina) > 1:
            for prior in fina[1:]:
                cand = _safe(prior, "ebitda")
                if cand and cand != 0:
                    ebitda = cand
                    ebitda_period = prior.get("end_date")
                    break
        if ebitda and ebitda != 0:
            ratio = interest_debt / float(ebitda)
            sev = "ERROR" if ratio > 4.0 else ("WARN" if ratio > 2.5 else None)
            rows.append(("L8.fin.debt_pressure",
                         {"interest_debt_to_ebitda": _round(ratio), "debt_to_assets": float(debt_ratio) if debt_ratio is not None else None,
                          "alert_severity": sev, "interest_debt_cny": interest_debt,
                          "ebitda_cny": float(ebitda), "ebitda_period": ebitda_period, "latest_period": bperiod},
                         "Known" if sev else "Inactive", 0.75 if sev else 0.0,
                         "tushare:balancesheet+fina_indicator.derived"))

    # L8.op.inventory_glut
    if bs and fina:
        bs0 = bs[0]
        bperiod = bs0.get("end_date")
        cur_inv = _safe(bs0, "inventories")
        prior_bs2 = _find_record(bs, _yoy_period(bperiod or ""))
        prior_inv = _safe(prior_bs2, "inventories") if prior_bs2 else None
        inv_yoy = ((cur_inv - prior_inv) / prior_inv * 100.0) if (cur_inv is not None and prior_inv and prior_inv != 0) else None
        finap = _find_record(fina, bperiod or "") or fina[0]
        prior_fina = _find_record(fina, _yoy_period(bperiod or ""))
        cur_days = _safe(finap, "turn_days")
        prior_days = _safe(prior_fina, "turn_days") if prior_fina else None
        turn_chg = (-((cur_days - prior_days) / prior_days * 100.0)) if (cur_days is not None and prior_days and prior_days != 0) else None
        if inv_yoy is not None or turn_chg is not None:
            err = (inv_yoy is not None and inv_yoy > 15.0) and (turn_chg is not None and turn_chg < -10.0)
            warn = (inv_yoy is not None and inv_yoy > 8.0) and (turn_chg is not None and turn_chg < -5.0)
            sev = "ERROR" if err else ("WARN" if warn else None)
            rows.append(("L8.op.inventory_glut",
                         {"inventory_yoy_pct": _round(inv_yoy), "turnover_yoy_pct_change": _round(turn_chg),
                          "alert_severity": sev, "latest_period": bperiod},
                         "Known" if sev else "Inactive", 0.75 if sev else 0.0,
                         "tushare:balancesheet+fina_indicator.derived"))
    return rows


def emit_daily_basic_snapshot(db_row: Mapping, asof: str) -> list[EmitRow]:
    """L6.mult.pe/ps/pb + L7.trade.volume_turnover from the asof daily_basic row."""

    if not db_row:
        return []
    rows: list[EmitRow] = []
    pe = _safe_num(db_row.get("pe_ttm"))
    pb = _safe_num(db_row.get("pb"))
    ps = _safe_num(db_row.get("ps_ttm"))
    total_mv = _safe_num(db_row.get("total_mv"))
    total_share = _safe_num(db_row.get("total_share"))
    turnover = _safe_num(db_row.get("turnover_rate"))
    vol_ratio = _safe_num(db_row.get("volume_ratio"))
    for dp_id, val in (("L6.mult.pe", pe), ("L6.mult.pb", pb), ("L6.mult.ps", ps)):
        if val is None:
            continue
        payload = {"scalar": float(val), "unit": "ratio", "ttm": True, "trade_date": asof}
        if dp_id == "L6.mult.pe":
            if total_mv is not None:
                payload["total_mv_cny"] = float(total_mv) * 10000.0
            if total_share is not None:
                payload["total_share"] = float(total_share) * 10000.0
        rows.append((dp_id, payload, "Known", 0.7, "tushare:daily_basic"))
    if turnover is not None or vol_ratio is not None:
        rows.append(("L7.trade.volume_turnover",
                     {"turnover_rate_pct": turnover, "volume_ratio": vol_ratio, "trade_date": asof},
                     "Known", 0.7, "tushare:daily_basic"))
    return rows


def emit_moneyflow(pro, ts: str, asof: str) -> tuple[list[EmitRow], float | None]:
    """L7.flow.active_inflow (asof snapshot) + L8.cap.outflow_cut (5d).

    Returns (rows, main_net_asof_wanyuan) — the latter is the crowdedness proxy.
    """

    df = _rpc(pro.moneyflow, ts_code=ts, start_date=_cal_back(asof, 16), end_date=asof,
              fields="ts_code,trade_date,net_mf_amount,buy_lg_amount,sell_lg_amount,buy_elg_amount,sell_elg_amount")
    if df is None or len(df) == 0:
        return [], None
    recs = [r for r in df.to_dict("records") if str(r.get("trade_date", "")) <= asof]
    recs.sort(key=lambda r: str(r.get("trade_date", "")), reverse=True)
    if not recs:
        return [], None
    rows: list[EmitRow] = []
    top = recs[0]
    netbuy = _safe(top, "net_mf_amount")
    buy_lg = _safe(top, "buy_lg_amount") or 0
    sell_lg = _safe(top, "sell_lg_amount") or 0
    buy_elg = _safe(top, "buy_elg_amount") or 0
    sell_elg = _safe(top, "sell_elg_amount") or 0
    big_net = (buy_lg + buy_elg) - (sell_lg + sell_elg)
    rows.append(("L7.flow.active_inflow",
                 {"main_net": float(netbuy) if netbuy is not None else None,
                  "big_orders_net": float(big_net), "unit": "万元",
                  "trade_date": top.get("trade_date")}, "Known", 0.75, "tushare:moneyflow"))
    # outflow_cut (5d sum, 万元 -> 元)
    window = recs[:5]
    net_clean = [_safe(r, "net_mf_amount") for r in window]
    net_clean = [x for x in net_clean if x is not None]
    if net_clean:
        main_net_5d = sum(net_clean) * 1e4
        signal = main_net_5d <= -1e8
        rows.append(("L8.cap.outflow_cut",
                     {"signal": signal, "main_net_5d": main_net_5d, "stage_pct_change_5d": None,
                      "last_price": None, "alert_severity": "WARN" if signal else None,
                      "as_of": f"{asof[:4]}-{asof[4:6]}-{asof[6:]}T15:00:00+08:00"},
                     "Known" if signal else "Inactive", 0.65, "tushare:moneyflow.5d"))
    return rows, (float(netbuy) if netbuy is not None else None)


def emit_price_technicals(pro, ts: str, asof: str) -> list[EmitRow]:
    """Tier-0 + valuation-history dp_ids from qfq price + daily_basic history.

    L6.priced.run_up, L6.priced.crowdedness, L10.val.historical_quantile,
    L8.val.overvalued (via reused pure derive funcs), plus
    L6.state.expansion_compression, L6.state.historical_percentile,
    L8.cap.crowdedness, L8.cap.liquidity_short.
    """

    rows: list[EmitRow] = []
    # --- qfq close history (run_up) ---
    hist = pit_prices.hfq_close_history(pro, ts, _cal_back(asof, 100), asof)
    closes_desc = [r["hfq_close"] for r in reversed(hist) if r["hfq_close"] is not None]
    ru = derive_run_up(closes_desc)
    if ru is not None:
        rows.append(("L6.priced.run_up", ru, "Known", 0.6, "derived:price_history"))

    # --- daily_basic history (pe/pb/turnover) ---
    dbh = pit_prices.daily_basic_history(
        pro, ts, _cal_back(asof, 400), asof,
        fields="ts_code,trade_date,pe_ttm,pb,ps_ttm,turnover_rate,total_mv",
    )
    # newest-first series
    dbh_desc = list(reversed(dbh))
    pe_series = [_safe_num(r.get("pe_ttm")) for r in dbh_desc]
    pe_series = [v for v in pe_series if v is not None and v > 0]
    pb_series = [_safe_num(r.get("pb")) for r in dbh_desc]
    pb_series = [v for v in pb_series if v is not None and v > 0]
    turnover_desc = [_safe_num(r.get("turnover_rate")) for r in dbh_desc]
    cur_turn = turnover_desc[0] if turnover_desc else None

    # L6.priced.crowdedness (pure func; ~90 trading days window)
    turn_hist_90 = [v for v in turnover_desc[:98] if v is not None]
    cr = derive_crowdedness(cur_turn, turn_hist_90)
    if cr is not None:
        rows.append(("L6.priced.crowdedness", cr, "Known", 0.7, "derived:turnover_history"))

    # L10.val.historical_quantile + L8.val.overvalued (pure funcs)
    cur_pe = pe_series[0] if pe_series else None
    cur_pb = pb_series[0] if pb_series else None
    hq = derive_historical_quantile(cur_pe, pe_series[:250], cur_pb, pb_series[:250])
    if hq is not None:
        rows.append(("L10.val.historical_quantile", hq, "Known", 0.6, "derived:pe_pb_history"))
        ov = derive_overvalued(hq)
        if ov is not None:
            rows.append(("L8.val.overvalued", ov, "Known", 0.6, "derived:from_quantile"))

    # L6.state.expansion_compression (60/250 PE MA)
    if len(pe_series) >= 60:
        pe_60 = pe_series[:60]
        pe_250 = pe_series[: min(250, len(pe_series))]
        ma60 = _avg(pe_60)
        ma250 = _avg(pe_250)
        if ma250 and ma250 != 0:
            ratio = cur_pe / ma250
            regime = "compressed" if ratio < 0.95 else ("expanded" if ratio > 1.05 else "neutral")
            rows.append(("L6.state.expansion_compression",
                         {"pe_current": _round(cur_pe), "pe_60d_ma": _round(ma60), "pe_250d_ma": _round(ma250),
                          "ratio_vs_250d": _round(ratio), "slope": _round((cur_pe - ma250) / ma250),
                          "regime": regime, "n_days_60d": len(pe_60), "n_days_250d": len(pe_250)},
                         "Known", 0.7, "tushare:daily_basic.history_long"))

    # L6.state.historical_percentile (~280cal window)
    pe_280 = [v for r, v in zip(dbh_desc, [_safe_num(x.get("pe_ttm")) for x in dbh_desc])
              if str(r.get("trade_date", "")) >= _cal_back(asof, 280) and v is not None and v > 0]
    pb_280 = [v for r, v in zip(dbh_desc, [_safe_num(x.get("pb")) for x in dbh_desc])
              if str(r.get("trade_date", "")) >= _cal_back(asof, 280) and v is not None and v > 0]
    hp: dict[str, Any] = {"history_window_days": max(len(pe_280), len(pb_280))}
    if cur_pe is not None and len(pe_280) > 1:
        hp["pe_percentile"] = sum(1 for v in pe_280 if v < cur_pe) / len(pe_280)
        hp["pe_current"] = cur_pe
    if cur_pb is not None and len(pb_280) > 1:
        hp["pb_percentile"] = sum(1 for v in pb_280 if v < cur_pb) / len(pb_280)
        hp["pb_current"] = cur_pb
    if "pe_percentile" in hp or "pb_percentile" in hp:
        rows.append(("L6.state.historical_percentile", hp, "Known", 0.7, "tushare:daily_basic.history"))

    return rows


def emit_capital_risk(pro, ts: str, asof: str, main_net_asof: float | None) -> list[EmitRow]:
    """L8.cap.crowdedness, L8.cap.short_increase, L8.cap.liquidity_short."""

    rows: list[EmitRow] = []
    # crowdedness (turnover 30d MA) — daily_basic 150cal
    dbh = pit_prices.daily_basic_history(pro, ts, _cal_back(asof, 150), asof,
                                         fields="ts_code,trade_date,turnover_rate,pe_ttm")
    turn_desc = [_safe_num(r.get("turnover_rate")) for r in reversed(dbh)]
    turn30 = _moving_average(turn_desc, 30)
    if turn30 is not None:
        high_turn = turn30 > 8.0
        high_inflow = main_net_asof is not None and main_net_asof > 0
        if high_turn and high_inflow:
            sev = "ERROR" if turn30 > 15.0 else "WARN"
        elif high_turn:
            sev = "WARN"
        else:
            sev = None
        latest_date = str(reversed_first(dbh))
        rows.append(("L8.cap.crowdedness",
                     {"turnover_30d_avg": _round(turn30), "industry_pct_rank": 0.95 if high_turn else 0.50,
                      "main_net_5d": main_net_asof, "alert_severity": sev, "latest_date": latest_date},
                     "Known" if sev else "Inactive", 0.7 if sev else 0.0, "tushare:daily_basic.history"))

    # short_increase (margin rqye 30d vs 90d) — margin_detail 150cal
    mdf = _rpc(pro.margin_detail, ts_code=ts, start_date=_cal_back(asof, 150), end_date=asof,
               fields="ts_code,trade_date,rzye,rqye,rzmre,rqmcl")
    if mdf is not None and len(mdf):
        mrecs = [r for r in mdf.to_dict("records") if str(r.get("trade_date", "")) <= asof]
        mrecs.sort(key=lambda r: str(r.get("trade_date", "")), reverse=True)
        rqye = [_safe_num(r.get("rqye")) for r in mrecs]
        ma30 = _moving_average(rqye, 30)
        ma90 = _moving_average(rqye, 90)
        if ma30 is not None and ma90 is not None and ma90 > 0:
            delta = (ma30 - ma90) / ma90 * 100.0
            sev = "ERROR" if delta >= 40.0 else ("WARN" if delta >= 20.0 else None)
            rows.append(("L8.cap.short_increase",
                         {"rqye_30d": _round(ma30), "rqye_90d": _round(ma90), "delta_pct": _round(delta),
                          "alert_severity": sev, "latest_date": mrecs[0].get("trade_date") if mrecs else None},
                         "Known" if sev else "Inactive", 0.75 if sev else 0.0, "tushare:margin_detail.history"))

    # liquidity_short (daily amount 30d + dive days) — daily 75cal
    ddf = _rpc(pro.daily, ts_code=ts, start_date=_cal_back(asof, 75), end_date=asof,
               fields="ts_code,trade_date,close,pct_chg,amount,vol")
    if ddf is not None and len(ddf):
        drecs = [r for r in ddf.to_dict("records") if str(r.get("trade_date", "")) <= asof]
        drecs.sort(key=lambda r: str(r.get("trade_date", "")), reverse=True)
        amount30 = _moving_average([_safe_num(r.get("amount")) for r in drecs], 30)
        vol30 = _moving_average([_safe_num(r.get("vol")) for r in drecs], 30) or 0.0
        if amount30 is not None:
            dive = 0
            for r in drecs[:30]:
                pct = _safe_num(r.get("pct_chg"))
                v = _safe_num(r.get("vol"))
                if pct is not None and v is not None and pct <= -5.0 and v >= vol30 * 1.5:
                    dive += 1
            thin = amount30 < 100_000
            if thin and dive >= 2:
                sev = "ERROR"
            elif dive >= 1:
                sev = "WARN"
            else:
                sev = None
            rows.append(("L8.cap.liquidity_short",
                         {"amount_30d_avg": _round(amount30, 2), "industry_pct_rank": 0.05 if thin else 0.50,
                          "dive_day_count": dive, "alert_severity": sev,
                          "latest_date": drecs[0].get("trade_date") if drecs else None},
                         "Known" if sev else "Inactive", 0.7 if sev else 0.0, "tushare:daily.history"))
    return rows


def reversed_first(seq):
    return seq[-1].get("trade_date") if seq else None


# --- rating maps (verbatim) --------------------------------------------------
_RATING_MAP = {
    "买入": 5, "强烈推荐": 5, "强推": 5,
    "推荐": 4, "增持": 4, "审慎推荐": 4, "审慎增持": 4,
    "中性": 3, "持有": 3, "审慎": 3,
    "减持": 2, "卖出": 1, "回避": 1, "未评级": None,
}


def _classify_rating(rating: str):
    score = _RATING_MAP.get((rating or "").strip())
    if score is None:
        return ("hold", None)
    if score >= 5:
        return ("strong_buy", 5)
    if score == 4:
        return ("buy", 4)
    if score == 3:
        return ("hold", 3)
    if score == 2:
        return ("sell", 2)
    return ("strong_sell", 1)


def emit_report_rc(pro, ts: str, asof: str) -> list[EmitRow]:
    """L7.mood.analyst_rating, L6.priced.analyst_revision, L5.fcst.eps_cf."""

    df = _rpc(pro.report_rc, ts_code=ts, start_date=_cal_back(asof, 90), end_date=asof)
    if df is None or len(df) == 0:
        return []
    recs = [r for r in df.to_dict("records") if str(r.get("report_date", "")) <= asof]
    if not recs:
        return []
    rows: list[EmitRow] = []

    # analyst_rating
    seen = set()
    counts = {"strong_buy": 0, "buy": 0, "hold": 0, "sell": 0, "strong_sell": 0}
    scores: list[int] = []
    for r in recs:
        key = (r.get("report_date"), r.get("org_name"), r.get("author_name"))
        if key in seen:
            continue
        seen.add(key)
        bucket, score = _classify_rating(r.get("rating"))
        counts[bucket] += 1
        if score is not None:
            scores.append(score)
    n_reports = sum(counts.values())
    if scores:
        rows.append(("L7.mood.analyst_rating",
                     {**counts, "avg_rating_score": _round(sum(scores) / len(scores)),
                      "n_reports": n_reports, "period_days": 90}, "Known", 0.75, "tushare:report_rc"))

    # analyst_revision (per-broker chronological)
    by_org: dict[str, list[dict]] = {}
    for r in recs:
        by_org.setdefault(str(r.get("org_name") or ""), []).append(r)
    up = down = maintains = inits = 0
    for org, reps in by_org.items():
        reps_sorted = sorted(reps, key=lambda x: str(x.get("report_date", "")))
        last = None
        for rep in reps_sorted:
            _, score = _classify_rating(rep.get("rating"))
            if score is None:
                continue
            if last is None:
                inits += 1
            elif score > last:
                up += 1
            elif score < last:
                down += 1
            else:
                maintains += 1
            last = score
    denom = up + down + maintains
    if (up + down + maintains + inits) > 0:
        rows.append(("L6.priced.analyst_revision",
                     {"upgrades": up, "downgrades": down, "maintains": maintains, "initiations": inits,
                      "net_revision_score": _round((up - down) / denom if denom > 0 else 0.0),
                      "period_days": 90, "n_reports": len(recs)}, "Known", 0.75, "tushare:report_rc"))

    # eps_cf (nearest forward forecast year)
    cur_year = int(asof[:4])
    by_year_eps: dict[int, list[float]] = {}
    eps_keys: dict[int, set] = {}
    for r in recs:
        q = str(r.get("quarter") or "")
        if len(q) < 4:
            continue
        try:
            yr = int(q[:4])
        except ValueError:
            continue
        eps = _safe_num(r.get("eps"))
        if yr >= cur_year and eps is not None:
            by_year_eps.setdefault(yr, []).append(eps)
            eps_keys.setdefault(yr, set()).add(
                (r.get("report_date"), r.get("org_name"), r.get("author_name"), r.get("report_title")))
    fwd_years = sorted(by_year_eps)
    if fwd_years:
        ty = fwd_years[0]
        eps_vals = by_year_eps[ty]
        rows.append(("L5.fcst.eps_cf",
                     {"eps_avg": _avg(eps_vals), "eps_low": min(eps_vals), "eps_high": max(eps_vals),
                      "cashflow_estimate": None, "cashflow_available": False,
                      "num_analysts": len(eps_keys[ty]), "period": f"{ty}Q4", "unit": "CNY/share"},
                     "Known", 0.8, "tushare:report_rc"))
    return rows


def _midpoint(rec: Mapping) -> float | None:
    mn = _safe_num(rec.get("p_change_min"))
    mx = _safe_num(rec.get("p_change_max"))
    if mn is not None and mx is not None:
        return (mn + mx) / 2.0
    return mn if mn is not None else mx


def emit_forecast(pro, ts: str, asof: str) -> list[EmitRow]:
    """L9.company.earnings_guidance + L5.fcst.guidance_change (ann_date<=asof)."""

    df = _rpc(pro.forecast, ts_code=ts)
    rows: list[EmitRow] = []
    recs_all = _visible_records(df, asof)  # ann_date<=asof
    if not recs_all:
        return rows
    # earnings_guidance: sort by (end_date, ann_date) desc, take latest
    recs_eg = sorted(recs_all, key=lambda r: (str(r.get("end_date", "")), str(r.get("ann_date", ""))), reverse=True)
    latest = recs_eg[0]
    p_min = _safe_num(latest.get("p_change_min"))
    p_max = _safe_num(latest.get("p_change_max"))
    np_min = _safe_num(latest.get("net_profit_min"))
    np_max = _safe_num(latest.get("net_profit_max"))
    last_parent = _safe_num(latest.get("last_parent_net"))
    rows.append(("L9.company.earnings_guidance",
                 {"type": latest.get("type"), "change_pct_min": p_min, "change_pct_max": p_max,
                  "net_profit_min": np_min, "net_profit_max": np_max, "last_parent_net": last_parent,
                  "summary": latest.get("summary"), "ann_date": latest.get("ann_date"),
                  "period": latest.get("end_date"), "unit_net_profit": "万元"},
                 "Known", 0.85, "tushare:forecast"))
    # guidance_change: sort by (ann_date, end_date) desc, compare [0] vs [1]
    recs_gc = sorted(recs_all, key=lambda r: (str(r.get("ann_date", "")), str(r.get("end_date", ""))), reverse=True)
    cur = recs_gc[0]
    cur_mid = _midpoint(cur)
    cur_type = cur.get("type")
    if len(recs_gc) == 1:
        rows.append(("L5.fcst.guidance_change",
                     {"prev_type": None, "current_type": cur_type, "prev_range_pct": None,
                      "current_range_pct": cur_mid, "change_direction": "new",
                      "ann_date": cur.get("ann_date"), "period": cur.get("end_date")},
                     "Known", 0.8, "tushare:forecast"))
    else:
        prev = recs_gc[1]
        prev_mid = _midpoint(prev)
        prev_type = prev.get("type")
        if cur_mid is None or prev_mid is None:
            direction = "unchanged" if cur_type == prev_type else "type_change"
        elif cur_mid > prev_mid + 0.01:
            direction = "upgraded"
        elif cur_mid < prev_mid - 0.01:
            direction = "downgraded"
        else:
            direction = "unchanged"
        rows.append(("L5.fcst.guidance_change",
                     {"prev_type": prev_type, "current_type": cur_type, "prev_range_pct": prev_mid,
                      "current_range_pct": cur_mid, "change_direction": direction,
                      "ann_date": cur.get("ann_date"), "period": cur.get("end_date")},
                     "Known", 0.8, "tushare:forecast"))
    return rows


def emit_peer_compare(ts: str, asof: str, stock_pe: float | None, industry_id: str | None,
                      industry_pe_median: float | None) -> list[EmitRow]:
    """L6.state.peer_compare — PIT industry median computed across the universe.

    NOTE: production's industry median uses a broader industry-center; we
    reconstruct it from the in-universe peers at asof (documented divergence).
    """

    if stock_pe is None or industry_pe_median is None or industry_pe_median <= 0:
        return []
    premium = (stock_pe - industry_pe_median) / industry_pe_median * 100.0
    return [("L6.state.peer_compare",
             {"stock_pe": _round(stock_pe), "industry_pe_median": _round(industry_pe_median),
              "industry_id": industry_id, "premium_vs_industry_pct": _round(premium),
              "trade_date": asof}, "Known", 0.7, "tushare:daily_basic.peer_compare")]


# ---------------------------------------------------------------------------
# In-pipeline PIT assertion (leakage guard #1)
# ---------------------------------------------------------------------------

_OBSERVATION_DATE_KEYS = ("ann_date", "f_ann_date", "trade_date", "latest_date")


def assert_pit_rows(rows: Sequence[tuple], asof: str) -> None:
    """Fail loudly if any observation/announcement date in a payload exceeds
    ``asof``. (Report ``period``/forecast-year fields are intentionally NOT
    checked — a forecast target period can legitimately be in the future.)"""

    for row in rows:
        ts, dp, payload = row[0], row[1], row[2]
        if not isinstance(payload, dict):
            continue
        for k in _OBSERVATION_DATE_KEYS:
            v = payload.get(k)
            if isinstance(v, str) and len(v) == 8 and v.isdigit() and v > asof:
                raise AssertionError(
                    f"PIT LEAK: {ts} {dp} {k}={v} > asof={asof}"
                )


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def get_pro():
    from mvp20.sources import tushare_source as tss

    pro = tss._get_pro_api()
    if pro is None:
        raise RuntimeError("tushare pro_api unavailable (TUSHARE_TOKEN missing?)")
    return pro


_DB_SNAP_FIELDS = ("ts_code,trade_date,close,turnover_rate,pe_ttm,pb,volume_ratio,"
                   "ps_ttm,total_mv,total_share")


def wide_daily_basic_snapshot(pro, asof: str, max_back: int = 8) -> tuple[dict[str, dict], str]:
    """Whole-market daily_basic at ``asof`` (walk back a few sessions if empty).

    Returns ({ts_code: row}, used_date). One call for all 116 stocks' snapshot
    + the cross-section needed for the peer-compare industry median.
    """

    d = asof
    for _ in range(max_back + 1):
        df = _rpc(pro.daily_basic, trade_date=d, fields=_DB_SNAP_FIELDS)
        if df is not None and len(df):
            return {str(r["ts_code"]): r for r in df.to_dict("records")}, d
        d = (datetime.strptime(d, "%Y%m%d") - timedelta(days=1)).strftime("%Y%m%d")
    return {}, asof


def industry_pe_medians(snap: Mapping[str, dict], codes: Sequence[str],
                        industry_of: Mapping[str, str | None]) -> dict[str, float]:
    """Median pe_ttm per primary industry across the in-universe peers at asof."""

    import statistics

    buckets: dict[str, list[float]] = {}
    for ts in codes:
        row = snap.get(ts)
        ind = industry_of.get(ts)
        if not row or not ind:
            continue
        pe = _safe_num(row.get("pe_ttm"))
        if pe is not None and pe > 0:
            buckets.setdefault(ind, []).append(pe)
    return {ind: float(statistics.median(v)) for ind, v in buckets.items() if v}


def already_collected(db_path: Path, ts: str) -> bool:
    import sqlite3

    if not Path(db_path).exists():
        return False
    try:
        con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        try:
            r = con.execute(
                "SELECT 1 FROM realtime_current WHERE ts_code=? LIMIT 1", (ts,)
            ).fetchone()
        finally:
            con.close()
        return r is not None
    except sqlite3.OperationalError:
        return False


def collect_stock(pro, ts: str, asof: str, now: int, db_row: Mapping | None,
                  industry_id: str | None, ind_pe_median: float | None) -> list[tuple]:
    """All PIT rows for one stock at ``asof`` as upsert 7-tuples."""

    emits: list[EmitRow] = []
    stmts = fetch_statements(pro, ts, asof)
    emits += emit_fina_indicator(stmts["fina"])
    emits += emit_income(stmts["income"])
    total_mv = _safe_num(db_row.get("total_mv")) if db_row else None
    emits += emit_cashflow(stmts["cashflow"], total_mv)
    emits += emit_balancesheet(stmts["balancesheet"])
    emits += emit_derived_metrics(stmts)
    if db_row:
        emits += emit_daily_basic_snapshot(db_row, asof)
    mf_rows, main_net = emit_moneyflow(pro, ts, asof)
    emits += mf_rows
    emits += emit_price_technicals(pro, ts, asof)
    emits += emit_capital_risk(pro, ts, asof, main_net)
    emits += emit_report_rc(pro, ts, asof)
    emits += emit_forecast(pro, ts, asof)
    stock_pe = _safe_num(db_row.get("pe_ttm")) if db_row else None
    emits += emit_peer_compare(ts, asof, stock_pe, industry_id, ind_pe_median)

    rows = [(ts, dp, payload, status, conf, src, now)
            for (dp, payload, status, conf, src) in emits]
    assert_pit_rows(rows, asof)  # leakage guard — raises on any future-dated obs
    return rows


def collect_universe_asof(asof: str, codes: Sequence[str], db_path: Path,
                          industry_of: Mapping[str, str | None], *,
                          pro=None, resume: bool = True, progress=None) -> dict:
    """Collect PIT rows for all ``codes`` at ``asof`` into an isolated DB.

    Resumable: skips stocks already present in ``db_path``. Returns stats.
    """

    pro = pro or get_pro()
    now = asof_epoch(asof)
    db_path = Path(db_path)
    storage.init_db(db_path)
    snap, used = wide_daily_basic_snapshot(pro, asof)
    if used != asof:
        log.warning("daily_basic snapshot walked back %s -> %s", asof, used)
    ind_pe = industry_pe_medians(snap, codes, industry_of)

    stats = {"asof": asof, "n_codes": len(codes), "collected": 0, "skipped": 0,
             "rows": 0, "errors": 0}
    for i, ts in enumerate(codes):
        if resume and already_collected(db_path, ts):
            stats["skipped"] += 1
            continue
        try:
            rows = collect_stock(pro, ts, asof, now, snap.get(ts),
                                 industry_of.get(ts), ind_pe.get(industry_of.get(ts)))
            n = storage.upsert_realtime(db_path, rows)
            stats["collected"] += 1
            stats["rows"] += n
        except AssertionError:
            raise  # PIT leak must abort the run
        except Exception as e:  # noqa: BLE001
            stats["errors"] += 1
            log.warning("collect %s @ %s failed: %s", ts, asof, str(e)[:160])
        if progress:
            progress(i + 1, len(codes), ts)
    return stats

