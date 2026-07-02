# A-share non-LLM materialization audit

- Generated: `2026-06-24T01:45:16+08:00`
- Dry run: `True`
- Stocks: `1646`
- Target fields: `55`
- Target cells: `90530`
- Candidate available: `86701`
- Candidate unavailable: `3829`
- Schema invalid: `0`
- Overlays written: `0`
- Sample: `1735/1735` passed

## Actions

| action | count |
|---|---:|
| `would_update` | 86701 |
| `skipped` | 3829 |

## Skip Reasons

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
| `L1.position.growth_rank` | `{"skipped": 1, "would_update": 1645}` |
| `L1.position.market_share` | `{"skipped": 1, "would_update": 1645}` |
| `L1.role.tag` | `{"would_update": 1646}` |
| `L1.stock_attr.tags` | `{"would_update": 1646}` |
| `L2.segment.cash_contrib` | `{"skipped": 4, "would_update": 1642}` |
| `L2.segment.industry_exposure` | `{"skipped": 4, "would_update": 1642}` |
| `L2.segment.opex_ratio` | `{"skipped": 2, "would_update": 1644}` |
| `L2.segment.profit_share` | `{"skipped": 75, "would_update": 1571}` |
| `L3.channel.cost` | `{"skipped": 2, "would_update": 1644}` |
| `L3.channel.efficiency` | `{"skipped": 2, "would_update": 1644}` |
| `L3.channel.mix` | `{"would_update": 1646}` |
| `L3.channel.overseas` | `{"skipped": 353, "would_update": 1293}` |
| `L3.customer.concentration` | `{"skipped": 282, "would_update": 1364}` |
| `L3.customer.solvency` | `{"skipped": 93, "would_update": 1553}` |
| `L3.delivery.capacity_supply` | `{"skipped": 775, "would_update": 871}` |
| `L3.delivery.fulfillment_cost` | `{"skipped": 2, "would_update": 1644}` |
| `L3.product.margin_mix` | `{"skipped": 74, "would_update": 1572}` |
| `L3.product.portfolio` | `{"skipped": 44, "would_update": 1602}` |
| `L3.region.domestic_overseas` | `{"skipped": 343, "would_update": 1303}` |
| `L3.region.fx_geo` | `{"would_update": 1646}` |
| `L3.region.tier_mix` | `{"skipped": 353, "would_update": 1293}` |
| `L4.cost.cac_production` | `{"skipped": 2, "would_update": 1644}` |
| `L4.cost.rent_energy_logistics` | `{"skipped": 1, "would_update": 1645}` |
| `L4.eff.capacity_utilization` | `{"skipped": 775, "would_update": 871}` |
| `L4.eff.store_labor` | `{"skipped": 2, "would_update": 1644}` |
| `L4.price.asp_aov_arpu` | `{"skipped": 1, "would_update": 1645}` |
| `L4.price.discount` | `{"skipped": 91, "would_update": 1555}` |
| `L4.price.elasticity` | `{"skipped": 95, "would_update": 1551}` |
| `L4.price.pricing_power` | `{"skipped": 91, "would_update": 1555}` |
| `L4.share.market` | `{"skipped": 1, "would_update": 1645}` |
| `L4.share.substitution` | `{"skipped": 1, "would_update": 1645}` |
| `L4.volume.orders` | `{"skipped": 1, "would_update": 1645}` |
| `L4.volume.sales` | `{"skipped": 1, "would_update": 1645}` |
| `L4.volume.shipments` | `{"skipped": 1, "would_update": 1645}` |
| `L4.volume.users` | `{"skipped": 1, "would_update": 1645}` |
| `L5.fcst.beat_probability` | `{"skipped": 338, "would_update": 1308}` |
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
| `L9.company.product_order` | `{"skipped": 17, "would_update": 1629}` |
| `L9.media.short_report` | `{"would_update": 1646}` |

## 2% Sample Correctness

All sampled cells passed status/value/evidence/fingerprint/schema checks.
