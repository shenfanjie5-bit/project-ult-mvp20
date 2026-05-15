# Changelog

Most recent milestones first. Each entry summarizes a code-level
checkpoint; for design rationale see `docs/data_sources/` and
`docs/audit/`. SQLite stats are measured against
`runtime/hot.sqlite:realtime_current` after a `--source all` collector
run.

## 2026-05-15 — Bucket A (31 hard-data dp_id)

- Tushare: +26 dp_id (14 financial-report derived + 12 valuation /
  sell-side / L0 industry sentiment).
- Futu: +3 option-chain dp_id (`L6.priced.iv` / `L7.trade.iv` /
  `L7.trade.options_cp`).
- AKShare: +2 dp_id (`L8.cap.outflow_cut` / `L9.capital.etf_block`).
- SQLite ∩ spec: 105 → **136** (+31). avg_realtime per stock:
  66.7 → **77.5**. avg_effective: 71.6 → **83.5** / 250 (33.4%).
- A/B test complete: codex high / codex low / minimax-M2 over 16 runs
  (2 stocks × 4 tiers × 2 engines, plus codex high vs low diff).
  Reports: `docs/audit/ab_test_codex_vs_minimax_v1.md`,
  `docs/audit/codex_high_vs_low_v1.md`. Field-strategy synthesis in
  `docs/data_sources/field_strategy_v1.md`.
- Fix A excerpt semantic verifier wired in
  `verify_overlay_closed_loop --check-excerpt` (full activation
  pending A2 numeric-tolerant comparison).

## 2026-05-14 — Phase Z (governance + immutability)

- **Z1a** — `merge_preserve_existing_overlay()` helper in
  `mvp20/overlays.py`; default behavior preserves codex-filled
  Known / N/A / Optionality / Inactive across re-generation.
  `--force` opts out for re-baselining.
- **Z1b** — `config/llm_field_governance.yaml` schema bootstrapped
  with 58 dp_id minimal version (route / model_tier /
  refresh_trigger / source_dependencies / write_policy).
- **Z1c** — `scripts/verify_overlay_closed_loop.py` splits policy by
  `model_tier`: closed-loop tier rejects URLs; web_analysis tier
  requires `url` + `checksum` + `fetched_at`. `docs/codex/codex_fill_guide.md`
  rewritten to match.
- **Z1d** — `scripts/codex_prompt_gen.py` filters by governance
  allowlist (`route ∈ {llm_close, llm_web}`) and accepts
  `--model-tier <cheap_extract|cheap_classify|analysis|web_analysis>`.
- **Z2** — `mvp20/fingerprint.py` snapshots
  `(dp_id, upstream values, event)` so a second codex run is idempotent
  unless the fingerprint changes; integrates with
  `EVENT_DRIVEN_DP_IDS` in `overlays.py`.
- **Z3** — governance expanded from 58 → **111 dp_id** (full LLM
  schema coverage; eight bucket-D fields declared web_analysis with
  explicit `allowed_evidence_kinds`).
- **Z5** — four targeted fixes: status-induced fields no longer leak
  into prompt body; web_analysis prompt lists allowed evidence kinds;
  event fingerprint normalized; `EVENT_DRIVEN_DP_IDS` shared between
  `codex_prompt_gen` and `merge_preserve_existing_overlay`.

## 2026-05-12 – 2026-05-13 — Phase X (4 sources + derive)

- **X1** — Tushare naming alias (5 source emit → 2 spec dp_id
  dual-write) so adapter changes don't break spec coverage.
- **X2** — declared-but-silent 6 fields filled + industry-to-em-board
  mapping refreshed.
- **X3a** — FMP US macro + derived (7 + 3 = 10 dp_id).
- **X3b** — Tushare derived bucket (7 dp_id).
- **X4** — `mvp20/derive.py` formalized: 17 derive formulas + 11
  bootstrap fields.
- Cleanup A — Proxy `data_status` correctly emitted by adapter when
  source is partial.
- Cleanup B — sentinel `MARKET:` / `INDUSTRY:` join fallback for
  per-stock hot-snapshot read.
- Cleanup C — `sector_heat` retry / backoff.
- SQLite ∩ spec: 88 → **132** during this phase (later 132 → 136 in
  Bucket A above).

## 2026-05-11 — Initial 5-source skeleton

- First end-to-end wire across Tushare / FMP / Futu / AKShare /
  yfinance with `runtime/hot.sqlite:realtime_current` (UPSERT-in-place)
  and `runtime/history/minute/` (Parquet append).
- `mvp20 generate-overlays` / `validate-overlays` / `compile-overlays`
  chain produces `company_graph_snapshot` for the BFF.
- Baseline: 88 distinct dp_id, avg_effective 49.3 / 250 (19.7%).
