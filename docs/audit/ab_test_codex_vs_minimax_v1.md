# A/B test report — codex CLI vs minimax-M2

Stocks: `000063.SZ` (中兴通讯), `NVDA.US` (NVIDIA)

Tiers: cheap_extract, cheap_classify, analysis, web_analysis

**Engine setup:**
- **codex** (gpt-5.5 xhigh, `codex exec --full-auto`): can read local files; web access depends on sandbox. On this machine outbound DNS was blocked, so codex's web_analysis tier ran **search-only** (no real fetch) and consequently emitted some **unverified URLs** with no checksum — a soft violation that `verify_overlay_closed_loop.py` would warn on.
- **minimax (`MiniMax-M2`)**: instructed via system prompt to stay closed-loop on all 4 tiers. Returns a single yaml-patch block; `scripts/apply_yaml_patch.py` merges it into the overlay with a salvage path for malformed entries.

## Cell-by-cell totals

| stock | tier | fillable | codex Known | codex avg conf | mm Known | mm avg conf | agree | agreement_rate |
|---|---|---|---|---|---|---|---|---|
| 000063.SZ | cheap_extract | 6 | 4 | 0.63 | 6 | 0.68 | 4/6 | 67% |
| 000063.SZ | cheap_classify | 20 | 1 | 0.43 | 1 | 0.65 | 11/20 | 55% |
| 000063.SZ | analysis | 77 | 37 | 0.50 | 34 | 0.69 | 71/77 | 92% |
| 000063.SZ | web_analysis | 8 | 3 | 0.64 | 0 | - | 5/8 | 62% |
| NVDA.US | cheap_extract | 6 | 3 | 0.55 | 6 | 0.62 | 3/6 | 50% |
| NVDA.US | cheap_classify | 20 | 10 | 0.41 | 0 | - | 7/20 | 35% |
| NVDA.US | analysis | 77 | 13 | 0.55 | 9 | 0.69 | 66/77 | 86% |
| NVDA.US | web_analysis | 8 | 3 | 0.69 | 3 | 0.72 | 5/8 | 62% |

## Evidence kind distribution (per cell)

| stock | tier | codex kinds | minimax kinds |
|---|---|---|---|
| 000063.SZ | cheap_extract | local_dp_id=6 | local_dp_id=10 |
| 000063.SZ | cheap_classify | local_dp_id=26, local_overlay=1 | industry_inference=14, local_dp_id=4 |
| 000063.SZ | analysis | industry_inference=8, local_dp_id=87 | industry_inference=25, local_dp_id=61, local_overlay=1 |
| 000063.SZ | web_analysis | annual_report=7, external_url=2, industry_panel=1, investor_relations=5, local_dp_id=3 | - |
| NVDA.US | cheap_extract | industry_inference=1, local_dp_id=5, local_overlay=1 | industry_inference=3, local_dp_id=4 |
| NVDA.US | cheap_classify | industry_inference=1, local_dp_id=22, local_overlay=5 | industry_inference=1 |
| NVDA.US | analysis | industry_inference=6, local_dp_id=52, local_overlay=1 | industry_inference=26, local_dp_id=37 |
| NVDA.US | web_analysis | annual_report=9, external_url=1, industry_panel=3, investor_relations=5 | annual_report=1, industry_inference=4, industry_panel=1, investor_relations=1, research_report=1 |

## Cost & speed proxies

| stock | tier | prompt_chars | codex tokens | mm prompt_tokens | mm completion_tokens | mm total_tokens |
|---|---|---|---|---|---|---|
| 000063.SZ | cheap_extract | 23306 | 268270 | 7707 | 2042 | 9749 |
| 000063.SZ | cheap_classify | 26378 | 377444 | 8686 | 4186 | 12872 |
| 000063.SZ | analysis | 34330 | 226472 | 11078 | 12077 | 23155 |
| 000063.SZ | web_analysis | 22535 | 322430 | 7538 | 2083 | 9621 |
| NVDA.US | cheap_extract | 15095 | 195940 | 5228 | 2238 | 7466 |
| NVDA.US | cheap_classify | 16804 | 234092 | 5754 | 3366 | 9120 |
| NVDA.US | analysis | 26119 | 242794 | 8617 | 10888 | 19505 |
| NVDA.US | web_analysis | 14324 | 324735 | 5062 | 2772 | 7834 |

## Status-pair disagreement breakdown

Format: `codex_status -> minimax_status: count`. Same status pairs are agreement; different pairs are divergence.

### 000063.SZ / cheap_extract

