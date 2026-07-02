# Frontend Browser QA 2026-06-19

Production preview QA was run against `http://127.0.0.1:1422` with the BFF on
`http://127.0.0.1:8799/api`.

## Result

| Check | Result |
|---|---:|
| production build | pass |
| routes checked | 4 |
| max navigation-to-h1 | 240 ms |
| max first-h1 wait | 106 ms |
| console error/warn count | 0 |
| framework overlays | 0 |
| horizontal overflow | 0 |
| stock detail explanation drawer | 306 ms |
| stock detail core ready | 945 ms |
| stock detail enriched ready | 1,429 ms |
| mobile stock detail core ready | 875 ms |
| mobile stock detail enriched ready | 1,366 ms |
| mobile stock detail horizontal overflow | 0 |

The first meaningful route identity is under 1 second for `/`, `/pool`,
`/stock/300750.SZ`, and `/add-stock`.

`StockDetail` now stages lower-page work. The production build split the route
chunk from roughly 256.87 kB to 115.96 kB, lazy-loading `PathGraphPanel`
separately. The visible core (header, graph shell, score content) is under the
1 second threshold on desktop and 390px mobile.

## Remaining Risk

The lower-page enriched panels (`aggregate` path graph, technical indicators,
and history sparkline) finish after 1 second by design. They no longer block
the visible core response, but they remain the next optimization target if the
product requirement becomes "all below-fold panels fully hydrated within 1s".
