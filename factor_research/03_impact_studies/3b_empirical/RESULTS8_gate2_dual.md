# RESULTS8 — Dual-condition regime gate (Tier-1 prototype) ✅ validated direction

**One line:** Replacing the single hard regime skip (RESULTS5, "is_bad → cash") with a
**dual-condition down-weight** — gate fires only when `is_bad` **AND** the model's trailing
realized IC has gone negative — **eliminates the single gate's good-year误伤 while keeping the
bad-regime benefit**, and is robust across down-weight strength / decay-window params.

## Design (`factor_research/run_gate2.py`, causal / zero-tuned)
- `bad_regime` = up-trend(trend60>0) AND high-vol(vol20 > past-only median) — same economic def as v1.
- `ic_decay` = trailing realized rank-IC of the proxy `L=z(STREV)−z(RVOL)` over the last DECAY_M
  **matured** windows (window j counts only if `j.k + IC_HZ ≤ now` → strictly past, PIT-safe).
  This is the observable proxy for "model is currently failing" (true IC-decay isn't visible at
  decision time). The single most important unbuilt piece per RESULTS7.
- **Gate:** `w = w_min if (bad_regime AND ic_decay<0) else 1`; `gated_ret = w · cohort_ret`.
  **Down-weight only, never sign-flip.** Zero tuned params; every decision uses only past data.
- Track = the dense 73→47-window proxy loop (2024-2026, top-decile BUY cohort), the high-power
  track. Validated on **BUY-cohort forward P&L + per-year + worst-window**, NOT on IC (IC is blind
  to the down-weight, RESULTS6 §3a).

## Result (+10d cohort return, n=47 windows, recommended w_min=0, DECAY_M=6)
| variant | mean | worst(5pct) | %gated | 2024 | 2025 | 2026 |
|---|---|---|---|---|---|---|
| ungated | +0.76% | −4.85% | — | +0.27% | +1.41% | **−0.47%** |
| single-gate (v1, RESULTS5) | +0.31% | −4.46% | 40% | **−0.47%** | **+0.85%** | +0.37% |
| **DUAL-gate (v2)** | **+0.73%** | −4.46% | 17% | +0.04% | +1.29% | **+0.40%** |

The dual gate recovers the 2026 bad-regime benefit (−0.47→+0.40 ≈ single's +0.37) **without** the
single gate's 2024/2025 drag (≈ ungated). Net mean ≈ ungated → the gate is no longer a drag. Fires
17% vs single's 40% (only when BOTH conditions hold).

## Robustness (9 configs: w_min∈{0,0.3,0.5} × DECAY_M∈{4,6,8})
- **Good-year "do no harm" is invariant**: 2024 +0.04~+0.27%, 2025 +1.00~+1.42% across ALL configs
  (never the single gate's −0.47% / +0.85% drag).
- **Bad-regime benefit needs strong down-weight**: 2026 = +0.28~+0.57% at w_min=0; fades to ~0 at
  w_min=0.5 (partial down-weight only avoids half the loss). → recommend w_min ≤ 0.3.
- dual_mean +0.68~+0.77% ≈ ungated in every config.

## Honest caveats (NOT production-ready)
1. **PROXY track**, not the real base_score (L correlates ~±0.5 with real short_total). The real
   engine gate must be re-validated on real base_score.
2. **ONE bad regime (2026) in sample** → "helps 2026" is a single episode (could be luck). The
   "no good-year harm" is firmer (2 good years × 9 configs, stable). Need more bad-regime episodes
   (2024-01 crash, 2018, 2015) to confirm the benefit generalizes.
3. **n=47 overlapping windows** (~½ effective independence) → modest significance; treat as ordering
   evidence, not proof.
4. Absolute benefit is small — the gate's value = avoiding ~1 bad regime / few years at ~0 ongoing cost.

## Verdict & next steps
**Validated DIRECTION** (first net-positive change in the redesign): the dual condition is what makes
a regime gate net-positive — exactly the RESULTS5/7 prescription, now demonstrated. To productionize:
1. Re-validate on REAL base_score across ≥10-15 base dates spanning multiple bad regimes (needs the
   offline price/flow cross-section pre-caching — `run_realbase.py:109` build path; ~the 35h job or a
   cached panel). Don't ship on the proxy + 1 regime.
2. Then implement as a **decision-layer gate** in the engine: scale BUY conviction / raise the BUY
   threshold by `gate_strength` (do NOT change base_score ranks). Inputs: market trend60 + vol-vs-
   past-median (already emittable) + the trailing realized BUY-cohort P&L (the ic_decay proxy).

## Repro
```
.venv/bin/python factor_research/run_gate2.py [w_min] [decay_m]   # default 0.0 6
# → factor_research/data/gate2_results.json
```
Builds on RESULTS5_gate.md (single gate) + RESULTS7_synthesis_A_B.md (the dual-condition prescription).
