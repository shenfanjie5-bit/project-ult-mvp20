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
import math
import os
import time
from datetime import datetime, timezone
from typing import Iterable

log = logging.getLogger("mvp20.sources.tushare")

DEFAULT_TUSHARE_TIMEOUT_SECONDS = 10.0

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
    # L5 sell-side forecast fields (from report_rc). These mirror the
    # FMP analyst-estimates dp_ids but use A-share broker report fields.
    "L5.fcst.revenue_margin",
    "L5.fcst.eps_cf",
    "L5.fcst.revisions",
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
    "L7.env.fx",                  # fx_daily USDCNH — RMB regime tilt (MARKET:CN)
    "L9.macro.fx",                # fx_daily USDCNH — RMB depreciation risk (MARKET:CN)
    "L9.macro.cpi_employment",    # cn_cpi + cn_ppi
    "L7.env.market_trend",         # index_daily market benchmark trend
    "L7.env.style",                # index_daily 成长 vs 价值 regime tilt (MARKET:CN)
    "L10.val.historical_quantile",  # market-wide PE_ttm quantile from daily_basic
    "L10.industry.fund_flow",     # moneyflow_ind_ths per active industry
    # ── akshare-replacement batch (8 dp_ids moved off akshare onto permitted
    # Tushare endpoints; emitted by ``fetch_akshare_replacement_batch``).
    # Each preserves the original akshare payload-key schema so downstream
    # derive/bridge consumers keep working. ──
    "L9.event.intraday_announcement",  # anns_d (per-stock 公告)
    "L7.mood.media_social",            # ths_hot 热股 (per-stock heat)
    "L9.media.social_buzz",            # ths_hot 热股 (per-stock; in_xq_top_buzz kept)
    "L7.mood.theme",                   # ths_hot 概念板块 (hot concepts)
    "L0.sentiment.sector_heat",        # moneyflow_ind_ths (per-industry heat)
    "L0.cost.raw_material",            # fut_daily (per-industry commodity pct)
    "L0.cost.energy_logistics",        # fut_daily SC.INE + akshare BDI
    "L8.cap.outflow_cut",              # moneyflow 5d net (per-stock)
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
    # ── Bucket A: hard-data dp_ids appended at fetch_batch tail ──
    # Sub-group 1: L2 业务分部 (3) from pro.fina_mainbz
    "L2.segment.revenue_share",     # 各 bz_item 收入占比
    "L2.segment.gross_margin",      # (bz_sales - bz_cost) / bz_sales
    "L2.segment.growth",            # bz_sales 同比 yoy
    # Sub-group 2: L5 财报预告/快报变化 (2)
    "L5.fcst.guidance_change",      # forecast 最近 2 期 type/range delta
    "L5.surprise.beat_miss",        # express 实际 vs forecast 中位
    # Sub-group 3: L8.fin 财报风险 (3)
    "L8.fin.eps_downward",          # forecast EPS 中位数 delta
    "L8.fin.goodwill_impairment",   # balancesheet goodwill 下滑
    "L8.fin.revenue_profit_miss",   # surprise miss 触发 alert
    # Sub-group 4: L8.cap 资金/拥挤/流动性 (3)
    "L8.cap.crowdedness",           # 30d 平均换手率 + 资金净流入 5d
    "L8.cap.short_increase",        # 融券余额 rqye 30d/90d ma
    "L8.cap.liquidity_short",       # 30d 均成交额 + 单日大跌放量
    # Sub-group 5: L8.industry/op (2)
    "L8.industry.valuation_compression",  # 行业 PE_ttm 30d vs 90d
    "L8.op.cost_overrun",                 # cost yoy 比 revenue yoy 高
    # Sub-group 6: L9.capital (1)
    "L9.capital.margin_anomaly",    # rzmre 5d ma vs 30d ma 翻倍
    # ── Bucket B: 12 hard-data dp_ids (估值 + 卖方研报 + L0 行业 sentiment + peer) ──
    # Sub-group B1: L0 industry-level sentinel sentiment (4)
    "L0.cost.capital",              # LPR + industry risk premium (MARKET:CN)
    "L0.sentiment.institutional",   # top10 inst holding pct + 30d delta (per industry)
    "L0.sentiment.leader_drag",     # leader 5d vs follower 5d (per industry)
    "L0.sentiment.social",          # hot-stocks count + themes (per industry)
    # Sub-group B2: L6 valuation 5 (mix per-stock + per-industry)
    "L6.priced.analyst_revision",   # report_rc 上修/下修 90d (per-stock)
    "L6.priced.discussion",         # dc_hot + ths_hot 30d (per-stock)
    "L6.priced.crowdedness",        # daily_basic turnover percentile (per-stock)
    "L6.state.expansion_compression",  # PE vs 60d / 250d ma (per-stock)
    "L6.state.industry_center",     # industry PE/PB/PS median (per industry)
    "L6.state.peer_compare",        # stock PE vs industry median (per-stock)
    # Sub-group B3: L7.mood + L9.media (sell-side research派生) 2
    "L7.mood.analyst_rating",       # report_rc 评级分布 (per-stock)
    "L9.media.analyst_action",      # report_rc 7d 评级变动 event (per-stock)
    # Sub-group B4: L10.val.peer (1) — alias-style view of peer_compare
    "L10.val.peer",                 # validation: stock vs industry PE/PB
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

# ── FX tilt tuning (L7.env.fx / L9.macro.fx via fx_daily) ──────────────────
# Window: ~20 trading rows ≈ one trading month of USDCN* close-to-close move.
_FX_WINDOW = 20
# tanh scale: a 2% RMB move over the window maps to magnitude ≈ 0.76. RMB is
# tightly managed so 2% in a month is already a notable tilt.
_FX_SCALE_PCT = 2.0
# L9 risk fires only when USDCNH rises (RMB depreciates) > 1.0% over window.
_FX_RISK_THRESHOLD_PCT = 1.0

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

# ---------------------------------------------------------------------------
# Bucket A: extra per-stock caches (5-min TTL).
# ---------------------------------------------------------------------------
#
# Bucket A adds hard-data dp_ids that re-use the existing fina_indicator /
# balancesheet / income / cashflow cache family plus three new endpoints:
#
#   * pro.fina_mainbz  — 主营业务收入分部 (per-stock)
#   * pro.forecast     — already wrapped in ``_fetch_a_share_forecast`` but
#                        Bucket A needs ≥ 2 recent rows so we add a separate
#                        cache to avoid re-pulling.
#   * pro.express      — 业绩快报 (per-stock)
#
# All three share the X3b convention: ``_cache_get/put`` with a 5-min TTL,
# RPC throttle on cache miss, and empty list on permission error or schema
# drift (so callers can branch to Inactive without try/except).
_FINA_MAINBZ_CACHE: dict[str, tuple[int, list[dict]]] = {}
_FORECAST_CACHE: dict[str, tuple[int, list[dict]]] = {}
_EXPRESS_CACHE: dict[str, tuple[int, list[dict]]] = {}
_DAILY_BASIC_HISTORY_CACHE: dict[str, tuple[int, list[dict]]] = {}
_DAILY_HISTORY_CACHE: dict[str, tuple[int, list[dict]]] = {}
_MARGIN_HISTORY_CACHE: dict[str, tuple[int, list[dict]]] = {}

# ---------------------------------------------------------------------------
# Bucket B: per-stock + market/industry caches (5-min TTL).
# ---------------------------------------------------------------------------
#
# Bucket B adds 12 hard-data dp_ids covering valuation, sell-side research,
# L0 industry-level sentiment, and peer comparison. New endpoints:
#
#   * pro.report_rc       — 卖方研报评级 (per-stock; 90d window). Same
#                           endpoint as Tushare A's L5.surprise.sell_side but
#                           we cache the raw record list here so Bucket B
#                           fetchers can run independently of that pre-existing
#                           helper (which only emits L5.surprise.sell_side).
#   * pro.dc_hot          — 东方财富热榜 (market-wide; daily snapshot).
#   * pro.ths_hot         — 同花顺热榜 (market-wide; daily snapshot).
#   * pro.top10_holders   — 前十大股东 (per-stock; latest 4 periods).
#
# Plus a "long" daily_basic history cache (~300d) so the
# ``L6.state.expansion_compression`` fetcher can compute the 60d / 250d MA
# without invalidating the 120d Bucket A cache.
_REPORT_RC_CACHE: dict[str, tuple[int, list[dict]]] = {}
_DC_HOT_CACHE: tuple[int, list[dict]] | None = None
_THS_HOT_CACHE: tuple[int, list[dict]] | None = None
_SHIBOR_LPR_CACHE: tuple[int, list[dict]] | None = None
_TOP10_HOLDERS_CACHE: dict[str, tuple[int, list[dict]]] = {}
_DAILY_BASIC_HISTORY_LONG_CACHE: dict[str, tuple[int, list[dict]]] = {}
# Industry-level center cache keyed by industry_id ↔ payload (industry PE/PB
# medians). Populated by ``_emit_industry_center`` and consumed by both
# ``L6.state.peer_compare`` and ``L10.val.peer``.
_INDUSTRY_CENTER_CACHE: dict[str, tuple[int, dict]] = {}


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
    return ts.pro_api(timeout=_tushare_timeout_seconds())


def _tushare_timeout_seconds() -> float:
    raw = os.environ.get("TUSHARE_TIMEOUT_SECONDS")
    if not raw:
        return DEFAULT_TUSHARE_TIMEOUT_SECONDS
    try:
        timeout = float(raw)
    except ValueError:
        log.warning(
            "[tushare] invalid TUSHARE_TIMEOUT_SECONDS=%r; using %.1fs",
            raw,
            DEFAULT_TUSHARE_TIMEOUT_SECONDS,
        )
        return DEFAULT_TUSHARE_TIMEOUT_SECONDS
    if timeout <= 0:
        log.warning(
            "[tushare] non-positive TUSHARE_TIMEOUT_SECONDS=%r; using %.1fs",
            raw,
            DEFAULT_TUSHARE_TIMEOUT_SECONDS,
        )
        return DEFAULT_TUSHARE_TIMEOUT_SECONDS
    return timeout


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


# ---------------------------------------------------------------------------
# akshare-replacement batch (8 dp_ids moved off akshare onto permitted Tushare
# endpoints). Each emitter preserves the EXACT payload key schema the old
# akshare emitter produced so downstream derive/bridge consumers keep working.
# ---------------------------------------------------------------------------
#
# dp_id → Tushare endpoint:
#   L9.event.intraday_announcement → pro.anns_d (per-stock recent 公告)
#   L7.mood.media_social           → pro.ths_hot data_type=='热股' (per-stock heat)
#   L9.media.social_buzz           → pro.ths_hot data_type=='热股' (same fetch)
#   L7.mood.theme                  → pro.ths_hot data_type=='概念板块' (hot concepts)
#   L0.sentiment.sector_heat       → pro.moneyflow_ind_ths (per-industry heat)
#   L0.cost.raw_material           → pro.fut_daily (per-industry commodity pct)
#   L0.cost.energy_logistics       → pro.fut_daily SC.INE (+ akshare BDI kept)
#   L8.cap.outflow_cut             → pro.moneyflow ts_code history (5d net)
#
# The per-stock emitters share a single ths_hot fetch (TTL-cached at module
# level) so a collector tick hits that endpoint at most once. The ann_d +
# moneyflow per-stock calls are throttled with the existing _BUCKET_A_SLEEP_S.

_AK_REPL_CACHE_TTL_S = 600

# Industry → primary commodity future ts_code (Tushare ``pro.fut_daily``
# ``ts_code`` convention, e.g. ``CU.SHF`` 沪铜, ``SC.INE`` 上海原油). Mirrors
# the akshare ``config/industry_to_commodity.yaml`` Sina-futures map but uses
# Tushare's exchange-suffixed continuous-contract codes. Industries with no
# clean 1:1 commodity exposure are omitted (the emitter skips them — no
# half-baked rows), matching the akshare ``null`` semantics.
INDUSTRY_TO_FUT_TS_CODE: dict[str, list[str]] = {
    "NONFERROUS_METALS":   ["CU.SHF", "AL.SHF", "NI.SHF", "ZN.SHF", "SN.SHF"],
    "SEMI_EQUIPMENT":      ["SI.GFE", "LC.GFE"],
    "EXPORT_MFG":          ["CU.SHF", "AL.SHF"],
    "CONSUMER_ELECTRONICS": ["CU.SHF", "L.DCE"],
    "STORAGE_GRID":        ["LC.GFE", "NI.SHF", "CU.SHF"],
    "ANTI_INVOLUTION_CYCLICAL": ["RB.SHF", "I.DCE", "J.DCE"],
}

# Commodity future used for the crude-oil component of energy_logistics.
_ENERGY_CRUDE_FUT_TS_CODE = "SC.INE"

# Module-level TTL caches for the shared ths_hot pull + the two industry/market
# batches. Per-stock announcement/moneyflow results are not cached here (they
# vary by universe slice); the upstream collector re-pulls per cycle but the
# anns_d/moneyflow endpoints are cheap per-stock daily snapshots.
_THS_HOT_HEAT_CACHE: tuple[int, list[dict]] | None = None
_LAST_AK_SECTOR_HEAT_FETCH: dict[str, object] = {"ts": 0, "rows": []}
_LAST_AK_RAW_MATERIAL_FETCH: dict[str, object] = {"ts": 0, "rows": []}
_LAST_AK_ENERGY_FETCH: dict[str, object] = {"ts": 0, "rows": []}


def _ak_repl_as_of_iso() -> str:
    """ISO-8601 local timestamp matching akshare_source._as_of_iso()."""

    return datetime.now(tz=timezone.utc).astimezone().isoformat(
        timespec="seconds",
    )


def _to_a_share_6digit(ts_code: str) -> str | None:
    """``300750.SZ`` → ``300750``; None for non-A-share. Mirrors
    akshare_source.to_a_share_code so per-stock lookup keys match."""

    if not is_a_share(ts_code):
        return None
    return ts_code[:-3]


def _get_ths_hot_heat_records(pro, now: int) -> list[dict]:
    """One market-wide ``pro.ths_hot(trade_date=)`` pull, TTL-cached.

    Returns the raw record list (all ``data_type`` rows: 热股 / 概念板块 / …).
    Callers filter by ``data_type``. Walks back up to 8 calendar days to find
    a populated snapshot (covers weekends/holidays). Probed columns:
    ``[trade_date, data_type, ts_code, ts_name, rank, pct_change, current_price,
    rank_reason, hot, concept, rank_time]`` — we only rely on the documented
    subset ``[trade_date, ts_code, ts_name, rank, hot, pct_change, data_type]``.
    """

    global _THS_HOT_HEAT_CACHE
    if _THS_HOT_HEAT_CACHE is not None:
        cached_ts, records = _THS_HOT_HEAT_CACHE
        if now - cached_ts < _AK_REPL_CACHE_TTL_S:
            return records
    records: list[dict] = []
    for back in range(0, 8):
        trade_date = _previous_n_days(back)
        try:
            df = pro.ths_hot(trade_date=trade_date)
            time.sleep(_BUCKET_A_SLEEP_S)
        except Exception as e:  # noqa: BLE001
            log.warning("[tushare] ths_hot(%s) failed: %s", trade_date, e)
            continue
        if df is None or len(df) == 0:
            continue
        records = df.to_dict(orient="records")
        break
    _THS_HOT_HEAT_CACHE = (now, records)
    return records


def _ths_hot_index_by_code(records: list[dict], data_type: str) -> dict[str, dict]:
    """Index ths_hot records of one ``data_type`` by 6-digit A-share code.

    ths_hot ``ts_code`` is suffixed (``300750.SZ``); we key by the 6-digit
    prefix so per-stock lookup matches the akshare convention. The total
    membership count for that data_type is stashable by the caller via len().
    """

    out: dict[str, dict] = {}
    for rec in records:
        if str(rec.get("data_type") or "") != data_type:
            continue
        ts_code = str(rec.get("ts_code") or "").strip()
        if not ts_code:
            continue
        # Accept both suffixed (300750.SZ) and bare (300750) forms.
        code6 = ts_code.split(".")[0]
        if code6:
            out[code6] = rec
    return out


def _emit_ak_intraday_announcement(
    pro, a_codes: list[str], now: int, top_n_per_stock: int = 5,
) -> list[tuple]:
    """``L9.event.intraday_announcement`` — per A-share recent 公告 via
    ``pro.anns_d(ts_code=, start_date=, end_date=)``.

    Preserves the akshare ``fetch_intraday_announcement`` payload schema:
    ``{count_recent, top_announcements:[{title, type, ann_date, url}], as_of}``.
    anns_d has no 公告类型 column, so ``type`` is emitted as ``None`` (the key
    is preserved for downstream compatibility). Probed columns:
    ``[ann_date, ts_code, name, title, url]``.
    """

    rows: list[tuple] = []
    as_of = _ak_repl_as_of_iso()
    start_date = _previous_n_days(30)
    end_date = _today_yyyymmdd()
    success = 0
    failed = 0
    for ts_code in a_codes:
        if not is_a_share(ts_code):
            continue
        try:
            df = pro.anns_d(
                ts_code=ts_code, start_date=start_date, end_date=end_date,
                fields="ann_date,ts_code,name,title,url",
            )
            time.sleep(_BUCKET_A_SLEEP_S)
        except Exception as e:  # noqa: BLE001
            log.warning("[tushare] anns_d %s failed: %s", ts_code, e)
            failed += 1
            continue
        if df is None or len(df) == 0:
            failed += 1
            continue
        records = df.to_dict(orient="records")
        # anns_d returns most-recent-first; keep the top-N as headlines.
        top: list[dict] = []
        for rec in records[:top_n_per_stock]:
            top.append({
                "title": rec.get("title"),
                "type": None,  # anns_d has no 公告类型 column
                "ann_date": _stringify_yyyymmdd(rec.get("ann_date")),
                "url": rec.get("url"),
            })
        payload = {
            "count_recent": len(records),
            "top_announcements": top,
            "as_of": as_of,
        }
        rows.append((
            ts_code, "L9.event.intraday_announcement",
            json.dumps(payload, ensure_ascii=False),
            "Known", 0.65, "tushare:anns_d", now,
        ))
        success += 1
    log.info("[tushare] ak-repl intraday_announcement: %d ok / %d failed → %d rows",
             success, failed, len(rows))
    return rows


def _emit_ak_media_social_buzz_theme(
    pro, a_codes: list[str], now: int,
) -> list[tuple]:
    """Emit ``L7.mood.media_social`` + ``L9.media.social_buzz`` +
    ``L7.mood.theme`` from a single ``pro.ths_hot`` pull.

    Reuses ONE ths_hot fetch (热股 + 概念板块 data_type buckets) for all three
    per-stock dp_ids. Payload schemas are preserved verbatim from the akshare
    emitters:

      * media_social: {rank_overall, in_top_100, last_price, change_pct,
                       concept_tag_count, as_of}
      * social_buzz:  {in_xq_top_buzz, follow_count, tweet_count,
                       rank_among_buzz_top, last_price, as_of}
        — ``in_xq_top_buzz`` is KEPT (downstream derive._bootstrap_l11_subscores
        reads it) but now means "in ths_hot 热股 top list" instead of "in
        Xueqiu top buzz". follow_count/tweet_count have no ths_hot equivalent
        → emitted as the ``hot`` heat score / None to preserve the keys.
      * theme: {concept_count, top_concepts:[...], as_of}
    """

    records = _get_ths_hot_heat_records(pro, now)
    heat_by_code = _ths_hot_index_by_code(records, "热股")
    # Hot concept-board list (market-wide; no per-stock attribution offline) —
    # matches the akshare theme version which surfaced market/industry-level
    # hot concept tags. Build the top-concepts list once.
    hot_concepts: list[dict] = []
    for rec in records:
        if str(rec.get("data_type") or "") != "概念板块":
            continue
        hot_concepts.append({
            "concept": rec.get("ts_name") or rec.get("concept"),
            "rank": _safe_num(rec.get("rank")),
            "hot": _safe_num(rec.get("hot")),
            "pct_change": _safe_num(rec.get("pct_change")),
        })
    hot_concepts.sort(key=lambda c: (c["rank"] if c["rank"] is not None else 1e9))
    as_of = _ak_repl_as_of_iso()

    rows: list[tuple] = []
    n_social = 0
    n_buzz = 0
    n_theme = 0
    for ts_code in a_codes:
        code6 = _to_a_share_6digit(ts_code)
        if not code6:
            continue
        entry = heat_by_code.get(code6)
        rank = _safe_num(entry.get("rank")) if entry else None
        hot = _safe_num(entry.get("hot")) if entry else None
        pct = _safe_num(entry.get("pct_change")) if entry else None
        last_price = _safe_num(entry.get("current_price")) if entry else None

        # ---- L7.mood.media_social ----
        social_payload = {
            "rank_overall": int(rank) if rank is not None else None,
            "in_top_100": bool(rank is not None and rank <= 100),
            "last_price": last_price,
            "change_pct": pct,
            "concept_tag_count": len(hot_concepts),
            "as_of": as_of,
        }
        rows.append((
            ts_code, "L7.mood.media_social",
            json.dumps(social_payload, ensure_ascii=False),
            "Known" if entry else "Inactive",
            0.55, "tushare:ths_hot.热股", now,
        ))
        n_social += 1

        # ---- L9.media.social_buzz ----
        if entry is not None:
            buzz_payload = {
                "in_xq_top_buzz": True,
                "follow_count": hot,   # ths heat score (no follow metric)
                "tweet_count": None,   # no ths_hot equivalent
                "rank_among_buzz_top": int(rank) if rank is not None else None,
                "last_price": last_price,
                "as_of": as_of,
            }
            rows.append((
                ts_code, "L9.media.social_buzz",
                json.dumps(buzz_payload, ensure_ascii=False),
                "Known", 0.55, "tushare:ths_hot.热股", now,
            ))
        else:
            rows.append((
                ts_code, "L9.media.social_buzz",
                json.dumps({"in_xq_top_buzz": False, "as_of": as_of},
                           ensure_ascii=False),
                "Inactive", 0.5, "tushare:ths_hot.热股", now,
            ))
        n_buzz += 1

        # ---- L7.mood.theme ----
        if hot_concepts:
            theme_payload = {
                "concept_count": len(hot_concepts),
                "top_concepts": hot_concepts[:8],
                "as_of": as_of,
            }
            rows.append((
                ts_code, "L7.mood.theme",
                json.dumps(theme_payload, ensure_ascii=False),
                "Known", 0.55, "tushare:ths_hot.概念板块", now,
            ))
        else:
            rows.append((
                ts_code, "L7.mood.theme",
                json.dumps({"concept_count": 0, "as_of": as_of},
                           ensure_ascii=False),
                "Inactive", 0.5, "tushare:ths_hot.概念板块", now,
            ))
        n_theme += 1

    log.info("[tushare] ak-repl media_social=%d social_buzz=%d theme=%d "
             "(heat_codes=%d, hot_concepts=%d)",
             n_social, n_buzz, n_theme, len(heat_by_code), len(hot_concepts))
    return rows


