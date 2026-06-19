# A-share external business-metric value-selection gate

- Generated: `2026-06-19T20:23:51+08:00`
- Business-metric rows: `3`
- Value-review packets: `6`
- Candidate value options: `8`
- Bridge-probe-ready options: `8`
- Review value-selection required: `0`
- Review value-policy draft ready: `1`
- Value-policy draft ready: `1`
- Source metric missing: `2`
- Auto-selectable values: `0`
- Proposed value JSONs: `1`
- Selected value JSONs: `0`
- Known-draft sufficient: `0`
- Approval-ready rows: `0`
- Production writes allowed: `0`
- Score mutation: `none; this audit is read-only and does not alter realtime_current`

## Rows

| dp_id | status | packets | options | bridge-ready options | value-policy draft ready | missing before Known |
|---|---|---:|---:|---:|---:|---|
| L0.demand.frequency | source_metric_missing | 0 | 0 | 0 | 0 | order count, transaction count, shipment frequency, or usage cadence, active customer or user denominator when cadence is normalized, reviewed decomposition separating cadence from ASP and revenue growth |
| L0.demand.penetration | review_value_policy_draft_ready | 6 | 8 | 8 | 1 | approval_record, issuer_or_industry_applicability_review, reviewed_bounds, reviewed_formula_policy, reviewed_numeric_value_selection |
| L0.demand.replacement | source_metric_missing | 0 | 0 | 0 | 0 | product lifecycle or launch/refresh cadence, installed base, fleet size, or active-device/customer stock, replacement cycle months/years or renewal trend, shipment, order, user, or channel evidence that separates replacement from new demand |

## Interpretation

- Value candidates that still carry `review_required=true`, low confidence, missing reviewed bounds, or missing formula policy cannot become Known drafts automatically.
- Value-policy-draft-ready rows have a reviewer-facing proposed value JSON and a bridge-ready payload, but they still require explicit review before Known draft creation.
- Bridge-probe-ready means the candidate value shape can reach a final-score target if later reviewed; it does not prove the value is valid information.
- This audit creates no approval records and allows no production writes.
