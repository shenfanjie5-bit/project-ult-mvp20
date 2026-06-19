# A-share event-text preclassification screen

- Generated: `2026-06-19T08:49:25+08:00`
- Preclassification packets: `12`
- Packets screened: `12`
- Title-level only packets: `12`
- Target keyword-hit packets: `3`
- A-share transmission keyword-hit packets: `11`
- Target + transmission keyword-hit packets: `2`
- Direct Known candidates allowed: `0`
- Production writes allowed: `0`
- Score mutation: `none; this audit is read-only and does not alter realtime_current`

## Rows

| dp_id | target | screen status | target hits | A-share hits | matched headlines |
|---|---|---|---:|---:|---:|
| `L0.compete.new_entrant` | `fundamental_score` | `screened_no_target_keyword_hit` | 0 | 3 | 1 |
| `L0.compete.price_war` | `fundamental_score` | `screened_no_target_keyword_hit` | 0 | 3 | 1 |
| `L0.compete.share_concentration` | `fundamental_score` | `screened_no_target_keyword_hit` | 0 | 3 | 1 |
| `L0.policy.access_license` | `fundamental_score` | `screened_no_target_keyword_hit` | 0 | 3 | 1 |
| `L0.policy.regulation` | `fundamental_score` | `screened_target_and_transmission_keyword_hit_requires_review` | 1 | 3 | 2 |
| `L0.policy.subsidy` | `fundamental_score` | `screened_no_target_keyword_hit` | 0 | 3 | 1 |
| `L0.policy.tax_trade` | `fundamental_score` | `screened_target_keyword_hit_without_a_share_transmission` | 1 | 0 | 1 |
| `L0.tech.ai_automation` | `fundamental_score` | `screened_no_target_keyword_hit` | 0 | 3 | 1 |
| `L0.tech.breakthrough` | `fundamental_score` | `screened_no_target_keyword_hit` | 0 | 3 | 1 |
| `L0.tech.substitute_tech` | `fundamental_score` | `screened_no_target_keyword_hit` | 0 | 3 | 1 |
| `L8.shock.black_swan` | `risk_discount` | `screened_target_and_transmission_keyword_hit_requires_review` | 6 | 3 | 6 |
| `L8.shock.supply_break` | `risk_discount` | `screened_no_target_keyword_hit` | 0 | 3 | 1 |

## Interpretation

- This is a deterministic screen, not a classifier.
- Keyword hits are title-level hints and do not prove event concept, direction, magnitude, or A-share transmission.
- All packets remain `Unknown`, `review_required`, and blocked from runtime or production writes.