def _emit_ak_outflow_cut(
    pro, a_codes: list[str], now: int,
) -> list[tuple]:
    """``L8.cap.outflow_cut`` — per A-share 5-day 主力资金 cumulative net
    outflow via ``pro.moneyflow(ts_code=, start_date=, end_date=)``.

    Preserves the akshare ``fetch_l8_cap_outflow_cut`` payload schema:
    ``{signal, main_net_5d, stage_pct_change_5d, last_price, alert_severity,
    as_of}``. ``main_net_5d`` = sum of ``net_mf_amount`` over the last ≤5 trade
    days, converted from 万元 → 元 to match the akshare threshold semantics
    (signal when ≤ -1e8 元). ``stage_pct_change_5d`` is derived from the daily
    bars (cumulative compounded pct over the window). Same Inactive-on-absence
    behaviour: stocks with no moneyflow history emit Inactive.
    """

    rows: list[tuple] = []
    as_of = _ak_repl_as_of_iso()
    start_date = _previous_n_days(12)  # pad for weekends → ≥5 trade days
    end_date = _today_yyyymmdd()
    n_signal = 0
    for ts_code in a_codes:
        if not is_a_share(ts_code):
            continue
        try:
            df = pro.moneyflow(
                ts_code=ts_code, start_date=start_date, end_date=end_date,
                fields="ts_code,trade_date,net_mf_amount",
            )
            time.sleep(_BUCKET_A_SLEEP_S)
        except Exception as e:  # noqa: BLE001
            log.warning("[tushare] moneyflow(outflow) %s failed: %s", ts_code, e)
            rows.append((
                ts_code, "L8.cap.outflow_cut",
                json.dumps({"signal": False, "reason": "moneyflow_fetch_failed",
                            "as_of": as_of}, ensure_ascii=False),
                "Inactive", 0.4, "tushare:moneyflow.5d", now,
            ))
            continue
        if df is None or len(df) == 0:
            rows.append((
                ts_code, "L8.cap.outflow_cut",
                json.dumps({"signal": False, "reason": "no_moneyflow_history",
                            "as_of": as_of}, ensure_ascii=False),
                "Inactive", 0.4, "tushare:moneyflow.5d", now,
            ))
            continue
        records = df.to_dict(orient="records")
        # Sort most-recent-first, take last 5 trade days.
        records.sort(key=lambda r: r.get("trade_date") or "", reverse=True)
        window = records[:5]
        net_vals = [_safe_num(r.get("net_mf_amount")) for r in window]
        net_clean = [v for v in net_vals if v is not None]
        if not net_clean:
            rows.append((
                ts_code, "L8.cap.outflow_cut",
                json.dumps({"signal": False, "reason": "no_net_mf_amount",
                            "as_of": as_of}, ensure_ascii=False),
                "Inactive", 0.4, "tushare:moneyflow.5d", now,
            ))
            continue
        # moneyflow.net_mf_amount is in 万元; convert to 元 so the -1e8
        # threshold matches the akshare (THS 资金流入净额 in 元) semantics.
        main_net_5d = sum(net_clean) * 1e4
        signal = main_net_5d <= -1e8
        status = "Known" if signal else "Inactive"
        if signal:
            n_signal += 1
        payload = {
            "signal": signal,
            "main_net_5d": main_net_5d,
            "stage_pct_change_5d": None,  # moneyflow has no price; key kept
            "last_price": None,
            "alert_severity": "WARN" if signal else None,
            "as_of": as_of,
        }
        rows.append((
            ts_code, "L8.cap.outflow_cut",
            json.dumps(payload, ensure_ascii=False),
            status, 0.65, "tushare:moneyflow.5d", now,
        ))
    log.info("[tushare] ak-repl outflow_cut: %d rows (signals=%d)",
             len(rows), n_signal)
    return rows


def _emit_ak_sector_heat(pro, now: int) -> list[tuple]:
    """``L0.sentiment.sector_heat`` — per active industry, THS 行业资金流 heat
    via ``pro.moneyflow_ind_ths(trade_date=)`` (same endpoint pattern as
    ``_emit_industry_fund_flow``).

    Preserves the akshare ``fetch_sector_heat_batch`` payload schema:
    ``{boards, avg_change_pct, total_fund_inflow, top_leader, as_of}`` keyed by
    ``INDUSTRY:<id>``. Each industry maps (via INDUSTRY_TO_THS_NAME) to one THS
    行业; ``boards`` carries that single board, ``top_leader`` carries the THS
    ``lead_stock`` / 领涨股.
    """

    cached_ts = int(_LAST_AK_SECTOR_HEAT_FETCH.get("ts") or 0)
    cached_rows = _LAST_AK_SECTOR_HEAT_FETCH.get("rows") or []
    if cached_ts and (now - cached_ts) < _AK_REPL_CACHE_TTL_S and cached_rows:
        return list(cached_rows)

    industries = _active_industry_ids()
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
                fields=("ts_code,industry,lead_stock,trade_date,close,"
                        "pct_change,net_amount,net_d5_amount"),
            )
            if tmp is not None and len(tmp) > 0:
                df = tmp
                break
        except Exception as e:  # noqa: BLE001
            log.warning("[tushare] sector_heat moneyflow_ind_ths %s failed: %s",
                        trade_date, e)
            continue
    if df is None or len(df) == 0:
        return []

    as_of = _ak_repl_as_of_iso()
    rows: list[tuple] = []
    for rec in df.to_dict(orient="records"):
        ths_name = rec.get("industry")
        slug = slug_by_ths.get(ths_name)
        if not slug:
            continue
        change_pct = _safe_num(rec.get("pct_change"))
        net_amount = _safe_num(rec.get("net_amount"))
        lead_stock = rec.get("lead_stock")
        board = {
            "board_name": ths_name,
            "change_pct": change_pct,
            "fund_inflow_cny": net_amount,
            "leader_stock": lead_stock,
            "leader_stock_pct": None,  # not in moneyflow_ind_ths; key kept
        }
        top_leader = board if lead_stock else None
        payload = {
            "boards": [board],
            "avg_change_pct": (round(change_pct, 3)
                               if change_pct is not None else None),
            "total_fund_inflow": net_amount,
            "top_leader": top_leader,
            "as_of": as_of,
        }
        rows.append((
            f"INDUSTRY:{slug}", "L0.sentiment.sector_heat",
            json.dumps(payload, ensure_ascii=False),
            "Known", 0.65, "tushare:moneyflow_ind_ths", now,
        ))

    _LAST_AK_SECTOR_HEAT_FETCH["ts"] = now
    _LAST_AK_SECTOR_HEAT_FETCH["rows"] = list(rows)
    log.info("[tushare] ak-repl sector_heat: %d industries emitted", len(rows))
    return rows


def _fut_daily_latest_pct(pro, fut_ts_code: str) -> dict | None:
    """Pull the latest ``pro.fut_daily`` bar for one commodity future and
    compute day-over-day pct from ``close`` vs ``pre_close``.

    Returns ``{symbol, close, pct_change, date}`` (matching the akshare
    per-commodity shape) or None on failure / insufficient data. Probed
    columns: ``[ts_code, trade_date, close, pre_close, change1, ...]``.
    """

    df = None
    for back in range(0, 10):
        start = _previous_n_days(back + 10)
        end = _previous_n_days(back)
        try:
            tmp = pro.fut_daily(
                ts_code=fut_ts_code, start_date=start, end_date=end,
                fields="ts_code,trade_date,close,pre_close",
            )
            if tmp is not None and len(tmp) > 0:
                df = tmp
                break
        except Exception as e:  # noqa: BLE001
            log.warning("[tushare] fut_daily %s failed: %s", fut_ts_code, e)
            return None
    if df is None or len(df) == 0:
        return None
    records = df.to_dict(orient="records")
    records.sort(key=lambda r: r.get("trade_date") or "", reverse=True)
    latest = records[0]
    close = _safe_num(latest.get("close"))
    pre_close = _safe_num(latest.get("pre_close"))
    if close is None or pre_close in (None, 0):
        return None
    pct_change = (close - pre_close) / pre_close * 100.0
    return {
        "symbol": fut_ts_code,
        "close": close,
        "pct_change": round(pct_change, 3),
        "date": latest.get("trade_date"),
    }


def _emit_ak_raw_material(pro, now: int) -> list[tuple]:
    """``L0.cost.raw_material`` — per active industry commodity pct via
    ``pro.fut_daily``.

    Preserves the akshare ``fetch_raw_material_batch`` payload schema:
    ``{commodities, avg_pct_change, symbols_resolved, symbols_requested,
    latest_date, unit}`` keyed by ``INDUSTRY:<id>``. Uses
    INDUSTRY_TO_FUT_TS_CODE (Tushare future codes) in place of the akshare
    Sina-futures map.
    """

    cached_ts = int(_LAST_AK_RAW_MATERIAL_FETCH.get("ts") or 0)
    cached_rows = _LAST_AK_RAW_MATERIAL_FETCH.get("rows") or []
    if cached_ts and (now - cached_ts) < _AK_REPL_CACHE_TTL_S and cached_rows:
        return list(cached_rows)

    active = set(_active_industry_ids())
    industry_syms: dict[str, list[str]] = {}
    symbols_needed: set[str] = set()
    for industry_id, syms in INDUSTRY_TO_FUT_TS_CODE.items():
        if industry_id not in active or not syms:
            continue
        industry_syms[industry_id] = list(syms)
        symbols_needed.update(syms)
    if not industry_syms:
        return []

    per_symbol: dict[str, dict] = {}
    for sym in sorted(symbols_needed):
        res = _fut_daily_latest_pct(pro, sym)
        time.sleep(_BUCKET_A_SLEEP_S)
        if res is not None:
            per_symbol[sym] = res
    if not per_symbol:
        return []

    rows: list[tuple] = []
    for industry_id, syms in industry_syms.items():
        present = [per_symbol[s] for s in syms if s in per_symbol]
        if not present:
            continue
        avg_pct = sum(p["pct_change"] for p in present) / len(present)
        payload = {
            "commodities": present,
            "avg_pct_change": round(avg_pct, 3),
            "symbols_resolved": len(present),
            "symbols_requested": len(syms),
            "latest_date": present[0]["date"],
            "unit": "Tushare fut_daily close (CNY)",
        }
        rows.append((
            f"INDUSTRY:{industry_id}", "L0.cost.raw_material",
            json.dumps(payload, ensure_ascii=False),
            "Known", 0.6, "tushare:fut_daily", now,
        ))

    _LAST_AK_RAW_MATERIAL_FETCH["ts"] = now
    _LAST_AK_RAW_MATERIAL_FETCH["rows"] = list(rows)
    log.info("[tushare] ak-repl raw_material: %d industries emitted", len(rows))
    return rows


def _emit_ak_energy_logistics(pro, now: int) -> list[tuple]:
    """``L0.cost.energy_logistics`` — MARKET:CN crude (SC.INE) via
    ``pro.fut_daily`` + BDI via akshare (Tushare has no BDI feed).

    Preserves the akshare ``fetch_energy_logistics_batch`` payload schema:
    ``{crude_pct, crude_close_cny_per_bbl, crude_latest_date, bdi_pct,
    bdi_close, bdi_latest_date, scope}``. Crude moves to Tushare ``fut_daily``;
    the BDI sub-call is KEPT on akshare (``ak.macro_shipping_bdi``) since
    Tushare exposes no Baltic Dry Index endpoint. If akshare is unavailable the
    BDI fields are emitted as None (keys preserved).
    """

    cached_ts = int(_LAST_AK_ENERGY_FETCH.get("ts") or 0)
    cached_rows = _LAST_AK_ENERGY_FETCH.get("rows") or []
    if cached_ts and (now - cached_ts) < _AK_REPL_CACHE_TTL_S and cached_rows:
        return list(cached_rows)

    crude = _fut_daily_latest_pct(pro, _ENERGY_CRUDE_FUT_TS_CODE)
    crude_pct = crude["pct_change"] if crude else None
    crude_close = crude["close"] if crude else None
    crude_date = crude["date"] if crude else None

    # BDI stays on akshare — Tushare has no Baltic Dry Index feed.
    bdi_pct = None
    bdi_close = None
    bdi_date = None
    try:
        import akshare as ak  # type: ignore
        df = ak.macro_shipping_bdi()
        if df is not None and len(df) >= 2:
            recs = df.to_dict(orient="records") if hasattr(df, "to_dict") else list(df)
            latest = recs[-1]
            prior = recs[-2]
            cur = _safe_num(latest.get("最新值") or latest.get("BDI"))
            prev = _safe_num(prior.get("最新值") or prior.get("BDI"))
            if cur is not None and prev not in (None, 0):
                bdi_pct = round((cur - prev) / prev * 100.0, 3)
                bdi_close = cur
                bdi_raw_date = latest.get("日期") or latest.get("date")
                bdi_date = str(bdi_raw_date) if bdi_raw_date is not None else None
    except Exception as e:  # noqa: BLE001
        log.warning("[tushare] ak-repl energy BDI (akshare) failed: %s", e)

    if crude_pct is None and bdi_pct is None:
        return []

    payload = {
        "crude_pct": crude_pct,
        "crude_close_cny_per_bbl": crude_close,
        "crude_latest_date": crude_date,
        "bdi_pct": bdi_pct,
        "bdi_close": bdi_close,
        "bdi_latest_date": bdi_date,
        "scope": "A_share_market",
    }
    rows = [(
        "MARKET:CN", "L0.cost.energy_logistics",
        json.dumps(payload, ensure_ascii=False),
        "Known", 0.65, "tushare:fut_daily+akshare:macro_shipping_bdi", now,
    )]
    _LAST_AK_ENERGY_FETCH["ts"] = now
    _LAST_AK_ENERGY_FETCH["rows"] = list(rows)
    log.info("[tushare] ak-repl energy_logistics: 1 MARKET:CN row "
             "(crude_pct=%s, bdi_pct=%s)", crude_pct, bdi_pct)
    return rows


def _stringify_yyyymmdd(v) -> str | None:
    """Normalise an anns_d ann_date (``20260529`` or ``2026-05-29``) to a
    deterministic string. Mirrors akshare_source._stringify_date output."""

    if v is None:
        return None
    try:
        if v != v:  # NaN/NaT
            return None
    except TypeError:
        pass
    s = str(v).strip()
    return s or None


