# A-share event-text market document evidence

- Generated: `2026-06-19T11:01:45+08:00`
- Unknown event-text rows checked: `12`
- Market HTML files scanned: `14956`
- Market HTML read errors: `0`
- Rows with market-doc target evidence: `12`
- Rows with market-doc direct transmission: `12`
- Rows with target and direct transmission in a document: `12`
- Rows with same-sentence target/direct candidates: `11`
- Rows still requiring target evidence: `0`
- Rows still requiring direct transmission link: `1`
- Market-doc review candidates: `11`
- Auto Known candidates allowed: `0`
- Production writes allowed: `0`
- Score mutation: `none; this audit is read-only and does not alter realtime_current`

## Rows

| dp_id | target docs | direct docs | target+direct docs | same-sentence candidates | status | production write |
|---|---:|---:|---:|---:|---|---:|
| `L0.compete.new_entrant` | 20 | 160 | 6 | 0 | `market_docs_require_direct_transmission_link` | no |
| `L0.compete.price_war` | 28 | 165 | 11 | 3 | `market_docs_candidate_requires_review` | no |
| `L0.compete.share_concentration` | 91 | 199 | 47 | 20 | `market_docs_candidate_requires_review` | no |
| `L0.policy.access_license` | 263 | 240 | 89 | 23 | `market_docs_candidate_requires_review` | no |
| `L0.policy.regulation` | 793 | 333 | 191 | 93 | `market_docs_candidate_requires_review` | no |
| `L0.policy.subsidy` | 132 | 184 | 31 | 8 | `market_docs_candidate_requires_review` | no |
| `L0.policy.tax_trade` | 281 | 249 | 104 | 89 | `market_docs_candidate_requires_review` | no |
| `L0.tech.ai_automation` | 1704 | 540 | 469 | 249 | `market_docs_candidate_requires_review` | no |
| `L0.tech.breakthrough` | 618 | 351 | 209 | 95 | `market_docs_candidate_requires_review` | no |
| `L0.tech.substitute_tech` | 178 | 224 | 74 | 34 | `market_docs_candidate_requires_review` | no |
| `L8.shock.black_swan` | 2957 | 333 | 205 | 89 | `market_docs_candidate_requires_review` | no |
| `L8.shock.supply_break` | 140 | 198 | 48 | 14 | `market_docs_candidate_requires_review` | no |

## Interpretation

- Same-sentence candidates are review inputs only, not automatic Known values.
- Direct A-share transmission excludes broad A50/futures-only market context.
- Production score-affecting writes remain disabled.
