# A-share Unknown acquisition backlog

- Generated: `2026-06-19T13:10:17+08:00`
- Acquisition tasks: `7`
- Event document search tasks: `2`
- Local formula source tasks: `2`
- External/text business source tasks: `3`
- Tasks with existing candidate evidence: `3`
- Tasks with runtime overlay hints: `1`
- Web/external acquisition required: `6`
- LLM allowed tasks: `7`
- Formula inputs ready: `0`
- Auto Known-ready tasks: `0`
- Approval-ready tasks: `0`
- Valid task contracts: `7`
- Invalid task contracts: `0`
- Runtime writes allowed: `0`
- Production writes allowed: `0`
- Source mutations allowed: `0`
- Score mutation: `none; this audit is read-only and does not alter realtime_current`

## Tasks

| task | acquisition track | current evidence | blocking inputs | write allowed |
|---|---|---:|---:|---:|
| `L0.compete.new_entrant` | `dockcase_market_doc_deep_search` | 0 | 2 | no |
| `L0.tech.substitute_tech` | `dockcase_market_doc_deep_search` | 5 | 4 | no |
| `L0.demand.frequency` | `external_or_text_business_metric` | 0 | 3 | no |
| `L0.demand.penetration` | `external_or_text_business_metric` | 0 | 3 | no |
| `L0.demand.replacement` | `external_or_text_business_metric` | 0 | 4 | no |
| `L0.cost.rent` | `local_structured_formula_source` | 1 | 3 | no |
| `L0.price.product_asp` | `local_structured_formula_source` | 4 | 3 | no |

## Interpretation

- The backlog is source acquisition only; no task can write to runtime scoring.
- Event-document tasks must prove direct A-share transmission before a Known packet can be drafted.
- Local structured formula tasks need complete numeric formula inputs, not just supporting columns.
- External/text business-metric tasks need business denominators or cadence/lifecycle evidence before scoring.
