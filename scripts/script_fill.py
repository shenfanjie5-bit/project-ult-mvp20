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
import re
import sqlite3
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent

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
            include_catalysts: bool = True) -> dict[str, dict]:
    """年报优先 + fina_mainbz 兜底,产出可写入 overlay 的字段字典。

    ``include_catalysts``: 关掉则跳过 dividend/forecast 抓取。当前 catalyst 产出的
    dp_id(L9.company.buyback_dividend / earnings_guidance)在 SLOT_DEFS 里【未实例化为
    overlay 节点】,write_to_overlay 会丢弃 → 批量补空时关掉以省去无谓的逐股抓取。
    待这些 slot 被加进图谱后再开启。"""
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

    # 纯结构化 catalysts(无需年报)——仅在目标 slot 存在时才值得抓取
    if include_catalysts:
        out.update(_catalysts(ts_code))
    return _native(out)


def _catalysts(ts_code: str) -> dict[str, dict]:
    """L9.company.buyback_dividend ← dividend;earnings_guidance ← forecast。
    走缓存 pro(命中 DockCase 不下载),最近一条记录。"""
    out: dict[str, dict] = {}
    try:
        from mvp20.sources import tushare_source as tsrc
        pro = tsrc._get_pro_api()
    except Exception:  # noqa: BLE001
        return out
    try:
        dv = pro.dividend(ts_code=ts_code,
                          fields="ts_code,end_date,ann_date,div_proc,cash_div,stk_div,pay_date")
        if dv is not None and len(dv):
            r = dv.sort_values("end_date", ascending=False).iloc[0]
            out["L9.company.buyback_dividend"] = {"data_status": "Known",
                "value": {"latest_end_date": str(r.get("end_date")), "div_proc": r.get("div_proc"),
                          "cash_div": r.get("cash_div"), "stk_div": r.get("stk_div"),
                          "source": "tushare:dividend"},
                "evidence_sources": [{"kind": "local_dp_id", "dp_id": "dividend",
                                      "source": "tushare:dividend"}]}
    except Exception:  # noqa: BLE001
        pass
    try:
        fc = pro.forecast(ts_code=ts_code)
        if fc is not None and len(fc):
            r = fc.sort_values("end_date", ascending=False).iloc[0]
            out["L9.company.earnings_guidance"] = {"data_status": "Known",
                "value": {"end_date": str(r.get("end_date")), "type": r.get("type"),
                          "p_change_min": r.get("p_change_min"), "p_change_max": r.get("p_change_max"),
                          "summary": str(r.get("summary"))[:120] if r.get("summary") else None,
                          "source": "tushare:forecast"},
                "evidence_sources": [{"kind": "local_dp_id", "dp_id": "forecast",
                                      "source": "tushare:forecast"}]}
    except Exception:  # noqa: BLE001
        pass
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
