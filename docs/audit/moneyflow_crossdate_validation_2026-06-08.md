# Moneyflow signal — cross-date validation & decision (2026-06-08)

**Verdict: REJECTED. The proposed `smart_money_signal_5d` moneyflow signal does NOT have a
stable cross-date edge. The single-date +0.16 rank-IC was an artifact and does not replicate.
The collector change was reverted; the engine's existing conservative moneyflow treatment is
empirically validated as correct.**

## Background

Starting question (user): "异常的资金流动是怎么算分的" → redesign exploration of moneyflow as a
scoring input. A 5-day, market-cap-normalized, retail-vs-institutional **divergence** signal
was proposed:

```
zhuli_net = (buy_lg+buy_elg) - (sell_lg+sell_elg)        # 主力净额 (large+xl orders)
sanhu_net = buy_sm - sell_sm                              # 散户净额 (small orders)
intensity = Σ_5d(zhuli_net - sanhu_net) / circ_mv        # normalized 5-day divergence
signal    = tanh(intensity / 0.02)  ∈ [-1, 1]
```

On a single base date (20260116) this scored **rank-IC +0.16 @ +10d** vs raw single-day 主力净额
+0.04 — a 4× improvement that looked promising. Per the agreed protocol ("稳了再接 live"), it was
validated across additional base dates **before** wiring into live `funding_score`.

## Method

- **Universe:** canonical 1641 A-share pool (date1 scored set), read directly from DockCase cache
  (moneyflow + daily_basic.circ_mv + daily), independent of per-date scoring progress.
- **Dates:** 20260116 (date1, in-sample), 20260309 (date2), 20260421 (date3).
- **Metric:** cross-sectional Spearman rank-IC of each signal vs +5/+10/+20d forward returns.
- **Constructions tested (7):** smart (shipped helper), diverge (=smart source), persist
  (Σ5d主力/circ), pv (量价折价), pos_days (5d净流入天数), norm (1日/circ), raw (1日绝对).
- **Control:** engine `base_score` rank-IC over the same windows (is the date measurable at all?).

## Results — moneyflow rank-IC @ +10d (the signal's best horizon)

| construction      | date1 (0116) | date2 (0309) | date3 (0421) |
|-------------------|--------------|--------------|--------------|
| smart (SHIPPED)   | **+0.161** ✅ | +0.030 (p0.24) ❌ | −0.049 (p0.05) ❌ |
| diverge (=source) | +0.161 ✅ | +0.030 ❌ | −0.049 ❌ |
| persist (5d/circ) | +0.150 ✅ | +0.029 ❌ | −0.033 ❌ |
| pv (量价折价)      | +0.149 ✅ | +0.016 ❌ | −0.026 ❌ |
| pos_days          | +0.088 ✅ | +0.039 ❌ | −0.025 ❌ |
| norm (1日)        | +0.065 | +0.001 ❌ | −0.073 ❌ |
| raw (1日)         | +0.043 | +0.006 ❌ | −0.074 ❌ |

**Every construction is significant-positive on date1 only, then collapses to statistical zero
(date2) or turns negative (date3). Not one of 7 survives out-of-sample.** This is the textbook
signature of a single-date / regime artifact, not a stable factor.

## Control — `base_score` rank-IC (n=1641 all dates)

| | +5d | +10d | +20d |
|---|---|---|---|
| date1 (0116) | −0.016 | **+0.113** (p0.00) ✅ | +0.078 (p0.00) ✅ |
| date2 (0309) | +0.158 (p0.00) ✅ | **+0.093** (p0.00) ✅ | +0.027 (p0.29) |
| date3 (0421) | −0.013 | **−0.241** (p0.00) ❗ | −0.205 (p0.00) ❗ |

**The decisive contrast is date2:** same 1641 names, same +10d window — `base_score` works
(+0.093, p0.00) while every moneyflow construction is dead (~0). This rules out the "date2 is an
unmeasurable dead zone" hypothesis: the failure is **specific to moneyflow**, not a measurement
problem. moneyflow adds nothing where the engine demonstrably works.

## Why this is the right outcome

The engine already treats moneyflow **conservatively**:
- `L11.short.flow_boost` (derive.py) is `audit_only` / `participates=False` → never enters score.
- `L7.flow.active_inflow` carries no `value.score` → near-zero funding contribution.
- `L7.mood.fomo` uses moneyflow only to **discount** overheating (fade, not chase).

Cross-date validation confirms this conservatism is correct: a *stronger* moneyflow scoring driver
would have diluted a working `base_score` on date2 and pushed the **same direction as the failure**
on date3. There is no regime in the sample where moneyflow rescues or complements the engine.

## Decision & action

- **REVERTED** `mvp20/sources/tushare_source.py` (removed `smart_money_signal_5d` helper + the
  `_emit_ak_outflow_cut` full-field/circ_mv/smart_money additions). Tree restored to baseline.
- **REMOVED** `tests/test_smart_money.py`.
- Full test suite re-run after revert → rc=0.
- No change to live scoring at any point (the experiment was additive/non-scoring throughout).

## Side-finding worth a separate thread (NOT moneyflow)

**date3 (20260421) `base_score` inverts hard: −0.241 @ +10d, −0.205 @ +20d, both p0.00, n=1641.**
The value/mean-reversion engine has a regime (forward window 20260421→20260522) where high-scored
names *underperform* — consistent with a momentum/junk rally or quality-selloff regime. This is an
**engine-level** finding, not a moneyflow one. It is the empirical case for activating the currently
**dormant `market_regime` multiplier** (a regime detector that down-weights the value tilt when the
cross-section inverts). Recommend investigating separately.

## Repro

```
python3 /tmp/mf_xdate2.py <base_date>     # 7 constructions × rank-IC, one date
# base_score control: inline script in session (scores table vs daily-cache forward returns)
```
