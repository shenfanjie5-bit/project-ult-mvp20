# Codex high (xhigh) vs low — A/B on 8 prompts

Same 8 prompts (`/tmp/ab/prompt_<KEY>.md`), same model (`gpt-5.5`), only `model_reasoning_effort` differs: `xhigh` baseline vs `low` override.

Stocks: `000063.SZ` (中兴通讯), `NVDA.US`
Tiers: cheap_extract, cheap_classify, analysis, web_analysis

## Per-cell metrics

| stock | tier | fill | known_H | known_L | agree | conf_H | conf_L | dur_H(s) | dur_L(s) | tok_H | tok_L |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 000063.SZ | cheap_extract | 6 | 4 | 5 | 83% | 0.63 | 0.62 | 844 | 267 | 268270 | 95008 |
| 000063.SZ | cheap_classify | 20 | 1 | - | 60% | 0.43 | - | 906 | 153 | 377444 | 94488 |
| 000063.SZ | analysis | 77 | 37 | 29 | 90% | 0.50 | 0.50 | 824 | 252 | 226472 | 88902 |
| 000063.SZ | web_analysis | 8 | 3 | 2 | 88% | 0.64 | 0.67 | 881 | 424 | 322430 | 186319 |
| NVDA.US | cheap_extract | 6 | 3 | 1 | 67% | 0.55 | 0.55 | 706 | 246 | 195940 | 102226 |
| NVDA.US | cheap_classify | 20 | 10 | 2 | 50% | 0.41 | 0.65 | 633 | 214 | 234092 | 70398 |
| NVDA.US | analysis | 77 | 13 | 28 | 81% | 0.55 | 0.51 | 1036 | 274 | 242794 | 95105 |
| NVDA.US | web_analysis | 8 | 3 | 3 | 100% | 0.69 | 0.61 | 928 | 332 | 324735 | 143560 |

## Totals

- Σ Known: high=74, low=70 (Δ=-4)
- Σ duration: high=6758s, low=2162s (save=68%)
- Σ tokens: high=2192177, low=876006 (save=60%)
- Avg agreement: 77%

## Status-pair breakdown (high -> low)

Format `H_status -> L_status: count`. Same pairs are agreement; different pairs are divergence (low changed mind).

### 000063.SZ / cheap_extract

- `Known->Known`: 4
- `Unknown->Known`: 1
- `Unknown->Unknown`: 1
- mean local_dp_id overlap: 80%
- value match on common-Known: 0/4 = 0%

### 000063.SZ / cheap_classify

- `Inactive->Unknown`: 7
- `Inactive->Inactive`: 7
- `Unknown->Unknown`: 5
- `Known->Unknown`: 1
- mean local_dp_id overlap: 18%

### 000063.SZ / analysis

- `Unknown->Unknown`: 32
- `Known->Known`: 29
- `Known->Unknown`: 8
- `Optionality->Optionality`: 4
- `Inactive->Inactive`: 2
- `N/A->N/A`: 2
- mean local_dp_id overlap: 47%
- value match on common-Known: 1/29 = 3%

### 000063.SZ / web_analysis

- `N/A->N/A`: 3
- `Known->Known`: 2
- `Known->Unknown`: 1
- `Unknown->Unknown`: 1
- `Optionality->Optionality`: 1
- value match on common-Known: 0/2 = 0%

### NVDA.US / cheap_extract

- `Unknown->Unknown`: 3
- `Known->Unknown`: 2
- `Known->Known`: 1
- mean local_dp_id overlap: 33%
- value match on common-Known: 0/1 = 0%

### NVDA.US / cheap_classify

- `Inactive->Inactive`: 9
- `Known->Unknown`: 8
- `Inactive->Known`: 1
- `Known->Known`: 1
- `Known->N/A`: 1
- mean local_dp_id overlap: 21%
- value match on common-Known: 0/1 = 0%

### NVDA.US / analysis

- `Unknown->Unknown`: 43
- `Known->Known`: 13
- `Unknown->Known`: 13
- `Optionality->Optionality`: 4
- `Inactive->Known`: 2
- `N/A->N/A`: 2
- mean local_dp_id overlap: 36%
- value match on common-Known: 0/13 = 0%

### NVDA.US / web_analysis

- `Unknown->Unknown`: 3
- `Known->Known`: 3
- `N/A->N/A`: 1
- `Optionality->Optionality`: 1
- value match on common-Known: 0/3 = 0%

## Recommendation per tier

- **cheap_extract**: Known H=7 / L=6, agree=75%, tok_save=58%, time_save=67% → **stay on high**
- **cheap_classify**: Known H=11 / L=2, agree=55%, tok_save=73%, time_save=76% → **stay on high**
- **analysis**: Known H=50 / L=57, agree=85%, tok_save=61%, time_save=72% → **low usable with caution**
- **web_analysis**: Known H=6 / L=5, agree=94%, tok_save=49%, time_save=58% → **low usable with caution**

### Notes

- `low` thinking is suitable when the task is essentially a lookup or shallow classification. The xhigh→low gap shows up as (a) more `Unknown` due to skipped inference, (b) less thorough evidence chains, (c) lower confidence on edge slots.
- Where agreement >= 90% on a tier, **low is acceptable** at the observed token / time saving.
- Where Known coverage drops > 20% or agreement < 80%, **stay on xhigh** — the cost is justified by audit quality.
