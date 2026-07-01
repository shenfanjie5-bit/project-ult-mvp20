# A-share non-LLM materialization audit

- Generated: `2026-06-24T01:58:30+08:00`
- Dry run: `True`
- Stocks: `1646`
- Target fields: `55`
- Target cells: `90530`
- Candidate available: `86701`
- Candidate unavailable: `3829`
- Write unavailable: `True`
- Schema invalid: `0`
- Overlays written: `0`
- Sample: `1811/1811` passed

## Actions

| action | count |
|---|---:|
| `would_update` | 90530 |

## Skip Reasons

| reason | count |
|---|---:|

## Candidate Unavailable Reasons

| reason | count |
|---|---:|
| `missing capex or PPE` | 1550 |
| `missing L3.region.domestic_overseas runtime value` | 706 |
| `no local extractor implemented` | 377 |
| `main business text does not directly expose both domestic and overseas business lines` | 343 |
| `missing forecast revisions and EPS consensus` | 338 |
| `missing gross margin` | 278 |
| `missing comparable segment revenue/gross margin` | 75 |
| `missing L2.segment.gross_margin` | 74 |
| `main business text does not expose an enumerable product list` | 44 |
| `keyword hit requires LLM/human gate before Known` | 17 |
| `missing L2.segment.revenue_share` | 8 |
| `missing L5.is.sga_rd/L5.is.revenue` | 8 |
| `missing revenue growth` | 7 |
| `missing SGA/R&D ratio and gross margin` | 2 |
| `missing peer revenue rank` | 2 |

## Field Actions

| dp_id | actions |
|---|---|
| `L1.moat.tags` | `{"would_update": 1646}` |
| `L1.model.tag` | `{"would_update": 1646}` |
| `L1.position.growth_rank` | `{"would_update": 1646}` |
| `L1.position.market_share` | `{"would_update": 1646}` |
| `L1.role.tag` | `{"would_update": 1646}` |
| `L1.stock_attr.tags` | `{"would_update": 1646}` |
| `L2.segment.cash_contrib` | `{"would_update": 1646}` |
| `L2.segment.industry_exposure` | `{"would_update": 1646}` |
| `L2.segment.opex_ratio` | `{"would_update": 1646}` |
| `L2.segment.profit_share` | `{"would_update": 1646}` |
| `L3.channel.cost` | `{"would_update": 1646}` |
| `L3.channel.efficiency` | `{"would_update": 1646}` |
| `L3.channel.mix` | `{"would_update": 1646}` |
| `L3.channel.overseas` | `{"would_update": 1646}` |
| `L3.customer.concentration` | `{"would_update": 1646}` |
| `L3.customer.solvency` | `{"would_update": 1646}` |
| `L3.delivery.capacity_supply` | `{"would_update": 1646}` |
| `L3.delivery.fulfillment_cost` | `{"would_update": 1646}` |
| `L3.product.margin_mix` | `{"would_update": 1646}` |
| `L3.product.portfolio` | `{"would_update": 1646}` |
| `L3.region.domestic_overseas` | `{"would_update": 1646}` |
| `L3.region.fx_geo` | `{"would_update": 1646}` |
| `L3.region.tier_mix` | `{"would_update": 1646}` |
| `L4.cost.cac_production` | `{"would_update": 1646}` |
| `L4.cost.rent_energy_logistics` | `{"would_update": 1646}` |
| `L4.eff.capacity_utilization` | `{"would_update": 1646}` |
| `L4.eff.store_labor` | `{"would_update": 1646}` |
| `L4.price.asp_aov_arpu` | `{"would_update": 1646}` |
| `L4.price.discount` | `{"would_update": 1646}` |
| `L4.price.elasticity` | `{"would_update": 1646}` |
| `L4.price.pricing_power` | `{"would_update": 1646}` |
| `L4.share.market` | `{"would_update": 1646}` |
| `L4.share.substitution` | `{"would_update": 1646}` |
| `L4.volume.orders` | `{"would_update": 1646}` |
| `L4.volume.sales` | `{"would_update": 1646}` |
| `L4.volume.shipments` | `{"would_update": 1646}` |
| `L4.volume.users` | `{"would_update": 1646}` |
| `L5.fcst.beat_probability` | `{"would_update": 1646}` |
| `L8.gov.fraud_control` | `{"would_update": 1646}` |
| `L8.gov.litigation` | `{"would_update": 1646}` |
| `L8.industry.demand_supply` | `{"would_update": 1646}` |
| `L8.industry.price_war` | `{"would_update": 1646}` |
| `L8.industry.substitute` | `{"would_update": 1646}` |
| `L8.op.customer_channel` | `{"would_update": 1646}` |
| `L8.op.order_miss` | `{"would_update": 1646}` |
| `L8.op.product_fail` | `{"would_update": 1646}` |
| `L8.reg.license_risk` | `{"would_update": 1646}` |
| `L8.reg.subsidy_off` | `{"would_update": 1646}` |
| `L8.reg.tax_trade` | `{"would_update": 1646}` |
| `L8.reg.tighten` | `{"would_update": 1646}` |
| `L8.shock.crisis` | `{"would_update": 1646}` |
| `L8.shock.supply_break` | `{"would_update": 1646}` |
| `L9.company.ma` | `{"would_update": 1646}` |
| `L9.company.product_order` | `{"would_update": 1646}` |
| `L9.media.short_report` | `{"would_update": 1646}` |

## 2% Sample Correctness

All sampled cells passed status/value/evidence/fingerprint/schema checks.
