# LLM Evidence Contract

Every decision claim must cite frozen `evidence_ref` values. The validator
rejects claims that cite unknown evidence or use stale, unverified, unavailable,
mock, proxy, unknown, inactive, or not-applicable rows as supporting evidence.

## Evidence Status

- `Known` + fresh + verified + available can support claims.
- `Mock` is rejected and blocked.
- `Unknown` is blocked.
- `Proxy` is diagnostic only.
- `N/A` and `Inactive` are context only, not negative evidence.
- Stale or expired evidence is diagnostic only.
- Unverified or review-required evidence is diagnostic only unless explicitly
  used as a data-quality caveat.

The context preserves `_origin_ts_code` so sentinel or market-level rows remain
auditable when they are copied into a stock context.

## Probability Rules

Valid primary probability estimates must be:

- present in `context.model_probabilities`;
- linked to an evidence item in `context.evidence_pack`;
- fresh;
- validated;
- non-fallback;
- non-shadow;
- explicit about `target_kind`, `probability_semantics`, and `horizon_days`.

`signal_5d` is not absolute upside. It can only represent the relative
cross-sectional target unless a future artifact explicitly changes target kind.

`signal_up_5d` is the absolute-up target, but the current artifact is still
diagnostic because it is stale/unvalidated fallback or shadow evidence.

The validator rejects attempts to treat `final_score`, `base_score`,
`company_score`, `trading_signal`, `mode_confidence`, technical indicators, or
heat scores as probabilities.

## Closed-Loop Boundary

The reasoner may not introduce external URLs or unsupported facts. URLs in
claims or thesis are only allowed when already present in the frozen source
packets or evidence rows. This keeps replay and audit tied to local snapshots
rather than model memory.
