# Single-Stock LLM Decision API

All endpoints return the existing mvp20 envelope: `{ "data": ..., "request_id": ... }`.

## Build Context

```http
GET /api/project-ult/llm/stock-context?ts_code=000977.SZ&horizon=5d&market=A_share&dry_run=1
```

Query parameters:

- `ts_code`: required, same allowlist as other stock routes.
- `horizon`: default `5d`; supported values are `5d`, `10d`, `30d`, `3m`,
  `6m`, `180d`, `1y`, `2y`.
- `market`: currently only A-share is supported for a full context.
- `dry_run`: default `true`.
- `persist`: default is `false` when `dry_run=true`; set `persist=1` to write
  `runtime/llm_contexts/...`.
- `include_raw`, `include_unusable`, `max_evidence`, `industry_id`, `as_of`.

Unsupported markets return status `unsupported` inside `data` with no context
instead of pretending to make a decision.

## Create Decision

```http
POST /api/project-ult/llm/stock-decision
Content-Type: application/json

{
  "ts_code": "000977.SZ",
  "horizon": "5d",
  "market": "A_share",
  "dry_run": true,
  "max_evidence": 80
}
```

The local path is deterministic and does not call an LLM provider. Without a
valid external `decision_output`, it returns an inconclusive decision when the
primary evidence gates fail. The result includes `validation_result`,
`provider_status`, and runtime storage paths.

To validate a previously frozen context:

```json
{
  "ts_code": "000977.SZ",
  "horizon": "5d",
  "market": "A_share",
  "context_id": "ctx_...",
  "context_hash": "sha256:...",
  "decision_output": { "...": "structured decision output" }
}
```

Invalid structured output returns HTTP 422 and is not persisted.

## Read Decision

```http
GET /api/project-ult/llm/stock-decision?ts_code=000977.SZ&horizon=5d
```

Add `decision_id=dec_...` to read a specific snapshot. Missing snapshots return
`available=false`.

## Audit

```http
GET /api/project-ult/llm/audit?ts_code=000977.SZ&horizon=5d
```

Returns the latest context, latest decision, summary, and snapshot counts.

## Score Embedding

```http
GET /api/project-ult/score?ts_code=000977.SZ
```

The response includes `llm_decision_summary`. This field is appended after the
existing score cache is read, so decision snapshots do not leak through cached
score payloads.
