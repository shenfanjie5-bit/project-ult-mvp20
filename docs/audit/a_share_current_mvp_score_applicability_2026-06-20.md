# A-share current-MVP score applicability audit

- Generated: `2026-06-20T03:36:09+08:00`
- Raw final-score closure: `132` / `174` (75.86%)
- Current-MVP final-score closure: `120` / `120` (100.0%)
- Current-MVP actionable gap: `0`
- Current-MVP deviation: `0.0%`
- Excluded from current-MVP denominator: `54`
- Runtime execution status: `executed`
- Post-write verified rows: `11006`
- Score-sink no-final-score-delta fields: `12`
- Score mutation: `none; this audit is read-only and only defines current-MVP applicability`

## Exclusion Reasons

| Reason | Count |
|---|---:|
| `formula_policy_review_required` | 6 |
| `governance_suppression_verified` | 8 |
| `no_valid_target_data_requires_unapproved_generation` | 21 |
| `option_universe_na_verified` | 3 |
| `score_sink_no_effect_verified` | 12 |
| `valuation_peer_context_superseded` | 4 |

## Actionable Gaps

| dp_id | target | reason |
|---|---|---|
| none | none | none |

## Interpretation

- The raw spec denominator is preserved for transparency.
- The current-MVP denominator excludes only fields backed by audit evidence showing an unresolved approval, formula-policy, provider-universe, peer-context-supersession, or verified no-final-score-delta score-sink gate.
- Excluded fields stay in backlog/design scope; they are not counted as completed and are not written as fabricated Known values.
