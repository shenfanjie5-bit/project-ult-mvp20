# A-share Unknown closure matrix

- Generated: `2026-06-19T12:52:51+08:00`
- Unknown closure rows: `7`
- Closure routes assigned: `7`
- Missing closure routes: `0`
- Review-ready concrete rows: `27`
- Review-gated Unknown rows: `7`
- Approval-ready concrete packets: `27`
- Auto Known-ready rows: `0`
- Approval-ready Unknown rows: `0`
- Event evidence gaps: `2`
- Local structured formula reviews: `2`
- External/text business sources required: `3`
- Rows with source candidates: `3`
- Formula inputs ready: `0`
- Contract valid rows: `7`
- Contract invalid rows: `0`
- Runtime writes allowed: `0`
- Production writes allowed: `0`
- Score mutation: `none; this audit is read-only and does not alter realtime_current`

## Rows

| dp_id | blocker class | current evidence | auto Known | next action bucket |
|---|---|---|---:|---|
| `L0.demand.frequency` | `external_business_source_required` | external_source_required, columns=0, missing_inputs=3 | no | `local_structured_mapping_required` |
| `L0.demand.penetration` | `external_business_source_required` | external_source_required, columns=0, missing_inputs=3 | no | `local_structured_mapping_required` |
| `L0.demand.replacement` | `lifecycle_source_and_policy_required` | requires_lifecycle_or_replacement_cycle_source, runtime_dep=True | no | `single_dependency_policy_required` |
| `L0.cost.rent` | `formula_policy_required` | review_candidate_ready, columns=1, missing_inputs=3 | no | `local_structured_mapping_required` |
| `L0.price.product_asp` | `quantity_or_price_index_source_required` | supporting_candidate_needs_quantity_source, columns=4, missing_inputs=3 | no | `local_structured_mapping_required` |
| `L0.compete.new_entrant` | `direct_event_transmission_evidence_required` | requires_direct_transmission_link, examples=0 | no | `event_text_classification_required` |
| `L0.tech.substitute_tech` | `clean_substitution_risk_evidence_required` | market_doc_review_ready, examples=5 | no | `event_text_classification_required` |

## Interpretation

- None of the remaining Unknown rows is auto Known-ready or approval-ready.
- `L0.cost.rent` and `L0.price.product_asp` have local structured source candidates, but neither has complete formula inputs.
- `L0.compete.new_entrant` and `L0.tech.substitute_tech` remain event-evidence problems, not approval problems.
- `L0.demand.frequency`, `L0.demand.penetration`, and `L0.demand.replacement` need external or text-derived business metrics before a value can be scored.
