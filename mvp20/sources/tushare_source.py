"""Tushare source for A-share realtime/daily data.

A-share is NOT covered by Futu (no permission), so Tushare picks up the
slack. Most Tushare endpoints used here are daily (EOD); the collector
re-pulls them every minute but the values only change after market close.
That's fine — UPSERT is idempotent and the freshness panel will show the
real ``updated_at`` of the underlying daily snapshot.

Real intraday A-share data (minute bars, 1s tick) requires Tushare credit
score 5000+ which we don't enforce here; if those endpoints fail we just
skip them — never crash the collector cycle.
"""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Iterable

log = logging.getLogger("mvp20.sources.tushare")

SUPPORTED_DP_IDS = {
    # L6/L7 daily (from daily_basic / moneyflow / hk_hold)
    "L6.mult.pe",                # was L6.priced.intraday_pe
    "L6.mult.pb",                # was L6.priced.intraday_pb
    "L6.mult.ps",                # daily_basic.ps_ttm (Phase B.7)
    "L6.mult.mcap_fcf",          # daily_basic.total_mv / cashflow.free_cashflow (TTM)
    "L6.state.historical_percentile",  # PE/PB historical percentile (alias of L10.val.historical_quantile)
    "L7.trade.volume_turnover",  # merges old L7.trade.turnover_pct + volume_ratio
    "L7.flow.active_inflow",     # merges old L7.flow.netbuy + 大单 derived
    "L7.flow.passive_northbound",
    "L7.flow.margin_balance",
    "L7.flow.block_trade",
    "L7.flow.etf_inflow",
    "L7.trade.margin_short",     # 融资融券
    # L5 quarterly (from income / cashflow / balancesheet / fina_indicator)
    "L5.is.revenue",
    "L5.is.revenue_growth",
    "L5.is.gross_profit",
    "L5.is.gross_margin",
    "L5.is.operating_profit",
    "L5.is.net_profit",
    "L5.is.eps",
    "L5.is.margins",
    "L5.is.sga_rd",
    "L5.cf.ocf",
    "L5.cf.fcf",
    "L5.cf.capex",
    "L5.cf.icf_fcf",
    "L5.cf.buyback_dividend",
    "L5.bs.cash_debt",
    "L5.bs.leverage",
    "L5.bs.inventory",
    "L5.bs.ar_ap",
    "L5.bs.goodwill_ppe",
    # L5 financial indicators (from fina_indicator) — A-share deep-dive metrics.
    # Note: these specific L5.fina.* dp_ids are NOT individually enumerated in
    # 图谱设计.md (spec stops at the L5.{is,bs,cf} family). They extend the
    # 财务报表与财务预期层 with ratio/per-share/YoY indicators per Phase B.4.
    "L5.fina.roe",
    "L5.fina.roa",
    "L5.fina.net_margin",
    "L5.fina.gross_margin",
    "L5.fina.debt_ratio",
    "L5.fina.asset_turnover",
    "L5.fina.revenue_yoy_q",
    "L5.fina.profit_yoy_q",
    "L5.fina.ocf_quality",
    "L5.fina.working_capital",
    "L5.fina.bps",
    "L5.fina.eps",
    "L5.fina.cfps",
    "L5.fina.revenue_yoy",
    "L5.fina.total_revenue_yoy",
    "L5.fina.net_profit_yoy",
    # L9 events
    "L9.company.earnings_guidance",
    "L9.company.buyback_dividend",
    "L9.company.mgmt_litigation",
    "L9.capital.inst_buy_sell",
    # L5 sell-side consensus (Phase B.7) — from report_rc 90d aggregate
    "L5.surprise.sell_side",
    # L9 holder-trade signals (from stk_holdertrade, Phase B.6a). The spec
    # (图谱设计.md §9/§治理风险) calls out "机构增持/减持" under 资金事件 and
    # "股东减持" under 治理风险 but does not enumerate per-dp_id names. We
    # mirror the L9.event.* convention used by fmp_source for consistency.
    "L9.event.holder_trade_signal",
    "L9.event.major_holder_increase",
    "L9.event.major_holder_decrease",
    # ── X1 spec-canonical aliases (dual-emitted from the above legacy
    # dp_ids by ``_emit_spec_aliases``). Confidence + status are inherited
    # from the legacy row; payload is reshaped where the spec semantics
    # differ (e.g. increase/decrease magnitude → signed net_change_pct).
    "L8.gov.insider_sell",            # alias of major_holder_increase /
                                       # major_holder_decrease /
                                       # holder_trade_signal
    "L7.flow.institutional",          # alias of L9.capital.inst_buy_sell
    "L8.gov.management_change",       # alias of L9.company.mgmt_litigation
    # ── China macro / industry beat (Phase B.8) ────────────────────────────
    # Market-wide and industry-level dp_ids emitted by
    # ``fetch_macro_china_batch``. ts_code uses MARKET:CN / INDUSTRY:<id>
    # sentinels (not registered in universe.yaml — SQLite PK on (ts_code,
    # dp_id) only needs uniqueness, not FK referential integrity).
    "L10.industry.pmi",           # cn_pmi (manufacturing + non-manuf + composite)
    "L7.env.rates",               # shibor_lpr — LPR1Y/5Y + Shibor (state)
    "L9.macro.rates",             # same source, event-shaped when LPR moves
    "L7.env.liquidity",           # cn_m M0/M1/M2 (state)
    "L9.macro.liquidity",         # cn_m event-shaped when M2 yoy shifts
    "L9.macro.cpi_employment",    # cn_cpi + cn_ppi
    "L10.val.historical_quantile",  # market-wide PE_ttm quantile from daily_basic
    "L10.industry.fund_flow",     # moneyflow_ind_ths per active industry
    # ── X3b: per-stock derived A-share fundamentals (Phase B.9) ──
    # Each dp_id is computed in ``_fetch_a_share_derived_metrics`` from a
    # mix of fina_indicator + balancesheet + cashflow + income. Per-stock
    # cache (``_FINA_CACHE`` family) keeps the Tushare RPC count flat
    # within a 5-min window.
    "L4.cost.labor",              # cashflow.c_paid_to_for_empl / revenue + YoY
    "L4.cost.raw_material",       # oper_cost - labor proxy; YoY + primary_commodity
    "L4.eff.turnover",            # DIO + DSO + DPO from balancesheet + income
    "L4.eff.cycle",               # CCC = DIO + DSO - DPO
    "L8.fin.cash_ar",             # OCF/NI + AR yoy, alert_severity threshold
    "L8.fin.debt_pressure",       # interest_debt / EBITDA, alert_severity
    "L8.op.inventory_glut",       # inventory yoy vs turnover delta, alert
    # ── X5: text-disclosure dp_ids surfaced to codex prompts ──
    # These three dp_ids are *not* in spec 250 (data_point_roles.yaml).
    # They are mvp20-internal facts that codex consumes via prompt injection
    # to fill the 26 new closed-loop slots without hitting external sources.
    # field_governance treats them as unmanaged, which is fine — the SQLite
    # emit only powers codex_prompt_gen.py, not score aggregation.
    "L9.disclosure.qa_recent",    # irm_qa_sh / irm_qa_sz (投资者关系 Q&A)
    "L1.company.main_business",   # stock_company (主营业务 + 业务范围)
    "L8.gov.management_table",    # stk_managers (top10 高管 + 任期表)
}


# ---------------------------------------------------------------------------
# Macro / industry-level config (Phase B.8)
# ---------------------------------------------------------------------------
#
# Map of industry slug (matches files under config/industry_overlays/) to the
# Tushare 同花顺 industry name expected by ``pro.moneyflow_ind_ths``. Slugs
# with ``None`` are intentionally skipped until a clean mapping is verified.
# Anything we don't trust to be a precise 1:1 match stays a TODO so we never
# accidentally surface mis-attributed fund-flow data.
INDUSTRY_TO_THS_NAME: dict[str, str | None] = {
    "SEMI_EQUIPMENT":          "半导体",       # THS 行业「半导体」
    "EXPORT_MFG":              "通用设备",     # 近似映射，跨多个 THS 板块
    "STORAGE_GRID":            "电池",         # 储能 → THS「电池」
    "CONSUMER_ELECTRONICS":    "消费电子",     # THS 行业「消费电子」
    "AI_COMPUTE":              "计算机设备",   # 算力硬件 → THS「计算机设备」
    "INNOVATIVE_PHARMA":       "生物制品",     # 创新药/生物医药 → THS「生物制品」
    "ROBOTICS":                "自动化设备",   # 具身智能装备 → THS「自动化设备」
    "FINANCIAL_HIGH_DIVIDEND": "证券",         # 取代表性子行业；可扩展为多映射
    # TODO: 余下行业 THS 没有 1:1 干净映射，留 None 跳过：
    "NONFERROUS_METALS":       None,  # TODO THS 拆为「贵金属」+「能源金属」+「工业金属」+「小金属」四张表
    "ANTI_INVOLUTION_CYCLICAL": None,  # TODO 跨化工/建材/钢铁多个 THS 行业，待拆分
    "DOMESTIC_CONSUMPTION":    None,   # TODO 涵盖文旅/酒店/航空/医美，THS 无 1:1
    "HK_CN_INTERNET":          None,   # TODO 港股 moneyflow_ind_ths 不覆盖
    "SPACE_ECONOMY":           None,   # TODO 行业本身 graph_status=pending
}

# Macro endpoints update at most daily (some monthly). Collector ticks every
# ~60s but a 600s cache window keeps Tushare API budget under control while
# still re-emitting "cached" rows each cycle so freshness panel sees motion.
_MACRO_CACHE_TTL_S = 600
_LAST_MACRO_FETCH: dict[str, object] = {
    "ts": 0,        # unix epoch of last real Tushare fetch
    "rows": [],     # cached row list (with original updated_at preserved)
}

# ---------------------------------------------------------------------------
# X3b: per-stock Tushare financial-statement cache (5-min TTL)
# ---------------------------------------------------------------------------
#
# The seven derived dp_ids added in X3b read from a mix of fina_indicator,
# balancesheet, cashflow and income. The legacy fetchers
# ``_fetch_a_share_financials`` and ``_fetch_a_share_fina_indicator`` already
# loop per-stock and call each endpoint once. To avoid re-pulling the same
# data inside ``_fetch_a_share_derived_metrics`` we stash the raw record
# lists keyed by ts_code with a short TTL — the collector's cycle is < 60s
# so a 5-min window comfortably covers a single cycle even when calls take
# wall-clock time.
_FINA_CACHE_TTL_S = 300
# Maps ts_code → (epoch, list[dict]) for each endpoint.
_FINA_CACHE: dict[str, tuple[int, list[dict]]] = {}
_BALANCESHEET_CACHE: dict[str, tuple[int, list[dict]]] = {}
_CASHFLOW_CACHE: dict[str, tuple[int, list[dict]]] = {}
_INCOME_CACHE: dict[str, tuple[int, list[dict]]] = {}

# ---------------------------------------------------------------------------
# X5: text-disclosure cache (10-min TTL)
# ---------------------------------------------------------------------------
#
# The three X5 text fetchers (irm_qa, stock_company, stk_managers) all serve
# *slow-moving* disclosure data — Q&A backlog, main business descriptions,
# and the 高管 table. A 10-min cache keeps the collector's per-minute tick
# from blowing the Tushare RPC budget on data that updates at most weekly.
_DISCLOSURE_CACHE_TTL_S = 600
_IRM_QA_CACHE: dict[str, tuple[int, list[dict]]] = {}
_STOCK_COMPANY_CACHE: dict[str, tuple[int, list[dict]]] = {}
_STK_MANAGERS_CACHE: dict[str, tuple[int, list[dict]]] = {}


def is_a_share(ts_code: str) -> bool:
    return ts_code.endswith((".SH", ".SZ", ".BJ"))


# ---------------------------------------------------------------------------
# Init
# ---------------------------------------------------------------------------


def _get_pro_api():
    """Lazy-init Tushare pro_api with TUSHARE_TOKEN from env. Returns None
    if token is missing — caller treats that as 'source unavailable'."""

    import tushare as ts  # type: ignore

    token = os.environ.get("TUSHARE_TOKEN")
    if not token:
        # Try loading .env on demand
        from . import load_dotenv
        load_dotenv()
        token = os.environ.get("TUSHARE_TOKEN")
    if not token:
        return None
    ts.set_token(token)
    return ts.pro_api()


def health_check() -> dict:
    """Probe Tushare: call a trivial endpoint to verify token + connectivity."""

    try:
        import tushare as ts  # type: ignore
    except ImportError as e:
        return {"ok": False, "error": f"tushare not installed: {e}"}

    pro = _get_pro_api()
    if pro is None:
        return {"ok": False, "error": "TUSHARE_TOKEN missing in env / .env"}

    try:
        # Trade calendar is small, fast, and a good liveness probe
        df = pro.trade_cal(exchange="SSE", start_date="20260101", end_date="20260105")
        return {
            "ok": True,
            "trade_cal_rows": int(len(df)),
            "tushare_version": ts.__version__,
        }
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"trade_cal probe failed: {e}"}


# ---------------------------------------------------------------------------
# Code conversion: mvp20 ts_code is already Tushare-native (no conversion)
# Tushare uses "300750.SZ" / "600519.SH" / "832735.BJ" identically to mvp20.
# ---------------------------------------------------------------------------


def _today_yyyymmdd() -> str:
    return datetime.now(tz=timezone.utc).strftime("%Y%m%d")


def _previous_n_days(n: int) -> str:
    from datetime import timedelta
    return (datetime.now(tz=timezone.utc) - timedelta(days=n)).strftime("%Y%m%d")


# ---------------------------------------------------------------------------
# dp_id alias dual-emit helper (X1 spec-alignment)
# ---------------------------------------------------------------------------
#
# Several legacy mvp20-coined dp_ids (e.g. ``L9.event.major_holder_increase``,
# ``L9.event.holder_trade_signal``, ``L9.capital.inst_buy_sell``,
# ``L9.company.mgmt_litigation``) carry semantics that the global spec
# expresses with different canonical names under the L7/L8 namespace
# (``L7.flow.institutional``, ``L8.gov.insider_sell``,
# ``L8.gov.management_change``). To converge with the spec **without breaking
# downstream consumers that already key off the legacy names**, we keep the
# legacy emit untouched and *also* emit a sibling row under the spec dp_id.
#
# ``_alias_emit`` scans the row list for the legacy dp_id, copies each
# matching row into a new row keyed by the spec dp_id (optionally with a
# payload transform for semantic remapping such as
# increase→insider_sell-with-negative-magnitude), and appends the aliases to
# the same list. confidence/status/source/ts are preserved 1:1 unless a
# transform overrides them.


def _alias_emit(
    rows: list[tuple],
    old_dp_id: str,
    new_dp_id: str,
    payload_transform=None,
    status_transform=None,
) -> int:
    """Append spec-aligned alias rows for every ``old_dp_id`` row in ``rows``.

    Arguments:
        rows: the in-progress row list (modified in place).
        old_dp_id: the legacy dp_id to duplicate from.
        new_dp_id: the spec-aligned dp_id to emit as the alias.
        payload_transform: optional ``callable(payload_dict, legacy_row)``
            returning the new payload dict. If None, the payload is copied
            verbatim. The transform receives the parsed payload + the full
            7-tuple legacy row (handy for the increase→insider_sell case
            where we flip the sign of the magnitude).
        status_transform: optional ``callable(legacy_status) -> new_status``.
            Defaults to passing the legacy status through.

    Returns: number of alias rows appended.
    """

    appended = 0
    legacy_rows = [r for r in rows if r[1] == old_dp_id]
    for legacy_row in legacy_rows:
        ts_code, _dp, value_json, status, conf, source, ts = legacy_row
        try:
            payload = json.loads(value_json) if value_json else {}
        except (TypeError, ValueError):
            payload = {}
        if payload_transform is not None:
            try:
                payload = payload_transform(payload, legacy_row)
            except Exception as e:  # noqa: BLE001 — never let an alias
                # transform poison the legacy emit; just skip this row.
                log.warning(
                    "[tushare] _alias_emit %s→%s transform failed on %s: %s",
                    old_dp_id, new_dp_id, ts_code, e,
                )
                continue
        new_status = status
        if status_transform is not None:
            try:
                new_status = status_transform(status)
            except Exception:  # noqa: BLE001
                new_status = status
        # Tag the alias source so we can tell legacy and alias apart in the
        # freshness panel without breaking the existing emit string.
        alias_source = f"{source}|alias→{new_dp_id}"
        rows.append((
            ts_code, new_dp_id,
            json.dumps(payload, ensure_ascii=False),
            new_status, conf, alias_source, ts,
        ))
        appended += 1
    return appended


# ---------------------------------------------------------------------------
# Batch fetch
# ---------------------------------------------------------------------------


def _safe(d: dict, key: str):
    v = d.get(key)
    if v is None or (isinstance(v, float) and v != v):
        return None
    return v


def _compute_ttm_fcf(
    by_period: dict[str, dict],
    periods_desc: list[str],
) -> float | None:
    """Derive trailing-twelve-month free cashflow from Tushare cashflow YTD.

    Tushare ``cashflow.free_cashflow`` is cumulative year-to-date for each
    ``end_date``. To approximate TTM:
      * If the latest period is fiscal year-end (``MMDD == 1231``) we treat
        it as a full-year TTM directly.
      * Otherwise TTM = latest_YTD + prior_FY - prior_year_same_quarter_YTD,
        where same quarter is matched by ``MMDD``.
    Returns ``None`` if we cannot assemble the components or every value
    is null.
    """

    if not periods_desc:
        return None
    latest = periods_desc[0]
    latest_fcf = _safe(by_period[latest], "free_cashflow")

    # Full-year case: latest is fiscal year-end (e.g. 20251231)
    if latest.endswith("1231"):
        if latest_fcf is None:
            return None
        try:
            return float(latest_fcf)
        except (TypeError, ValueError):
            return None

    if latest_fcf is None:
        return None

    # Otherwise need prior FY (YYYY-1)1231 and same-quarter prior-year YTD
    try:
        latest_year = int(latest[:4])
        latest_mmdd = latest[4:]
    except (TypeError, ValueError):
        return None

    prior_fy = f"{latest_year - 1}1231"
    prior_q = f"{latest_year - 1}{latest_mmdd}"

    prior_fy_fcf = _safe(by_period.get(prior_fy) or {}, "free_cashflow")
    prior_q_fcf = _safe(by_period.get(prior_q) or {}, "free_cashflow")

    if prior_fy_fcf is None or prior_q_fcf is None:
        # Fall back to latest YTD as a coarse approximation. Better than
        # returning None for interim quarters where the prior-year row
        # isn't in our 8-row window (rare but possible after a re-statement).
        try:
            return float(latest_fcf)
        except (TypeError, ValueError):
            return None

    try:
        return float(latest_fcf) + float(prior_fy_fcf) - float(prior_q_fcf)
    except (TypeError, ValueError):
        return None


