# Regime conditioning (R-7) — date3 inversion: two prototypes & decision (2026-06-08)

**Verdict: NEITHER prototype is shippable on 3 base dates.** The date3 base_score inversion is
**mostly intrinsic to the engine's value/quality identity**, not an incidental over-penalty.
(A) a portfolio-level regime filter cannot detect the hostile regime PIT (the froth hypothesis
fires *backwards*); (B) component-level penalty-shrink is the right *kind* of lever and helps, but
even fully zeroed it recovers only ~⅓ of the trading-day inversion. The dormant
`market_regime_multiplier` (a market-wide **scalar**) is mathematically incapable of fixing a rank
inversion — confirmed. This closes the first empirical data point for the R-7 work deferred at
`scoring.py:134` and `scoring.py:190`.

## Background

PIT backtest (1641 A-shares, 3 base dates) found `base_score` rank-IC vs +10d fwd ret:
date1=20260116 **+0.113**, date2=20260309 **+0.093**, date3=20260421 **−0.241** — date3 is a hard
inversion. Diagnosis (`/tmp/date3_regime.py`): date3 was a **tech/growth/small-cap MOMENTUM
melt-up** (半导体 +14% / 电子 +10.6% / AI +9.4% / 机器人 +9.2%; small-cap Q1 +10.9%; prior winners
kept winning, momentum IC +0.19). The engine (value + quality + anti-crowding + mean-reversion)
faded exactly these hot names → AVOID +8.0% vs BUY +0.5%.

Two prototypes were run in parallel to test fixes (read-only / non-destructive; baseline scores and
DockCase cache untouched, `DOCKCASE_WRITEBACK=0` throughout).

---

## A — Portfolio-level regime filter (`/tmp/regime_filter.py`)

A PIT regime detector → neutralize exposure (go flat) in hostile regimes; keep the engine's signal
otherwise. Read-only overlay on the existing `base_score`.

**Regime-detector legs, rank-IC vs +10d (PIT, only data ≤ base date):**

| leg | date1 | date2 | date3 | isolates date3? |
|---|---|---|---|---|
| style_gmv_20d (国证成长 399370 − 国证价值 399371) | +0.052 | −0.026 | +0.059 | barely (margin +0.008, noise) |
| smfroth csi2000−hs300 (20d) | **+0.091** | +0.027 | +0.055 | **no — date1 frothier** |
| smfroth gz2000−hs300 (20d) | **+0.100** | +0.016 | +0.057 | **no — date1 frothier** |
| mom_persist (PIT prior-40→20d vs 20d→base) | +0.081 | −0.084 | +0.007 | **no — date3 lowest** |
| forward momentum (prior-20d vs +10d fwd) — NOT PIT | −0.045 | −0.003 | **+0.186** | yes, but unobservable |

