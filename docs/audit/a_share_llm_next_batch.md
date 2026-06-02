# A-share LLM/Overlay Next Closed-loop Batch

Snapshot basis: `docs/audit/a_share_llm_fill_plan.md`,
`docs/audit/a_share_spec_completion.json`, and dry-run checks against
`scripts/codex_prompt_gen.py` on 2026-05-26.

Scope: A-share company overlay only, L3/L4 closed-loop fields only. Do not use
external network. Do not modify FrontEnd, main audit scripts, runtime DB, or
bulk overlay YAML in this preparation pass.

## Dry-run confirmation

- A-share stock overlay files: 121 files, 116 unique `ts_code`s.
- Broad local evidence is available for all 116 A-share `ts_code`s:
  `L1.company.main_business`, `L9.disclosure.qa_recent`,
  `L8.gov.management_table`, `L5.is.revenue`,
  `L5.is.revenue_growth`, `L5.is.sga_rd`, and `L5.cf.capex`.
- Local `L5.is.gross_margin` exists for 108 A-share `ts_code`s.
- Local `L9.disclosure.annual_report` currently exists only for
  `000977.SZ` (`AI_COMPUTE`, 浪潮信息). This makes it the best pilot because
  annual-report sections can be quoted as `local_dp_id` evidence.
- `codex_prompt_gen.py --model-tier analysis` surfaces many non-target fields
  on a company prompt, usually around 50 rows. The closed-loop execution must
  accept edits only for the L3/L4 target fields listed below.

## Field execution order

Run the fields in dependency order, not in the raw order printed by
`codex_prompt_gen.py`.

| order | dp_id | tier | local evidence dependency | execution rule |
|---:|---|---|---|---|
| 1 | `L3.channel.mix` | `cheap_extract` | `L9.disclosure.qa_recent`, `L1.company.main_business`, annual-report revenue/customer sections if present | First pass. Extract only stated channel split; otherwise `Unknown`. |
| 2 | `L3.region.domestic_overseas` | `analysis` | `L5.is.revenue`, `L1.company.main_business`, annual-report region/revenue sections if present | Must precede overseas/fx/geography fields. Prefer direct disclosure; otherwise `Unknown`. |
| 3 | `L3.region.tier_mix` | `analysis` | `L9.disclosure.qa_recent`, `L1.company.main_business` | Relevant mainly to retail/local-service models. For B2B manufacturers, usually `Unknown` or `N/A`. |
| 4 | `L4.price.subscription` | `analysis` | `L5.is.revenue`, `L9.disclosure.qa_recent` | Mark `N/A` only when local business model text clearly rules out subscription pricing. |
| 5 | `L4.cost.rent_energy_logistics` | `analysis` | `L5.is.gross_margin`, annual-report business/risk sections if present | Do not split rent/energy/logistics without direct local text. |
| 6 | `L4.eff.store_labor` | `analysis` | `L5.is.sga_rd`, annual-report business/revenue sections if present | Strongest for store/labor-heavy models; otherwise `Unknown`/`N/A`. |
| 7 | `L4.price.asp_aov_arpu` | `analysis` | `L5.is.revenue`, annual-report revenue sections, IR Q&A | Needs disclosed volume/users/order denominator; revenue alone is only background. |
| 8 | `L4.share.market` | `analysis` | `L5.is.revenue`, `L9.disclosure.qa_recent`, annual-report business/revenue sections | Prefer explicit market-share/rank wording. |
| 9 | `L4.volume.orders` | `analysis` | `L5.is.revenue`, `L9.disclosure.qa_recent`, annual-report customer/revenue sections | Fill only if orders/backlog/deliveries are locally disclosed. |
| 10 | `L4.volume.users` | `analysis` | `L5.is.revenue`, `L9.disclosure.qa_recent`, annual-report customer/revenue sections | Fill only for user/customer-count businesses with direct evidence. |
| 11 | `L3.channel.overseas` | `analysis` | `L3.region.domestic_overseas`, annual-report region/channel sections if present | Second pass after domestic/overseas is filled. |
| 12 | `L3.region.fx_geo` | `analysis` | `L3.region.domestic_overseas`, `L9.macro.fx` | Current A-share dry run shows `L9.macro.fx` missing. Leave `Unknown` unless local annual-report risk text directly supports it. |
| 13 | `L3.region.key_risk` | `analysis` | `L3.region.fx_geo`, `L9.macro.geo` | Current A-share dry run shows `L9.macro.geo` missing. Treat as hold/Unknown unless direct local annual-report risk text exists. |

Do not include these web-tier fields in closed-loop execution:
`L3.delivery.csat`, `L4.eff.conversion_retention`,
`L4.volume.foot_traffic`, `L4.volume.frequency`.

## Core batch

Wave 1 is the recommended next execution batch. It covers the only annual-report
pilot plus five high-signal A-share manufacturing/technology overlays where
the target L3/L4 fields are broadly applicable and the local SQLite evidence is
dense.

