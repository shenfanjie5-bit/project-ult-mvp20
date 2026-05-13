# MVP Runbook

## Scope

The MVP uses a 13-industry decision universe with a 120-month history window
and a two-hop graph context. Every `graph_status: present` industry owns at
least one constituent stock; pending industries may temporarily have no
constituent. A stock may belong to up to three industries (e.g. 胜宏科技-H
spans AI compute hardware / semi packaging / consumer electronics). Each
constituent carries a `role` field — `target` for Chinese leaders that the
MVP scores, `customer` for upstream capex drivers (Meta / MSFT / GOOGL /
AMZN), and `both` for entities that play both roles in different industries
(TSLA, AAPL). A separate `pool` field labels each constituent as `regular`
(the full leader pool) or `core` (the hand-curated subset destined for
deep-dive LLM analysis); the default is `regular` until an operator promotes
specific tickers.

## Operator Gates

1. Confirm `config/mvp20.industries.yaml` declares the 13 industry slugs the
   MVP cares about, with `graph_status` set per industry (present or
   pending).
2. Fill `config/mvp20.universe.yaml` with real constituent `ts_code` values
   (A-share `<NNNNNN>.SH|SZ|BJ`, Hong Kong `<NNNN[N]>.HK`, or US-listed
   `<SYMBOL>.US` including Berkshire-style `<SYM>.<CLASS>.US`). Every
   `present` industry must keep at least one constituent; `pending`
   industries may stay empty until the matching graph YAML is added.
3. Each industry with `graph_status: present` must own a causal graph YAML
   at `config/industry_graphs/<slug>.yaml`, structured per the v3.1 16-section
   template plus shared nodes / edges / four-view filters.
   See `docs/industry_graphs/FOUR_VIEWS_DESIGN.md` for the design and the
   Meta Capex → NVDA walk-through.
4. Run `mvp20 validate-manifest`.
5. Run `mvp20 validate-graphs` to enforce per-industry graph schema, the
   four required views, valuation weights summing to 100%, state
   probabilities summing to 100%, cross-graph node id consistency, edge
   endpoint resolution, and walk-through fixture references.
6. Run `mvp20 validate-providers` to certify the data-provider catalog
   covers every market in the leader pool. The catalog
   (`config/data_providers.yaml`) declares five active providers:
   FMP (US primary), Tushare (A-share primary), AKShare (A/HK fallback),
   yfinance (US/HK fallback), and Futu OpenAPI (HK / US deep data via
   the OpenD local gateway). FRED stays planned for the macro epic.
   Secrets MUST come from the env var named in `secret_env_var`
   (e.g. `FMP_API_KEY`, `TUSHARE_TOKEN`, `FUTU_OPEND_PASSWORD`);
   inline secrets in the catalog cause validation to fail.

   Futu OpenD requires extra setup before live use: install OpenD from
   `https://www.futunn.com/download/OpenAPI`, run it locally (default
   `127.0.0.1:11111`), log in once with a Futu account that has the
   relevant HK / US market-data subscriptions, and set
   `FUTU_OPEND_PASSWORD` in `.env`. Override `gateway.host` /
   `gateway.port` in `data_providers.yaml` if OpenD runs on a different
   machine.
7. Run `mvp20 verify-lock` and confirm every dependency is pinned to a full
   commit SHA, not `main`.
8. Run `mvp20 plan-backfill` and review provider coverage / gaps. The
   plan auto-loads `data_providers.yaml` when it sits next to the
   manifest and surfaces per-market provider lists.
9. Verify the 6 vendored upstream modules (under `upstream/`) are
   importable through their skeleton adapters:
   `python -c "from mvp20.adapters import audit_eval, data_platform,
   entity_registry, graph_engine, main_core, reasoner_runtime;
   all_avail = all(m._AVAILABLE for m in [audit_eval, data_platform,
   entity_registry, graph_engine, main_core, reasoner_runtime]);
   print('all adapters available:', all_avail)"`. If any adapter shows
   `_AVAILABLE=False`, check `_IMPORT_ERR` for the missing dep and either
   install the runtime dep or accept that the corresponding routes will
   return 503 `UPSTREAM_UNAVAILABLE`.
10. **Overlay source / compiler sanity check** — graph information is
    authored in YAML and compiled into SQLite before the frontend reads it:

    `mvp20 generate-overlays --period 2026-Q1`
    `mvp20 validate-overlays`
    `mvp20 compile-overlays --db runtime/hot.sqlite`

    Expected storage layout:

    | Layer | Location | Responsibility |
    |---|---|---|
    | YAML source | `config/industry_overlays/<industry_id>.yaml` | 14 L0 industry-derived slots |
    | YAML source | `config/stock_overlays/<industry_id>/<ts_code>.yaml` | company-industry overlay source |
    | SQLite compiled | `runtime/hot.sqlite:company_graph_snapshot` | frontend main graph payload |
    | SQLite compiled | `runtime/hot.sqlite:overlay_alert` | missing/low-confidence overlay alerts |

11. **Downloaded data sanity check** — only after collector has run at least
    one cycle, the stock-overlay endpoint should return 200 with a non-empty
    `realtime` map and the SSE stream should emit an initial `snapshot` frame
    within ~1s of connecting::

    `python scripts/init_hot_db.py`
    `python scripts/collector.py --source mock --interval 60 --max-cycles 2`
    `mvp20 serve --port 8701 &`
    `curl 'http://127.0.0.1:8701/api/project-ult/stock-overlay?ts_code=300750.SZ' | jq '.data.freshness'`
    `# Expect: realtime_node_count > 0 and realtime_max_age_seconds < 120`

    Runtime storage:

    | Layer | Location | Responsibility |
    |---|---|---|
    | SQLite current | `runtime/hot.sqlite:realtime_current` | latest value per `(ts_code, dp_id)`; UPSERT in place |
    | SQLite freshness | `runtime/hot.sqlite:freshness_meta` | sync timestamps and status |
    | Parquet history | `runtime/history/minute/partition_minute=YYYYMMDD_HHMM` | minute replay archive when `--enable-history` is set |
    | Parquet compact | `runtime/history/daily_compact/date=YYYY-MM-DD` | daily compacted archive for DuckDB scans |

    Daily compaction (cron, 01:00):
    `python scripts/compact_history.py`
12. Run fixture and live evidence only through explicit gates.

## Evidence Hygiene

Do not commit raw provider payloads, DSNs, tokens, local runtime paths, parquet
files, generated manifests, stdout/stderr captures, or exitcode files.

## Not Claimed

- Default/full propagation enabled.
- Broad production rollout complete.
- M4.7/financial-doc complete.
- Contracts subtype changes.
- New relation types.