def fetch_batch(
    constituents: Iterable[dict],
    tick: int,
) -> list[tuple]:
    """Pull EOD/daily snapshot of every A-share constituent from Tushare.

    HK/US rows are silently skipped (Futu's domain).
    """

    pro = _get_pro_api()
    if pro is None:
        log.warning("[tushare] TUSHARE_TOKEN not set — skipping batch")
        return []

    # Materialize once — ``constituents`` may be a generator. We need both
    # the A-share ts_code list and a per-stock industry map for the X3b
    # raw_material primary-commodity attribution.
    cons_list = [c for c in constituents if c.get("ts_code")]
    a_codes = [c["ts_code"] for c in cons_list if is_a_share(c["ts_code"])]
    if not a_codes:
        return []

    # ``code_to_industry``: ts_code → first industry_id in the universe
    # entry, used by X3b L4.cost.raw_material to populate primary_commodity.
    code_to_industry: dict[str, str | None] = {}
    for c in cons_list:
        code = c.get("ts_code")
        if not code or not is_a_share(code):
            continue
        ids = c.get("industry_ids") or []
        code_to_industry[code] = ids[0] if ids else None

    now = int(time.time())
    rows: list[tuple] = []

    # ── daily_basic: PE, PB, turnover_rate, volume_ratio per A股 ──
    # NOTE: pro.daily_basic does NOT accept comma-separated ts_codes
    # (unlike moneyflow). Fetch the entire trading-day snapshot in one call
    # and filter to our universe in-memory; 5K rows is small.
    a_codes_set = set(a_codes)
    daily_basic_df = None
    for back in range(0, 8):
        trade_date = _previous_n_days(back)
        try:
            df = pro.daily_basic(
                trade_date=trade_date,
                fields=("ts_code,trade_date,close,turnover_rate,pe_ttm,pb,"
                        "volume_ratio,ps_ttm,total_mv"),
            )
            if df is not None and len(df) > 0:
                # Filter to universe
                df = df[df["ts_code"].isin(a_codes_set)]
                if len(df) > 0:
                    daily_basic_df = df
                    log.info("[tushare] daily_basic from %s rows=%d (filtered)",
                             trade_date, len(df))
                    break
        except Exception as e:  # noqa: BLE001
            log.warning("[tushare] daily_basic %s failed: %s", trade_date, e)
            continue

    # ``total_mv_by_ts_code`` is reused below to derive L6.mult.mcap_fcf;
    # Tushare returns it in 万元 (10k CNY). We carry the 万元 value
    # untouched in the dp_id payload and convert to 元 only when computing
    # the mcap/fcf ratio.
    total_mv_by_ts_code: dict[str, float] = {}

    if daily_basic_df is not None:
        for rec in daily_basic_df.to_dict(orient="records"):
            ts_code = rec.get("ts_code")
            if not ts_code:
                continue
            pe = _safe(rec, "pe_ttm")
            pb = _safe(rec, "pb")
            ps = _safe(rec, "ps_ttm")
            total_mv = _safe(rec, "total_mv")
            turnover_rate = _safe(rec, "turnover_rate")
            volume_ratio = _safe(rec, "volume_ratio")
            trade_date = rec.get("trade_date")

            if total_mv is not None:
                try:
                    total_mv_by_ts_code[ts_code] = float(total_mv)
                except (TypeError, ValueError):
                    pass

            # spec-aligned: L6.mult.pe / L6.mult.pb / L6.mult.ps
            # (was L6.priced.intraday_*)
            for dp_id, val in (("L6.mult.pe", pe), ("L6.mult.pb", pb),
                                ("L6.mult.ps", ps)):
                if val is None:
                    continue
                rows.append((
                    ts_code, dp_id,
                    json.dumps({"scalar": float(val), "unit": "ratio",
                                "ttm": True, "trade_date": trade_date},
                               ensure_ascii=False),
                    "Known", 0.7, "tushare:daily_basic", now,
                ))
            # spec L7.trade.volume_turnover bundles turnover_rate + volume_ratio
            if turnover_rate is not None or volume_ratio is not None:
                rows.append((
                    ts_code, "L7.trade.volume_turnover",
                    json.dumps({
                        "turnover_rate_pct": float(turnover_rate) if turnover_rate is not None else None,
                        "volume_ratio": float(volume_ratio) if volume_ratio is not None else None,
                        "trade_date": trade_date,
                    }, ensure_ascii=False),
                    "Known", 0.7, "tushare:daily_basic", now,
                ))

    # ── moneyflow: 大单/中单/小单 流入流出 (EOD) per A股 ──
    # Same comma-separated limitation observed empirically (only ~half of
    # codes round-trip). Use trade_date-wide fetch + in-memory filter.
    moneyflow_df = None
    for back in range(0, 8):
        trade_date = _previous_n_days(back)
        try:
            df = pro.moneyflow(
                trade_date=trade_date,
                fields="ts_code,trade_date,net_mf_amount,buy_lg_amount,sell_lg_amount,buy_elg_amount,sell_elg_amount",
            )
            if df is not None and len(df) > 0:
                df = df[df["ts_code"].isin(a_codes_set)]
                if len(df) > 0:
                    moneyflow_df = df
                    log.info("[tushare] moneyflow from %s rows=%d (filtered)",
                             trade_date, len(df))
                    break
        except Exception as e:  # noqa: BLE001
            log.warning("[tushare] moneyflow %s failed: %s", trade_date, e)
            continue

    if moneyflow_df is not None:
        for rec in moneyflow_df.to_dict(orient="records"):
            ts_code = rec.get("ts_code")
            if not ts_code:
                continue
            netbuy = _safe(rec, "net_mf_amount")
            buy_lg = _safe(rec, "buy_lg_amount") or 0
            sell_lg = _safe(rec, "sell_lg_amount") or 0
            buy_elg = _safe(rec, "buy_elg_amount") or 0
            sell_elg = _safe(rec, "sell_elg_amount") or 0
            big_orders_net = (buy_lg + buy_elg) - (sell_lg + sell_elg)  # 大+特大单净买入

            # spec L7.flow.active_inflow bundles both Tushare net_mf_amount
            # (主力净流入) and the derived 大+特大 单净买入. The frontend gets
            # one dp_id with a structured JSON value rather than two.
            rows.append((
                ts_code, "L7.flow.active_inflow",
                json.dumps({
                    "main_net": float(netbuy) if netbuy is not None else None,
                    "big_orders_net": float(big_orders_net),
                    "unit": "万元",
                    "trade_date": rec.get("trade_date"),
                }, ensure_ascii=False),
                "Known", 0.75, "tushare:moneyflow", now,
            ))

    # ── hk_hold: per-stock Hong Kong holding amount (北向资金 per-stock持仓) ──
    # 这是 EOD 数据，每天一条；近似 passive_northbound 这个 dp_id
    try:
        df = pro.hk_hold(
            trade_date=_previous_n_days(1),  # T-1
            fields="ts_code,trade_date,vol,ratio",
        )
        if df is not None and len(df) > 0:
            df = df[df["ts_code"].isin(a_codes_set)]
        if df is not None and len(df) > 0:
            for rec in df.to_dict(orient="records"):
                ts_code = rec.get("ts_code")
                if not ts_code:
                    continue
                vol = _safe(rec, "vol")
                ratio = _safe(rec, "ratio")
                rows.append((
                    ts_code, "L7.flow.passive_northbound",
                    json.dumps({"vol": vol, "ratio_pct": ratio,
                                "trade_date": rec.get("trade_date")},
                               ensure_ascii=False),
                    "Known", 0.7, "tushare:hk_hold", now,
                ))
    except Exception as e:  # noqa: BLE001
        log.warning("[tushare] hk_hold failed (likely permission): %s", e)

    # ── L7 capital events: margin / top_list / block_trade (trade-date-wide) ──
    rows.extend(_fetch_a_share_capital_events(pro, a_codes_set, now))

    # ── L5 财务报表（per A 股一次性最新季度）──
    # income / balancesheet / cashflow 都不接受 trade_date-wide 全市场调用
    # （必须 ts_code），所以这里 loop per-stock。Tushare 500 calls/min 的限额
    # 对 116 × 4 = 464 calls 来说勉强；如果命中限速会在 token 内部 sleep。
    #
    # ``total_mv_by_ts_code`` is forwarded so the cashflow loop can derive
    # L6.mult.mcap_fcf without re-pulling daily_basic.
    rows.extend(_fetch_a_share_financials(
        pro, a_codes, now, total_mv_by_ts_code=total_mv_by_ts_code,
    ))

    # ── L5 财务指标（fina_indicator, per A 股）──
    # 116 stocks × 1 call/stock = 116 calls, throttled to keep total
    # Tushare-API budget (income+balance+cashflow+dividend+fina = ~580 calls)
    # comfortably under 500/min when the prior loops have already burned
    # wall-clock. ~0.13s sleep gives ~7.6 RPS within the new sub-batch.
    rows.extend(_fetch_a_share_fina_indicator(pro, a_codes, now))

    # ── L9 重要股东增减持（stk_holdertrade, per A 股, Phase B.6a）──
    # Single ts_code per call; ~0.13s sleep keeps us under 500/min along
    # with the prior fina_indicator burst.
    rows.extend(_fetch_a_share_holder_trade(pro, a_codes, now))

    # ── L9 业绩预告（forecast, per A 股, Phase B.7）──
    # 业绩预告/预增/预减/扭亏 — event-type field, Inactive when no forecast.
    rows.extend(_fetch_a_share_forecast(pro, a_codes, now))

    # ── L9.company.mgmt_litigation (X2: declared-but-silent fix) ──
    # Tushare ``stk_managers`` per A-share, aggregated to 180-day window.
    # Pre-X2 this dp_id had 0 rows in SQLite because no emit path existed.
    rows.extend(_fetch_a_share_mgmt_litigation(pro, a_codes, now))

    # ── L5 卖方一致预期（report_rc, per A 股, Phase B.7）──
    # 券商研报评级 + 业绩预测 — 90-day aggregate; Inactive when no report.
    rows.extend(_fetch_a_share_report_rc(pro, a_codes, now))

    # ── L6.state.historical_percentile (alias of L10.val.historical_quantile) ──
    # The derive.py pipeline emits L10.val.historical_quantile after history
    # backfill; we also need L6.state.historical_percentile per spec. The
    # derive.py edit is out of scope (U-stream owns derive.py), so the
    # collector instead emits the alias here by recomputing PE/PB percentile
    # from a 250-trading-day daily_basic window — same data, alternate dp_id.
    rows.extend(_fetch_a_share_historical_percentile(pro, a_codes, now))

    # ── China macro / industry beat (Phase B.8) ──
    # Sentinel ts_codes (MARKET:CN / INDUSTRY:<id>); ~600s in-process cache
    # so the collector's per-minute tick doesn't burn Tushare API budget on
    # monthly-cadence data.
    try:
        rows.extend(fetch_macro_china_batch(now))
    except Exception as e:  # noqa: BLE001
        log.warning("[tushare] fetch_macro_china_batch failed: %s", e)

    # ── X3b: per-stock derived A-share fundamentals (Phase B.9) ──
    # Seven dp_ids derived from fina_indicator + balancesheet + cashflow +
    # income. The fetcher reuses a per-stock 5-min cache so the additional
    # RPC pressure is bounded (worst case 4 endpoints × 116 stocks within
    # a 5-min window). Each individual dp_id fetch is wrapped in its own
    # try/except — a single endpoint failure cannot poison the rest.
    try:
        rows.extend(_fetch_a_share_derived_metrics(
            pro, a_codes, code_to_industry, now,
        ))
    except Exception as e:  # noqa: BLE001
        log.warning("[tushare] X3b derived metrics batch failed: %s", e)

    # ── X1 spec-alignment: dual-emit spec-canonical aliases ──
    # The legacy mvp20-coined dp_ids stay untouched (downstream consumers
    # keep working) while we also emit the spec equivalent so coverage
    # converges with config/data_point_roles.yaml. Confidence/status are
    # preserved 1:1 unless the transform overrides them.
    try:
        _emit_spec_aliases(rows)
    except Exception as e:  # noqa: BLE001
        log.warning("[tushare] spec alias emit failed: %s", e)

    # ── X5: text-disclosure fetchers (irm_qa, stock_company, stk_managers) ──
    # These three dp_ids exist solely to give codex LLM prompts inline facts
    # for the X5 closed-loop pipeline (no web search, no training-memory
    # quoting). They are not registered in data_point_roles.yaml — keep them
    # at the tail so any per-endpoint failure cannot affect the spec-managed
    # rows above.
    try:
        rows.extend(fetch_disclosure_batch(pro, a_codes, now))
    except Exception as e:  # noqa: BLE001
        log.warning("[tushare] X5 disclosure batch failed: %s", e)

    return rows


def _emit_spec_aliases(rows: list[tuple]) -> None:
    """Dual-emit X1 spec-canonical alias rows into ``rows`` (in place).

    Five legacy→spec mappings:

      * ``L9.event.major_holder_increase`` → ``L8.gov.insider_sell``
        (increase is *reverse* of insider_sell; we negate the magnitude so
        the spec dp_id reads as a single signed signal — a positive
        net_change_pct value means net buying, negative means net selling.
        This collapses the legacy increase/decrease pair into the spec's
        single signed dp_id.)
      * ``L9.event.major_holder_decrease`` → ``L8.gov.insider_sell``
        (sign preserved; decrease maps to negative net_change_pct).
      * ``L9.event.holder_trade_signal`` → ``L8.gov.insider_sell``
        (aggregate 90-day signal; primary spec emit per the X1 table).
      * ``L9.capital.inst_buy_sell`` → ``L7.flow.institutional``
        (龙虎榜 institutional buying/selling is the spec's "机构资金流向"
        proxy; payload copied verbatim).
      * ``L9.company.mgmt_litigation`` → ``L8.gov.management_change``
        (management litigation events are a sub-signal of management
        change; payload copied verbatim. Until X2 wires the legacy emit
        this alias is a no-op.)
    """

    def _increase_to_insider_sell(payload: dict, _legacy_row: tuple) -> dict:
        """Increase semantics → spec dp_id with **positive** net_change_pct.

        Legacy major_holder_increase carries ``total_pct >= 0`` (magnitude
        only — increase implies buy). The spec L8.gov.insider_sell is a
        risk_discount field, so a positive net_change_pct means net
        *buying* (protective signal); a negative means net selling
        (risk). We mirror this by emitting +total_pct here.
        """

        magnitude = payload.get("total_pct") or 0.0
        try:
            net_change_pct = float(magnitude)
        except (TypeError, ValueError):
            net_change_pct = 0.0
        return {
            "net_change_pct": net_change_pct,
            "direction": "increase",
            "count": payload.get("count", 0),
            "latest_date": payload.get("latest_date"),
            "lookback_days": payload.get("lookback_days"),
            "_from_legacy": "L9.event.major_holder_increase",
        }

    def _decrease_to_insider_sell(payload: dict, _legacy_row: tuple) -> dict:
        """Decrease → negative net_change_pct (insider selling = risk)."""

        magnitude = payload.get("total_pct") or 0.0
        try:
            net_change_pct = -abs(float(magnitude))
        except (TypeError, ValueError):
            net_change_pct = 0.0
        return {
            "net_change_pct": net_change_pct,
            "direction": "decrease",
            "count": payload.get("count", 0),
            "latest_date": payload.get("latest_date"),
            "lookback_days": payload.get("lookback_days"),
            "_from_legacy": "L9.event.major_holder_decrease",
        }

    def _signal_to_insider_sell(payload: dict, _legacy_row: tuple) -> dict:
        """Aggregate signal → spec dp_id with signed net_change_pct (sign
        already present in legacy ``net_change_pct``: + IN, - DE)."""

        net = payload.get("net_change_pct", 0.0)
        try:
            net_change_pct = float(net) if net is not None else 0.0
        except (TypeError, ValueError):
            net_change_pct = 0.0
        return {
            "net_change_pct": net_change_pct,
            "direction": "aggregate",
            "count_90d": payload.get("count_90d", 0),
            "increases": payload.get("increases", 0),
            "decreases": payload.get("decreases", 0),
            "latest_ann_date": payload.get("latest_ann_date"),
            "lookback_days": payload.get("lookback_days"),
            "_from_legacy": "L9.event.holder_trade_signal",
        }

    n = 0
    n += _alias_emit(rows, "L9.event.major_holder_increase",
                     "L8.gov.insider_sell", _increase_to_insider_sell)
    n += _alias_emit(rows, "L9.event.major_holder_decrease",
                     "L8.gov.insider_sell", _decrease_to_insider_sell)
    n += _alias_emit(rows, "L9.event.holder_trade_signal",
                     "L8.gov.insider_sell", _signal_to_insider_sell)
    n += _alias_emit(rows, "L9.capital.inst_buy_sell",
                     "L7.flow.institutional")
    n += _alias_emit(rows, "L9.company.mgmt_litigation",
                     "L8.gov.management_change")
    if n:
        log.info("[tushare] X1 spec aliases: emitted %d alias rows", n)


def _fetch_a_share_capital_events(pro, a_codes_set: set[str], now: int) -> list[tuple]:
    """L7 capital-flow events that Tushare exposes via trade-date-wide
    endpoints (one HTTP call covers all A-share constituents). Cheaper than
    per-ts_code loops — preferred whenever the API supports it."""

    rows: list[tuple] = []

    # ── 融资融券余额（per ts_code, EOD）→ L7.trade.margin_short ──
    for back in range(0, 8):
        trade_date = _previous_n_days(back)
        try:
            df = pro.margin_detail(trade_date=trade_date,
                                   fields="ts_code,trade_date,rzye,rqye,rzmre,rqmcl")
            if df is not None and len(df) > 0:
                df = df[df["ts_code"].isin(a_codes_set)]
                if len(df) > 0:
                    for rec in df.to_dict(orient="records"):
                        ts_code = rec.get("ts_code")
                        if not ts_code:
                            continue
                        rzye = _safe(rec, "rzye")  # 融资余额
                        rqye = _safe(rec, "rqye")  # 融券余额
                        rows.append((
                            ts_code, "L7.trade.margin_short",
                            json.dumps({
                                "margin_balance": float(rzye) if rzye is not None else None,
                                "short_balance": float(rqye) if rqye is not None else None,
                                "margin_buy_today": _safe(rec, "rzmre"),
                                "short_sell_today": _safe(rec, "rqmcl"),
                                "unit": "元", "trade_date": rec.get("trade_date"),
                            }, ensure_ascii=False),
                            "Known", 0.8, "tushare:margin_detail", now,
                        ))
                    log.info("[tushare] margin_detail from %s rows=%d (filtered)",
                             trade_date, len(df))
                    break
        except Exception as e:  # noqa: BLE001
            log.warning("[tushare] margin_detail %s failed: %s", trade_date, e)

    # ── 龙虎榜（机构买卖）→ L9.capital.inst_buy_sell ──
    for back in range(0, 8):
        trade_date = _previous_n_days(back)
        try:
            df = pro.top_list(trade_date=trade_date,
                              fields="ts_code,trade_date,reason,net_amount,float_values,pct_change")
            if df is not None and len(df) > 0:
                df = df[df["ts_code"].isin(a_codes_set)]
                if len(df) > 0:
                    # Group by ts_code — a stock can appear on the list with multiple reasons
                    for ts_code, group in df.groupby("ts_code"):
                        reasons = group[["reason", "net_amount", "pct_change"]].to_dict(orient="records")
                        rows.append((
                            ts_code, "L9.capital.inst_buy_sell",
                            json.dumps({
                                "on_top_list": True,
                                "entries": reasons,
                                "trade_date": trade_date,
                            }, ensure_ascii=False),
                            "Known", 0.85, "tushare:top_list", now,
                        ))
                    log.info("[tushare] top_list from %s rows=%d (filtered)",
                             trade_date, len(df))
                    break
        except Exception as e:  # noqa: BLE001
            log.warning("[tushare] top_list %s failed: %s", trade_date, e)

    # ── 大宗交易 → L7.flow.block_trade ──
    for back in range(0, 8):
        trade_date = _previous_n_days(back)
        try:
            df = pro.block_trade(trade_date=trade_date,
                                 fields="ts_code,trade_date,price,vol,amount,buyer,seller")
            if df is not None and len(df) > 0:
                df = df[df["ts_code"].isin(a_codes_set)]
                if len(df) > 0:
                    # Aggregate per ts_code — sum of amount + count of trades
                    agg = df.groupby("ts_code").agg(
                        total_amount=("amount", "sum"),
                        trade_count=("ts_code", "count"),
                    ).reset_index()
                    for rec in agg.to_dict(orient="records"):
                        ts_code = rec.get("ts_code")
                        rows.append((
                            ts_code, "L7.flow.block_trade",
                            json.dumps({
                                "total_amount": float(rec.get("total_amount") or 0),
                                "trade_count": int(rec.get("trade_count") or 0),
                                "trade_date": trade_date,
                                "unit": "万元",
                            }, ensure_ascii=False),
                            "Known", 0.8, "tushare:block_trade", now,
                        ))
                    log.info("[tushare] block_trade from %s rows=%d, aggregated to %d ts_codes",
                             trade_date, len(df), len(agg))
                    break
        except Exception as e:  # noqa: BLE001
            log.warning("[tushare] block_trade %s failed: %s", trade_date, e)

    return rows