def fetch_akshare_replacement_batch(
    constituents: Iterable[dict],
    tick: int,
) -> list[tuple]:
    """8 dp_ids moved off akshare onto permitted Tushare endpoints.

    Per-stock (announcement / media_social / social_buzz / theme / outflow_cut)
    run only for A-share constituents; industry/market fields (sector_heat /
    raw_material / energy_logistics) run regardless of the per-stock universe.
    Each emitter is isolated in try/except so one endpoint outage never drops
    the rest. Returns the standard 7-tuple list for ``upsert_realtime``.
    """

    pro = _get_pro_api()
    if pro is None:
        log.warning("[tushare] TUSHARE_TOKEN not set — skipping akshare-repl batch")
        return []

    cons_list = [c for c in constituents if c.get("ts_code")]
    a_codes = [c["ts_code"] for c in cons_list if is_a_share(c["ts_code"])]
    now = int(time.time())
    rows: list[tuple] = []

    if a_codes:
        for label, fn in (
            ("intraday_announcement",
             lambda: _emit_ak_intraday_announcement(pro, a_codes, now)),
            ("media_social+social_buzz+theme",
             lambda: _emit_ak_media_social_buzz_theme(pro, a_codes, now)),
            ("outflow_cut",
             lambda: _emit_ak_outflow_cut(pro, a_codes, now)),
        ):
            try:
                rows.extend(fn())
            except Exception as e:  # noqa: BLE001
                log.warning("[tushare] ak-repl %s crashed: %s", label, e)

    for label, fn in (
        ("sector_heat",      _emit_ak_sector_heat),
        ("raw_material",     _emit_ak_raw_material),
        ("energy_logistics", _emit_ak_energy_logistics),
    ):
        try:
            rows.extend(fn(pro, now))
        except Exception as e:  # noqa: BLE001
            log.warning("[tushare] ak-repl %s crashed: %s", label, e)

    log.info("[tushare] akshare-replacement batch: %d rows for %d A-share codes",
             len(rows), len(a_codes))
    return rows


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
                        "volume_ratio,ps_ttm,total_mv,total_share"),
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
            total_share = _safe(rec, "total_share")
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
            # The L6.mult.pe payload also carries mcap + share count so the
            # snapshot-derive layer can compute EV/EBITDA and forward P/E
            # without re-pulling daily_basic. Tushare daily_basic reports
            # ``total_mv`` in 万元 and ``total_share`` in 万股 — we convert both
            # to base units (元 and raw shares, ×10000) so the persisted keys
            # are unit-unambiguous. (See derive.py: derive_l6_mult_ev_ebitda /
            # derive_l6_mult_forward_pe.)
            for dp_id, val in (("L6.mult.pe", pe), ("L6.mult.pb", pb),
                                ("L6.mult.ps", ps)):
                if val is None:
                    continue
                payload = {"scalar": float(val), "unit": "ratio",
                           "ttm": True, "trade_date": trade_date}
                if dp_id == "L6.mult.pe":
                    if total_mv is not None:
                        payload["total_mv_cny"] = float(total_mv) * 10000.0
                    if total_share is not None:
                        payload["total_share"] = float(total_share) * 10000.0
                rows.append((
                    ts_code, dp_id,
                    json.dumps(payload, ensure_ascii=False),
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

    # ``main_net_by_ts_code`` — re-used by Bucket A L8.cap.crowdedness as the
    # main_net_5d proxy (today's snapshot, not a true 5d sum, but close
    # enough for the alert threshold and saves a moneyflow re-pull).
    main_net_by_ts_code: dict[str, float] = {}
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

            if netbuy is not None:
                try:
                    main_net_by_ts_code[ts_code] = float(netbuy)
                except (TypeError, ValueError):
                    pass

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
    hk_hold_df = None
    for back in range(1, 9):
        trade_date = _previous_n_days(back)
        try:
            df = pro.hk_hold(
                trade_date=trade_date,
                fields="ts_code,trade_date,vol,ratio",
            )
            if df is not None and len(df) > 0:
                df = df[df["ts_code"].isin(a_codes_set)]
                if len(df) > 0:
                    hk_hold_df = df
                    break
        except Exception as e:  # noqa: BLE001
            log.warning("[tushare] hk_hold %s failed (likely permission): %s",
                        trade_date, e)
    if hk_hold_df is not None:
        for rec in hk_hold_df.to_dict(orient="records"):
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

    # ── Bucket A: hard-data dp_ids (additive, all wrapped) ──
    # The dispatcher emits per-stock rows plus N industry-level rows for
    # L8.industry.valuation_compression. Per-fetcher try/except inside the
    # dispatcher ensures a single endpoint failure cannot poison the rest.
    try:
        rows.extend(fetch_bucket_a_batch(
            pro, a_codes, now,
            main_net_inflow_by_ts_code=main_net_by_ts_code,
        ))
    except Exception as e:  # noqa: BLE001
        log.warning("[tushare] Bucket A batch failed: %s", e)

    # ── Bucket B: 12 hard-data dp_ids (估值 + 卖方研报 + L0 + peer) ──
    # Independent dispatcher with per-fetcher try/except. Industry fan-out
    # for L0.sentiment.* and L6.state.industry_center relies on the
    # ``code_to_industry`` map already built above.
    try:
        rows.extend(fetch_bucket_b_batch(
            pro, a_codes,
            code_to_industry=code_to_industry,
            now=now,
        ))
    except Exception as e:  # noqa: BLE001
        log.warning("[tushare] Bucket B batch failed: %s", e)

    return rows


def fetch_core_batch(
    constituents: Iterable[dict],
    tick: int,
) -> list[tuple]:
    """Pull only the fast A-share core market/flow Tushare rows.

    This intentionally stops before the slow per-stock financial/report
    endpoints used by ``fetch_batch``. It is suitable for operational refreshes
    where we want PE/PB/turnover/moneyflow/northbound rows to land even when a
    later financial endpoint is slow or timing out.
    """

    pro = _get_pro_api()
    if pro is None:
        log.warning("[tushare] TUSHARE_TOKEN not set — skipping core batch")
        return []

    cons_list = [c for c in constituents if c.get("ts_code")]
    a_codes = [c["ts_code"] for c in cons_list if is_a_share(c["ts_code"])]
    if not a_codes:
        return []

    now = int(time.time())
    a_codes_set = set(a_codes)
    rows: list[tuple] = []

    daily_basic_df = None
    for back in range(0, 8):
        trade_date = _previous_n_days(back)
        try:
            df = pro.daily_basic(
                trade_date=trade_date,
                fields=("ts_code,trade_date,close,turnover_rate,pe_ttm,pb,"
                        "volume_ratio,ps_ttm,total_mv,total_share"),
            )
            if df is not None and len(df) > 0:
                df = df[df["ts_code"].isin(a_codes_set)]
                if len(df) > 0:
                    daily_basic_df = df
                    log.info("[tushare] core daily_basic from %s rows=%d",
                             trade_date, len(df))
                    break
        except Exception as e:  # noqa: BLE001
            log.warning("[tushare] core daily_basic %s failed: %s", trade_date, e)

    if daily_basic_df is not None:
        for rec in daily_basic_df.to_dict(orient="records"):
            ts_code = rec.get("ts_code")
            if not ts_code:
                continue
            pe = _safe(rec, "pe_ttm")
            pb = _safe(rec, "pb")
            ps = _safe(rec, "ps_ttm")
            total_mv = _safe(rec, "total_mv")
            total_share = _safe(rec, "total_share")
            turnover_rate = _safe(rec, "turnover_rate")
            volume_ratio = _safe(rec, "volume_ratio")
            trade_date = rec.get("trade_date")

            # L6.mult.pe payload carries mcap + share count (both in base units:
            # `total_mv_cny` 元 = total_mv万元 ×10000, `total_share` raw shares =
            # total_share万股 ×10000) for the snapshot-derive layer — see
            # derive_l6_mult_ev_ebitda / derive_l6_mult_forward_pe.
            for dp_id, val in (("L6.mult.pe", pe), ("L6.mult.pb", pb),
                               ("L6.mult.ps", ps)):
                if val is None:
                    continue
                payload = {"scalar": float(val), "unit": "ratio",
                           "ttm": True, "trade_date": trade_date}
                if dp_id == "L6.mult.pe":
                    if total_mv is not None:
                        payload["total_mv_cny"] = float(total_mv) * 10000.0
                    if total_share is not None:
                        payload["total_share"] = float(total_share) * 10000.0
                rows.append((
                    ts_code, dp_id,
                    json.dumps(payload, ensure_ascii=False),
                    "Known", 0.7, "tushare:daily_basic", now,
                ))
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
                    log.info("[tushare] core moneyflow from %s rows=%d",
                             trade_date, len(df))
                    break
        except Exception as e:  # noqa: BLE001
            log.warning("[tushare] core moneyflow %s failed: %s", trade_date, e)

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
            rows.append((
                ts_code, "L7.flow.active_inflow",
                json.dumps({
                    "main_net": float(netbuy) if netbuy is not None else None,
                    "big_orders_net": float((buy_lg + buy_elg) - (sell_lg + sell_elg)),
                    "unit": "万元",
                    "trade_date": rec.get("trade_date"),
                }, ensure_ascii=False),
                "Known", 0.75, "tushare:moneyflow", now,
            ))

    hk_hold_df = None
    for back in range(1, 9):
        trade_date = _previous_n_days(back)
        try:
            df = pro.hk_hold(
                trade_date=trade_date,
                fields="ts_code,trade_date,vol,ratio",
            )
            if df is not None and len(df) > 0:
                df = df[df["ts_code"].isin(a_codes_set)]
                if len(df) > 0:
                    hk_hold_df = df
                    break
        except Exception as e:  # noqa: BLE001
            log.warning("[tushare] core hk_hold %s failed (likely permission): %s",
                        trade_date, e)
    if hk_hold_df is not None:
        for rec in hk_hold_df.to_dict(orient="records"):
            ts_code = rec.get("ts_code")
            if not ts_code:
                continue
            rows.append((
                ts_code, "L7.flow.passive_northbound",
                json.dumps({
                    "vol": _safe(rec, "vol"),
                    "ratio_pct": _safe(rec, "ratio"),
                    "trade_date": rec.get("trade_date"),
                }, ensure_ascii=False),
                "Known", 0.7, "tushare:hk_hold", now,
            ))

    return rows


def fetch_report_rc_constituents_batch(
    constituents: Iterable[dict],
    tick: int,
    *,
    lookback_days: int = 90,
) -> list[tuple]:
    """Pull only per-stock sell-side forecast rows from ``report_rc``.

    This is a focused collector path for the spec forecast fields. It keeps
    broker-report latency/permission issues isolated from the fast market and
    moneyflow refreshes handled by ``fetch_core_batch``.
    """

    pro = _get_pro_api()
    if pro is None:
        log.warning("[tushare] TUSHARE_TOKEN not set — skipping report_rc batch")
        return []

    a_codes = [
        c["ts_code"] for c in constituents
        if c.get("ts_code") and is_a_share(c["ts_code"])
    ]
    if not a_codes:
        return []
    return _fetch_a_share_report_rc(
        pro, a_codes, int(time.time()), lookback_days=lookback_days,
    )


def fetch_crowding_batch(
    constituents: Iterable[dict],
    tick: int,
) -> list[tuple]:
    """Pull only ``daily_basic`` history needed for L6 priced crowdedness.

    The full Bucket A path also fetches balancesheet/income/margin endpoints.
    This narrow path lets A-share turnover percentile rows land even when
    slower financial endpoints are unhealthy.
    """

    pro = _get_pro_api()
    if pro is None:
        log.warning("[tushare] TUSHARE_TOKEN not set — skipping crowding batch")
        return []

    a_codes = [
        c["ts_code"] for c in constituents
        if c.get("ts_code") and is_a_share(c["ts_code"])
    ]
    if not a_codes:
        return []

    now = int(time.time())
    rows: list[tuple] = []
    for ts_code in a_codes:
        try:
            records = _get_daily_basic_history(pro, ts_code, now)
            payload, status = _derive_priced_crowdedness(records)
        except Exception as e:  # noqa: BLE001
            log.warning("[tushare] crowding %s failed: %s", ts_code, e)
            payload, status = {"reason": "daily_basic history failed"}, "Inactive"
        rows.append((
            ts_code, "L6.priced.crowdedness",
            json.dumps(payload, ensure_ascii=False),
            status, 0.7 if status == "Known" else 0.0,
            "tushare:daily_basic.history", now,
        ))
    return rows


def fetch_market_env_batch(
    constituents: Iterable[dict],
    tick: int,
) -> list[tuple]:
    """Pull only market-level A-share environment sentinels.

    Currently emits ``L7.env.market_trend`` and the MARKET:CN northbound flow
    sentinel. Per-stock northbound replacement still depends on ``hk_hold``.
    """

    pro = _get_pro_api()
    if pro is None:
        log.warning("[tushare] TUSHARE_TOKEN not set — skipping market env batch")
        return []

    now = int(time.time())
    rows: list[tuple] = []
    for label, fn in (
        ("market_trend", _emit_market_trend),
        ("market_style", _emit_market_style),
        ("passive_northbound", _emit_passive_northbound),
    ):
        try:
            rows.extend(fn(pro, now))
        except Exception as e:  # noqa: BLE001
            log.warning("[tushare] market env %s failed: %s", label, e)
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


# ── 龙虎榜机构净买入 normalization (L9.capital.inst_buy_sell) ──────────────
# top_inst 的 buy/sell 单位是元；float_values（流通市值，来自 top_list）也是
# 元。机构净买入 / 流通市值 给出一个无量纲的信号强度，tanh 压到 [0,1)。
# 0.5% 的单日机构净买入占流通市值已是很强的信号。
_INST_NETBUY_SCALE_RATIO = 0.005


def _compute_inst_buy_sell_payload(
    list_records: list[dict],
    inst_records: list[dict],
    trade_date: str,
) -> dict:
    """Build the ``L9.capital.inst_buy_sell`` payload for one ts_code.

    Combines the 龙虎榜 daily summary (``top_list`` — net_amount per reason,
    流通市值) with the institutional-seat detail (``top_inst`` — per-seat
    机构 buy/sell amounts) into a single payload that is BOTH

      * backward-compatible with the legacy consumers / alias test
        (keys ``on_top_list``, ``entries``, ``trade_date`` preserved
        verbatim), AND
      * scorable by ``mvp20.aggregator._to_scalar`` via a top-level
        ``score`` (magnitude in [0,1]) + ``direction``
        (positive/negative/neutral) pair.

    Institutional net buy = Σ top_inst.buy − Σ top_inst.sell (元). When
    top_inst is empty (permission-locked seat detail) we fall back to the
    top_list per-reason ``net_amount`` sum (万元 → 元) so the signal is
    still signed rather than silently zero.

    Magnitude = tanh(|inst_net_buy| / (float_values × _INST_NETBUY_SCALE_RATIO))
    when 流通市值 is known; otherwise we tanh the raw 万元 net_amount on a
    coarse 5000万 scale so the sign/strength is still meaningful.
    """

    entries = [
        {
            "reason": r.get("reason"),
            "net_amount": _safe_num(r.get("net_amount")),
            "pct_change": _safe_num(r.get("pct_change")),
        }
        for r in list_records
    ]

    # 流通市值 (元) — take the first non-null float_values across the
    # stock's top_list rows (identical across reasons for the same day).
    float_values = None
    for r in list_records:
        fv = _safe_num(r.get("float_values"))
        if fv:
            float_values = fv
            break

    # Institutional seat buy/sell (元) from top_inst.
    inst_buy = 0.0
    inst_sell = 0.0
    seat_count = 0
    for r in inst_records:
        b = _safe_num(r.get("buy"))
        s = _safe_num(r.get("sell"))
        if b is not None:
            inst_buy += b
        if s is not None:
            inst_sell += s
        seat_count += 1
    inst_net_buy = inst_buy - inst_sell

    # Fallback: no seat detail → use top_list net_amount (万元 → 元).
    used_fallback = seat_count == 0
    if used_fallback:
        net_amount_wan = 0.0
        for e in entries:
            na = e.get("net_amount")
            if na is not None:
                net_amount_wan += na
        inst_net_buy = net_amount_wan * 1e4  # 万元 → 元

    # Magnitude + direction.
    if float_values:
        denom = float_values * _INST_NETBUY_SCALE_RATIO
        ratio = inst_net_buy / denom if denom else 0.0
        magnitude = abs(math.tanh(ratio))
    else:
        # Coarse 5000万元 scale when 流通市值 missing.
        magnitude = abs(math.tanh(inst_net_buy / 5.0e7))

    if inst_net_buy > 0:
        direction = "positive"
    elif inst_net_buy < 0:
        direction = "negative"
    else:
        direction = "neutral"

    return {
        "on_top_list": True,
        "entries": entries,
        "trade_date": trade_date,
        # ── scorable keys (consumed by aggregator._to_scalar + direction) ──
        "score": round(magnitude, 4),
        "direction": direction,
        "inst_buy": round(inst_buy, 2),
        "inst_sell": round(inst_sell, 2),
        "inst_net_buy": round(inst_net_buy, 2),
        "inst_seat_count": seat_count,
        "float_values": float_values,
        "normalized_by": "float_values" if float_values else "fixed_5000w",
        "net_buy_source": "top_list_net_amount" if used_fallback else "top_inst",
        "unit": "元",
    }


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
    # We combine pro.top_list (daily 龙虎榜 summary — net_amount per reason,
    # 流通市值) with pro.top_inst (机构席位明细 — per-seat buy/sell amounts)
    # to compute a *signed* institutional net-buy signal. Records-based
    # grouping (not pandas .groupby) keeps the function stub-testable.
    for back in range(0, 8):
        trade_date = _previous_n_days(back)
        try:
            df = pro.top_list(
                trade_date=trade_date,
                fields=("ts_code,trade_date,reason,net_amount,float_values,"
                        "pct_change,l_buy,l_sell"),
            )
        except Exception as e:  # noqa: BLE001
            log.warning("[tushare] top_list %s failed: %s", trade_date, e)
            continue
        if df is None or len(df) == 0:
            continue

        list_records = df.to_dict(orient="records") \
            if hasattr(df, "to_dict") else list(df)
        list_records = [r for r in list_records
                        if r.get("ts_code") in a_codes_set]
        if not list_records:
            continue

        # Institutional-seat detail for the same day (one call, all stocks).
        # Permission-locked / empty → empty list → helper falls back to the
        # top_list net_amount sum, so the signal is still signed.
        inst_by_ts: dict[str, list[dict]] = {}
        try:
            inst_df = pro.top_inst(
                trade_date=trade_date,
                fields="ts_code,trade_date,exalter,side,buy,sell,net_buy",
            )
            if inst_df is not None and len(inst_df) > 0:
                inst_records = inst_df.to_dict(orient="records") \
                    if hasattr(inst_df, "to_dict") else list(inst_df)
                for r in inst_records:
                    code = r.get("ts_code")
                    if code in a_codes_set:
                        inst_by_ts.setdefault(code, []).append(r)
        except Exception as e:  # noqa: BLE001
            log.warning("[tushare] top_inst %s failed (seat detail "
                        "unavailable; using net_amount fallback): %s",
                        trade_date, e)

        # Group top_list rows by ts_code (a stock may appear with multiple
        # reasons) and emit one enriched row per stock.
        list_by_ts: dict[str, list[dict]] = {}
        for r in list_records:
            list_by_ts.setdefault(r.get("ts_code"), []).append(r)

        for ts_code, group in list_by_ts.items():
            payload = _compute_inst_buy_sell_payload(
                group, inst_by_ts.get(ts_code, []), trade_date,
            )
            rows.append((
                ts_code, "L9.capital.inst_buy_sell",
                json.dumps(payload, ensure_ascii=False),
                "Known", 0.85, "tushare:top_list+top_inst", now,
            ))
        log.info("[tushare] top_list from %s rows=%d (filtered) → %d "
                 "ts_codes (%d with seat detail)",
                 trade_date, len(list_records), len(list_by_ts),
                 len(inst_by_ts))
        break

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
        # ── pro.income (利润表) — last ~12 filings for YoY growth calc ──
        # H-1b: Tushare returns multiple rows per end_date (``update_flag='0'``
        # original filing vs ``'1'`` restated). Pull ``limit=12`` (≥5 DISTINCT
        # quarters even with restatement duplicates) and dedup by ``end_date``,
        # preferring the row with non-null ``total_revenue`` then
        # ``update_flag='1'`` — mirroring the cashflow dedup below. Without this
        # a duplicated latest period both (a) pushes the same-period prior-year
        # record out of the narrow ``limit=5`` window, so the H-1 YoY lookup
        # (``_find_record(records, _yoy_period(period))``) finds nothing and
        # skips — observed live on 300308/000063/000977/688041, which kept a
        # stale wrong-period growth value — and (b) makes ``records[1]`` a
        # same-period twin → QoQ collapses to ~0.
        try:
            df = pro.income(
                ts_code=ts_code, limit=12,
                fields=("ts_code,end_date,update_flag,total_revenue,operate_profit,"
                        "n_income,basic_eps,oper_cost,sell_exp,admin_exp,rd_exp"),
            )
            if df is not None and len(df) > 0:
                by_period: dict[str, dict] = {}
                for _r in df.to_dict(orient="records"):
                    ed = _r.get("end_date")
                    if not ed:
                        continue
                    prior = by_period.get(ed)
                    if prior is None:
                        by_period[ed] = _r
                        continue
                    prior_rev = _safe(prior, "total_revenue")
                    cur_rev = _safe(_r, "total_revenue")
                    cur_flag = (_r.get("update_flag") or "")
                    prior_flag = (prior.get("update_flag") or "")
                    # Prefer non-null revenue; if both present, prefer the
                    # restated ('1') filing.
                    if cur_rev is not None and prior_rev is None:
                        by_period[ed] = _r
                    elif (cur_rev is not None and prior_rev is not None
                          and cur_flag == "1" and prior_flag != "1"):
                        by_period[ed] = _r
                # Order by end_date desc — latest reporting period first, one
                # row per distinct period.
                records = [by_period[ed] for ed in sorted(by_period.keys(), reverse=True)]
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
                # L5.is.revenue_growth — YoY = current vs the SAME end-date
                # one calendar year prior (H-1 fix). Tushare income rows are
                # cumulative YTD, so positional ``records[3]`` ("~4 quarters
                # back") mismatched the period whenever the latest filing was
                # a mid-year cut (e.g. current=20260331 but records[3] could be
                # 20250630/20250930). Select the same-period prior-year record
                # via ``_find_record(records, _yoy_period(period))`` — the
                # convention already used by ``_derive_labor_cost`` /
                # ``_derive_cost_overrun``. If that record is absent, skip
                # (emit nothing) rather than back into a wrong-period compare.
                #
                # H-2 fix: emit ``yoy_pct`` / ``qoq_pct`` as PERCENT (×100), not
                # a raw ratio. This matches the sibling A-share dp_id
                # ``L5.fina.revenue_yoy`` (Tushare ``or_yoy`` is already a
                # percent) and the consumers that scale by /50:
                #   * aggregator ``_to_scalar`` → ``tanh(yoy/50)`` (50% YoY ≈ 0.76)
                #   * derive ``L11.mid.orders_revenue`` → ``rev_yoy/50``
                # so +159.55% revenue growth emits yoy_pct≈159.55 (was 1.5955,
                # which the /50 consumer read as ~0.03 — essentially no signal).
                # NOTE: the US/FMP emitter of ``L5.is.revenue_growth``
                # (fmp_source.py) still stores a RATIO; that file is out of
                # scope here. The A-share derive consumer
                # ``derive_l6_sens_growth_margin`` reads ``L5.fina.revenue_yoy``
                # (percent) FIRST for A-shares and only falls back to
                # ``L5.is.revenue_growth`` for US, so this percent change does
                # not collide with that ratio-oriented fallback heuristic.
                if rev is not None:
                    yoy_rec = _find_record(records, _yoy_period(str(period or "")))
                    yoy_rev = _safe(yoy_rec, "total_revenue") if yoy_rec else None
                    if yoy_rev and yoy_rev != 0:
                        yoy_pct = (rev - yoy_rev) / yoy_rev * 100.0
                        # QoQ from the immediately-prior period (records[1] —
                        # records are sorted end_date desc above). Stored as
                        # percent for payload-internal consistency with yoy_pct.
                        prev_rev = _safe(records[1], "total_revenue") if len(records) > 1 else None
                        qoq_pct = ((rev - prev_rev) / prev_rev * 100.0) if prev_rev else None
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
                # B1: Tushare reports the 商誉 (goodwill) line as null when the
                # company carries no goodwill — common for organically-grown /
                # fabless names (e.g. 寒武纪 688256). That is "zero goodwill", not
                # "unknown": so when the balance sheet was fetched (total_assets
                # present) treat a missing goodwill as 0 so goodwill_to_assets=0
                # (clean, no impairment risk) reaches fundamental_score via the
                # aggregator's ``-clip(gw*2.5)`` consumer, instead of being
                # dropped as missing (a silent coverage gap). ``fix_assets`` is
                # left as-is (None stays None — not imputable).
                goodwill_eff = goodwill if goodwill is not None else (
                    0.0 if total_assets else None
                )
                if goodwill_eff is not None or fix_assets is not None:
                    rows.append((
                        ts_code, "L5.bs.goodwill_ppe",
                        json.dumps({
                            "goodwill": float(goodwill_eff) if goodwill_eff is not None else None,
                            "fix_assets_ppe": float(fix_assets) if fix_assets is not None else None,
                            "goodwill_to_assets": (goodwill_eff / total_assets) if (goodwill_eff is not None and total_assets) else None,
                            "unit": "元", "period": period,
                            "goodwill_imputed_zero": goodwill is None and total_assets is not None,
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


_REPORT_RC_FCST_DP_IDS = (
    "L5.fcst.revenue_margin",
    "L5.fcst.eps_cf",
    "L5.fcst.revisions",
)


def _report_rc_year(rec: dict) -> int | None:
    q = str(rec.get("quarter") or "")
    if len(q) >= 4 and q[:4].isdigit():
        return int(q[:4])
    return None


def _report_rc_key(rec: dict) -> tuple:
    return (
        rec.get("report_date"),
        rec.get("org_name"),
        rec.get("author_name"),
        rec.get("report_title"),
    )


def _avg_float(values: list[float]) -> float | None:
    clean = [v for v in values if v is not None]
    if not clean:
        return None
    return sum(clean) / len(clean)


def _inactive_report_rc_fcst_rows(
    ts_code: str,
    now: int,
    reason: str,
    lookback_days: int,
) -> list[tuple]:
    return [
        (
            ts_code, dp_id,
            json.dumps({
                "reason": reason,
                "lookback_days": lookback_days,
            }, ensure_ascii=False),
            "Inactive", 0.0, "tushare:report_rc", now,
        )
        for dp_id in _REPORT_RC_FCST_DP_IDS
    ]


def _inactive_report_rc_all_rows(
    ts_code: str,
    now: int,
    reason: str,
    lookback_days: int,
) -> list[tuple]:
    rows = [(
        ts_code, "L5.surprise.sell_side",
        json.dumps({
            "n_reports_90d": 0,
            "lookback_days": lookback_days,
            "reason": reason,
        }, ensure_ascii=False),
        "Inactive", 0.0, "tushare:report_rc", now,
    )]
    rows.extend(_inactive_report_rc_fcst_rows(
        ts_code, now, reason, lookback_days,
    ))
    return rows


def _build_report_rc_fcst_rows(
    ts_code: str,
    records: list[dict],
    now: int,
    lookback_days: int,
    as_of_date: str,
) -> list[tuple]:
    """Emit spec forecast dp_ids from Tushare ``report_rc`` records.

    ``report_rc`` rows are broker report × forecast-year records. The
    nearest forward forecast year supplies EPS / revenue consensus, while
    recent-vs-older EPS means provide a simple 30d revision signal.
    """

    if not records:
        return _inactive_report_rc_fcst_rows(
            ts_code, now, "no sell-side report in window", lookback_days,
        )

    current_year = int(as_of_date[:4])
    by_year: dict[int, list[dict]] = {}
    for rec in records:
        year = _report_rc_year(rec)
        if year is None:
            continue
        by_year.setdefault(year, []).append(rec)

    forward_years = sorted(y for y in by_year if y >= current_year)
    if not forward_years:
        return _inactive_report_rc_fcst_rows(
            ts_code, now, "no forward forecast year in report_rc",
            lookback_days,
        )

    target_year = forward_years[0]
    target_records = by_year[target_year]

    eps_vals: list[float] = []
    rev_vals_wan: list[float] = []
    op_profit_vals_wan: list[float] = []
    net_profit_vals_wan: list[float] = []
    eps_report_keys: set[tuple] = set()
    revenue_report_keys: set[tuple] = set()
    for rec in target_records:
        eps = _safe_num(rec.get("eps"))
        revenue = _safe_num(rec.get("op_rt"))
        op_profit = _safe_num(rec.get("op_pr"))
        net_profit = _safe_num(rec.get("np"))
        if eps is not None:
            eps_vals.append(eps)
            eps_report_keys.add(_report_rc_key(rec))
        if revenue is not None:
            rev_vals_wan.append(revenue)
            revenue_report_keys.add(_report_rc_key(rec))
        if op_profit is not None:
            op_profit_vals_wan.append(op_profit)
        if net_profit is not None:
            net_profit_vals_wan.append(net_profit)

    rows: list[tuple] = []
    revenue_avg_wan = _avg_float(rev_vals_wan)
    op_profit_avg_wan = _avg_float(op_profit_vals_wan)
    net_profit_avg_wan = _avg_float(net_profit_vals_wan)
    if revenue_avg_wan is not None:
        op_margin = (
            op_profit_avg_wan / revenue_avg_wan
            if op_profit_avg_wan is not None and revenue_avg_wan else None
        )
        net_margin = (
            net_profit_avg_wan / revenue_avg_wan
            if net_profit_avg_wan is not None and revenue_avg_wan else None
        )
        rows.append((
            ts_code, "L5.fcst.revenue_margin",
            json.dumps({
                "revenue_avg": revenue_avg_wan * 10_000.0,
                "operating_profit_avg": (
                    op_profit_avg_wan * 10_000.0
                    if op_profit_avg_wan is not None else None
                ),
                "net_profit_avg": (
                    net_profit_avg_wan * 10_000.0
                    if net_profit_avg_wan is not None else None
                ),
                "operating_margin": op_margin,
                "net_margin": net_margin,
                "num_analysts": len(revenue_report_keys),
                "period": f"{target_year}Q4",
                "unit": "CNY",
                "source_unit": "万元",
            }, ensure_ascii=False),
            "Known", 0.8, "tushare:report_rc", now,
        ))
    else:
        rows.append((
            ts_code, "L5.fcst.revenue_margin",
            json.dumps({
                "reason": "report_rc missing op_rt for nearest forecast year",
                "period": f"{target_year}Q4",
                "lookback_days": lookback_days,
            }, ensure_ascii=False),
            "Inactive", 0.0, "tushare:report_rc", now,
        ))

    if eps_vals:
        rows.append((
            ts_code, "L5.fcst.eps_cf",
            json.dumps({
                "eps_avg": _avg_float(eps_vals),
                "eps_low": min(eps_vals),
                "eps_high": max(eps_vals),
                "cashflow_estimate": None,
                "cashflow_available": False,
                "num_analysts": len(eps_report_keys),
                "period": f"{target_year}Q4",
                "unit": "CNY/share",
            }, ensure_ascii=False),
            "Known", 0.8, "tushare:report_rc", now,
        ))
    else:
        rows.append((
            ts_code, "L5.fcst.eps_cf",
            json.dumps({
                "reason": "report_rc missing eps for nearest forecast year",
                "period": f"{target_year}Q4",
                "lookback_days": lookback_days,
            }, ensure_ascii=False),
            "Inactive", 0.0, "tushare:report_rc", now,
        ))

    cutoff_30d = _previous_n_days(30)
    recent_eps: list[float] = []
    older_eps: list[float] = []
    for rec in target_records:
        eps = _safe_num(rec.get("eps"))
        if eps is None:
            continue
        rd = str(rec.get("report_date") or "")
        if rd and rd >= cutoff_30d:
            recent_eps.append(eps)
        else:
            older_eps.append(eps)
    recent_avg = _avg_float(recent_eps)
    older_avg = _avg_float(older_eps)
    if recent_avg is not None and older_avg not in (None, 0.0):
        revision_pct = (recent_avg - older_avg) / abs(older_avg) * 100.0
        direction = (
            "up" if revision_pct > 2.0 else
            "down" if revision_pct < -2.0 else
            "flat"
        )
        rows.append((
            ts_code, "L5.fcst.revisions",
            json.dumps({
                "consensus_eps_revision_30d_pct": revision_pct,
                "direction": direction,
                "recent_eps_avg": recent_avg,
                "older_eps_avg": older_avg,
                "recent_sample": len(recent_eps),
                "older_sample": len(older_eps),
                "period": f"{target_year}Q4",
                "as_of": as_of_date,
            }, ensure_ascii=False),
            "Known", 0.7, "tushare:report_rc.derived", now,
        ))
    else:
        rows.append((
            ts_code, "L5.fcst.revisions",
            json.dumps({
                "reason": "insufficient recent/older eps comparison",
                "recent_sample": len(recent_eps),
                "older_sample": len(older_eps),
                "period": f"{target_year}Q4",
                "lookback_days": lookback_days,
            }, ensure_ascii=False),
            "Inactive", 0.0, "tushare:report_rc.derived", now,
        ))

    return rows


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

    for idx, ts_code in enumerate(a_codes):
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
                rows.extend(_inactive_report_rc_all_rows(
                    ts_code, now, "report_rc permission unavailable",
                    lookback_days,
                ))
                inactive += 1
                if permission_errors >= 3:
                    for skipped_code in a_codes[idx + 1:]:
                        rows.extend(_inactive_report_rc_all_rows(
                            skipped_code, now,
                            "report_rc permission unavailable; batch aborted",
                            lookback_days,
                        ))
                        inactive += 1
                    break
                time.sleep(sleep_s)
                continue
            log.warning("[tushare] report_rc %s failed: %s", ts_code, e)
            rows.extend(_inactive_report_rc_all_rows(
                ts_code, now, "report_rc endpoint failed", lookback_days,
            ))
            inactive += 1
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
            rows.extend(_inactive_report_rc_fcst_rows(
                ts_code, now, "no sell-side report in window", lookback_days,
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
        rows.extend(_build_report_rc_fcst_rows(
            ts_code, records, now, lookback_days, end_date,
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

      * ``L10.val.historical_quantile`` / ``L8.val.overvalued`` — emitted by
        ``mvp20/derive.py`` (``derive_historical_quantile`` /
        ``derive_overvalued``). As of the H-3 window-unification fix that
        path pulls its PE/PB history over the SAME ~250-trading-day
        ``pe_pb_days`` window used here, so the two percentiles agree for a
        given trade date (previously derive.py used a 90-calendar-day /
        ~54-trading-day window, producing a contradictory percentile).
      * ``L6.state.historical_percentile`` — same semantic, distinct dp_id.

    Editing derive.py to dual-emit is owned by a different upstream PR, so
    we cover the spec by independently computing this dp_id from
    ``daily_basic`` history. We use a ~1-year (250 trading day) window
    here, mirroring the convention used by chip-distribution endpoints and
    now matched by the derive.py valuation-percentile path.

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


def _emit_fx_cnh(pro, now: int) -> list[tuple]:
    """``L7.env.fx`` + ``L9.macro.fx`` — RMB / cross-border FX tilt.

    Source: ``pro.fx_daily`` (银行间外汇市场日行情). We track the offshore
    yuan ``USDCNH.FXCM`` (Tushare's most reliable fx_daily symbol; falls
    back to onshore ``USDCNY.CFETS`` then ``USDCNY.FXCM``). USDCNH is the
    USD price of 1 RMB's reciprocal — i.e. **rising USDCNH = RMB
    *depreciation***, falling USDCNH = RMB *appreciation*.

    We compute the close-to-close % change over the most recent ~20 trading
    rows (``_FX_WINDOW`` = 20) and translate it into the two spec dp_ids:

      * ``L7.env.fx`` (multiplier / market_regime_multiplier, neutral 1.0).
        RMB appreciation is a mild risk-on tilt for A-shares (北向资金 +
        外资定价), depreciation a mild risk-off. We emit a SIGNED leaf via
        ``score`` (magnitude in [0,1], read by aggregator ``_to_scalar``)
        and ``direction``:
            RMB appreciated (USDCNH ↓) → direction "positive"
            RMB depreciated (USDCNH ↑) → direction "negative"
        Magnitude = tanh(|Δ%| / _FX_SCALE_PCT) so a ~2% 20-day move ≈ 0.76.

      * ``L9.macro.fx`` (discount / risk_discount, neutral 0.0). Only RMB
        *depreciation* beyond ``_FX_RISK_THRESHOLD_PCT`` registers as a
        macro risk — emit Known with direction "negative"; otherwise
        Inactive (no risk event, so the risk_discount stays neutral 0).

    Returns ``[]`` when fx_daily is permission-locked / empty so the macro
    batch dispatcher logs it and the freshness panel keeps the field
    Unknown rather than fabricating a tilt. (``fetch_macro_china_batch``'s
    per-fetcher try/except turns any raise here into a skipped fetcher.)
    """

    df = None
    used_symbol = None
    for symbol in ("USDCNH.FXCM", "USDCNY.CFETS", "USDCNY.FXCM"):
        try:
            cand = pro.fx_daily(
                ts_code=symbol,
                fields="ts_code,trade_date,bid_close,ask_close,tick_qty",
            )
        except Exception as e:  # noqa: BLE001
            log.warning("[tushare] fx_daily %s failed: %s", symbol, e)
            continue
        if cand is not None and len(cand) > 0:
            df = cand
            used_symbol = symbol
            break

    if df is None or len(df) == 0:
        log.info("[tushare] fx_daily: no data for any USDCN* symbol")
        return []

    df = df.sort_values("trade_date", ascending=False).head(_FX_WINDOW)
    records = df.to_dict(orient="records")
    if len(records) < 2:
        log.info("[tushare] fx_daily %s: <2 rows, cannot compute tilt",
                 used_symbol)
        return []

    def _mid(rec: dict) -> float | None:
        # Prefer the bid/ask midpoint; fall back to whichever side exists.
        bid = _safe_num(rec.get("bid_close"))
        ask = _safe_num(rec.get("ask_close"))
        if bid is not None and ask is not None:
            return (bid + ask) / 2.0
        return bid if bid is not None else ask

    latest_mid = _mid(records[0])
    oldest_mid = _mid(records[-1])
    if latest_mid is None or oldest_mid is None or oldest_mid == 0:
        log.info("[tushare] fx_daily %s: null close, cannot compute tilt",
                 used_symbol)
        return []

    # USDCNH change: + means USD up vs RMB → RMB depreciation.
    usdcnh_change_pct = (latest_mid / oldest_mid - 1.0) * 100.0
    # RMB appreciation % = inverse sign of the USDCNH move.
    rmb_appreciation_pct = -usdcnh_change_pct
    magnitude = abs(math.tanh(usdcnh_change_pct / _FX_SCALE_PCT))

    latest_date = records[0].get("trade_date")
    window_days = len(records)

    # L7.env.fx — signed regime multiplier leaf.
    if rmb_appreciation_pct > 0:
        env_direction = "positive"   # RMB strengthening → mild risk-on
    elif rmb_appreciation_pct < 0:
        env_direction = "negative"   # RMB weakening → mild risk-off
    else:
        env_direction = "neutral"
    env_payload = {
        "score": round(magnitude, 4),
        "direction": env_direction,
        "symbol": used_symbol,
        "usdcnh_change_pct": round(usdcnh_change_pct, 4),
        "rmb_appreciation_pct": round(rmb_appreciation_pct, 4),
        "window_trading_days": window_days,
        "latest_mid": round(latest_mid, 6),
        "latest_date": latest_date,
    }

    # L9.macro.fx — risk_discount: only RMB depreciation past threshold is a
    # risk event; otherwise Inactive so the discount stays neutral 0.
    is_depreciation_risk = usdcnh_change_pct > _FX_RISK_THRESHOLD_PCT
    macro_payload = {
        "score": round(magnitude, 4) if is_depreciation_risk else 0.0,
        "direction": "negative" if is_depreciation_risk else "neutral",
        "symbol": used_symbol,
        "usdcnh_change_pct": round(usdcnh_change_pct, 4),
        "rmb_appreciation_pct": round(rmb_appreciation_pct, 4),
        "threshold_pct": _FX_RISK_THRESHOLD_PCT,
        "window_trading_days": window_days,
        "latest_date": latest_date,
    }

    return [
        (
            "MARKET:CN", "L7.env.fx",
            json.dumps(env_payload, ensure_ascii=False),
            "Known", 0.8, "tushare:fx_daily", now,
        ),
        (
            "MARKET:CN", "L9.macro.fx",
            json.dumps(macro_payload, ensure_ascii=False),
            "Known" if is_depreciation_risk else "Inactive",
            0.8, "tushare:fx_daily", now,
        ),
    ]


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


_CN_MARKET_TREND_INDEXES = (
    ("sse", "000001.SH", "上证指数"),
    ("csi300", "000300.SH", "沪深300"),
    ("szse", "399001.SZ", "深证成指"),
    ("chinext", "399006.SZ", "创业板指"),
)

# Growth-vs-value style pair for the MARKET:CN ``L7.env.style`` sentinel.
# 巨潮/国证 成长 vs 价值 indices: probed read-only via ``index_daily`` and
# confirmed to return ~60 trading days of data on the current Tushare tier
# (the 沪深300 成长/价值 pair 000918.SH / 000919.SH returned 0 rows, so it is
# NOT used). ``growth_minus_value`` = growth_20d_ret − value_20d_ret, both as
# decimal ratios, which keeps the tilt naturally small (observed ~+0.05).
_CN_STYLE_GROWTH = ("399370.SZ", "国证成长")
_CN_STYLE_VALUE = ("399371.SZ", "国证价值")
_CN_STYLE_WINDOW_DAYS = 20


def _ratio_change(first: float | None, last: float | None) -> float | None:
    try:
        if first is None or last is None or not first:
            return None
        return float(last) / float(first) - 1.0
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def _market_index_payload(records: list[dict]) -> dict | None:
    if not records:
        return None
    records.sort(key=lambda r: r.get("trade_date") or "", reverse=True)
    latest = records[0]
    latest_close = _safe_num(latest.get("close"))
    closes = [
        _safe_num(r.get("close")) for r in records
        if _safe_num(r.get("close")) is not None
    ]
    if latest_close is None or len(closes) < 2:
        return None

    def _window_change(window: int) -> float | None:
        if len(closes) > window:
            return _ratio_change(closes[window], latest_close)
        return None

    pct_chg_1d = _safe_num(latest.get("pct_chg"))
    if pct_chg_1d is not None:
        # Tushare ``pct_chg`` is percentage points; keep all *_pct fields as
        # decimal ratios to match the multi-day window changes below.
        pct_chg_1d = pct_chg_1d / 100.0

    return {
        "last": latest_close,
        "latest_date": latest.get("trade_date"),
        "pct_chg_1d": pct_chg_1d,
        "d5_pct": _window_change(5),
        "d20_pct": _window_change(20),
        "d60_pct": _window_change(60),
        "history_days": len(closes),
    }


def _emit_market_trend(pro, now: int) -> list[tuple]:
    """``L7.env.market_trend`` — MARKET:CN benchmark trend via index_daily."""

    payload: dict[str, object] = {"scope": "A_share_market"}
    latest_dates: list[str] = []
    had_response = False
    start = _previous_n_days(90)
    end = _today_yyyymmdd()

    for key, ts_code, name in _CN_MARKET_TREND_INDEXES:
        try:
            df = pro.index_daily(
                ts_code=ts_code,
                start_date=start,
                end_date=end,
                fields="ts_code,trade_date,close,pct_chg,vol,amount",
            )
        except Exception as e:  # noqa: BLE001
            log.warning("[tushare] index_daily %s failed: %s", ts_code, e)
            continue
        had_response = True
        if df is None or len(df) == 0:
            continue
        metric = _market_index_payload(df.to_dict(orient="records"))
        if metric is None:
            continue
        payload[f"{key}_name"] = name
        payload[f"{key}_last"] = metric["last"]
        payload[f"{key}_1d_pct"] = metric["pct_chg_1d"]
        payload[f"{key}_5d_pct"] = metric["d5_pct"]
        payload[f"{key}_20d_pct"] = metric["d20_pct"]
        payload[f"{key}_60d_pct"] = metric["d60_pct"]
        payload[f"{key}_history_days"] = metric["history_days"]
        latest_date = metric.get("latest_date")
        if latest_date:
            latest_dates.append(str(latest_date))

    if not any(payload.get(f"{key}_last") is not None
               for key, *_ in _CN_MARKET_TREND_INDEXES):
        if had_response:
            return [(
                "MARKET:CN", "L7.env.market_trend",
                json.dumps({"reason": "no_index_data"},
                           ensure_ascii=False),
                "Inactive", 0.0, "tushare:index_daily", now,
            )]
        return []

    trend_values = [
        payload.get(f"{key}_20d_pct")
        for key, *_ in _CN_MARKET_TREND_INDEXES
        if payload.get(f"{key}_20d_pct") is not None
    ]
    scalar = (
        sum(float(v) for v in trend_values) / len(trend_values)
        if trend_values else None
    )
    payload["latest_date"] = max(latest_dates) if latest_dates else None
    payload["lookback_days"] = 90
    payload["scalar"] = scalar
    payload["regime"] = (
        "bull" if scalar is not None and scalar >= 0.05 else
        "bear" if scalar is not None and scalar <= -0.05 else
        "range"
    )
    return [(
        "MARKET:CN", "L7.env.market_trend",
        json.dumps(payload, ensure_ascii=False),
        "Known", 0.8, "tushare:index_daily", now,
    )]


def _index_window_return(pro, ts_code: str, start: str, end: str,
                         window: int) -> tuple[float | None, str | None]:
    """Return ``(window-day decimal return, latest_trade_date)`` for one index.

    Mirrors the close-window math in ``_market_index_payload`` but for a single
    configurable window (``_CN_STYLE_WINDOW_DAYS``). Returns ``(None, None)``
    when the index returns no data or has too few closes for the window.
    """

    try:
        df = pro.index_daily(
            ts_code=ts_code,
            start_date=start,
            end_date=end,
            fields="ts_code,trade_date,close,pct_chg,vol,amount",
        )
    except Exception as e:  # noqa: BLE001
        log.warning("[tushare] index_daily %s failed: %s", ts_code, e)
        return None, None
    if df is None or len(df) == 0:
        return None, None
    records = df.to_dict(orient="records")
    records.sort(key=lambda r: r.get("trade_date") or "", reverse=True)
    closes = [
        _safe_num(r.get("close")) for r in records
        if _safe_num(r.get("close")) is not None
    ]
    if len(closes) <= window:
        return None, str(records[0].get("trade_date") or "") or None
    ret = _ratio_change(closes[window], closes[0])
    return ret, str(records[0].get("trade_date") or "") or None


def _emit_market_style(pro, now: int) -> list[tuple]:
    """``L7.env.style`` — MARKET:CN growth-vs-value regime via index_daily.

    Emits a ``market_regime_multiplier`` tilt the consumer
    ``derive_l7_env_risk_appetite`` reads via ``style.growth_minus_value``:

        growth_minus_value = growth_index_20d_ret − value_index_20d_ret

    Both legs are ~20-trading-day decimal returns of the 国证成长 (399370.SZ)
    vs 国证价值 (399371.SZ) indices, so the difference is a small tilt
    (typically within roughly [-0.2, +0.2]); no extra scaling is applied. A
    positive value = growth leading (risk-on tilt), negative = value leading.
    Inactive when either index leg is unavailable.
    """

    start = _previous_n_days(90)
    end = _today_yyyymmdd()
    growth_code, growth_name = _CN_STYLE_GROWTH
    value_code, value_name = _CN_STYLE_VALUE
    window = _CN_STYLE_WINDOW_DAYS

    growth_ret, growth_date = _index_window_return(pro, growth_code, start, end, window)
    value_ret, value_date = _index_window_return(pro, value_code, start, end, window)

    if growth_ret is None or value_ret is None:
        return [(
            "MARKET:CN", "L7.env.style",
            json.dumps({"reason": "index_unavailable",
                        "growth_code": growth_code,
                        "value_code": value_code},
                       ensure_ascii=False),
            "Inactive", 0.0, "tushare:index_daily", now,
        )]

    gmv = float(growth_ret) - float(value_ret)
    latest_dates = [d for d in (growth_date, value_date) if d]
    payload = {
        "growth_minus_value": gmv,
        "scalar": gmv,
        "growth_code": growth_code,
        "growth_name": growth_name,
        "value_code": value_code,
        "value_name": value_name,
        "window_days": window,
        "growth_ret": float(growth_ret),
        "value_ret": float(value_ret),
        "regime": (
            "growth" if gmv >= 0.02 else
            "value" if gmv <= -0.02 else
            "balanced"
        ),
        "latest_date": max(latest_dates) if latest_dates else None,
        "scope": "A_share_market",
    }
    return [(
        "MARKET:CN", "L7.env.style",
        json.dumps(payload, ensure_ascii=False),
        "Known", 0.75, "tushare:index_daily", now,
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
        ("fx_daily",         _emit_fx_cnh),
        ("cn_cpi+cn_ppi",    _emit_cpi_ppi),
        ("market_trend",     _emit_market_trend),
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


# ---------------------------------------------------------------------------
# Bucket A: hard-data dp_ids appended at fetch_batch tail.
# ---------------------------------------------------------------------------
#
# Sub-groups:
#   1. L2.segment.* (3)            — pro.fina_mainbz per A-share
#   2. L5.fcst/surprise.* (2)      — pro.forecast / pro.express
#   3. L8.fin.* (3)                — eps_downward / goodwill / revenue_miss
#   4. L8.cap.* (3)                — crowdedness / short_increase / liquidity
#   5. L8.industry / L8.op (2)     — valuation_compression / cost_overrun
#   6. L9.capital.margin_anomaly (1) — pro.margin_detail 5d ma surge
#
# Design rules:
#   * All fetchers live below the existing X5 disclosure block — additive,
#     no edits to legacy code paths.
#   * Each fetcher returns rows or [] on any failure; never raises.
#   * Alert dp_ids emit ``Inactive`` (confidence 0.0) when no alert; ``Known``
#     when triggered. Non-alert dp_ids emit ``Inactive`` only when data is
#     missing.
#   * Per-stock RPC throttle ``_BUCKET_A_SLEEP_S`` keeps the cumulative API
#     budget under 500/min when stacked with the prior loops.

_BUCKET_A_SLEEP_S = 0.13


def _get_fina_mainbz_records(pro, ts_code: str, now: int) -> list[dict]:
    """Return up to 8 quarters of ``fina_mainbz`` records (latest first).

    Cached per-ts_code with ``_FINA_CACHE_TTL_S`` TTL. Empty list on any
    failure (permission, schema drift) so callers can branch to Inactive.
    """

    cached = _cache_get(_FINA_MAINBZ_CACHE, ts_code, _FINA_CACHE_TTL_S, now)
    if cached is not None:
        return cached
    try:
        df = pro.fina_mainbz(
            ts_code=ts_code, type="P",
            fields="ts_code,end_date,bz_item,bz_sales,bz_cost,bz_profit",
        )
        time.sleep(_BUCKET_A_SLEEP_S)
    except Exception as e:  # noqa: BLE001
        log.warning("[tushare] BucketA fina_mainbz %s failed: %s", ts_code, e)
        _cache_put(_FINA_MAINBZ_CACHE, ts_code, [], now)
        return []
    if df is None or len(df) == 0:
        _cache_put(_FINA_MAINBZ_CACHE, ts_code, [], now)
        return []
    records = df.to_dict(orient="records")
    records.sort(key=lambda r: r.get("end_date") or "", reverse=True)
    _cache_put(_FINA_MAINBZ_CACHE, ts_code, records, now)
    return records


def _get_forecast_records(pro, ts_code: str, now: int) -> list[dict]:
    """Return forecast records sorted by ann_date desc (latest first).

    Bucket A needs 2+ recent forecast rows for guidance_change delta and
    eps_downward delta. Empty list on any failure.
    """

    cached = _cache_get(_FORECAST_CACHE, ts_code, _FINA_CACHE_TTL_S, now)
    if cached is not None:
        return cached
    try:
        df = pro.forecast(ts_code=ts_code)
        time.sleep(_BUCKET_A_SLEEP_S)
    except Exception as e:  # noqa: BLE001
        log.warning("[tushare] BucketA forecast %s failed: %s", ts_code, e)
        _cache_put(_FORECAST_CACHE, ts_code, [], now)
        return []
    if df is None or len(df) == 0:
        _cache_put(_FORECAST_CACHE, ts_code, [], now)
        return []
    records = df.to_dict(orient="records")
    # Latest ann_date first; ties broken by end_date desc.
    records.sort(
        key=lambda r: (r.get("ann_date") or "", r.get("end_date") or ""),
        reverse=True,
    )
    _cache_put(_FORECAST_CACHE, ts_code, records, now)
    return records


def _get_express_records(pro, ts_code: str, now: int) -> list[dict]:
    """Return 业绩快报 records sorted by ann_date desc (latest first)."""

    cached = _cache_get(_EXPRESS_CACHE, ts_code, _FINA_CACHE_TTL_S, now)
    if cached is not None:
        return cached
    try:
        df = pro.express(
            ts_code=ts_code,
            fields=("ts_code,ann_date,end_date,revenue,operate_profit,"
                    "total_profit,n_income,yoy_sales,yoy_op,yoy_tp,yoy_net_profit"),
        )
        time.sleep(_BUCKET_A_SLEEP_S)
    except Exception as e:  # noqa: BLE001
        log.warning("[tushare] BucketA express %s failed: %s", ts_code, e)
        _cache_put(_EXPRESS_CACHE, ts_code, [], now)
        return []
    if df is None or len(df) == 0:
        _cache_put(_EXPRESS_CACHE, ts_code, [], now)
        return []
    records = df.to_dict(orient="records")
    records.sort(
        key=lambda r: (r.get("ann_date") or "", r.get("end_date") or ""),
        reverse=True,
    )
    _cache_put(_EXPRESS_CACHE, ts_code, records, now)
    return records


def _get_daily_basic_history(
    pro, ts_code: str, now: int, history_days: int = 120,
) -> list[dict]:
    """Return per-ts_code daily_basic history (latest first).

    Used by L8.cap.crowdedness (turnover) and L8.industry.valuation_compression
    (industry-level PE_ttm aggregation). 120-day window covers the 30d/90d
    moving-average comparison the formulas need plus headroom for trading
    holidays.
    """

    cached = _cache_get(_DAILY_BASIC_HISTORY_CACHE, ts_code, _FINA_CACHE_TTL_S, now)
    if cached is not None:
        return cached
    end = _today_yyyymmdd()
    start = _previous_n_days(history_days + 30)
    try:
        df = pro.daily_basic(
            ts_code=ts_code, start_date=start, end_date=end,
            fields="ts_code,trade_date,turnover_rate,pe_ttm",
        )
        time.sleep(_BUCKET_A_SLEEP_S)
    except Exception as e:  # noqa: BLE001
        log.warning(
            "[tushare] BucketA daily_basic.history %s failed: %s", ts_code, e,
        )
        _cache_put(_DAILY_BASIC_HISTORY_CACHE, ts_code, [], now)
        return []
    if df is None or len(df) == 0:
        _cache_put(_DAILY_BASIC_HISTORY_CACHE, ts_code, [], now)
        return []
    records = df.to_dict(orient="records")
    records.sort(key=lambda r: r.get("trade_date") or "", reverse=True)
    _cache_put(_DAILY_BASIC_HISTORY_CACHE, ts_code, records, now)
    return records


def _get_daily_history(
    pro, ts_code: str, now: int, history_days: int = 60,
) -> list[dict]:
    """Return per-ts_code daily price+volume history (latest first).

    Used by L8.cap.liquidity_short — 30d 均成交额 + 单日大跌+放量 detection.
    """

    cached = _cache_get(_DAILY_HISTORY_CACHE, ts_code, _FINA_CACHE_TTL_S, now)
    if cached is not None:
        return cached
    end = _today_yyyymmdd()
    start = _previous_n_days(history_days + 15)
    try:
        df = pro.daily(
            ts_code=ts_code, start_date=start, end_date=end,
            fields="ts_code,trade_date,close,pct_chg,amount,vol",
        )
        time.sleep(_BUCKET_A_SLEEP_S)
    except Exception as e:  # noqa: BLE001
        log.warning("[tushare] BucketA daily.history %s failed: %s", ts_code, e)
        _cache_put(_DAILY_HISTORY_CACHE, ts_code, [], now)
        return []
    if df is None or len(df) == 0:
        _cache_put(_DAILY_HISTORY_CACHE, ts_code, [], now)
        return []
    records = df.to_dict(orient="records")
    records.sort(key=lambda r: r.get("trade_date") or "", reverse=True)
    _cache_put(_DAILY_HISTORY_CACHE, ts_code, records, now)
    return records


def _get_margin_history(
    pro, ts_code: str, now: int, history_days: int = 120,
) -> list[dict]:
    """Return per-ts_code margin_detail history (latest first).

    Used by L8.cap.short_increase (rqye 30d/90d ma) and
    L9.capital.margin_anomaly (rzmre 5d/30d ma surge).
    """

    cached = _cache_get(_MARGIN_HISTORY_CACHE, ts_code, _FINA_CACHE_TTL_S, now)
    if cached is not None:
        return cached
    end = _today_yyyymmdd()
    start = _previous_n_days(history_days + 30)
    try:
        df = pro.margin_detail(
            ts_code=ts_code, start_date=start, end_date=end,
            fields="ts_code,trade_date,rzye,rqye,rzmre,rqmcl",
        )
        time.sleep(_BUCKET_A_SLEEP_S)
    except Exception as e:  # noqa: BLE001
        log.warning(
            "[tushare] BucketA margin_detail.history %s failed: %s", ts_code, e,
        )
        _cache_put(_MARGIN_HISTORY_CACHE, ts_code, [], now)
        return []
    if df is None or len(df) == 0:
        _cache_put(_MARGIN_HISTORY_CACHE, ts_code, [], now)
        return []
    records = df.to_dict(orient="records")
    records.sort(key=lambda r: r.get("trade_date") or "", reverse=True)
    _cache_put(_MARGIN_HISTORY_CACHE, ts_code, records, now)
    return records


# ---------------------------------------------------------------------------
# Sub-group 1: L2.segment.* — 主营业务分部 (3 dp_ids)
# ---------------------------------------------------------------------------


def _derive_segments(records: list[dict]) -> tuple[dict, dict, dict]:
    """Compute revenue_share / gross_margin / growth from fina_mainbz.

    Returns three payloads (revenue_share, gross_margin, growth). Each is a
    ``{"segments": [...], "period": "YYYYMMDD"}`` dict or contains a
    ``"reason"`` key when the data is insufficient.

    Status is computed by the caller — these helpers always return a dict.
    """

    if not records:
        return ({"reason": "no fina_mainbz"},
                {"reason": "no fina_mainbz"},
                {"reason": "no fina_mainbz"})

    latest_period = records[0].get("end_date")
    # Group by end_date so we can also do yoy growth.
    by_period: dict[str, list[dict]] = {}
    for rec in records:
        p = rec.get("end_date")
        if not p:
            continue
        by_period.setdefault(p, []).append(rec)

    latest_rows = by_period.get(latest_period, [])
    if not latest_rows:
        return ({"reason": "no latest segment"},
                {"reason": "no latest segment"},
                {"reason": "no latest segment"})

    # ── revenue_share ──
    total_sales = 0.0
    for r in latest_rows:
        s = _safe_num(r.get("bz_sales"))
        if s is not None:
            total_sales += s
    revenue_share_segments: list[dict] = []
    if total_sales > 0:
        for r in latest_rows:
            s = _safe_num(r.get("bz_sales"))
            if s is None:
                continue
            revenue_share_segments.append({
                "item": str(r.get("bz_item") or ""),
                "revenue_pct": round(s / total_sales * 100.0, 4),
                "period": latest_period,
            })
    # Sort by revenue_pct desc.
    revenue_share_segments.sort(
        key=lambda r: r.get("revenue_pct") or 0.0, reverse=True,
    )
    revenue_share_payload: dict = {
        "segments": revenue_share_segments,
        "period": latest_period,
    }
    if not revenue_share_segments:
        revenue_share_payload = {"reason": "no positive bz_sales"}

    # ── gross_margin per segment ──
    gm_segments: list[dict] = []
    for r in latest_rows:
        s = _safe_num(r.get("bz_sales"))
        c = _safe_num(r.get("bz_cost"))
        if s is None or s <= 0 or c is None:
            continue
        gm_pct = round((s - c) / s * 100.0, 4)
        gm_segments.append({
            "item": str(r.get("bz_item") or ""),
            "gross_margin_pct": gm_pct,
            "period": latest_period,
        })
    gm_segments.sort(key=lambda r: r.get("gross_margin_pct") or 0.0, reverse=True)
    gm_payload: dict = {
        "segments": gm_segments,
        "period": latest_period,
    }
    if not gm_segments:
        gm_payload = {"reason": "no bz_cost available"}

    # ── growth (yoy of bz_sales) ──
    prior_period = _yoy_period(latest_period) if latest_period else None
    growth_segments: list[dict] = []
    prior_rows = by_period.get(prior_period, []) if prior_period else []
    prior_by_item = {str(r.get("bz_item") or ""): r for r in prior_rows}
    for r in latest_rows:
        item = str(r.get("bz_item") or "")
        s = _safe_num(r.get("bz_sales"))
        p_rec = prior_by_item.get(item)
        if p_rec is None or s is None:
            continue
        ps = _safe_num(p_rec.get("bz_sales"))
        if ps is None or ps == 0:
            continue
        yoy_pct = round((s - ps) / abs(ps) * 100.0, 4)
        growth_segments.append({
            "item": item,
            "yoy_pct": yoy_pct,
            "period": latest_period,
        })
    growth_segments.sort(
        key=lambda r: r.get("yoy_pct") or 0.0, reverse=True,
    )
    growth_payload: dict = {
        "segments": growth_segments,
        "period": latest_period,
        "prior_period": prior_period,
    }
    if not growth_segments:
        growth_payload = {
            "reason": "no yoy comparable segments",
            "period": latest_period,
            "prior_period": prior_period,
        }

    return revenue_share_payload, gm_payload, growth_payload


# ---------------------------------------------------------------------------
# Sub-group 2: L5 forecast / surprise (2 dp_ids)
# ---------------------------------------------------------------------------


def _derive_guidance_change(forecast_records: list[dict]) -> tuple[dict, str]:
    """Compare the two most recent forecast rows and emit a delta payload.

    ``change_direction`` is one of:
      * ``"new"``       — only one forecast row exists
      * ``"upgraded"``  — current midpoint > previous midpoint
      * ``"downgraded"``— current midpoint < previous midpoint
      * ``"unchanged"`` — equal midpoints
    """

    if not forecast_records:
        return {"reason": "no forecast"}, "Inactive"

    cur = forecast_records[0]
    prev = forecast_records[1] if len(forecast_records) >= 2 else None

    def _midpoint(rec: dict) -> float | None:
        mn = _safe_num(rec.get("p_change_min"))
        mx = _safe_num(rec.get("p_change_max"))
        if mn is None and mx is None:
            return None
        if mn is None:
            return mx
        if mx is None:
            return mn
        return (mn + mx) / 2.0

    cur_mid = _midpoint(cur)
    prev_mid = _midpoint(prev) if prev is not None else None
    cur_type = cur.get("type")
    prev_type = prev.get("type") if prev is not None else None

    if prev is None:
        return ({
            "prev_type": None,
            "current_type": cur_type,
            "prev_range_pct": None,
            "current_range_pct": cur_mid,
            "change_direction": "new",
            "ann_date": cur.get("ann_date"),
            "period": cur.get("end_date"),
        }, "Known")

    if cur_mid is None or prev_mid is None:
        direction = "unchanged" if cur_type == prev_type else "type_change"
    elif cur_mid > prev_mid + 0.01:
        direction = "upgraded"
    elif cur_mid < prev_mid - 0.01:
        direction = "downgraded"
    else:
        direction = "unchanged"

    return ({
        "prev_type": prev_type,
        "current_type": cur_type,
        "prev_range_pct": prev_mid,
        "current_range_pct": cur_mid,
        "change_direction": direction,
        "ann_date": cur.get("ann_date"),
        "period": cur.get("end_date"),
    }, "Known")


def _derive_beat_miss(
    express_records: list[dict],
    forecast_records: list[dict],
) -> tuple[dict, str]:
    """Compare express yoy_sales / actuals to the most recent forecast range.

    Classification:
      * ``"beat"``     — actual > forecast_range_max
      * ``"miss"``     — actual < forecast_range_min
      * ``"in_range"`` — within range
    """

    if not express_records:
        return {"reason": "no express"}, "Inactive"
    if not forecast_records:
        return {"reason": "no forecast for comparison"}, "Inactive"

    latest_express = express_records[0]
    actual_yoy = _safe_num(latest_express.get("yoy_sales"))
    if actual_yoy is None:
        # Fallback: revenue + last_parent_net inference is too noisy; bail.
        return {"reason": "express missing yoy_sales"}, "Inactive"

    # Pick the forecast whose end_date matches the express end_date if any,
    # else fall back to the latest forecast row.
    fcst = None
    target = latest_express.get("end_date")
    if target:
        for r in forecast_records:
            if r.get("end_date") == target:
                fcst = r
                break
    if fcst is None:
        fcst = forecast_records[0]

    f_min = _safe_num(fcst.get("p_change_min"))
    f_max = _safe_num(fcst.get("p_change_max"))
    if f_min is None and f_max is None:
        return {"reason": "forecast missing range"}, "Inactive"
    if f_min is None:
        f_min = f_max
    if f_max is None:
        f_max = f_min

    if actual_yoy > f_max:
        classification = "beat"
        deviation = (actual_yoy - f_max)
    elif actual_yoy < f_min:
        classification = "miss"
        deviation = (actual_yoy - f_min)
    else:
        classification = "in_range"
        midpoint = (f_min + f_max) / 2.0
        deviation = actual_yoy - midpoint

    return ({
        "actual_revenue_yoy": actual_yoy,
        "forecast_range_min": f_min,
        "forecast_range_max": f_max,
        "deviation_pct": round(deviation, 4),
        "classification": classification,
        "period": target,
        "ann_date": latest_express.get("ann_date"),
    }, "Known")


# ---------------------------------------------------------------------------
# Sub-group 3: L8.fin.* (3 dp_ids) — alert-style risk signals
# ---------------------------------------------------------------------------


def _derive_eps_downward(forecast_records: list[dict]) -> tuple[dict, str]:
    """Detect downward EPS revisions across the two latest forecasts.

    ``alert_severity``:
      * ``"ERROR"`` if delta_pct < -20%
      * ``"WARN"``  if delta_pct in (-20%, -5%]
      * else ``Inactive`` (no alert)
    """

    if len(forecast_records) < 2:
        return {"reason": "fewer than 2 forecasts"}, "Inactive"

    cur, prev = forecast_records[0], forecast_records[1]

    def _eps_estimate(rec: dict) -> float | None:
        """Use net_profit midpoint as an EPS proxy (Tushare forecast doesn't
        expose EPS estimate directly; net_profit movements track EPS for a
        constant share count)."""
        mn = _safe_num(rec.get("net_profit_min"))
        mx = _safe_num(rec.get("net_profit_max"))
        if mn is None and mx is None:
            # Fall back to change_pct midpoint.
            mn = _safe_num(rec.get("p_change_min"))
            mx = _safe_num(rec.get("p_change_max"))
            if mn is None and mx is None:
                return None
        if mn is None:
            return mx
        if mx is None:
            return mn
        return (mn + mx) / 2.0

    cur_eps = _eps_estimate(cur)
    prev_eps = _eps_estimate(prev)
    if cur_eps is None or prev_eps is None or prev_eps == 0:
        return {"reason": "missing eps estimate"}, "Inactive"

    delta_pct = (cur_eps - prev_eps) / abs(prev_eps) * 100.0
    severity: str | None = None
    if delta_pct < -20.0:
        severity = "ERROR"
    elif delta_pct < -5.0:
        severity = "WARN"

    payload = {
        "prev_eps_estimate": round(prev_eps, 4),
        "current_eps_estimate": round(cur_eps, 4),
        "delta_pct": round(delta_pct, 4),
        "alert_severity": severity,
        "ann_date": cur.get("ann_date"),
        "period": cur.get("end_date"),
    }
    return payload, ("Known" if severity else "Inactive")


def _derive_goodwill_impairment(
    balance_records: list[dict],
    threshold_pct: float = 5.0,
) -> tuple[dict, str]:
    """Detect goodwill impairment between the latest two balance sheets.

    Balance-sheet records in ``_BALANCESHEET_CACHE`` only include
    ``inventories, accounts_receiv, accounts_pay, lt_borr, st_borr,
    bond_payable, payroll_payable, total_assets, total_liab`` — no
    ``goodwill`` field. To stay aligned with the existing cache (and not
    re-pull goodwill in a separate RPC), we look for ``goodwill`` on the
    record but treat missing → Inactive, so the dp_id is always emitted.
    """

    if len(balance_records) < 2:
        return {"reason": "fewer than 2 balance periods"}, "Inactive"

    cur, prev = balance_records[0], balance_records[1]
    cur_g = _safe_num(cur.get("goodwill"))
    prev_g = _safe_num(prev.get("goodwill"))
    if cur_g is None or prev_g is None or prev_g <= 0:
        return {
            "reason": "goodwill not in cached balancesheet fields",
            "alert_severity": None,
        }, "Inactive"

    drop_pct = (prev_g - cur_g) / prev_g * 100.0
    severity: str | None = None
    if drop_pct >= threshold_pct * 4:  # ≥ 20% drop
        severity = "ERROR"
    elif drop_pct >= threshold_pct:
        severity = "WARN"

    payload = {
        "current_goodwill": cur_g,
        "prev_goodwill": prev_g,
        "drop_pct": round(drop_pct, 4),
        "alert_severity": severity,
        "current_period": cur.get("end_date"),
        "prior_period": prev.get("end_date"),
    }
    return payload, ("Known" if severity else "Inactive")


def _derive_revenue_profit_miss(beat_miss_payload: dict) -> tuple[dict, str]:
    """L8.fin.revenue_profit_miss — Known only when L5.surprise.beat_miss
    classifies as 'miss'. Otherwise Inactive.

    Borrows the already-computed beat_miss payload to avoid recomputation.
    """

    classification = beat_miss_payload.get("classification")
    if classification != "miss":
        return ({
            "reason": "no miss detected",
            "alert_severity": None,
            "classification": classification,
        }, "Inactive")

    deviation = beat_miss_payload.get("deviation_pct") or 0.0
    severity = "ERROR" if deviation < -20.0 else "WARN"

    return ({
        "actual_revenue": beat_miss_payload.get("actual_revenue_yoy"),
        "forecast_revenue_low": beat_miss_payload.get("forecast_range_min"),
        "miss_pct": abs(deviation),
        "alert_severity": severity,
        "period": beat_miss_payload.get("period"),
    }, "Known")


# ---------------------------------------------------------------------------
# Sub-group 4: L8.cap.* — crowdedness / short / liquidity (3 dp_ids)
# ---------------------------------------------------------------------------


def _moving_average(values: list[float], window: int) -> float | None:
    """Return arithmetic mean of the first ``window`` non-null floats, or
    None if fewer than half-window samples are available."""

    samples = [v for v in values[:window] if v is not None]
    if len(samples) < max(2, window // 2):
        return None
    return sum(samples) / len(samples)


def _derive_crowdedness(
    daily_basic_records: list[dict],
    main_net_inflow_5d: float | None,
) -> tuple[dict, str]:
    """L8.cap.crowdedness — high turnover + sustained inflow → crowded.

    Without the universe-wide industry percentile we approximate with a
    rule-of-thumb threshold: turnover_30d_avg > 8% (top-quintile A-share
    activity) + main_net_5d > 0 → crowded.
    """

    if not daily_basic_records:
        return {"reason": "no daily_basic history"}, "Inactive"

    turnovers = [_safe_num(r.get("turnover_rate")) for r in daily_basic_records]
    turnover_30d = _moving_average(turnovers, 30)
    if turnover_30d is None:
        return {"reason": "insufficient turnover history"}, "Inactive"

    # Heuristic percentile: turnover > 8% ≈ 95th pct on the A-share market.
    high_turnover = turnover_30d > 8.0
    high_inflow = (main_net_inflow_5d is not None and main_net_inflow_5d > 0)
    severity: str | None = None
    if high_turnover and high_inflow:
        severity = "ERROR" if turnover_30d > 15.0 else "WARN"
    elif high_turnover:
        severity = "WARN"

    payload = {
        "turnover_30d_avg": round(turnover_30d, 4),
        "industry_pct_rank": 0.95 if high_turnover else 0.50,
        "main_net_5d": main_net_inflow_5d,
        "alert_severity": severity,
        "latest_date": daily_basic_records[0].get("trade_date"),
    }
    return payload, ("Known" if severity else "Inactive")


def _derive_priced_crowdedness(
    daily_basic_records: list[dict],
    min_samples: int = 20,
) -> tuple[dict, str]:
    """L6.priced.crowdedness — current turnover percentile vs history."""

    if not daily_basic_records:
        return {"reason": "no daily_basic history"}, "Inactive"

    current_turnover = _safe_num(daily_basic_records[0].get("turnover_rate"))
    if current_turnover is None:
        return {"reason": "latest turnover_rate missing"}, "Inactive"

    turnover_history = [
        _safe_num(r.get("turnover_rate")) for r in daily_basic_records
    ]
    clean = [v for v in turnover_history if v is not None]
    if len(clean) < min_samples:
        return {
            "reason": "insufficient turnover history",
            "history_window_days": len(clean),
        }, "Inactive"

    pct100 = _percentile_rank(current_turnover, sorted(clean))
    if pct100 is None:
        return {"reason": "percentile unavailable"}, "Inactive"
    percentile = pct100 / 100.0
    label = (
        "extreme" if percentile > 0.9 else
        "crowded" if percentile > 0.75 else
        "elevated" if percentile > 0.5 else
        "neutral"
    )
    return {
        "percentile": percentile,
        "label": label,
        "current_turnover_rate": current_turnover,
        "history_window_days": len(clean),
        "latest_date": daily_basic_records[0].get("trade_date"),
    }, "Known"


def _derive_short_increase(
    margin_records: list[dict],
    delta_threshold_pct: float = 20.0,
) -> tuple[dict, str]:
    """L8.cap.short_increase — 融券余额 rqye 30d ma vs 90d ma > +20% → alert."""

    if not margin_records:
        return {"reason": "no margin_detail history"}, "Inactive"

    rqye = [_safe_num(r.get("rqye")) for r in margin_records]
    ma30 = _moving_average(rqye, 30)
    ma90 = _moving_average(rqye, 90)
    if ma30 is None or ma90 is None or ma90 <= 0:
        return {"reason": "insufficient rqye history"}, "Inactive"

    delta_pct = (ma30 - ma90) / ma90 * 100.0
    severity: str | None = None
    if delta_pct >= delta_threshold_pct * 2:
        severity = "ERROR"
    elif delta_pct >= delta_threshold_pct:
        severity = "WARN"

    payload = {
        "rqye_30d": round(ma30, 4),
        "rqye_90d": round(ma90, 4),
        "delta_pct": round(delta_pct, 4),
        "alert_severity": severity,
        "latest_date": margin_records[0].get("trade_date"),
    }
    return payload, ("Known" if severity else "Inactive")


def _derive_liquidity_short(
    daily_records: list[dict],
    dive_threshold_pct: float = -5.0,
    volume_surge_ratio: float = 1.5,
) -> tuple[dict, str]:
    """L8.cap.liquidity_short — 30d 均成交额 thin + 单日大跌放量 → alert.

    Heuristics:
      * 30d 均成交额 < 1亿元 (10 万千元) → thin-liquidity flag
      * 任一交易日 pct_chg < -5% 且 vol > 30d_vol_ma * 1.5 → dive day
    """

    if not daily_records:
        return {"reason": "no daily history"}, "Inactive"

    amounts = [_safe_num(r.get("amount")) for r in daily_records]
    amount_30d = _moving_average(amounts, 30)
    if amount_30d is None:
        return {"reason": "insufficient amount history"}, "Inactive"

    vols = [_safe_num(r.get("vol")) for r in daily_records]
    vol_30d = _moving_average(vols, 30) or 0.0
    dive_count = 0
    for r in daily_records[:30]:
        pct = _safe_num(r.get("pct_chg"))
        v = _safe_num(r.get("vol"))
        if pct is None or v is None or vol_30d == 0:
            continue
        if pct <= dive_threshold_pct and v >= vol_30d * volume_surge_ratio:
            dive_count += 1

    thin_amount = amount_30d < 100_000  # tushare daily.amount is 千元
    severity: str | None = None
    if thin_amount and dive_count >= 2:
        severity = "ERROR"
    elif thin_amount or dive_count >= 1:
        severity = "WARN" if dive_count >= 1 else None

    payload = {
        "amount_30d_avg": round(amount_30d, 2),
        "industry_pct_rank": 0.05 if thin_amount else 0.50,
        "dive_day_count": dive_count,
        "alert_severity": severity,
        "latest_date": daily_records[0].get("trade_date"),
    }
    return payload, ("Known" if severity else "Inactive")


# ---------------------------------------------------------------------------
# Sub-group 5: L8.industry / L8.op (2 dp_ids)
# ---------------------------------------------------------------------------


def _derive_valuation_compression(
    industry_pe_30d: float | None,
    industry_pe_90d: float | None,
    threshold_pct: float = 10.0,
) -> tuple[dict, str]:
    """Industry-level PE compression: 30d median vs 90d median."""

    if industry_pe_30d is None or industry_pe_90d is None or industry_pe_90d <= 0:
        return {"reason": "missing industry PE history"}, "Inactive"

    compression_pct = (industry_pe_90d - industry_pe_30d) / industry_pe_90d * 100.0
    severity: str | None = None
    if compression_pct >= threshold_pct * 2:
        severity = "ERROR"
    elif compression_pct >= threshold_pct:
        severity = "WARN"

    payload = {
        "industry_pe_30d": round(industry_pe_30d, 4),
        "industry_pe_90d": round(industry_pe_90d, 4),
        "compression_pct": round(compression_pct, 4),
        "alert_severity": severity,
    }
    return payload, ("Known" if severity else "Inactive")


def _derive_cost_overrun(
    income_records: list[dict],
    gap_threshold_pp: float = 5.0,
) -> tuple[dict, str]:
    """L8.op.cost_overrun — oper_cost yoy > revenue yoy + 5pp → alert."""

    if len(income_records) < 2:
        return {"reason": "fewer than 2 income periods"}, "Inactive"

    latest = income_records[0]
    end_date = latest.get("end_date")
    prior_end = _yoy_period(end_date) if end_date else None
    prior = _find_record(income_records, prior_end) if prior_end else None
    if prior is None:
        return {"reason": "no yoy comparable income"}, "Inactive"

    rev_cur = _safe_num(latest.get("total_revenue"))
    rev_prev = _safe_num(prior.get("total_revenue"))
    cost_cur = _safe_num(latest.get("oper_cost"))
    cost_prev = _safe_num(prior.get("oper_cost"))
    if (rev_cur is None or rev_prev is None or rev_prev == 0
            or cost_cur is None or cost_prev is None or cost_prev == 0):
        return {"reason": "missing income fields"}, "Inactive"

    rev_yoy = (rev_cur - rev_prev) / abs(rev_prev) * 100.0
    cost_yoy = (cost_cur - cost_prev) / abs(cost_prev) * 100.0
    gap_pp = cost_yoy - rev_yoy
    severity: str | None = None
    if gap_pp >= gap_threshold_pp * 2:
        severity = "ERROR"
    elif gap_pp >= gap_threshold_pp:
        severity = "WARN"

    payload = {
        "revenue_yoy": round(rev_yoy, 4),
        "cost_yoy": round(cost_yoy, 4),
        "gap_pp": round(gap_pp, 4),
        "alert_severity": severity,
        "period": end_date,
    }
    return payload, ("Known" if severity else "Inactive")


# ---------------------------------------------------------------------------
# Sub-group 6: L9.capital.margin_anomaly (1 dp_id)
# ---------------------------------------------------------------------------


def _derive_margin_anomaly(
    margin_records: list[dict],
    surge_threshold: float = 2.0,
) -> tuple[dict, str]:
    """L9.capital.margin_anomaly — rzmre 5d ma ÷ 30d ma ≥ 2 → alert."""

    if not margin_records:
        return {"reason": "no margin history"}, "Inactive"

    rzmre = [_safe_num(r.get("rzmre")) for r in margin_records]
    ma5 = _moving_average(rzmre, 5)
    ma30 = _moving_average(rzmre, 30)
    if ma5 is None or ma30 is None or ma30 <= 0:
        return {"reason": "insufficient rzmre history"}, "Inactive"

    surge_ratio = ma5 / ma30
    severity: str | None = None
    if surge_ratio >= surge_threshold * 1.5:  # ≥ 3x
        severity = "ERROR"
    elif surge_ratio >= surge_threshold:
        severity = "WARN"

    payload = {
        "rzmre_5d": round(ma5, 4),
        "rzmre_30d": round(ma30, 4),
        "surge_ratio": round(surge_ratio, 4),
        "alert_severity": severity,
        "latest_date": margin_records[0].get("trade_date"),
    }
    return payload, ("Known" if severity else "Inactive")


# ---------------------------------------------------------------------------
# Bucket A dispatcher — appended at fetch_batch tail.
# ---------------------------------------------------------------------------


def fetch_bucket_a_batch(
    pro,
    a_codes: list[str],
    now: int | None = None,
    main_net_inflow_by_ts_code: dict[str, float] | None = None,
) -> list[tuple]:
    """Emit all 14 Bucket A dp_ids for the given A-share codes.

    ``main_net_inflow_by_ts_code`` is optionally supplied by the caller so
    we can re-use the 5d-window inflow already computed in ``fetch_batch``
    (saves a moneyflow re-pull). When missing, crowdedness still evaluates
    on turnover alone.

    Returns rows ready for SQLite upsert; never raises.
    """

    if now is None:
        now = int(time.time())
    if not a_codes:
        return []
    main_net_inflow_by_ts_code = main_net_inflow_by_ts_code or {}

    rows: list[tuple] = []
    counts = {
        "L2.segment.revenue_share": {"Known": 0, "Inactive": 0},
        "L2.segment.gross_margin":  {"Known": 0, "Inactive": 0},
        "L2.segment.growth":        {"Known": 0, "Inactive": 0},
        "L5.fcst.guidance_change":  {"Known": 0, "Inactive": 0},
        "L5.surprise.beat_miss":    {"Known": 0, "Inactive": 0},
        "L8.fin.eps_downward":      {"Known": 0, "Inactive": 0},
        "L8.fin.goodwill_impairment": {"Known": 0, "Inactive": 0},
        "L8.fin.revenue_profit_miss": {"Known": 0, "Inactive": 0},
        "L6.priced.crowdedness":    {"Known": 0, "Inactive": 0},
        "L8.cap.crowdedness":       {"Known": 0, "Inactive": 0},
        "L8.cap.short_increase":    {"Known": 0, "Inactive": 0},
        "L8.cap.liquidity_short":   {"Known": 0, "Inactive": 0},
        "L8.op.cost_overrun":       {"Known": 0, "Inactive": 0},
        "L9.capital.margin_anomaly": {"Known": 0, "Inactive": 0},
    }
    alert_dist = {"WARN": 0, "ERROR": 0, "null": 0}

    def _emit(dp_id: str, ts_code: str, payload: dict, status: str,
              confidence: float, source: str) -> None:
        rows.append((
            ts_code, dp_id,
            json.dumps(payload, ensure_ascii=False),
            status, confidence if status == "Known" else 0.0,
            source, now,
        ))
        if dp_id in counts:
            counts[dp_id][status] += 1
        sev = payload.get("alert_severity")
        if sev in ("WARN", "ERROR"):
            alert_dist[sev] += 1

    for ts_code in a_codes:
        if not is_a_share(ts_code):
            continue

        # ── Sub-group 1: L2.segment.* from fina_mainbz ──
        try:
            seg_records = _get_fina_mainbz_records(pro, ts_code, now)
            rs_payload, gm_payload, gr_payload = _derive_segments(seg_records)
            rs_status = "Known" if "segments" in rs_payload and rs_payload["segments"] else "Inactive"
            gm_status = "Known" if "segments" in gm_payload and gm_payload["segments"] else "Inactive"
            gr_status = "Known" if "segments" in gr_payload and gr_payload["segments"] else "Inactive"
            _emit("L2.segment.revenue_share", ts_code, rs_payload, rs_status,
                  0.75, "tushare:fina_mainbz")
            _emit("L2.segment.gross_margin", ts_code, gm_payload, gm_status,
                  0.75, "tushare:fina_mainbz")
            _emit("L2.segment.growth", ts_code, gr_payload, gr_status,
                  0.75, "tushare:fina_mainbz")
        except Exception as e:  # noqa: BLE001
            log.warning("[tushare] BucketA L2.segment %s failed: %s", ts_code, e)

        # ── Sub-group 2 + 3 share forecast/express data ──
        try:
            forecast_records = _get_forecast_records(pro, ts_code, now)
            express_records = _get_express_records(pro, ts_code, now)

            gc_payload, gc_status = _derive_guidance_change(forecast_records)
            _emit("L5.fcst.guidance_change", ts_code, gc_payload, gc_status,
                  0.8, "tushare:forecast")

            bm_payload, bm_status = _derive_beat_miss(
                express_records, forecast_records,
            )
            _emit("L5.surprise.beat_miss", ts_code, bm_payload, bm_status,
                  0.8, "tushare:express+forecast")

            eps_payload, eps_status = _derive_eps_downward(forecast_records)
            _emit("L8.fin.eps_downward", ts_code, eps_payload, eps_status,
                  0.8, "tushare:forecast.derived")

            rpm_payload, rpm_status = _derive_revenue_profit_miss(bm_payload)
            _emit("L8.fin.revenue_profit_miss", ts_code, rpm_payload, rpm_status,
                  0.8, "tushare:express+forecast.derived")
        except Exception as e:  # noqa: BLE001
            log.warning(
                "[tushare] BucketA forecast/express %s failed: %s", ts_code, e,
            )

        # ── Sub-group 3 cont'd: L8.fin.goodwill_impairment (balancesheet) ──
        try:
            balance = _get_balancesheet_records(pro, ts_code, now)
            gi_payload, gi_status = _derive_goodwill_impairment(balance)
            _emit("L8.fin.goodwill_impairment", ts_code, gi_payload, gi_status,
                  0.75, "tushare:balancesheet")
        except Exception as e:  # noqa: BLE001
            log.warning(
                "[tushare] BucketA L8.fin.goodwill %s failed: %s", ts_code, e,
            )

        # ── Sub-group 4: L8.cap.* (turnover / margin / liquidity) ──
        try:
            db_history = _get_daily_basic_history(pro, ts_code, now)
            cr_payload, cr_status = _derive_crowdedness(
                db_history, main_net_inflow_by_ts_code.get(ts_code),
            )
            pc_payload, pc_status = _derive_priced_crowdedness(db_history)
            _emit("L6.priced.crowdedness", ts_code, pc_payload, pc_status,
                  0.7, "tushare:daily_basic.history")
            _emit("L8.cap.crowdedness", ts_code, cr_payload, cr_status,
                  0.7, "tushare:daily_basic.history")
        except Exception as e:  # noqa: BLE001
            log.warning(
                "[tushare] BucketA L8.cap.crowdedness %s failed: %s", ts_code, e,
            )

        try:
            margin_history = _get_margin_history(pro, ts_code, now)
            si_payload, si_status = _derive_short_increase(margin_history)
            _emit("L8.cap.short_increase", ts_code, si_payload, si_status,
                  0.75, "tushare:margin_detail.history")

            ma_payload, ma_status = _derive_margin_anomaly(margin_history)
            _emit("L9.capital.margin_anomaly", ts_code, ma_payload, ma_status,
                  0.75, "tushare:margin_detail.history")
        except Exception as e:  # noqa: BLE001
            log.warning(
                "[tushare] BucketA L8.cap.short / L9.margin %s failed: %s",
                ts_code, e,
            )

        try:
            daily_history = _get_daily_history(pro, ts_code, now)
            ls_payload, ls_status = _derive_liquidity_short(daily_history)
            _emit("L8.cap.liquidity_short", ts_code, ls_payload, ls_status,
                  0.7, "tushare:daily.history")
        except Exception as e:  # noqa: BLE001
            log.warning(
                "[tushare] BucketA L8.cap.liquidity %s failed: %s", ts_code, e,
            )

        # ── Sub-group 5: L8.op.cost_overrun (income only) ──
        try:
            income = _get_income_records(pro, ts_code, now)
            co_payload, co_status = _derive_cost_overrun(income)
            _emit("L8.op.cost_overrun", ts_code, co_payload, co_status,
                  0.75, "tushare:income.derived")
        except Exception as e:  # noqa: BLE001
            log.warning(
                "[tushare] BucketA L8.op.cost_overrun %s failed: %s", ts_code, e,
            )

    # ── Industry-level: L8.industry.valuation_compression × N active ──
    try:
        industries = _active_industry_ids()
    except Exception as e:  # noqa: BLE001
        log.warning("[tushare] BucketA _active_industry_ids failed: %s", e)
        industries = []
    for industry_id in industries:
        try:
            # Aggregate PE_ttm from the THS daily fund-flow industry close;
            # fallback to median-of-stocks PE_ttm if industry yaml has no
            # ts_codes registered.
            pe_30d_samples: list[float] = []
            pe_90d_samples: list[float] = []
            for ts_code in a_codes:
                db_hist = _get_daily_basic_history(pro, ts_code, now)
                if not db_hist:
                    continue
                pes = [_safe_num(r.get("pe_ttm")) for r in db_hist]
                pes_30 = [v for v in pes[:30] if v is not None and v > 0]
                pes_90 = [v for v in pes[:90] if v is not None and v > 0]
                if pes_30:
                    pes_30.sort()
                    pe_30d_samples.append(pes_30[len(pes_30)//2])
                if pes_90:
                    pes_90.sort()
                    pe_90d_samples.append(pes_90[len(pes_90)//2])
            industry_pe_30d = None
            industry_pe_90d = None
            if pe_30d_samples:
                pe_30d_samples.sort()
                industry_pe_30d = pe_30d_samples[len(pe_30d_samples)//2]
            if pe_90d_samples:
                pe_90d_samples.sort()
                industry_pe_90d = pe_90d_samples[len(pe_90d_samples)//2]
            vc_payload, vc_status = _derive_valuation_compression(
                industry_pe_30d, industry_pe_90d,
            )
            vc_payload["industry_id"] = industry_id
            rows.append((
                f"INDUSTRY:{industry_id}", "L8.industry.valuation_compression",
                json.dumps(vc_payload, ensure_ascii=False),
                vc_status, 0.7 if vc_status == "Known" else 0.0,
                "tushare:daily_basic.industry_pe", now,
            ))
            sev = vc_payload.get("alert_severity")
            if sev in ("WARN", "ERROR"):
                alert_dist[sev] += 1
        except Exception as e:  # noqa: BLE001
            log.warning(
                "[tushare] BucketA L8.industry.valuation %s failed: %s",
                industry_id, e,
            )

    log.info(
        "[tushare] BucketA: %d rows across %d A-shares + %d industries; "
        "Known/Inactive per dp_id: %s; alert_severity: %s",
        len(rows), len(a_codes), len(industries), counts, alert_dist,
    )
    return rows


# ===========================================================================
# Bucket B — 12 hard-data dp_ids (估值 + 卖方研报 + L0 行业 sentiment + peer)
# ===========================================================================
#
# Bucket B emits the following dp_ids, additive over Tushare A + Bucket A:
#
#   B1 — L0.* industry sentinel (4):
#     * L0.cost.capital            (MARKET:CN)  shibor_lpr + industry spread
#     * L0.sentiment.institutional (per industry) top10_holders avg / 30d delta
#     * L0.sentiment.leader_drag   (per industry) leader 5d vs follower 5d
#     * L0.sentiment.social        (per industry) dc_hot + ths_hot count
#   B2 — L6 valuation (5):
#     * L6.priced.analyst_revision  (per-stock) report_rc 90d up/down counts
#     * L6.priced.discussion        (per-stock) dc_hot + ths_hot 30d hits
#     * L6.state.expansion_compression (per-stock) PE vs 60d / 250d MA regime
#     * L6.state.industry_center    (per industry) PE/PB/PS median
#     * L6.state.peer_compare       (per-stock) stock PE vs industry median
#   B3 — L7.mood + L9.media (2):
#     * L7.mood.analyst_rating      (per-stock) rating distribution + score
#     * L9.media.analyst_action     (per-stock) recent 7d rating changes
#   B4 — L10.val.peer (1):
#     * L10.val.peer                (per-stock) validation view (mirror of
#                                    L6.state.peer_compare with the L10
#                                    convergent/divergent label).
#
# Caching: each Tushare endpoint is wrapped in a per-stock or per-market
# helper with a 5-min TTL. Cross-sectional ``daily_basic`` snapshots used by
# ``L6.state.industry_center`` reuse Tushare A's full-market call where
# possible (passed in via ``daily_basic_full_snapshot``).
#
# Each fetcher is independently try/except'd: a single endpoint permission
# denial or schema drift never zeros out the rest of the batch.


def _get_report_rc_records(
    pro,
    ts_code: str,
    now: int,
    lookback_days: int = 90,
) -> list[dict]:
    """Return per-ts_code report_rc records sorted by report_date desc.

    Cached per-ts_code with ``_FINA_CACHE_TTL_S`` TTL. Empty list on any
    failure (permission, schema drift) so callers can branch to Inactive.
    """

    cached = _cache_get(_REPORT_RC_CACHE, ts_code, _FINA_CACHE_TTL_S, now)
    if cached is not None:
        return cached
    end_date = _today_yyyymmdd()
    start_date = _previous_n_days(lookback_days)
    try:
        df = pro.report_rc(
            ts_code=ts_code,
            start_date=start_date,
            end_date=end_date,
        )
        time.sleep(_BUCKET_A_SLEEP_S)
    except Exception as e:  # noqa: BLE001
        msg = str(e)
        if any(k in msg for k in ("权限", "积分", "permission", "credit")):
            log.warning(
                "[tushare] BucketB report_rc %s permission issue: %s",
                ts_code, e,
            )
        else:
            log.warning(
                "[tushare] BucketB report_rc %s failed: %s", ts_code, e,
            )
        _cache_put(_REPORT_RC_CACHE, ts_code, [], now)
        return []
    if df is None or len(df) == 0:
        _cache_put(_REPORT_RC_CACHE, ts_code, [], now)
        return []
    records = df.to_dict(orient="records")
    records.sort(key=lambda r: r.get("report_date") or "", reverse=True)
    _cache_put(_REPORT_RC_CACHE, ts_code, records, now)
    return records


def _get_dc_hot_records(pro, now: int) -> list[dict]:
    """Return latest dc_hot (东方财富热榜) records — market-wide, single TTL slot.

    Cached at module level (not per-ts_code) because the endpoint returns the
    whole market snapshot in one call.
    """

    global _DC_HOT_CACHE
    if _DC_HOT_CACHE is not None:
        cached_ts, records = _DC_HOT_CACHE
        if now - cached_ts < _FINA_CACHE_TTL_S:
            return records
    try:
        df = pro.dc_hot(market="A股市场", hot_type="人气榜")
        time.sleep(_BUCKET_A_SLEEP_S)
    except Exception as e:  # noqa: BLE001
        log.warning("[tushare] BucketB dc_hot failed: %s", e)
        _DC_HOT_CACHE = (now, [])
        return []
    if df is None or len(df) == 0:
        _DC_HOT_CACHE = (now, [])
        return []
    records = df.to_dict(orient="records")
    _DC_HOT_CACHE = (now, records)
    return records


def _get_ths_hot_records(pro, now: int) -> list[dict]:
    """Return latest ths_hot (同花顺热榜) records — market-wide, single TTL slot."""

    global _THS_HOT_CACHE
    if _THS_HOT_CACHE is not None:
        cached_ts, records = _THS_HOT_CACHE
        if now - cached_ts < _FINA_CACHE_TTL_S:
            return records
    try:
        df = pro.ths_hot(market="A股市场", is_new="Y")
        time.sleep(_BUCKET_A_SLEEP_S)
    except Exception as e:  # noqa: BLE001
        log.warning("[tushare] BucketB ths_hot failed: %s", e)
        _THS_HOT_CACHE = (now, [])
        return []
    if df is None or len(df) == 0:
        _THS_HOT_CACHE = (now, [])
        return []
    records = df.to_dict(orient="records")
    _THS_HOT_CACHE = (now, records)
    return records


def _get_top10_holders_records(pro, ts_code: str, now: int) -> list[dict]:
    """Return up to 4 most recent reporting periods of top10 holders.

    Used for ``L0.sentiment.institutional`` to compute mean institutional
    holding pct and 30-day delta.
    """

    cached = _cache_get(_TOP10_HOLDERS_CACHE, ts_code, _FINA_CACHE_TTL_S, now)
    if cached is not None:
        return cached
    try:
        df = pro.top10_holders(
            ts_code=ts_code,
            start_date=_previous_n_days(180),
            end_date=_today_yyyymmdd(),
        )
        time.sleep(_BUCKET_A_SLEEP_S)
    except Exception as e:  # noqa: BLE001
        log.warning(
            "[tushare] BucketB top10_holders %s failed: %s", ts_code, e,
        )
        _cache_put(_TOP10_HOLDERS_CACHE, ts_code, [], now)
        return []
    if df is None or len(df) == 0:
        _cache_put(_TOP10_HOLDERS_CACHE, ts_code, [], now)
        return []
    records = df.to_dict(orient="records")
    # Sort by end_date desc so latest period is first; we'll need 2 periods
    # to compute the delta.
    records.sort(key=lambda r: r.get("end_date") or "", reverse=True)
    _cache_put(_TOP10_HOLDERS_CACHE, ts_code, records, now)
    return records


def _get_daily_basic_history_long(
    pro, ts_code: str, now: int, history_days: int = 300,
) -> list[dict]:
    """Return per-ts_code daily_basic history with ≥250 trading days.

    Used by ``L6.state.expansion_compression`` to compute the 60d / 250d
    PE_ttm moving averages. A separate cache from the Bucket A 120d version
    so we don't invalidate that on Bucket B's wider window.
    """

    cached = _cache_get(
        _DAILY_BASIC_HISTORY_LONG_CACHE, ts_code, _FINA_CACHE_TTL_S, now,
    )
    if cached is not None:
        return cached
    end = _today_yyyymmdd()
    # Pad +60 days for trading holidays so 250 trading days fit.
    start = _previous_n_days(history_days + 60)
    try:
        df = pro.daily_basic(
            ts_code=ts_code, start_date=start, end_date=end,
            fields="ts_code,trade_date,pe_ttm,pb,ps_ttm,total_mv",
        )
        time.sleep(_BUCKET_A_SLEEP_S)
    except Exception as e:  # noqa: BLE001
        log.warning(
            "[tushare] BucketB daily_basic.history_long %s failed: %s",
            ts_code, e,
        )
        _cache_put(_DAILY_BASIC_HISTORY_LONG_CACHE, ts_code, [], now)
        return []
    if df is None or len(df) == 0:
        _cache_put(_DAILY_BASIC_HISTORY_LONG_CACHE, ts_code, [], now)
        return []
    records = df.to_dict(orient="records")
    records.sort(key=lambda r: r.get("trade_date") or "", reverse=True)
    _cache_put(_DAILY_BASIC_HISTORY_LONG_CACHE, ts_code, records, now)
    return records


def _get_daily_basic_full_snapshot(pro, now: int) -> list[dict]:
    """Return the latest full-market daily_basic cross-section.

    Used by L6.state.industry_center to compute industry-wide PE/PB/PS
    medians. Cache key is fixed since the call covers all A-shares for the
    latest trade_date — a 5-min TTL is more than enough.
    """

    cache_key = "__FULL_DAILY_BASIC__"
    cached = _cache_get(
        _DAILY_BASIC_HISTORY_LONG_CACHE, cache_key, _FINA_CACHE_TTL_S, now,
    )
    if cached is not None:
        return cached
    df = None
    latest_trade_date = None
    for back in range(0, 8):
        trade_date = _previous_n_days(back)
        try:
            tmp = pro.daily_basic(
                trade_date=trade_date,
                fields=("ts_code,trade_date,pe_ttm,pb,ps_ttm,total_mv,"
                        "turnover_rate,pct_chg"),
            )
            time.sleep(_BUCKET_A_SLEEP_S)
            if tmp is not None and len(tmp) > 0:
                df = tmp
                latest_trade_date = trade_date
                break
        except Exception as e:  # noqa: BLE001
            log.warning(
                "[tushare] BucketB daily_basic full %s failed: %s",
                trade_date, e,
            )
            continue
    if df is None or len(df) == 0:
        _cache_put(_DAILY_BASIC_HISTORY_LONG_CACHE, cache_key, [], now)
        return []
    records = df.to_dict(orient="records")
    # Stamp latest_trade_date on each record for the caller's convenience.
    for r in records:
        r.setdefault("__trade_date__", latest_trade_date)
    _cache_put(_DAILY_BASIC_HISTORY_LONG_CACHE, cache_key, records, now)
    return records


# ---------------------------------------------------------------------------
# Derivation helpers
# ---------------------------------------------------------------------------


def _median(values: list[float]) -> float | None:
    """Compute median (ignoring None/NaN)."""

    clean = [v for v in values if v is not None]
    if not clean:
        return None
    clean.sort()
    n = len(clean)
    if n % 2 == 1:
        return clean[n // 2]
    return (clean[n // 2 - 1] + clean[n // 2]) / 2.0


def _percentile_rank(value: float | None, sorted_values: list[float]) -> float | None:
    """Return the percentile rank (0-100) of ``value`` against ``sorted_values``.

    ``sorted_values`` must already be sorted ascending. Returns None on
    empty / missing input.
    """

    if value is None or not sorted_values:
        return None
    n = len(sorted_values)
    below = 0
    for v in sorted_values:
        if v < value:
            below += 1
        else:
            break
    return (below / n) * 100.0


# ---------------------------------------------------------------------------
# B1: L0 industry-sentinel fetchers
# ---------------------------------------------------------------------------


def _emit_cost_capital(pro, now: int) -> list[tuple]:
    """``L0.cost.capital`` — MARKET:CN row from shibor_lpr + industry spread.

    Simplification: 行业资金成本 = LPR_1y + 1.5pp industry risk premium.
    The payload exposes both components so downstream layers can refine.

    Caches the shibor_lpr response at module level (``_SHIBOR_LPR_CACHE``)
    with the standard 5-min TTL so back-to-back collector cycles don't
    re-pull the same monthly data.
    """

    global _SHIBOR_LPR_CACHE
    records: list[dict] = []
    if _SHIBOR_LPR_CACHE is not None:
        cached_ts, cached_records = _SHIBOR_LPR_CACHE
        if now - cached_ts < _FINA_CACHE_TTL_S:
            records = cached_records
    if not records:
        try:
            df = pro.shibor_lpr(fields="date,1y,5y")
            time.sleep(_BUCKET_A_SLEEP_S)
        except Exception as e:  # noqa: BLE001
            log.warning("[tushare] BucketB shibor_lpr failed: %s", e)
            _SHIBOR_LPR_CACHE = (now, [])
            return [(
                "MARKET:CN", "L0.cost.capital",
                json.dumps({"reason": "shibor_lpr endpoint failed"},
                           ensure_ascii=False),
                "Inactive", 0.0, "tushare:shibor_lpr", now,
            )]
        if df is None or len(df) == 0:
            _SHIBOR_LPR_CACHE = (now, [])
            return [(
                "MARKET:CN", "L0.cost.capital",
                json.dumps({"reason": "no shibor_lpr data"},
                           ensure_ascii=False),
                "Inactive", 0.0, "tushare:shibor_lpr", now,
            )]
        df_sorted = df.sort_values("date", ascending=False)
        records = df_sorted.to_dict(orient="records")
        _SHIBOR_LPR_CACHE = (now, records)
    if not records:
        return [(
            "MARKET:CN", "L0.cost.capital",
            json.dumps({"reason": "no shibor_lpr data"},
                       ensure_ascii=False),
            "Inactive", 0.0, "tushare:shibor_lpr", now,
        )]
    latest = records[0]
    lpr_1y = _safe_num(latest.get("1y"))
    lpr_5y = _safe_num(latest.get("5y"))
    industry_spread_pp = 1.5  # heuristic; downstream may refine per industry
    cost_capital = None
    if lpr_1y is not None:
        cost_capital = lpr_1y + industry_spread_pp
    payload = {
        "lpr_1y_pct": lpr_1y,
        "lpr_5y_pct": lpr_5y,
        "industry_spread_pp": industry_spread_pp,
        "implied_cost_of_capital_pct": cost_capital,
        "as_of": latest.get("date"),
        "method": "LPR_1y + 1.5pp industry risk premium",
    }
    status = "Known" if lpr_1y is not None else "Inactive"
    return [(
        "MARKET:CN", "L0.cost.capital",
        json.dumps(payload, ensure_ascii=False),
        status, 0.7 if status == "Known" else 0.0,
        "tushare:shibor_lpr", now,
    )]


def _emit_sentiment_institutional(
    pro,
    industries: list[str],
    code_to_industry: dict[str, str | None],
    now: int,
) -> list[tuple]:
    """``L0.sentiment.institutional`` — per industry top10 inst holding stats.

    For each active industry we sample the constituent stocks present in
    ``code_to_industry`` (mapped to that industry_id), pull top10_holders for
    each, average the latest-period hold_ratio, and compute a 30-day delta
    vs the prior period. Inactive if the industry has no mapped stocks.
    """

    # Build per-industry sample list (cap to first 5 stocks for RPC budget)
    industry_to_codes: dict[str, list[str]] = {}
    for code, ind in code_to_industry.items():
        if not ind:
            continue
        industry_to_codes.setdefault(ind, []).append(code)

    rows: list[tuple] = []
    for industry_id in industries:
        sample = industry_to_codes.get(industry_id, [])[:5]
        if not sample:
            rows.append((
                f"INDUSTRY:{industry_id}", "L0.sentiment.institutional",
                json.dumps({
                    "industry_id": industry_id,
                    "reason": "no sampled constituents in code_to_industry",
                }, ensure_ascii=False),
                "Inactive", 0.0, "tushare:top10_holders", now,
            ))
            continue

        latest_ratios: list[float] = []
        delta_30d: list[float] = []
        n_stocks = 0
        for ts_code in sample:
            recs = _get_top10_holders_records(pro, ts_code, now)
            if not recs:
                continue
            # Group by end_date so we can average per period.
            by_period: dict[str, list[float]] = {}
            for r in recs:
                ed = r.get("end_date")
                if not ed:
                    continue
                ratio = _safe_num(r.get("hold_ratio"))
                if ratio is None:
                    continue
                by_period.setdefault(ed, []).append(ratio)
            periods = sorted(by_period.keys(), reverse=True)
            if not periods:
                continue
            latest_avg = sum(by_period[periods[0]]) / len(by_period[periods[0]])
            latest_ratios.append(latest_avg)
            if len(periods) >= 2:
                prior_avg = (
                    sum(by_period[periods[1]]) / len(by_period[periods[1]])
                )
                delta_30d.append(latest_avg - prior_avg)
            n_stocks += 1

        if not latest_ratios:
            rows.append((
                f"INDUSTRY:{industry_id}", "L0.sentiment.institutional",
                json.dumps({
                    "industry_id": industry_id,
                    "reason": "no top10_holders data for sampled stocks",
                    "n_stocks_sampled": n_stocks,
                }, ensure_ascii=False),
                "Inactive", 0.0, "tushare:top10_holders", now,
            ))
            continue

        mean_inst = sum(latest_ratios) / len(latest_ratios)
        delta_mean = (
            sum(delta_30d) / len(delta_30d) if delta_30d else None
        )
        payload = {
            "industry_id": industry_id,
            "mean_inst_holding_pct": round(mean_inst, 4),
            "delta_30d_pp": round(delta_mean, 4) if delta_mean is not None else None,
            "n_stocks_sampled": n_stocks,
            "as_of": _today_yyyymmdd(),
        }
        rows.append((
            f"INDUSTRY:{industry_id}", "L0.sentiment.institutional",
            json.dumps(payload, ensure_ascii=False),
            "Known", 0.65, "tushare:top10_holders", now,
        ))
    return rows


def _emit_sentiment_leader_drag(
    pro,
    industries: list[str],
    code_to_industry: dict[str, str | None],
    now: int,
    daily_basic_snapshot: list[dict] | None = None,
) -> list[tuple]:
    """``L0.sentiment.leader_drag`` — leader 5d vs follower 5d per industry.

    Uses the full-market daily_basic snapshot (passed in or fetched) to find
    each industry's top-3 by total_mv (the *leaders*) and computes their
    mean 5d return vs the rest of the industry. Positive drag = leaders
    outperforming; negative = leaders lagging.

    Note: total_mv from daily_basic is current-day market cap, not historical.
    For the 5d return we use ``pct_chg`` from daily_basic (today's daily move)
    aggregated via cached daily history per stock. Cheapest path: fall back
    to a coarse same-day pct_chg if the 5d series isn't cached.
    """

    if daily_basic_snapshot is None:
        daily_basic_snapshot = _get_daily_basic_full_snapshot(pro, now)
    if not daily_basic_snapshot:
        return [(
            f"INDUSTRY:{ind}", "L0.sentiment.leader_drag",
            json.dumps({
                "industry_id": ind,
                "reason": "no daily_basic full snapshot",
            }, ensure_ascii=False),
            "Inactive", 0.0, "tushare:daily_basic", now,
        ) for ind in industries]

    # Index snapshot by ts_code
    by_code: dict[str, dict] = {}
    for r in daily_basic_snapshot:
        code = r.get("ts_code")
        if code:
            by_code[code] = r

    # Per-industry stocks
    industry_to_codes: dict[str, list[str]] = {}
    for code, ind in code_to_industry.items():
        if not ind:
            continue
        industry_to_codes.setdefault(ind, []).append(code)

    rows: list[tuple] = []
    for industry_id in industries:
        codes = industry_to_codes.get(industry_id, [])
        if len(codes) < 2:
            rows.append((
                f"INDUSTRY:{industry_id}", "L0.sentiment.leader_drag",
                json.dumps({
                    "industry_id": industry_id,
                    "reason": "fewer than 2 stocks in industry universe",
                }, ensure_ascii=False),
                "Inactive", 0.0, "tushare:daily_basic", now,
            ))
            continue

        # Rank by total_mv to find leaders
        ranked: list[tuple[str, float, float]] = []
        for code in codes:
            rec = by_code.get(code)
            if rec is None:
                continue
            mv = _safe_num(rec.get("total_mv"))
            pct = _safe_num(rec.get("pct_chg"))
            if mv is None:
                continue
            ranked.append((code, mv, pct or 0.0))
        if len(ranked) < 2:
            rows.append((
                f"INDUSTRY:{industry_id}", "L0.sentiment.leader_drag",
                json.dumps({
                    "industry_id": industry_id,
                    "reason": "insufficient daily_basic coverage",
                    "n_stocks_in_snapshot": len(ranked),
                }, ensure_ascii=False),
                "Inactive", 0.0, "tushare:daily_basic", now,
            ))
            continue
        ranked.sort(key=lambda t: t[1], reverse=True)
        leaders = ranked[:3]
        followers = ranked[3:]
        if not followers:
            followers = ranked  # single-bucket edge case (very small industry)
        leader_5d = sum(t[2] for t in leaders) / len(leaders)
        follower_5d = sum(t[2] for t in followers) / len(followers)
        drag_pp = leader_5d - follower_5d
        polarity = "positive" if drag_pp >= 0 else "negative"
        payload = {
            "industry_id": industry_id,
            "leader_5d_pct": round(leader_5d, 4),
            "follower_5d_pct": round(follower_5d, 4),
            "drag_pp": round(drag_pp, 4),
            "polarity": polarity,
            "leader_ts_codes": [t[0] for t in leaders],
            "n_leaders": len(leaders),
            "n_followers": len(followers),
            "method": "pct_chg (latest trade_date) proxy for 5d return",
        }
        rows.append((
            f"INDUSTRY:{industry_id}", "L0.sentiment.leader_drag",
            json.dumps(payload, ensure_ascii=False),
            "Known", 0.6, "tushare:daily_basic.industry_pct", now,
        ))
    return rows


def _emit_sentiment_social(
    pro,
    industries: list[str],
    code_to_industry: dict[str, str | None],
    now: int,
) -> list[tuple]:
    """``L0.sentiment.social`` — per industry hot-board count + themes.

    Aggregates dc_hot + ths_hot across the active industries' constituent
    stocks. Hot-stocks count is the number of universe stocks in that
    industry appearing in either hot list today. Themes are the top-5
    distinct ``concept`` strings reported by either list for the industry
    stocks.
    """

    dc_records = _get_dc_hot_records(pro, now)
    ths_records = _get_ths_hot_records(pro, now)
    if not dc_records and not ths_records:
        return [(
            f"INDUSTRY:{ind}", "L0.sentiment.social",
            json.dumps({
                "industry_id": ind,
                "reason": "no dc_hot / ths_hot data",
            }, ensure_ascii=False),
            "Inactive", 0.0, "tushare:dc_hot+ths_hot", now,
        ) for ind in industries]

    # Index by ts_code
    dc_by_code: dict[str, dict] = {}
    for r in dc_records:
        c = r.get("ts_code")
        if c:
            dc_by_code[c] = r
    ths_by_code: dict[str, dict] = {}
    for r in ths_records:
        c = r.get("ts_code")
        if c:
            ths_by_code[c] = r

    industry_to_codes: dict[str, list[str]] = {}
    for code, ind in code_to_industry.items():
        if not ind:
            continue
        industry_to_codes.setdefault(ind, []).append(code)

    rows: list[tuple] = []
    for industry_id in industries:
        codes = industry_to_codes.get(industry_id, [])
        hot_codes: set[str] = set()
        themes_counter: dict[str, int] = {}
        ranks: list[float] = []
        for code in codes:
            dc = dc_by_code.get(code)
            ths = ths_by_code.get(code)
            if dc is not None:
                hot_codes.add(code)
                concept = dc.get("concept")
                if concept:
                    themes_counter[str(concept)] = (
                        themes_counter.get(str(concept), 0) + 1
                    )
                rank = _safe_num(dc.get("rank"))
                if rank is not None:
                    ranks.append(rank)
            if ths is not None:
                hot_codes.add(code)
                concept = ths.get("concept")
                if concept:
                    themes_counter[str(concept)] = (
                        themes_counter.get(str(concept), 0) + 1
                    )
                rank = _safe_num(ths.get("rank"))
                if rank is not None:
                    ranks.append(rank)

        hot_count = len(hot_codes)
        top_themes = sorted(
            themes_counter.items(), key=lambda kv: kv[1], reverse=True,
        )[:5]
        # engagement_proxy: 100 / average rank (lower rank → higher heat)
        avg_rank = (sum(ranks) / len(ranks)) if ranks else None
        engagement_proxy = (100.0 / avg_rank) if avg_rank and avg_rank > 0 else None
        if hot_count == 0:
            rows.append((
                f"INDUSTRY:{industry_id}", "L0.sentiment.social",
                json.dumps({
                    "industry_id": industry_id,
                    "hot_stocks_count_30d": 0,
                    "reason": "no industry stock on hot lists today",
                }, ensure_ascii=False),
                "Inactive", 0.0, "tushare:dc_hot+ths_hot", now,
            ))
            continue
        payload = {
            "industry_id": industry_id,
            "hot_stocks_count_30d": hot_count,
            "hot_themes": [t[0] for t in top_themes],
            "engagement_proxy": (
                round(engagement_proxy, 4) if engagement_proxy is not None else None
            ),
            "avg_rank": round(avg_rank, 2) if avg_rank is not None else None,
            "as_of": _today_yyyymmdd(),
            "method": "dc_hot + ths_hot today, industry stock count",
        }
        rows.append((
            f"INDUSTRY:{industry_id}", "L0.sentiment.social",
            json.dumps(payload, ensure_ascii=False),
            "Known", 0.6, "tushare:dc_hot+ths_hot", now,
        ))
    return rows


# ---------------------------------------------------------------------------
# B2 / B3 / B4: per-stock fetchers
# ---------------------------------------------------------------------------


_RATING_MAP = {
    # Common Tushare rating strings → score (5 = strong buy, 1 = strong sell)
    "买入": 5,
    "强烈推荐": 5,
    "强推": 5,
    "推荐": 4,
    "增持": 4,
    "审慎推荐": 4,
    "中性": 3,
    "持有": 3,
    "审慎增持": 4,
    "审慎": 3,
    "减持": 2,
    "卖出": 1,
    "回避": 1,
    "未评级": None,
}


def _classify_rating(rating: str) -> tuple[str, int | None]:
    """Map a Tushare rating string to (bucket, score) where bucket is one of
    ``strong_buy``, ``buy``, ``hold``, ``sell``, ``strong_sell``."""

    if not rating:
        return ("hold", None)
    r = str(rating).strip()
    score = _RATING_MAP.get(r)
    if score is None:
        return ("hold", None)
    if score >= 5:
        return ("strong_buy", score)
    if score == 4:
        return ("buy", score)
    if score == 3:
        return ("hold", score)
    if score == 2:
        return ("sell", score)
    return ("strong_sell", score)


def _derive_analyst_revision(records: list[dict]) -> tuple[dict, str]:
    """Compute ``L6.priced.analyst_revision`` payload + status.

    Counts upgrades / downgrades / maintains based on the comparison between
    each report's rating bucket and the same broker's prior rating in the
    90-day window. Reports without a prior comparable broker rating are
    classified as ``initiation`` (counted but not in net_revision_score).
    """

    if not records:
        return {"reason": "no sell-side reports in window"}, "Inactive"

    # Index by broker for prior-rating lookup
    by_broker: dict[str, list[dict]] = {}
    for r in records:
        broker = str(r.get("org_name") or "")
        if not broker:
            continue
        by_broker.setdefault(broker, []).append(r)
    for lst in by_broker.values():
        lst.sort(key=lambda x: x.get("report_date") or "")

    upgrades = 0
    downgrades = 0
    maintains = 0
    initiations = 0
    for broker, lst in by_broker.items():
        last_score: int | None = None
        for r in lst:
            bucket, score = _classify_rating(r.get("rating") or "")
            if score is None:
                continue
            if last_score is None:
                initiations += 1
            elif score > last_score:
                upgrades += 1
            elif score < last_score:
                downgrades += 1
            else:
                maintains += 1
            last_score = score

    total_signed = upgrades - downgrades
    denom = upgrades + downgrades + maintains
    net_revision_score = (total_signed / denom) if denom > 0 else 0.0
    payload = {
        "upgrades": upgrades,
        "downgrades": downgrades,
        "maintains": maintains,
        "initiations": initiations,
        "net_revision_score": round(net_revision_score, 4),
        "period_days": 90,
        "n_reports": len(records),
    }
    status = "Known" if (upgrades + downgrades + maintains + initiations) > 0 else "Inactive"
    return payload, status


def _derive_discussion(
    ts_code: str,
    dc_records: list[dict],
    ths_records: list[dict],
) -> tuple[dict, str]:
    """Compute ``L6.priced.discussion`` payload for a single ts_code.

    Tushare's dc_hot / ths_hot return only the *current* day's snapshot —
    we can't compute a true 30d window without a per-day fan-out. We use the
    latest snapshot's rank as a proxy: a stock on the hot list today has at
    least one hit; the rank-percentile gives a relative heat score.
    """

    dc_hits = sum(1 for r in dc_records if r.get("ts_code") == ts_code)
    ths_hits = sum(1 for r in ths_records if r.get("ts_code") == ts_code)
    if dc_hits == 0 and ths_hits == 0:
        return ({"reason": "not on dc_hot or ths_hot today",
                 "dc_hot_count_30d": 0, "ths_hot_count_30d": 0}, "Inactive")

    # Average rank percentile across hits
    ranks: list[float] = []
    n_dc = len(dc_records) or 1
    n_ths = len(ths_records) or 1
    for r in dc_records:
        if r.get("ts_code") == ts_code:
            rank = _safe_num(r.get("rank"))
            if rank is not None:
                ranks.append(rank / n_dc * 100.0)
    for r in ths_records:
        if r.get("ts_code") == ts_code:
            rank = _safe_num(r.get("rank"))
            if rank is not None:
                ranks.append(rank / n_ths * 100.0)
    avg_rank_pct = (sum(ranks) / len(ranks)) if ranks else None
    payload = {
        "dc_hot_count_30d": dc_hits,
        "ths_hot_count_30d": ths_hits,
        "avg_rank_pct": round(avg_rank_pct, 4) if avg_rank_pct is not None else None,
        "as_of": _today_yyyymmdd(),
        "method": "today's dc_hot + ths_hot rank (single-day snapshot proxy)",
    }
    return payload, "Known"


def _derive_expansion_compression(
    daily_basic_records: list[dict],
) -> tuple[dict, str]:
    """Compute ``L6.state.expansion_compression`` payload + status.

    Compare current PE to 60d MA and 250d MA. < 0.95 → compressed (cheap),
    > 1.05 → expanded (rich), else neutral. Slope = (current - 250d MA) /
    250d MA, signed.
    """

    if not daily_basic_records:
        return ({"reason": "no daily_basic history"}, "Inactive")
    # Records are pre-sorted newest first.
    pe_series = [
        _safe_num(r.get("pe_ttm")) for r in daily_basic_records
    ]
    pe_clean = [v for v in pe_series if v is not None and v > 0]
    if len(pe_clean) < 60:
        return ({"reason": "insufficient history (<60 trading days)",
                 "n_days": len(pe_clean)}, "Inactive")
    pe_current = pe_clean[0]
    pe_60d = pe_clean[:60]
    pe_250d = pe_clean[: min(250, len(pe_clean))]
    pe_60d_ma = sum(pe_60d) / len(pe_60d)
    pe_250d_ma = sum(pe_250d) / len(pe_250d)
    # Compare current vs 250d MA for regime classification.
    if pe_250d_ma == 0:
        return ({"reason": "PE 250d MA = 0"}, "Inactive")
    ratio = pe_current / pe_250d_ma
    if ratio < 0.95:
        regime = "compressed"
    elif ratio > 1.05:
        regime = "expanded"
    else:
        regime = "neutral"
    slope = (pe_current - pe_250d_ma) / pe_250d_ma
    payload = {
        "pe_current": round(pe_current, 4),
        "pe_60d_ma": round(pe_60d_ma, 4),
        "pe_250d_ma": round(pe_250d_ma, 4),
        "ratio_vs_250d": round(ratio, 4),
        "slope": round(slope, 4),
        "regime": regime,
        "n_days_60d": len(pe_60d),
        "n_days_250d": len(pe_250d),
    }
    return payload, "Known"


def _derive_industry_center(
    industry_id: str,
    codes: list[str],
    snapshot_by_code: dict[str, dict],
    trade_date: str | None,
) -> tuple[dict, str]:
    """Compute ``L6.state.industry_center`` payload + status for one industry.

    Uses the full-market daily_basic snapshot to extract PE/PB/PS for the
    industry's constituent stocks and takes the median. Inactive when fewer
    than 2 stocks have valid data.
    """

    pe_vals: list[float] = []
    pb_vals: list[float] = []
    ps_vals: list[float] = []
    for code in codes:
        rec = snapshot_by_code.get(code)
        if rec is None:
            continue
        pe = _safe_num(rec.get("pe_ttm"))
        pb = _safe_num(rec.get("pb"))
        ps = _safe_num(rec.get("ps_ttm"))
        if pe is not None and pe > 0:
            pe_vals.append(pe)
        if pb is not None and pb > 0:
            pb_vals.append(pb)
        if ps is not None and ps > 0:
            ps_vals.append(ps)
    n_stocks = max(len(pe_vals), len(pb_vals), len(ps_vals))
    if n_stocks < 2:
        return ({
            "industry_id": industry_id,
            "reason": "fewer than 2 stocks with valuation data",
            "n_stocks": n_stocks,
        }, "Inactive")
    payload = {
        "industry_id": industry_id,
        "industry_pe_median": _median(pe_vals),
        "industry_pb_median": _median(pb_vals),
        "industry_ps_median": _median(ps_vals),
        "n_stocks": n_stocks,
        "trade_date": trade_date,
    }
    # Round
    for k in ("industry_pe_median", "industry_pb_median", "industry_ps_median"):
        if payload[k] is not None:
            payload[k] = round(payload[k], 4)
    return payload, "Known"


def _derive_peer_compare(
    ts_code: str,
    stock_record: dict | None,
    industry_center: dict | None,
) -> tuple[dict, dict, str]:
    """Compute (peer_compare_payload, val_peer_payload, status) for a stock.

    Returns both ``L6.state.peer_compare`` and ``L10.val.peer`` payloads from
    the same computation so the two dp_ids stay byte-identical on the input
    side.
    """

    if stock_record is None or industry_center is None:
        reason = "no stock daily_basic record" if stock_record is None else \
                 "no industry_center for stock's industry"
        return (
            {"reason": reason},
            {"reason": reason},
            "Inactive",
        )
    if "industry_pe_median" not in industry_center:
        return (
            {"reason": "industry_center missing pe_median"},
            {"reason": "industry_center missing pe_median"},
            "Inactive",
        )
    stock_pe = _safe_num(stock_record.get("pe_ttm"))
    stock_pb = _safe_num(stock_record.get("pb"))
    ind_pe = industry_center.get("industry_pe_median")
    ind_pb = industry_center.get("industry_pb_median")
    if stock_pe is None or ind_pe is None or ind_pe <= 0:
        return (
            {"reason": "missing stock or industry PE",
             "stock_pe": stock_pe, "industry_pe_median": ind_pe},
            {"reason": "missing stock or industry PE",
             "stock_pe": stock_pe, "industry_pe_median": ind_pe},
            "Inactive",
        )
    premium_pct = (stock_pe - ind_pe) / ind_pe * 100.0
    # Percentile rank: not computed without full industry distribution; use
    # ratio as a coarse signal.
    if abs(premium_pct) < 15.0:
        validation_signal = "convergent"
    else:
        validation_signal = "divergent"
    peer_compare_payload = {
        "stock_pe": round(stock_pe, 4),
        "industry_pe_median": round(ind_pe, 4),
        "industry_id": industry_center.get("industry_id"),
        "premium_vs_industry_pct": round(premium_pct, 4),
        "trade_date": industry_center.get("trade_date"),
    }
    val_peer_payload = {
        "stock_pe": round(stock_pe, 4),
        "stock_pb": round(stock_pb, 4) if stock_pb is not None else None,
        "industry_pe_median": round(ind_pe, 4),
        "industry_pb_median": (
            round(ind_pb, 4) if ind_pb is not None else None
        ),
        "industry_id": industry_center.get("industry_id"),
        "premium_vs_industry_pct": round(premium_pct, 4),
        "validation_signal": validation_signal,
        "trade_date": industry_center.get("trade_date"),
    }
    return peer_compare_payload, val_peer_payload, "Known"


def _derive_analyst_rating(records: list[dict]) -> tuple[dict, str]:
    """Compute ``L7.mood.analyst_rating`` payload + status.

    Counts each report's rating bucket. Reports without a parseable rating
    are dropped silently.
    """

    if not records:
        return ({"reason": "no sell-side reports in window"}, "Inactive")
    counts = {
        "strong_buy": 0, "buy": 0, "hold": 0, "sell": 0, "strong_sell": 0,
    }
    scores: list[int] = []
    # Dedup by (report_date, org_name) to avoid year-fan-out double counting.
    seen: set[tuple] = set()
    for r in records:
        key = (
            r.get("report_date"),
            r.get("org_name"),
            r.get("author_name"),
        )
        if key in seen:
            continue
        seen.add(key)
        bucket, score = _classify_rating(r.get("rating") or "")
        if score is None:
            continue
        counts[bucket] = counts.get(bucket, 0) + 1
        scores.append(score)
    n_reports = sum(counts.values())
    if n_reports == 0:
        return ({"reason": "no parseable ratings in window",
                 "raw_records": len(records)}, "Inactive")
    avg_score = sum(scores) / len(scores)
    payload = {
        **counts,
        "avg_rating_score": round(avg_score, 4),
        "n_reports": n_reports,
        "period_days": 90,
    }
    return payload, "Known"


def _derive_analyst_action(records: list[dict]) -> tuple[dict, str]:
    """Compute ``L9.media.analyst_action`` payload + status.

    Scans the last 7 days for any rating change (broker's prior rating vs
    this report's rating, both within the 90d cache window). Reports a list
    of recent changes + count_7d + action_type ("upgrade_event" /
    "downgrade_event" / "none").
    """

    if not records:
        return ({"reason": "no sell-side reports", "count_7d": 0,
                 "action_type": "none"}, "Inactive")

    cutoff_7d = _previous_n_days(7)
    # Sort by report_date ASC for sliding broker comparison
    by_broker: dict[str, list[dict]] = {}
    for r in records:
        broker = str(r.get("org_name") or "")
        if not broker:
            continue
        by_broker.setdefault(broker, []).append(r)
    for lst in by_broker.values():
        lst.sort(key=lambda x: x.get("report_date") or "")

    recent_changes: list[dict] = []
    upgrade_count = 0
    downgrade_count = 0
    for broker, lst in by_broker.items():
        last_score: int | None = None
        last_rating: str | None = None
        for r in lst:
            rating = r.get("rating") or ""
            bucket, score = _classify_rating(rating)
            if score is None:
                continue
            rd = r.get("report_date") or ""
            if last_score is not None and score != last_score and rd >= cutoff_7d:
                if score > last_score:
                    upgrade_count += 1
                    change_type = "upgrade"
                else:
                    downgrade_count += 1
                    change_type = "downgrade"
                recent_changes.append({
                    "date": rd,
                    "broker": broker,
                    "prev_rating": last_rating,
                    "new_rating": rating,
                    "change_type": change_type,
                })
            last_score = score
            last_rating = rating

    count_7d = upgrade_count + downgrade_count
    if count_7d == 0:
        return ({
            "recent_changes": [],
            "count_7d": 0,
            "action_type": "none",
            "lookback_days": 7,
        }, "Inactive")
    if upgrade_count >= downgrade_count:
        action_type = "upgrade_event"
    else:
        action_type = "downgrade_event"
    payload = {
        "recent_changes": recent_changes[:10],
        "count_7d": count_7d,
        "upgrade_count": upgrade_count,
        "downgrade_count": downgrade_count,
        "action_type": action_type,
        "lookback_days": 7,
    }
    return payload, "Known"


# ---------------------------------------------------------------------------
# B: top-level dispatcher
# ---------------------------------------------------------------------------


def fetch_bucket_b_batch(
    pro,
    a_codes: list[str],
    code_to_industry: dict[str, str | None] | None = None,
    now: int | None = None,
) -> list[tuple]:
    """Emit all 12 Bucket B dp_ids for the given A-share codes.

    ``code_to_industry`` is optional but recommended — without it the
    industry-level fan-out (L0.sentiment.* and L6.state.industry_center) only
    emits ``Inactive`` rows because there's nothing to aggregate. The
    market-level row (``L0.cost.capital``) is unaffected.

    Returns rows in the standard 7-tuple shape; never raises.
    """

    if now is None:
        now = int(time.time())
    if code_to_industry is None:
        code_to_industry = {}
    rows: list[tuple] = []

    counts = {
        "L0.cost.capital":               {"Known": 0, "Inactive": 0},
        "L0.sentiment.institutional":    {"Known": 0, "Inactive": 0},
        "L0.sentiment.leader_drag":      {"Known": 0, "Inactive": 0},
        "L0.sentiment.social":           {"Known": 0, "Inactive": 0},
        "L6.priced.analyst_revision":    {"Known": 0, "Inactive": 0},
        "L6.priced.discussion":          {"Known": 0, "Inactive": 0},
        "L6.state.expansion_compression": {"Known": 0, "Inactive": 0},
        "L6.state.industry_center":      {"Known": 0, "Inactive": 0},
        "L6.state.peer_compare":         {"Known": 0, "Inactive": 0},
        "L7.mood.analyst_rating":        {"Known": 0, "Inactive": 0},
        "L9.media.analyst_action":       {"Known": 0, "Inactive": 0},
        "L10.val.peer":                  {"Known": 0, "Inactive": 0},
    }

    def _emit(dp_id: str, ts_code: str, payload: dict, status: str,
              confidence: float, source: str) -> None:
        rows.append((
            ts_code, dp_id,
            json.dumps(payload, ensure_ascii=False),
            status, confidence if status == "Known" else 0.0,
            source, now,
        ))
        if dp_id in counts:
            counts[dp_id][status] = counts[dp_id].get(status, 0) + 1

    # ── B1.a: L0.cost.capital (market-level) ──
    try:
        for r in _emit_cost_capital(pro, now):
            rows.append(r)
            if r[1] in counts:
                counts[r[1]][r[3]] = counts[r[1]].get(r[3], 0) + 1
    except Exception as e:  # noqa: BLE001
        log.warning("[tushare] BucketB L0.cost.capital failed: %s", e)

    # ── Industry-level fetchers ──
    try:
        industries = _active_industry_ids()
    except Exception as e:  # noqa: BLE001
        log.warning("[tushare] BucketB _active_industry_ids failed: %s", e)
        industries = []

    # Pull full-market daily_basic snapshot once and reuse across
    # industry-center + leader_drag.
    try:
        snapshot = _get_daily_basic_full_snapshot(pro, now)
    except Exception as e:  # noqa: BLE001
        log.warning(
            "[tushare] BucketB daily_basic full snapshot failed: %s", e,
        )
        snapshot = []

    snapshot_by_code: dict[str, dict] = {}
    snapshot_trade_date: str | None = None
    for rec in snapshot:
        c = rec.get("ts_code")
        if c:
            snapshot_by_code[c] = rec
            if snapshot_trade_date is None:
                snapshot_trade_date = (
                    rec.get("__trade_date__") or rec.get("trade_date")
                )

    # B1.b: L0.sentiment.institutional
    try:
        for r in _emit_sentiment_institutional(
            pro, industries, code_to_industry, now,
        ):
            rows.append(r)
            if r[1] in counts:
                counts[r[1]][r[3]] = counts[r[1]].get(r[3], 0) + 1
    except Exception as e:  # noqa: BLE001
        log.warning("[tushare] BucketB L0.sentiment.institutional failed: %s", e)

    # B1.c: L0.sentiment.leader_drag
    try:
        for r in _emit_sentiment_leader_drag(
            pro, industries, code_to_industry, now,
            daily_basic_snapshot=snapshot,
        ):
            rows.append(r)
            if r[1] in counts:
                counts[r[1]][r[3]] = counts[r[1]].get(r[3], 0) + 1
    except Exception as e:  # noqa: BLE001
        log.warning("[tushare] BucketB L0.sentiment.leader_drag failed: %s", e)

    # B1.d: L0.sentiment.social
    try:
        for r in _emit_sentiment_social(
            pro, industries, code_to_industry, now,
        ):
            rows.append(r)
            if r[1] in counts:
                counts[r[1]][r[3]] = counts[r[1]].get(r[3], 0) + 1
    except Exception as e:  # noqa: BLE001
        log.warning("[tushare] BucketB L0.sentiment.social failed: %s", e)

    # B2.d: L6.state.industry_center (per industry)
    # Populate the in-memory _INDUSTRY_CENTER_CACHE keyed by industry_id so
    # the per-stock peer_compare/val.peer step can read without re-deriving.
    industry_to_codes: dict[str, list[str]] = {}
    for code, ind in code_to_industry.items():
        if not ind:
            continue
        industry_to_codes.setdefault(ind, []).append(code)
    industry_center_by_id: dict[str, dict] = {}
    for industry_id in industries:
        try:
            codes_for_ind = industry_to_codes.get(industry_id, [])
            payload, status = _derive_industry_center(
                industry_id, codes_for_ind, snapshot_by_code,
                snapshot_trade_date,
            )
            _emit(
                "L6.state.industry_center",
                f"INDUSTRY:{industry_id}",
                payload, status, 0.7, "tushare:daily_basic.industry_median",
            )
            if status == "Known":
                industry_center_by_id[industry_id] = payload
                _INDUSTRY_CENTER_CACHE[industry_id] = (now, payload)
        except Exception as e:  # noqa: BLE001
            log.warning(
                "[tushare] BucketB L6.state.industry_center %s failed: %s",
                industry_id, e,
            )

    # Pre-fetch dc_hot / ths_hot (used by both per-stock discussion + industry social)
    try:
        dc_records = _get_dc_hot_records(pro, now)
    except Exception as e:  # noqa: BLE001
        log.warning("[tushare] BucketB dc_hot pre-fetch failed: %s", e)
        dc_records = []
    try:
        ths_records = _get_ths_hot_records(pro, now)
    except Exception as e:  # noqa: BLE001
        log.warning("[tushare] BucketB ths_hot pre-fetch failed: %s", e)
        ths_records = []

    # ── Per-stock fetchers (B2.a/b/c/e + B3 + B4) ──
    for ts_code in a_codes:
        if not is_a_share(ts_code):
            continue

        # B2.a / B3.a / B3.b: report_rc derived dp_ids share a single
        # _get_report_rc_records call.
        try:
            rc_records = _get_report_rc_records(pro, ts_code, now)
            rev_payload, rev_status = _derive_analyst_revision(rc_records)
            _emit("L6.priced.analyst_revision", ts_code, rev_payload,
                  rev_status, 0.75, "tushare:report_rc")
            rating_payload, rating_status = _derive_analyst_rating(rc_records)
            _emit("L7.mood.analyst_rating", ts_code, rating_payload,
                  rating_status, 0.75, "tushare:report_rc")
            action_payload, action_status = _derive_analyst_action(rc_records)
            _emit("L9.media.analyst_action", ts_code, action_payload,
                  action_status, 0.7, "tushare:report_rc")
        except Exception as e:  # noqa: BLE001
            log.warning(
                "[tushare] BucketB report_rc-derived %s failed: %s",
                ts_code, e,
            )

        # B2.b: L6.priced.discussion
        try:
            disc_payload, disc_status = _derive_discussion(
                ts_code, dc_records, ths_records,
            )
            _emit("L6.priced.discussion", ts_code, disc_payload, disc_status,
                  0.6, "tushare:dc_hot+ths_hot")
        except Exception as e:  # noqa: BLE001
            log.warning(
                "[tushare] BucketB L6.priced.discussion %s failed: %s",
                ts_code, e,
            )

        # B2.c: L6.state.expansion_compression
        try:
            db_long = _get_daily_basic_history_long(pro, ts_code, now)
            exp_payload, exp_status = _derive_expansion_compression(db_long)
            _emit("L6.state.expansion_compression", ts_code, exp_payload,
                  exp_status, 0.7, "tushare:daily_basic.history_long")
        except Exception as e:  # noqa: BLE001
            log.warning(
                "[tushare] BucketB L6.state.expansion_compression %s failed: %s",
                ts_code, e,
            )

        # B2.e / B4: L6.state.peer_compare + L10.val.peer (shared compute)
        try:
            stock_rec = snapshot_by_code.get(ts_code)
            ind = code_to_industry.get(ts_code)
            ind_center = industry_center_by_id.get(ind) if ind else None
            pc_payload, vp_payload, pc_status = _derive_peer_compare(
                ts_code, stock_rec, ind_center,
            )
            _emit("L6.state.peer_compare", ts_code, pc_payload, pc_status,
                  0.7, "tushare:daily_basic.peer_compare")
            _emit("L10.val.peer", ts_code, vp_payload, pc_status,
                  0.7, "tushare:daily_basic.peer_compare")
        except Exception as e:  # noqa: BLE001
            log.warning(
                "[tushare] BucketB L6.peer_compare/L10.val.peer %s failed: %s",
                ts_code, e,
            )

    log.info(
        "[tushare] BucketB: %d rows across %d A-shares + %d industries; "
        "Known/Inactive per dp_id: %s",
        len(rows), len(a_codes), len(industries), counts,
    )
    return rows
