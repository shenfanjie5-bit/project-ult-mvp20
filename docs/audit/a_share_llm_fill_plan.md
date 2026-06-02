# A-share LLM/Overlay Fill Plan

Snapshot basis: `docs/audit/a_share_spec_completion.json` generated on
2026-05-26. The main audit report/script are owned by the main thread; this
plan only records the LLM/overlay closed-loop path.

## Closed-loop evidence policy

Closed-loop fills must not use open internet. Valid evidence is already-local
project state:

- `local_dp_id`: values injected from `runtime/hot.sqlite`, including
  Tushare rows such as `L1.company.main_business`
  (`tushare:stock_company`), `L9.disclosure.qa_recent`
  (`tushare:irm_qa_sz` / `tushare:irm_qa_sh`), `L8.gov.management_table`
  (`tushare:stk_managers`), local financial statements, and any locally
  extracted `L9.disclosure.annual_report` sections.
- `local_overlay`: already-filled overlay fields.
- `industry_inference`: framework-only inference, confidence <= 0.5,
  evidence quality `low`.

For `local_dp_id`, the overlay must cite the dp_id/source and copy the
`excerpt` verbatim from the injected value. Do not write `url` on closed-loop
evidence, even if the local value contains an original disclosure URL; the
verifier treats any `http(s)` string as web evidence.

## Mechanism check

The current mechanism can use local Tushare facts without internet:

- `scripts/codex_prompt_gen.py` filters fillable fields through
  `config/llm_field_governance.yaml`, injects declared
  `source_dependencies` from SQLite, and writes the current source
  fingerprint into the prompt.
- `scripts/verify_overlay_closed_loop.py` accepts local evidence when cited as
  `kind=local_dp_id` / `local_overlay` / `industry_inference`, and hard-fails
  web evidence on closed-loop tiers.
- `--check-excerpt` verifies `local_dp_id.excerpt` against the local SQLite
  value, so announcements/Q&A/company-main-business/management-table excerpts
  remain auditable without fetching the original web page.

Observed local evidence breadth in the current A-share snapshot:

| local dp_id | A-share coverage | source |
|---|---:|---|
| `L1.company.main_business` | 116 ts_codes | `tushare:stock_company` |
| `L9.disclosure.qa_recent` | 116 ts_codes | `tushare:irm_qa_sz`, `tushare:irm_qa_sh` |
| `L8.gov.management_table` | 116 ts_codes | `tushare:stk_managers` |
| `L5.is.revenue`, `L5.is.revenue_growth`, `L5.is.sga_rd`, `L5.cf.capex` | 116 ts_codes | Tushare financial statements / derived |
| `L5.is.gross_margin` | 108 ts_codes | Tushare income derived |
| `L5.bs.inventory`, `L5.bs.goodwill_ppe` | 106 ts_codes | Tushare balance sheet |
| `L9.disclosure.annual_report` | 1 ts_code currently | local cninfo annual-report extraction |

## Fillable field groups

### Ready for closed-loop company overlay

These L3/L4 gaps can be filled or left `Unknown` using only local Tushare
company facts plus local financials. They should be batched with
`--model-tier cheap_extract` and `--model-tier analysis`.

| dp_id | evidence to use | review notes |
|---|---|---|
| `L3.channel.mix` | `L9.disclosure.qa_recent`, `L1.company.main_business`, local annual-report revenue/customer sections if present | Extract only if channel split is stated; otherwise `Unknown`. |
| `L3.channel.overseas` | `L3.region.domestic_overseas`, local annual-report region/revenue sections | Fill after domestic/overseas is filled. |
| `L3.region.domestic_overseas` | `L5.is.revenue`, `L1.company.main_business`, annual-report region/revenue sections | Prefer disclosed revenue geography over inference. |
| `L3.region.fx_geo` | `L9.macro.fx`, `L3.region.domestic_overseas`, annual-report risk/region sections | If macro FX local row is missing, keep low confidence or `Unknown`. |
| `L3.region.key_risk` | `L3.region.fx_geo`, `L9.macro.geo`, annual-report risk/region sections | Requires human review for geopolitical interpretation. |
| `L3.region.tier_mix` | `L9.disclosure.qa_recent`, `L1.company.main_business` | Mostly relevant to retail/local services; many manufacturers should stay `Unknown`. |
| `L4.cost.rent_energy_logistics` | `L5.is.gross_margin`, annual-report business/risk sections | Do not split rent/energy/logistics without direct text. |
| `L4.eff.store_labor` | `L5.is.sga_rd`, annual-report business/revenue sections | Applicable mainly to store/labor-heavy models. |
| `L4.price.asp_aov_arpu` | `L5.is.revenue`, annual-report revenue sections, IR Q&A | Needs disclosed volume/users/order denominator; otherwise trend proxy only. |
| `L4.price.subscription` | `L5.is.revenue`, `L9.disclosure.qa_recent`, annual-report business/revenue sections | Set `N/A` only when business model clearly has no subscription pricing. |
| `L4.share.market` | `L5.is.revenue`, `L9.disclosure.qa_recent`, annual-report business/revenue sections | Prefer explicit market-share/rank wording; revenue rank is proxy. |
| `L4.volume.orders` | `L5.is.revenue`, `L9.disclosure.qa_recent`, annual-report customer/revenue sections | Fill only if orders/backlog/deliveries are disclosed. |
| `L4.volume.users` | `L5.is.revenue`, `L9.disclosure.qa_recent`, annual-report customer/revenue sections | Fill only for user/customer-count businesses with direct evidence. |

