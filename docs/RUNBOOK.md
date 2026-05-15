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

## Phase Z: schema governance + LLM workflow

Phase Z makes every LLM-derived dp_id immutable-by-default and routed
through `config/llm_field_governance.yaml` (111 dp_ids). The three
commands you will use most:

### `mvp20 generate-overlays` — default merge-preserve vs `--force`

```bash
# Default: keep codex-filled Known / N/A / Optionality / Inactive,
#         only fill in slots that are still empty / Unknown.
.venv/bin/mvp20 generate-overlays --period 2026-Q1

# Re-baseline EVERY overlay from SLOT_DEFS. DESTRUCTIVE — overwrites
# codex-filled fields. Use only when re-cutting the schema.
.venv/bin/mvp20 generate-overlays --period 2026-Q1 --force
```

The preserve logic lives in
`merge_preserve_existing_overlay()` (`mvp20/overlays.py`). Rules:

- Codex-filled `Known` / `N/A` / `Optionality` / `Inactive` is preserved
  unless the field is in `EVENT_DRIVEN_DP_IDS` and the event
  fingerprint changed.
- Slots that are still `Unknown` (or `Optionality` with empty `value`)
  are regenerated from `SLOT_DEFS`.
- `--force` skips preserve entirely.

### `scripts/codex_prompt_gen.py --model-tier` — scoped LLM prompts

```bash
# Industry-level prompt (L0 fields).
.venv/bin/python scripts/codex_prompt_gen.py \
    --industry AI_COMPUTE \
    --out /tmp/codex_AI_COMPUTE.md

# Company-level prompt — only cheap_extract tier slots.
.venv/bin/python scripts/codex_prompt_gen.py \
    --industry STORAGE_GRID --ts-code 300750.SZ \
    --model-tier cheap_extract \
    --out /tmp/codex_300750_SZ_cheap.md

# List-only dry run (no prompt body).
.venv/bin/python scripts/codex_prompt_gen.py \
    --industry AI_COMPUTE --ts-code 000063.SZ \
    --model-tier analysis --list-only
```

`--model-tier` reads `model_tier` from
`config/llm_field_governance.yaml` and filters the output to one of
`cheap_extract` / `cheap_classify` / `analysis` / `web_analysis`. This
matters for cost routing — see README §Engine routing decisions.

### `scripts/verify_overlay_closed_loop.py` — evidence policy enforcement

```bash
# Plain run: warn on violations.
.venv/bin/python scripts/verify_overlay_closed_loop.py

# Auto-demote closed-loop-tier violations back to data_status: Unknown.
# Hard violations only — soft (missing checksum etc.) is never demoted.
.venv/bin/python scripts/verify_overlay_closed_loop.py --auto-demote

# Verify the excerpt_quote in evidence actually appears in the upstream
# realtime_current row (semantic check; reads runtime/hot.sqlite).
.venv/bin/python scripts/verify_overlay_closed_loop.py --check-excerpt

# Combine: auto-demote AND check excerpt.
.venv/bin/python scripts/verify_overlay_closed_loop.py \
    --auto-demote --check-excerpt
```

Tier behavior:

- **closed-loop** (`cheap_extract` / `cheap_classify` / `analysis`):
  only `local_dp_id` / `local_overlay` / `industry_inference` are
  allowed. Any URL or web kind is a HARD violation.
- **web-enabled** (`web_analysis`): four web kinds allowed
  (`annual_report` / `research_report` / `investor_relations` /
  `external_url`). Each web entry MUST carry `url` + `checksum` +
  `fetched_at`. Missing those is a SOFT violation (warn only).

## Bucket A 31 hard-data dp_id verification steps

After wiring a new Bucket A field (or as a periodic re-baseline), run:

```bash
# 1. Pull from all 4 sources (Tushare / FMP / Futu / AKShare) + derive.
.venv/bin/python scripts/collector.py --source all --max-cycles 1

# 2. Re-audit injection. Expect: avg_effective ≥ 80 / 250 and
#    avg_realtime ≥ 75 with the 31-dp Bucket A wired.
.venv/bin/python -m mvp20.cli audit-injection

# 3. Verify governance / evidence policy is closed for LLM fields.
.venv/bin/python scripts/verify_overlay_closed_loop.py --check-excerpt

# Spot-check expected numbers:
.venv/bin/python -c "
import sqlite3, yaml
conn = sqlite3.connect('runtime/hot.sqlite')
print('distinct_dp:', conn.execute('SELECT COUNT(DISTINCT dp_id) FROM realtime_current').fetchone()[0])
spec = set(yaml.safe_load(open('config/data_point_roles.yaml'))['data_points'].keys())
sdps = set(r[0] for r in conn.execute('SELECT DISTINCT dp_id FROM realtime_current').fetchall())
print('spec_intersect:', len(sdps & spec), '/ 250')
"
# Current baseline: 166 distinct_dp / 136 spec_intersect.
```

## Q4 — Z4 LLM run preparation

Z4 is the operator-driven LLM fill pass (codex + minimax) that
populates the 111-dp governance schema for an entire quarter.

### codex CLI configuration

```bash
# Standard "high" run — xhigh thinking, single shot, no operator confirm.
codex exec --full-auto -c model_reasoning_effort=xhigh < /tmp/codex_prompt.md

# Low-effort variant — cheap_extract / cheap_classify only; ~60% token
# / time save with ≥80% agreement on those two tiers.
codex exec --full-auto -c model_reasoning_effort=low < /tmp/codex_prompt.md
```

Notes:

- `--full-auto` means codex never pauses for operator confirmation;
  combine with `--sandbox` if you don't trust the local filesystem ACL.
- web_analysis on a sandboxed host (outbound DNS blocked) will emit
  unverified URLs from training memory. The verifier flags these as
  SOFT violations; review before merging.

### minimax-M2 configuration

```bash
export MINIMAX_API_KEY=...   # provisioned per-operator, NOT in repo
.venv/bin/python scripts/minimax_run_prompt.py \
    --prompt /tmp/codex_prompt.md \
    --out runtime/minimax_runs/<ts_code>_<tier>.yaml
```

Then merge through `scripts/apply_yaml_patch.py`, which has a salvage
path for malformed entries.

### Quota / cost control

- Bulk-fill tier order: prefer **minimax for `analysis`** (~10x cheaper
  tokens at 89% agreement), **codex for `cheap_classify`** (audit-trail
  reliant), **codex-low for `cheap_extract`** (within 1 Known of
  xhigh at half the cost), **codex-high (or minimax fallback) for
  `web_analysis`**.
- Rough per-stock budget for a full 4-tier pass: codex ~1 M tokens
  total at xhigh, ~400 K at low; minimax ~50 K tokens. Budget for the
  111-dp schema × 328 stocks accordingly.
- Always run `verify_overlay_closed_loop --check-excerpt --auto-demote`
  after each batch — it catches the most common cost-of-not-checking
  failure (codex inventing a URL from memory).

## Evidence Hygiene

Do not commit raw provider payloads, DSNs, tokens, local runtime paths, parquet
files, generated manifests, stdout/stderr captures, or exitcode files.

## Not Claimed

- Default/full propagation enabled.
- Broad production rollout complete.
- M4.7/financial-doc complete.
- Contracts subtype changes.
- New relation types.
