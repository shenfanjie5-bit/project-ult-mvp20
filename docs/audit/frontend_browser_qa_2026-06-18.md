# Frontend browser QA

## Follow-up Recheck After Project ULT Route Fixes

- Rechecked at: `2026-06-18T06:50Z`
- Base URL: `http://127.0.0.1:1421`
- BFF URL: `http://127.0.0.1:8701`
- Scope: 18 direct Project ULT route checks with `?data_mode=projectUlt`
- Verification command: Playwright MCP browser navigation, measuring navigation
  commit to first `h1` identity render.
- Static check: `npm run check` in `FrontEnd/` passed after the route fixes.

Result summary:

- Previously blank/crashing direct routes are now visible: `/alerts`,
  `/admin/health`, `/project-ult/cycles`, `/project-ult/graph`, and
  `/project-ult/evidence`.
- Legacy `/graph` now redirects in Project ULT mode to
  `/project-ult/graph?data_mode=projectUlt`, avoiding the heavy demo
  GraphExplorer route.
- Project ULT `/recommend` now renders a lightweight read-only entry at the
  App route layer instead of waiting for the legacy `/api/recommendations/latest`
  mock endpoint.
- `SystemGate` no longer blocks first paint while the initial BFF reachability
  probe is in flight; an explicit backend failure can still show the start
  panel.
- Commit-to-`h1` warm route checks were under 1 second for the audited route
  set. Representative latest samples: `/recommend` 497 ms in full route
  sequence and 82-98 ms in repeated `/pool -> /recommend` checks;
  `/project-ult/graph` 78 ms; `/project-ult/evidence` 75 ms; `/stock/300750.SZ`
  75-114 ms in repeated direct checks.

Important caveat:

- Vite dev-server cold transform and full-document `DOMContentLoaded` samples
  can still produce occasional >1 s outliers immediately after code changes.
  The current browser evidence supports the user-visible warm path, not a
  production build performance budget.

Latest route-level evidence:

| Route | Final route | Latest commit-to-H1 sample | Result |
|---|---|---:|---|
| `/` | `/?data_mode=projectUlt` | 117 ms | pass |
| `/pool` | `/pool?data_mode=projectUlt` | 107 ms | pass |
| `/recommend` | `/recommend?data_mode=projectUlt` | 497 ms | pass |
| `/graph` | `/project-ult/graph?data_mode=projectUlt` | 116 ms | pass |
| `/report` | `/report?data_mode=projectUlt` | 74 ms | pass |
| `/subsystems` | `/subsystems?data_mode=projectUlt` | 75 ms | pass |
| `/audit` | `/audit?data_mode=projectUlt` | 70 ms | pass |
| `/backtest` | `/backtest?data_mode=projectUlt` | 72 ms | pass |
| `/options` | `/options?data_mode=projectUlt` | 73 ms | pass |
| `/alerts` | `/alerts?data_mode=projectUlt` | 71 ms | pass |
| `/admin/health` | `/admin/health?data_mode=projectUlt` | 73 ms | pass |
| `/project-ult/system` | `/project-ult/system?data_mode=projectUlt` | 75 ms | pass |
| `/project-ult/cycles` | `/project-ult/cycles?data_mode=projectUlt` | 72 ms | pass |
| `/project-ult/data` | `/project-ult/data?data_mode=projectUlt` | 73 ms | pass |
| `/project-ult/graph` | `/project-ult/graph?data_mode=projectUlt` | 78 ms | pass |
| `/project-ult/evidence` | `/project-ult/evidence?data_mode=projectUlt` | 75 ms | pass |
| `/stock/300750.SZ` | `/stock/300750.SZ?data_mode=projectUlt` | 75-114 ms repeated direct | pass |
| `/add-stock` | `/add-stock?data_mode=projectUlt` | 72 ms | pass |

- Generated at: `2026-06-18T05:47:26.079Z`
- Collector: `Browser plugin node_repl browser-client`
- Base URL: `http://127.0.0.1:1420`
- BFF URL: `http://127.0.0.1:8701`
- Threshold: `1000 ms`
- Coverage scope: 18 direct route visibility checks, 2 interaction checks, and 1 mobile viewport overflow check
- Console errors / warnings: `0`

## Route Visibility

| Route | Meaningful selector | First | Warm samples | Warm median | Warm max | Result |
|---|---|---:|---:|---:|---:|---|
| Market overview | `h1 has text 工作台` | 452 ms | 370, 328, 599 ms | 370 ms | 599 ms | pass |
| Pool management | `h1 has text 股票池` | 454 ms | 358, 823 ms | 590.5 ms | 823 ms | pass |
| Add stock | `h1 has text 添加股票` | 2371 ms | 718, 194, 203 ms | 203 ms | 718 ms | pass |
| Recommendations | `h1 has text 建议总览` | 199 ms | 256, 165, 153 ms | 165 ms | 256 ms | pass |
| Graph explorer | `h1 has text 图谱中心` | 148 ms | 155, 151, 141 ms | 151 ms | 155 ms | pass |
| Daily report | `h1 has text 日报` | 152 ms | 153, 142, 145 ms | 145 ms | 153 ms | pass |
| Subsystems | `h1 has text 数据源与子系统` | 144 ms | 143, 140, 141 ms | 141 ms | 143 ms | pass |
| Audit replay | `h1 has text 审计回放` | 147 ms | 142, 144, 141 ms | 142 ms | 144 ms | pass |
| Backtest | `h1 has text 回测报告` | fail ms | - ms | - ms | - ms | review |
| Alerts | `h1 has text 实时预警` | fail ms | - ms | - ms | - ms | review |
| Options signals | `h1 has text 期权信号` | 180 ms | 144, 165, 148 ms | 148 ms | 165 ms | pass |
| Admin health | `h1 has text 管理后台` | fail ms | - ms | - ms | - ms | review |
| Project ULT System Map | `h1 has text Project ULT System Map` | fail ms | - ms | - ms | - ms | review |
| Project ULT Cycle / Formal | `h1 has text Project ULT Cycle / Formal` | fail ms | - ms | - ms | - ms | review |
| Project ULT Data Explorer | `h1 has text Project ULT Data Explorer` | fail ms | - ms | - ms | - ms | review |
| Project ULT Graph | `h1 has text 图谱探索` | fail ms | - ms | - ms | - ms | review |
| Project ULT Evidence Console | `h1 has text Project ULT Evidence Console` | fail ms | - ms | - ms | - ms | review |
| Stock detail 300750.SZ | `h1 has text 个股详情 · 宁德时代` | 174 ms | 185, 173, 165 ms | 173 ms | 185 ms | pass |

## Interactions

| Interaction | Target count | Time | Result |
|---|---:|---:|---|
| stock_detail_open_explanation_drawer | 1 | 311 ms | pass |
| sidebar_open_project_ult_data_explorer | 0 | fail ms | review |

## Mobile

| Route | Viewport | Meaningful visible | Horizontal overflow | Result |
|---|---|---:|---|---|
| http://127.0.0.1:1420/stock/300750.SZ?data_mode=projectUlt | 390x844 | 202 ms | no | pass |

## Notes

- Meaningful visible state is h1/page identity visibility, not full downstream data hydration.
- Sidebar navigation and explanation drawer are interaction-level checks.
- Screenshots were captured through Browser for stock-detail drawer and mobile stock-detail states.