### Possible after local industry/peer rollup

These L0 fields are already in governance, but current industry prompts often
see missing `INDUSTRY:<id>` source rows for financial dependencies. They are
closed-loop candidates only after a local peer/leader rollup injects industry
or constituent-company facts into the prompt.

| group | dp_ids | local evidence path |
|---|---|---|
| Industry cost | `L0.cost.cac`, `L0.cost.energy_logistics`, `L0.cost.labor`, `L0.cost.raw_material`, `L0.cost.rent` | A-share peer `L5.is.sga_rd`, `L5.is.gross_margin`, `L5.cf.capex`, `L5.bs.goodwill_ppe`, `L4.cost.labor`; `L0.cost.raw_material` only where local commodity rows exist. |
| Industry demand | `L0.demand.frequency`, `L0.demand.penetration`, `L0.demand.replacement`, `L0.demand.terminal`, `L0.demand.user_count` | Constituent revenue/revenue-growth trends plus IR Q&A excerpts. |
| Industry price | `L0.price.contract_spot`, `L0.price.discount`, `L0.price.pricing_power`, `L0.price.product_asp` | Local gross-margin trend, raw-material rows, and Q&A pricing comments. |
| Industry supply | `L0.supply.capacity`, `L0.supply.chain_eff`, `L0.supply.channel_service`, `L0.supply.inventory` | Local capex/PPE/inventory/turnover/cycle rows plus Q&A. |

### Event-driven candidates needing better local feeds

These can remain closed-loop, but current evidence is too sparse or generic for
automatic broad promotion:

- `L0.compete.share_concentration`
- `L0.policy.access_license`
- `L0.policy.regulation`
- `L0.policy.subsidy`
- `L0.policy.tax_trade`
- `L0.tech.ai_automation`
- `L0.tech.breakthrough`
- `L0.tech.substitute_tech`
- `L0.sentiment.social`

Use only local event/news/policy/social rows. If the only available source is
mock or a generic industry row, leave `Unknown` or `Inactive` and require
manual review.

### Not generally closed-loop fillable

These should not be counted as LLM/overlay closed-loop work until upstream
facts exist or governance/overlay schema is added:

| dp_id | reason |
|---|---|
| `L0.cost.capital` | No current governance entry or overlay node; needs rates/credit-cost source design. |
| `L0.sentiment.institutional` | Premium/positioning-style field; no local closed-loop evidence. |
| `L0.sentiment.leader_drag` | No current governance entry or overlay node; needs explicit leader linkage rule. |
| `L0.sentiment.sector_heat` | No current governance entry or overlay node; ETF/sector flow source not present. |
| `L3.delivery.csat` | Usually requires customer-review/CSAT alt-data; fill closed-loop only if local annual report/IR directly states satisfaction/service metrics. |
| `L4.eff.conversion_retention` | Usually needs funnel/retention data; local revenue proxy alone is insufficient. |
| `L4.volume.foot_traffic` | Usually needs store traffic alt-data; many A-share industrial names are `N/A` rather than fillable. |
| `L4.volume.frequency` | Usually needs usage-frequency alt-data; fill only with direct local disclosure. |

## Prompt and overlay requirements

1. Generate field batches with `scripts/codex_prompt_gen.py`; use
   `--list-only` first to confirm only intended dp_ids are fillable.
2. For closed-loop tiers, do not browse and do not add `http(s)` anywhere in
   `evidence_sources`.
3. Write `source_fingerprint_at_fill`, `last_filled_period`, and
   `last_event_id` exactly as prompted.
4. For `Known`, cite at least one `local_dp_id` or `local_overlay` evidence
   with a verbatim excerpt. For weak framework-only conclusions, keep
   confidence <= 0.5 and `evidence_quality: low`.
5. If local evidence does not directly support the field, leave
   `data_status: Unknown` with `missing_reason: "no_local_evidence"` or a more
   specific local-source reason.
6. Run verification before promoting:

```bash
python3 scripts/verify_overlay_closed_loop.py --check-excerpt --check-schema --quiet
```

Use `--auto-demote` only after reviewing the violation list because it rewrites
overlay files.
