# A-share approval source-sample coverage gate

- Generated: `2026-06-19T23:41:32+08:00`
- Approval packets checked: `25`
- Source-sample supported packets: `25`
- Source samples found: `25`
- Source-sample reviewer packets complete: `25`
- Source payloads match candidates: `25`
- Source-sample review templates valid: `25`
- Approval templates blank/valid: `25`
- Approval inputs ready: `25`
- Approval inputs not ready: `0`
- Runtime writes allowed: `0`
- Production writes allowed: `0`
- Score mutation: `none; approval source-sample coverage is read-only and does not alter realtime_current`

## Coverage Matrix

| dp_id | risk | route | source sample | source template | approval template | approval input |
|---|---|---|---:|---:|---:|---:|
| `L0.cost.cac` | `bulk_structured_review_candidate` | `bulk_review_source_sample` | yes | yes | yes | yes |
| `L0.cost.labor` | `bulk_structured_review_candidate` | `bulk_review_source_sample` | yes | yes | yes | yes |
| `L0.price.pricing_power` | `bulk_structured_review_candidate` | `bulk_review_source_sample` | yes | yes | yes | yes |
| `L0.supply.capacity` | `bulk_structured_review_candidate` | `bulk_review_source_sample` | yes | yes | yes | yes |
| `L0.supply.chain_eff` | `bulk_structured_review_candidate` | `bulk_review_source_sample` | yes | yes | yes | yes |
| `L0.supply.channel_service` | `borderline_structured_text_review_candidate` | `bulk_review_source_sample` | yes | yes | yes | yes |
| `L0.supply.inventory` | `bulk_structured_review_candidate` | `bulk_review_source_sample` | yes | yes | yes | yes |
| `L0.compete.price_war` | `individual_event_evidence_review_required` | `event_approval_source_sample` | yes | yes | yes | yes |
| `L0.compete.share_concentration` | `individual_event_evidence_review_required` | `event_approval_source_sample` | yes | yes | yes | yes |
| `L0.policy.access_license` | `individual_event_evidence_review_required` | `event_approval_source_sample` | yes | yes | yes | yes |
| `L0.policy.regulation` | `individual_event_evidence_review_required` | `event_approval_source_sample` | yes | yes | yes | yes |
| `L0.policy.subsidy` | `individual_event_evidence_review_required` | `event_approval_source_sample` | yes | yes | yes | yes |
| `L0.policy.tax_trade` | `individual_event_evidence_review_required` | `event_approval_source_sample` | yes | yes | yes | yes |
| `L0.tech.ai_automation` | `individual_event_evidence_review_required` | `event_approval_source_sample` | yes | yes | yes | yes |
| `L0.tech.breakthrough` | `individual_event_evidence_review_required` | `event_approval_source_sample` | yes | yes | yes | yes |
| `L0.demand.terminal` | `individual_structured_review_required` | `individual_review_source_sample` | yes | yes | yes | yes |
| `L0.demand.user_count` | `individual_structured_review_required` | `individual_review_source_sample` | yes | yes | yes | yes |
| `L0.price.contract_spot` | `individual_structured_review_required` | `individual_review_source_sample` | yes | yes | yes | yes |
| `L0.price.discount` | `individual_structured_review_required` | `individual_review_source_sample` | yes | yes | yes | yes |
| `L6.mult.dcf` | `individual_policy_review_required` | `individual_review_source_sample` | yes | yes | yes | yes |
| `L6.priced.realization_risk` | `individual_policy_review_required` | `individual_review_source_sample` | yes | yes | yes | yes |
| `L7.reflex.tag` | `individual_policy_review_required` | `individual_review_source_sample` | yes | yes | yes | yes |
| `L8.shock.black_swan` | `individual_policy_review_required` | `individual_review_source_sample` | yes | yes | yes | yes |
| `L8.shock.supply_break` | `individual_policy_review_required` | `individual_review_source_sample` | yes | yes | yes | yes |
| `L8.val.slope_risk_off` | `individual_policy_review_required` | `individual_review_source_sample` | yes | yes | yes | yes |

## Interpretation

- Approval-input ready means the packet has traceable source samples and valid blank templates; it is not an approval.
- Runtime writes remain blocked until a reviewer fills approval records with matching payload hashes and risk acknowledgement.
