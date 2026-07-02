# Single-Stock LLM Decision Architecture

This layer converts Project ULT's stock data into a frozen, source-backed
decision context before any LLM-style reasoning is allowed. The first supported
market is A-share single-stock analysis.

## Contract

1. Build `SingleStockDecisionContext` with `mvp20.llm_context`.
2. Persist immutable context JSON under
   `runtime/llm_contexts/{market}/{ts_code}/{horizon}/{context_id}.json`.
3. Validate a structured decision with `mvp20.llm_decision`.
4. Persist immutable decision JSON under
   `runtime/llm_decisions/{market}/{ts_code}/{horizon}/{decision_id}.json`.
5. Embed an L7 audit record. Local dry-run decisions set
   `llm_lineage.called=false`, so formal replay fields remain null by design.

The LLM is not allowed to browse, infer from memory, or introduce new sources.
It may only cite `evidence_ref` values present in the frozen context.

## Current Runtime Behavior

- `GET /api/project-ult/llm/stock-context` builds the frozen evidence context.
- `POST /api/project-ult/llm/stock-decision` builds or loads a context, returns
  a deterministic dry-run decision when no provider output is supplied, validates
  it, and stores the snapshots.
- `GET /api/project-ult/llm/stock-decision` reads the latest or requested
  decision snapshot.
- `GET /api/project-ult/llm/audit` returns latest snapshot metadata.
- `/api/project-ult/score` includes `llm_decision_summary` as an additive field.

No frontend source is changed in this commit. UI consumers must render
`status != ok` or `validation_result.evidence_gate_passed=false` as an
insufficient conclusion, not as BUY or REDUCE.

## Probability Governance

`signal_5d` is a relative target:

`P(5d return beats same-day liquid-universe median); not absolute P(up)`.

`signal_up_5d` is an absolute target:

`P(5d return > 0)`.

Both current artifacts are stale/unvalidated fallback or shadow diagnostics in
the generated 2026-06-21 audit. They are preserved in the context but cannot be
used as primary decision probabilities until fresh, validated, and non-fallback.

Score fields such as `final_score`, `base_score`, `trading_signal`,
`trading_signal_v2`, `mode_confidence`, RSI, MACD, and heat indicators are not
probabilities.

## Audit Artifacts

Run:

```bash
.venv/bin/python scripts/audit_llm_stock_decision.py --ts-code 000977.SZ --horizon 5d --as-of 2026-06-21
```

This writes:

- `docs/audit/2026-06-21_llm_stock_decision_architecture_audit.json`
- `docs/audit/2026-06-21_llm_stock_context_smoke.json`
- `docs/audit/2026-06-21_llm_decision_validator_audit.json`
