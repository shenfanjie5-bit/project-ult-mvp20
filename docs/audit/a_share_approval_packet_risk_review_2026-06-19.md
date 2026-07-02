# A-share approval packet risk review

- Generated: `2026-06-19T20:03:51+08:00`
- Packets reviewed: `25`
- Bulk structured-review candidates: `6`
- Borderline structured-text candidates: `1`
- Individual review required: `18`
- Event-evidence individual reviews: `8`
- Structured individual reviews: `4`
- Policy / non-fundamental individual reviews: `6`
- Do-not-approve until contract fixed: `0`
- Auto approvals allowed: `0`
- Runtime writes allowed: `0`
- Production writes allowed: `0`
- Score mutation: `none; this audit is read-only and does not alter realtime_current`

## Risk classes

| risk class | count |
|---|---:|
| `borderline_structured_text_review_candidate` | 1 |
| `bulk_structured_review_candidate` | 6 |
| `individual_event_evidence_review_required` | 8 |
| `individual_policy_review_required` | 6 |
| `individual_structured_review_required` | 4 |

## Packets

| dp_id | target | source | confidence | impact | risk class | reason |
|---|---|---|---:|---:|---|---|
| `L0.supply.channel_service` | `fundamental_score` | `local_structured_text_policy_pilot` | 0.36 | 0.124543 | `borderline_structured_text_review_candidate` | structured-text packet should be sample-checked before approval |
| `L0.cost.cac` | `fundamental_score` | `local_structured_policy_pilot` | 0.36 | 0.022717 | `bulk_structured_review_candidate` | structured/local dependency packet with bounded impact |
| `L0.cost.labor` | `fundamental_score` | `local_structured_policy_pilot` | 0.38 | 0.080821 | `bulk_structured_review_candidate` | structured/local dependency packet with bounded impact |
| `L0.price.pricing_power` | `fundamental_score` | `local_single_dependency_policy_pilot` | 0.42 | 0.076791 | `bulk_structured_review_candidate` | structured/local dependency packet with bounded impact |
| `L0.supply.capacity` | `fundamental_score` | `local_structured_policy_pilot` | 0.34 | 0.063117 | `bulk_structured_review_candidate` | structured/local dependency packet with bounded impact |
| `L0.supply.chain_eff` | `fundamental_score` | `local_structured_policy_pilot` | 0.38 | 0.011778 | `bulk_structured_review_candidate` | structured/local dependency packet with bounded impact |
| `L0.supply.inventory` | `fundamental_score` | `local_single_dependency_policy_pilot` | 0.42 | 0.144172 | `bulk_structured_review_candidate` | structured/local dependency packet with bounded impact |
| `L0.compete.price_war` | `fundamental_score` | `event_text_policy_pilot` | 0.46 | 0.25 | `individual_event_evidence_review_required` | event/text evidence requires source and transmission review; packet depends on local market-document snippets |
| `L0.compete.share_concentration` | `fundamental_score` | `event_text_policy_pilot` | 0.44 | 0.22 | `individual_event_evidence_review_required` | event/text evidence requires source and transmission review; packet depends on local market-document snippets |
| `L0.policy.access_license` | `fundamental_score` | `event_text_policy_pilot` | 0.43 | 0.2 | `individual_event_evidence_review_required` | event/text evidence requires source and transmission review; packet depends on local market-document snippets |
| `L0.policy.regulation` | `fundamental_score` | `event_text_policy_pilot` | 0.41 | 0.12 | `individual_event_evidence_review_required` | event/text evidence requires source and transmission review; packet depends on local market-document snippets |
| `L0.policy.subsidy` | `fundamental_score` | `event_text_policy_pilot` | 0.4 | 0.1 | `individual_event_evidence_review_required` | event/text evidence requires source and transmission review; packet depends on local market-document snippets |
| `L0.policy.tax_trade` | `fundamental_score` | `event_text_policy_pilot` | 0.42 | 0.18 | `individual_event_evidence_review_required` | event/text evidence requires source and transmission review; packet depends on local market-document snippets |
| `L0.tech.ai_automation` | `fundamental_score` | `event_text_policy_pilot` | 0.45 | 0.28 | `individual_event_evidence_review_required` | event/text evidence requires source and transmission review; packet depends on local market-document snippets |
| `L0.tech.breakthrough` | `fundamental_score` | `event_text_policy_pilot` | 0.44 | 0.24 | `individual_event_evidence_review_required` | event/text evidence requires source and transmission review; packet depends on local market-document snippets |
| `L6.priced.realization_risk` | `priced_in_discount` | `manual_policy_pilot` | 0.45 | 0.250584 | `individual_policy_review_required` | non-fundamental score target: priced_in_discount; manual-policy payload requires explicit policy review; high score impact 0.250584 |
| `L7.reflex.tag` | `reflexivity_multiplier` | `manual_policy_pilot` | 0.4 | 0.008829 | `individual_policy_review_required` | non-fundamental score target: reflexivity_multiplier; manual-policy payload requires explicit policy review |
| `L8.shock.black_swan` | `risk_discount` | `event_text_policy_pilot` | 0.48 | 0.55 | `individual_policy_review_required` | non-fundamental score target: risk_discount; high score impact 0.55 |
| `L8.shock.supply_break` | `risk_discount` | `event_text_policy_pilot` | 0.47 | 0.45 | `individual_policy_review_required` | non-fundamental score target: risk_discount; high score impact 0.45 |
| `L8.val.slope_risk_off` | `risk_discount` | `manual_policy_pilot` | 0.45 | 0.235192 | `individual_policy_review_required` | non-fundamental score target: risk_discount; manual-policy payload requires explicit policy review |
| `L6.mult.dcf` | `valuation_rerating` | `manual_policy_pilot` | 0.32 | 0.677314 | `individual_policy_review_required` | non-fundamental score target: valuation_rerating; manual-policy payload requires explicit policy review; high score impact 0.677314 |
| `L0.demand.terminal` | `fundamental_score` | `local_structured_policy_pilot` | 0.34 | 0.204771 | `individual_structured_review_required` | structured proxy semantics require individual review |
| `L0.demand.user_count` | `fundamental_score` | `local_structured_text_policy_pilot` | 0.37 | 0.245 | `individual_structured_review_required` | structured proxy semantics require individual review |
| `L0.price.contract_spot` | `fundamental_score` | `local_structured_policy_pilot` | 0.32 | 0.063964 | `individual_structured_review_required` | structured proxy semantics require individual review |
| `L0.price.discount` | `fundamental_score` | `local_structured_text_policy_pilot` | 0.38 | 0.196519 | `individual_structured_review_required` | structured proxy semantics require individual review |

## Interpretation

- This report prioritizes review work; it is not an approval list.
- Bulk structured-review candidates still require reviewer identity, timestamp, matching payload hash, and risk acknowledgement before runtime write.
- Borderline structured-text candidates should receive source-text sample checks before any batch approval.
- Event/text, manual-policy, and non-fundamental score-target packets remain individual-review items.
- The report does not write runtime values or change scores.
