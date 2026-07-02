# A-share non-LLM materialization audit

- Generated: `2026-06-24T01:59:58+08:00`
- Dry run: `False`
- Stocks: `1646`
- Target fields: `55`
- Target cells: `90530`
- Candidate available: `86701`
- Candidate unavailable: `3829`
- Write unavailable: `True`
- Schema invalid: `0`
- Overlays written: `1646`
- Sample: `1811/1811` passed

## Actions

| action | count |
|---|---:|
| `updated` | 90530 |

## Skip Reasons

None.

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
| `L1.moat.tags` | `{"updated": 1646}` |
| `L1.model.tag` | `{"updated": 1646}` |
| `L1.position.growth_rank` | `{"updated": 1646}` |
| `L1.position.market_share` | `{"updated": 1646}` |
| `L1.role.tag` | `{"updated": 1646}` |
| `L1.stock_attr.tags` | `{"updated": 1646}` |
| `L2.segment.cash_contrib` | `{"updated": 1646}` |
| `L2.segment.industry_exposure` | `{"updated": 1646}` |
| `L2.segment.opex_ratio` | `{"updated": 1646}` |
| `L2.segment.profit_share` | `{"updated": 1646}` |
| `L3.channel.cost` | `{"updated": 1646}` |
| `L3.channel.efficiency` | `{"updated": 1646}` |
| `L3.channel.mix` | `{"updated": 1646}` |
| `L3.channel.overseas` | `{"updated": 1646}` |
| `L3.customer.concentration` | `{"updated": 1646}` |
| `L3.customer.solvency` | `{"updated": 1646}` |
| `L3.delivery.capacity_supply` | `{"updated": 1646}` |
| `L3.delivery.fulfillment_cost` | `{"updated": 1646}` |
| `L3.product.margin_mix` | `{"updated": 1646}` |
| `L3.product.portfolio` | `{"updated": 1646}` |
| `L3.region.domestic_overseas` | `{"updated": 1646}` |
| `L3.region.fx_geo` | `{"updated": 1646}` |
| `L3.region.tier_mix` | `{"updated": 1646}` |
| `L4.cost.cac_production` | `{"updated": 1646}` |
| `L4.cost.rent_energy_logistics` | `{"updated": 1646}` |
| `L4.eff.capacity_utilization` | `{"updated": 1646}` |
| `L4.eff.store_labor` | `{"updated": 1646}` |
| `L4.price.asp_aov_arpu` | `{"updated": 1646}` |
| `L4.price.discount` | `{"updated": 1646}` |
| `L4.price.elasticity` | `{"updated": 1646}` |
| `L4.price.pricing_power` | `{"updated": 1646}` |
| `L4.share.market` | `{"updated": 1646}` |
| `L4.share.substitution` | `{"updated": 1646}` |
| `L4.volume.orders` | `{"updated": 1646}` |
| `L4.volume.sales` | `{"updated": 1646}` |
| `L4.volume.shipments` | `{"updated": 1646}` |
| `L4.volume.users` | `{"updated": 1646}` |
| `L5.fcst.beat_probability` | `{"updated": 1646}` |
| `L8.gov.fraud_control` | `{"updated": 1646}` |
| `L8.gov.litigation` | `{"updated": 1646}` |
| `L8.industry.demand_supply` | `{"updated": 1646}` |
| `L8.industry.price_war` | `{"updated": 1646}` |
| `L8.industry.substitute` | `{"updated": 1646}` |
| `L8.op.customer_channel` | `{"updated": 1646}` |
| `L8.op.order_miss` | `{"updated": 1646}` |
| `L8.op.product_fail` | `{"updated": 1646}` |
| `L8.reg.license_risk` | `{"updated": 1646}` |
| `L8.reg.subsidy_off` | `{"updated": 1646}` |
| `L8.reg.tax_trade` | `{"updated": 1646}` |
| `L8.reg.tighten` | `{"updated": 1646}` |
| `L8.shock.crisis` | `{"updated": 1646}` |
| `L8.shock.supply_break` | `{"updated": 1646}` |
| `L9.company.ma` | `{"updated": 1646}` |
| `L9.company.product_order` | `{"updated": 1646}` |
| `L9.media.short_report` | `{"updated": 1646}` |

## 2% Sample Correctness

All sampled cells passed status/value/evidence/fingerprint/schema checks.
