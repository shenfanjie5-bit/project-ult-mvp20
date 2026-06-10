"""Metrics aggregation + report generation for the PIT backtest.

Reads scores + forward-return labels from the results store, computes rank-IC /
quantile spreads / signal-bucket stats per (base_date, horizon) window, then
aggregates across same-horizon windows (overlap-aware: mean±std of per-window
ICs, NOT a stacked frame). Writes a bilingual markdown report + a tidy CSV under
docs/audit/, and embeds the independent leakage-audit summary.
"""

from __future__ import annotations

import csv
import math
from pathlib import Path
from typing import Any

from pit_backtest import calendar as cal
from pit_backtest import leakage_audit, metrics, store

_AUDIT_DIR = Path("docs/audit")


def _fmt(v, nd=4):
    if v is None or (isinstance(v, float) and not math.isfinite(v)):
        return "—"
    if isinstance(v, float):
        return f"{v:.{nd}f}"
    return str(v)


def _windows(base: dict[int, str]) -> list[dict]:
    return cal.forward_horizon_pairs(base)


def _cross_section(scores_idx, returns_idx, base_date, end_date):
    """Return parallel lists (base_score, signal, fwd_ret) over stocks with both
    a valid score and an OK realized return."""

    bs, sig, fr = [], [], []
    for (ts, bd), s in scores_idx.items():
        if bd != base_date:
            continue
        r = returns_idx.get((ts, base_date, end_date))
        if not r or r.get("fwd_ret") is None or r.get("status") != "OK":
            continue
        if s.get("base_score") is None:
            continue
        bs.append(s["base_score"]); sig.append(s.get("trading_signal")); fr.append(r["fwd_ret"])
    return bs, sig, fr


def compute_window_metrics(scores_idx, returns_idx, pair) -> dict:
    bs, sig, fr = _cross_section(scores_idx, returns_idx, pair["base_date"], pair["end_date"])
    ic = metrics.rank_ic(bs, fr)
    q = metrics.quantile_groups(bs, fr, k=5)
    sb = metrics.signal_buckets(sig, fr)
    return {
        "base_date": pair["base_date"], "end_date": pair["end_date"],
        "horizon_d": pair["horizon_d"], "n": ic["n"], "ic": ic, "quantile": q,
        "signal": sb, "_xs": {"bs": bs, "sig": sig, "fr": fr},
    }


def build_report(db: Path = store.DEFAULT_DB) -> dict:
    scores = store.read_scores(db)
    returns = store.read_returns(db)
    base = {int(k): v for k, v in (store.get_manifest("base_dates", db) or {}).items()}
    today = store.get_manifest("today", db) or base.get(0, "unknown")
    git_sha = store.get_manifest("git_sha", db)
    uni_n = store.get_manifest("universe_n", db)
    if not base:
        raise RuntimeError("no base_dates in manifest — run the backtest first")

    scores_idx = {(r["ts_code"], r["base_date"]): r for r in scores}
    returns_idx = {(r["ts_code"], r["base_date"], r["end_date"]): r for r in returns}

    pairs = _windows(base)
    win = [compute_window_metrics(scores_idx, returns_idx, p) for p in pairs]
    by_h: dict[int, list[dict]] = {}
    for w in win:
        by_h.setdefault(w["horizon_d"], []).append(w)

    # ---- CSV (tidy long form) ------------------------------------------------
    _AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    csv_path = _AUDIT_DIR / f"backtest_results_{today}.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        wr = csv.writer(f)
        wr.writerow(["base_date", "end_date", "horizon_d", "metric_type", "key",
                     "n", "value", "se", "ci_lo", "ci_hi", "p_value"])
        for w in win:
            bd, ed, h = w["base_date"], w["end_date"], w["horizon_d"]
            ic = w["ic"]; lo, hi = metrics.fisher_ci(ic["ic"], ic["n"])
            wr.writerow([bd, ed, h, "rank_ic", "base_score", ic["n"],
                         _fmt(ic["ic"]), "", _fmt(lo), _fmt(hi), _fmt(ic["p"])])
            q = w["quantile"]
            wr.writerow([bd, ed, h, "quantile", "top_minus_bottom", q["n"],
                         _fmt(q["top_minus_bottom"]), _fmt(q["se"]),
                         _fmt(q["ci"][0]), _fmt(q["ci"][1]), ""])
            sb = w["signal"]
            for s, st in sb["buckets"].items():
                wr.writerow([bd, ed, h, "signal_bucket", s, st["n"],
                             _fmt(st["mean_ret"]), _fmt(st["se"]), "", "",
                             _fmt(st["hit_rate"])])
            wr.writerow([bd, ed, h, "long_short", "BUY_minus_AVOID", "",
                         _fmt(sb["long_short_BUY_minus_AVOID"]), "", "", "",
                         _fmt(sb["perm_p"])])

    # ---- Markdown report -----------------------------------------------------
    md = _render_md(base, today, git_sha, uni_n, by_h, win, db)
    md_path = _AUDIT_DIR / f"a_share_pit_backtest_{today}.md"
    md_path.write_text(md, encoding="utf-8")
    return {"markdown": str(md_path), "csv": str(csv_path),
            "n_windows": len(win), "horizons": sorted(by_h)}


