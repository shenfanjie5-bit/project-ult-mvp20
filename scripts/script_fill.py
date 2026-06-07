"""Deterministic script-fill for the structured-extractable qualitative nodes
(替代 codex 对「能从结构化数据/年报抽出」的字段的填充).

策略:年报优先 + 结构化兜底。
  * 年报(realtime_current 的 L9.disclosure.annual_report.sections):正则解析
    ``revenue_structure``(按业务/按产品 + 按地区)、``customer_segment``(前五客户)。
    这是 codex 当初读的同一段文本 → 脚本确定性复现,且对最新财年【完整】(优于
    tushare fina_mainbz——后者最新年常缺境内行)。
  * 兜底:年报缺/解析失败 → tushare fina_mainbz(取最新【完整】期:有境内+境外/
    多产品行的那期),P=产品、D=地区。
  * 纯结构化(无需年报):dividend / forecast / stk_managers 等(后续扩展)。

每个字段产出 {data_status:'Known', value:{...}, evidence_sources:[{kind:'local_dp_id',
...}]} ——与 codex 的 local_dp_id 证据同构,可直接写进 overlay 节点。
"""

from __future__ import annotations

import json
import math
import re
import sqlite3
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent

# ── Track-B structured catalyst/risk constants ──────────────────────────────
# 业绩预告 type → expectation-gap direction. tushare ``forecast.type`` vocab.
# Positive = 上调预期(抬 expectation_gap);negative = 下调预期(压 expectation_gap)。
_FORECAST_POS_TYPES = ("预增", "略增", "扭亏", "续盈", "首盈", "减亏")
_FORECAST_NEG_TYPES = ("预减", "略减", "首亏", "续亏", "增亏", "预亏")
# A real (nonzero) guidance call must not collapse to ~0 when p_change is tiny/None.
_GUIDANCE_FLOOR = 0.15
# stk_managers 离任职位权重:核心高管离任比普通董监高更受关注。
_KEY_TITLES = ("董事长", "总经理", "总裁", "财务总监", "CFO", "CEO", "董事会秘书", "董秘")
# 一年窗口(自然日)用于 insider_sell / management_change 的近一年聚合。
_ONE_YEAR_DAYS = 365

# 国内/境外 地区标签(覆盖各家年报/接口的写法变体)
_DOMESTIC = ("中国大陆", "中国境内", "中国内地", "境内", "内销", "国内", "内地", "大陆", "中国")
_OVERSEAS = ("境外", "海外", "国外", "出口", "外销", "港澳台", "亚洲", "欧", "美", "非洲",
             "大洋", "国际")
_SKIP_ROWS = ("合计", "小计", "总计", "其他业务", "营业收入", "收入比重")
# 一行数据 = 名称 + 收入数 + 占比% (occasionally followed by cost/margin cols)
_ROW = re.compile(r"^(.{2,30}?)\s+([\d,]+\.?\d*)\s+([\d.]+)%")