def _fetch_a_share_financials(
    pro,
    a_codes: list[str],
    now: int,
    total_mv_by_ts_code: dict[str, float] | None = None,
) -> list[tuple]:
    """Pull latest quarterly income/balancesheet/cashflow + L9 dividend per
    A-share. Returns rows ready for upsert. Failures per-stock are skipped.

    Each company costs 4 API calls (income×1 for last 5 quarters + balance×1
    + cashflow×1 + dividend×1). 116 A股 × 4 = 464 calls. Tushare 500/min
    rate-limit handles this in ~1 min.

    Arguments:
        total_mv_by_ts_code: optional ``{ts_code: total_mv_in_万元}`` from
            the upstream daily_basic snapshot. When provided, this function
            also derives ``L6.mult.mcap_fcf`` for each stock that has a
            non-zero TTM free cashflow.
    """

    rows: list[tuple] = []
    total_mv_by_ts_code = total_mv_by_ts_code or {}
    for ts_code in a_codes:
        # ── pro.income (利润表) — latest 5 quarters for YoY growth calc ──
        try:
            df = pro.income(
                ts_code=ts_code, limit=5,
                fields=("ts_code,end_date,total_revenue,operate_profit,"
                        "n_income,basic_eps,oper_cost,sell_exp,admin_exp,rd_exp"),
            )
            if df is not None and len(df) > 0:
                records = df.to_dict(orient="records")
                # Sort by end_date desc (Tushare returns latest first usually,
                # but defensively sort)
                records.sort(key=lambda r: r.get("end_date") or "", reverse=True)
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

                if rev is not None:
                    rows.append((
                        ts_code, "L5.is.revenue",
                        json.dumps({"scalar": float(rev), "unit": "元",
                                    "period": period}, ensure_ascii=False),
                        "Known", 0.85, "tushare:income", now,
                    ))
                if rev is not None and oper_cost is not None:
                    gross = rev - oper_cost
                    rows.append((
                        ts_code, "L5.is.gross_profit",
                        json.dumps({"scalar": float(gross), "unit": "元",
                                    "period": period}, ensure_ascii=False),
                        "Known", 0.8, "tushare:income.derived", now,
                    ))
                    rows.append((
                        ts_code, "L5.is.gross_margin",
                        json.dumps({"scalar": gross / rev if rev else None,
                                    "unit": "ratio", "period": period},
                                   ensure_ascii=False),
                        "Known", 0.8, "tushare:income.derived", now,
                    ))
                if op_profit is not None:
                    rows.append((
                        ts_code, "L5.is.operating_profit",
                        json.dumps({"scalar": float(op_profit), "unit": "元",
                                    "period": period}, ensure_ascii=False),
                        "Known", 0.85, "tushare:income", now,
                    ))
                if net_profit is not None:
                    rows.append((
                        ts_code, "L5.is.net_profit",
                        json.dumps({"scalar": float(net_profit), "unit": "元",
                                    "period": period}, ensure_ascii=False),
                        "Known", 0.85, "tushare:income", now,
                    ))
                if eps is not None:
                    rows.append((
                        ts_code, "L5.is.eps",
                        json.dumps({"scalar": float(eps), "unit": "元/股",
                                    "period": period}, ensure_ascii=False),
                        "Known", 0.85, "tushare:income", now,
                    ))
                if rev and (op_profit is not None or net_profit is not None):
                    rows.append((
                        ts_code, "L5.is.margins",
                        json.dumps({
                            "operating": op_profit / rev if op_profit is not None else None,
                            "net": net_profit / rev if net_profit is not None else None,
                            "period": period,
                        }, ensure_ascii=False),
                        "Known", 0.8, "tushare:income.derived", now,
                    ))
                # L5.is.sga_rd — 三费（销售+管理+研发）
                if sell_exp or admin_exp or rd_exp:
                    rows.append((
                        ts_code, "L5.is.sga_rd",
                        json.dumps({
                            "sga_total": float(sell_exp + admin_exp),
                            "sell_exp": float(sell_exp),
                            "admin_exp": float(admin_exp),
                            "rd_exp": float(rd_exp),
                            "sga_rd_ratio_revenue": ((sell_exp + admin_exp + rd_exp) / rev) if rev else None,
                            "unit": "元", "period": period,
                        }, ensure_ascii=False),
                        "Known", 0.85, "tushare:income", now,
                    ))
                # L5.is.revenue_growth — YoY = current vs ~4 periods ago
                if rev is not None and len(records) >= 4:
                    yoy_rec = records[3]  # 4 quarters back (approx YoY)
                    yoy_rev = _safe(yoy_rec, "total_revenue")
                    if yoy_rev and yoy_rev != 0:
                        yoy_pct = (rev - yoy_rev) / yoy_rev
                        # QoQ from previous quarter (records[1])
                        prev_rev = _safe(records[1], "total_revenue") if len(records) > 1 else None
                        qoq_pct = ((rev - prev_rev) / prev_rev) if prev_rev else None
                        rows.append((
                            ts_code, "L5.is.revenue_growth",
                            json.dumps({
                                "yoy_pct": yoy_pct,
                                "qoq_pct": qoq_pct,
                                "current_period": period,
                                "yoy_compare_period": yoy_rec.get("end_date"),
                            }, ensure_ascii=False),
                            "Known", 0.8, "tushare:income.derived", now,
                        ))
        except Exception as e:  # noqa: BLE001
            log.warning("[tushare] income %s failed: %s", ts_code, e)

        # ── pro.cashflow (现金流量表) — Phase B.7 bug fix + TTM FCF ──
        # IMPORTANT: Tushare returns multiple update records per (end_date)
        # (``update_flag='0'`` = original filing, ``update_flag='1'`` = updated
        # filing). When the API order returns the '0' record first, the old
        # ``limit=1`` path picked it up — and the original filing typically
        # has ``free_cashflow=NaN`` even though the updated one carries the
        # real value. Bug observed live on 000063.SZ; 603993.SH happened to
        # round-trip the updated row first by coincidence.
        #
        # Fix: pull ``limit=8`` (covers ~5 quarters with duplicates), dedup
        # by ``end_date`` preferring ``update_flag='1'``, then use the
        # latest end_date as "current" and sum the last 4 unique quarters
        # for TTM FCF.
        try:
            df = pro.cashflow(
                ts_code=ts_code, limit=8,
                fields=("ts_code,end_date,update_flag,n_cashflow_act,"
                        "n_cashflow_inv_act,n_cash_flows_fnc_act,free_cashflow,"
                        "c_pay_acq_const_fiolta,c_pay_dist_dpcp_int_exp,"
                        "c_pay_acq_treasury_stock"),
            )
            if df is not None and len(df) > 0:
                # Dedup per (end_date): pick the record with non-null
                # free_cashflow, falling back to update_flag='1' when both
                # rows are NaN; final fallback is the first occurrence.
                by_period: dict[str, dict] = {}
                for rec in df.to_dict(orient="records"):
                    ed = rec.get("end_date")
                    if not ed:
                        continue
                    prior = by_period.get(ed)
                    if prior is None:
                        by_period[ed] = rec
                        continue
                    prior_fcf = _safe(prior, "free_cashflow")
                    cur_fcf = _safe(rec, "free_cashflow")
                    prior_flag = (prior.get("update_flag") or "")
                    cur_flag = (rec.get("update_flag") or "")
                    # Prefer the row whose free_cashflow is non-null;
                    # if both, prefer update_flag='1'.
                    if cur_fcf is not None and prior_fcf is None:
                        by_period[ed] = rec
                    elif (prior_fcf is None and cur_fcf is None
                          and cur_flag == "1" and prior_flag != "1"):
                        by_period[ed] = rec
                    elif (cur_fcf is not None and prior_fcf is not None
                          and cur_flag == "1" and prior_flag != "1"):
                        by_period[ed] = rec

                # Order periods by end_date desc — latest reporting period first.
                periods_desc = sorted(by_period.keys(), reverse=True)
                if periods_desc:
                    period = periods_desc[0]
                    rec = by_period[period]
                    ocf = _safe(rec, "n_cashflow_act")
                    fcf = _safe(rec, "free_cashflow")
                    capex = _safe(rec, "c_pay_acq_const_fiolta")
                    icf = _safe(rec, "n_cashflow_inv_act")
                    fncf = _safe(rec, "n_cash_flows_fnc_act")
                    div_paid = _safe(rec, "c_pay_dist_dpcp_int_exp")
                    buyback = _safe(rec, "c_pay_acq_treasury_stock")

                    for dp_id, val in (("L5.cf.ocf", ocf), ("L5.cf.fcf", fcf),
                                        ("L5.cf.capex", capex)):
                        if val is None:
                            continue
                        rows.append((
                            ts_code, dp_id,
                            json.dumps({"scalar": float(val), "unit": "元",
                                        "period": period}, ensure_ascii=False),
                            "Known", 0.85, "tushare:cashflow", now,
                        ))
                    if icf is not None or fncf is not None:
                        rows.append((
                            ts_code, "L5.cf.icf_fcf",
                            json.dumps({
                                "investing_cf": float(icf) if icf is not None else None,
                                "financing_cf": float(fncf) if fncf is not None else None,
                                "unit": "元", "period": period,
                            }, ensure_ascii=False),
                            "Known", 0.85, "tushare:cashflow", now,
                        ))
                    if div_paid is not None or buyback is not None:
                        rows.append((
                            ts_code, "L5.cf.buyback_dividend",
                            json.dumps({
                                "dividend_paid": float(div_paid) if div_paid is not None else None,
                                "buyback_paid": float(buyback) if buyback is not None else None,
                                "unit": "元", "period": period,
                            }, ensure_ascii=False),
                            "Known", 0.85, "tushare:cashflow", now,
                        ))

                    # ── L6.mult.mcap_fcf — derive market-cap / TTM FCF ──
                    # Tushare cashflow rows are cumulative YTD per end_date.
                    # TTM FCF approximation:
                    #   • if latest end_date is an annual (1231): use as TTM
                    #   • else: latest_YTD + prior_year_full - prior_year_same_QQ_YTD
                    #
                    # When we don't have all three reference periods we fall
                    # back to the latest single-period value (still better
                    # than nothing) and flag the payload accordingly.
                    fcf_ttm = _compute_ttm_fcf(by_period, periods_desc)
                    mv_wanyuan = total_mv_by_ts_code.get(ts_code)
                    if (fcf_ttm is not None and fcf_ttm != 0
                            and mv_wanyuan is not None):
                        # Convert mv to 元 (Tushare ships 万元) so units match
                        # the cashflow's 元-scale FCF.
                        mcap_yuan = float(mv_wanyuan) * 10_000.0
                        try:
                            ratio = mcap_yuan / float(fcf_ttm)
                        except (TypeError, ValueError, ZeroDivisionError):
                            ratio = None
                        if ratio is not None:
                            rows.append((
                                ts_code, "L6.mult.mcap_fcf",
                                json.dumps({
                                    "scalar": ratio,
                                    "unit": "ratio",
                                    "ttm": True,
                                    "fcf_period_end": period,
                                    "fcf_ttm_cny": float(fcf_ttm),
                                    "mcap_cny": mcap_yuan,
                                }, ensure_ascii=False),
                                "Known", 0.7, "tushare:daily_basic+cashflow", now,
                            ))
        except Exception as e:  # noqa: BLE001
            log.warning("[tushare] cashflow %s failed: %s", ts_code, e)

        # ── pro.balancesheet (资产负债表) — cash + debt + inventory + AR/AP + goodwill ──
        try:
            df = pro.balancesheet(
                ts_code=ts_code, limit=1,
                fields=("ts_code,end_date,money_cap,total_liab,total_assets,"
                        "lt_borr,st_borr,inventories,accounts_receiv,accounts_pay,"
                        "goodwill,fix_assets"),
            )
            if df is not None and len(df) > 0:
                rec = df.to_dict(orient="records")[0]
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

                if cash is not None or debt:
                    rows.append((
                        ts_code, "L5.bs.cash_debt",
                        json.dumps({
                            "cash": cash, "debt": debt,
                            "net": (cash or 0) - debt, "period": period,
                        }, ensure_ascii=False),
                        "Known", 0.85, "tushare:balancesheet", now,
                    ))
                if total_assets and total_liab is not None:
                    rows.append((
                        ts_code, "L5.bs.leverage",
                        json.dumps({
                            "leverage_ratio": total_liab / total_assets,
                            "period": period,
                        }, ensure_ascii=False),
                        "Known", 0.85, "tushare:balancesheet.derived", now,
                    ))
                if inventory is not None:
                    rows.append((
                        ts_code, "L5.bs.inventory",
                        json.dumps({
                            "scalar": float(inventory),
                            "inventory_to_assets": (inventory / total_assets) if total_assets else None,
                            "unit": "元", "period": period,
                        }, ensure_ascii=False),
                        "Known", 0.85, "tushare:balancesheet", now,
                    ))
                if accounts_receiv is not None or accounts_pay is not None:
                    rows.append((
                        ts_code, "L5.bs.ar_ap",
                        json.dumps({
                            "accounts_receivable": float(accounts_receiv) if accounts_receiv is not None else None,
                            "accounts_payable": float(accounts_pay) if accounts_pay is not None else None,
                            "net_working_capital_change_proxy": (
                                (accounts_receiv or 0) - (accounts_pay or 0)
                            ),
                            "unit": "元", "period": period,
                        }, ensure_ascii=False),
                        "Known", 0.85, "tushare:balancesheet", now,
                    ))
                if goodwill is not None or fix_assets is not None:
                    rows.append((
                        ts_code, "L5.bs.goodwill_ppe",
                        json.dumps({
                            "goodwill": float(goodwill) if goodwill is not None else None,
                            "fix_assets_ppe": float(fix_assets) if fix_assets is not None else None,
                            "goodwill_to_assets": (goodwill / total_assets) if (goodwill is not None and total_assets) else None,
                            "unit": "元", "period": period,
                        }, ensure_ascii=False),
                        "Known", 0.85, "tushare:balancesheet", now,
                    ))
        except Exception as e:  # noqa: BLE001
            log.warning("[tushare] balancesheet %s failed: %s", ts_code, e)

        # ── pro.dividend (分红送股事件) → L9.company.buyback_dividend ──
        try:
            df = pro.dividend(ts_code=ts_code, fields="ts_code,ann_date,div_proc,cash_div,pay_date,record_date,stk_div")
            if df is not None and len(df) > 0:
                # Most recent dividend announcement
                df_sorted = df.sort_values("ann_date", ascending=False)
                rec = df_sorted.to_dict(orient="records")[0]
                rows.append((
                    ts_code, "L9.company.buyback_dividend",
                    json.dumps({
                        "latest_ann_date": rec.get("ann_date"),
                        "div_proc": rec.get("div_proc"),
                        "cash_div_per_share": _safe(rec, "cash_div"),
                        "stk_div_per_share": _safe(rec, "stk_div"),
                        "pay_date": rec.get("pay_date"),
                        "record_date": rec.get("record_date"),
                    }, ensure_ascii=False),
                    "Known", 0.8, "tushare:dividend", now,
                ))
        except Exception as e:  # noqa: BLE001
            log.warning("[tushare] dividend %s failed: %s", ts_code, e)

    return rows


# ---------------------------------------------------------------------------
# L5.fina.* — fina_indicator deep financial metrics (Phase B.4)
# ---------------------------------------------------------------------------


# Mapping: Tushare fina_indicator column → (mvp20 dp_id, unit semantic)
# Unit semantics:
#   "ratio_pct" — Tushare returns the value as a percentage number
#                 (e.g. roe=24.72 means 24.72%, not 0.2472).
#   "ratio"    — Plain ratio in [0..N] (e.g. assets_turn=0.48 means turns/period).
#   "CNY"      — Currency amount (元) — bare scalar in 元.
#   "CNY_per_share" — 元 per share (eps, bps, cfps).
_FINA_FIELD_MAP: tuple[tuple[str, str, str], ...] = (
    # (tushare_column, dp_id, unit)
    ("roe",                "L5.fina.roe",              "ratio_pct"),
    ("roa",                "L5.fina.roa",              "ratio_pct"),
    ("netprofit_margin",   "L5.fina.net_margin",       "ratio_pct"),
    ("grossprofit_margin", "L5.fina.gross_margin",     "ratio_pct"),
    ("debt_to_assets",     "L5.fina.debt_ratio",       "ratio_pct"),
    ("assets_turn",        "L5.fina.asset_turnover",   "ratio"),
    ("q_sales_yoy",        "L5.fina.revenue_yoy_q",    "ratio_pct"),
    # q_profit_yoy isn't a direct Tushare column — closest is dt_netprofit_yoy
    # (累计diluted-净利YoY); see docs/data_sources mapping notes.
    ("dt_netprofit_yoy",   "L5.fina.profit_yoy_q",     "ratio_pct"),
    # ocf_quality is "经营现金流/营收"; Tushare exposes the single-quarter
    # version (q_ocf_to_sales) but not a cumulative ocf_to_or in this dataset.
    ("q_ocf_to_sales",     "L5.fina.ocf_quality",      "ratio_pct"),
    ("working_capital",    "L5.fina.working_capital",  "CNY"),
    ("bps",                "L5.fina.bps",              "CNY_per_share"),
    ("eps",                "L5.fina.eps",              "CNY_per_share"),
    ("cfps",               "L5.fina.cfps",             "CNY_per_share"),
    ("or_yoy",             "L5.fina.revenue_yoy",      "ratio_pct"),
    ("tr_yoy",             "L5.fina.total_revenue_yoy","ratio_pct"),
    ("netprofit_yoy",      "L5.fina.net_profit_yoy",   "ratio_pct"),
)

_FINA_FIELDS_CSV = "ts_code,end_date,ann_date," + ",".join(
    col for col, _, _ in _FINA_FIELD_MAP
)


def fetch_fina_indicator_batch(
    pro,
    a_codes: list[str],
    period: str | None = None,
) -> list[tuple]:
    """Top-level helper exposed for tests and direct invocation.
    Delegates to ``_fetch_a_share_fina_indicator``."""

    return _fetch_a_share_fina_indicator(pro, a_codes, int(time.time()), period=period)


