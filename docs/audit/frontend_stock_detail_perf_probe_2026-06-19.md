# Frontend StockDetail performance probe

- Generated: `2026-06-19T21:12:04+0800`
- Scope: local production-preview browser probe after the StockDetail request-ordering and BFF derived-response cache changes.
- Route: `/stock/300750.SZ?data_mode=projectUlt`
- Threshold: `1000 ms`

## Result

| signal | observed |
|---|---:|
| H1 ready | `173 ms` |
| Coverage response | `710 ms` |
| Score response | `836 ms` |
| Path graph canvas ready | `965 ms` |
| Console error/warn count | `0` |

## Change Verified

`StockDetail` lets score and coverage settle before starting non-core overlay,
realtime stream, aggregate, technicals, and history requests. The path graph
canvas does not wait for aggregate; it renders from score first and enriches
node totals when aggregate arrives. The BFF also caches short-lived derived
responses keyed by source file and hot DB fingerprints.

## Remaining Risk

This is one local production-preview browser sample, not a full cold-start or
multi-device benchmark. History and stock overlay still arrived just after 1
second in this sample, but they no longer block route identity or the path
graph canvas.
