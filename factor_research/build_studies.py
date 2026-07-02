#!/usr/bin/env python3
"""Phase-3a study generator (isolated). Reads the workflow output envelope,
saves clean JSON, writes per-unit markdown + SUMMARY.md. Read-only on project."""
import json, sys, pathlib
from collections import Counter

ROOT = pathlib.Path(__file__).parent
OUT_ENV = sys.argv[1]
env = json.loads(open(OUT_ENV, encoding="utf-8").read())
res = env["result"] if isinstance(env, dict) and "result" in env else env
studies = res.get("studies", [])
json.dump(res, open(ROOT/"data"/"phase3a_raw.json","w",encoding="utf-8"), ensure_ascii=False, indent=1)

DEST = ROOT/"03_impact_studies"; DEST.mkdir(exist_ok=True)

def norm_verdict(v):
    return (v or "?").upper().split("/")[0].split("(")[0].strip()

FIELDS = [
    ("target_axis","目标轴"),("already_in_system","系统已有?"),("orthogonality","正交性"),
    ("double_counting_risk","双计风险"),("direction_correctness","方向"),
    ("a_share_efficacy","A股有效性/陷阱"),("horizon_fit","周期契合"),
    ("institution_fit","机构适配"),("integration_design","接入设计"),
    ("failure_modes","负面情形"),("verdict_rationale","裁决理由"),
]

vc=Counter(); cc=Counter(); pc=Counter(); rows=[]
studies_sorted = sorted(studies, key=lambda s: s.get("unit_id",""))
for s in studies_sorted:
    uid=s.get("unit_id","?"); ver=norm_verdict(s.get("verdict"))
    vc[ver]+=1; cc[(s.get("confidence","?") or "?").lower()]+=1
    pc[(s.get("priority_to_implement","?") or "?").lower()]+=1
    lines=[f"# {uid} — {s.get('factor_title','')}",
           f"\n**裁决：{s.get('verdict','?')}** · 把握 {s.get('confidence','?')} · 实施优先级 {s.get('priority_to_implement','?')}\n"]
    for k,label in FIELDS:
        lines.append(f"### {label}\n{s.get(k,'—')}\n")
    (DEST/f"{uid}.md").write_text("\n".join(lines), encoding="utf-8")
    rows.append((uid, s.get("factor_title","")[:34], s.get("target_axis","")[:22],
                 ver, (s.get("confidence","") or "")[:4], (s.get("priority_to_implement","") or "")[:4]))

# SUMMARY
sm=["# Phase 3a 裁决汇总（27 单元）\n",
    f"裁决分布：{dict(vc)}　把握：{dict(cc)}　优先级：{dict(pc)}\n",
    "| 单元 | 因子 | 目标轴 | 裁决 | 把握 | 优先级 |",
    "|---|---|---|---|---|---|"]
for r in rows:
    sm.append(f"| {r[0]} | {r[1]} | {r[2]} | **{r[3]}** | {r[4]} | {r[5]} |")
(DEST/"SUMMARY.md").write_text("\n".join(sm), encoding="utf-8")

print("studies:", len(studies))
print("VERDICT:", dict(vc)); print("CONFIDENCE:", dict(cc)); print("PRIORITY:", dict(pc))
print("\n".join(f"{r[0]:6} {r[3]:11} prio={r[5]:4} {r[1]}" for r in rows))
