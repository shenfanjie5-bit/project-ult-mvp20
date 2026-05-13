# Holdings Queue/Freeze Rollout Evidence Template

This runbook records only sanitized queue/freeze evidence for a bounded
holdings production rollout. It is an operational checks template, not a
broad/default rollout declaration.

Do not paste proof-only database names, DSNs, tokens, raw provider payloads,
runtime artifacts, parquet paths, manifest paths, dbt logs, stdout/stderr,
exitcode files, `.env` values, local runtime paths, or full producer payloads.

## Scope State

Landed and required for holdings queue/freeze evidence:

- idempotent-required Ex-3 submission through `submit_candidate_idempotent`
- safe receipt recording through `CandidateSubmitReceipt.as_public_dict()`
- worker rejection metrics: `rejection_counts` and
  `rejections_by_reason_type`
- targeted freeze filters: `submitted_by="subsystem-holdings"` and
  `payload_type="Ex-3"`

This does not enable broad/default freeze rollout, full propagation, financial
document scope, new contracts subtypes, or any default producer migration.

## Preflight Operational Checks

Before recording evidence:

- confirm the rollout is bounded to a named cycle and the holdings producer
  identity `subsystem-holdings`
- confirm Ex-3 candidate producers use `submit_candidate_idempotent`; bare
  `submit_candidate` is not acceptable for holdings rollout evidence
- confirm duplicate Ex-3 `delta_id` submissions replay the existing row and
  return `replayed=true` instead of inserting another candidate
- confirm the worker command uses `--once` and a bounded `--limit`
- confirm freeze calls include both targeted filters:
  `submitted_by="subsystem-holdings"` and `payload_type="Ex-3"`
- confirm evidence stores parsed counts and sanitized receipts only

Safe status-count query shape:

```sql
SELECT validation_status, count(*) AS row_count
FROM data_platform.candidate_queue
WHERE submitted_by = 'subsystem-holdings'
  AND payload_type = 'Ex-3'
GROUP BY validation_status
ORDER BY validation_status;
```

Record the result as bounded counts only.

## Idempotent Submit Requirement

Holdings rollout evidence must use the idempotent submit path:

```python
from data_platform.queue import submit_candidate_idempotent

receipt = submit_candidate_idempotent(holdings_ex3_envelope)
public_receipt = receipt.as_public_dict()
```

The runbook may record `public_receipt` fields only. Do not record
`holdings_ex3_envelope`, provider payload fragments, source row values, local
paths, or runtime artifacts.

## Worker Command Shape

Use redacted placeholders and bounded counts:

```bash
DP_PG_DSN=<redacted-dsn> \
PYTHONPATH=src:../contracts/src \
python -m data_platform.queue.worker --once --limit <bounded-limit>
```

Record the parsed summary, not raw stdout/stderr:

```json
{
  "scanned": 42,
  "accepted": 40,
  "rejected": 2,
  "duration_ms": 1234,
  "rejection_counts": {
    "<sanitized rejection reason>": 2
  },
  "rejections_by_reason_type": {
    "CandidateValidationError": 2
  }
}
```

Operational checks:

- `scanned == accepted + rejected`
- `rejection_counts` is present even when empty
- `rejections_by_reason_type` is present even when empty
- any non-zero `rejected` count has a sanitized reason summary and an
  operator decision: retry after producer fix, accept the bounded rejection,
  or block the rollout

## Targeted Freeze Shape

Holdings production evidence must use a targeted freeze:

```python
freeze_cycle_candidates(
    "CYCLE_<YYYYMMDD>",
    submitted_by="subsystem-holdings",
    payload_type="Ex-3",
)
```

For holdings production evidence, a freeze without both filters is invalid.
Unfiltered freeze calls may remain useful in isolated tests or smoke fixtures,
but they are not acceptable as rollout evidence and do not imply broad/default
rollout.

Record only selected count and cutoff metadata from the returned cycle
metadata.

## Receipt Shape

Record idempotent submit receipts in this shape only:

```json
{
  "candidate_id": 123,
  "payload_type": "Ex-3",
  "submitted_by": "subsystem-holdings",
  "submitted_at": "<iso8601>",
  "ingest_seq": 456,
  "validation_status": "pending",
  "rejection_reason": null,
  "replayed": false
}
```

Receipt evidence must not include `payload`, provider response fields, local
paths, DSNs, tokens, raw dbt output, or runtime artifact paths.

## Evidence Fields

Record:

- cycle id and rollout date
- command shape with redacted placeholders
- idempotent submit receipt count and replay count
- worker `scanned`, `accepted`, `rejected`, `rejection_counts`, and
  `rejections_by_reason_type`
- targeted freeze filters: `submitted_by=subsystem-holdings`,
  `payload_type=Ex-3`
- selected count and cutoff metadata
- code commit hash
- sanitized receipt hash or count, never raw payload
- explicit statement that the evidence is bounded holdings rollout support,
  not broad/default rollout

## Blocker Recording

If a safety gate blocks live execution, record only the blocker code, command
shape, status, and relevant counts. Do not run a destructive smoke path without
its explicit safety gate.

Block the rollout when:

- idempotent submit is bypassed for holdings Ex-3 candidates
- receipts contain producer payloads, provider fields, DSNs, tokens, paths, or
  runtime artifacts
- worker rejection metrics are missing from the evidence
- targeted freeze filters are missing
- selected count or cutoff metadata cannot be reconciled with the bounded
  queue counts
