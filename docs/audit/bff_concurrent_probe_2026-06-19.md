# BFF concurrent probe

- Generated: `2026-06-19T21:12:04+0800`
- Scope: local BFF concurrent probe for StockDetail hot endpoints after the derived-response cache.
- Threshold: `1000 ms`

## Result

| signal | observed |
|---|---:|
| Endpoints | `8` |
| All HTTP 200 | `yes` |
| All under threshold | `yes` |
| Max endpoint latency | `276.407 ms` |
| Slowest endpoint | `/api/project-ult/aggregate?ts_code=300750.SZ&industry_id=STORAGE_GRID` |

The probe warmed profiles, industry graph, score, and coverage once before
issuing the concurrent batch. It validates the warm-path behavior the frontend
uses after route identity and core score/coverage are available.

## Remaining Risk

This is a local warm probe, not a WAN or cold-start benchmark. The cache TTL is
intentionally short and invalidates on source file and hot DB fingerprints.
