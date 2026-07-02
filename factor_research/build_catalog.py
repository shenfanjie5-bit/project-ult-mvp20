#!/usr/bin/env python3
"""Phase-1 catalog generator (isolated). Reads data/phase1_raw.json, emits
per-family markdown + a master INDEX.md + machine-readable factors.csv.
Read-only w.r.t. the main project."""
import json, csv, pathlib, re

ROOT = pathlib.Path(__file__).parent
RAW = json.load(open(ROOT / "data" / "phase1_raw.json", encoding="utf-8"))
CAT = ROOT / "01_factor_catalog"
CAT.mkdir(exist_ok=True)

FAM_SLUG = {
    "价值/估值（Value）": "01_value",
    "quality": "02_quality",
    "momentum_reversal": "03_momentum_reversal",
    "growth_expectation": "04_growth_expectation",
    "institutional_flow": "05_institutional_flow",
    "liquidity_micro": "06_liquidity_micro",
    "volatility_risk": "07_volatility_risk",
    "sentiment_attention": "08_sentiment_attention",
    "multifactor_models": "09_multifactor_models",
    "macro_regime_timing": "10_macro_regime_timing",
}

def slug(fam):
    return FAM_SLUG.get(fam, re.sub(r"[^a-z0-9]+", "_", fam.lower())[:30])

def li(xs):
    if not xs: return "—"
    if isinstance(xs, str): return xs
    return ", ".join(str(x) for x in xs)

rows = []
for fam in RAW["families"]:
    fname = fam.get("family", "?")
    facs = fam.get("factors", [])
    lines = [f"# 因子族：{fname}\n", f"> {fam.get('summary','')}\n", f"共 {len(facs)} 条。\n"]
    for i, x in enumerate(facs, 1):
        nm = x.get("name", "?")
        lines.append(f"\n## {i}. {nm}")
        if x.get("aka"): lines.append(f"**别名**：{x['aka']}  ")
        lines.append(f"**映射**：`{x.get('maps_to_score_target','?')}` · **可行性**：{x.get('feasibility_guess','?')} · **把握**：{x.get('confidence','?')} · **周期**：{x.get('horizon','?')} · **方向**：{x.get('direction','?')}")
        lines.append(f"\n- **定义/公式**：{x.get('definition','')}")
        lines.append(f"- **逻辑**：{x.get('rationale','')}")
        lines.append(f"- **数据输入**：{li(x.get('data_inputs'))}")
        lines.append(f"- **tushare 端点**：{li(x.get('tushare_endpoints'))}")
        lines.append(f"- **A股证据/陷阱**：{x.get('a_share_evidence','')}")
        lines.append(f"- **机构相关度**：{x.get('institutional_relevance','')}")
        if x.get("sources"): lines.append(f"- **出处**：{li(x.get('sources'))}")
        rows.append({
            "family": fname, "name": nm,
            "target": x.get("maps_to_score_target",""),
            "feasibility": (x.get("feasibility_guess","") or "").split("(")[0].strip().upper(),
            "confidence": (x.get("confidence","") or "").lower(),
            "horizon": x.get("horizon",""),
            "direction": x.get("direction",""),
            "tushare": li(x.get("tushare_endpoints")),
            "institutional_relevance": (x.get("institutional_relevance","") or "")[:60],
        })
    (CAT / f"{slug(fname)}.md").write_text("\n".join(lines), encoding="utf-8")

# master CSV
with open(ROOT / "data" / "factors.csv", "w", encoding="utf-8", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
    w.writeheader(); w.writerows(rows)

# INDEX.md
idx = ["# 因子目录总表（166 条）\n",
       "可行性：GREEN=现数据+字段直接可算 · YELLOW=数据有需新增派生/dp_id · RED=数据不足\n",
       "| # | 因子 | 族 | 映射 score_target | 可行 | 把握 | 周期 |",
       "|---|---|---|---|---|---|---|"]
for i, r in enumerate(rows, 1):
    idx.append(f"| {i} | {r['name']} | {r['family']} | `{r['target']}` | {r['feasibility']} | {r['confidence']} | {r['horizon'][:18]} |")
(CAT / "INDEX.md").write_text("\n".join(idx), encoding="utf-8")

# distributions
from collections import Counter
tgt = Counter(r["target"] for r in rows)
print("wrote", len(list(CAT.glob("*.md"))), "family files +", len(rows), "rows")
print("by target:", dict(tgt.most_common()))