def _fetch_a_share_fina_indicator(
    pro,
    a_codes: list[str],
    now: int,
    period: str | None = None,
) -> list[tuple]:
    """Pull latest quarterly fina_indicator per A-share ts_code.

    Tushare ``fina_indicator`` only accepts a single ``ts_code`` per call
    (no comma-separated batch), so we loop with a ~0.13s sleep to stay
    well under the 500-call/min limit (≈7.6 RPS within this sub-batch;
    116 stocks ≈ 15 s wall clock).

    For each stock we pull the most recent 5 quarters (ordered desc by
    ``end_date``), pick the latest row as the current value, and emit
    one row per mapped Tushare column → mvp20 dp_id. Tushare values that
    are None / NaN are skipped so downstream defaults to ``Unknown``.

    Arguments:
        pro: ``tushare.pro_api()`` client.
        a_codes: A-share ts_codes (already filtered upstream).
        now: epoch seconds to stamp ``updated_at``.
        period: optional ``YYYYMMDD`` end_date filter. When None, the
            latest available quarter is used.

    Returns: list of upsert tuples ready for ``upsert_realtime``.
    """

    rows: list[tuple] = []
    sleep_s = 0.13  # ≈7.6 RPS → 116 stocks ≈ 15 s
    success = 0
    skipped = 0
    for ts_code in a_codes:
        try:
            kwargs = dict(ts_code=ts_code, fields=_FINA_FIELDS_CSV)
            if period:
                kwargs["period"] = period
            df = pro.fina_indicator(**kwargs)
        except Exception as e:  # noqa: BLE001
            log.warning("[tushare] fina_indicator %s failed: %s", ts_code, e)
            skipped += 1
            time.sleep(sleep_s)
            continue

        if df is None or len(df) == 0:
            skipped += 1
            time.sleep(sleep_s)
            continue

        # Sort latest-first by end_date (Tushare returns latest first, but
        # defensively re-sort because a re-statement can flip ordering).
        records = df.to_dict(orient="records")
        records.sort(key=lambda r: r.get("end_date") or "", reverse=True)
        latest = records[0]
        end_date = latest.get("end_date")
        if not end_date:
            skipped += 1
            time.sleep(sleep_s)
            continue

        for tushare_col, dp_id, unit in _FINA_FIELD_MAP:
            v = _safe(latest, tushare_col)
            if v is None:
                continue
            try:
                v_f = float(v)
            except (TypeError, ValueError):
                continue
            value_payload = {
                "value": v_f,
                "period": str(end_date),
                "currency": "CNY",
                "unit": unit,
            }
            rows.append((
                ts_code, dp_id,
                json.dumps(value_payload, ensure_ascii=False),
                "Known", 0.85, "tushare:fina_indicator", now,
            ))
        success += 1
        time.sleep(sleep_s)

    log.info("[tushare] fina_indicator: %d ok / %d skipped → %d dp_id rows",
             success, skipped, len(rows))
    return rows


# ---------------------------------------------------------------------------
# L9.event.holder_trade_* — stk_holdertrade major-shareholder activity (Phase B.6a)
# ---------------------------------------------------------------------------


def fetch_holder_trade_batch(
    pro,
    a_codes: list[str],
    lookback_days: int = 90,
) -> list[tuple]:
    """Top-level helper exposed for tests and direct invocation.
    Delegates to ``_fetch_a_share_holder_trade``."""

    return _fetch_a_share_holder_trade(pro, a_codes, int(time.time()),
                                       lookback_days=lookback_days)


def _fetch_a_share_holder_trade(
    pro,
    a_codes: list[str],
    now: int,
    lookback_days: int = 90,
) -> list[tuple]:
    """Pull recent (last ~90 days) major-shareholder buy/sell records per
    A-share ts_code from Tushare ``stk_holdertrade`` and emit three L9 dp_ids:

    * ``L9.event.holder_trade_signal`` — full 90-day aggregate payload
      (count_90d / net_change_pct / top-5 actions / increases / decreases).
    * ``L9.event.major_holder_increase`` — increases-only sub-aggregate
      (count, total_pct, latest_date, top). Emitted as ``Inactive`` if no
      IN record was returned in the lookback window.
    * ``L9.event.major_holder_decrease`` — decreases-only sub-aggregate.
      Same shape; ``Inactive`` when no DE record in window.

    Tushare ``stk_holdertrade`` accepts a single ``ts_code`` per call (no
    comma-separated batch) so we loop with a ~0.13s sleep to stay under
    500 RPM. If the endpoint isn't permissioned on the active token
    (insufficient credit score) we silently skip — every emitted row is
    optional and the collector cycle must not fail.

    Arguments:
        pro: ``tushare.pro_api()`` client.
        a_codes: A-share ts_codes (already filtered upstream).
        now: epoch seconds to stamp ``updated_at``.
        lookback_days: window (default 90) for ann_date filter.

    Returns: list of upsert tuples ready for ``upsert_realtime``.
    """

    rows: list[tuple] = []
    sleep_s = 0.13  # ~7.6 RPS — under 500/min headroom even after fina_indicator
    end_date = _today_yyyymmdd()
    start_date = _previous_n_days(lookback_days)

    permission_errors = 0
    success = 0
    active = 0  # at least one record in window
    inactive = 0  # node available, no record (Inactive status)
    for ts_code in a_codes:
        try:
            df = pro.stk_holdertrade(
                ts_code=ts_code,
                start_date=start_date,
                end_date=end_date,
            )
        except Exception as e:  # noqa: BLE001
            # Tushare returns "权限不足" / 积分不足 errors as exceptions.
            # If we see one of these, the entire dataset is unavailable —
            # short-circuit the loop rather than spamming logs for 116 codes.
            msg = str(e)
            if any(k in msg for k in ("权限", "积分", "permission", "credit",
                                      "doc_id=175")):
                permission_errors += 1
                if permission_errors <= 1:
                    log.warning(
                        "[tushare] stk_holdertrade permission issue (%s); "
                        "skipping holder-trade injection for this cycle: %s",
                        ts_code, e,
                    )
                if permission_errors >= 3:
                    log.warning(
                        "[tushare] stk_holdertrade aborted after %d permission "
                        "errors — endpoint not available on this token",
                        permission_errors,
                    )
                    break
                time.sleep(sleep_s)
                continue
            log.warning("[tushare] stk_holdertrade %s failed: %s", ts_code, e)
            time.sleep(sleep_s)
            continue

        success += 1
        time.sleep(sleep_s)

        # Build per-stock rows even when df is empty: emit Inactive markers
        # for the increase/decrease dp_ids so the frontend can distinguish
        # "no event in window" from "field never injected".
        records: list[dict]
        if df is None or len(df) == 0:
            records = []
        else:
            records = df.to_dict(orient="records")
            # Latest first by ann_date for stable ordering of top-5
            records.sort(key=lambda r: r.get("ann_date") or "", reverse=True)

        increases = [r for r in records if (r.get("in_de") or "").upper() == "IN"]
        decreases = [r for r in records if (r.get("in_de") or "").upper() == "DE"]

        def _action_summary(rec: dict) -> dict:
            return {
                "holder": rec.get("holder_name"),
                "type": rec.get("holder_type"),       # G/P/C 国/人/法
                "action": rec.get("in_de"),           # IN / DE
                "change_vol": _safe(rec, "change_vol"),
                "ratio_pct": _safe(rec, "change_ratio"),
                "after_ratio_pct": _safe(rec, "after_ratio"),
                "avg_price": _safe(rec, "avg_price"),
                "ann_date": rec.get("ann_date"),
                "begin_date": rec.get("begin_date"),
                "close_date": rec.get("close_date"),
            }

        # Signed sum of change_ratio (Tushare reports magnitude; sign by in_de)
        def _signed_ratio(rec: dict) -> float:
            r = _safe(rec, "change_ratio")
            try:
                rf = float(r) if r is not None else 0.0
            except (TypeError, ValueError):
                rf = 0.0
            if (rec.get("in_de") or "").upper() == "DE":
                rf = -rf
            return rf

        net_change_pct = sum(_signed_ratio(r) for r in records) if records else 0.0
        latest_ann = records[0].get("ann_date") if records else None

        # ── L9.event.holder_trade_signal — full aggregate ──
        if records:
            active += 1
            signal_payload = {
                "count_90d": len(records),
                "latest_ann_date": latest_ann,
                "net_change_pct": net_change_pct,
                "increases": len(increases),
                "decreases": len(decreases),
                "actions": [_action_summary(r) for r in records[:5]],
                "lookback_days": lookback_days,
            }
            rows.append((
                ts_code, "L9.event.holder_trade_signal",
                json.dumps(signal_payload, ensure_ascii=False),
                "Known", 0.85, "tushare:stk_holdertrade", now,
            ))
        else:
            inactive += 1
            rows.append((
                ts_code, "L9.event.holder_trade_signal",
                json.dumps({
                    "count_90d": 0,
                    "lookback_days": lookback_days,
                    "reason": "no holder-trade records in window",
                }, ensure_ascii=False),
                "Inactive", 0.85, "tushare:stk_holdertrade", now,
            ))

        # ── L9.event.major_holder_increase — IN-only sub-aggregate ──
        if increases:
            total_inc_pct = sum(
                float(_safe(r, "change_ratio") or 0) for r in increases
            )
            rows.append((
                ts_code, "L9.event.major_holder_increase",
                json.dumps({
                    "count": len(increases),
                    "total_pct": total_inc_pct,
                    "latest_date": increases[0].get("ann_date"),
                    "top": [_action_summary(r) for r in increases[:5]],
                    "lookback_days": lookback_days,
                }, ensure_ascii=False),
                "Known", 0.85, "tushare:stk_holdertrade", now,
            ))
        else:
            rows.append((
                ts_code, "L9.event.major_holder_increase",
                json.dumps({
                    "count": 0,
                    "lookback_days": lookback_days,
                }, ensure_ascii=False),
                "Inactive", 0.85, "tushare:stk_holdertrade", now,
            ))

        # ── L9.event.major_holder_decrease — DE-only sub-aggregate ──
        if decreases:
            total_dec_pct = sum(
                float(_safe(r, "change_ratio") or 0) for r in decreases
            )
            rows.append((
                ts_code, "L9.event.major_holder_decrease",
                json.dumps({
                    "count": len(decreases),
                    "total_pct": total_dec_pct,
                    "latest_date": decreases[0].get("ann_date"),
                    "top": [_action_summary(r) for r in decreases[:5]],
                    "lookback_days": lookback_days,
                }, ensure_ascii=False),
                "Known", 0.85, "tushare:stk_holdertrade", now,
            ))
        else:
            rows.append((
                ts_code, "L9.event.major_holder_decrease",
                json.dumps({
                    "count": 0,
                    "lookback_days": lookback_days,
                }, ensure_ascii=False),
                "Inactive", 0.85, "tushare:stk_holdertrade", now,
            ))

    log.info(
        "[tushare] stk_holdertrade: %d calls ok, %d permission-skipped, "
        "%d active / %d inactive → %d dp_id rows",
        success, permission_errors, active, inactive, len(rows),
    )
    return rows


# ---------------------------------------------------------------------------
# L9.company.earnings_guidance — forecast (业绩预告) per A-share (Phase B.7)
# ---------------------------------------------------------------------------


def fetch_forecast_batch(
    pro,
    a_codes: list[str],
) -> list[tuple]:
    """Top-level helper exposed for tests and direct invocation.
    Delegates to ``_fetch_a_share_forecast``."""

    return _fetch_a_share_forecast(pro, a_codes, int(time.time()))


def _fetch_a_share_forecast(
    pro,
    a_codes: list[str],
    now: int,
) -> list[tuple]:
    """Pull latest earnings forecast (业绩预告) per A-share via Tushare
    ``forecast`` and emit ``L9.company.earnings_guidance``.

    Tushare ``forecast`` accepts a single ``ts_code`` per call; we throttle
    at ~0.13s sleep between calls to stay under 500 RPM. The endpoint
    returns 0+ rows per stock; we pick the most recent ``end_date`` (the
    upcoming reporting period). If multiple update rows exist for the same
    ``end_date`` (``update_flag``), we keep the latest ``ann_date``.

    Output payload includes both the categorical type (预增/预减/扭亏 etc.)
    and the quantitative change-percent range so the UI can render either
    style. When a stock has no forecast in the API, we still emit an
    ``Inactive`` row so the front-end can tell "no event yet" apart from
    "field not provisioned".
    """

    rows: list[tuple] = []
    sleep_s = 0.13
    permission_errors = 0
    active = 0
    inactive = 0

    for ts_code in a_codes:
        try:
            df = pro.forecast(ts_code=ts_code)
        except Exception as e:  # noqa: BLE001
            msg = str(e)
            if any(k in msg for k in ("权限", "积分", "permission", "credit")):
                permission_errors += 1
                if permission_errors <= 1:
                    log.warning(
                        "[tushare] forecast permission issue (%s); aborting "
                        "earnings-guidance injection for this cycle: %s",
                        ts_code, e,
                    )
                if permission_errors >= 3:
                    break
                time.sleep(sleep_s)
                continue
            log.warning("[tushare] forecast %s failed: %s", ts_code, e)
            time.sleep(sleep_s)
            continue

        time.sleep(sleep_s)

        if df is None or len(df) == 0:
            inactive += 1
            rows.append((
                ts_code, "L9.company.earnings_guidance",
                json.dumps({
                    "reason": "no forecast available",
                }, ensure_ascii=False),
                "Inactive", 0.85, "tushare:forecast", now,
            ))
            continue

        records = df.to_dict(orient="records")
        # Latest end_date first; within the same end_date, latest ann_date.
        records.sort(
            key=lambda r: (r.get("end_date") or "", r.get("ann_date") or ""),
            reverse=True,
        )
        latest = records[0]

        end_date = latest.get("end_date")
        ann_date = latest.get("ann_date")
        f_type = latest.get("type")
        p_min = _safe(latest, "p_change_min")
        p_max = _safe(latest, "p_change_max")
        np_min = _safe(latest, "net_profit_min")
        np_max = _safe(latest, "net_profit_max")
        last_parent = _safe(latest, "last_parent_net")
        summary = latest.get("summary")

        active += 1
        payload = {
            "type": f_type,
            "change_pct_min": float(p_min) if p_min is not None else None,
            "change_pct_max": float(p_max) if p_max is not None else None,
            "net_profit_min": float(np_min) if np_min is not None else None,
            "net_profit_max": float(np_max) if np_max is not None else None,
            "last_parent_net": float(last_parent) if last_parent is not None else None,
            "summary": summary,
            "ann_date": ann_date,
            "period": end_date,
            "unit_net_profit": "万元",
        }
        rows.append((
            ts_code, "L9.company.earnings_guidance",
            json.dumps(payload, ensure_ascii=False),
            "Known", 0.85, "tushare:forecast", now,
        ))

    log.info(
        "[tushare] forecast: %d active / %d inactive / %d permission-skipped "
        "→ %d dp_id rows",
        active, inactive, permission_errors, len(rows),
    )
    return rows


# ---------------------------------------------------------------------------
# L9.company.mgmt_litigation — stk_managers + dividend-cf litigation signals
# per A-share (X2: declared-but-silent fix).
# ---------------------------------------------------------------------------
#
# Why was this 0-rows before X2?
#
# The dp_id was listed in SUPPORTED_DP_IDS but no emit path was ever wired
# into ``fetch_batch`` — no fetcher, no insert, no row. The collector
# silently passed. SQLite ``select count(*) from realtime_current where
# dp_id='L9.company.mgmt_litigation'`` returned 0 every cycle.
#
# What we emit now:
#
# Tushare exposes ``pro.stk_managers`` (高管变动 list) which yields recent
# 高管入职/离职/罢免 events per ts_code. We aggregate the last
# ``lookback_days`` (default 180) of records and emit one
# ``L9.company.mgmt_litigation`` row per stock — Known if at least one
# event in window, Inactive otherwise (so freshness panel sees the field
# is wired). Litigation per-se needs ``stk_litigation`` which the active
# token does not expose; the spec definition of mgmt_litigation already
# bundles management changes + litigation, so 高管变动 alone is a valid
# (if narrower) signal — better than the previous all-zero-rows state.


def fetch_mgmt_litigation_batch(
    pro,
    a_codes: list[str],
    lookback_days: int = 180,
) -> list[tuple]:
    """Top-level helper exposed for tests and direct invocation.
    Delegates to ``_fetch_a_share_mgmt_litigation``."""

    return _fetch_a_share_mgmt_litigation(pro, a_codes, int(time.time()),
                                          lookback_days=lookback_days)


def _fetch_a_share_mgmt_litigation(
    pro,
    a_codes: list[str],
    now: int,
    lookback_days: int = 180,
) -> list[tuple]:
    """Emit ``L9.company.mgmt_litigation`` per A-share.

    Strategy: aggregate the last ``lookback_days`` of ``pro.stk_managers``
    records per ts_code. Each row has ``ann_date`` (announcement),
    ``name`` / ``title`` (person + 职位), ``begin_date`` / ``end_date``
    (任期). A row with ``end_date`` set indicates the person left → 高管
    离职 event. A row with ``begin_date`` recent indicates 入职 event.

    Throttle: 0.13s sleep per call → ~7.6 RPS, keeps us under Tushare's
    500/min limit when chained with the rest of fetch_batch.

    Failure isolation: permission error short-circuits the loop (Inactive
    rows for the remaining codes); per-stock failure logs + continues.
    """

    rows: list[tuple] = []
    sleep_s = 0.13
    cutoff = _previous_n_days(lookback_days)
    permission_errors = 0
    active = 0
    inactive = 0

    for ts_code in a_codes:
        try:
            df = pro.stk_managers(ts_code=ts_code)
        except Exception as e:  # noqa: BLE001
            msg = str(e)
            if any(k in msg for k in ("权限", "积分", "permission", "credit")):
                permission_errors += 1
                if permission_errors <= 1:
                    log.warning(
                        "[tushare] stk_managers permission issue (%s); "
                        "aborting mgmt_litigation injection for this cycle: %s",
                        ts_code, e,
                    )
                if permission_errors >= 3:
                    break
                time.sleep(sleep_s)
                continue
            log.warning("[tushare] stk_managers %s failed: %s", ts_code, e)
            time.sleep(sleep_s)
            continue

        time.sleep(sleep_s)

        if df is None or len(df) == 0:
            inactive += 1
            rows.append((
                ts_code, "L9.company.mgmt_litigation",
                json.dumps({
                    "events": [],
                    "count_window": 0,
                    "lookback_days": lookback_days,
                    "reason": "no stk_managers rows",
                }, ensure_ascii=False),
                "Inactive", 0.7, "tushare:stk_managers", now,
            ))
            continue

        records = df.to_dict(orient="records") if hasattr(df, "to_dict") else list(df)
        # Filter to within window by ann_date string compare (YYYYMMDD)
        in_window = [r for r in records
                     if (r.get("ann_date") or "") >= cutoff]
        # Sort latest first
        in_window.sort(key=lambda r: r.get("ann_date") or "", reverse=True)

        def _str_or_none(v):
            """Normalise pandas NaN / None / numpy types → str | None
            so the JSON payload is always valid (no bare NaN tokens)."""

            if v is None:
                return None
            if isinstance(v, float) and v != v:  # NaN
                return None
            s = str(v).strip()
            return s or None

        events = []
        for rec in in_window[:10]:
            end_date = _str_or_none(rec.get("end_date"))
            ev_type = "高管离职" if end_date else "高管变动"
            events.append({
                "type": ev_type,
                "person": _str_or_none(rec.get("name")),
                "title": _str_or_none(rec.get("title")),
                "ann_date": _str_or_none(rec.get("ann_date")),
                "begin_date": _str_or_none(rec.get("begin_date")),
                "end_date": end_date,
            })

        if events:
            active += 1
            rows.append((
                ts_code, "L9.company.mgmt_litigation",
                json.dumps({
                    "events": events,
                    "count_window": len(in_window),
                    "lookback_days": lookback_days,
                    "latest_ann_date": in_window[0].get("ann_date"),
                }, ensure_ascii=False),
                "Known", 0.7, "tushare:stk_managers", now,
            ))
        else:
            inactive += 1
            rows.append((
                ts_code, "L9.company.mgmt_litigation",
                json.dumps({
                    "events": [],
                    "count_window": 0,
                    "lookback_days": lookback_days,
                    "reason": "no events in window",
                }, ensure_ascii=False),
                "Inactive", 0.7, "tushare:stk_managers", now,
            ))

    log.info(
        "[tushare] stk_managers/mgmt_litigation: %d permission-skipped, "
        "%d active / %d inactive → %d dp_id rows",
        permission_errors, active, inactive, len(rows),
    )
    return rows


# ---------------------------------------------------------------------------
# L5.surprise.sell_side — report_rc (券商一致预期) per A-share (Phase B.7)
# ---------------------------------------------------------------------------


def fetch_report_rc_batch(
    pro,
    a_codes: list[str],
    lookback_days: int = 90,
) -> list[tuple]:
    """Top-level helper exposed for tests and direct invocation.
    Delegates to ``_fetch_a_share_report_rc``."""

    return _fetch_a_share_report_rc(pro, a_codes, int(time.time()),
                                    lookback_days=lookback_days)


