# A-share event-text classification inputs

- Generated: `2026-06-19T08:39:30+08:00`
- Classification input packets: `12`
- Input-ready packets: `12`
- Missing headline input: `0`
- Headline inputs: `78`
- Unique headlines: `8`
- Full article text available: `0`
- Title-level only packets: `12`
- Classified Known packets: `0`
- Production writes allowed: `0`
- Score mutation: `none; this audit is read-only and does not alter realtime_current`

## Rows

| dp_id | target | status | headline inputs | unique titles | full text |
|---|---|---|---:|---:|---:|
| `L0.compete.new_entrant` | `fundamental_score` | `classification_input_ready` | 7 | 6 | no |
| `L0.compete.price_war` | `fundamental_score` | `classification_input_ready` | 7 | 6 | no |
| `L0.compete.share_concentration` | `fundamental_score` | `classification_input_ready` | 7 | 6 | no |
| `L0.policy.access_license` | `fundamental_score` | `classification_input_ready` | 6 | 6 | no |
| `L0.policy.regulation` | `fundamental_score` | `classification_input_ready` | 6 | 6 | no |
| `L0.policy.subsidy` | `fundamental_score` | `classification_input_ready` | 6 | 6 | no |
| `L0.policy.tax_trade` | `fundamental_score` | `classification_input_ready` | 1 | 1 | no |
| `L0.tech.ai_automation` | `fundamental_score` | `classification_input_ready` | 7 | 6 | no |
| `L0.tech.breakthrough` | `fundamental_score` | `classification_input_ready` | 7 | 6 | no |
| `L0.tech.substitute_tech` | `fundamental_score` | `classification_input_ready` | 7 | 6 | no |
| `L8.shock.black_swan` | `risk_discount` | `classification_input_ready` | 10 | 8 | no |
| `L8.shock.supply_break` | `risk_discount` | `classification_input_ready` | 7 | 6 | no |

## Interpretation

- These are classification inputs, not classified Known values.
- Current evidence is title-level; full article text is not present in these packets.
- The classifier/reviewer must still decide concept, direction, magnitude, and A-share transmission before any Known review packet can be emitted.