- `Known->Known`: 4
- `Unknown->Known`: 2
- mean local_dp_id overlap: 61%

### 000063.SZ / cheap_classify

- `Inactive->Unknown`: 7
- `Inactive->Inactive`: 6
- `Unknown->Unknown`: 5
- `Inactive->Known`: 1
- `Known->Unknown`: 1
- mean local_dp_id overlap: 8%

### 000063.SZ / analysis

- `Known->Known`: 33
- `Unknown->Unknown`: 30
- `Optionality->Optionality`: 4
- `Known->Unknown`: 2
- `N/A->N/A`: 2
- `Inactive->Inactive`: 2
- `Known->N/A`: 2
- `Unknown->N/A`: 1
- `Unknown->Known`: 1
- mean local_dp_id overlap: 39%

### 000063.SZ / web_analysis

- `N/A->N/A`: 3
- `Known->Unknown`: 3
- `Optionality->Optionality`: 1
- `Unknown->Unknown`: 1

### NVDA.US / cheap_extract

- `Unknown->Known`: 3
- `Known->Known`: 3
- mean local_dp_id overlap: 83%

### NVDA.US / cheap_classify

- `Known->Unknown`: 9
- `Inactive->Inactive`: 7
- `Inactive->Unknown`: 3
- `Known->N/A`: 1
- mean local_dp_id overlap: 0%

### NVDA.US / analysis

- `Unknown->Unknown`: 52
- `Known->Unknown`: 7
- `Known->Known`: 6
- `Optionality->Optionality`: 4
- `Unknown->Known`: 3
- `N/A->N/A`: 2
- `Inactive->Inactive`: 2
- `Unknown->N/A`: 1
- mean local_dp_id overlap: 57%

### NVDA.US / web_analysis

- `Unknown->N/A`: 3
- `Known->Known`: 3
- `N/A->N/A`: 1
- `Optionality->Optionality`: 1

## Engine recommendation per tier

- **cheap_extract** (2/2 cells both-present): codex Known=7, mm Known=12 → coverage winner: **minimax (+5)**; avg agreement=58%; tokens codex=464210, minimax=17215
- **cheap_classify** (2/2 cells both-present): codex Known=11, mm Known=1 → coverage winner: **codex (+10)**; avg agreement=45%; tokens codex=611536, minimax=21992
- **analysis** (2/2 cells both-present): codex Known=50, mm Known=43 → coverage winner: **codex (+7)**; avg agreement=89%; tokens codex=469266, minimax=42660
- **web_analysis** (2/2 cells both-present): codex Known=6, mm Known=3 → coverage winner: **codex (+3)**; avg agreement=62%; tokens codex=647165, minimax=17455

### Heuristic guidance

- **cheap_extract** — codex was systematically more cautious (marked some L3.channel.mix / L1.position.growth_rank as Unknown where minimax inferred from main_business text). Minimax wins coverage; agreement on the cells where codex commits is high (`Known->Known` dominates). For bulk labeling on AI_COMPUTE B2B names, minimax is acceptable; for ambiguous SMB / consumer stocks, prefer codex.
- **cheap_classify** (event detection) — large divergence. Codex marks most slots `Inactive` ("no event observed") with concrete evidence_summary, while minimax leaves them `Unknown`. On 000063 codex used 26 local_dp_id refs vs minimax's 14 industry_inference + 4 local_dp_id. **Recommend codex** for cheap_classify — minimax's industry-inference-heavy answers lose the audit trail that downstream scoring relies on.
- **analysis** — both engines achieve high agreement (89% avg). Codex modestly higher coverage (+7 Known) and uses local_dp_id more heavily (mean overlap 57% on NVDA, 39% on 000063). Minimax leans on industry_inference (~25 refs per cell). For 80%+ of L1-L5 fills, minimax is a credible substitute at ~10x cheaper tokens; reserve codex for the most-material slots (high materiality + low minimax confidence).
- **web_analysis** — codex's web tier tried `curl` / search but outbound DNS was sandboxed, so codex emitted **URLs from training-set memory without checksum** (a soft policy violation the verifier flags). Minimax's industry_inference-only output is actually safer on a closed network. When real web access is available codex with `--search` is preferred; otherwise demote web_analysis nodes via the policy check rather than trust codex's offline URLs.

### Token-economics

Across paired cells codex used **20-35x the tokens** of minimax (see Cost & speed table above). The ratio is highest for cheap_extract/cheap_classify (where codex's reasoning agent over-explores for what is essentially a lookup task) and lowest for the analysis tier (where minimax also has to produce more structured output).