def _fetch_a_share_report_rc(
    pro,
    a_codes: list[str],
    now: int,
    lookback_days: int = 90,
) -> list[tuple]:
    """Pull sell-side analyst reports (券商研报+一致预期) per A-share via
    Tushare ``report_rc`` and emit ``L5.surprise.sell_side``.

    For each stock we aggregate the last ``lookback_days`` (default 90) of
    reports into a single dp_id row carrying:

      * ``n_reports_90d`` — total reports
      * ``rating_distribution`` — count by rating string (买入/增持/中性/...)
      * ``consensus_eps_<year>e`` — mean EPS per forward fiscal year
      * ``consensus_revenue_<year>e`` — mean revenue per forward fiscal year
      * ``consensus_eps_revision_30d_pct`` — % change of consensus EPS for
        the nearest forward year between (oldest 30-day mean) and (newest
        30-day mean). Positive = upgrade.
      * ``latest_report_date`` — date of most recent report

    Tushare ``report_rc`` accepts a single ``ts_code`` per call; throttle
    at ~0.13s sleep. Endpoint requires credit-score 2000+; if the token
    lacks permission we short-circuit after a handful of errors so the
    rest of the cycle keeps moving.

    Note: report_rc returns one row PER (report × forecast year). We group
    by year via the ``quarter`` field which Tushare formats as
    ``YYYYQ4`` (annual) — we strip the suffix to extract year.
    """

    from collections import Counter, defaultdict

    rows: list[tuple] = []
    sleep_s = 0.13
    permission_errors = 0
    active = 0
    inactive = 0

    end_date = _today_yyyymmdd()
    start_date = _previous_n_days(lookback_days)

    for ts_code in a_codes:
        try:
            df = pro.report_rc(
                ts_code=ts_code,
                start_date=start_date,
                end_date=end_date,
            )
        except Exception as e:  # noqa: BLE001
            msg = str(e)
            if any(k in msg for k in ("权限", "积分", "permission", "credit")):
                permission_errors += 1
                if permission_errors <= 1:
                    log.warning(
                        "[tushare] report_rc permission issue (%s); aborting "
                        "sell-side injection for this cycle: %s",
                        ts_code, e,
                    )
                if permission_errors >= 3:
                    break
                time.sleep(sleep_s)
                continue
            log.warning("[tushare] report_rc %s failed: %s", ts_code, e)
            time.sleep(sleep_s)
            continue

        time.sleep(sleep_s)

        if df is None or len(df) == 0:
            inactive += 1
            rows.append((
                ts_code, "L5.surprise.sell_side",
                json.dumps({
                    "n_reports_90d": 0,
                    "lookback_days": lookback_days,
                    "reason": "no sell-side report in window",
                }, ensure_ascii=False),
                "Inactive", 0.85, "tushare:report_rc", now,
            ))
            continue

        records = df.to_dict(orient="records")
        # Sort newest first by report_date
        records.sort(key=lambda r: r.get("report_date") or "", reverse=True)

        # Rating distribution — only counts unique (report_date, org_name,
        # rating) so multi-year rows for the same report don't inflate.
        seen_reports: set[tuple] = set()
        rating_counts: Counter[str] = Counter()
        unique_count = 0
        for r in records:
            key = (
                r.get("report_date"),
                r.get("org_name"),
                r.get("author_name"),
                r.get("report_title"),
            )
            if key in seen_reports:
                continue
            seen_reports.add(key)
            rating = r.get("rating") or "未评级"
            rating_counts[rating] += 1
            unique_count += 1

        # Consensus EPS / revenue per forward year
        eps_by_year: dict[int, list[float]] = defaultdict(list)
        rev_by_year: dict[int, list[float]] = defaultdict(list)
        # Track recent vs older for revision_30d_pct
        cutoff_30d = _previous_n_days(30)
        eps_recent_by_year: dict[int, list[float]] = defaultdict(list)
        eps_older_by_year: dict[int, list[float]] = defaultdict(list)

        for r in records:
            q = r.get("quarter") or ""
            # Tushare quarter format like "2026Q4" → year=2026
            year = None
            if isinstance(q, str) and len(q) >= 4 and q[:4].isdigit():
                year = int(q[:4])
            if year is None:
                continue
            eps_v = _safe(r, "eps")
            rev_v = _safe(r, "op_rt")  # 营业收入 (Tushare units = 万元)
            rd = r.get("report_date") or ""
            try:
                eps_f = float(eps_v) if eps_v is not None else None
                rev_f = float(rev_v) if rev_v is not None else None
            except (TypeError, ValueError):
                eps_f = None
                rev_f = None

            if eps_f is not None:
                eps_by_year[year].append(eps_f)
                if rd and rd >= cutoff_30d:
                    eps_recent_by_year[year].append(eps_f)
                else:
                    eps_older_by_year[year].append(eps_f)
            if rev_f is not None:
                rev_by_year[year].append(rev_f)

        payload: dict[str, object] = {
            "n_reports_90d": unique_count,
            "rating_distribution": dict(rating_counts),
            "latest_report_date": records[0].get("report_date"),
            "lookback_days": lookback_days,
        }
        # Consensus EPS / revenue keys: only emit forward years (year >=
        # current year) to keep the payload small.
        current_year = int(end_date[:4])
        for year in sorted(eps_by_year.keys()):
            if year < current_year:
                continue
            vals = eps_by_year[year]
            if vals:
                payload[f"consensus_eps_{year}e"] = sum(vals) / len(vals)
        for year in sorted(rev_by_year.keys()):
            if year < current_year:
                continue
            vals = rev_by_year[year]
            if vals:
                # rev is in 万元 — convert to 元 for consistency with other L5
                # fields.
                payload[f"consensus_revenue_{year}e"] = (sum(vals) / len(vals)) * 10_000.0

        # 30-day revision pct for the nearest forward year
        forward_years = sorted(
            y for y in eps_recent_by_year.keys() if y >= current_year
        )
        if forward_years:
            target_year = forward_years[0]
            recent_vals = eps_recent_by_year.get(target_year, [])
            older_vals = eps_older_by_year.get(target_year, [])
            if recent_vals and older_vals:
                recent_mean = sum(recent_vals) / len(recent_vals)
                older_mean = sum(older_vals) / len(older_vals)
                if older_mean and older_mean != 0:
                    payload["consensus_eps_revision_30d_pct"] = (
                        (recent_mean - older_mean) / abs(older_mean) * 100.0
                    )
                    payload["consensus_eps_revision_year"] = target_year

        active += 1
        rows.append((
            ts_code, "L5.surprise.sell_side",
            json.dumps(payload, ensure_ascii=False),
            "Known", 0.8, "tushare:report_rc", now,
        ))

    log.info(
        "[tushare] report_rc: %d active / %d inactive / %d permission-skipped "
        "→ %d dp_id rows",
        active, inactive, permission_errors, len(rows),
    )
    return rows


# ---------------------------------------------------------------------------
# L6.state.historical_percentile — PE/PB historical percentile alias
# ---------------------------------------------------------------------------


def fetch_historical_percentile_batch(
    pro,
    a_codes: list[str],
    history_days: int = 250,
) -> list[tuple]:
    """Top-level helper exposed for tests and direct invocation.
    Delegates to ``_fetch_a_share_historical_percentile``."""

    return _fetch_a_share_historical_percentile(
        pro, a_codes, int(time.time()), history_days=history_days,
    )


def _fetch_a_share_historical_percentile(
    pro,
    a_codes: list[str],
    now: int,
    history_days: int = 250,
) -> list[tuple]:
    """Emit ``L6.state.historical_percentile`` for each A-share.

    The spec calls out two similar percentile-style dp_ids:

      * ``L10.val.historical_quantile`` — emitted by ``mvp20/derive.py``
        with PE/PB percentiles over a 90-day window.
      * ``L6.state.historical_percentile`` — same semantic, distinct dp_id.

    Editing derive.py to dual-emit is owned by a different upstream PR, so
    we cover the spec by independently computing this dp_id from
    ``daily_basic`` history. We use a ~1-year (250 trading day) window
    here, mirroring the convention used by chip-distribution endpoints.

    Per-stock daily_basic call costs ~1 RPC each; throttle to 0.13s sleep
    so the 116-stock window adds ~15s wall time after the prior bursts.
    Failure modes (permission, malformed data) are downgraded to log
    warnings — never fail the cycle.
    """

    rows: list[tuple] = []
    sleep_s = 0.13
    permission_errors = 0
    end = _today_yyyymmdd()
    start = _previous_n_days(history_days + 30)  # +30d buffer for non-trading days

    for ts_code in a_codes:
        try:
            df = pro.daily_basic(
                ts_code=ts_code, start_date=start, end_date=end,
                fields="ts_code,trade_date,pe_ttm,pb",
            )
        except Exception as e:  # noqa: BLE001
            msg = str(e)
            if any(k in msg for k in ("权限", "积分", "permission", "credit")):
                permission_errors += 1
                if permission_errors >= 3:
                    break
                time.sleep(sleep_s)
                continue
            log.warning(
                "[tushare] historical_percentile %s failed: %s", ts_code, e,
            )
            time.sleep(sleep_s)
            continue

        time.sleep(sleep_s)

        if df is None or len(df) == 0:
            continue

        # Tushare returns latest first; defensively sort newest first.
        df = df.sort_values("trade_date", ascending=False)
        pe_series = [float(x) for x in df["pe_ttm"].dropna().tolist() if x and x > 0]
        pb_series = [float(x) for x in df["pb"].dropna().tolist() if x and x > 0]
        if not pe_series and not pb_series:
            continue

        current_pe = pe_series[0] if pe_series else None
        current_pb = pb_series[0] if pb_series else None

        payload: dict[str, object] = {
            "history_window_days": max(len(pe_series), len(pb_series)),
        }
        if current_pe is not None and len(pe_series) > 1:
            sorted_pe = sorted(pe_series)
            n_below = sum(1 for v in sorted_pe if v < current_pe)
            payload["pe_percentile"] = n_below / len(sorted_pe)
            payload["pe_current"] = current_pe
        if current_pb is not None and len(pb_series) > 1:
            sorted_pb = sorted(pb_series)
            n_below = sum(1 for v in sorted_pb if v < current_pb)
            payload["pb_percentile"] = n_below / len(sorted_pb)
            payload["pb_current"] = current_pb

        if "pe_percentile" not in payload and "pb_percentile" not in payload:
            continue

        rows.append((
            ts_code, "L6.state.historical_percentile",
            json.dumps(payload, ensure_ascii=False),
            "Known", 0.7, "tushare:daily_basic.history", now,
        ))

    log.info(
        "[tushare] historical_percentile: %d permission-skipped → %d dp_id rows",
        permission_errors, len(rows),
    )
    return rows


# ---------------------------------------------------------------------------
# China macro / industry beat (Phase B.8)
# ---------------------------------------------------------------------------
#
# Market-wide and industry-level fetcher. Emits a mix of L7 (state-shaped),
# L9 (event-shaped) and L10 (industry/market) dp_ids using sentinel
# ``MARKET:CN`` / ``INDUSTRY:<id>`` ts_codes. Macro updates are slow
# (monthly/daily), so the function caches results for ``_MACRO_CACHE_TTL_S``
# seconds — on cache hit it re-emits the previous rows verbatim (same
# ``updated_at``) so the storage layer's idempotent UPSERT preserves
# freshness panel semantics.
#
# Failure isolation: every Tushare endpoint is wrapped in its own try/except.
# A single API failing (permission error, network blip, schema drift) only
# drops that dp_id; the rest still flow.


def _active_industry_ids() -> list[str]:
    """Return industry slugs whose graph yaml is currently ``present``.

    Read at call time (not import) so test suites can fixture-override
    config without monkeypatching this module.
    """

    from pathlib import Path
    import yaml  # type: ignore

    cfg = (Path(__file__).resolve().parent.parent.parent
           / "config" / "mvp20.industries.yaml")
    if not cfg.exists():
        return []
    try:
        data = yaml.safe_load(cfg.read_text(encoding="utf-8")) or {}
    except Exception as e:  # noqa: BLE001
        log.warning("[tushare] _active_industry_ids parse failed: %s", e)
        return []
    out: list[str] = []
    for entry in data.get("industries") or []:
        if not isinstance(entry, dict):
            continue
        if entry.get("graph_status") == "present" and entry.get("id"):
            out.append(str(entry["id"]))
    return out


def _safe_num(v) -> float | None:
    """Float-coerce a Tushare cell value, treating NaN/None/'' as missing."""

    if v is None or v == "":
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if f != f:  # NaN
        return None
    return f


def _emit_pmi(pro, now: int) -> list[tuple]:
    """``L10.industry.pmi`` — single MARKET:CN row from ``pro.cn_pmi``."""

    try:
        df = pro.cn_pmi(
            fields=("month,pmi010000,pmi020100,pmi030000"),
        )
    except Exception as e:  # noqa: BLE001
        log.warning("[tushare] cn_pmi failed: %s", e)
        return []
    if df is None or len(df) == 0:
        return []
    # Tushare returns months in descending order; defensively sort.
    df = df.sort_values("month", ascending=False)
    rec = df.iloc[0].to_dict()
    manuf = _safe_num(rec.get("pmi010000"))           # 制造业 PMI
    non_manuf = _safe_num(rec.get("pmi020100"))        # 非制造业商务活动 PMI
    composite = _safe_num(rec.get("pmi030000"))        # 综合 PMI 产出指数
    payload = {
        "manufacturing_pmi": manuf,
        "non_manufacturing_pmi": non_manuf,
        "composite_pmi": composite,
        "latest_month": rec.get("month"),
    }
    return [(
        "MARKET:CN", "L10.industry.pmi",
        json.dumps(payload, ensure_ascii=False),
        "Known", 0.85, "tushare:cn_pmi", now,
    )]


def _emit_rates(pro, now: int) -> list[tuple]:
    """``L7.env.rates`` + ``L9.macro.rates`` — Shibor + LPR.

    L7 is always Known if we got any data. L9 is Known only when the latest
    LPR1Y or LPR5Y row differs from the prior month — emit ``change_bp``.
    Otherwise L9 is Inactive (no change event).
    """

    try:
        df = pro.shibor_lpr(
            fields="date,1y,5y,1w,1m,3m",
        )
    except Exception as e:  # noqa: BLE001
        log.warning("[tushare] shibor_lpr failed: %s", e)
        return []
    if df is None or len(df) == 0:
        return []
    df = df.sort_values("date", ascending=False).head(60)
    rows: list[tuple] = []
    latest = df.iloc[0].to_dict()
    lpr_1y = _safe_num(latest.get("1y"))
    lpr_5y = _safe_num(latest.get("5y"))
    shibor_1w = _safe_num(latest.get("1w"))
    shibor_1m = _safe_num(latest.get("1m"))
    shibor_3m = _safe_num(latest.get("3m"))

    # L7 — state-shaped, always Known on data presence.
    payload_state = {
        "lpr_1y_pct": lpr_1y, "lpr_5y_pct": lpr_5y,
        "shibor_1w_pct": shibor_1w, "shibor_1m_pct": shibor_1m,
        "shibor_3m_pct": shibor_3m,
        "as_of": latest.get("date"),
    }
    rows.append((
        "MARKET:CN", "L7.env.rates",
        json.dumps(payload_state, ensure_ascii=False),
        "Known", 0.85, "tushare:shibor_lpr", now,
    ))

    # L9 — event-shaped. Diff against the most recent row with a different
    # LPR1Y/LPR5Y value (LPR is published monthly, so adjacent rows in the
    # df might be the same cycle).
    prev_lpr_1y = None
    prev_lpr_5y = None
    for i in range(1, len(df)):
        rec = df.iloc[i].to_dict()
        rec_1y = _safe_num(rec.get("1y"))
        rec_5y = _safe_num(rec.get("5y"))
        if (prev_lpr_1y is None and rec_1y is not None
                and rec_1y != lpr_1y):
            prev_lpr_1y = rec_1y
        if (prev_lpr_5y is None and rec_5y is not None
                and rec_5y != lpr_5y):
            prev_lpr_5y = rec_5y
        if prev_lpr_1y is not None and prev_lpr_5y is not None:
            break

    def _bp(curr, prev):
        if curr is None or prev is None:
            return None
        return round((curr - prev) * 100, 2)  # pct → bp

    change_1y = _bp(lpr_1y, prev_lpr_1y)
    change_5y = _bp(lpr_5y, prev_lpr_5y)
    changed = (change_1y not in (None, 0)) or (change_5y not in (None, 0))
    event_payload = {
        "lpr_1y_pct": lpr_1y, "lpr_5y_pct": lpr_5y,
        "lpr_1y_change_bp": change_1y, "lpr_5y_change_bp": change_5y,
        "as_of": latest.get("date"),
    }
    rows.append((
        "MARKET:CN", "L9.macro.rates",
        json.dumps(event_payload, ensure_ascii=False),
        "Known" if changed else "Inactive", 0.8, "tushare:shibor_lpr", now,
    ))
    return rows


def _emit_money_supply(pro, now: int) -> list[tuple]:
    """``L7.env.liquidity`` + ``L9.macro.liquidity`` — cn_m M0/M1/M2."""

    try:
        df = pro.cn_m(
            fields="month,m0,m0_yoy,m1,m1_yoy,m2,m2_yoy",
        )
    except Exception as e:  # noqa: BLE001
        log.warning("[tushare] cn_m failed: %s", e)
        return []
    if df is None or len(df) == 0:
        return []
    df = df.sort_values("month", ascending=False)
    latest = df.iloc[0].to_dict()
    m1_yoy = _safe_num(latest.get("m1_yoy"))
    m2_yoy = _safe_num(latest.get("m2_yoy"))
    m2_minus_m1 = (m2_yoy - m1_yoy) if (m2_yoy is not None and m1_yoy is not None) else None

    payload_state = {
        "m2_yoy_pct": m2_yoy, "m1_yoy_pct": m1_yoy,
        "m2_minus_m1_pct": m2_minus_m1,
        "latest_month": latest.get("month"),
    }
    rows: list[tuple] = [(
        "MARKET:CN", "L7.env.liquidity",
        json.dumps(payload_state, ensure_ascii=False),
        "Known", 0.85, "tushare:cn_m", now,
    )]

    # Event: emit Known iff M2 yoy moved >= 0.3pct vs prior month.
    prev_m2_yoy = _safe_num(df.iloc[1].get("m2_yoy")) if len(df) > 1 else None
    delta_m2 = (m2_yoy - prev_m2_yoy) if (m2_yoy is not None and prev_m2_yoy is not None) else None
    significant = delta_m2 is not None and abs(delta_m2) >= 0.3
    rows.append((
        "MARKET:CN", "L9.macro.liquidity",
        json.dumps({
            "m2_yoy_pct": m2_yoy, "m2_yoy_change_pct": delta_m2,
            "m1_yoy_pct": m1_yoy, "latest_month": latest.get("month"),
        }, ensure_ascii=False),
        "Known" if significant else "Inactive", 0.8, "tushare:cn_m", now,
    ))
    return rows