| priority | industry | ts_code | name | target slots | reason |
|---:|---|---|---|---:|---|
| 1 | `AI_COMPUTE` | `000977.SZ` | 浪潮信息 | 12 | Only current local annual-report extraction; best closed-loop proof case. `L4.price.subscription` is already preserved/N/A in dry run. |
| 2 | `STORAGE_GRID` | `300750.SZ` | 宁德时代 | 13 | Leader-style storage/battery overlay; revenue, gross margin, SGA/RD, IR Q&A available. |
| 3 | `EXPORT_MFG` | `000333.SZ` | 美的集团 | 13 | Export/manufacturing model makes channel, overseas, ASP, cost, and share fields meaningful. |
| 4 | `CONSUMER_ELECTRONICS` | `002475.SZ` | 立讯精密 | 13 | Hardware supply-chain name with customer/channel/order/share relevance. |
| 5 | `SEMI_EQUIPMENT` | `002371.SZ` | 北方华创 | 13 | B2B equipment name; good for channel, share, order, cost, and region tests. |
| 6 | `ROBOTICS` | `300124.SZ` | 汇川技术 | 13 | Automation/industrial control name; useful cross-check for B2B operating metrics. |

Wave 2 queue after Wave 1 verification:

| priority | industry | ts_code | name | note |
|---:|---|---|---|---|
| 7 | `NONFERROUS_METALS` | `601899.SH` | 紫金矿业 | Good test for overseas/geography risk, but `L9.macro.fx`/`L9.macro.geo` are currently missing. |
| 8 | `DOMESTIC_CONSUMPTION` | `601888.SH` | 中国中免 | Useful for tier/channel/store-labor fields; avoid web-only foot-traffic/retention fields. |
| 9 | `HK_CN_INTERNET` | `300059.SZ` | 东方财富 | Better applicability for users/subscription than most manufacturers; still closed-loop only. |
| 10 | `INNOVATIVE_PHARMA` | `600276.SH` | 恒瑞医药 | Good pharma representative; expect many volume/user fields to need direct disclosure or stay `Unknown`. |
| 11 | `ANTI_INVOLUTION_CYCLICAL` | `600019.SH` | 宝钢股份 | Cyclical manufacturing test for cost, ASP, share, and orders. |
| 12 | `FINANCIAL_HIGH_DIVIDEND` | `600036.SH` | 招商银行 | Lower confidence for generic L3/L4 operating fields; dry run also misses `L5.is.gross_margin`, so cost field should likely stay `Unknown`. |

## Commands

List-only smoke check for Wave 1:

```bash
for item in \
  "AI_COMPUTE 000977.SZ" \
  "STORAGE_GRID 300750.SZ" \
  "EXPORT_MFG 000333.SZ" \
  "CONSUMER_ELECTRONICS 002475.SZ" \
  "SEMI_EQUIPMENT 002371.SZ" \
  "ROBOTICS 300124.SZ"
do
  set -- $item
  python3 scripts/codex_prompt_gen.py --industry "$1" --ts-code "$2" --model-tier cheap_extract --list-only
  python3 scripts/codex_prompt_gen.py --industry "$1" --ts-code "$2" --model-tier analysis --list-only
done
```

Prompt generation for execution, when ready:

```bash
mkdir -p /tmp/a_share_l3l4_next
for item in \
  "AI_COMPUTE 000977.SZ" \
  "STORAGE_GRID 300750.SZ" \
  "EXPORT_MFG 000333.SZ" \
  "CONSUMER_ELECTRONICS 002475.SZ" \
  "SEMI_EQUIPMENT 002371.SZ" \
  "ROBOTICS 300124.SZ"
do
  set -- $item
  industry="$1"
  ts_code="$2"
  safe_ts="${ts_code/./_}"
  python3 scripts/codex_prompt_gen.py --industry "$industry" --ts-code "$ts_code" --model-tier cheap_extract --out "/tmp/a_share_l3l4_next/${industry}_${safe_ts}_cheap_extract.md"
  python3 scripts/codex_prompt_gen.py --industry "$industry" --ts-code "$ts_code" --model-tier analysis --out "/tmp/a_share_l3l4_next/${industry}_${safe_ts}_analysis.md"
done
```

Execution guardrails:

- For `cheap_extract`, accept only `L3.channel.mix` from the generated prompt.
- For `analysis`, accept only the 12 target L3/L4 fields in the field-order
  table. Ignore L1/L2/L5/L8 rows that the generic prompt also exposes.
- For `000977.SZ`, annual-report evidence must be cited as
  `kind=local_dp_id`, `dp_id=L9.disclosure.annual_report`,
  `source=annual_report:cninfo:2025`, and verbatim excerpt text. Do not copy
  the local `ar_url` value into `evidence_sources`.
- If the source-value table says `(missing in SQLite)` for `L9.macro.fx`,
  `L9.macro.geo`, `L3.region.domestic_overseas`, or `L3.region.fx_geo`, the
  dependent geography fields should stay `Unknown` until the prerequisite is
  filled or a local annual-report risk excerpt directly supports them.

Verification after any overlay edits:

```bash
python3 scripts/verify_overlay_closed_loop.py --check-excerpt --check-schema --quiet
```

Do not use `--auto-demote` until the violation list has been reviewed, because
it rewrites overlay files.
