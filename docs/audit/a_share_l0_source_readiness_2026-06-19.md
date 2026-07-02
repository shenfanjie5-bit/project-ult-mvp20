# A-share L0/source-readiness audit

- Generated: `2026-06-19T19:47:09+08:00`
- Blocking gaps: `32`
- Direct structured Tushare remaining: `0`
- DOCKCASE `database_all` files: `173115`
- DOCKCASE `market_data` files: `15154`

## Route Counts

| Recommended route | Count |
|---|---:|
| `event_llm_from_runtime_news` | 12 |
| `local_llm_closed_loop` | 16 |
| `manual_design_review` | 4 |

## Blocking Gaps

| dp_id | priority | recommended route | trigger | deps with rows | deps without rows | next step |
|---|---|---|---|---|---|---|
| `L0.compete.new_entrant` | P2_llm_or_web_extraction | `event_llm_from_runtime_news` | event_driven | `L9.industry.compete_risk`, `L9.media.report` | - | use CLS/news/policy runtime rows first; add web crawl only when evidence is absent |
| `L0.compete.price_war` | P2_llm_or_web_extraction | `event_llm_from_runtime_news` | event_driven | `L9.industry.compete_risk`, `L9.media.report` | - | use CLS/news/policy runtime rows first; add web crawl only when evidence is absent |
| `L0.compete.share_concentration` | P2_llm_or_web_extraction | `event_llm_from_runtime_news` | event_driven | `L9.industry.compete_risk`, `L9.media.report` | - | use CLS/news/policy runtime rows first; add web crawl only when evidence is absent |
| `L0.cost.cac` | P2_llm_or_web_extraction | `local_llm_closed_loop` | quarterly_filing | `L5.is.sga_rd`, `L5.is.revenue` | - | use local financial/runtime deps plus annual/IR evidence; no open web required |
| `L0.cost.labor` | P2_llm_or_web_extraction | `local_llm_closed_loop` | quarterly_filing | `L5.is.sga_rd`, `L4.cost.labor` | - | use local financial/runtime deps plus annual/IR evidence; no open web required |
| `L0.cost.rent` | P2_llm_or_web_extraction | `local_llm_closed_loop` | quarterly_filing | `L5.bs.goodwill_ppe`, `L5.cf.capex` | - | use local financial/runtime deps plus annual/IR evidence; no open web required |
| `L0.demand.frequency` | P2_llm_or_web_extraction | `local_llm_closed_loop` | quarterly_filing | `L5.is.revenue`, `L5.is.revenue_growth` | - | use local financial/runtime deps plus annual/IR evidence; no open web required |
| `L0.demand.penetration` | P2_llm_or_web_extraction | `local_llm_closed_loop` | quarterly_filing | `L5.is.revenue`, `L5.is.revenue_growth` | - | use local financial/runtime deps plus annual/IR evidence; no open web required |
| `L0.demand.replacement` | P2_llm_or_web_extraction | `local_llm_closed_loop` | quarterly_filing | `L5.is.revenue` | - | use local financial/runtime deps plus annual/IR evidence; no open web required |
| `L0.demand.terminal` | P2_llm_or_web_extraction | `local_llm_closed_loop` | quarterly_filing | `L5.is.revenue`, `L5.is.revenue_growth` | - | use local financial/runtime deps plus annual/IR evidence; no open web required |
| `L0.demand.user_count` | P2_llm_or_web_extraction | `local_llm_closed_loop` | quarterly_filing | `L5.is.revenue`, `L9.disclosure.qa_recent` | - | use local financial/runtime deps plus annual/IR evidence; no open web required |
| `L0.policy.access_license` | P2_llm_or_web_extraction | `event_llm_from_runtime_news` | event_driven | `L9.industry.policy_change`, `L9.media.report` | - | use CLS/news/policy runtime rows first; add web crawl only when evidence is absent |
| `L0.policy.regulation` | P2_llm_or_web_extraction | `event_llm_from_runtime_news` | event_driven | `L9.industry.policy_change`, `L9.media.report` | - | use CLS/news/policy runtime rows first; add web crawl only when evidence is absent |
| `L0.policy.subsidy` | P2_llm_or_web_extraction | `event_llm_from_runtime_news` | event_driven | `L9.industry.policy_change`, `L9.media.report` | - | use CLS/news/policy runtime rows first; add web crawl only when evidence is absent |
| `L0.policy.tax_trade` | P2_llm_or_web_extraction | `event_llm_from_runtime_news` | event_driven | `L9.industry.policy_change`, `L9.macro.fx` | - | use CLS/news/policy runtime rows first; add web crawl only when evidence is absent |
| `L0.price.contract_spot` | P2_llm_or_web_extraction | `local_llm_closed_loop` | quarterly_filing | `L0.cost.raw_material`, `L5.is.gross_margin` | - | use local financial/runtime deps plus annual/IR evidence; no open web required |
| `L0.price.discount` | P2_llm_or_web_extraction | `local_llm_closed_loop` | quarterly_filing | `L5.is.gross_margin`, `L9.disclosure.qa_recent` | - | use local financial/runtime deps plus annual/IR evidence; no open web required |
| `L0.price.pricing_power` | P2_llm_or_web_extraction | `local_llm_closed_loop` | quarterly_filing | `L5.is.gross_margin` | - | use local financial/runtime deps plus annual/IR evidence; no open web required |
| `L0.price.product_asp` | P2_llm_or_web_extraction | `local_llm_closed_loop` | quarterly_filing | `L5.is.revenue`, `L5.is.gross_margin` | - | use local financial/runtime deps plus annual/IR evidence; no open web required |
| `L0.supply.capacity` | P2_llm_or_web_extraction | `local_llm_closed_loop` | quarterly_filing | `L5.cf.capex`, `L5.bs.goodwill_ppe` | - | use local financial/runtime deps plus annual/IR evidence; no open web required |
| `L0.supply.chain_eff` | P2_llm_or_web_extraction | `local_llm_closed_loop` | quarterly_filing | `L4.eff.turnover`, `L4.eff.cycle` | - | use local financial/runtime deps plus annual/IR evidence; no open web required |
| `L0.supply.channel_service` | P2_llm_or_web_extraction | `local_llm_closed_loop` | quarterly_filing | `L5.is.sga_rd`, `L9.disclosure.qa_recent` | - | use local financial/runtime deps plus annual/IR evidence; no open web required |
| `L0.supply.inventory` | P2_llm_or_web_extraction | `local_llm_closed_loop` | quarterly_filing | `L5.bs.inventory` | - | use local financial/runtime deps plus annual/IR evidence; no open web required |
| `L0.tech.ai_automation` | P2_llm_or_web_extraction | `event_llm_from_runtime_news` | event_driven | `L9.media.report`, `L9.industry.compete_risk` | - | use CLS/news/policy runtime rows first; add web crawl only when evidence is absent |
| `L0.tech.breakthrough` | P2_llm_or_web_extraction | `event_llm_from_runtime_news` | event_driven | `L9.media.report`, `L9.industry.compete_risk` | - | use CLS/news/policy runtime rows first; add web crawl only when evidence is absent |
| `L0.tech.substitute_tech` | P2_llm_or_web_extraction | `event_llm_from_runtime_news` | event_driven | `L9.media.report`, `L9.industry.compete_risk` | - | use CLS/news/policy runtime rows first; add web crawl only when evidence is absent |
| `L8.shock.black_swan` | P2_llm_or_web_extraction | `event_llm_from_runtime_news` | event_driven | `L9.media.report`, `L9.macro.geo` | - | use CLS/news/policy runtime rows first; add web crawl only when evidence is absent |
| `L8.shock.supply_break` | P2_llm_or_web_extraction | `event_llm_from_runtime_news` | event_driven | `L9.media.report`, `L9.industry.compete_risk` | - | use CLS/news/policy runtime rows first; add web crawl only when evidence is absent |
| `L6.mult.dcf` | P3_manual_review | `manual_design_review` | - | - | - | formula/market applicability needs human design before data fill |
| `L6.priced.realization_risk` | P3_manual_review | `manual_design_review` | - | - | - | formula/market applicability needs human design before data fill |
| `L7.reflex.tag` | P3_manual_review | `manual_design_review` | - | - | - | formula/market applicability needs human design before data fill |
| `L8.val.slope_risk_off` | P3_manual_review | `manual_design_review` | - | - | - | formula/market applicability needs human design before data fill |

## Interpretation

- Current evidence still supports the prior conclusion that no P1 direct Tushare/structured collector gaps remain for A-share score completion.
- The main work is now two pipelines: local closed-loop LLM fills for filing-derived L0 economics, and event/news classification from runtime media/policy/competition feeds.
- `L9.media.short_report` remains the clearest web-crawl gap because the generic CLS/media feed does not prove short-report semantics.
- P3 rows are not data-collection problems; they need formula/applicability design before they should affect final scores.