def _horizon_summary(ws: list[dict]) -> dict:
    ics = [w["ic"]["ic"] for w in ws]
    agg = metrics.aggregate_ic_across_windows(ics)
    # pooled signal buckets across windows (stock-window observations)
    sig_all, fr_all = [], []
    for w in ws:
        sig_all += w["_xs"]["sig"]; fr_all += w["_xs"]["fr"]
    pooled = metrics.signal_buckets(sig_all, fr_all)
    return {"agg_ic": agg, "pooled_signal": pooled, "n_obs": len(fr_all)}


def _render_md(base, today, git_sha, uni_n, by_h, win, db) -> str:
    audit = leakage_audit.run_full_audit(db)
    L: list[str] = []
    a = L.append
    a(f"# A 股评分系统 · 无超前 (Point-in-Time) 回测报告\n")
    a(f"**基准日 (today):** {today}　**池子:** {uni_n} 只 A 股 (survivorship-biased)　"
      f"**git:** `{git_sha}`\n")
    a(f"**基准日序列:** T0={base.get(0)} · T-30={base.get(30)} · T-60={base.get(60)} · T-90={base.get(90)}\n")
    a(f"**复权:** hfq · **打分口径:** 排除 LLM 定性层 (L0-L3) + 冻结行业景气 L0 · "
      f"**信号阈值:** BUY≥0.30 / HOLD≥−0.10 / WATCH≥−0.45 (固定)\n")

    # ---- 结论 ----
    a("\n## 结论 (One-line verdict)\n")
    for h in sorted(by_h):
        s = _horizon_summary(by_h[h])
        agg = s["agg_ic"]
        ls = s["pooled_signal"]["long_short_BUY_minus_AVOID"]
        mono = s["pooled_signal"]["monotone"]
        a(f"- **+{h}d:** mean rank-IC = {_fmt(agg['mean_ic'])} "
          f"(±{_fmt(agg['std_ic'])}, {agg['n_windows']} 窗口) · "
          f"signal 单调={mono} · BUY−AVOID(pooled)={_fmt(ls)} · n_obs={s['n_obs']}")
    a("\n> ⚠️ 小样本 (n≈%s/截面, 每 horizon 1–3 个跨窗口且非独立)，IC 标准误大；"
      "**这是泄漏/合理性审计，不是 alpha 证明**。survivorship 使 IC 上偏。\n" % uni_n)

    # ---- 泄漏审计 ----
    a("\n## 泄漏审计 (independent re-verification)\n")
    a(f"- HARD violations: **{audit['hard_total']}**　WARN: {audit['warn_total']}　"
      f"→ **{'PASS' if audit['ok'] else 'FAIL'}**")
    for asof, av in audit["per_asof"].items():
        over = {dp: d for dp, d in av["dp_max_date"].items() if d > asof}
        a(f"- [{asof}] {av['n_rows']} rows; 所有特征 observation-date ≤ asof "
          f"({'无越界' if not over else '越界: ' + str(over)})")
    a(f"- 前向收益: {audit['returns']['n']} 行, end_date≤T0 violations={len(audit['returns']['hard'])}")

    # ---- per-horizon tables ----
    a("\n## 各 horizon 明细\n")
    for h in sorted(by_h):
        ws = by_h[h]
        a(f"\n### +{h}d horizon\n")
        a("| base→end | n | rank-IC | p | IC 95%CI | 五分位 顶−底 | BUY−AVOID | perm-p |")
        a("|---|---|---|---|---|---|---|---|")
        for w in ws:
            ic = w["ic"]; lo, hi = metrics.fisher_ci(ic["ic"], ic["n"])
            q = w["quantile"]; sb = w["signal"]
            a(f"| {w['base_date']}→{w['end_date']} | {ic['n']} | {_fmt(ic['ic'])} | "
              f"{_fmt(ic['p'])} | [{_fmt(lo,2)}, {_fmt(hi,2)}] | {_fmt(q['top_minus_bottom'])} | "
              f"{_fmt(sb['long_short_BUY_minus_AVOID'])} | {_fmt(sb['perm_p'])} |")
        s = _horizon_summary(ws)
        a(f"\n**pooled signal buckets (+{h}d, n_obs={s['n_obs']}):**\n")
        a("| signal | n | mean fwd-ret | hit-rate |")
        a("|---|---|---|---|")
        for sgn, st in s["pooled_signal"]["buckets"].items():
            a(f"| {sgn} | {st['n']} | {_fmt(st['mean_ret'])} | {_fmt(st['hit_rate'])} |")

    a(METHODOLOGY)
    return "\n".join(L) + "\n"