**Findings:**
- **The small-cap-froth hypothesis is FALSIFIED, backwards.** Every froth leg is *higher on date1*
  than date3 — date1 was the bigger melt-up (csi2000−hs300 +9.1% vs +5.5%; breadth 84% up vs 45%).
  A "gmv + small-cap froth" composite flags **date1** (the engine's *best* day) as hostile.
- The only signal that cleanly isolates date3 is **forward** momentum (+0.186), which is **not
  PIT-observable**. Its PIT proxy (momentum *persistence*) ranks date3 *lowest* → uninformative.
- A "least-bad" rule `hostile if style_gmv_10d ≥ 0.0607` flags date3-only and matches an **oracle**
  that flattens date3 (3-date mean +10d IC −0.012 → +0.069; full recovery, zero cost on date1/2) —
  but the 10d lookback was chosen *after* seeing 20d ties and 40d inverts; margin is noise-level;
  ~18 leg/lookback combos searched → textbook curve-fit on 3 points.

**Verdict A:** promising direction, **NOT shippable**. Detector doesn't work PIT on this sample;
the proposed froth leg is actively harmful. Needs ≥15–20 more base dates spanning known momentum
melt-ups AND value/reversal regimes; prefer soft de-grossing over a hard binary flat.

---

## B — Component-level regime conditioning (`/tmp/regime_component.py`)

Shrink the cross-sectional anti-crowding penalties — `priced_in_discount` (crowdedness + run_up +
priced_in) and `overheat_risk` (fomo) — by factor s in a momentum regime. Re-scored all 3 dates
from the **frozen** `runtime/backtest/<asof>/pit.sqlite` via `pit_backtest.score.score_one`, with a
**monkeypatch** that scales penalty-node `score` by s after aggregation (repo source NEVER edited;
tree verified clean). Regime flag hardcoded per prototype (date3=momentum); the *detector* is A's
(failed) workstream — B tests only whether the *mechanism*, given a correct flag, repairs the rank.

**rank-IC, date3 (baseline inverted −0.239):**

| scenario | +5d | +10d | +15d | +20d | hfq-30cal |
|---|---|---|---|---|---|
| baseline s=1.0 | −0.012 | **−0.239** | −0.212 | −0.203 | **−0.153** |
| shrink s=0.5 | +0.018 | −0.208 | −0.173 | −0.162 | −0.110 |
| shrink s=0.0 (full) | +0.050 | **−0.168** | −0.126 | −0.114 | **−0.059** |

**Cost (same shrink applied at date1/date2):**

| | date1 +10d | date2 +10d | date1 hfq30 | date2 hfq30 |
|---|---|---|---|---|
| baseline | +0.113 | +0.158 | +0.064 | +0.033 |
| shrink s=0.0 | **+0.136** (rises) | +0.139 (−12%) | +0.060 (~flat) | +0.018 (−half) |

Diagnostic: s=0.0 lifts date3 mean `base_score` **+0.272** (max +0.999; 1137/1641 lifted) — a large
*level* shift, but only a partial *rank* fix.

**Findings:**
- **Mechanism is the right kind** — shrinking a cross-sectionally-varying penalty *does* move
  rank-IC (unlike a scalar). Given a correct flag the trade is favorable: big date3 recovery, small
  date2 cost (~12%), ~0 (even positive) date1 cost — the penalties carried edge only at date2.
- **But it only fixes ~⅓.** Fully zeroed, date3 stays inverted (−0.168 @ +10d / −0.059 @ hfq30).
  `priced_in_discount` + `overheat_risk` are only ~⅓ (trading +10d) / ~60% (hfq30) of the inversion.
  The residual comes from the engine's **core value/quality tilt** (`expectation_gap`,
  `valuation_rerating`, fundamental's preference for cheap quality) — which is the engine's *thesis*,
  not a removable knob. Shrinking *that* would gut date1/date2.

**Verdict B:** mechanism real and usable as a **secondary lever**, but alone insufficient — the
inversion is mostly the engine being a value engine.

---

## Combined verdict

| | A (portfolio filter) | B (component conditioning) |
|---|---|---|
| mechanism efficacy | can fully avoid date3 (flat) | recovers only ⅓–⅔; residual inversion |
| blocking wall | regime NOT PIT-detectable (froth fires backwards; 3-date curve-fit) | even a perfect flag fixes only part; full fix needs core tilt → destroys date1/2 |
| cost when correct | ~0 on date1/2 (if flag right) | date2 −12%, date1 ~flat |

**date3's inversion is largely an intrinsic property of the value/mean-reversion identity, not an
incidental over-penalty. It cannot be removed without changing what the engine IS.** The two
prototypes are complementary halves blocked on the same wall: you can't reliably detect the regime
(A), and even with perfect detection a component-shrink fixes only part (B).

## Recommendation

1. **Ship neither on 3 dates.**
2. **Near-term protection is positional, not algorithmic:** accept this is a value engine; add a
   portfolio/human regime guard — **de-gross / don't execute the signal when small-cap + momentum
   rip together**. (A's "option b"; portfolio overlay, doesn't touch score rank; lowest risk.)
3. **Algorithmic path is data-blocked:** gather ≥15–20 base dates (momentum melt-ups + value
   reversals), validate a **momentum-persistence** detector (mechanistically correct, PIT-safe
   candidate), then a **soft de-gross overlay**; use B's component-shrink as a secondary lever.

## Implications for the dormant `market_regime_multiplier` (R-7)

The TODOs at `scoring.py:134` (make `_INDUSTRY_TOTAL_SCALE` regime-adaptive) and `scoring.py:190`
(dynamic macro-regime amplification, "deferred to R-7 — validated by the point-in-time backtest")
now have their first data point:

- **A market-wide SCALAR multiplier cannot fix a rank inversion** (uniform positive scaling preserves
  rank order → rank-IC invariant). The dormant scalar (median 1.007) is the wrong tool — it can only
  retune BUY-count/aggressiveness, never the date3 cross-sectional inversion.
- A real regime fix requires either a **component-conditioning hook** (B — scale specific
  cross-sectional penalties) or a **portfolio-level overlay** (A's option b — de-gross), gated on a
  PIT detector that does **not yet exist** for this regime. Both need ≥15–20 dates to validate.

## Repro

```
python3 /tmp/date3_regime.py            # date3 inversion decomposition (sector/size/style/mode)
python3 /tmp/regime_filter.py           # A: portfolio filter + regime detector legs
python3 -u /tmp/regime_component.py     # B: re-score from frozen pit.sqlite, baseline vs s=0.5/0.0
```

Both prototypes are read-only / monkeypatch (no repo source edits; baseline `backtest.sqlite` and
DockCase cache untouched). 3-date sample → all conclusions are directional pending more dates.
