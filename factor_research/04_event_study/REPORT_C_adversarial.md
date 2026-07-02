# REPORT C — Adversarial review of the forecast (业绩预告) signal

**Mandate:** independently try to KILL the claim that forecast carries a deployable signed alpha; headline threat = survivorship. **Could not kill it.** Verdict: **SURVIVE — CONSTRAINED.**
(Numbers independently re-verified by the orchestrator with `adv/advlib.py` on 2026-06-09: survivor +31.1bps 6/7 t=8.4 → full/de-survivored +32.8bps 7/7 t=14.0.)

Artifacts: `adv/build_full_panel.py` (builds 5602×816 de-survivored panel), `adv/advlib.py` (`Panel.full()/survivor()`, reproduces `eventlib` to the bp), `adv/full_panel.npz`.

## (a) Survivorship — universe expanded, edge SURVIVED & strengthened
- The 1617-name panel = `universe()` (scored as of 20260116) **plus** an explicit `ST/PT/退` filename drop (`_datalib.py:38`). DockCase `历史日线/by_symbol` has **5825** symbols → ~4200 excluded; only **319 delisted (128 in-window)**, the other ~3700 are clean alive non-ST names dropped purely for not being in the scored set → this is dominantly **selection** bias, not delisting.
- De-survivored panel: **5602 stocks × 816 days, 18,127 priceable events** (vs 5210). Sign mix **flips 58% positive → 56% negative** — excluded names are disproportionately negative-forecast, exactly as a survivorship prior predicts.
- **Long-only @25bps: survivor +31.1bps (6/7) → full +32.8bps (7/7)** at h=1; +34.5/7-7 at h=3; 预增-only +43.2/7-7. The one losing fold (2023H1) flips positive. **Edge strengthened.**
- **Mechanism (key):** survivorship inflates the long leg's *raw* return AND the size-decile *benchmark* equally → the **abnormal** return is invariant ≈+56bps. Survivorship is real in raw returns but **cancels in the abnormal number**. Full-panel placebo (shuffled dates) = +4.5bps vs +57 real → PIT-clean.
- Buyable-only set (drop ST+delisted, 7302 events): +55.5bps gross / +30.5bps net — does not depend on un-tradeable names.

## (b) Size artifact? Survives — but exposes a framing correction
- Survives **plain market-adjust** (+31.1bps, 7/7) and **industry-adjust** (110 tushare industries: +31.5bps, 7/7). Not a sector bet.
- Small-cap *tilt* exists (smallest-MV decile +90bps vs mega-cap +38bps) but the edge is positive in **every** decile and abnormal is computed *within* size deciles → amplified-in-small-caps, not a small-cap factor in disguise.
- **The genuine hole:** the "long-only net" is on **size-adjusted** returns = a **hedged/market-neutral** alpha. An unhedged buy-and-hold long book earns RAW **+9.2bps net, 5/7, ±100bps/fold** on market beta. **"+32bps" is realized only if you run the size/market hedge.** Re-label it market-neutral, not "+30bps long-only".

## (c) Capacity / calendar
- **Capacity — micro-cap concern refuted.** 预增 Q5 winners (+108.8bps) are **mid-caps**: median MV ≈¥8bn, only 4% below ¥2bn, median daily notional ≈¥0.3bn. Magnitude effect orthogonal to size. Deployable at tens-to-low-hundreds of ¥M/window; will **not** scale to large books without impact.
- **Calendar — confirmed binding constraint.** **83% of long events in Jan+Jul** (mandatory preannouncement windows). Twice-a-year batch, idle ~8–9 months/yr → low annualized capital efficiency. All 7 folds positive (37–71bps gross) → not one-regime. Clustered significance: naive t=14 overstates (within-window correlation); clustered by day t=6.0, by month t=5.3 — still decisively positive.
- **Short leg fragile (confirmed):** +19.9bps but **4/7 folds** — not deployable standalone.

## (d) Final verdict + honest ceiling
**SURVIVE — CONSTRAINED.** Not an artifact. Deployable ≈ **+25–35bps/event net of 25bps as a size/industry-neutral, twice-a-year (Jan/Jul) batch overlay**, mid-cap capacity, long-tilted (short leg a soft avoid, not a confident short). Run unhedged it degrades to ≈+9bps and is unstable. Survives 40bps (+17.8/6-7), 1% trim (+27.2/7-7), winsor (+30.4/7-7), and de-survivoring. The required correction to the prior pass: **bill it as a market-neutral hedged alpha, not a "+30bps long-only" return** (overstates an actual long book by ~3×).
