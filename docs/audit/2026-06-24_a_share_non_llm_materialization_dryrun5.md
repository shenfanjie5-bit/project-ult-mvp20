# A-share non-LLM materialization audit

- Generated: `2026-06-24T01:44:06+08:00`
- Dry run: `True`
- Stocks: `5`
- Target fields: `55`
- Target cells: `275`
- Candidate available: `262`
- Candidate unavailable: `13`
- Schema invalid: `0`
- Overlays written: `0`
- Sample: `6/6` passed

## Actions

| action | count |
|---|---:|
| `would_update` | 262 |
| `skipped` | 13 |

## Skip Reasons

| reason | count |
|---|---:|
| `missing capex or PPE` | 8 |
| `missing L3.region.domestic_overseas runtime value` | 2 |
| `missing forecast revisions and EPS consensus` | 2 |
| `main business text does not directly expose both domestic and overseas business lines` | 1 |

## Field Actions

| dp_id | actions |
|---|---|
| `L1.moat.tags` | `{"would_update": 5}` |
| `L1.model.tag` | `{"would_update": 5}` |
| `L1.position.growth_rank` | `{"would_update": 5}` |
| `L1.position.market_share` | `{"would_update": 5}` |
| `L1.role.tag` | `{"would_update": 5}` |
| `L1.stock_attr.tags` | `{"would_update": 5}` |
| `L2.segment.cash_contrib` | `{"would_update": 5}` |
| `L2.segment.industry_exposure` | `{"would_update": 5}` |
| `L2.segment.opex_ratio` | `{"would_update": 5}` |
| `L2.segment.profit_share` | `{"would_update": 5}` |
| `L3.channel.cost` | `{"would_update": 5}` |
| `L3.channel.efficiency` | `{"would_update": 5}` |
| `L3.channel.mix` | `{"would_update": 5}` |
| `L3.channel.overseas` | `{"skipped": 1, "would_update": 4}` |
| `L3.customer.concentration` | `{"would_update": 5}` |
| `L3.customer.solvency` | `{"would_update": 5}` |
| `L3.delivery.capacity_supply` | `{"skipped": 4, "would_update": 1}` |
| `L3.delivery.fulfillment_cost` | `{"would_update": 5}` |
| `L3.product.margin_mix` | `{"would_update": 5}` |
| `L3.product.portfolio` | `{"would_update": 5}` |
| `L3.region.domestic_overseas` | `{"skipped": 1, "would_update": 4}` |
| `L3.region.fx_geo` | `{"would_update": 5}` |
| `L3.region.tier_mix` | `{"skipped": 1, "would_update": 4}` |
| `L4.cost.cac_production` | `{"would_update": 5}` |
| `L4.cost.rent_energy_logistics` | `{"would_update": 5}` |
| `L4.eff.capacity_utilization` | `{"skipped": 4, "would_update": 1}` |
| `L4.eff.store_labor` | `{"would_update": 5}` |
| `L4.price.asp_aov_arpu` | `{"would_update": 5}` |
| `L4.price.discount` | `{"would_update": 5}` |
| `L4.price.elasticity` | `{"would_update": 5}` |
| `L4.price.pricing_power` | `{"would_update": 5}` |
| `L4.share.market` | `{"would_update": 5}` |
| `L4.share.substitution` | `{"would_update": 5}` |
| `L4.volume.orders` | `{"would_update": 5}` |
| `L4.volume.sales` | `{"would_update": 5}` |
| `L4.volume.shipments` | `{"would_update": 5}` |
| `L4.volume.users` | `{"would_update": 5}` |
| `L5.fcst.beat_probability` | `{"skipped": 2, "would_update": 3}` |
| `L8.gov.fraud_control` | `{"would_update": 5}` |
| `L8.gov.litigation` | `{"would_update": 5}` |
| `L8.industry.demand_supply` | `{"would_update": 5}` |
| `L8.industry.price_war` | `{"would_update": 5}` |
| `L8.industry.substitute` | `{"would_update": 5}` |
| `L8.op.customer_channel` | `{"would_update": 5}` |
| `L8.op.order_miss` | `{"would_update": 5}` |
| `L8.op.product_fail` | `{"would_update": 5}` |
| `L8.reg.license_risk` | `{"would_update": 5}` |
| `L8.reg.subsidy_off` | `{"would_update": 5}` |
| `L8.reg.tax_trade` | `{"would_update": 5}` |
| `L8.reg.tighten` | `{"would_update": 5}` |
| `L8.shock.crisis` | `{"would_update": 5}` |
| `L8.shock.supply_break` | `{"would_update": 5}` |
| `L9.company.ma` | `{"would_update": 5}` |
| `L9.company.product_order` | `{"would_update": 5}` |
| `L9.media.short_report` | `{"would_update": 5}` |

## 2% Sample Correctness

All sampled cells passed status/value/evidence/fingerprint/schema checks.
