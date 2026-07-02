# A-share derive-layer normalization plan — wiring the remaining real fields into `final_score`

Generated 2026-05-29. Follow-on to the realtime→score bridge
(`mvp20/aggregator.py: synthesize_realtime_nodes` / `_realtime_signal`).

## Problem statement

The bridge already routes governance `participates_in_score` real-Known fields
into `final_score`, but `_realtime_signal` only maps payloads whose sign is
*unambiguous* (explicit `score`/`intensity`, `*_percentile`, `yoy_pct`, a few
curated signed-pct fields). Everything else returns `None` and is synthesized
**neutral** (no contribution) on purpose — to avoid injecting wrong signals.

Across the 116-stock A-share universe there are **78** participating real-Known
dp_ids; **67 are still neutral**. This plan turns them into correctly-signed
signals.

## Architectural recommendation — hybrid (not "all in derive")

Two homes for the value→signal logic; pick per field by whether normalization
needs an external reference:

- **Bridge-side** (extend `_realtime_signal`): for payloads that already carry
  a normalized/extractable signal (a `*_score` key, a `multiplier` centered at
  1.0, a severity/quantile, a signed pct, a rating distribution). No re-collect
  needed — works on existing rows immediately. ~30 fields.
- **Derive/source-side** (emit a signed `signal` key into the payload, then the
  bridge's existing `score`-key passthrough picks it up): for **raw ratio**
  fields (`L5.is.*`, `L6.mult.ps/mcap_fcf`, efficiency/leverage ratios) whose
  sign/magnitude is meaningless without a **history percentile or peer median**.
  That reference is only available where the row is produced (Tushare/derive),
  so normalization belongs there — exactly like `L10.val.historical_quantile`
  already does for PE/PB. Needs a re-collect/re-derive to populate. ~25 fields.

Both keep `score_company`/aggregation untouched. Adding a `signal` key to a
payload is additive (FrontEnd ignores unknown keys) — no FrontEnd change.

## Reusable normalization patterns (the leverage — ~12 rules cover the 67)

> All signals are signed, clipped to [-1, 1]. Direction sign for the
> *inverted* targets (`risk_discount`, `priced_in_discount`, `overheat_risk`,
> `valuation_rerating`-when-expensive) means "bad/expensive → negative".

| ID | Shape (payload keys) | Rule | Home |
|---|---|---|---|
| **A** | `multiplier` (~1.0) | `clip(multiplier - 1.0, -1, 1)` | bridge |
| **B** | explicit `*_score` (`priced_in_score`, `net_revision_score`) | extract, `clip(-1,1)`; negate for risk targets | bridge |
| **C** | `alert_severity` enum `{None,WARN,ERROR}` | `{None:0, WARN:0.5, ERROR:1.0}` → **negative** (risk). ⚠ verify ERROR=severity not fetch-error first | bridge |
| **D** | `max_quantile`/`pe_pct`/`pb_pct` | `(max_pct-0.5)*2`, invert for valuation/risk | bridge |
| **E** | momentum `d5_pct/d20_pct/d60_pct` | `-tanh(d20_pct/0.15)` for priced_in (run-up = priced-in) | bridge |
| **F** | guidance `change_pct_min/max` or `type` enum | `clip(((min+max)/2)/100, -1, 1)`; enum 预增/预减→±; ⚠ double-count w/ L11 bootstrap | bridge |
| **G** | rating dist `avg_rating_score` (1-5) or strong_buy..strong_sell | `(avg_rating_score-3)/2` | bridge |
| **H** | embedded `*_yoy_pct` (cost/inventory/ar) | `tanh(yoy/K)`, sign per cost(–)/growth(+) semantics | bridge/derive |
| **I** | named ratio vs threshold (`leverage_ratio`, `goodwill_to_assets`, `ccc_days`, turnover days) | piecewise vs domain norm → signed | derive (norms) |
| **J** | raw `scalar` ratio (`L5.is.*`, `L6.mult.ps/mcap_fcf`) | **emit history/peer percentile** at source → `(pct-0.5)*2` | derive/source |
| **K** | macro composite (`m2/m1`, `cpi/ppi`, `lpr_*_change_bp`, index `*_5d_pct`) | pick the driver indicator → bounded signal | derive/source |
| **L** | count/event (`count_24h`, `events`, `div_proc`, buyback) | presence/count → bounded; events polarity by type | bridge/derive |
| **M** | `segments[]` list | revenue-share-weighted aggregate of per-segment growth/margin | derive (bespoke) |
| **N** | named flow amount (`margin_balance`, block `total_amount`, `delta_30d_pp`, `net_amount`) | trend/Δ vs base → bounded | derive |

## Prioritized batches

Priority = score-impact (directional additive/subtractive > multipliers >
confidence) × mapping cleanliness × coverage.

### P0 — directional components, clean bridge-side mapping, high coverage (do first; immediate, no re-collect)

| dp_id | score_target | cov | pattern | note |
|---|---|---:|---|---|
| L8.val.overvalued | risk_discount | 116 | D | use `max_quantile`; expensive→negative |
| L8.val.priced_in | risk_discount | 116 | B | `priced_in_score`→negative |
| L6.priced.run_up | priced_in_discount | 116 | E | run-up→negative |
| L6.priced.analyst_revision | expectation_gap | 115 | B | `net_revision_score` |
| L9.company.earnings_guidance | expectation_gap | 116 | F | ⚠ L11 bootstrap already uses it |
| L5.fcst.guidance_change | expectation_gap | 116 | F | 预增/预减 enum→sign |
| L7.mood.analyst_rating | sentiment_score | 115 | G | `avg_rating_score` 1-5 |
| L6.state.expansion_compression | valuation_rerating | 105 | A/K | `ratio_vs_250d`,`slope` |
| L6.state.industry_center | valuation_rerating | 116 | J | stock vs `industry_pe/pb/ps_median` |
| L7.trade.margin_short | funding_score | 116 | N | margin_balance Δ |

### P0b — derive/source-side ratio normalization (the core "derive-layer" work; needs re-collect)

| dp_id | score_target | cov | pattern | reference to emit |
|---|---|---:|---|---|
| L6.mult.ps | valuation_rerating | 116 | J | PS history percentile (per stock) |
| L6.mult.mcap_fcf | valuation_rerating | 108 | J | MCap/FCF history percentile |
| L5.is.gross_margin | fundamental_score | 108 | J | margin vs own history + peer median |
| L5.is.margins | fundamental_score | 116 | J | operating/net vs history/peer |
| L5.is.operating_profit | fundamental_score | 116 | J | yoy or vs history |
| L5.is.eps | fundamental_score | 115 | J | eps yoy / vs history |
| L5.cf.capex | fundamental_score | 116 | J/N | capex intensity trend |
| L5.bs.leverage | fundamental_score | 116 | I | `leverage_ratio` vs ~0.6 norm |
| L5.bs.goodwill_ppe | fundamental_score | 106 | I | `goodwill_to_assets` threshold |
| L4.eff.cycle | fundamental_score | 106 | I | `ccc_days` vs peer/industry |
| L4.eff.turnover | fundamental_score | 108 | I | turnover days vs peer |
| L4.cost.labor | fundamental_score | 116 | H | `labor_cost_yoy_pct`→negative |
| L4.cost.raw_material | fundamental_score | 108 | H | `cogs_yoy_pct`→negative |

### P1 — multiplier / macro targets (scale the score; mostly pattern A or macro key-pick)

A-trivial (already carry `multiplier`): L6.sens.cashflow, L6.sens.growth_margin,
L6.sens.rates, L6.sens.risk_narrative, L7.env.risk_appetite.
Macro key-pick (K): L7.env.liquidity, L7.env.market_trend, L7.env.rates,
L9.macro.cpi_employment, L9.macro.rates, L0.cost.capital,
L0.cost.energy_logistics, L0.cost.raw_material, L9.media.report.
Flow/sentiment multipliers (N): L0.sentiment.institutional, L7.flow.etf_inflow,
L0.sentiment.sector_heat, L0.sentiment.leader_drag, L0.sentiment.social.
Events (L): L9.company.buyback_dividend.

### P2 — low coverage (<30), bespoke, or confidence-only (defer)

- Bespoke segments (M): L2.segment.gross_margin, L2.segment.growth,
  L2.segment.revenue_share.
- Sparse risk/capital (cov<30): L8.cap.liquidity_short(25),
  L8.cap.short_increase(34), L8.fin.debt_pressure(22), L8.fin.eps_downward(21),
  L8.gov.insider_sell(23), L8.op.cost_overrun(14), L8.op.inventory_glut(22),
  L9.capital.inst_buy_sell(4), L9.capital.margin_anomaly(12),
  L9.media.analyst_action(1), L7.flow.block_trade(15), L7.flow.institutional(2),
  L6.priced.discussion(26).
- Medium event/risk (C/L, cov~55-74): L8.cap.outflow_cut(74),
  L8.fin.cash_ar(66), L8.gov.management_change(55),
  L9.company.mgmt_litigation(55).
- Confidence-only (already contribute confidence via neutral nodes):
  L10.industry.pmi, L10.industry.fund_flow.

## Key risks to resolve before implementing

1. **`alert_severity` semantics (pattern C).** Values are `{None, WARN, ERROR}`.
   `L8.fin.debt_pressure` shows `alert_severity="ERROR"` *with valid data*
   (`interest_debt_to_ebitda=5.39`), so ERROR likely = severe-risk, not a fetch
   error — but VERIFY in the emitter before mapping. Safer: drive the risk
   signal from the underlying ratios (`interest_debt_to_ebitda`,
   `debt_to_assets`) vs thresholds, and use severity only as a confirm.
2. **Double-counting with the derive bootstrap.** `_bootstrap_l11_subscores`
   already consumes some of these inputs (earnings_guidance change_pct, gross
   margin, roe, net margin, pmi, active_inflow) into `L11.*.score`. Those L11
   scores have their own score_target. Confirm the bridge feeding the SAME
   underlying data into `expectation_gap`/`fundamental_score` is intended, not
   a duplicate of the L11 path, before wiring F/H/J for those dp_ids.
3. **Sign conventions per target** (esp. inverted targets) — lock each with a
   test asserting the *direction of the final_score change* (as done for the
   percentile/valuation cases in `tests/test_realtime_bridge.py`).
4. **Re-collect dependency** for P0b/J/K — signals that need history/peer
   references only populate after re-running the Tushare/derive pipeline.

## Suggested implementation order

1. **P0** (10 fields, bridge-side) — extend `_realtime_signal` with patterns
   B/D/E/F/G + the two valuation fields; per-field direction tests. Biggest
   score impact, no re-collect, low risk. Verify final_score deltas on
   300750.SZ + a basket.
2. **P0b** (13 fields, derive/source-side J/I/H) — add `signal` emission
   (history/peer percentile) alongside the raw ratios; re-collect; verify.
3. **P1** (multipliers/macro) — pattern A is ~free; macro key-pick next.
4. **P2** — only if the marginal coverage is worth it; many are sparse.

After each batch: re-run `scripts/check_a_share_spec_completion.py` (coverage)
and the score basket, and confirm no mock/`Mock`-status rows leak.
