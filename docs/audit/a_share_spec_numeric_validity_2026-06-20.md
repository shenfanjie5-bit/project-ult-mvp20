# A-share spec numeric-validity audit

- Generated: `2026-06-20T02:18:54+08:00`
- Score mutation: `none; this audit is read-only and does not alter realtime_current`
- Spec total config/runtime: `256` / `256`
- Spec total matches runtime: `True`
- Current numeric final-score fields: `132` / `174` (`75.86%`)
- Score-relevant fields not currently in final score: `42`
- Actionable blocking gaps: `21`
- Candidate dry-run bridge-ready fields: `32`
- Review-ready concrete final-score packets: `25`
- Review-gated Unknown packets: `7`
- Approved runtime writes: `0`
- Safe to upsert without review: `0`

## Current Chain Status

| Status | Count |
|---|---:|
| `current_numeric_final_score` | 132 |
| `no_valid_current_a_share_target_data` | 7 |
| `non_score_relevant` | 82 |
| `overlay_information_not_score_candidate` | 17 |
| `valid_runtime_information_formula_unmapped` | 18 |

## Candidate Gate Status

| Status | Count |
|---|---:|
| `none` | 224 |
| `review_gated_unknown` | 7 |
| `review_ready_concrete_approval_missing` | 25 |

## Review-gated Unknown Rows

| dp_id | target | current chain | next action |
|---|---|---|---|
| `L0.compete.new_entrant` | `fundamental_score` | `overlay_information_not_score_candidate` | `event_text_classification_required` |
| `L0.cost.rent` | `fundamental_score` | `overlay_information_not_score_candidate` | `local_structured_mapping_required` |
| `L0.demand.frequency` | `fundamental_score` | `overlay_information_not_score_candidate` | `local_structured_mapping_required` |
| `L0.demand.penetration` | `fundamental_score` | `overlay_information_not_score_candidate` | `local_structured_mapping_required` |
| `L0.demand.replacement` | `fundamental_score` | `overlay_information_not_score_candidate` | `single_dependency_policy_required` |
| `L0.price.product_asp` | `fundamental_score` | `overlay_information_not_score_candidate` | `local_structured_mapping_required` |
| `L0.tech.substitute_tech` | `fundamental_score` | `overlay_information_not_score_candidate` | `event_text_classification_required` |

## Interpretation

- `current_numeric_final_score` is the only state counted as already reaching the current production final-score path.
- Candidate dry-run bridge readiness proves the payload shape can become a numeric realtime node; it does not prove the business value is correct.
- Review-ready concrete packets are still gated because approval records are missing and runtime writes remain disabled.
- Review-gated Unknown packets still lack source evidence, formula policy, or mapping required to produce a bounded value.