METHODOLOGY = """
## 方法论与残留风险 (Methodology & residual risk)

**口径.** 基准日 T-30/-60/-90 为交易日 (tushare `trade_cal`)。前向收益 = hfq 复权收盘
`close(end)/close(base) − 1`，6 组 (base→end) 终点全部 ≤ T0（已实现）。打分复用生产引擎
(`aggregate_company_graph` + `score_company`)，但喂的是**独立 PIT 采集**的数据：财报按
`f_ann_date/ann_date ≤ 基准日` 过滤取最近一期、估值/资金/价按基准日当日、横截面 peer_context
每个基准日单独重建。rank-IC = Spearman(base_score, fwd_ret) 截面相关；signal 桶按 BUY/HOLD/
WATCH/AVOID 统计均收益/命中率/多空。跨同 horizon 窗口报 **per-window IC 的均值±std**（不堆叠成
单帧，避免伪独立）。

**残留泄漏风险（诚实告知）.**
1. **行业景气 L0 冻结** ⇒ fundamental 退化为硬财务(L5)+估值+资金+风险骨干；覆盖度低于生产，
   行业层信号被剔除（既因 overlay 内嵌当前 YoY 会泄漏，也按口径排除）。
2. **拟合常数** (信号阈值 BUY≥0.30 等、横截面再中心化基准 ROE_BENCH=3.1、archetype 毛利率中位数)
   均在当前 2026 池子上标定；过去基准日套用属**标签层二阶超前**（缓变的再中心化偏移，非预测标签
   本身）。按确认接受并在此说明，未按基准日重标。
3. **引擎内残留时间假设**（`aggregator._recency` wall-clock、DeriveRunner news_age）只作用于已排除
   的定性/新闻节点，低实质性。
4. **情绪类 dp_id**（雪球热度/新闻）无历史端点 → PIT 里 Inactive；它们属 sentiment/expectation_gap，
   非核心。
5. **生产泄漏 bug**（财报无 `f_ann_date` 过滤、forecast 无日期过滤、价无复权、`now` 锚定、peer_context
   读活库）见 `production_lookahead_findings.md`；本回测通过独立 PIT 采集**绕开**它们，未修改生产代码。

**LLM 隐性记忆.** 即便把检索输入约束到 ≤ 基准日，LLM 的参数化记忆仍“知道”基准日之后的事 —— 这无法
清除。因此严格无超前的唯一稳妥做法就是**分数不含 LLM 主观判断**：本回测正是如此（L0-L3 定性层完全
排除，分数只由确定性数值链驱动）。

**survivorship / 选样偏差.** 池子是**今天**精选的主题龙头 (config/mvp20.universe.yaml)，无退市/失败
标的；回测只回测了“幸存者”，IC 系统性上偏。结论仅在“幸存者内”成立。

**统计功效.** n≈100+/截面、每 horizon 仅 1–3 个跨窗口且复用同一池子（时间不重叠但截面非独立），
IC 标准误大；单点 IC 不显著属正常。本报告是**泄漏审计 + 合理性检查**，非策略验证。
"""