def _emit_cpi_ppi(pro, now: int) -> list[tuple]:
    """``L9.macro.cpi_employment`` — cn_cpi + cn_ppi merged into one row.

    Tushare doesn't expose unemployment via free pro endpoints, so we
    bundle CPI + PPI under the spec dp_id (the *employment* sub-key stays
    None / TODO until an alternative source lands).
    """

    cpi_yoy = None
    cpi_mom = None
    cpi_month = None
    try:
        df_cpi = pro.cn_cpi(
            fields="month,nt_yoy,nt_mom",
        )
        if df_cpi is not None and len(df_cpi) > 0:
            df_cpi = df_cpi.sort_values("month", ascending=False)
            rec = df_cpi.iloc[0].to_dict()
            cpi_yoy = _safe_num(rec.get("nt_yoy"))
            cpi_mom = _safe_num(rec.get("nt_mom"))
            cpi_month = rec.get("month")
    except Exception as e:  # noqa: BLE001
        log.warning("[tushare] cn_cpi failed: %s", e)

    ppi_yoy = None
    ppi_month = None
    try:
        df_ppi = pro.cn_ppi(
            fields="month,ppi_yoy",
        )
        if df_ppi is not None and len(df_ppi) > 0:
            df_ppi = df_ppi.sort_values("month", ascending=False)
            rec = df_ppi.iloc[0].to_dict()
            ppi_yoy = _safe_num(rec.get("ppi_yoy"))
            ppi_month = rec.get("month")
    except Exception as e:  # noqa: BLE001
        log.warning("[tushare] cn_ppi failed: %s", e)

    if cpi_yoy is None and ppi_yoy is None:
        return []
    payload = {
        "cpi_yoy_pct": cpi_yoy, "cpi_mom_pct": cpi_mom,
        "ppi_yoy_pct": ppi_yoy,
        "latest_month": cpi_month or ppi_month,
        "employment_unemployment_pct": None,  # TODO: Tushare 无失业率自由接口
    }
    return [(
        "MARKET:CN", "L9.macro.cpi_employment",
        json.dumps(payload, ensure_ascii=False),
        "Known", 0.85, "tushare:cn_cpi+cn_ppi", now,
    )]


def _emit_market_pe_quantile(pro, now: int) -> list[tuple]:
    """``L10.val.historical_quantile`` — market-wide PE_ttm quantile.

    Spec asks for P10/P25/P50/P75/P90 of the cross-section of A-share
    PE_ttm on the most recent trading day. Cheap: one ``daily_basic`` call.
    """

    df = None
    for back in range(0, 8):
        trade_date = _previous_n_days(back)
        try:
            tmp = pro.daily_basic(
                trade_date=trade_date,
                fields="ts_code,trade_date,pe_ttm",
            )
            if tmp is not None and len(tmp) > 0:
                df = tmp
                latest_trade_date = trade_date
                break
        except Exception as e:  # noqa: BLE001
            log.warning("[tushare] daily_basic (macro quantile) %s failed: %s",
                        trade_date, e)
            continue
    if df is None or len(df) == 0:
        return []
    pe_series = sorted(float(x) for x in df["pe_ttm"].dropna().tolist()
                       if x is not None and x > 0)
    if len(pe_series) < 100:
        return []
    n = len(pe_series)
    def _quantile(p: float) -> float:
        idx = max(0, min(n - 1, int(p * n)))
        return pe_series[idx]
    payload = {
        "p10": _quantile(0.10),
        "p25": _quantile(0.25),
        "p50": _quantile(0.50),
        "p75": _quantile(0.75),
        "p90": _quantile(0.90),
        "sample_size": n,
        "trade_date": latest_trade_date,
        "scope": "A_share_market",
    }
    return [(
        "MARKET:CN", "L10.val.historical_quantile",
        json.dumps(payload, ensure_ascii=False),
        "Known", 0.8, "tushare:daily_basic.cross_section", now,
    )]


def _emit_industry_fund_flow(pro, now: int) -> list[tuple]:
    """``L10.industry.fund_flow`` — 同花顺行业资金流, per active industry.

    One Tushare call covers all THS industries for a given trade_date;
    we filter to the mapped slugs and emit one row per industry.
    """

    industries = _active_industry_ids()
    if not industries:
        return []

    # Map present slugs → THS name; drop unmapped (None).
    slug_by_ths: dict[str, str] = {}
    for slug in industries:
        ths = INDUSTRY_TO_THS_NAME.get(slug)
        if ths:
            slug_by_ths[ths] = slug
    if not slug_by_ths:
        return []

    df = None
    for back in range(0, 8):
        trade_date = _previous_n_days(back)
        try:
            tmp = pro.moneyflow_ind_ths(
                trade_date=trade_date,
                fields=("ts_code,industry,trade_date,close,pct_change,"
                        "net_amount,buy_amount,sell_amount,net_d5_amount"),
            )
            if tmp is not None and len(tmp) > 0:
                df = tmp
                break
        except Exception as e:  # noqa: BLE001
            log.warning("[tushare] moneyflow_ind_ths %s failed: %s",
                        trade_date, e)
            continue
    if df is None or len(df) == 0:
        return []

    rows: list[tuple] = []
    for rec in df.to_dict(orient="records"):
        ths_name = rec.get("industry")
        slug = slug_by_ths.get(ths_name)
        if not slug:
            continue
        payload = {
            "industry_ths_name": ths_name,
            "net_amount": _safe_num(rec.get("net_amount")),
            "buy_amount": _safe_num(rec.get("buy_amount")),
            "sell_amount": _safe_num(rec.get("sell_amount")),
            "net_5d_amount": _safe_num(rec.get("net_d5_amount")),
            "pct_change": _safe_num(rec.get("pct_change")),
            "unit": "亿元",
            "trade_date": rec.get("trade_date"),
        }
        rows.append((
            f"INDUSTRY:{slug}", "L10.industry.fund_flow",
            json.dumps(payload, ensure_ascii=False),
            "Known", 0.75, "tushare:moneyflow_ind_ths", now,
        ))
    return rows


def _emit_passive_northbound(pro, now: int) -> list[tuple]:
    """``L7.flow.passive_northbound`` — MARKET:CN aggregate of 沪深港通 daily
    net buy / sell. Uses ``pro.moneyflow_hsgt``.

    The existing per-stock ``L7.flow.passive_northbound`` emit in
    ``fetch_batch`` (via ``pro.hk_hold``) covers individual持仓股票. This
    function adds the **market-level** sentinel row so the spec dp_id has
    both per-stock + market-wide coverage.

    Tushare returns one row per trade_date with:
      * ``north_money`` (北向资金净流入, 万元)
      * ``south_money`` (南向资金净流入, 万元)
      * ``hgt`` (沪股通) / ``sgt`` (深股通) / ``ggt_ss`` / ``ggt_sz``
    Sign: positive = inflow into mainland (北向 buy A-share net).
    """

    try:
        df = pro.moneyflow_hsgt(
            start_date=_previous_n_days(30),
            end_date=_today_yyyymmdd(),
        )
    except Exception as e:  # noqa: BLE001
        log.warning("[tushare] moneyflow_hsgt failed: %s", e)
        return []
    if df is None or len(df) == 0:
        return []
    df = df.sort_values("trade_date", ascending=False)
    latest = df.iloc[0].to_dict()
    north_net = _safe_num(latest.get("north_money"))
    south_net = _safe_num(latest.get("south_money"))
    hgt = _safe_num(latest.get("hgt"))
    sgt = _safe_num(latest.get("sgt"))

    # 5d moving average of north_money — gives momentum context for the
    # frontend chips ("北向 5日累计 +X 亿").
    n5 = df.head(5).to_dict(orient="records")
    n5_vals = [_safe_num(r.get("north_money")) for r in n5]
    n5_clean = [v for v in n5_vals if v is not None]
    north_net_5d_ma = (sum(n5_clean) / len(n5_clean)) if n5_clean else None

    payload = {
        "north_net_amount": north_net,
        "south_net_amount": south_net,
        "hgt_net": hgt,
        "sgt_net": sgt,
        "north_net_5d_ma": north_net_5d_ma,
        "unit": "万元",
        "latest_date": latest.get("trade_date"),
        "scope": "A_share_market",
    }
    return [(
        "MARKET:CN", "L7.flow.passive_northbound",
        json.dumps(payload, ensure_ascii=False),
        "Known", 0.8, "tushare:moneyflow_hsgt", now,
    )]


def _emit_etf_inflow(pro, now: int) -> list[tuple]:
    """``L7.flow.etf_inflow`` — MARKET:CN aggregate of the top-N A-share ETFs
    by 1-day share delta (新增份额 / 净申购).

    Per-ETF inflow proxy: ``fund_share`` returns daily 流通份额 (``fd_share``)
    per ETF. We diff the latest trade_date against the prior trade_date to
    approximate the 1-day net subscription rate as a percentage of total
    shares. Positive = net 申购 = bullish inflow signal.

    Strategy:
      1. Fetch fund_basic(market='E') once → list of ETF ts_codes + names.
      2. Cap to top-20 by latest fd_share (largest ETFs dominate flow).
      3. For each, fetch fund_share(ts_code=...) and take the latest 2 rows.
      4. Aggregate into payload {top_etf_inflow: [{ts_code, name,
         share_delta_pct, share_delta}], total_share_delta, latest_date}.

    Cost: ~21 Tushare calls per cache cycle (~600s) — well within budget.
    Per-stock fan-out is intentionally NOT done (the source's scope is
    market-wide flow context, not per-ticker holdings).
    """

    try:
        df_basic = pro.fund_basic(market="E")
    except Exception as e:  # noqa: BLE001
        log.warning("[tushare] fund_basic(market=E) failed: %s", e)
        return []
    if df_basic is None or len(df_basic) == 0:
        return []
    basic_records = df_basic.to_dict(orient="records") \
        if hasattr(df_basic, "to_dict") else list(df_basic)
    # Build ts_code → name map; only keep listed (delist_date == None / NaN)
    name_by_code: dict[str, str] = {}
    for rec in basic_records:
        ts_code = rec.get("ts_code")
        if not ts_code or not ts_code.endswith((".SH", ".SZ")):
            continue
        delist = rec.get("delist_date")
        if delist and not (isinstance(delist, float) and delist != delist):
            continue  # skip delisted
        name_by_code[ts_code] = rec.get("name") or ts_code

    if not name_by_code:
        return []

    # Heuristic: take the first N (Tushare's fund_basic comes ordered by
    # something stable enough that the broader-market ETFs cluster at top).
    sample_codes = list(name_by_code.keys())[:20]
    per_etf: list[dict] = []
    latest_date: str | None = None
    total_delta_pct = 0.0
    delta_count = 0
    for ts_code in sample_codes:
        try:
            df = pro.fund_share(ts_code=ts_code)
        except Exception as e:  # noqa: BLE001
            log.warning("[tushare] fund_share %s failed: %s", ts_code, e)
            continue
        time.sleep(0.05)
        if df is None or len(df) < 2:
            continue
        recs = df.to_dict(orient="records") if hasattr(df, "to_dict") else list(df)
        # Latest first
        recs.sort(key=lambda r: r.get("trade_date") or "", reverse=True)
        latest = recs[0]
        prior = recs[1]
        cur_share = _safe_num(latest.get("fd_share"))
        prior_share = _safe_num(prior.get("fd_share"))
        if cur_share is None or prior_share is None or prior_share == 0:
            continue
        delta = cur_share - prior_share
        delta_pct = (delta / prior_share) * 100.0
        per_etf.append({
            "ts_code": ts_code,
            "name": name_by_code.get(ts_code),
            "share_delta": delta,
            "share_delta_pct": round(delta_pct, 3),
            "latest_share": cur_share,
            "trade_date": latest.get("trade_date"),
        })
        if latest_date is None:
            latest_date = latest.get("trade_date")
        total_delta_pct += delta_pct
        delta_count += 1

    if not per_etf:
        return []
    per_etf.sort(key=lambda x: abs(x["share_delta_pct"]), reverse=True)
    top10 = per_etf[:10]
    avg_delta_pct = total_delta_pct / delta_count if delta_count else 0.0

    payload = {
        "top_etf_inflow": top10,
        "etf_avg_delta_pct": round(avg_delta_pct, 3),
        "etf_sampled": delta_count,
        "latest_date": latest_date,
        "scope": "A_share_market",
        "method": "fund_share.fd_share day-over-day delta",
    }
    return [(
        "MARKET:CN", "L7.flow.etf_inflow",
        json.dumps(payload, ensure_ascii=False),
        "Known", 0.7, "tushare:fund_share", now,
    )]


def fetch_macro_china_batch(now: int) -> list[tuple]:
    """Emit market-wide & industry-level macro dp_id rows.

    Returns the standard 7-tuple shape; safe to extend an existing
    ``fetch_batch`` result list with it. Each underlying Tushare call is
    independently try/except'd: a single permission denial or schema
    drift never zeros out the rest of the batch.

    Caching: macro data updates at most daily, so we only hit Tushare
    every ``_MACRO_CACHE_TTL_S`` seconds and replay the previous rows in
    between (preserves their original ``updated_at`` so freshness panel
    still reads the true age).
    """

    cached_ts = int(_LAST_MACRO_FETCH.get("ts") or 0)
    cached_rows = _LAST_MACRO_FETCH.get("rows") or []
    if cached_ts and (now - cached_ts) < _MACRO_CACHE_TTL_S and cached_rows:
        log.debug("[tushare] macro cache hit (age=%ds, rows=%d)",
                  now - cached_ts, len(cached_rows))
        return list(cached_rows)  # shallow copy — callers may mutate

    pro = _get_pro_api()
    if pro is None:
        log.warning("[tushare] TUSHARE_TOKEN not set — skipping macro batch")
        return []

    rows: list[tuple] = []
    for label, fn in (
        ("cn_pmi",           _emit_pmi),
        ("shibor_lpr",       _emit_rates),
        ("cn_m",             _emit_money_supply),
        ("cn_cpi+cn_ppi",    _emit_cpi_ppi),
        ("market_pe_quantile", _emit_market_pe_quantile),
        ("industry_fund_flow", _emit_industry_fund_flow),
        # X2 declared-but-silent fetchers — MARKET:CN sentinel rows
        ("passive_northbound", _emit_passive_northbound),
        ("etf_inflow",       _emit_etf_inflow),
    ):
        try:
            rows.extend(fn(pro, now))
        except Exception as e:  # noqa: BLE001 — last-ditch isolation
            log.warning("[tushare] macro fetcher %s crashed: %s", label, e)

    _LAST_MACRO_FETCH["ts"] = now
    _LAST_MACRO_FETCH["rows"] = list(rows)
    log.info("[tushare] macro batch: emitted %d rows (next fetch in %ds)",
             len(rows), _MACRO_CACHE_TTL_S)
    return rows


# ---------------------------------------------------------------------------
# X3b: per-stock derived A-share fundamentals (Phase B.9)
# ---------------------------------------------------------------------------
#
# Seven dp_ids are emitted per A-share constituent:
#
#   * L4.cost.labor — labor cost as % of revenue + YoY change. Derived from
#     cashflow.c_paid_to_for_empl (cash paid to employees, cumulative YTD)
#     divided by income.total_revenue.
#   * L4.cost.raw_material — raw-material cost proxy = (oper_cost − labor
#     estimate) / revenue. Carries the stock's primary industry-mapped
#     commodity name from config/industry_to_commodity.yaml.
#   * L4.eff.turnover — DIO / DSO / DPO days from balancesheet + income.
#   * L4.eff.cycle — Cash Conversion Cycle = DIO + DSO − DPO.
#   * L8.fin.cash_ar — OCF/NI ratio + AR yoy %; triggers WARN/ERROR alerts.
#     status flips to "Inactive" when no alert fires.
#   * L8.fin.debt_pressure — interest_debt / EBITDA + debt_to_assets;
#     thresholds 2.5/4.0 → WARN/ERROR.
#   * L8.op.inventory_glut — inventory yoy% vs turnover yoy% change;
#     thresholds detect glut buildup (inventory↑ + turnover↓).
#
# Cache strategy: each Tushare endpoint (fina_indicator, balancesheet,
# cashflow, income) is wrapped in a per-stock helper that consults a 5-min
# ``_*_CACHE`` dict keyed by ts_code. The collector cycles every ~60s so
# any stock touched once in this batch will hit the cache on the next 4-5
# cycles, capping API RPS to ~one burst per 5 min per stock per endpoint.
#
# Per-fetcher try/except: any single dp_id's derivation can fail (missing
# field, schema drift) without dropping the other six.


def _cache_get(cache: dict, key: str, ttl_s: int, now: int) -> list[dict] | None:
    """Return cached records for ``key`` if within TTL, else None."""

    entry = cache.get(key)
    if entry is None:
        return None
    cached_ts, records = entry
    if now - cached_ts < ttl_s:
        return records
    return None


def _cache_put(cache: dict, key: str, records: list[dict], now: int) -> None:
    cache[key] = (now, records)


_X3B_RPC_SLEEP_S = 0.10  # ~10 RPS throttle on Tushare RPC calls


def _get_fina_indicator_records(pro, ts_code: str, now: int) -> list[dict]:
    """Return up to 8 quarters of fina_indicator records (latest first).

    Cached per-ts_code with ``_FINA_CACHE_TTL_S`` TTL. Returns ``[]`` on
    any error so callers can branch to Inactive without try/except. Sleeps
    ``_X3B_RPC_SLEEP_S`` only on cache miss (real Tushare RPC).
    """

    cached = _cache_get(_FINA_CACHE, ts_code, _FINA_CACHE_TTL_S, now)
    if cached is not None:
        return cached
    try:
        df = pro.fina_indicator(
            ts_code=ts_code,
            fields=("ts_code,end_date,ann_date,ar_turn,assets_turn,"
                    "turn_days,inv_turn,interestdebt,ebitda,debt_to_assets,"
                    "ocf_yoy,netprofit_yoy,or_yoy,netprofit_margin"),
        )
        time.sleep(_X3B_RPC_SLEEP_S)
    except Exception as e:  # noqa: BLE001
        log.warning("[tushare] X3b fina_indicator %s failed: %s", ts_code, e)
        _cache_put(_FINA_CACHE, ts_code, [], now)
        return []
    if df is None or len(df) == 0:
        _cache_put(_FINA_CACHE, ts_code, [], now)
        return []
    records = df.to_dict(orient="records")
    records.sort(key=lambda r: r.get("end_date") or "", reverse=True)
    _cache_put(_FINA_CACHE, ts_code, records, now)
    return records


def _get_balancesheet_records(pro, ts_code: str, now: int) -> list[dict]:
    """Return up to 8 quarters of balancesheet records (latest first)."""

    cached = _cache_get(_BALANCESHEET_CACHE, ts_code, _FINA_CACHE_TTL_S, now)
    if cached is not None:
        return cached
    try:
        df = pro.balancesheet(
            ts_code=ts_code, limit=8,
            fields=("ts_code,end_date,inventories,accounts_receiv,accounts_pay,"
                    "lt_borr,st_borr,bond_payable,payroll_payable,"
                    "total_assets,total_liab"),
        )
        time.sleep(_X3B_RPC_SLEEP_S)
    except Exception as e:  # noqa: BLE001
        log.warning("[tushare] X3b balancesheet %s failed: %s", ts_code, e)
        _cache_put(_BALANCESHEET_CACHE, ts_code, [], now)
        return []
    if df is None or len(df) == 0:
        _cache_put(_BALANCESHEET_CACHE, ts_code, [], now)
        return []
    records = df.to_dict(orient="records")
    records.sort(key=lambda r: r.get("end_date") or "", reverse=True)
    _cache_put(_BALANCESHEET_CACHE, ts_code, records, now)
    return records


def _get_cashflow_records(pro, ts_code: str, now: int) -> list[dict]:
    """Return up to 8 quarters of cashflow records (latest first)."""

    cached = _cache_get(_CASHFLOW_CACHE, ts_code, _FINA_CACHE_TTL_S, now)
    if cached is not None:
        return cached
    try:
        df = pro.cashflow(
            ts_code=ts_code, limit=8,
            fields=("ts_code,end_date,update_flag,n_cashflow_act,"
                    "c_paid_to_for_empl"),
        )
        time.sleep(_X3B_RPC_SLEEP_S)
    except Exception as e:  # noqa: BLE001
        log.warning("[tushare] X3b cashflow %s failed: %s", ts_code, e)
        _cache_put(_CASHFLOW_CACHE, ts_code, [], now)
        return []
    if df is None or len(df) == 0:
        _cache_put(_CASHFLOW_CACHE, ts_code, [], now)
        return []
    # Dedup per end_date preferring records with non-null n_cashflow_act +
    # update_flag='1'.
    by_period: dict[str, dict] = {}
    for rec in df.to_dict(orient="records"):
        ed = rec.get("end_date")
        if not ed:
            continue
        prior = by_period.get(ed)
        if prior is None:
            by_period[ed] = rec
            continue
        prior_ocf = _safe(prior, "n_cashflow_act")
        cur_ocf = _safe(rec, "n_cashflow_act")
        prior_flag = (prior.get("update_flag") or "")
        cur_flag = (rec.get("update_flag") or "")
        if cur_ocf is not None and prior_ocf is None:
            by_period[ed] = rec
        elif (cur_flag == "1" and prior_flag != "1"
              and cur_ocf is not None):
            by_period[ed] = rec
    records = sorted(by_period.values(),
                     key=lambda r: r.get("end_date") or "", reverse=True)
    _cache_put(_CASHFLOW_CACHE, ts_code, records, now)
    return records


