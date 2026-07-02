# A-share event Unknown strict review packets

- Generated: `2026-06-19T17:56:49+08:00`
- Strict review packets: `8`
- Rows represented: `2`
- Low-confidence community/forum source packets: `2`
- Secondary-newswire packets: `6`
- Requires primary-source confirmation: `2`
- Requires manual review: `0`
- Deterministic rejected: `6`
- Classifier-ready packets: `0`
- Known-draft sufficient packets: `0`
- Approval-ready packets: `0`
- Packet contracts valid: `8`
- Packet contracts invalid: `0`
- Production writes allowed: `0`
- Score mutation: `none; this audit is read-only and does not alter realtime_current`

## Rows

| packet | dp_id | source quality | status | reason | contract | production write |
|---|---|---|---|---|---:|---:|
| `L0.compete.new_entrant#strict_review_candidate#1` | `L0.compete.new_entrant` | `low_confidence_community_source` | `requires_primary_source_confirmation` | `community_or_forum_source_cannot_support_known_value` | yes | no |
| `L0.tech.substitute_tech#strict_review_candidate#1` | `L0.tech.substitute_tech` | `secondary_newswire` | `deterministic_rejected` | `cycle_clearance_or_overcapacity_not_substitute_technology_risk` | yes | no |
| `L0.tech.substitute_tech#strict_review_candidate#2` | `L0.tech.substitute_tech` | `secondary_newswire` | `deterministic_rejected` | `foreign_industry_pressure_without_direct_a_share_substitution_value` | yes | no |
| `L0.tech.substitute_tech#strict_review_candidate#3` | `L0.tech.substitute_tech` | `secondary_newswire` | `deterministic_rejected` | `macro_strategy_or_factor_context_not_substitute_technology_risk` | yes | no |
| `L0.tech.substitute_tech#strict_review_candidate#4` | `L0.tech.substitute_tech` | `secondary_newswire` | `deterministic_rejected` | `false_positive_process_term_not_substitution_risk` | yes | no |
| `L0.tech.substitute_tech#strict_review_candidate#5` | `L0.tech.substitute_tech` | `secondary_newswire` | `deterministic_rejected` | `geopolitical_import_shift_or_demand_opportunity_not_negative_substitute_risk` | yes | no |
| `L0.tech.substitute_tech#strict_review_candidate#6` | `L0.tech.substitute_tech` | `secondary_newswire` | `deterministic_rejected` | `geopolitical_import_shift_or_demand_opportunity_not_negative_substitute_risk` | yes | no |
| `L0.tech.substitute_tech#strict_review_candidate#7` | `L0.tech.substitute_tech` | `low_confidence_community_source` | `requires_primary_source_confirmation` | `community_or_forum_source_cannot_support_known_value` | yes | no |

## Interpretation

- These packets narrow the strict-source review queue; they do not accept evidence.
- Low-confidence community/forum leads require primary-source confirmation before classification.
- Deterministically rejected packets are retained only as negative evidence.
- Classifier-ready, Known-draft-sufficient, approval-ready, runtime writes, and production writes remain zero.