def _native(x: Any) -> Any:
    """Coerce numpy/pandas scalars → native Python (yaml/json serialisable);
    NaN → None. Recurses into dict/list."""
    if isinstance(x, dict):
        return {k: _native(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_native(v) for v in x]
    if hasattr(x, "item") and not isinstance(x, (str, bytes)):
        try:
            x = x.item()
        except (ValueError, AttributeError):
            pass
    if isinstance(x, float) and x != x:  # NaN
        return None
    return x


def _is_domestic(name: str) -> bool:
    s = str(name)
    if any(x in s for x in _OVERSEAS):
        return False
    return any(x in s for x in _DOMESTIC)


def _to_float(x: Any) -> float | None:
    """Best-effort float; numpy/pandas/str-safe; NaN/None → None."""
    if x is None:
        return None
    if isinstance(x, float) and x != x:  # NaN
        return None
    try:
        f = float(x)
    except (TypeError, ValueError):
        return None
    return None if f != f else f


def _clip01(x: float) -> float:
    return max(0.0, min(1.0, x))


# ── annual-report parsing ───────────────────────────────────────────────────

def _annual_sections(ts_code: str, db_path: Path) -> dict[str, str]:
    try:
        conn = sqlite3.connect(db_path)
        row = conn.execute(
            "SELECT value_json FROM realtime_current WHERE ts_code=? AND "
            "dp_id='L9.disclosure.annual_report'", (ts_code,)).fetchone()
        conn.close()
    except sqlite3.Error:
        return {}
    if not row:
        return {}
    try:
        v = json.loads(row[0])
        return v.get("sections") or {}
    except (ValueError, TypeError):
        return {}


# dimension headers — handle both "按X划分"(000063 style) and "分X"(分产品/分地区) style.
def _dim_of(line: str) -> str | None:
    if any(k in line for k in ("按地区", "分地区", "按区域", "分区域", "境内外", "境内境外")):
        return "region"
    if any(k in line for k in ("按业务", "按产品", "分产品", "分业务", "按产品类", "分产品类")):
        return "product"
    if any(k in line for k in ("按行业", "分行业")):
        return "industry"
    if any(k in line for k in ("按销售模式", "分销售模式", "按销售渠道", "分销售渠道")):
        return "sales_mode"
    return None


def _parse_revenue_structure(text: str) -> tuple[list[dict], dict | None]:
    """Return (products, region) parsed from the 营业收入构成 / 主营业务构成 section.
    Groups data rows under the current dimension header (product / region / industry
    / sales_mode), accepting both 表头 styles. Prefers the 分产品 dimension for
    products; falls back to 分行业 only when no product dimension exists."""
    if not text:
        return [], None
    lines = [ln.strip() for ln in text.replace("\r", "\n").split("\n")]

    grouped: dict[str, list[dict]] = {"product": [], "region": [], "industry": [], "sales_mode": []}
    cum: dict[str, float] = {k: 0.0 for k in grouped}
    closed: set[str] = set()  # a dim is closed once its rows sum to ~100% (main table done)
    cur: str | None = None
    for ln in lines:
        dim = _dim_of(ln)
        if dim:
            cur = dim
        if cur is None or cur in closed or any(s in ln for s in _SKIP_ROWS):
            continue
        m = _ROW.match(ln)
        if not m:
            continue
        name = m.group(1).strip("、 ·")
        for w in ("分产品", "分地区", "分行业", "按业务划分", "按产品划分", "按地区划分", "按行业划分"):
            if name.startswith(w):
                name = name[len(w):].strip("、 ·")
        # strip a leaked revenue figure that the lazy capture pulled into the name
        # ("数据通讯 14,656,300,288" → "数据通讯"; keeps "3C电子产品"/"5G" intact).
        name = re.sub(r"\s+[\d][\d,]{2,}.*$", "", name).strip("、 ·")
        cjk = len(re.findall(r"[一-鿿]", name))
        if re.search(r"\d{4,}", name) or cjk < 2 or _dim_of(name):
            continue
        pct = float(m.group(3))
        if not (0 < pct <= 100):
            continue
        grouped[cur].append({"name": name, "revenue_pct": round(pct, 2)})
        cum[cur] += pct
        if cum[cur] >= 99:        # main breakdown complete → ignore trailing sub-tables
            closed.add(cur)

    def sane(rows: list[dict]) -> bool:
        return bool(rows) and 90 <= sum(r["revenue_pct"] for r in rows) <= 110

    products = grouped["product"] if sane(grouped["product"]) else (
        grouped["industry"] if sane(grouped["industry"]) else [])
    region_items = grouped["region"] if sane(grouped["region"]) else []
    region = None
    if region_items:
        dom = sum(r["revenue_pct"] for r in region_items if _is_domestic(r["name"]))
        region = {"domestic_pct": round(dom, 2), "items": region_items}
    return products, region


def _parse_customer_concentration(text: str) -> dict | None:
    if not text:
        return None
    m = re.search(r"前五名客户.{0,20}?(?:合计|销售).{0,20}?占.{0,12}?([\d.]+)%", text)
    if not m:
        m = re.search(r"前五(?:大|名).{0,40}?([\d.]+)%", text)
    if not m:
        return None
    top5 = float(m.group(1))
    sup = re.search(r"前五名供应商.{0,30}?占.{0,12}?([\d.]+)%", text)
    return {"top5_customer_pct": round(top5, 2),
            "top5_supplier_pct": round(float(sup.group(1)), 2) if sup else None}


# ── fina_mainbz fallback ────────────────────────────────────────────────────

def _fina_mainbz_latest_complete(ts_code: str):
    """Return the latest fina_mainbz period whose region (D) block has BOTH a
    domestic and an overseas row (so the latest-but-incomplete year is skipped)."""
    from mvp20.sources import dockcase_cache as dc
    import pandas as pd
    df = dc.read("fina_mainbz", {"ts_code": ts_code})
    if df is None or len(df) == 0:
        return None, [], None
    df = df.copy()
    df["bz_sales"] = pd.to_numeric(df["bz_sales"], errors="coerce")
    df["end_date"] = df["end_date"].astype(str)
    for per in sorted(df["end_date"].unique(), reverse=True):
        d = df[(df["bz_code"] == "D") & (df["end_date"] == per)]
        d = d[~d["bz_item"].astype(str).str.contains("其他业务")]
        has_dom = any(_is_domestic(x) for x in d["bz_item"].astype(str))
        has_ovs = any(not _is_domestic(x) for x in d["bz_item"].astype(str))
        if len(d) and has_dom and has_ovs and d["bz_sales"].sum() > 0:
            P = df[(df["bz_code"] == "P") & (df["end_date"] == per)]
            P = P[~P["bz_item"].astype(str).str.contains("其他业务")]
            ptot = P["bz_sales"].sum()
            products = ([{"name": str(r["bz_item"]), "revenue_pct": round(100 * r["bz_sales"] / ptot, 2)}
                         for _, r in P.iterrows()] if ptot > 0 else [])
            dtot = d["bz_sales"].sum()
            dom = sum(r["bz_sales"] for _, r in d.iterrows() if _is_domestic(r["bz_item"]))
            region = {"domestic_pct": round(100 * dom / dtot, 2)}
            return per, products, region
    return None, [], None


# ── unified extract ─────────────────────────────────────────────────────────

def extract(ts_code: str, db_path: Path = ROOT / "runtime" / "hot.sqlite",
            include_catalysts: bool = True,
            include_management_change: bool = False) -> dict[str, dict]:
    """年报优先 + fina_mainbz 兜底,产出可写入 overlay 的字段字典。

    ``include_catalysts``: 关掉则跳过 Track-B 结构化 catalyst/risk 抓取
    (buyback_dividend / earnings_guidance / insider_sell / management_change)。
    这 4 个 dp_id 现已实例化为 overlay 节点(L9.company.* / L8.gov.*),
    write_to_overlay 会写入。批量补空若想省去逐股抓取可关掉。

    ``include_management_change``: L8.gov.management_change ← tushare
    ``stk_managers``,该接口【不在 DockCase 缓存】→ 走【联网 live 读】。默认 False
    (关闭),避免批量补空时为每只股触发网络。其余三个字段全走 DockCase 缓存(零下载)。
    """
    secs = _annual_sections(ts_code, db_path)
    ar_year = None
    try:
        conn = sqlite3.connect(db_path)
        r = conn.execute("SELECT value_json FROM realtime_current WHERE ts_code=? AND "
                         "dp_id='L9.disclosure.annual_report'", (ts_code,)).fetchone()
        conn.close()
        ar_year = json.loads(r[0]).get("ar_year") if r else None
    except Exception:  # noqa: BLE001
        pass

    ar_products, ar_region = _parse_revenue_structure(secs.get("revenue_structure", ""))
    ar_cust = _parse_customer_concentration(secs.get("customer_segment", ""))

    out: dict[str, dict] = {}

    def ar_ev(section: str) -> list[dict]:
        return [{"kind": "local_dp_id", "dp_id": "L9.disclosure.annual_report",
                 "source": f"annual_report:{ar_year}:{section}"}]

    def fmb_ev(per: str) -> list[dict]:
        return [{"kind": "local_dp_id", "dp_id": "fina_mainbz",
                 "source": f"tushare:fina_mainbz:{per}"}]

    # L3.product.portfolio — 年报按业务/产品 → fina_mainbz P
    if ar_products:
        out["L3.product.portfolio"] = {"data_status": "Known",
            "value": {"products": ar_products, "source": f"年报{ar_year}按业务划分"},
            "evidence_sources": ar_ev("revenue_structure")}
    # L3.region.domestic_overseas — 年报按地区 → fina_mainbz D(完整期)
    if ar_region:
        out["L3.region.domestic_overseas"] = {"data_status": "Known",
            "value": {"domestic_pct": ar_region["domestic_pct"],
                      "overseas_pct": round(100 - ar_region["domestic_pct"], 2),
                      "regions": ar_region["items"], "source": f"年报{ar_year}按地区划分"},
            "evidence_sources": ar_ev("revenue_structure")}
    # L3.customer.concentration — 年报前五客户
    if ar_cust and ar_cust.get("top5_customer_pct") is not None:
        out["L3.customer.concentration"] = {"data_status": "Known",
            "value": {"top5_pct": ar_cust["top5_customer_pct"],
                      "top5_supplier_pct": ar_cust.get("top5_supplier_pct"),
                      "source": f"年报{ar_year}前五名客户"},
            "evidence_sources": ar_ev("customer_segment")}

    # 兜底:年报缺产品/地区 → fina_mainbz 最新完整期
    if "L3.product.portfolio" not in out or "L3.region.domestic_overseas" not in out:
        per, fp, fr = _fina_mainbz_latest_complete(ts_code)
        if per:
            if "L3.product.portfolio" not in out and fp:
                out["L3.product.portfolio"] = {"data_status": "Known",
                    "value": {"products": fp, "source": f"fina_mainbz {per} 按产品"},
                    "evidence_sources": fmb_ev(per)}
            if "L3.region.domestic_overseas" not in out and fr:
                out["L3.region.domestic_overseas"] = {"data_status": "Known",
                    "value": {"domestic_pct": fr["domestic_pct"],
                              "overseas_pct": round(100 - fr["domestic_pct"], 2),
                              "source": f"fina_mainbz {per} 按地区"},
                    "evidence_sources": fmb_ev(per)}

    # 纯结构化 catalysts/risks(无需年报)——走 DockCase 缓存(零下载)。
    # management_change 例外:走联网 stk_managers,默认关。
    if include_catalysts:
        out.update(_catalysts(ts_code,
                              include_management_change=include_management_change))
    return _native(out)


# ── Track-B structured catalyst/risk parsers (pure, hermetically testable) ──
#
# Each parser takes a list of endpoint records (DataFrame.to_dict("records"))
# and returns an overlay-node payload {data_status, value, evidence_sources,
# direction?} or None. The crucial field is ``value.score`` — a [0,1] MAGNITUDE
# that the scoring aggregator reads via ``_to_scalar`` (it looks for score/
# intensity/strength). Sign/direction is carried by the node's ``direction``
# (positive → 抬 expectation_gap;negative → 进 risk_discount / 压 expectation_gap),
# so a value with no ``score`` key would contribute ZERO regardless of direction.
#
# expectation_gap is a SIGNED damped sum (Σ score×conf / max(1,Σconf)); risk_
# discount is the ABS-value damped sum (sign ignored, magnitude subtracted).


def _ev(endpoint: str, period: str | None = None) -> list[dict]:
    src = f"tushare:{endpoint}" + (f":{period}" if period else "")
    return [{"kind": "local_dp_id", "dp_id": endpoint, "source": src}]


def parse_buyback_dividend(records: list[dict]) -> dict | None:
    """L9.company.buyback_dividend ← tushare ``dividend``.

    取最新【已实施 div_proc=='实施'】记录(没有已实施的则回落到最新一条)。
    有实质现金分红/送转→正向 expectation_gap。score 由现金分红(主)+ 送转股(辅)
    的存在与力度编码,封顶 1.0。direction 恒 positive(分红是利好)。"""
    if not records:
        return None
    impl = [r for r in records if str(r.get("div_proc") or "").strip() == "实施"]
    pool = impl or records

    def _key(r: dict) -> str:
        return str(r.get("end_date") or r.get("ann_date") or "")

    r = sorted(pool, key=_key, reverse=True)[0]
    cash = _to_float(r.get("cash_div")) or 0.0          # 每股现金分红(元/税前)
    stk = _to_float(r.get("stk_div")) or 0.0            # 每股送转股
    if cash <= 0 and stk <= 0:
        return None
    # 分红是温和利好,不应主导 expectation_gap。现金分红 knee 在 1.0 元/股
    # (0.3 元/股 → ~0.29;1.0 元/股 → ~0.76),送转每 0.5 股加 ~0.23(辅)。
    score = _clip01(0.8 * math.tanh(cash / 1.0) + 0.2 * math.tanh(stk / 0.5))
    if score <= 0:
        return None
    return {
        "data_status": "Known", "direction": "positive",
        "value": {
            "score": round(score, 4),
            "div_proc": str(r.get("div_proc") or "").strip() or None,
            "cash_div": _to_float(r.get("cash_div")),
            "stk_div": _to_float(r.get("stk_div")),
            "latest_end_date": str(r.get("end_date") or "") or None,
            "ann_date": str(r.get("ann_date") or "") or None,
            "source": "tushare:dividend",
        },
        "evidence_sources": _ev("dividend", str(r.get("end_date") or "") or None),
    }


def parse_earnings_guidance(records: list[dict]) -> dict | None:
    """L9.company.earnings_guidance ← tushare ``forecast``.

    取最新一期业绩预告。type(预增/扭亏/略增 → 正;预减/首亏/续亏 → 负)定方向;
    p_change_min/max 的均值经 tanh 编码 magnitude(+100% → ~0.76)。方向写进节点
    ``direction``(预减时为 negative → 压低 expectation_gap)。"""
    if not records:
        return None

    def _key(r: dict) -> str:
        return str(r.get("end_date") or r.get("ann_date") or "")

    r = sorted(records, key=_key, reverse=True)[0]
    typ = str(r.get("type") or "").strip()
    if any(t in typ for t in _FORECAST_POS_TYPES):
        direction = "positive"
    elif any(t in typ for t in _FORECAST_NEG_TYPES):
        direction = "negative"
    else:
        # 不确定/续盈无幅度/未知类型 → 不构成清晰方向,跳过(不污染 expectation_gap)。
        return None
    pmin = _to_float(r.get("p_change_min"))
    pmax = _to_float(r.get("p_change_max"))
    vals = [v for v in (pmin, pmax) if v is not None]
    mag = math.tanh(abs(sum(vals) / len(vals)) / 100.0) if vals else 0.0
    score = _clip01(max(mag, _GUIDANCE_FLOOR))          # 真实预告不塌到 ~0
    return {
        "data_status": "Known", "direction": direction,
        "value": {
            "score": round(score, 4),
            "type": typ or None,
            "p_change_min": pmin, "p_change_max": pmax,
            "end_date": str(r.get("end_date") or "") or None,
            "summary": (str(r.get("summary"))[:120] if r.get("summary") else None),
            "source": "tushare:forecast",
        },
        "evidence_sources": _ev("forecast", str(r.get("end_date") or "") or None),
    }


def parse_insider_sell(records: list[dict], *, asof: str | None = None) -> dict | None:
    """L8.gov.insider_sell ← tushare ``stk_holdertrade``.

    近一年股东/高管【减持 in_de=='DE'】的净减持比例 + 笔数 → 风险强度。
    score = tanh(净减持比例% / 3.0)(3% 净减持 ≈ 0.76),笔数多再小幅加成。
    direction negative(进 risk_discount;magnitude 被 abs 取用)。无减持 → None。"""
    if not records:
        return None
    cutoff = _cutoff(asof, _ONE_YEAR_DAYS)
    rows = [r for r in records if str(r.get("ann_date") or "") >= cutoff]
    decreases = [r for r in rows if str(r.get("in_de") or "").upper() == "DE"]
    if not decreases:
        return None
    net_de_pct = 0.0
    for r in decreases:
        ratio = _to_float(r.get("change_ratio"))
        if ratio is not None:
            net_de_pct += abs(ratio)                     # change_ratio 为幅度,DE 即减持
    if net_de_pct <= 0:
        return None
    n = len(decreases)
    score = _clip01(math.tanh(net_de_pct / 3.0) + 0.05 * min(n, 4))
    return {
        "data_status": "Known", "direction": "negative",
        "value": {
            "score": round(score, 4),
            "net_decrease_pct": round(net_de_pct, 3),
            "decrease_count": n,
            "latest_ann_date": str(decreases[0].get("ann_date") or "") or None,
            "window_days": _ONE_YEAR_DAYS,
            "source": "tushare:stk_holdertrade",
        },
        "evidence_sources": _ev("stk_holdertrade"),
    }


def parse_management_change(records: list[dict], *, asof: str | None = None) -> dict | None:
    """L8.gov.management_change ← tushare ``stk_managers`` (LIVE 联网,非缓存)。

    近一年高管【离任 end_date 非空】数量 → 风险强度;核心高管(董事长/总经理/CFO/
    董秘…)离任额外加权。score = tanh(加权离任数 / 3.0)。direction negative。
    无离任 → None。"""
    if not records:
        return None
    cutoff = _cutoff(asof, _ONE_YEAR_DAYS)
    departures = []
    for r in records:
        end_date = str(r.get("end_date") or "").strip()
        ann = str(r.get("ann_date") or "")
        if end_date and end_date.lower() not in ("nan", "none") and ann >= cutoff:
            departures.append(r)
    if not departures:
        return None
    weighted = 0.0
    for r in departures:
        title = str(r.get("title") or "")
        weighted += 1.5 if any(t in title for t in _KEY_TITLES) else 1.0
    score = _clip01(math.tanh(weighted / 3.0))
    return {
        "data_status": "Known", "direction": "negative",
        "value": {
            "score": round(score, 4),
            "departure_count": len(departures),
            "weighted_departures": round(weighted, 2),
            "people": [str(r.get("name") or "") for r in departures[:5] if r.get("name")],
            "window_days": _ONE_YEAR_DAYS,
            "source": "tushare:stk_managers",
        },
        "evidence_sources": _ev("stk_managers"),
    }


def _cutoff(asof: str | None, days: int) -> str:
    """YYYYMMDD cutoff = asof - days. asof None → today (UTC date)."""
    from datetime import datetime, timedelta, timezone
    if asof:
        try:
            base = datetime.strptime(str(asof)[:8], "%Y%m%d")
        except ValueError:
            base = datetime.now(tz=timezone.utc)
    else:
        base = datetime.now(tz=timezone.utc)
    return (base - timedelta(days=days)).strftime("%Y%m%d")


def _records(df) -> list[dict]:
    """DataFrame → list[dict] records; None/empty → []."""
    if df is None or len(df) == 0:
        return []
    try:
        return df.to_dict(orient="records")
    except AttributeError:
        return list(df)


def _catalysts(ts_code: str, *, include_management_change: bool = False) -> dict[str, dict]:
    """Fetch + parse the 4 Track-B structured fields. dividend / forecast /
    stk_holdertrade hit the DockCase cache (零下载, DOCKCASE_WRITEBACK 由调用方置 0);
    stk_managers (management_change) 走【联网 live 读】且默认关闭。"""
    out: dict[str, dict] = {}
    try:
        from mvp20.sources import tushare_source as tsrc
        pro = tsrc._get_pro_api()
    except Exception:  # noqa: BLE001
        return out

    def _safe_fetch(fn, **kw):
        try:
            return _records(fn(**kw))
        except Exception:  # noqa: BLE001
            return []

    parsed = {
        "L9.company.buyback_dividend": parse_buyback_dividend(
            _safe_fetch(pro.dividend, ts_code=ts_code,
                        fields="ts_code,end_date,ann_date,div_proc,cash_div,stk_div,pay_date")),
        "L9.company.earnings_guidance": parse_earnings_guidance(
            _safe_fetch(pro.forecast, ts_code=ts_code)),
        "L8.gov.insider_sell": parse_insider_sell(
            _safe_fetch(pro.stk_holdertrade, ts_code=ts_code)),
    }
    if include_management_change:
        # 联网读(stk_managers 不在 DockCase 缓存)。
        parsed["L8.gov.management_change"] = parse_management_change(
            _safe_fetch(pro.stk_managers, ts_code=ts_code))
    for dp, node in parsed.items():
        if node is not None:
            out[dp] = node
    return out


def write_to_overlay(ts_code: str, extracted: dict[str, dict],
                     overlays_dir: Path = ROOT / "config" / "stock_overlays") -> int:
    """Fill ONLY currently-empty nodes (data_status != Known) with the extracted
    values — never overwrite an existing codex/LLM fill. Returns nodes filled."""
    import glob as _glob
    import yaml
    hits = _glob.glob(str(overlays_dir / "*" / f"{ts_code}.yaml"))
    if not hits:
        return 0
    path = Path(hits[0])
    overlay = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    filled = 0
    for node in overlay.get("nodes") or []:
        dp = node.get("dp_id")
        if dp in extracted and node.get("data_status") != "Known":
            ex = extracted[dp]
            node["data_status"] = "Known"
            node["value"] = ex["value"]
            node["evidence_sources"] = ex["evidence_sources"]
            # Event-driven slots default Inactive/active_weight=0 + missing_policy
            # 'inactive_zero_weight'. Once a real event is observed, activate the
            # node so its status/coverage round-trip correctly. (active_weight is
            # scoring-inert for these parent_node=None standalone leaves — their
            # leaf score is stored weight-independent — but the frontend / coverage
            # accounting read it, so keep it consistent.)
            if node.get("missing_policy") == "inactive_zero_weight":
                node["missing_policy"] = "known"
                if not node.get("active_weight"):
                    node["active_weight"] = node.get("base_weight") or 1.0
            # ``direction`` is LOAD-BEARING for earnings_guidance: a 预减/亏损 forecast
            # must carry direction='negative' so it LOWERS the signed expectation_gap
            # (the slot default is 'positive'). buyback/insider/mgmt directions match
            # their slot default but we set it uniformly for correctness.
            if ex.get("direction"):
                node["direction"] = ex["direction"]
            filled += 1
    if filled:
        from mvp20.overlays import _write_yaml_if_changed
        _write_yaml_if_changed(path, overlay)
    return filled


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--ts-code", required=True)
    args = ap.parse_args()
    print(json.dumps(extract(args.ts_code), ensure_ascii=False, indent=2))