def _get_income_records(pro, ts_code: str, now: int) -> list[dict]:
    """Return up to 8 quarters of income records (latest first)."""

    cached = _cache_get(_INCOME_CACHE, ts_code, _FINA_CACHE_TTL_S, now)
    if cached is not None:
        return cached
    try:
        df = pro.income(
            ts_code=ts_code, limit=8,
            fields=("ts_code,end_date,total_revenue,oper_cost,n_income"),
        )
        time.sleep(_X3B_RPC_SLEEP_S)
    except Exception as e:  # noqa: BLE001
        log.warning("[tushare] X3b income %s failed: %s", ts_code, e)
        _cache_put(_INCOME_CACHE, ts_code, [], now)
        return []
    if df is None or len(df) == 0:
        _cache_put(_INCOME_CACHE, ts_code, [], now)
        return []
    records = df.to_dict(orient="records")
    records.sort(key=lambda r: r.get("end_date") or "", reverse=True)
    _cache_put(_INCOME_CACHE, ts_code, records, now)
    return records


def _period_days(end_date: str | None) -> int:
    """Approximate cumulative days for a quarterly end_date.

    Tushare YTD-style figures (revenue, oper_cost, OCF, cash paid to
    employees) are cumulative from Jan 1 to end_date. For per-day
    normalisation (DIO/DSO/DPO) we need the actual day count. Use a
    coarse 90/180/270/360 lookup keyed on the month-day suffix; sub-day
    accuracy is irrelevant for turnover ratios.
    """

    if not end_date:
        return 360
    mmdd = str(end_date)[-4:]
    if mmdd.startswith("03"):
        return 90
    if mmdd.startswith("06"):
        return 180
    if mmdd.startswith("09"):
        return 270
    return 360


def _yoy_period(end_date: str) -> str:
    """Compute YoY comparison period: same MM-DD, prev year."""

    if not end_date or len(end_date) < 8:
        return ""
    try:
        year = int(end_date[:4])
    except ValueError:
        return ""
    return f"{year - 1}{end_date[4:]}"


def _find_record(records: list[dict], end_date: str) -> dict | None:
    for r in records:
        if r.get("end_date") == end_date:
            return r
    return None


def _industry_primary_commodity(industry_id: str | None) -> str | None:
    """Look up the first mapped commodity symbol for an industry.

    Reads ``config/industry_to_commodity.yaml`` lazily. Returns None when
    the industry is unmapped (``null`` in the YAML) or unknown.
    """

    if not industry_id:
        return None
    from pathlib import Path
    try:
        import yaml  # type: ignore
    except ImportError:
        return None
    cfg = (Path(__file__).resolve().parent.parent.parent
           / "config" / "industry_to_commodity.yaml")
    if not cfg.exists():
        return None
    try:
        data = yaml.safe_load(cfg.read_text(encoding="utf-8")) or {}
    except Exception:  # noqa: BLE001
        return None
    industries = data.get("industries") or {}
    syms = industries.get(industry_id)
    if not syms:
        return None
    clean = [str(s) for s in syms if s]
    return clean[0] if clean else None


def _derive_labor_cost(
    income_records: list[dict],
    cashflow_records: list[dict],
) -> tuple[dict, str]:
    """Compute ``L4.cost.labor`` payload + status.

    Returns ({payload}, 'Known' | 'Inactive'). Inactive when revenue or
    employee-payment is unavailable.
    """

    if not income_records or not cashflow_records:
        return {"reason": "no income/cashflow data"}, "Inactive"
    inc = income_records[0]
    cf = _find_record(cashflow_records, inc.get("end_date") or "")
    if cf is None:
        cf = cashflow_records[0]
    period = inc.get("end_date")
    rev = _safe(inc, "total_revenue")
    labor_cash = _safe(cf, "c_paid_to_for_empl")
    if rev is None or rev == 0 or labor_cash is None:
        return ({"reason": "missing revenue or employee-cash field",
                 "latest_period": period}, "Inactive")
    labor_pct = (float(labor_cash) / float(rev)) * 100.0

    # YoY: find income+cashflow at same period last year, compute prior
    # labor_pct, return yoy_pct delta in percentage points.
    yoy = _yoy_period(str(period or ""))
    labor_yoy_pct = None
    prior_inc = _find_record(income_records, yoy) if yoy else None
    prior_cf = _find_record(cashflow_records, yoy) if yoy else None
    if prior_inc and prior_cf:
        prior_rev = _safe(prior_inc, "total_revenue")
        prior_labor = _safe(prior_cf, "c_paid_to_for_empl")
        if prior_rev and prior_labor is not None and prior_rev != 0:
            prior_pct = (float(prior_labor) / float(prior_rev)) * 100.0
            labor_yoy_pct = labor_pct - prior_pct

    return ({
        "labor_cost_pct": round(labor_pct, 4),
        "labor_cost_yoy_pct": round(labor_yoy_pct, 4) if labor_yoy_pct is not None else None,
        "latest_period": period,
    }, "Known")


def _derive_raw_material(
    income_records: list[dict],
    cashflow_records: list[dict],
    primary_commodity: str | None,
) -> tuple[dict, str]:
    """Compute ``L4.cost.raw_material`` payload + status.

    raw_material_pct ≈ (oper_cost − employee-cash estimate) / revenue.
    cogs_yoy_pct = YoY of oper_cost.
    """

    if not income_records:
        return ({"reason": "no income data"}, "Inactive")
    inc = income_records[0]
    period = inc.get("end_date")
    rev = _safe(inc, "total_revenue")
    cogs = _safe(inc, "oper_cost")
    if rev is None or rev == 0 or cogs is None:
        return ({"reason": "missing revenue or oper_cost",
                 "latest_period": period}, "Inactive")
    cf = _find_record(cashflow_records, period) if cashflow_records else None
    labor_cash = _safe(cf, "c_paid_to_for_empl") if cf else None
    # Raw material = cogs - labor (best-effort). When labor unavailable,
    # raw_material reduces to cogs share — still useful but flagged.
    if labor_cash is not None:
        raw_material = float(cogs) - float(labor_cash)
    else:
        raw_material = float(cogs)
    raw_pct = (raw_material / float(rev)) * 100.0

    yoy = _yoy_period(str(period or ""))
    cogs_yoy_pct = None
    prior_inc = _find_record(income_records, yoy) if yoy else None
    if prior_inc:
        prior_cogs = _safe(prior_inc, "oper_cost")
        if prior_cogs and prior_cogs != 0:
            cogs_yoy_pct = ((float(cogs) - float(prior_cogs))
                            / float(prior_cogs)) * 100.0

    return ({
        "raw_material_cost_pct": round(raw_pct, 4),
        "cogs_yoy_pct": round(cogs_yoy_pct, 4) if cogs_yoy_pct is not None else None,
        "latest_period": period,
        "primary_commodity": primary_commodity,
        "labor_adjusted": labor_cash is not None,
    }, "Known")


def _derive_turnover(
    income_records: list[dict],
    balancesheet_records: list[dict],
) -> tuple[dict, str]:
    """Compute ``L4.eff.turnover`` payload + status.

    Returns DIO/DSO/DPO days. Formulas (cumulative YTD basis):
      DIO = inventories / (oper_cost / period_days)
      DSO = accounts_receiv / (revenue / period_days)
      DPO = accounts_pay / (oper_cost / period_days)

    Where period_days ≈ 90/180/270/360 per quarter (annualised by
    multiplying daily cogs/revenue by 365 for the implicit ratio).
    """

    if not income_records or not balancesheet_records:
        return ({"reason": "no income/balancesheet data"}, "Inactive")
    inc = income_records[0]
    period = inc.get("end_date")
    bs = _find_record(balancesheet_records, period or "") or balancesheet_records[0]
    rev = _safe(inc, "total_revenue")
    cogs = _safe(inc, "oper_cost")
    inv = _safe(bs, "inventories")
    ar = _safe(bs, "accounts_receiv")
    ap = _safe(bs, "accounts_pay")
    days = _period_days(str(period or ""))
    if not (rev and cogs and days):
        return ({"reason": "missing revenue/oper_cost", "latest_period": period},
                "Inactive")

    dio = (float(inv) / float(cogs)) * days if inv is not None and cogs else None
    dso = (float(ar) / float(rev)) * days if ar is not None and rev else None
    dpo = (float(ap) / float(cogs)) * days if ap is not None and cogs else None

    if dio is None and dso is None and dpo is None:
        return ({"reason": "no inventory/AR/AP data",
                 "latest_period": period}, "Inactive")

    return ({
        "inventory_turnover_days": round(dio, 2) if dio is not None else None,
        "ar_turnover_days": round(dso, 2) if dso is not None else None,
        "ap_turnover_days": round(dpo, 2) if dpo is not None else None,
        "latest_period": period,
        "period_days_basis": days,
    }, "Known")


def _derive_cycle(turnover_payload: dict, turnover_status: str) -> tuple[dict, str]:
    """Compute ``L4.eff.cycle`` (CCC = DIO + DSO − DPO) from turnover."""

    if turnover_status != "Known":
        return ({"reason": "no turnover data"}, "Inactive")
    dio = turnover_payload.get("inventory_turnover_days")
    dso = turnover_payload.get("ar_turnover_days")
    dpo = turnover_payload.get("ap_turnover_days")
    if dio is None or dso is None or dpo is None:
        return ({"reason": "incomplete DIO/DSO/DPO",
                 "latest_period": turnover_payload.get("latest_period")},
                "Inactive")
    ccc = float(dio) + float(dso) - float(dpo)
    return ({
        "ccc_days": round(ccc, 2),
        "dio": round(float(dio), 2),
        "dso": round(float(dso), 2),
        "dpo": round(float(dpo), 2),
        "latest_period": turnover_payload.get("latest_period"),
    }, "Known")


def _derive_cash_ar(
    income_records: list[dict],
    cashflow_records: list[dict],
    balancesheet_records: list[dict],
) -> tuple[dict, str]:
    """Compute ``L8.fin.cash_ar`` — OCF/NI quality + AR yoy alert.

    Alert thresholds:
      * OCF/NI < 0.8 OR AR yoy > 20% → WARN
      * OCF/NI < 0.5 OR AR yoy > 50% → ERROR
    status="Known" when alert fires (or data present), else "Inactive".

    Empty/missing data → Inactive with reason.
    """

    if not income_records or not cashflow_records:
        return ({"reason": "no income/cashflow data"}, "Inactive")
    inc = income_records[0]
    period = inc.get("end_date")
    cf = _find_record(cashflow_records, period or "") or cashflow_records[0]
    ni = _safe(inc, "n_income")
    ocf = _safe(cf, "n_cashflow_act")
    ocf_to_ni = None
    if ni and ni != 0 and ocf is not None:
        ocf_to_ni = float(ocf) / float(ni)

    # AR yoy from balancesheet
    ar_yoy_pct = None
    if balancesheet_records:
        bs = _find_record(balancesheet_records, period or "") or balancesheet_records[0]
        current_ar = _safe(bs, "accounts_receiv")
        yoy = _yoy_period(str(period or ""))
        prior_bs = _find_record(balancesheet_records, yoy) if yoy else None
        prior_ar = _safe(prior_bs, "accounts_receiv") if prior_bs else None
        if current_ar is not None and prior_ar and prior_ar != 0:
            ar_yoy_pct = ((float(current_ar) - float(prior_ar))
                          / float(prior_ar)) * 100.0

    if ocf_to_ni is None and ar_yoy_pct is None:
        return ({"reason": "no OCF/NI or AR yoy computable",
                 "latest_period": period}, "Inactive")

    # Threshold evaluation.
    alert_severity: str | None = None
    warn_triggered = (ocf_to_ni is not None and ocf_to_ni < 0.8) \
        or (ar_yoy_pct is not None and ar_yoy_pct > 20.0)
    error_triggered = (ocf_to_ni is not None and ocf_to_ni < 0.5) \
        or (ar_yoy_pct is not None and ar_yoy_pct > 50.0)
    if error_triggered:
        alert_severity = "ERROR"
    elif warn_triggered:
        alert_severity = "WARN"

    payload = {
        "ocf_to_ni": round(ocf_to_ni, 4) if ocf_to_ni is not None else None,
        "ar_yoy_pct": round(ar_yoy_pct, 4) if ar_yoy_pct is not None else None,
        "alert_severity": alert_severity,
        "latest_period": period,
    }
    status = "Known" if alert_severity else "Inactive"
    return payload, status


def _derive_debt_pressure(
    balancesheet_records: list[dict],
    fina_records: list[dict],
) -> tuple[dict, str]:
    """Compute ``L8.fin.debt_pressure`` — interest_debt / EBITDA.

    Thresholds:
      * > 4.0 → ERROR
      * > 2.5 → WARN
    status="Known" when alert fires, else "Inactive".
    """

    if not balancesheet_records or not fina_records:
        return ({"reason": "no balancesheet/fina data"}, "Inactive")
    bs = balancesheet_records[0]
    period = bs.get("end_date")
    fina = _find_record(fina_records, period or "") or fina_records[0]
    lt = _safe(bs, "lt_borr") or 0
    st = _safe(bs, "st_borr") or 0
    bond = _safe(bs, "bond_payable") or 0
    interest_debt = float(lt) + float(st) + float(bond)
    ebitda = _safe(fina, "ebitda")
    debt_ratio = _safe(fina, "debt_to_assets")

    # Tushare's quarterly fina_indicator often carries NaN EBITDA until the
    # full-year filing arrives. Walk back through prior periods to find the
    # most recent non-null EBITDA so the ratio stays computable.
    ebitda_period = period
    if (not ebitda or ebitda == 0) and len(fina_records) > 1:
        for prior in fina_records[1:]:
            cand = _safe(prior, "ebitda")
            if cand and cand != 0:
                ebitda = cand
                ebitda_period = prior.get("end_date")
                break

    if not ebitda or ebitda == 0:
        # Fallback: surface debt_to_assets only
        if debt_ratio is not None:
            return ({
                "interest_debt_to_ebitda": None,
                "debt_to_assets": float(debt_ratio),
                "alert_severity": None,
                "latest_period": period,
                "reason": "EBITDA missing — debt_to_assets only",
            }, "Inactive")
        return ({"reason": "EBITDA missing"}, "Inactive")

    ratio = interest_debt / float(ebitda)
    alert_severity: str | None = None
    if ratio > 4.0:
        alert_severity = "ERROR"
    elif ratio > 2.5:
        alert_severity = "WARN"

    payload = {
        "interest_debt_to_ebitda": round(ratio, 4),
        "debt_to_assets": float(debt_ratio) if debt_ratio is not None else None,
        "alert_severity": alert_severity,
        "interest_debt_cny": interest_debt,
        "ebitda_cny": float(ebitda),
        "ebitda_period": ebitda_period,
        "latest_period": period,
    }
    status = "Known" if alert_severity else "Inactive"
    return payload, status


def _derive_inventory_glut(
    balancesheet_records: list[dict],
    fina_records: list[dict],
    income_records: list[dict],
) -> tuple[dict, str]:
    """Compute ``L8.op.inventory_glut`` — inventory yoy vs turnover yoy.

    Thresholds:
      * inventory_yoy > 15% AND turnover_change < -10% → ERROR
      * inventory_yoy > 8% AND turnover_change < -5% → WARN
    status="Known" when alert fires, else "Inactive".

    "turnover change" is the YoY change in inventory_turnover_days
    expressed as a percentage (days up = turnover *slower*, so a positive
    days_change_pct is the "turnover decline" signal).
    """

    if not balancesheet_records or not income_records:
        return ({"reason": "no balancesheet/income data"}, "Inactive")
    bs = balancesheet_records[0]
    period = bs.get("end_date")
    inv = _safe(bs, "inventories")
    if inv is None:
        return ({"reason": "no inventories", "latest_period": period},
                "Inactive")
    yoy = _yoy_period(str(period or ""))
    prior_bs = _find_record(balancesheet_records, yoy) if yoy else None
    prior_inv = _safe(prior_bs, "inventories") if prior_bs else None
    inventory_yoy_pct = None
    if prior_inv and prior_inv != 0:
        inventory_yoy_pct = ((float(inv) - float(prior_inv))
                             / float(prior_inv)) * 100.0

    # Turnover change: prefer turn_days field from fina_indicator.
    turnover_change_pct = None
    if fina_records:
        cur_fina = _find_record(fina_records, period or "") or fina_records[0]
        cur_days = _safe(cur_fina, "turn_days")
        prior_fina = _find_record(fina_records, yoy) if yoy else None
        prior_days = _safe(prior_fina, "turn_days") if prior_fina else None
        if cur_days and prior_days:
            # days_change = (cur - prior) / prior — positive means slower
            # turnover. Spec: turnover_yoy_pct_change is the change in the
            # turnover rate, so a slowdown = negative value. Invert sign.
            days_change = ((float(cur_days) - float(prior_days))
                           / float(prior_days)) * 100.0
            turnover_change_pct = -days_change

    # If we cannot compute either signal, downgrade.
    if inventory_yoy_pct is None and turnover_change_pct is None:
        return ({"reason": "no YoY signals", "latest_period": period},
                "Inactive")

    alert_severity: str | None = None
    error_trigger = (inventory_yoy_pct is not None
                     and turnover_change_pct is not None
                     and inventory_yoy_pct > 15.0
                     and turnover_change_pct < -10.0)
    warn_trigger = (inventory_yoy_pct is not None
                    and turnover_change_pct is not None
                    and inventory_yoy_pct > 8.0
                    and turnover_change_pct < -5.0)
    if error_trigger:
        alert_severity = "ERROR"
    elif warn_trigger:
        alert_severity = "WARN"

    payload = {
        "inventory_yoy_pct": round(inventory_yoy_pct, 4)
            if inventory_yoy_pct is not None else None,
        "turnover_yoy_pct_change": round(turnover_change_pct, 4)
            if turnover_change_pct is not None else None,
        "alert_severity": alert_severity,
        "latest_period": period,
    }
    status = "Known" if alert_severity else "Inactive"
    return payload, status


def _fetch_a_share_derived_metrics(
    pro,
    a_codes: list[str],
    code_to_industry: dict[str, str | None],
    now: int,
) -> list[tuple]:
    """X3b entrypoint — emit seven derived dp_ids per A-share constituent.

    Per-stock pulls (cached for 5 min):
      * fina_indicator → debt, ebitda, turn_days, debt_to_assets
      * balancesheet → inventories, AR, AP, lt/st borr, bond_payable
      * cashflow → c_paid_to_for_empl, n_cashflow_act
      * income → total_revenue, oper_cost, n_income

    Each derived dp_id is wrapped in its own try/except — a failed
    computation only drops that one dp_id for that one ts_code.

    Confidence semantics:
      * 0.7 for ratio-style metrics derived across 3+ endpoints
      * 0.75 for alert dp_ids (L8.*) — slightly more weight because the
        alert_severity is action-relevant.
    """

    rows: list[tuple] = []
    seven_dp_ids = (
        "L4.cost.labor", "L4.cost.raw_material",
        "L4.eff.turnover", "L4.eff.cycle",
        "L8.fin.cash_ar", "L8.fin.debt_pressure",
        "L8.op.inventory_glut",
    )
    counts = {dp: {"Known": 0, "Inactive": 0} for dp in seven_dp_ids}
    alert_dist = {"WARN": 0, "ERROR": 0, "null": 0}

    for ts_code in a_codes:
        if not is_a_share(ts_code):
            continue
        # Per-stock pulls — each helper handles its own cache + RPC throttle.
        # On cache hit the call is free; on cache miss the helper sleeps
        # ``_X3B_RPC_SLEEP_S`` so the cumulative RPC rate stays under the
        # Tushare 500/min budget when stacked with the prior loops.
        income = _get_income_records(pro, ts_code, now)
        balance = _get_balancesheet_records(pro, ts_code, now)
        cashflow = _get_cashflow_records(pro, ts_code, now)
        fina = _get_fina_indicator_records(pro, ts_code, now)

        primary_commodity = _industry_primary_commodity(
            code_to_industry.get(ts_code),
        )

        # ── L4.cost.labor ──
        try:
            payload, status = _derive_labor_cost(income, cashflow)
            rows.append((
                ts_code, "L4.cost.labor",
                json.dumps(payload, ensure_ascii=False),
                status, 0.7 if status == "Known" else 0.0,
                "tushare:cashflow+income.derived", now,
            ))
            counts["L4.cost.labor"][status] += 1
        except Exception as e:  # noqa: BLE001
            log.warning("[tushare] X3b L4.cost.labor %s failed: %s", ts_code, e)

        # ── L4.cost.raw_material ──
        try:
            payload, status = _derive_raw_material(
                income, cashflow, primary_commodity,
            )
            rows.append((
                ts_code, "L4.cost.raw_material",
                json.dumps(payload, ensure_ascii=False),
                status, 0.7 if status == "Known" else 0.0,
                "tushare:income.derived", now,
            ))
            counts["L4.cost.raw_material"][status] += 1
        except Exception as e:  # noqa: BLE001
            log.warning("[tushare] X3b L4.cost.raw_material %s failed: %s",
                        ts_code, e)

        # ── L4.eff.turnover + L4.eff.cycle (cycle uses turnover output) ──
        try:
            turnover_payload, turnover_status = _derive_turnover(income, balance)
            rows.append((
                ts_code, "L4.eff.turnover",
                json.dumps(turnover_payload, ensure_ascii=False),
                turnover_status,
                0.7 if turnover_status == "Known" else 0.0,
                "tushare:balancesheet+income.derived", now,
            ))
            counts["L4.eff.turnover"][turnover_status] += 1

            cycle_payload, cycle_status = _derive_cycle(
                turnover_payload, turnover_status,
            )
            rows.append((
                ts_code, "L4.eff.cycle",
                json.dumps(cycle_payload, ensure_ascii=False),
                cycle_status,
                0.7 if cycle_status == "Known" else 0.0,
                "tushare:balancesheet+income.derived", now,
            ))
            counts["L4.eff.cycle"][cycle_status] += 1
        except Exception as e:  # noqa: BLE001
            log.warning("[tushare] X3b L4.eff.* %s failed: %s", ts_code, e)

        # ── L8.fin.cash_ar ──
        try:
            payload, status = _derive_cash_ar(income, cashflow, balance)
            rows.append((
                ts_code, "L8.fin.cash_ar",
                json.dumps(payload, ensure_ascii=False),
                status, 0.75 if status == "Known" else 0.0,
                "tushare:cashflow+income+balancesheet.derived", now,
            ))
            counts["L8.fin.cash_ar"][status] += 1
            sev = payload.get("alert_severity")
            alert_dist[sev if sev in ("WARN", "ERROR") else "null"] += 1
        except Exception as e:  # noqa: BLE001
            log.warning("[tushare] X3b L8.fin.cash_ar %s failed: %s",
                        ts_code, e)

        # ── L8.fin.debt_pressure ──
        try:
            payload, status = _derive_debt_pressure(balance, fina)
            rows.append((
                ts_code, "L8.fin.debt_pressure",
                json.dumps(payload, ensure_ascii=False),
                status, 0.75 if status == "Known" else 0.0,
                "tushare:balancesheet+fina_indicator.derived", now,
            ))
            counts["L8.fin.debt_pressure"][status] += 1
            sev = payload.get("alert_severity")
            alert_dist[sev if sev in ("WARN", "ERROR") else "null"] += 1
        except Exception as e:  # noqa: BLE001
            log.warning("[tushare] X3b L8.fin.debt_pressure %s failed: %s",
                        ts_code, e)

        # ── L8.op.inventory_glut ──
        try:
            payload, status = _derive_inventory_glut(balance, fina, income)
            rows.append((
                ts_code, "L8.op.inventory_glut",
                json.dumps(payload, ensure_ascii=False),
                status, 0.75 if status == "Known" else 0.0,
                "tushare:balancesheet+fina_indicator.derived", now,
            ))
            counts["L8.op.inventory_glut"][status] += 1
            sev = payload.get("alert_severity")
            alert_dist[sev if sev in ("WARN", "ERROR") else "null"] += 1
        except Exception as e:  # noqa: BLE001
            log.warning("[tushare] X3b L8.op.inventory_glut %s failed: %s",
                        ts_code, e)

    log.info(
        "[tushare] X3b derived metrics: %d rows across %d A-shares; "
        "Known/Inactive per dp_id: %s; alert_severity: %s",
        len(rows), len(a_codes), counts, alert_dist,
    )
    return rows


# ---------------------------------------------------------------------------
# X5: text-disclosure fetchers (irm_qa, stock_company, stk_managers)
# ---------------------------------------------------------------------------
#
# These three dp_ids are mvp20-internal facts surfaced to codex LLM prompts
# via the X5 closed-loop pipeline. They are *not* spec-managed and are not
# registered in ``data_point_roles.yaml``; their only role is to give codex
# concrete inline evidence for the 26 new closed-loop slots so the prompt
# never has to ask the LLM to invent URLs or recall training-set facts.
#
# All three are slow-moving (Q&A backlog updates weekly at most, main
# business and 高管 table update at announcement events). A 10-min cache
# is plenty; a permission-error short-circuit aborts the loop early so
# one missing endpoint cannot drag down the whole disclosure batch.
#
# Per-stock failure isolation: every endpoint call is wrapped, and a
# missing row emits ``data_status="Inactive"`` rather than dropping
# silently. This is the same pattern as ``_fetch_a_share_mgmt_litigation``.


def _truncate_text(value, limit: int) -> str | None:
    """Normalize a Tushare text cell to ``str`` and clip to ``limit`` chars.

    Tushare returns pandas NaN (a float), ``None``, or arbitrary unicode for
    text columns. We collapse NaN/None to None and clip the string to keep
    the SQLite payload bounded (the codex prompt only needs a snippet).
    """

    if value is None:
        return None
    if isinstance(value, float) and value != value:  # NaN
        return None
    s = str(value).strip()
    if not s:
        return None
    return s[:limit]


def _fetch_a_share_irm_qa(
    pro,
    a_codes: list[str],
    now: int,
    *,
    top_n: int = 10,
) -> list[tuple]:
    """Emit ``L9.disclosure.qa_recent`` per A-share.

    Strategy: pick the SH or SZ variant of ``irm_qa`` based on the ts_code
    suffix (``.SH`` → ``irm_qa_sh``; ``.SZ`` / ``.BJ`` → ``irm_qa_sz``).
    Pull the top ``top_n`` recent Q&A pairs, truncate to 300 chars each, and
    bundle them with ``count_recent`` + ``latest_date``.

    Per-stock 10-min cache via ``_IRM_QA_CACHE``. Permission error → stop
    issuing further calls for the failing endpoint (Tushare 没积分 returns
    permission error consistently for both _sh and _sz variants).
    """

    rows: list[tuple] = []
    sleep_s = 0.13
    permission_sh = 0
    permission_sz = 0
    active = 0
    inactive = 0

    for ts_code in a_codes:
        cached = _IRM_QA_CACHE.get(ts_code)
        records: list[dict] | None = None
        endpoint = "irm_qa_sh" if ts_code.endswith(".SH") else "irm_qa_sz"
        if cached and now - cached[0] < _DISCLOSURE_CACHE_TTL_S:
            records = cached[1]
        else:
            # If this endpoint has already tripped its permission threshold,
            # short-circuit immediately and emit an Inactive row without
            # re-issuing the failing call. ``permission_*`` counters survive
            # the ts_code loop and are how we know.
            already_dead = (
                (endpoint == "irm_qa_sh" and permission_sh >= 3)
                or (endpoint == "irm_qa_sz" and permission_sz >= 3)
            )
            fn = getattr(pro, endpoint, None)
            if fn is None or already_dead:
                inactive += 1
                rows.append((
                    ts_code, "L9.disclosure.qa_recent",
                    json.dumps({
                        "count_recent": 0,
                        "top_qa": [],
                        "latest_date": None,
                        "reason": (
                            f"endpoint {endpoint} unavailable"
                            if fn is None
                            else f"{endpoint} permission denied (threshold)"
                        ),
                    }, ensure_ascii=False),
                    "Inactive", 0.0, f"tushare:{endpoint}", now,
                ))
                continue
            try:
                df = fn(ts_code=ts_code)
            except Exception as e:  # noqa: BLE001
                msg = str(e)
                is_perm = any(k in msg for k in
                              ("权限", "积分", "permission", "credit"))
                if is_perm:
                    if endpoint == "irm_qa_sh":
                        permission_sh += 1
                    else:
                        permission_sz += 1
                if permission_sh + permission_sz <= 1:
                    log.warning(
                        "[tushare] %s permission/error on %s: %s",
                        endpoint, ts_code, e,
                    )
                # Once the threshold is hit, emit Inactive for *this* ts_code
                # so the codex prompt still sees a row; future ts_codes will
                # short-circuit via the ``already_dead`` check above.
                if (endpoint == "irm_qa_sh" and permission_sh >= 3) or (
                    endpoint == "irm_qa_sz" and permission_sz >= 3
                ):
                    inactive += 1
                    rows.append((
                        ts_code, "L9.disclosure.qa_recent",
                        json.dumps({
                            "count_recent": 0,
                            "top_qa": [],
                            "latest_date": None,
                            "reason": f"{endpoint} permission denied",
                        }, ensure_ascii=False),
                        "Inactive", 0.0, f"tushare:{endpoint}", now,
                    ))
                    time.sleep(sleep_s)
                    continue
                time.sleep(sleep_s)
                continue
            time.sleep(sleep_s)
            records = df.to_dict(orient="records") if hasattr(df, "to_dict") else list(df or [])
            _IRM_QA_CACHE[ts_code] = (now, records)

        if not records:
            inactive += 1
            rows.append((
                ts_code, "L9.disclosure.qa_recent",
                json.dumps({
                    "count_recent": 0,
                    "top_qa": [],
                    "latest_date": None,
                    "reason": "no Q&A rows",
                }, ensure_ascii=False),
                "Inactive", 0.6,
                "tushare:irm_qa_sh" if ts_code.endswith(".SH") else "tushare:irm_qa_sz",
                now,
            ))
            continue

        # Sort latest-first by date; Tushare returns ``trade_date`` or
        # ``ann_date`` for these endpoints — fall back to any non-empty
        # date-shaped key.
        def _qa_date(r: dict) -> str:
            return str(
                r.get("trade_date") or r.get("ann_date")
                or r.get("date") or ""
            )

        records_sorted = sorted(records, key=_qa_date, reverse=True)
        top_qa: list[dict] = []
        for rec in records_sorted[:top_n]:
            top_qa.append({
                "question": _truncate_text(rec.get("q") or rec.get("question"), 300),
                "answer": _truncate_text(rec.get("a") or rec.get("answer"), 300),
                "date": _qa_date(rec) or None,
            })
        active += 1
        rows.append((
            ts_code, "L9.disclosure.qa_recent",
            json.dumps({
                "count_recent": len(records),
                "top_qa": top_qa,
                "latest_date": _qa_date(records_sorted[0]) or None,
            }, ensure_ascii=False),
            "Known", 0.7,
            "tushare:irm_qa_sh" if ts_code.endswith(".SH") else "tushare:irm_qa_sz",
            now,
        ))

    log.info(
        "[tushare] irm_qa: %d active / %d inactive (sh-perm=%d sz-perm=%d) → %d rows",
        active, inactive, permission_sh, permission_sz, len(rows),
    )
    return rows


def _fetch_a_share_stock_company(
    pro,
    a_codes: list[str],
    now: int,
) -> list[tuple]:
    """Emit ``L1.company.main_business`` per A-share.

    Pulls ``stock_company`` for ``main_business``, ``business_scope``,
    ``introduction``, ``chairman``, ``manager``. Truncates text to 500
    chars for main_business/business_scope, 300 for introduction.

    Per-stock 10-min cache via ``_STOCK_COMPANY_CACHE``.
    """

    rows: list[tuple] = []
    sleep_s = 0.13
    permission_errors = 0
    active = 0
    inactive = 0

    for ts_code in a_codes:
        cached = _STOCK_COMPANY_CACHE.get(ts_code)
        records: list[dict] | None = None
        if cached and now - cached[0] < _DISCLOSURE_CACHE_TTL_S:
            records = cached[1]
        else:
            try:
                df = pro.stock_company(
                    ts_code=ts_code,
                    fields=("ts_code,chairman,manager,main_business,"
                            "business_scope,introduction"),
                )
            except Exception as e:  # noqa: BLE001
                msg = str(e)
                if any(k in msg for k in
                       ("权限", "积分", "permission", "credit")):
                    permission_errors += 1
                if permission_errors <= 1:
                    log.warning(
                        "[tushare] stock_company %s failed: %s",
                        ts_code, e,
                    )
                if permission_errors >= 3:
                    break
                time.sleep(sleep_s)
                continue
            time.sleep(sleep_s)
            records = df.to_dict(orient="records") if hasattr(df, "to_dict") else list(df or [])
            _STOCK_COMPANY_CACHE[ts_code] = (now, records)

        if not records:
            inactive += 1
            rows.append((
                ts_code, "L1.company.main_business",
                json.dumps({
                    "main_business": None,
                    "business_scope": None,
                    "introduction": None,
                    "chairman": None,
                    "manager": None,
                    "reason": "no stock_company row",
                }, ensure_ascii=False),
                "Inactive", 0.5, "tushare:stock_company", now,
            ))
            continue

        rec = records[0]
        main_business = _truncate_text(rec.get("main_business"), 500)
        business_scope = _truncate_text(rec.get("business_scope"), 500)
        introduction = _truncate_text(rec.get("introduction"), 300)
        chairman = _truncate_text(rec.get("chairman"), 80)
        manager = _truncate_text(rec.get("manager"), 80)

        any_text = any((main_business, business_scope, introduction))
        if any_text:
            active += 1
            status = "Known"
            conf = 0.8
        else:
            inactive += 1
            status = "Inactive"
            conf = 0.4
        rows.append((
            ts_code, "L1.company.main_business",
            json.dumps({
                "main_business": main_business,
                "business_scope": business_scope,
                "introduction": introduction,
                "chairman": chairman,
                "manager": manager,
            }, ensure_ascii=False),
            status, conf, "tushare:stock_company", now,
        ))

    log.info(
        "[tushare] stock_company: %d active / %d inactive (perm-skipped=%d) → %d rows",
        active, inactive, permission_errors, len(rows),
    )
    return rows


def _fetch_a_share_stk_managers_table(
    pro,
    a_codes: list[str],
    now: int,
    *,
    top_n: int = 10,
    change_lookback_days: int = 365,
) -> list[tuple]:
    """Emit ``L8.gov.management_table`` per A-share.

    Pulls ``stk_managers`` per stock. Emits top-N current managers (by
    most recent take_office_date / ann_date) plus a one-year change count.
    The legacy ``L9.company.mgmt_litigation`` fetcher reuses ``stk_managers``
    but with a 180-day event window — this is a *table* view rather than an
    event view, so per-stock fields don't overlap.

    Per-stock 10-min cache via ``_STK_MANAGERS_CACHE``.
    """

    rows: list[tuple] = []
    sleep_s = 0.13
    permission_errors = 0
    active = 0
    inactive = 0
    cutoff = _previous_n_days(change_lookback_days)

    for ts_code in a_codes:
        cached = _STK_MANAGERS_CACHE.get(ts_code)
        records: list[dict] | None = None
        if cached and now - cached[0] < _DISCLOSURE_CACHE_TTL_S:
            records = cached[1]
        else:
            try:
                df = pro.stk_managers(ts_code=ts_code)
            except Exception as e:  # noqa: BLE001
                msg = str(e)
                if any(k in msg for k in
                       ("权限", "积分", "permission", "credit")):
                    permission_errors += 1
                if permission_errors <= 1:
                    log.warning(
                        "[tushare] stk_managers(table) %s failed: %s",
                        ts_code, e,
                    )
                if permission_errors >= 3:
                    break
                time.sleep(sleep_s)
                continue
            time.sleep(sleep_s)
            records = df.to_dict(orient="records") if hasattr(df, "to_dict") else list(df or [])
            _STK_MANAGERS_CACHE[ts_code] = (now, records)

        if not records:
            inactive += 1
            rows.append((
                ts_code, "L8.gov.management_table",
                json.dumps({
                    "managers": [],
                    "change_count_recent_year": 0,
                    "lookback_days": change_lookback_days,
                    "reason": "no stk_managers rows",
                }, ensure_ascii=False),
                "Inactive", 0.5, "tushare:stk_managers", now,
            ))
            continue

        def _mgr_date(r: dict) -> str:
            return str(
                r.get("take_office_date") or r.get("ann_date")
                or r.get("begin_date") or ""
            )

        # Most recent first (current management table)
        sorted_records = sorted(records, key=_mgr_date, reverse=True)
        managers = []
        for rec in sorted_records[:top_n]:
            managers.append({
                "name": _truncate_text(rec.get("name"), 50),
                "title": _truncate_text(rec.get("title"), 80),
                "gender": _truncate_text(rec.get("gender"), 4),
                "edu": _truncate_text(rec.get("edu"), 80),
                "ann_date": _truncate_text(rec.get("ann_date"), 8),
                "take_office_date": _truncate_text(rec.get("take_office_date"), 8),
            })
        # Change count: ann_date within last year
        change_count = sum(
            1 for r in records
            if (r.get("ann_date") or "") >= cutoff
        )

        active += 1
        rows.append((
            ts_code, "L8.gov.management_table",
            json.dumps({
                "managers": managers,
                "change_count_recent_year": int(change_count),
                "lookback_days": change_lookback_days,
            }, ensure_ascii=False),
            "Known", 0.7, "tushare:stk_managers", now,
        ))

    log.info(
        "[tushare] stk_managers(table): %d active / %d inactive (perm-skipped=%d) → %d rows",
        active, inactive, permission_errors, len(rows),
    )
    return rows


def fetch_disclosure_batch(
    pro,
    a_codes: list[str],
    now: int | None = None,
) -> list[tuple]:
    """Top-level X5 disclosure helper exposed for tests and direct invocation.

    Aggregates the three text-disclosure fetchers (irm_qa, stock_company,
    stk_managers table) for the given A-share codes. Each underlying call is
    independently wrapped — a single endpoint failure cannot poison the rest.
    """

    if now is None:
        now = int(time.time())
    rows: list[tuple] = []
    try:
        rows.extend(_fetch_a_share_irm_qa(pro, a_codes, now))
    except Exception as e:  # noqa: BLE001
        log.warning("[tushare] X5 irm_qa batch failed: %s", e)
    try:
        rows.extend(_fetch_a_share_stock_company(pro, a_codes, now))
    except Exception as e:  # noqa: BLE001
        log.warning("[tushare] X5 stock_company batch failed: %s", e)
    try:
        rows.extend(_fetch_a_share_stk_managers_table(pro, a_codes, now))
    except Exception as e:  # noqa: BLE001
        log.warning("[tushare] X5 stk_managers_table batch failed: %s", e)
    return rows
