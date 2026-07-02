# A-share LLM field goal execution plan

- Date: `2026-06-21`
- Target scope: A-share stock overlays only (`.SH`, `.SZ`, `.BJ`)
- LLM runtime: GPT-5.5 through Codex CLI
- Scope audit: `docs/audit/2026-06-21_a_share_llm_target_scope.json`

## Confirmed rules

- Already-latest fields are skipped.
- `Known` / event-driven `Inactive` nodes with only a missing legacy fingerprint baseline are preserved under the goal policy, instead of being sent to the LLM just to establish a baseline.
- `Known` nodes with a real `source_changed_*` fingerprint rotation still enter the prompt.
- `Unknown + missing_reason: no_local_evidence` nodes are preserved once their `source_fingerprint_at_fill` is unchanged, so no-evidence outcomes are not repeatedly sent to the LLM.
- True source changes still reopen those no-evidence Unknown nodes.
- Batch runs must be A-share-only and should be split by `model_tier`.

## Current scope

| Metric | Count |
|---|---:|
| A-share overlay files | 1,646 |
| Governed LLM node instances | 134,972 |
| Fillable under current policy | 112,230 |
| Skipped under current policy | 22,742 |

## Fillable by tier

| model_tier | Fillable |
|---|---:|
| cheap_extract | 9,732 |
| cheap_classify | 16,471 |
| analysis | 73,517 |
| web_analysis | 12,510 |

## Completed pilot

- Pilot target: `config/stock_overlays/SEMI_EQUIPMENT/002371.SZ.yaml`
- Pilot tier: `cheap_extract`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Nodes handled: 6
- Post-pilot cheap_extract dry-run for `002371.SZ`: 0 fillable
- Closed-loop verifier: 0 hard violations; `002371.SZ` has 0 violations in the verifier JSON
- Overlay validation: `ok: True`, `error_count: 0`

## Completed batch 1

- Batch target: `SEMI_EQUIPMENT`, A-share, `cheap_extract`
- Stocks completed: `001309.SZ`, `002049.SZ`, `002156.SZ`, `002185.SZ`, `002409.SZ`, `002643.SZ`, `002741.SZ`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Nodes handled: 42
- Post-run cheap_extract dry-run:
  - `001309.SZ`: 0 fillable; 6 `preserved_known:fingerprint_unchanged`
  - `002049.SZ`: 0 fillable; 6 `preserved_known:fingerprint_unchanged`
  - `002156.SZ`: 0 fillable; 6 `preserved_known:fingerprint_unchanged`
  - `002185.SZ`: 0 fillable; 6 `preserved_known:fingerprint_unchanged`
  - `002409.SZ`: 0 fillable; 6 `preserved_known:fingerprint_unchanged`
  - `002643.SZ`: 0 fillable; 6 `preserved_known:fingerprint_unchanged`
  - `002741.SZ`: 0 fillable; 6 `preserved_known:fingerprint_unchanged`
- Scoped closed-loop verifier:
  - `001309.SZ`: target 6 dp_ids have 0 violations; overlay has historical non-target warnings
  - `002049.SZ`: target 6 dp_ids have 0 violations; overlay has historical non-target warnings
  - `002156.SZ`: target 6 dp_ids have 0 violations; overlay has historical non-target warnings
  - `002185.SZ`: target 6 dp_ids have 0 violations; overlay has historical non-target warnings
  - `002409.SZ`: target 6 dp_ids have 0 violations; overlay has historical non-target warnings
  - `002643.SZ`: target 6 dp_ids have 0 violations; overlay has historical non-target warnings
  - `002741.SZ`: target 6 dp_ids have 0 violations; overlay has historical non-target warnings
- Overlay validation after batch: `ok: True`, `error_count: 0`
- Scope audit after batch: `fillable_total=112326`, `cheap_extract=9828`

## Completed batch 2

- Batch target: `AI_COMPUTE`, A-share, `cheap_extract`
- Stocks completed: `600050.SH`, `688635.SH`, `920808.BJ`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Nodes handled: 18
- Post-run cheap_extract dry-run:
  - `600050.SH`: 0 fillable; 5 `preserved_known:fingerprint_unchanged`; 1 `preserved_unknown_no_local_evidence:fingerprint_unchanged`
  - `688635.SH`: 0 fillable; 5 `preserved_known:fingerprint_unchanged`; 1 `preserved_unknown_no_local_evidence:fingerprint_unchanged`
  - `920808.BJ`: 0 fillable; 5 `preserved_known:fingerprint_unchanged`; 1 `preserved_unknown_no_local_evidence:fingerprint_unchanged`
- Scoped closed-loop verifier:
  - `600050.SH`: target 6 dp_ids have 0 violations; scoped run has historical industry-overlay warnings
  - `688635.SH`: target 6 dp_ids have 0 violations; scoped run has historical industry-overlay warnings
  - `920808.BJ`: target 6 dp_ids have 0 violations; scoped run has historical industry-overlay warnings
- Overlay validation after batch: `ok: True`, `error_count: 0`
- Scope audit after batch: `fillable_total=112308`, `cheap_extract=9810`

## Completed batch 3

- Batch target: `ANTI_INVOLUTION_CYCLICAL`, A-share, `cheap_extract`
- Stocks completed: `603393.SH`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Nodes handled: 6
- Post-run cheap_extract dry-run:
  - `603393.SH`: 0 fillable; 5 `preserved_known:fingerprint_unchanged`; 1 `preserved_unknown_no_local_evidence:fingerprint_unchanged`
- Scoped closed-loop verifier:
  - `603393.SH`: target 6 dp_ids have 0 violations; scoped run has historical industry-overlay warnings
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count: 164253`
- Test gate after batch: `tests/test_prompt_gen_governance.py tests/test_fingerprint.py` passed, 70 tests
- Scope audit after batch: `fillable_total=112302`, `skipped_total=22670`, `cheap_extract=9804`

## Completed batch 4

- Batch target: `ANTI_INVOLUTION_CYCLICAL`, A-share, `cheap_extract`
- Stocks completed: `920077.BJ`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Nodes handled: 6
- Post-run cheap_extract dry-run:
  - `920077.BJ`: 0 fillable; 6 `preserved_known:fingerprint_unchanged`
- Scoped closed-loop verifier:
  - `920077.BJ`: target 6 dp_ids have 0 violations; scoped run has historical industry-overlay warnings
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count: 164247`
- Test gate after batch: `tests/test_prompt_gen_governance.py tests/test_fingerprint.py` passed, 70 tests
- Scope audit after batch: `fillable_total=112296`, `skipped_total=22676`, `cheap_extract=9798`

## Completed batch 5

- Batch target: `DOMESTIC_CONSUMPTION`, A-share, `cheap_extract`
- Stocks completed: `601107.SH`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Nodes handled: 6
- Post-run cheap_extract dry-run:
  - `601107.SH`: 0 fillable; 6 `preserved_known:fingerprint_unchanged`
- Scoped closed-loop verifier:
  - `601107.SH`: target 6 dp_ids have 0 violations; scoped run has historical industry-overlay warnings
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count: 164241`
- Test gate after batch: `tests/test_prompt_gen_governance.py tests/test_fingerprint.py` passed, 70 tests
- Scope audit after batch: `fillable_total=112290`, `skipped_total=22682`, `cheap_extract=9792`

## Completed batch 6

- Batch target: `DOMESTIC_CONSUMPTION`, A-share, `cheap_extract`
- Stocks completed: `603099.SH`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Nodes handled: 6
- Post-run cheap_extract dry-run:
  - `603099.SH`: 0 fillable; 6 `preserved_known:fingerprint_unchanged`
- Scoped closed-loop verifier:
  - `603099.SH`: target 6 dp_ids have 0 violations; scoped run has historical industry-overlay warnings
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count: 164235`
- Test gate after batch: `tests/test_prompt_gen_governance.py tests/test_fingerprint.py` passed, 70 tests
- Scope audit after batch: `fillable_total=112284`, `skipped_total=22688`, `cheap_extract=9786`

## Completed batch 7

- Batch target: `EXPORT_MFG`, A-share, `cheap_extract`
- Stocks completed: `001365.SZ`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Nodes handled: 6
- Post-run cheap_extract dry-run:
  - `001365.SZ`: 0 fillable; 5 `preserved_known:fingerprint_unchanged`; 1 `preserved_unknown_no_local_evidence:fingerprint_unchanged`
- Scoped closed-loop verifier:
  - `001365.SZ`: target 6 dp_ids have 0 violations; scoped run has historical industry-overlay warnings
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count: 164230`
- Test gate after batch: `tests/test_prompt_gen_governance.py tests/test_fingerprint.py` passed, 70 tests
- Scope audit after batch: `fillable_total=112278`, `skipped_total=22694`, `cheap_extract=9780`

## Completed batch 8

- Batch target: `AI_COMPUTE`, A-share, `cheap_extract`
- Stocks completed: `000063.SZ`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Nodes handled: 6
- Refresh reason before run: 6 `Known` nodes with `source_fingerprint_changed`
- Post-run cheap_extract dry-run:
  - `000063.SZ`: 0 fillable; 6 `preserved_known:fingerprint_unchanged`
- Scoped closed-loop verifier:
  - `000063.SZ`: target 6 dp_ids have 0 violations; scoped run has historical industry-overlay and non-target stock warnings
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count: 164230`
- Test gate after batch: `tests/test_prompt_gen_governance.py tests/test_fingerprint.py` passed, 70 tests
- Scope audit after batch: `fillable_total=112272`, `skipped_total=22700`, `cheap_extract=9774`

## Completed batch 9

- Batch target: `AI_COMPUTE`, A-share, `cheap_extract`
- Stocks completed: `000066.SZ`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Nodes handled: 6
- Fill reason before run: 6 `Unknown` nodes without local completion
- Post-run cheap_extract dry-run:
  - `000066.SZ`: 0 fillable; 6 `preserved_known:fingerprint_unchanged`
- Scoped closed-loop verifier:
  - `000066.SZ`: target 6 dp_ids have 0 violations; scoped run has historical industry-overlay and non-target stock warnings
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count: 164224`
- Test gate after batch: `tests/test_prompt_gen_governance.py tests/test_fingerprint.py` passed, 70 tests
- Scope audit after batch: `fillable_total=112266`, `skipped_total=22706`, `cheap_extract=9768`

## Completed batch 10

- Batch target: `FINANCIAL_HIGH_DIVIDEND`, A-share, `cheap_extract`
- Stocks completed: `000686.SZ`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Nodes handled: 6
- Fill reason before run: 6 `Unknown` nodes with source fingerprint trigger
- Post-run cheap_extract dry-run:
  - `000686.SZ`: 0 fillable; 5 `preserved_known:fingerprint_unchanged`; 1 `preserved_unknown_no_local_evidence:fingerprint_unchanged`
- Scoped closed-loop verifier:
  - `000686.SZ`: target 6 dp_ids have 0 violations; scoped run has historical industry-overlay warnings
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count: 164219`
- Test gate after batch: `tests/test_prompt_gen_governance.py tests/test_fingerprint.py` passed, 70 tests
- Scope audit after batch: `fillable_total=112260`, `skipped_total=22712`, `cheap_extract=9762`

## Completed batch 11

- Batch target: `FINANCIAL_HIGH_DIVIDEND`, A-share, `cheap_extract`
- Stocks completed: `000690.SZ`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Nodes handled: 6
- Fill reason before run: 6 `Unknown` nodes with source fingerprint trigger
- Structural diff after run: exactly 6 target dp_ids changed (`L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`)
- Post-run cheap_extract dry-run:
  - `000690.SZ`: 0 fillable; 6 `preserved_known:fingerprint_unchanged`
- Scoped closed-loop verifier:
  - `000690.SZ`: target 6 dp_ids have 0 violations; scoped run has historical industry-overlay warnings
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count: 164213`
- Test gate after batch: `tests/test_prompt_gen_governance.py tests/test_fingerprint.py` passed, 70 tests
- Scope audit after batch: `fillable_total=112254`, `skipped_total=22718`, `cheap_extract=9756`

## Completed batch 12

- Batch target: `FINANCIAL_HIGH_DIVIDEND`, A-share, `cheap_extract`
- Stocks completed: `000750.SZ`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Nodes handled: 6
- Fill reason before run: 6 `Unknown` nodes with source fingerprint trigger
- Structural diff after run: exactly 6 target dp_ids changed (`L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`)
- Post-run cheap_extract dry-run:
  - `000750.SZ`: 0 fillable; 5 `preserved_known:fingerprint_unchanged`; 1 `preserved_unknown_no_local_evidence:fingerprint_unchanged`
- Scoped closed-loop verifier:
  - `000750.SZ`: target 6 dp_ids have 0 violations; scoped run has historical industry-overlay warnings
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count: 164208`
- Test gate after batch: `tests/test_prompt_gen_governance.py tests/test_fingerprint.py` passed, 70 tests
- Scope audit after batch: `fillable_total=112248`, `skipped_total=22724`, `cheap_extract=9750`

## Completed batch 13

- Batch target: `FINANCIAL_HIGH_DIVIDEND`, A-share, `cheap_extract`
- Stocks completed: `001227.SZ`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Nodes handled: 6
- Fill reason before run: 6 `Unknown` nodes with source fingerprint trigger
- Structural diff after run: exactly 6 target dp_ids changed (`L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`)
- Post-run cheap_extract dry-run:
  - `001227.SZ`: 0 fillable; 5 `preserved_known:fingerprint_unchanged`; 1 `preserved_unknown_no_local_evidence:fingerprint_unchanged`
- Scoped closed-loop verifier:
  - `001227.SZ`: target 6 dp_ids have 0 violations; scoped run has historical industry-overlay warnings
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count: 164203`
- Test gate after batch: `tests/test_prompt_gen_governance.py tests/test_fingerprint.py` passed, 70 tests
- Scope audit after batch: `fillable_total=112242`, `skipped_total=22730`, `cheap_extract=9744`

## Completed batch 14

- Batch target: `FINANCIAL_HIGH_DIVIDEND`, A-share, `cheap_extract`
- Stocks completed: `002500.SZ`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Nodes handled: 6
- Fill reason before run: 6 `Unknown` nodes with source fingerprint trigger
- Structural diff after run: exactly 6 target dp_ids changed (`L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`)
- Post-run cheap_extract dry-run:
  - `002500.SZ`: 0 fillable; 5 `preserved_known:fingerprint_unchanged`; 1 `preserved_unknown_no_local_evidence:fingerprint_unchanged`
- Scoped closed-loop verifier:
  - `002500.SZ`: target 6 dp_ids have 0 violations; scoped run has historical industry-overlay warnings
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count: 164198`
- Test gate after batch: `tests/test_prompt_gen_governance.py tests/test_fingerprint.py` passed, 70 tests
- Scope audit after batch: `fillable_total=112236`, `skipped_total=22736`, `cheap_extract=9738`

## Completed batch 15

- Batch target: `FINANCIAL_HIGH_DIVIDEND`, A-share, `cheap_extract`
- Stocks completed: `002670.SZ`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Nodes handled: 6
- Fill reason before run: 6 `Unknown` nodes with source fingerprint trigger
- Structural diff after run: exactly 6 target dp_ids changed (`L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`)
- Post-run cheap_extract dry-run:
  - `002670.SZ`: 0 fillable; 5 `preserved_known:fingerprint_unchanged`; 1 `preserved_unknown_no_local_evidence:fingerprint_unchanged`
- Scoped closed-loop verifier:
  - `002670.SZ`: target 6 dp_ids have 0 violations; scoped run has historical industry-overlay warnings
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count: 164193`
- Test gate after batch: `tests/test_prompt_gen_governance.py tests/test_fingerprint.py` passed, 70 tests
- Scope audit after batch: `fillable_total=112230`, `skipped_total=22742`, `cheap_extract=9732`

## Completed batch 16

- Batch target: `FINANCIAL_HIGH_DIVIDEND`, A-share, `cheap_extract`
- Stocks completed: `002673.SZ`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Nodes handled: 6
- Fill reason before run: 6 `Unknown` nodes with source fingerprint trigger
- Structural diff after run: exactly 6 target dp_ids changed (`L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`)
- Post-run cheap_extract dry-run:
  - `002673.SZ`: 0 fillable; 5 `preserved_known:fingerprint_unchanged`; 1 `preserved_unknown_no_local_evidence:fingerprint_unchanged`
- Scoped closed-loop verifier:
  - `002673.SZ`: target 6 dp_ids have 0 violations; scoped run has historical industry-overlay warnings
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count: 164188`
- Test gate after batch: `tests/test_prompt_gen_governance.py tests/test_fingerprint.py` passed, 70 tests
- Scope audit after batch: `fillable_total=112224`, `skipped_total=22748`, `cheap_extract=9726`

## Completed batch 17

- Batch target: `FINANCIAL_HIGH_DIVIDEND`, A-share, `cheap_extract`
- Stocks completed: `002797.SZ`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Nodes handled: 6
- Fill reason before run: 6 `Unknown` nodes with source fingerprint trigger
- Structural diff after run: exactly 6 target dp_ids changed (`L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`)
- Post-run cheap_extract dry-run:
  - `002797.SZ`: 0 fillable; 5 `preserved_known:fingerprint_unchanged`; 1 `preserved_unknown_no_local_evidence:fingerprint_unchanged`
- Manual governance normalization:
  - Set the 5 filled `Known` L1 nodes to `data_source: llm_derived`
  - Kept `L3.channel.mix` as `Unknown` with `missing_reason: no_local_evidence`
- Scoped closed-loop verifier:
  - `002797.SZ`: target 6 dp_ids have 0 violations; scoped run has historical industry-overlay warnings
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count: 164183`
- Test gate after batch: `tests/test_prompt_gen_governance.py tests/test_fingerprint.py` passed, 70 tests
- Scope audit after batch: `fillable_total=112218`, `skipped_total=22754`, `cheap_extract=9720`

## Completed batch 18

- Batch target: `FINANCIAL_HIGH_DIVIDEND`, A-share, `cheap_extract`
- Stocks completed: `002807.SZ`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Nodes handled: 6
- Fill reason before run: 6 `Unknown` nodes with source fingerprint trigger
- Execution note:
  - Initial child patch used broad YAML context and hit 8 non-target nodes
  - Non-target edits were reverted to baseline
  - Final fill was applied with `scripts/apply_yaml_patch.py` by exact `dp_id`, then `status` was normalized to `Known` for the 5 L1 nodes
- Structural diff after final fix: exactly 6 target dp_ids changed (`L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`)
- Post-run cheap_extract dry-run:
  - `002807.SZ`: 0 fillable; 5 `preserved_known:fingerprint_unchanged`; 1 `preserved_unknown_no_local_evidence:fingerprint_unchanged`
- Scoped closed-loop verifier:
  - `002807.SZ`: target 6 dp_ids have 0 violations; scoped run has historical industry-overlay warnings
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count: 164178`
- Test gate after batch: `tests/test_prompt_gen_governance.py tests/test_fingerprint.py` passed, 70 tests
- Scope audit after batch: `fillable_total=112212`, `skipped_total=22760`, `cheap_extract=9714`

## Completed batch 19

- Batch target: `FINANCIAL_HIGH_DIVIDEND`, A-share, `cheap_extract`
- Stocks completed: `002839.SZ`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Nodes handled: 6
- Fill reason before run: 6 `Unknown` nodes with source fingerprint trigger
- Execution note:
  - Child run used an exact `dp_id` YAML patch via `scripts/apply_yaml_patch.py`
  - Kept `L3.channel.mix` as `Unknown` with `missing_reason: no_local_evidence` because local sources do not disclose direct/distributor/ecommerce/other channel percentages
  - Filled the 5 L1 nodes as `Known` with `data_source: llm_derived`
- Structural diff after run: exactly 6 target dp_ids changed (`L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`)
- Post-run cheap_extract dry-run:
  - `002839.SZ`: 0 fillable; 5 `preserved_known:fingerprint_unchanged`; 1 `preserved_unknown_no_local_evidence:fingerprint_unchanged`
- Scoped closed-loop verifier:
  - `002839.SZ`: target 6 dp_ids have 0 violations; scoped run has historical industry-overlay warnings
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count: 164173`
- Test gate after batch: `tests/test_prompt_gen_governance.py tests/test_fingerprint.py` passed, 70 tests
- Scope audit after batch: `fillable_total=112206`, `skipped_total=22766`, `cheap_extract=9708`

## Completed batch 20

- Batch target: `FINANCIAL_HIGH_DIVIDEND`, A-share, `cheap_extract`
- Stocks completed: `002926.SZ`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Nodes handled: 6
- Fill reason before run: 6 `Unknown` nodes with source fingerprint trigger
- Execution note:
  - Child run used an exact `dp_id` YAML patch via `scripts/apply_yaml_patch.py`
  - Kept `L3.channel.mix` as `Unknown` with `missing_reason: no_local_evidence` because local sources do not disclose direct/distributor/ecommerce/other channel percentages
  - Filled the 5 L1 nodes as `Known`; normalized their `data_source` to `llm_derived`
- Structural diff after run: exactly 6 target dp_ids changed (`L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`)
- Post-run cheap_extract dry-run:
  - `002926.SZ`: 0 fillable; 5 `preserved_known:fingerprint_unchanged`; 1 `preserved_unknown_no_local_evidence:fingerprint_unchanged`
- Scoped closed-loop verifier:
  - `002926.SZ`: target 6 dp_ids have 0 violations; scoped run has historical industry-overlay warnings
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count: 164168`
- Test gate after batch: `tests/test_prompt_gen_governance.py tests/test_fingerprint.py` passed, 70 tests
- Scope audit after batch: `fillable_total=112200`, `skipped_total=22772`, `cheap_extract=9702`

## Completed batch 21

- Batch target: `FINANCIAL_HIGH_DIVIDEND`, A-share, `cheap_extract`
- Stocks completed: `002936.SZ`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Nodes handled: 6
- Fill reason before run: 6 `Unknown` nodes with source fingerprint trigger
- Execution note:
  - Child run used an exact `dp_id` YAML patch via `scripts/apply_yaml_patch.py`
  - Kept `L3.channel.mix` as `Unknown` with `missing_reason: no_local_evidence` because local sources do not disclose direct/distributor/ecommerce/other channel percentages
  - Filled the 5 L1 nodes as `Known`; normalized their `data_source` to `llm_derived`
- Structural diff after run: exactly 6 target dp_ids changed (`L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`)
- Post-run cheap_extract dry-run:
  - `002936.SZ`: 0 fillable; 5 `preserved_known:fingerprint_unchanged`; 1 `preserved_unknown_no_local_evidence:fingerprint_unchanged`
- Scoped closed-loop verifier:
  - `002936.SZ`: single-file scoped run has 0 hard violations, 0 soft warnings, 0 excerpt mis-cites, and 0 schema violations
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count: 164163`
- Test gate after batch: `tests/test_prompt_gen_governance.py tests/test_fingerprint.py` passed, 70 tests
- Scope audit after batch: `fillable_total=112194`, `skipped_total=22778`, `cheap_extract=9696`

## Completed batch 22

- Batch target: `FINANCIAL_HIGH_DIVIDEND`, A-share, `cheap_extract`
- Stocks completed: `002939.SZ`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Nodes handled: 6
- Fill reason before run: 6 `Unknown` nodes with source fingerprint trigger
- Execution note:
  - Child run used an exact `dp_id` YAML patch via `scripts/apply_yaml_patch.py`
  - Kept `L3.channel.mix` as `Unknown` with `missing_reason: no_local_evidence` because local sources do not disclose direct/distributor/ecommerce/other channel percentages
  - Filled the 5 L1 nodes as `Known` with `data_source: llm_derived`
- Structural diff after run: exactly 6 target dp_ids changed (`L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`)
- Post-run cheap_extract dry-run:
  - `002939.SZ`: 0 fillable; 5 Known fields shown in preserved list; `L3.channel.mix` is excluded from dispatch by the no-local-evidence preserve policy
- Scoped closed-loop verifier:
  - `002939.SZ`: single-file scoped run has 0 hard violations, 0 soft warnings, 0 excerpt mis-cites, and 0 schema violations
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count: 164158`
- Test gate after batch: `tests/test_prompt_gen_governance.py tests/test_fingerprint.py` passed, 70 tests
- Scope audit after batch: `fillable_total=112188`, `skipped_total=22784`, `cheap_extract=9690`

## Completed batch 23

- Batch target: `FINANCIAL_HIGH_DIVIDEND`, A-share, `cheap_extract`
- Stocks completed: `002945.SZ`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Nodes handled: 6
- Fill reason before run: 6 `Unknown` nodes with source fingerprint trigger
- Execution note:
  - Child run used an exact `dp_id` YAML patch via `scripts/apply_yaml_patch.py`
  - Kept `L3.channel.mix` as `Unknown` with `missing_reason: no_local_evidence` because local sources disclose business lines, branch/region distribution, and revenue geography but no direct/distributor/ecommerce/other channel percentages
  - Filled the 5 L1 nodes as `Known`, then normalized their `data_source` to `llm_derived`
  - Interrupted the child run's full-repository verifier after it exceeded the useful wait window; outer validation used the single-file scoped verifier instead
- Structural diff after run: exactly 6 target dp_ids changed (`L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`); non-`nodes` YAML payload unchanged
- Post-run cheap_extract dry-run:
  - `002945.SZ`: 0 fillable; 5 Known fields shown in preserved list; `L3.channel.mix` is excluded from dispatch by the no-local-evidence preserve policy
- Scoped closed-loop verifier:
  - `002945.SZ`: single-file scoped run has 0 hard violations, 0 soft warnings, 0 excerpt mis-cites, and 0 schema violations
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count: 164153`
- Test gate after batch: `tests/test_prompt_gen_governance.py tests/test_fingerprint.py` passed, 70 tests
- Scope audit after batch: `fillable_total=112182`, `skipped_total=22790`, `cheap_extract=9684`

## Completed batch 24

- Batch target: `FINANCIAL_HIGH_DIVIDEND`, A-share, `cheap_extract`
- Stocks completed: `002948.SZ`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Nodes handled: 6
- Fill reason before run: 6 `Unknown` nodes with source fingerprint trigger
- Execution note:
  - Child run used an exact `dp_id` YAML patch via `scripts/apply_yaml_patch.py`
  - Kept `L3.channel.mix` as `Unknown` with `missing_reason: no_local_evidence` because local sources disclose business lines and revenue structure but no direct/distributor/ecommerce/other channel percentages
  - Filled the 5 L1 nodes as `Known` with `data_source: llm_derived`
- Structural diff after run: exactly 6 target dp_ids changed (`L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`); non-`nodes` YAML payload unchanged
- Post-run cheap_extract dry-run:
  - `002948.SZ`: 0 fillable; 5 Known fields shown in preserved list; `L3.channel.mix` is excluded from dispatch by the no-local-evidence preserve policy
- Scoped closed-loop verifier:
  - `002948.SZ`: single-file scoped run has 0 hard violations, 0 soft warnings, 0 excerpt mis-cites, and 0 schema violations
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count: 164148`
- Test gate after batch: `tests/test_prompt_gen_governance.py tests/test_fingerprint.py` passed, 70 tests
- Scope audit after batch: `fillable_total=112176`, `skipped_total=22796`, `cheap_extract=9678`

## Completed batch 25

- Batch target: `FINANCIAL_HIGH_DIVIDEND`, A-share, `cheap_extract`
- Stocks completed: `002958.SZ`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Nodes handled: 6
- Fill reason before run: 6 `Unknown` nodes with source fingerprint trigger
- Execution note:
  - Child run used an exact `dp_id` YAML patch via `scripts/apply_yaml_patch.py`
  - Kept `L3.channel.mix` as `Unknown` with `missing_reason: no_local_evidence` because local sources disclose bank business lines, region, and online/offline wording but no direct/distributor/ecommerce/other channel percentages
  - Filled the 5 L1 nodes as `Known` with `data_source: llm_derived`
  - Restored a non-semantic `scores.formula` YAML line-wrap drift so the final textual diff contains only target node hunks
- Structural diff after run: exactly 6 target dpids changed (`L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`); non-`nodes` YAML payload unchanged
- Post-run cheap_extract dry-run:
  - `002958.SZ`: 0 fillable; 5 Known fields shown in preserved list; `L3.channel.mix` is excluded from dispatch by the no-local-evidence preserve policy
- Scoped closed-loop verifier:
  - `002958.SZ`: single-file scoped run has 0 hard violations, 0 soft warnings, 0 excerpt mis-cites, and 0 schema violations
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count: 164143`
- Test gate after batch: `tests/test_prompt_gen_governance.py tests/test_fingerprint.py` passed, 70 tests
- Scope audit after batch: `fillable_total=112170`, `skipped_total=22802`, `cheap_extract=9672`

## Completed batch 26

- Batch target: `FINANCIAL_HIGH_DIVIDEND`, A-share, `cheap_extract`
- Stocks completed: `002966.SZ`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Nodes handled: 6
- Fill reason before run: 6 `Unknown` nodes with source fingerprint trigger
- Execution note:
  - Child run used an exact `dp_id` YAML patch via `scripts/apply_yaml_patch.py`
  - Kept `L3.channel.mix` as `Unknown` with `missing_reason: no_local_evidence` because local annual-report sections did not disclose direct/distributor/ecommerce/other channel percentages
  - Filled the 5 L1 nodes as `Known` with `data_source: llm_derived`
  - Split two multi-line main-business excerpts into exact local substrings so excerpt verification stays strict
- Structural diff after run: exactly 6 target dpids changed (`L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`); non-`nodes` YAML payload unchanged
- Post-run cheap_extract dry-run:
  - `002966.SZ`: 0 fillable; 5 Known fields shown in preserved list; `L3.channel.mix` is excluded from dispatch by the no-local-evidence preserve policy
- Scoped closed-loop verifier:
  - `002966.SZ`: single-file scoped run has 0 hard violations, 0 soft warnings, 0 excerpt mis-cites, and 0 schema violations
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count: 164138`
- Test gate after batch: `tests/test_prompt_gen_governance.py tests/test_fingerprint.py` passed, 70 tests
- Scope audit after batch: `fillable_total=112164`, `skipped_total=22808`, `cheap_extract=9666`

## Completed batch 27

- Batch target: `FINANCIAL_HIGH_DIVIDEND`, A-share, `cheap_extract`
- Stocks completed: `600015.SH`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Nodes handled: 6
- Fill reason before run: 6 `Unknown` nodes with source fingerprint trigger
- Execution note:
  - Child run used an exact `dp_id` YAML patch via `scripts/apply_yaml_patch.py`
  - Kept `L3.channel.mix` as `Unknown` with `missing_reason: no_local_evidence` because local business scope, revenue structure, and regional revenue did not disclose direct/distributor/ecommerce/other channel percentages
  - Filled the 5 L1 nodes as `Known` with `data_source: llm_derived`
  - Parent pass normalized no-local-evidence metadata, restored a non-semantic `scores.formula` YAML line-wrap drift, and confirmed no non-target node changed
- Structural diff after run: exactly 6 target dpids changed (`L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`); non-`nodes` YAML payload unchanged
- Post-run cheap_extract dry-run:
  - `600015.SH`: 0 fillable; 5 Known fields shown in preserved list; `L3.channel.mix` is excluded from dispatch by the no-local-evidence preserve policy
- Scoped closed-loop verifier:
  - `600015.SH`: single-file scoped run has 0 hard violations, 0 soft warnings, 0 excerpt mis-cites, and 0 schema violations
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count: 164133`
- Test gate after batch: `tests/test_prompt_gen_governance.py tests/test_fingerprint.py` passed, 70 tests
- Scope audit after batch: `fillable_total=112158`, `skipped_total=22814`, `cheap_extract=9660`

## Completed batch 28

- Batch target: `FINANCIAL_HIGH_DIVIDEND`, A-share, `cheap_extract`
- Stocks completed: `600109.SH`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Nodes handled: 6
- Fill reason before run: 6 `Unknown` nodes with source fingerprint trigger
- Execution note:
  - Child run used an exact `dp_id` YAML patch via `scripts/apply_yaml_patch.py`
  - Kept `L3.channel.mix` as `Unknown` with `missing_reason: no_local_evidence` because local business-line, regional, and revenue-structure evidence did not disclose direct/distributor/ecommerce/other channel percentages
  - Filled the 5 L1 nodes as `Known` with `data_source: llm_derived`
  - Parent pass restored a non-semantic `scores.formula` YAML line-wrap drift and confirmed no non-target node changed
- Structural diff after run: exactly 6 target dpids changed (`L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`); non-`nodes` YAML payload unchanged
- Post-run cheap_extract dry-run:
  - `600109.SH`: 0 fillable; 5 Known fields shown in preserved list; `L3.channel.mix` is excluded from dispatch by the no-local-evidence preserve policy
- Scoped closed-loop verifier:
  - `600109.SH`: single-file scoped run has 0 hard violations, 0 soft warnings, 0 excerpt mis-cites, and 0 schema violations
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count: 164128`
- Test gate after batch: `tests/test_prompt_gen_governance.py tests/test_fingerprint.py` passed, 70 tests
- Scope audit after batch: `fillable_total=112152`, `skipped_total=22820`, `cheap_extract=9654`

## Completed batch 29

- Batch target: `FINANCIAL_HIGH_DIVIDEND`, A-share, `cheap_extract`
- Stocks completed: `600123.SH`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Nodes handled: 6
- Fill reason before run: 6 `Unknown` nodes with source fingerprint trigger
- Execution note:
  - Child run used an exact `dp_id` YAML patch via `scripts/apply_yaml_patch.py`
  - Kept `L3.channel.mix` as `Unknown` with `missing_reason: no_local_evidence` because local sources only disclose main business, product/business lines, and operating scope, not direct/distributor/ecommerce/other channel percentages
  - Filled the 5 L1 nodes as `Known` with `data_source: llm_derived`
  - Parent pass confirmed the child-restored `scores.formula` YAML line wrapping left no non-target structural changes
- Structural diff after run: exactly 6 target dpids changed (`L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`); non-`nodes` YAML payload unchanged
- Post-run cheap_extract dry-run:
  - `600123.SH`: 0 fillable; 5 Known fields shown in preserved list; `L3.channel.mix` is excluded from dispatch by the no-local-evidence preserve policy
- Scoped closed-loop verifier:
  - `600123.SH`: single-file scoped run has 0 hard violations, 0 soft warnings, 0 excerpt mis-cites, and 0 schema violations
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count: 164123`
- Test gate after batch: `tests/test_prompt_gen_governance.py tests/test_fingerprint.py` passed, 70 tests
- Scope audit after batch: `fillable_total=112146`, `skipped_total=22826`, `cheap_extract=9648`

## Completed batch 30

- Batch target: `FINANCIAL_HIGH_DIVIDEND`, A-share, `cheap_extract`
- Stocks completed: `600155.SH`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Nodes handled: 6
- Fill reason before run: 6 `Unknown` nodes with source fingerprint trigger
- Execution note:
  - Child run used an exact `dp_id` YAML patch via `scripts/apply_yaml_patch.py`
  - Kept `L3.channel.mix` as `Unknown` with `missing_reason: no_local_evidence` because local sources disclose business lines, product/industry/region revenue structure, and operating scope, but no direct/distributor/ecommerce/other channel percentages
  - Filled the 5 L1 nodes as `Known` with `data_source: llm_derived`
  - Parent pass restored a non-semantic `scores.formula` YAML line-wrap drift and confirmed no non-target node changed
- Structural diff after run: exactly 6 target dpids changed (`L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`); non-`nodes` YAML payload unchanged
- Post-run cheap_extract dry-run:
  - `600155.SH`: 0 fillable; 5 Known fields shown in preserved list; `L3.channel.mix` is excluded from dispatch by the no-local-evidence preserve policy
- Scoped closed-loop verifier:
  - `600155.SH`: single-file scoped run has 0 hard violations, 0 soft warnings, 0 excerpt mis-cites, and 0 schema violations
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count: 164118`
- Test gate after batch: `tests/test_prompt_gen_governance.py tests/test_fingerprint.py` passed, 70 tests
- Scope audit after batch: `fillable_total=112140`, `skipped_total=22832`, `cheap_extract=9642`

## Completed batch 31

- Batch target: `FINANCIAL_HIGH_DIVIDEND`, A-share, `cheap_extract`
- Stocks completed: `600369.SH`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Nodes handled: 6
- Fill reason before run: 6 `Unknown` nodes with source fingerprint trigger
- Execution note:
  - Child run used an exact `dp_id` YAML patch via `scripts/apply_yaml_patch.py`
  - Kept `L3.channel.mix` as `Unknown` with `missing_reason: no_local_evidence` because local annual-report channel sections do not disclose direct/distributor/ecommerce/other channel percentages
  - Filled the 5 L1 nodes as `Known` with `data_source: llm_derived`
  - Parent pass restored a non-semantic `scores.formula` YAML line-wrap drift and confirmed no non-target node changed
- Structural diff after run: exactly 6 target dpids changed (`L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`); non-`nodes` YAML payload unchanged
- Post-run cheap_extract dry-run:
  - `600369.SH`: 0 fillable; 5 Known fields shown in preserved list; `L3.channel.mix` is excluded from dispatch by the no-local-evidence preserve policy
- Scoped closed-loop verifier:
  - `600369.SH`: single-file scoped run has 0 hard violations, 0 soft warnings, 0 excerpt mis-cites, and 0 schema violations
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count: 164113`
- Test gate after batch: `tests/test_prompt_gen_governance.py tests/test_fingerprint.py` passed, 70 tests
- Scope audit after batch: `fillable_total=112134`, `skipped_total=22838`, `cheap_extract=9636`

## Completed batch 32

- Batch target: `FINANCIAL_HIGH_DIVIDEND`, A-share, `cheap_extract`
- Stocks completed: `600621.SH`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Nodes handled: 6
- Fill reason before run: 6 `Unknown` nodes with source fingerprint trigger
- Execution note:
  - Child run used an exact `dp_id` YAML patch via `scripts/apply_yaml_patch.py`
  - Kept `L3.channel.mix` as `Unknown` with `missing_reason: no_local_evidence` because local annual-report disclosure provides business-line and regional revenue structure, but no direct/distributor/ecommerce/other channel percentages
  - Filled the 5 L1 nodes as `Known` with `data_source: llm_derived`; `L1.position.growth_rank` uses the local 2026Q1 revenue YoY of `-0.967%` with exact rank left null
  - Parent pass restored a non-semantic `scores.formula` YAML line-wrap drift and confirmed no non-target node changed
- Structural diff after run: exactly 6 target dpids changed (`L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`); non-`nodes` YAML payload unchanged
- Post-run cheap_extract dry-run:
  - `600621.SH`: 0 fillable; 5 Known fields shown in preserved list; `L3.channel.mix` is excluded from dispatch by the no-local-evidence preserve policy
- Scoped closed-loop verifier:
  - `600621.SH`: single-file scoped run has 0 hard violations, 0 soft warnings, 0 excerpt mis-cites, and 0 schema violations
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count: 164108`
- Test gate after batch: `tests/test_prompt_gen_governance.py tests/test_fingerprint.py` passed, 70 tests
- Scope audit after batch: `fillable_total=112128`, `skipped_total=22844`, `cheap_extract=9630`

## Completed batch 33

- Batch target: `FINANCIAL_HIGH_DIVIDEND`, A-share, `cheap_extract`
- Stocks completed: `600816.SH`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Nodes handled: 6
- Fill reason before run: 6 `Unknown` nodes with source fingerprint trigger
- Execution note:
  - Child run used an exact `dp_id` YAML patch via `scripts/apply_yaml_patch.py`
  - Kept `L3.channel.mix` as `Unknown` with `missing_reason: no_local_evidence` because local annual-report disclosure provides business and revenue structure, but no direct/distributor/ecommerce/other channel percentages
  - Filled the 5 L1 nodes as `Known` with `data_source: llm_derived`; `L1.position.growth_rank` uses the local 2026Q1 revenue YoY of `-38.8032%` with exact rank left null
  - Parent pass fixed missing `data_source: llm_derived` metadata on the 5 Known L1 nodes and confirmed no non-target node or non-`nodes` payload changed
- Structural diff after run: exactly 6 target dpids changed (`L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`); non-`nodes` YAML payload unchanged
- Post-run cheap_extract dry-run:
  - `600816.SH`: 0 fillable; 5 Known fields shown in preserved list; `L3.channel.mix` is excluded from dispatch by the no-local-evidence preserve policy
- Scoped closed-loop verifier:
  - `600816.SH`: single-file scoped run has 0 hard violations, 0 soft warnings, 0 excerpt mis-cites, and 0 schema violations
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count: 164103`
- Test gate after batch: `tests/test_prompt_gen_governance.py tests/test_fingerprint.py` passed, 70 tests
- Scope audit after batch: `fillable_total=112122`, `skipped_total=22850`, `cheap_extract=9624`

## Completed batch 34

- Batch target: `FINANCIAL_HIGH_DIVIDEND`, A-share, `cheap_extract`
- Stocks completed: `600901.SH`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Nodes handled: 6
- Fill reason before run: 6 `Unknown` nodes with source fingerprint trigger
- Execution note:
  - Child run used an exact `dp_id` YAML patch via `scripts/apply_yaml_patch.py`
  - Kept `L3.channel.mix` as `Unknown` with `missing_reason: no_local_evidence` because local disclosure provides business, regional, customer, and revenue structure, but no direct/distributor/ecommerce/other channel percentages
  - Filled the 5 L1 nodes as `Known` with `data_source: llm_derived`; `L1.position.growth_rank` uses local 2026Q1 revenue YoY values `16.459307181281492%` and `16.4593%`, with exact rank left null
  - Parent pass fixed missing `data_source: llm_derived` metadata on the 5 Known L1 nodes and confirmed no non-target node or non-`nodes` payload changed
- Structural diff after run: exactly 6 target dpids changed (`L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`); non-`nodes` YAML payload unchanged
- Post-run cheap_extract dry-run:
  - `600901.SH`: 0 fillable; 5 Known fields shown in preserved list; `L3.channel.mix` is excluded from dispatch by the no-local-evidence preserve policy
- Scoped closed-loop verifier:
  - `600901.SH`: single-file scoped run has 0 hard violations, 0 soft warnings, 0 excerpt mis-cites, and 0 schema violations
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count: 164098`
- Test gate after batch: `tests/test_prompt_gen_governance.py tests/test_fingerprint.py` passed, 70 tests
- Scope audit after batch: `fillable_total=112116`, `skipped_total=22856`, `cheap_extract=9618`

## Completed batch 35

- Batch target: `FINANCIAL_HIGH_DIVIDEND`, A-share, `cheap_extract`
- Stocks completed: `600906.SH`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Nodes handled: 6
- Fill reason before run: 6 `Unknown` nodes with source fingerprint trigger
- Execution note:
  - Child run used an exact `dp_id` YAML patch via `scripts/apply_yaml_patch.py`
  - Kept `L3.channel.mix` as `Unknown` with `missing_reason: no_local_evidence` because local annual-report disclosure provides business-line and regional revenue structure, but no direct/distributor/ecommerce/other channel percentages
  - Filled the 5 L1 nodes as `Known` with `data_source: llm_derived`; `L1.position.growth_rank` uses local 2026Q1 revenue YoY values `51.0612116654822%` and `51.0612%`, with rank/percentile left null because no local industry ranking was available
  - Parent pass confirmed the child already set `data_source: llm_derived` on the 5 Known L1 nodes and confirmed no non-target node or non-`nodes` payload changed
- Structural diff after run: exactly 6 target dpids changed (`L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`); non-`nodes` YAML payload unchanged
- Post-run cheap_extract dry-run:
  - `600906.SH`: 0 fillable; 5 Known fields shown in preserved list; `L3.channel.mix` is excluded from dispatch by the no-local-evidence preserve policy
- Scoped closed-loop verifier:
  - `600906.SH`: single-file scoped run has 0 hard violations, 0 soft warnings, 0 excerpt mis-cites, and 0 schema violations
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count: 164093`
- Test gate after batch: `tests/test_prompt_gen_governance.py tests/test_fingerprint.py` passed, 70 tests
- Scope audit after batch: `fillable_total=112110`, `skipped_total=22862`, `cheap_extract=9612`

## Completed batch 36

- Batch target: `FINANCIAL_HIGH_DIVIDEND`, A-share, `cheap_extract`
- Stocks completed: `600908.SH`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Nodes handled: 6
- Fill reason before run: 6 `Unknown` nodes with source fingerprint trigger
- Execution note:
  - Child run used an exact `dp_id` YAML patch via `scripts/apply_yaml_patch.py`
  - Kept `L3.channel.mix` as `Unknown` with `missing_reason: no_local_evidence` because the local 2025 annual-report excerpt discloses company/individual/funds/other business revenue and regional revenue, but no direct/distributor/ecommerce/other channel percentages
  - Filled the 5 L1 nodes as `Known` with `data_source: llm_derived`; `L1.position.growth_rank` uses local 2026Q1 revenue YoY values `2.595647434492319%` and `2.5956%`, with rank/share left null because no local industry ranking was available
  - Parent pass confirmed no non-target node or non-`nodes` payload changed; child-created YAML formatting drift in `scores.formula` was restored before final gates
- Structural diff after run: exactly 6 target dpids changed (`L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`); non-`nodes` YAML payload unchanged
- Post-run cheap_extract dry-run:
  - `600908.SH`: 0 fillable; 5 Known fields shown in preserved list; `L3.channel.mix` is excluded from dispatch by the no-local-evidence preserve policy
- Scoped closed-loop verifier:
  - `600908.SH`: single-file scoped run has 0 hard violations, 0 soft warnings, 0 excerpt mis-cites, and 0 schema violations
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count: 164088`
- Test gate after batch: `tests/test_prompt_gen_governance.py tests/test_fingerprint.py` passed, 70 tests
- Scope audit after batch: `fillable_total=112104`, `skipped_total=22868`, `cheap_extract=9606`

## Completed batch 37

- Batch target: `FINANCIAL_HIGH_DIVIDEND`, A-share, `cheap_extract`
- Stocks completed: `600909.SH`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Nodes handled: 6
- Fill reason before run: 6 `Unknown` nodes with source fingerprint trigger
- Execution note:
  - Child run used an exact `dp_id` YAML patch via `scripts/apply_yaml_patch.py`
  - Kept `L3.channel.mix` as `Unknown` with `missing_reason: no_local_evidence` because local source text discloses business lines and licenses, but no direct/distributor/ecommerce/other channel percentages
  - Filled the 5 L1 nodes as `Known` with `data_source: llm_derived`; `L1.position.growth_rank` uses local 2026Q1 revenue YoY values `-21.6102%` and `-32.07570464058313%`, with rank left null because no local industry ranking was available
  - Parent pass confirmed no non-target node or non-`nodes` payload changed
- Structural diff after run: exactly 6 target dpids changed (`L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`); non-`nodes` YAML payload unchanged
- Post-run cheap_extract dry-run:
  - `600909.SH`: 0 fillable; 5 Known fields shown in preserved list; `L3.channel.mix` is excluded from dispatch by the no-local-evidence preserve policy
- Scoped closed-loop verifier:
  - `600909.SH`: scoped temp run has 0 hard violations, 0 schema violations, and 0 target-node violation rows; existing industry-overlay soft excerpt warnings were outside the 6 target stock nodes
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count: 164083`
- Test gate after batch: `tests/test_prompt_gen_governance.py tests/test_fingerprint.py` passed, 70 tests
- Scope audit after batch: `fillable_total=112098`, `skipped_total=22874`, `cheap_extract=9600`

## Completed batch 38

- Batch target: `FINANCIAL_HIGH_DIVIDEND`, A-share, `cheap_extract`
- Stocks completed: `600918.SH`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Nodes handled: 6
- Fill reason before run: 6 `Unknown` nodes with source fingerprint trigger
- Execution note:
  - Child run used an exact `dp_id` YAML patch via `scripts/apply_yaml_patch.py`
  - Kept `L3.channel.mix` as `Unknown` with `missing_reason: no_local_evidence` because local 2025 annual-report excerpt discloses business-line revenue and regional revenue, but no direct/distributor/ecommerce/other channel percentages
  - Filled the 5 L1 nodes as `Known` with `data_source: llm_derived`; `L1.position.growth_rank` uses local 2026Q1 revenue YoY values `22.074130084892168%` and `25.1367%`, with rank/percentile left null because no local industry ranking was available
  - Parent pass confirmed no non-target node or non-`nodes` payload changed
- Structural diff after run: exactly 6 target dpids changed (`L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`); non-`nodes` YAML payload unchanged
- Post-run cheap_extract dry-run:
  - `600918.SH`: 0 fillable; 5 Known fields shown in preserved list; `L3.channel.mix` is excluded from dispatch by the no-local-evidence preserve policy
- Scoped closed-loop verifier:
  - `600918.SH`: scoped temp run has 0 hard violations, 0 schema violations, and 0 target-node violation rows; existing industry-overlay soft excerpt warnings were outside the 6 target stock nodes
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count: 164078`
- Test gate after batch: `tests/test_prompt_gen_governance.py tests/test_fingerprint.py` passed, 70 tests
- Scope audit after batch: `fillable_total=112092`, `skipped_total=22880`, `cheap_extract=9594`

## Completed batch 39

- Batch target: `FINANCIAL_HIGH_DIVIDEND`, A-share, `cheap_extract`
- Stocks completed: `600926.SH`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Nodes handled: 6
- Fill reason before run: 6 `Unknown` nodes with source fingerprint trigger
- Execution note:
  - Child run used an exact `dp_id` YAML patch via `scripts/apply_yaml_patch.py`
  - Kept `L3.channel.mix` as `Unknown` with `missing_reason: no_local_evidence` because local source text discloses business lines, business scope, and regional institution coverage, but no direct/distributor/ecommerce/other channel percentages
  - Filled the 5 L1 nodes as `Known` with `data_source: llm_derived`; `L1.position.growth_rank` uses local 2026Q1 revenue YoY values `4.288808918981058%` and `4.2888%`, with rank left null because no local industry ranking was available
  - Parent pass confirmed no non-target node or non-`nodes` payload changed; child-created YAML formatting drift in `scores.formula` was restored before final gates
- Structural diff after run: exactly 6 target dpids changed (`L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`); non-`nodes` YAML payload unchanged
- Post-run cheap_extract dry-run:
  - `600926.SH`: 0 fillable; 5 Known fields shown in preserved list; `L3.channel.mix` is excluded from dispatch by the no-local-evidence preserve policy
- Scoped closed-loop verifier:
  - `600926.SH`: single-file scoped run has 0 hard violations, 0 soft warnings, 0 excerpt mis-cites, and 0 schema violations
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count: 164073`
- Test gate after batch: `tests/test_prompt_gen_governance.py tests/test_fingerprint.py` passed, 70 tests
- Scope audit after batch: `fillable_total=112086`, `skipped_total=22886`, `cheap_extract=9588`

## Completed batch 40

- Batch target: `FINANCIAL_HIGH_DIVIDEND`, A-share, `cheap_extract`
- Stocks completed: `600928.SH`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Nodes handled: 6
- Fill reason before run: 6 `Unknown` nodes with source fingerprint trigger
- Execution note:
  - Child run used an exact `dp_id` YAML patch via `scripts/apply_yaml_patch.py`
  - Kept `L3.channel.mix` as `Unknown` with `missing_reason: no_local_evidence` because local SQLite annual-report sections `customer_segment`, `revenue_structure`, and `region_distribution` are empty, and available business overview/main-business text does not disclose direct/distributor/ecommerce/other channel percentages
  - Filled the 5 L1 nodes as `Known` with `data_source: llm_derived`; parent pass normalized `data_source` after the child patch omitted it
  - `L1.position.growth_rank` uses local 2026Q1 revenue YoY values `41.540301119314776%` and `41.5403%`, with rank left null because no local industry ranking was available
  - Parent pass confirmed no non-target node or non-`nodes` payload changed; child-created YAML formatting drift in `scores.formula` was restored before final gates
- Structural diff after run: exactly 6 target dpids changed (`L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`); non-`nodes` YAML payload unchanged
- Post-run cheap_extract dry-run:
  - `600928.SH`: 0 fillable; 5 Known fields shown in preserved list; `L3.channel.mix` is excluded from dispatch by the no-local-evidence preserve policy
- Scoped closed-loop verifier:
  - `600928.SH`: single-file scoped run has 0 hard violations, 0 soft warnings, 0 excerpt mis-cites, and 0 schema violations
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count: 164068`
- Test gate after batch: `tests/test_prompt_gen_governance.py tests/test_fingerprint.py` passed, 70 tests
- Scope audit after batch: `fillable_total=112080`, `skipped_total=22892`, `cheap_extract=9582`

## Completed batch 41

- Batch target: `FINANCIAL_HIGH_DIVIDEND`, A-share, `cheap_extract`
- Stocks completed: `601009.SH`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Nodes handled: 6
- Fill reason before run: 6 `Unknown` nodes with source fingerprint trigger
- Execution note:
  - Child run used an exact `dp_id` YAML patch via `scripts/apply_yaml_patch.py`
  - Kept `L3.channel.mix` as `Unknown` with `missing_reason: no_local_evidence` because local annual-report sections `customer_segment` and `revenue_structure` are empty for channel evidence, while available business/region text does not disclose direct/distributor/ecommerce/other channel percentages
  - Filled the 5 L1 nodes as `Known` with `data_source: llm_derived`
  - `L1.position.growth_rank` uses local 2026Q1 revenue YoY values `13.540011013375741%` and `13.54%`, with rank left null because no local industry ranking was available
  - Parent pass confirmed no non-target node or non-`nodes` payload changed; child-created YAML formatting drift in `scores.formula` was restored before final gates
- Structural diff after run: exactly 6 target dpids changed (`L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`); non-`nodes` YAML payload unchanged
- Post-run cheap_extract dry-run:
  - `601009.SH`: 0 fillable; 5 Known fields shown in preserved list; `L3.channel.mix` is excluded from dispatch by the no-local-evidence preserve policy
- Scoped closed-loop verifier:
  - `601009.SH`: single-file scoped run has 0 hard violations, 0 soft warnings, 0 excerpt mis-cites, and 0 schema violations
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count: 164063`
- Test gate after batch: `tests/test_prompt_gen_governance.py tests/test_fingerprint.py` passed, 70 tests
- Scope audit after batch: `fillable_total=112074`, `skipped_total=22898`, `cheap_extract=9576`

## Completed batch 42

- Batch target: `FINANCIAL_HIGH_DIVIDEND`, A-share, `cheap_extract`
- Stocks completed: `601059.SH`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Nodes handled: 6
- Fill reason before run: 6 `Unknown` nodes with source fingerprint trigger
- Execution note:
  - Child run used an exact `dp_id` YAML patch via `scripts/apply_yaml_patch.py`
  - Kept `L3.channel.mix` as `Unknown` with `missing_reason: no_local_evidence` because local annual-report `revenue_structure` discloses business-line, regional, and revenue structure percentages, but does not disclose direct/distributor/ecommerce/other channel percentages
  - Filled the 5 L1 nodes as `Known`; parent pass normalized their `data_source` to `llm_derived`
  - `L1.position.growth_rank` uses local 2026Q1 revenue YoY values `13.006451689207127%` and `13.0065%`, with rank left null because no local industry ranking was available
  - Parent pass confirmed no non-target node or non-`nodes` payload changed; child-created YAML formatting drift in `scores.formula` was restored before final gates
- Structural diff after run: exactly 6 target dpids changed (`L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`); non-`nodes` YAML payload unchanged
- Post-run cheap_extract dry-run:
  - `601059.SH`: 0 fillable; 5 Known fields shown in preserved list; `L3.channel.mix` is excluded from dispatch by the no-local-evidence preserve policy
- Scoped closed-loop verifier:
  - `601059.SH`: single-file scoped run has 0 hard violations, 0 soft warnings, 0 excerpt mis-cites, and 0 schema violations
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count: 164058`
- Test gate after batch: `tests/test_prompt_gen_governance.py tests/test_fingerprint.py` passed, 70 tests
- Scope audit after batch: `fillable_total=112068`, `skipped_total=22904`, `cheap_extract=9570`

## Completed batch 43

- Batch target: `FINANCIAL_HIGH_DIVIDEND`, A-share, `cheap_extract`
- Stocks completed: `601077.SH`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Nodes handled: 6
- Fill reason before run: 6 `Unknown` nodes with source fingerprint trigger
- Execution note:
  - Child run used an exact `dp_id` YAML patch via `scripts/apply_yaml_patch.py`
  - Kept `L3.channel.mix` as `Unknown` with `missing_reason: no_local_evidence` because local annual-report `customer_segment` and `revenue_structure` sections are empty, and available bank business-line text does not disclose direct/distributor/ecommerce/other channel percentages
  - Filled the 5 L1 nodes as `Known` with `data_source: llm_derived`
  - `L1.position.growth_rank` uses local 2026Q1 revenue YoY values `8.39436873968323%` and `8.3944%`, with rank left null because no local industry ranking was available
  - Parent pass confirmed no non-target node or non-`nodes` payload changed; child-created YAML formatting drift in `scores.formula` was restored before final gates
- Structural diff after run: exactly 6 target dpids changed (`L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`); non-`nodes` YAML payload unchanged
- Post-run cheap_extract dry-run:
  - `601077.SH`: 0 fillable; 5 Known fields shown in preserved list; `L3.channel.mix` is excluded from dispatch by the no-local-evidence preserve policy
- Scoped closed-loop verifier:
  - `601077.SH`: single-file scoped run has 0 hard violations, 0 soft warnings, 0 excerpt mis-cites, and 0 schema violations
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count: 164053`
- Test gate after batch: `tests/test_prompt_gen_governance.py tests/test_fingerprint.py` passed, 70 tests
- Scope audit after batch: `fillable_total=112062`, `skipped_total=22910`, `cheap_extract=9564`

## Completed batch 44

- Batch target: `FINANCIAL_HIGH_DIVIDEND`, A-share, `cheap_extract`
- Stocks completed: `601099.SH`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Nodes handled: 6
- Fill reason before run: 6 `Unknown` nodes with source fingerprint trigger
- Execution note:
  - Child run used an exact `dp_id` YAML patch via `scripts/apply_yaml_patch.py`
  - Kept `L3.channel.mix` as `Unknown` with `missing_reason: no_local_evidence` because local annual-report `revenue_structure` discloses business-line revenue, while `customer_segment` is empty and no local source discloses direct/distributor/ecommerce/other channel percentages
  - Filled the 5 L1 nodes as `Known` with `data_source: llm_derived`
  - `L1.position.growth_rank` uses local 2026Q1 revenue YoY values `-18.621335603476783%` and `-18.6213%`, with rank left null because no local industry ranking was available
  - Parent pass confirmed no non-target node or non-`nodes` payload changed; child-created YAML formatting drift in `scores.formula` was restored before final gates
- Structural diff after run: exactly 6 target dpids changed (`L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`); non-`nodes` YAML payload unchanged
- Post-run cheap_extract dry-run:
  - `601099.SH`: 0 fillable; 5 Known fields shown in preserved list; `L3.channel.mix` is excluded from dispatch by the no-local-evidence preserve policy
- Scoped closed-loop verifier:
  - `601099.SH`: single-file scoped run has 0 hard violations, 0 soft warnings, 0 excerpt mis-cites, and 0 schema violations
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count: 164048`
- Test gate after batch: `tests/test_prompt_gen_governance.py tests/test_fingerprint.py` passed, 70 tests
- Scope audit after batch: `fillable_total=112056`, `skipped_total=22916`, `cheap_extract=9558`

## Completed batch 45

- Batch target: `FINANCIAL_HIGH_DIVIDEND`, A-share, `cheap_extract`
- Stocks completed: `601128.SH`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Nodes handled: 6
- Fill reason before run: 6 `Unknown` nodes with source fingerprint trigger
- Execution note:
  - Child run used an exact `dp_id` YAML patch via `scripts/apply_yaml_patch.py`
  - Kept `L3.channel.mix` as `Unknown` with `missing_reason: no_local_evidence` because local annual-report `customer_segment`, `revenue_structure`, and `business_overview` sections are empty, while `region_distribution` only discloses regional/business income mix and does not disclose direct/distributor/ecommerce/other channel percentages
  - Filled the 5 L1 nodes as `Known` with `data_source: llm_derived`
  - `L1.position.growth_rank` uses local 2026Q1 revenue YoY values `6.7443239063629274%` and `6.7443%`, with rank left null because no local industry ranking was available
  - Parent pass confirmed no non-target node or non-`nodes` payload changed; no parent data-source normalization or formula restoration was required after the final child output
- Structural diff after run: exactly 6 target dpids changed (`L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`); non-`nodes` YAML payload unchanged
- Post-run cheap_extract dry-run:
  - `601128.SH`: 0 fillable; 5 Known fields shown in preserved list; `L3.channel.mix` is excluded from dispatch by the no-local-evidence preserve policy
- Scoped closed-loop verifier:
  - `601128.SH`: single-file scoped run has 0 hard violations, 0 soft warnings, 0 excerpt mis-cites, and 0 schema violations
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count: 164043`
- Test gate after batch: `tests/test_prompt_gen_governance.py tests/test_fingerprint.py` passed, 70 tests
- Scope audit after batch: `fillable_total=112050`, `skipped_total=22922`, `cheap_extract=9552`

## Completed batch 46

- Batch target: `FINANCIAL_HIGH_DIVIDEND`, A-share, `cheap_extract`
- Stocks completed: `601136.SH`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Nodes handled: 6
- Fill reason before run: 6 `Unknown` nodes with source fingerprint trigger
- Execution note:
  - Child run used an exact `dp_id` YAML patch via `scripts/apply_yaml_patch.py`
  - Kept `L3.channel.mix` as `Unknown` with `missing_reason: no_local_evidence` because local annual-report `revenue_structure` discloses business-line revenue mix (`投资类业务61.48%`, `财富管理类业务19.64%`, `资产管理类业务18.86%`, `投资银行类业务7.46%`), while `customer_segment` is empty and no local source discloses direct/distributor/ecommerce/other channel percentages
  - Filled the 5 L1 nodes as `Known` with `data_source: llm_derived`
  - `L1.position.growth_rank` uses local 2026Q1 revenue YoY values `30.798808708173464%` and `30.7988%`, with rank left null because no local industry ranking was available
  - Parent pass confirmed no non-target node or non-`nodes` payload changed; child-created YAML formatting drift in `scores.formula` was restored before final gates
- Structural diff after run: exactly 6 target dpids changed (`L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`); non-`nodes` YAML payload unchanged
- Post-run cheap_extract dry-run:
  - `601136.SH`: 0 fillable; 5 Known fields shown in preserved list; `L3.channel.mix` is excluded from dispatch by the no-local-evidence preserve policy
- Scoped closed-loop verifier:
  - `601136.SH`: single-file scoped run has 0 hard violations, 0 soft warnings, 0 excerpt mis-cites, and 0 schema violations
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count: 164038`
- Test gate after batch: `tests/test_prompt_gen_governance.py tests/test_fingerprint.py` passed, 70 tests
- Scope audit after batch: `fillable_total=112044`, `skipped_total=22928`, `cheap_extract=9546`

## Completed batch 47

- Batch target: `FINANCIAL_HIGH_DIVIDEND`, A-share, `cheap_extract`
- Stocks completed: `601162.SH`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Nodes handled: 6
- Fill reason before run: 6 `Unknown` nodes with source fingerprint trigger
- Execution note:
  - Child run used an exact `dp_id` YAML patch via `scripts/apply_yaml_patch.py`
  - Kept `L3.channel.mix` as `Unknown` with `missing_reason: no_local_evidence` because local annual-report `revenue_structure` discloses business-line and regional revenue only (`证券经纪业务`, `证券自营业务`, `投资银行业务`, `资产管理业务`, `私募基金业务`; `湖北省内`, `湖北省外`, `总部及子公司`), while `customer_segment` is empty and no local source discloses direct/distributor/ecommerce/other channel percentages
  - Filled the 5 L1 nodes as `Known` with `data_source: llm_derived`
  - `L1.position.growth_rank` uses local 2026Q1 revenue YoY values `-31.064905585472115%` and `-31.0649%`, with rank left null because no local industry ranking was available
  - Child-created YAML formatting drift in `scores.formula` was restored before final gates; parent pass confirmed no non-target node or non-`nodes` payload changed
- Structural diff after run: exactly 6 target dpids changed (`L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`); non-`nodes` YAML payload unchanged
- Post-run cheap_extract dry-run:
  - `601162.SH`: 0 fillable; 5 Known fields shown in preserved list; `L3.channel.mix` is excluded from dispatch by the no-local-evidence preserve policy
- Scoped closed-loop verifier:
  - `601162.SH`: single-file scoped run has 0 hard violations, 0 soft warnings, 0 excerpt mis-cites, and 0 schema violations
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count: 164033`
- Test gate after batch: `tests/test_prompt_gen_governance.py tests/test_fingerprint.py` passed, 70 tests
- Scope audit after batch: `fillable_total=112038`, `skipped_total=22934`, `cheap_extract=9540`

## Completed batch 48

- Batch target: `FINANCIAL_HIGH_DIVIDEND`, A-share, `cheap_extract`
- Stocks completed: `601169.SH`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Nodes handled: 6
- Fill reason before run: 6 `Unknown` nodes with source fingerprint trigger
- Execution note:
  - Child run used exact `dp_id` YAML patches via `scripts/apply_yaml_patch.py`
  - Kept `L3.channel.mix` as `Unknown` with `missing_reason: no_local_evidence` because local annual-report `revenue_structure` discloses only revenue composition and regional distribution (`净利息收入77.72%`, `净手续费及佣金收入5.62%`, `其他净收入16.66%`; `京津冀及环渤海地区78.86%`, `长三角地区10.21%`), with no local direct/distributor/ecommerce/other channel percentages
  - Filled the 5 L1 nodes as `Known` with `data_source: llm_derived`
  - `L1.position.growth_rank` uses local 2026Q1 revenue YoY values `14.43335084953582%` and `14.4334%`, with rank left null because no local industry ranking was available
  - Parent pass restored child-created YAML formatting drift in `scores.formula`; temporary patch artifacts were removed before final gates
- Structural diff after run: exactly 6 target dpids changed (`L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`); non-`nodes` YAML payload unchanged
- Post-run cheap_extract dry-run:
  - `601169.SH`: 0 fillable; 5 Known fields shown in preserved list; `L3.channel.mix` is excluded from dispatch by the no-local-evidence preserve policy
- Scoped closed-loop verifier:
  - `601169.SH`: single-file scoped run has 0 hard violations, 0 soft warnings, 0 excerpt mis-cites, and 0 schema violations
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count: 164028`
- Test gate after batch: `tests/test_prompt_gen_governance.py tests/test_fingerprint.py` passed, 70 tests
- Scope audit after batch: `fillable_total=112032`, `skipped_total=22940`, `cheap_extract=9534`

## Completed batch 49

- Batch target: `FINANCIAL_HIGH_DIVIDEND`, A-share, `cheap_extract`
- Stocks completed: `601187.SH`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Nodes handled: 6
- Fill reason before run: 6 `Unknown` nodes with source fingerprint trigger
- Execution note:
  - Child run used an exact `dp_id` YAML patch via `scripts/apply_yaml_patch.py`
  - Kept `L3.channel.mix` as `Unknown` with `missing_reason: no_local_evidence` because local annual-report business overview discloses business-segment revenue mix (`公司业务61.47%`, `个人业务21.65%`, `资金业务16.77%`, `其他业务0.11%`), while `customer_segment` and `revenue_structure` are empty and no local source discloses direct/distributor/ecommerce/other channel percentages
  - Filled the 5 L1 nodes as `Known`; parent pass normalized their `data_source` to `llm_derived`
  - `L1.position.growth_rank` uses local 2026Q1 revenue YoY values `25.05162992460549%` and `25.0516%`, with rank left null because no local industry ranking was available
  - Parent pass restored child-created YAML formatting drift in `scores.formula`; temporary patch artifacts stayed outside the repo
- Structural diff after run: exactly 6 target dpids changed (`L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`); non-`nodes` YAML payload unchanged
- Post-run cheap_extract dry-run:
  - `601187.SH`: 0 fillable; 5 Known fields shown in preserved list; `L3.channel.mix` is excluded from dispatch by the no-local-evidence preserve policy
- Scoped closed-loop verifier:
  - `601187.SH`: single-file scoped run has 0 hard violations, 0 soft warnings, 0 excerpt mis-cites, and 0 schema violations
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count: 164023`
- Test gate after batch: `tests/test_prompt_gen_governance.py tests/test_fingerprint.py` passed, 70 tests
- Scope audit after batch: `fillable_total=112026`, `skipped_total=22946`, `cheap_extract=9528`

## Completed batch 50

- Batch target: `FINANCIAL_HIGH_DIVIDEND`, A-share, `cheap_extract`
- Stocks completed: `601198.SH`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Nodes handled: 6
- Fill reason before run: 6 `Unknown` nodes with source fingerprint trigger
- Execution note:
  - Child run used an exact `dp_id` YAML patch via `scripts/apply_yaml_patch.py`
  - Kept `L3.channel.mix` as `Unknown` with `missing_reason: no_local_evidence` because local annual-report `revenue_structure` discloses business-line and regional revenue/cost structure (`财富管理业务`, `投资交易业务`, `投资银行业务`, `资产管理业务`, `其他业务`; `福建省内机构`, `福建省外机构`, `公司本部及子公司`), while no local source discloses direct/distributor/ecommerce/other channel percentages
  - Filled the 5 L1 nodes as `Known` with `data_source: llm_derived`
  - `L1.position.growth_rank` uses local 2026Q1 revenue YoY values `-36.10087514028587%` and `-11.5545%`, with rank left null because no local industry ranking was available
  - Parent pass rewrote the child-emitted old `growth_bucket/revenue_yoy_pct` payload to the current `rank/share_pct/trend/source_year` structure; temporary patch artifacts were removed and `scores.formula` matched HEAD before final gates
- Structural diff after run: exactly 6 target dpids changed (`L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`); non-`nodes` YAML payload unchanged
- Post-run cheap_extract dry-run:
  - `601198.SH`: 0 fillable; 5 Known fields shown in preserved list; `L3.channel.mix` is excluded from dispatch by the no-local-evidence preserve policy
- Scoped closed-loop verifier:
  - `601198.SH`: single-file scoped run has 0 hard violations, 0 soft warnings, 0 excerpt mis-cites, and 0 schema violations
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count: 164018`
- Test gate after batch: `tests/test_prompt_gen_governance.py tests/test_fingerprint.py` passed, 70 tests
- Scope audit after batch: `fillable_total=112020`, `skipped_total=22952`, `cheap_extract=9522`

## Completed batch 51

- Batch target: `FINANCIAL_HIGH_DIVIDEND`, A-share, `cheap_extract`
- Stocks completed: `601229.SH`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Nodes handled: 6
- Fill reason before run: 6 `Unknown` nodes with source fingerprint trigger
- Execution note:
  - Child run used an exact `dp_id` YAML patch via `scripts/apply_yaml_patch.py`
  - Kept `L3.channel.mix` as `Unknown` with `missing_reason: no_local_evidence` because local sources disclose banking business and financial-service scope, but no direct/distributor/ecommerce/other channel percentages
  - Filled the 5 L1 nodes as `Known` with `data_source: llm_derived`
  - `L1.position.growth_rank` uses local 2026Q1 revenue YoY values `4.250420437401988%` and `4.2504%`, with rank and share left null because no local industry ranking was available
  - Parent pass rewrote the child-emitted old `growth_yoy_pct` payload to the current `rank/share_pct/trend/source_year/market_size_unit` structure and restored `L3.channel.mix` `last_filled_period` to `2025`
- Structural diff after run: exactly 6 target dpids changed (`L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`); non-`nodes` YAML payload unchanged
- Post-run cheap_extract dry-run:
  - `601229.SH`: 0 fillable; 5 Known fields shown in preserved list; `L3.channel.mix` is excluded from dispatch by the no-local-evidence preserve policy
- Scoped closed-loop verifier:
  - `601229.SH`: single-file scoped run has 0 hard violations, 0 soft warnings, 0 excerpt mis-cites, and 0 schema violations
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count: 164013`
- Test gate after batch: `tests/test_prompt_gen_governance.py tests/test_fingerprint.py` passed, 70 tests
- Scope audit after batch: `fillable_total=112014`, `skipped_total=22958`, `cheap_extract=9516`

## Completed batch 52

- Batch target: `FINANCIAL_HIGH_DIVIDEND`, A-share, `cheap_extract`
- Stocks completed: `601236.SH`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Nodes handled: 6
- Fill reason before run: 6 `Unknown` nodes with source fingerprint trigger
- Execution note:
  - Child run used an exact `dp_id` YAML patch via `scripts/apply_yaml_patch.py`
  - Kept `L3.channel.mix` as `Unknown` with `missing_reason: no_local_evidence` because local annual-report `revenue_structure` discloses business-line and regional revenue/cost structure (`自营投资业务`, `财富管理业务`, `机构服务业务`; `云南省内经纪业务分支机构`, `云南省外经纪业务分支机构`, `公司总部及各子公司`), while no local source discloses direct/distributor/ecommerce/other channel percentages
  - Filled the 5 L1 nodes as `Known`; parent pass normalized their `data_source` to `llm_derived`
  - `L1.position.growth_rank` uses local 2026Q1 revenue YoY values `-21.642841583278766%` and `-21.6428%`, with rank and share left null because no local industry ranking was available
  - Parent pass normalized `L3.channel.mix` no-evidence metadata, rewrote the child-emitted old `growth_yoy_pct` payload to the current `rank/share_pct/trend/source_year/market_size_unit` structure, and restored child-created `scores.formula` formatting drift before final gates
- Structural diff after run: exactly 6 target dpids changed (`L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`); non-`nodes` YAML payload unchanged
- Post-run cheap_extract dry-run:
  - `601236.SH`: 0 fillable; 5 Known fields shown in preserved list; `L3.channel.mix` is excluded from dispatch by the no-local-evidence preserve policy
- Scoped closed-loop verifier:
  - `601236.SH`: single-file scoped run has 0 hard violations, 0 soft warnings, 0 excerpt mis-cites, and 0 schema violations
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count: 164008`
- Test gate after batch: `tests/test_prompt_gen_governance.py tests/test_fingerprint.py` passed, 70 tests
- Scope audit after batch: `fillable_total=112008`, `skipped_total=22964`, `cheap_extract=9510`

## Completed batch 53

- Batch target: `FINANCIAL_HIGH_DIVIDEND`, A-share, `cheap_extract`
- Stocks completed: `601377.SH`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Nodes handled: 6
- Fill reason before run: 6 `Unknown` nodes with source fingerprint trigger
- Execution note:
  - Child run used an exact `dp_id` YAML patch via `scripts/apply_yaml_patch.py`
  - Kept `L3.channel.mix` as `Unknown` with `missing_reason: no_local_evidence` because local annual-report `revenue_structure` discloses business-line, regional and customer-context facts (`证券及期货经纪业务`, `资产管理业务`, `机构服务业务`, `自营投资业务`, `海外业务`; `福建地区`, `上海地区`, `其他地区`, `公司本部及子公司`; 前五大客户收入占比不超过 10%), while no local source discloses direct/distributor/ecommerce/other channel percentages
  - Filled the 5 L1 nodes as `Known` with `data_source: llm_derived`
  - `L1.position.growth_rank` uses local 2026Q1 revenue YoY values `-4.5733662865342%` and `13.4374%`; parent pass kept rank and share null and marked the trend as `mixed` because the two local revenue-growth sources disagree and no local industry ranking was available
  - Parent pass narrowed L1 tag `value` payloads back to the current `tags + notes` shape and restored child-created `scores.formula` formatting drift before final gates
- Structural diff after run: exactly 6 target dpids changed (`L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`); non-`nodes` YAML payload unchanged
- Post-run cheap_extract dry-run:
  - `601377.SH`: 0 fillable; 5 Known fields shown in preserved list; `L3.channel.mix` is excluded from dispatch by the no-local-evidence preserve policy
- Scoped closed-loop verifier:
  - `601377.SH`: single-file scoped run has 0 hard violations, 0 soft warnings, 0 excerpt mis-cites, and 0 schema violations
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count: 164003`
- Test gate after batch: `tests/test_prompt_gen_governance.py tests/test_fingerprint.py` passed, 70 tests
- Scope audit after batch: `fillable_total=112002`, `skipped_total=22970`, `cheap_extract=9504`

## Completed batch 54

- Batch target: `FINANCIAL_HIGH_DIVIDEND`, A-share, `cheap_extract`
- Stocks completed: `601555.SH`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Nodes handled: 6
- Fill reason before run: 6 `Unknown` nodes with source fingerprint trigger
- Execution note:
  - Child run used an exact `dp_id` YAML patch via `scripts/apply_yaml_patch.py`
  - Kept `L3.channel.mix` as `Unknown` with `missing_reason: no_local_evidence` because local annual-report `revenue_structure` discloses business-line and regional revenue structure (`财富管理业务`, `投资银行业务`, `投资交易业务`, `资产管理业务`; `江苏省内`, `江苏省外`, `总部及子公司`), while no local source discloses direct/distributor/ecommerce/other channel percentages
  - Filled the 5 L1 nodes as `Known` with `data_source: llm_derived`
  - `L1.position.growth_rank` uses local 2026Q1 revenue YoY values `-33.759595382528936%` and `-9.4536%`; parent pass kept rank and share null, marked the trend as `decline`, and did not fabricate an industry ranking
  - Parent pass normalized `L3.channel.mix` no-evidence metadata, rewrote the child-emitted old `revenue_yoy_pct`/`rank_bucket` payload to the current `rank/share_pct/trend/source_year/market_size_unit/evidence_summary/notes` structure, and restored child-created `scores.formula` formatting drift before final gates
- Structural diff after run: exactly 6 target dpids changed (`L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`); non-`nodes` YAML payload unchanged
- Post-run cheap_extract dry-run:
  - `601555.SH`: 0 fillable; 5 Known fields shown in preserved list; `L3.channel.mix` is excluded from dispatch by the no-local-evidence preserve policy
- Scoped closed-loop verifier:
  - `601555.SH`: single-file scoped run has 0 hard violations, 0 soft warnings, 0 excerpt mis-cites, and 0 schema violations
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count: 163998`
- Test gate after batch: `tests/test_prompt_gen_governance.py tests/test_fingerprint.py` passed, 70 tests
- Scope audit after batch: `fillable_total=111996`, `skipped_total=22976`, `cheap_extract=9498`

## Completed batch 55

- Batch target: `FINANCIAL_HIGH_DIVIDEND`, A-share, `cheap_extract`
- Stocks completed: `601577.SH`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Nodes handled: 6
- Fill reason before run: 6 `Unknown` nodes with source fingerprint trigger
- Execution note:
  - Child run used an exact `dp_id` YAML patch via `scripts/apply_yaml_patch.py`
  - Kept `L3.channel.mix` as `Unknown` with `missing_reason: no_local_evidence` because local annual-report `customer_segment`, `revenue_structure`, and `region_distribution` sections are empty, and local business text only discloses banking business scope and service network, not direct/distributor/ecommerce/other channel percentages
  - Filled the 5 L1 nodes as `Known` with `data_source: llm_derived`
  - `L1.position.growth_rank` uses local 2026Q1 revenue YoY values `5.6354317012693835%` and `5.6354%`; rank and share remain null because no local industry ranking denominator was available
  - Child patch already used the current `rank/share_pct/trend/source_year/market_size_unit/evidence_summary/notes` structure and restored child-created `scores.formula` formatting drift before final gates
- Structural diff after run: exactly 6 target dpids changed (`L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`); non-`nodes` YAML payload unchanged
- Post-run cheap_extract dry-run:
  - `601577.SH`: 0 fillable; 5 Known fields shown in preserved list; `L3.channel.mix` is excluded from dispatch by the no-local-evidence preserve policy
- Scoped closed-loop verifier:
  - `601577.SH`: single-file scoped run has 0 hard violations, 0 soft warnings, 0 excerpt mis-cites, and 0 schema violations
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count: 163993`
- Test gate after batch: `tests/test_prompt_gen_governance.py tests/test_fingerprint.py` passed, 70 tests
- Scope audit after batch: `fillable_total=111990`, `skipped_total=22982`, `cheap_extract=9492`

## Completed batch 56

- Batch target: `FINANCIAL_HIGH_DIVIDEND`, A-share, `cheap_extract`
- Stocks completed: `601665.SH`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Nodes handled: 6
- Fill reason before run: 6 `Unknown` nodes with source fingerprint trigger
- Execution note:
  - Child run used an exact `dp_id` YAML patch via `scripts/apply_yaml_patch.py`
  - Kept `L3.channel.mix` as `Unknown` with `missing_reason: no_local_evidence` because local annual-report `customer_segment`, `revenue_structure`, and `region_distribution` sections are empty, and local business overview only discloses banking business lines, customer activity, and transaction-scale facts, not direct/distributor/ecommerce/other channel percentages
  - Filled the 5 L1 nodes as `Known` with `data_source: llm_derived`
  - `L1.position.growth_rank` uses local 2026Q1 revenue YoY values `13.015864189320054%` and `13.0159%`; parent pass kept rank and share null, marked the trend as `modest_growth`, and did not fabricate an industry ranking
  - Parent pass removed an unnecessary local industry-overlay citation from `L1.position.growth_rank`, normalized the trend/notes wording to the current `rank/share_pct/trend/source_year/market_size_unit/evidence_summary/notes` structure, and confirmed child-created `scores.formula` formatting drift was restored before final gates
- Structural diff after run: exactly 6 target dpids changed (`L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`); non-`nodes` YAML payload unchanged
- Post-run cheap_extract dry-run:
  - `601665.SH`: 0 fillable; 5 Known fields shown in preserved list; `L3.channel.mix` is excluded from dispatch by the no-local-evidence preserve policy
- Scoped closed-loop verifier:
  - `601665.SH`: single-file scoped run has 0 hard violations, 0 soft warnings, 0 excerpt mis-cites, and 0 schema violations
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count: 163988`
- Test gate after batch: `tests/test_prompt_gen_governance.py tests/test_fingerprint.py` passed, 70 tests
- Diff hygiene after batch: `git diff --check` passed
- Scope audit after batch: `fillable_total=111984`, `skipped_total=22988`, `cheap_extract=9486`

## Completed batch 57

- Batch target: `FINANCIAL_HIGH_DIVIDEND`, A-share, `cheap_extract`
- Stocks completed: `601696.SH`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Nodes handled: 6
- Fill reason before run: 6 `Unknown` nodes with source fingerprint trigger
- Execution note:
  - Child run used an exact `dp_id` YAML patch via `scripts/apply_yaml_patch.py`
  - Kept `L3.channel.mix` as `Unknown` with `missing_reason: no_local_evidence` because local annual-report revenue-structure text discloses business-line and regional revenue (`投资银行业务`, `证券经纪业务`, `资产管理业务`, `证券自营业务`, `期货业务`, `私募股权投资业务`; multiple province/city rows), but not direct/distributor/ecommerce/other channel percentages
  - Filled the 5 L1 nodes as `Known` with `data_source: llm_derived`
  - `L1.position.growth_rank` uses local 2026Q1 revenue YoY values `22.57453371396495%` and `22.5745%`; parent pass kept rank and share null, marked the trend as `modest_growth`, and did not fabricate an industry ranking
  - Parent pass normalized the child-emitted `positive` trend and notes to the current `rank/share_pct/trend/source_year/market_size_unit/evidence_summary/notes` structure, then confirmed `scores.formula` formatting drift was restored before final gates
- Structural diff after run: exactly 6 target dpids changed (`L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`); non-`nodes` YAML payload unchanged
- Post-run cheap_extract dry-run:
  - `601696.SH`: 0 fillable; 5 Known fields shown in preserved list; `L3.channel.mix` is excluded from dispatch by the no-local-evidence preserve policy
- Scoped closed-loop verifier:
  - `601696.SH`: single-file scoped run has 0 hard violations, 0 soft warnings, 0 excerpt mis-cites, and 0 schema violations
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count: 163983`
- Test gate after batch: `tests/test_prompt_gen_governance.py tests/test_fingerprint.py` passed, 70 tests
- Diff hygiene after batch: `git diff --check` passed
- Scope audit after batch: `fillable_total=111978`, `skipped_total=22994`, `cheap_extract=9480`

## Completed batch 58

- Batch target: `FINANCIAL_HIGH_DIVIDEND`, A-share, `cheap_extract`
- Stocks completed: `601788.SH`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Nodes handled: 6
- Fill reason before run: 6 `Unknown` nodes with source fingerprint trigger
- Execution note:
  - Child run used an exact `dp_id` YAML patch via `scripts/apply_yaml_patch.py`; parent interrupted the child after the patch landed because it had moved into an unnecessary full-stock verifier scan
  - Kept `L3.channel.mix` as `Unknown` with `missing_reason: no_local_evidence` because local annual-report revenue-structure text discloses income source, business-line, and regional revenue structure, but not direct/distributor/ecommerce/other channel percentages
  - Filled the 5 L1 nodes as `Known` with `data_source: llm_derived`
  - `L1.position.growth_rank` uses local 2026Q1 revenue YoY values `23.100689392210754%` and `23.1007%`; parent pass kept rank and share null, marked the trend as `modest_growth`, and did not fabricate an industry ranking
  - Parent pass normalized the child-emitted `growth_pct` and free-text trend to the current `rank/share_pct/trend/source_year/market_size_unit/evidence_summary/notes` structure, removed an unnecessary local industry-overlay citation, and restored `scores.formula` formatting before final gates
- Structural diff after run: exactly 6 target dpids changed (`L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`); non-`nodes` YAML payload unchanged
- Post-run cheap_extract dry-run:
  - `601788.SH`: 0 fillable; 5 Known fields shown in preserved list; `L3.channel.mix` is excluded from dispatch by the no-local-evidence preserve policy
- Scoped closed-loop verifier:
  - `601788.SH`: single-file scoped run has 0 hard violations, 0 soft warnings, 0 excerpt mis-cites, and 0 schema violations
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count: 163978`
- Test gate after batch: `tests/test_prompt_gen_governance.py tests/test_fingerprint.py` passed, 70 tests
- Diff hygiene after batch: `git diff --check` passed
- Scope audit after batch: `fillable_total=111972`, `skipped_total=23000`, `cheap_extract=9474`

## Completed batch 59

- Batch target: `FINANCIAL_HIGH_DIVIDEND`, A-share, `cheap_extract`
- Stocks completed: `601825.SH`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Nodes handled: 6
- Fill reason before run: 6 `Unknown` nodes with source fingerprint trigger
- Execution note:
  - Child run used an exact `dp_id` YAML patch via `scripts/apply_yaml_patch.py`
  - Kept `L3.channel.mix` as `Unknown` with `missing_reason: no_local_evidence` because local evidence only discloses bank business lines and general business scope, not direct/distributor/ecommerce/other channel percentages
  - Filled the 5 L1 nodes as `Known` with `data_source: llm_derived`
  - `L1.position.growth_rank` uses local 2026Q1 revenue YoY values `1.2313689873793026%` and `1.2314%`; parent pass kept rank and share null, marked the trend as `modest_growth`, and did not fabricate an industry ranking
  - Parent pass normalized child-emitted report periods and growth evidence quality to the current `rank/share_pct/trend/source_year/market_size_unit/evidence_summary/notes` structure before final gates
- Structural diff after run: exactly 6 target dpids changed (`L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`); non-`nodes` YAML payload unchanged
- Post-run cheap_extract dry-run:
  - `601825.SH`: 0 fillable; 5 Known fields shown in preserved list; `L3.channel.mix` is excluded from dispatch by the no-local-evidence preserve policy
- Scoped closed-loop verifier:
  - `601825.SH`: single-file scoped run has 0 hard violations, 0 soft warnings, 0 excerpt mis-cites, and 0 schema violations
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count: 163973`
- Test gate after batch: `tests/test_prompt_gen_governance.py tests/test_fingerprint.py` passed, 70 tests
- Diff hygiene after batch: `git diff --check` passed
- Scope audit after batch: `fillable_total=111966`, `skipped_total=23006`, `cheap_extract=9468`

## Completed batch 60

- Batch target: `FINANCIAL_HIGH_DIVIDEND`, A-share, `cheap_extract`
- Stocks completed: `601838.SH`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Nodes handled: 6
- Fill reason before run: 6 `Unknown` nodes with source fingerprint trigger
- Execution note:
  - Child run used an exact `dp_id` YAML patch via `scripts/apply_yaml_patch.py --strict-schema`
  - Kept `L3.channel.mix` as `Unknown` with `missing_reason: no_local_evidence` because local evidence only discloses bank business lines, business scope, and general annual-report sections, not direct/distributor/ecommerce/other channel percentages
  - Filled the 5 L1 nodes as `Known` with `data_source: llm_derived`
  - `L1.position.growth_rank` uses local 2026Q1 revenue YoY values `6.542798987787435%` and `6.5428%`; parent pass kept rank and share null, marked the trend as `modest_growth`, and did not fabricate an industry ranking
  - Parent pass normalized `L3.channel.mix` report period to `2025`, downgraded growth evidence quality to `low` with `confidence: 0.52`, removed the child-emitted non-business moat tag `毛利率本地缺失`, and kept `scores.formula` formatting stable before final gates
- Structural diff after run: exactly 6 target dpids changed (`L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`); non-`nodes` YAML payload unchanged
- Post-run cheap_extract dry-run:
  - `601838.SH`: 0 fillable; 5 Known fields shown in preserved list; `L3.channel.mix` is excluded from dispatch by the no-local-evidence preserve policy
- Scoped closed-loop verifier:
  - `601838.SH`: single-file scoped run has 0 hard violations, 0 soft warnings, 0 excerpt mis-cites, and 0 schema violations
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count: 163968`
- Test gate after batch: `tests/test_prompt_gen_governance.py tests/test_fingerprint.py` passed, 70 tests
- Diff hygiene after batch: `git diff --check` passed
- Scope audit after batch: `fillable_total=111960`, `skipped_total=23012`, `cheap_extract=9462`

## Completed batch 61

- Batch target: `FINANCIAL_HIGH_DIVIDEND`, A-share, `cheap_extract`
- Stocks completed: `601878.SH`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Nodes handled: 6
- Fill reason before run: 6 `Unknown` nodes with source fingerprint trigger
- Execution note:
  - Child run used an exact `dp_id` YAML patch via `scripts/apply_yaml_patch.py --strict-schema`; parent interrupted the child after the patch landed because its scoped verifier command used an invalid temp directory shape and then hit policy rejection
  - Kept `L3.channel.mix` as `Unknown` with `missing_reason: no_local_evidence` because local evidence disclosed business-line and regional revenue structure, not direct/distributor/ecommerce/other channel percentages
  - Filled the 5 L1 nodes as `Known` with `data_source: llm_derived`
  - `L1.position.growth_rank` uses local 2026Q1 revenue YoY values `-21.2043865663857%` and `40.816%`; parent pass marked the trend as `mixed`, kept rank and share null, and did not fabricate an industry ranking
  - Parent pass normalized child-emitted old growth keys (`growth_pct`, `growth_tier`) to the current `rank/share_pct/trend/source_year/market_size_unit/evidence_summary/notes` structure, set 5 L1 `last_filled_period` values to `2026Q1`, downgraded growth evidence quality to `low`, and kept `scores.formula` formatting stable before final gates
- Structural diff after run: exactly 6 target dpids changed (`L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`); non-`nodes` YAML payload unchanged
- Post-run cheap_extract dry-run:
  - `601878.SH`: 0 fillable; 5 Known fields shown in preserved list; `L3.channel.mix` is excluded from dispatch by the no-local-evidence preserve policy
- Scoped closed-loop verifier:
  - `601878.SH`: single-file scoped run has 0 hard violations, 0 soft warnings, 0 excerpt mis-cites, and 0 schema violations
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count: 163963`
- Test gate after batch: `tests/test_prompt_gen_governance.py tests/test_fingerprint.py` passed, 70 tests
- Diff hygiene after batch: `git diff --check` passed
- Scope audit after batch: `fillable_total=111954`, `skipped_total=23018`, `cheap_extract=9456`

## Completed batch 62

- Batch target: `FINANCIAL_HIGH_DIVIDEND`, A-share, `cheap_extract`
- Stocks completed: `601901.SH`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Nodes handled: 6
- Fill reason before run: 6 `Unknown` nodes with source fingerprint trigger
- Execution note:
  - Child run used an exact `dp_id` YAML patch via `scripts/apply_yaml_patch.py --strict-schema`; parent interrupted the child after the patch landed to avoid extra unrelated operations
  - Kept `L3.channel.mix` as `Unknown` with `missing_reason: no_local_evidence` because local evidence disclosed business-line services and "线上线下结合", but not direct/distributor/ecommerce/other channel percentages
  - Filled the 5 L1 nodes as `Known` with `data_source: llm_derived`
  - `L1.position.growth_rank` uses local 2026Q1 revenue YoY values `14.695238896077237%` and `14.6952%`; parent pass marked the trend as `modest_growth`, kept rank and share null, and did not fabricate an industry ranking
  - Parent pass normalized child-emitted old growth keys (`rank_bucket`, `revenue_yoy_pct`, `trend: up`) to the current `rank/share_pct/trend/source_year/market_size_unit/evidence_summary/notes` structure, set report periods to `2025` for `L3.channel.mix` and `2026Q1` for the 5 L1 nodes, downgraded growth evidence quality to `low`, deleted the temporary patch file, and kept `scores.formula` formatting stable before final gates
- Structural diff after run: exactly 6 target dpids changed (`L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`); non-`nodes` YAML payload unchanged
- Post-run cheap_extract dry-run:
  - `601901.SH`: 0 fillable; 5 Known fields shown in preserved list; `L3.channel.mix` is excluded from dispatch by the no-local-evidence preserve policy
- Scoped closed-loop verifier:
  - `601901.SH`: single-file scoped run has 0 hard violations, 0 soft warnings, 0 excerpt mis-cites, and 0 schema violations
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count: 163958`
- Test gate after batch: `tests/test_prompt_gen_governance.py tests/test_fingerprint.py` passed, 70 tests
- Diff hygiene after batch: `git diff --check` passed
- Scope audit after batch: `fillable_total=111948`, `skipped_total=23024`, `cheap_extract=9450`

## Completed batch 63

- Batch target: `FINANCIAL_HIGH_DIVIDEND`, A-share, `cheap_extract`
- Stocks completed: `601916.SH`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Nodes handled: 6
- Fill reason before run: 6 `Unknown` nodes with source fingerprint trigger
- Execution note:
  - Child run used an exact `dp_id` YAML patch via `scripts/apply_yaml_patch.py --strict-schema`; parent interrupted the child after the patch landed and took over verification
  - Kept `L3.channel.mix` as `Unknown` with `missing_reason: no_local_evidence` because local evidence disclosed bank business scope, comprehensive financial services, and branch coverage, but not direct/distributor/ecommerce/other channel percentages
  - Filled the 5 L1 nodes as `Known` with `data_source: llm_derived`
  - `L1.position.growth_rank` uses local 2026Q1 revenue YoY values `0.4969307220111079%` and `0.4969%`; parent pass marked the trend as `modest_growth`, kept rank and share null, and did not fabricate an industry ranking
  - Parent pass normalized child-emitted `L3.channel.mix` metadata back to no-evidence Unknown policy, set report periods to `2025` for `L3.channel.mix` and `2026Q1` for the 5 L1 nodes, changed growth evidence quality to `low` with `confidence: 0.52`, replaced child `trend: slight_growth` with the current `modest_growth` vocabulary, removed the gross-margin-missing note from moat tags, and kept `scores.formula` formatting stable before final gates
- Structural diff after run: exactly 6 target dpids changed (`L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`); non-`nodes` YAML payload unchanged
- Post-run cheap_extract dry-run:
  - `601916.SH`: 0 fillable; 5 Known fields shown in preserved list; `L3.channel.mix` is excluded from dispatch by the no-local-evidence preserve policy
- Scoped closed-loop verifier:
  - `601916.SH`: single-file scoped run has 0 hard violations, 0 soft warnings, 0 excerpt mis-cites, and 0 schema violations
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count: 163953`
- Test gate after batch: `tests/test_prompt_gen_governance.py tests/test_fingerprint.py` passed, 70 tests
- Diff hygiene after batch: `git diff --check` passed
- Scope audit after batch: `fillable_total=111942`, `skipped_total=23030`, `cheap_extract=9444`

## Completed batch 64

- Batch target: `FINANCIAL_HIGH_DIVIDEND`, A-share, `cheap_extract`
- Stocks completed: `601963.SH`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Nodes handled: 6
- Fill reason before run: 6 `Unknown` nodes with source fingerprint trigger
- Execution note:
  - Child run used an exact `dp_id` YAML patch via `scripts/apply_yaml_patch.py --strict-schema`; parent interrupted after the patch landed and completed verification
  - Kept `L3.channel.mix` as `Unknown` with `missing_reason: no_local_evidence` because local evidence disclosed company banking, retail banking, funding-market business, and business scope, but not direct/distributor/ecommerce/other channel percentages
  - Filled the 5 L1 nodes as `Known` with `data_source: llm_derived`
  - `L1.position.growth_rank` uses local 2026Q1 revenue YoY values `11.568888720111513%` and `11.5689%`; parent pass marked the trend as `modest_growth`, kept rank and share null, and did not fabricate an industry ranking
  - Parent pass set report periods to `2025` for `L3.channel.mix` and `2026Q1` for the 5 L1 nodes, changed growth evidence quality to `low` with `confidence: 0.52`, replaced child `trend: growth` with the current `modest_growth` vocabulary, removed the gross-margin-missing note from moat tags, deleted the temporary patch file, and kept `scores.formula` formatting stable before final gates
- Structural diff after run: exactly 6 target dpids changed (`L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`); non-`nodes` YAML payload unchanged
- Post-run cheap_extract dry-run:
  - `601963.SH`: 0 fillable; 5 Known fields shown in preserved list; `L3.channel.mix` is excluded from dispatch by the no-local-evidence preserve policy
- Scoped closed-loop verifier:
  - `601963.SH`: single-file scoped run has 0 hard violations, 0 soft warnings, 0 excerpt mis-cites, and 0 schema violations
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count: 163948`
- Test gate after batch: `tests/test_prompt_gen_governance.py tests/test_fingerprint.py` passed, 70 tests
- Diff hygiene after batch: `git diff --check` passed
- Scope audit after batch: `fillable_total=111936`, `skipped_total=23036`, `cheap_extract=9438`

## Completed batch 65

- Batch target: `FINANCIAL_HIGH_DIVIDEND`, A-share, `cheap_extract`
- Stocks completed: `601990.SH`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Nodes handled: 6
- Fill reason before run: 6 `Unknown` nodes with source fingerprint trigger
- Execution note:
  - Child run generated an exact `dp_id` YAML patch and applied it via `scripts/apply_yaml_patch.py --strict-schema`; parent interrupted after the patch landed and after child started a full-repo verifier
  - Kept `L3.channel.mix` as `Unknown` with `missing_reason: no_local_evidence` because local evidence disclosed securities/futures brokerage, securities investment, investment banking, asset management, investment management, and related licensed services, but not direct/distributor/ecommerce/other channel percentages
  - Filled the 5 L1 nodes as `Known` with `data_source: llm_derived`
  - `L1.position.growth_rank` uses local 2026Q1 revenue YoY values `-7.219417091911458%` and `-4.45%`; parent pass marked the trend as `decline`, kept rank and share null, and did not fabricate an industry ranking
  - Parent pass added missing `data_source: llm_derived` on the 5 L1 nodes, set report periods to `2025` for `L3.channel.mix` and `2026Q1` for the 5 L1 nodes, changed growth confidence to `0.52`, replaced child `trend: declining` with the current `decline` vocabulary, removed the gross-margin-missing note from moat tags, expanded growth excerpts to full local JSON snippets, and kept `scores.formula` formatting stable before final gates
- Structural diff after run: exactly 6 target dpids changed (`L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`); non-`nodes` YAML payload unchanged
- Post-run cheap_extract dry-run:
  - `601990.SH`: 0 fillable; 5 Known fields shown in preserved list; `L3.channel.mix` is excluded from dispatch by the no-local-evidence preserve policy
- Scoped closed-loop verifier:
  - `601990.SH`: single-file scoped run has 0 hard violations, 0 soft warnings, 0 excerpt mis-cites, and 0 schema violations
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count: 163943`
- Test gate after batch: `tests/test_prompt_gen_governance.py tests/test_fingerprint.py` passed, 70 tests
- Diff hygiene after batch: `git diff --check` passed
- Scope audit after batch: `fillable_total=111930`, `skipped_total=23042`, `cheap_extract=9432`

## Completed batch 66

- Batch target: `FINANCIAL_HIGH_DIVIDEND`, A-share, `cheap_extract`
- Stocks completed: `601997.SH`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Nodes handled: 6
- Fill reason before run: 6 `Unknown` nodes with source fingerprint trigger
- Execution note:
  - Child run consumed the generated GPT-5.5 prompt and local evidence but did not land a patch in a reasonable time; parent interrupted it and completed the 6-node fill manually from the generated prompt's local SQLite evidence
  - Kept `L3.channel.mix` as `Unknown` with `missing_reason: no_local_evidence` because local evidence disclosed company financial, personal financial, funding, other banking businesses, and Guizhou county network coverage, but not direct/distributor/ecommerce/other channel percentages
  - Filled the 5 L1 nodes as `Known` with `data_source: llm_derived`
  - `L1.position.growth_rank` uses local 2026Q1 revenue YoY values `14.596221102700577%` and `14.5962%`; parent pass marked the trend as `modest_growth`, kept rank and share null, and did not fabricate an industry ranking
  - Parent pass initially caught and corrected an over-broad patch that had touched `L0.demand.terminal` and `L3.region.tier_mix`; final structural diff is limited to the 6 intended dpids
- Structural diff after run: exactly 6 target dpids changed (`L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`); non-`nodes` YAML payload unchanged
- Post-run cheap_extract dry-run:
  - `601997.SH`: 0 fillable; 5 Known fields shown in preserved list; `L3.channel.mix` is excluded from dispatch by the no-local-evidence preserve policy
- Scoped closed-loop verifier:
  - `601997.SH`: single-file scoped run has 0 hard violations, 0 soft warnings, 0 excerpt mis-cites, and 0 schema violations
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count: 163938`
- Test gate after batch: `tests/test_prompt_gen_governance.py tests/test_fingerprint.py` passed, 70 tests
- Diff hygiene after batch: `git diff --check` passed
- Scope audit after batch: `fillable_total=111924`, `skipped_total=23048`, `cheap_extract=9426`

## Completed batch 67

- Batch target: `FINANCIAL_HIGH_DIVIDEND`, A-share, `cheap_extract`
- Stocks completed: `603093.SH`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Nodes handled: 6
- Fill reason before run: 6 `Unknown` nodes with source fingerprint trigger
- Execution note:
  - Child run consumed the generated GPT-5.5 prompt and local evidence, but expanded into broad local sample/schema reads and did not land a patch in a reasonable time; parent interrupted it and completed the 6-node fill manually from the generated prompt's local SQLite and annual-report evidence
  - Kept `L3.channel.mix` as `Unknown` with `missing_reason: no_local_evidence` because local evidence disclosed期货经纪、财富管理、风险管理、境外金融服务、其他业务收入结构和地区结构, but not direct/distributor/ecommerce/other channel percentages
  - Filled the 5 L1 nodes as `Known` with `data_source: llm_derived`
  - `L1.position.growth_rank` uses local 2026Q1 revenue YoY values `-18.845564400714245%` and `60.6553%`; parent pass marked the trend as `mixed`, kept rank and share null, and did not fabricate an industry ranking
  - Parent pass restored `scores.formula` formatting after `scripts/apply_yaml_patch.py` safe-dump wrapping
- Structural diff after run: exactly 6 target dpids changed (`L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`); non-`nodes` YAML payload unchanged
- Post-run cheap_extract dry-run:
  - `603093.SH`: 0 fillable; 5 Known fields shown in preserved list; `L3.channel.mix` is excluded from dispatch by the no-local-evidence preserve policy
- Scoped closed-loop verifier:
  - `603093.SH`: single-file scoped run has 0 hard violations, 0 soft warnings, 0 excerpt mis-cites, and 0 schema violations
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count: 163933`
- Test gate after batch: `tests/test_prompt_gen_governance.py tests/test_fingerprint.py` passed, 70 tests
- Diff hygiene after batch: `git diff --check` passed
- Scope audit after batch: `fillable_total=111918`, `skipped_total=23054`, `cheap_extract=9420`

## Completed batch 68

- Batch target: `FINANCIAL_HIGH_DIVIDEND`, A-share, `cheap_extract`
- Stocks completed: `603300.SH`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Nodes handled: 6 cheap_extract targets, plus 2 preserved-node schema cleanups in the same overlay
- Fill reason before run: 6 `Unknown` nodes with source fingerprint trigger
- Execution note:
  - Child run generated and applied a 6-node patch via `scripts/apply_yaml_patch.py --strict-schema`; parent interrupted after the patch landed to prevent further broad validation work
  - Parent pass changed `L3.channel.mix` from child `Unknown` to `Known` because the 2025 annual report discloses sales-mode revenue with only `直销`, and direct sales revenue equals the sales-mode total; final value is `direct_pct=100.0`, `distributor_pct=0.0`, `ecommerce_pct=0.0`, `others_pct=0.0`
  - Filled the 5 L1 nodes as `Known` with `data_source: llm_derived`
  - `L1.position.growth_rank` uses local 2026Q1 revenue YoY values `17.877320833603385%` and `17.8773%`; parent pass marked the trend as `modest_growth`, kept rank and share null, and did not fabricate an industry ranking
  - Parent pass normalized two pre-existing preserved nodes so the scoped verifier would be fully clean: `L3.product.portfolio` moved `source` into `evidence_summary`, and `L3.customer.concentration` moved `top5_pct` into `top5_revenue_pct` while preserving the supplier concentration note
  - Parent pass restored `scores.formula` formatting after `scripts/apply_yaml_patch.py` safe-dump wrapping
- Structural diff after run: 8 dpids changed: 6 target dpids (`L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`) plus 2 schema cleanup dpids (`L3.product.portfolio`, `L3.customer.concentration`); non-`nodes` YAML payload unchanged
- Post-run cheap_extract dry-run:
  - `603300.SH`: 0 fillable; 6 target fields shown in preserved list
- Scoped closed-loop verifier:
  - `603300.SH`: single-file scoped run has 0 hard violations, 0 soft warnings, 0 excerpt mis-cites, and 0 schema violations
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count: 163927`
- Test gate after batch: `tests/test_prompt_gen_governance.py tests/test_fingerprint.py` passed, 70 tests
- Diff hygiene after batch: `git diff --check` passed
- Scope audit after batch: `fillable_total=111912`, `skipped_total=23060`, `cheap_extract=9414`

## Completed batch 69

- Batch target: `FINANCIAL_HIGH_DIVIDEND`, A-share, `cheap_extract`
- Stocks completed: `603693.SH`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Nodes handled: 6 cheap_extract targets, plus 1 preserved-node schema cleanup in the same overlay
- Fill reason before run: 6 `Unknown` nodes with source fingerprint trigger
- Execution note:
  - Child run consumed the generated GPT-5.5 prompt and local evidence, then expanded into broad local sample/schema reads without landing a patch; parent interrupted it and completed the 6-node fill manually from the generated prompt's local SQLite and annual-report evidence
  - Filled `L3.channel.mix` as `Known` because the 2025 annual report discloses sales-mode revenue with only `直销`; final value is `direct_pct=100.0`, `distributor_pct=0.0`, `ecommerce_pct=0.0`, `others_pct=0.0`
  - Filled the 5 L1 nodes as `Known` with `data_source: llm_derived`
  - `L1.position.growth_rank` uses local 2026Q1 revenue YoY values `-11.586834454567619%` and `-11.5868%`; parent pass marked the trend as `decline`, kept rank and share null, and did not fabricate an industry ranking
  - Parent pass normalized one pre-existing preserved node so the scoped verifier would be fully clean: `L3.customer.concentration` moved `top5_pct` into `top5_revenue_pct` and preserved the supplier concentration note
  - Parent pass restored `scores.formula` formatting after `scripts/apply_yaml_patch.py` safe-dump wrapping
- Structural diff after run: 7 dpids changed: 6 target dpids (`L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`) plus 1 schema cleanup dpid (`L3.customer.concentration`); non-`nodes` YAML payload unchanged
- Post-run cheap_extract dry-run:
  - `603693.SH`: 0 fillable; 6 target fields shown in preserved list
- Scoped closed-loop verifier:
  - `603693.SH`: single-file scoped run has 0 hard violations, 0 soft warnings, 0 excerpt mis-cites, and 0 schema violations
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count: 163921`
- Test gate after batch: `tests/test_prompt_gen_governance.py tests/test_fingerprint.py` passed, 70 tests
- Diff hygiene after batch: `git diff --check` passed
- Scope audit after batch: `fillable_total=111906`, `skipped_total=23066`, `cheap_extract=9408`

## Completed batch 70

- Batch target: `FINANCIAL_HIGH_DIVIDEND`, A-share, `cheap_extract`
- Stocks completed: `605090.SH`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Nodes handled: 6 cheap_extract targets, plus 2 preserved-node schema cleanups in the same overlay
- Fill reason before run: 6 `Unknown` nodes with source fingerprint trigger
- Execution note:
  - Child run consumed the generated GPT-5.5 prompt and local evidence, then expanded into broad local source/spec reads without landing a patch; parent interrupted it and completed the 6-node fill manually from local SQLite and annual-report evidence
  - Kept `L3.channel.mix` as `Unknown` with `missing_reason: no_local_evidence` because the local annual report disclosed industry, product, region revenue structure and customer matching logic, but did not disclose direct/distributor/ecommerce/other channel percentages
  - Filled the 5 L1 nodes as `Known` with `data_source: llm_derived`
  - `L1.position.growth_rank` uses local 2026Q1 revenue YoY values `-17.982020884355425%` and `-17.982%`; parent pass marked the trend as `decline`, kept rank and share null, and did not fabricate an industry ranking
  - Parent pass normalized two pre-existing preserved nodes so the scoped verifier would be fully clean: `L3.product.portfolio` moved `source` into `evidence_summary`, and `L3.customer.concentration` moved `top5_pct` into `top5_revenue_pct` while preserving the supplier concentration note
  - Parent pass restored `scores.formula` formatting after `scripts/apply_yaml_patch.py` safe-dump wrapping
- Structural diff after run: 8 dpids changed: 6 target dpids (`L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`) plus 2 schema cleanup dpids (`L3.product.portfolio`, `L3.customer.concentration`); non-`nodes` YAML payload unchanged
- Post-run cheap_extract dry-run:
  - `605090.SH`: 0 fillable; 5 target Known fields shown in preserved list; `L3.channel.mix` is excluded from dispatch by the no-local-evidence preserve policy
- Scoped closed-loop verifier:
  - `605090.SH`: single-file scoped run has 0 hard violations, 0 soft warnings, 0 excerpt mis-cites, and 0 schema violations
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count: 163916`
- Test gate after batch: `tests/test_prompt_gen_governance.py tests/test_fingerprint.py` passed, 70 tests
- Diff hygiene after batch: `git diff --check` passed
- Scope audit after batch: `fillable_total=111900`, `skipped_total=23072`, `cheap_extract=9402`

## Completed batch 71

- Batch target: `HK_CN_INTERNET`, A-share, `cheap_extract`
- Stocks completed: `688031.SH`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Nodes handled: 6 cheap_extract targets
- Fill reason before run: 6 `Unknown` nodes with source fingerprint trigger
- Execution note:
  - Child run consumed the generated GPT-5.5 prompt and produced a 6-node patch, but parent pass corrected period metadata and replaced the old `L1.position.growth_rank` value shape with the current rank/share/trend schema before verification
  - Kept `L3.channel.mix` as `Unknown` with `missing_reason: no_local_evidence` because the local annual report disclosed product revenue structure and terminal-user industry structure, but did not disclose direct/distributor/ecommerce/other channel percentages
  - Filled the 5 L1 nodes as `Known` with `data_source: llm_derived`
  - `L1.position.growth_rank` uses local 2026Q1 revenue YoY values `26.242615123764583%` and `26.2426%`; parent pass marked the trend as `modest_growth`, kept rank and share null, and did not fabricate an industry ranking
  - Parent pass restored `scores.formula` formatting after `scripts/apply_yaml_patch.py` safe-dump wrapping
- Structural diff after run: 6 dpids changed: `L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`; non-`nodes` YAML payload unchanged
- Post-run cheap_extract dry-run:
  - `688031.SH`: 0 fillable; 5 target Known fields shown in preserved list; `L3.channel.mix` is excluded from dispatch by the no-local-evidence preserve policy
- Scoped closed-loop verifier:
  - `688031.SH`: single-file scoped run has 0 hard violations, 0 soft warnings, 0 excerpt mis-cites, and 0 schema violations
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count: 163911`
- Test gate after batch: `tests/test_prompt_gen_governance.py tests/test_fingerprint.py` passed, 70 tests
- Diff hygiene after batch: `git diff --check` passed
- Scope audit after batch: `fillable_total=111894`, `skipped_total=23078`, `cheap_extract=9396`

## Completed batch 72

- Batch target: `INNOVATIVE_PHARMA`, A-share, `cheap_extract`
- Stocks completed: `600420.SH`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Nodes handled: 6 cheap_extract targets
- Fill reason before run: 6 `Unknown` nodes with source fingerprint trigger
- Execution note:
  - Child run consumed the generated GPT-5.5 prompt but expanded into legacy examples that used an old `growth_pct/trend: up` shape; parent interrupted it and completed the 6-node fill manually from prompt-injected local evidence
  - Kept `L3.channel.mix` as `Unknown` with `missing_reason: no_local_evidence` because `L9.disclosure.qa_recent` is missing and local main-business text does not disclose direct/distributor/ecommerce/other channel percentages
  - Filled the 5 L1 nodes as `Known` with `data_source: llm_derived`
  - `L1.position.growth_rank` uses local 2026Q1 revenue YoY values `-20.80995483866207%` and `-20.81%`; parent pass marked the trend as `decline`, kept rank and share null, and did not fabricate an industry ranking
  - Parent pass restored `scores.formula` formatting after `scripts/apply_yaml_patch.py` safe-dump wrapping
- Structural diff after run: 6 dpids changed: `L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`; non-`nodes` YAML payload unchanged
- Post-run cheap_extract dry-run:
  - `600420.SH`: 0 fillable; 5 target Known fields shown in preserved list; `L3.channel.mix` is excluded from dispatch by the no-local-evidence preserve policy
- Scoped closed-loop verifier:
  - `600420.SH`: single-file scoped run has 0 hard violations, 0 soft warnings, 0 excerpt mis-cites, and 0 schema violations
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count: 163906`
- Test gate after batch: `tests/test_prompt_gen_governance.py tests/test_fingerprint.py` passed, 70 tests
- Diff hygiene after batch: `git diff --check` passed
- Scope audit after batch: `fillable_total=111888`, `skipped_total=23084`, `cheap_extract=9390`

## Completed batch 73

- Batch target: `INNOVATIVE_PHARMA`, A-share, `cheap_extract`
- Stocks completed: `688319.SH`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Nodes handled: 6 cheap_extract targets
- Fill reason before run: 6 `Unknown` nodes with source fingerprint trigger
- Execution note:
  - Child run consumed the generated GPT-5.5 prompt, then began broad local guideline/governance reads; parent interrupted it after confirming the prompt contained direct annual-report channel evidence and completed the 6-node fill manually
  - Filled `L3.channel.mix` as `Known` because the 2025 annual report discloses sales mode as only `直销`; final value is `direct_pct=100.0`, `distributor_pct=0.0`, `ecommerce_pct=0.0`, `others_pct=0.0`
  - Filled the 5 L1 nodes as `Known` with `data_source: llm_derived`
  - `L1.position.growth_rank` uses local 2026Q1 revenue YoY values `80.36724233678139%` and `80.3672%`; parent pass marked the trend as `modest_growth`, kept rank and share null, and did not fabricate an industry ranking
  - Parent pass restored `scores.formula` formatting after `scripts/apply_yaml_patch.py` safe-dump wrapping
- Structural diff after run: 6 dpids changed: `L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`; non-`nodes` YAML payload unchanged
- Post-run cheap_extract dry-run:
  - `688319.SH`: 0 fillable; all 6 target fields shown in preserved list
- Scoped closed-loop verifier:
  - `688319.SH`: single-file scoped run has 0 hard violations, 0 soft warnings, 0 excerpt mis-cites, and 0 schema violations
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count: 163900`
- Test gate after batch: `tests/test_prompt_gen_governance.py tests/test_fingerprint.py` passed, 70 tests
- Diff hygiene after batch: `git diff --check` passed
- Scope audit after batch: `fillable_total=111882`, `skipped_total=23090`, `cheap_extract=9384`

## Completed batch 74

- Batch target: `AI_COMPUTE`, A-share, `cheap_extract`
- Stocks completed: `000839.SZ`, `000997.SZ`, `001267.SZ`, `001339.SZ`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Nodes handled: 24 cheap_extract targets
- Execution note:
  - Parent first hardened the batch path after observing that zero-fill prompts said `✅ 没有可填字段` while dispatch only skipped the legacy `✅ 已全部填完` marker; `scripts/codex_dispatch.sh` and `scripts/codex_run_stocks_chunk.sh` now skip both markers.
  - Parent hardened the company prompt to treat the prompt-inlined output_schema/source values as highest priority and explicitly avoid old docs/overlay samples for schema discovery.
  - Child runs consumed the generated GPT-5.5 prompts and applied patches through `scripts/apply_yaml_patch.py --strict-schema`.
  - Parent added strict patch metadata validation so future patches reject numeric top-level `evidence_quality`; `evidence_quality` must be the string enum `low` / `medium` / `high`, while `confidence` remains the 0-1 numeric field.
  - Parent restored `scores.formula` formatting after safe-dump wrapping in three child-written files and normalized `001267.SZ` target-node `evidence_quality` values from floats to `medium`.
- Structural diff after run:
  - `000839.SZ`, `000997.SZ`, `001267.SZ`, `001339.SZ` each changed exactly the 6 target dpids: `L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`
  - Non-`nodes` YAML payload is unchanged for all 4 files
- Post-run cheap_extract dry-run:
  - all 4 stocks now show `Fillable: 0`
- Scoped closed-loop verifier:
  - target-file violations filtered from `/tmp/ai_compute_closed_loop_after_batch2.json`: 0
  - target-node evidence_quality type check: 0 bad target nodes
  - schema-violating nodes: 0
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count: 163879`
- Test gate after batch: `tests/test_apply_yaml_patch.py tests/test_prompt_gen_schema_block.py tests/test_prompt_gen_governance.py tests/test_schema_validator.py` passed, 83 tests
- Diff hygiene after batch: `git diff --check` passed
- Scope audit after batch: `fillable_total=111858`, `skipped_total=23114`, `cheap_extract=9360`

## Completed batch 75

- Batch target: `AI_COMPUTE`, A-share, `cheap_extract`
- Stocks completed: `002152.SZ`, `002180.SZ`, `002236.SZ`, `002268.SZ`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Nodes handled: 24 cheap_extract targets, plus 1 preserved-node schema cleanup in the same overlay
- Execution note:
  - Child runs consumed the generated GPT-5.5 prompts and applied patches through `scripts/apply_yaml_patch.py --strict-schema`.
  - `002152.SZ`, `002180.SZ`, and `002236.SZ` each changed exactly the 6 target dpids.
  - `002268.SZ` changed the same 6 target dpids plus one preserved-node cleanup: `L3.customer.concentration` moved legacy `top5_pct/source` shape into the current `top5_revenue_pct/notes/evidence_summary` schema so the scoped verifier is clean.
  - Parent restored `scores.formula` formatting after child safe-dump wrapping in all 4 files.
- Structural diff after run:
  - `002152.SZ`, `002180.SZ`, `002236.SZ`: only 6 target dpids changed (`L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`)
  - `002268.SZ`: 7 dpids changed: the same 6 target dpids plus `L3.customer.concentration`
  - Non-`nodes` YAML payload is unchanged for all 4 files
- Post-run cheap_extract dry-run:
  - all 4 stocks now show `Fillable: 0`
- Scoped closed-loop verifier:
  - target-file violations filtered from `/tmp/ai_compute_closed_loop_after_batch75.json`: 0
  - target-node evidence_quality type check: 0 bad target nodes
  - schema-violating nodes: 0
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count: 163857`
- Test gate after batch: `tests/test_apply_yaml_patch.py tests/test_prompt_gen_schema_block.py tests/test_prompt_gen_governance.py tests/test_schema_validator.py` passed, 83 tests
- Diff hygiene after batch: `git diff --check` passed
- Scope audit after batch: `fillable_total=111834`, `skipped_total=23138`, `cheap_extract=9336`

## Completed batch 76

- Batch target: `AI_COMPUTE`, A-share, `cheap_extract`
- Stocks completed: `000070.SZ`, `000815.SZ`, `000977.SZ`, `002281.SZ`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Nodes handled: 24 cheap_extract targets
- Execution note:
  - Child runs consumed the generated GPT-5.5 prompts and applied patches through `scripts/apply_yaml_patch.py --strict-schema`.
  - `000070.SZ`, `000815.SZ`, `000977.SZ`, and `002281.SZ` each changed exactly the 6 target dpids.
  - `002281.SZ:L1.position.growth_rank` was a fingerprint refresh of an already-filled old-schema value (`rank_bucket/growth_metric/value_pct`); the batch migrated it to the current `rank/share_pct/trend/source_year/market_size_unit` schema.
  - Parent restored `scores.formula` formatting after child safe-dump wrapping in `000070.SZ`, `000815.SZ`, and `000977.SZ`.
- Structural diff after run:
  - all 4 files changed only `L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`
  - Non-`nodes` YAML payload is unchanged for all 4 files
- Post-run cheap_extract dry-run:
  - all 4 stocks now show `Fillable: 0`
- Scoped closed-loop verifier:
  - full verifier output: `/tmp/ai_compute_closed_loop_after_batch76.json`
  - full hard violations: 0
  - target-node violations filtered to the 24 batch dpids: 0
  - target-node evidence_quality type and growth_rank old-key check: 0 bad target nodes
  - target-file soft warnings: 41 historical non-target warnings only
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count: 163846`
- Test gate after batch: `tests/test_apply_yaml_patch.py tests/test_prompt_gen_schema_block.py tests/test_prompt_gen_governance.py tests/test_schema_validator.py` passed, 83 tests
- Diff hygiene after batch: `git diff --check` passed
- Scope audit after batch: `fillable_total=111810`, `skipped_total=23162`, `cheap_extract=9312`

## Completed batch 77

- Batch target: `AI_COMPUTE`, A-share, `cheap_extract`
- Stocks completed: `002289.SZ`, `002396.SZ`, `002415.SZ`, `002463.SZ`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Nodes handled: 24 cheap_extract targets
- Execution note:
  - Child runs consumed the generated GPT-5.5 prompts and applied patches through `scripts/apply_yaml_patch.py --strict-schema`.
  - `002289.SZ`, `002396.SZ`, `002415.SZ`, and `002463.SZ` each changed exactly the 6 target dpids.
  - `002415.SZ:L3.channel.mix` and `002463.SZ:L3.channel.mix` were kept `Unknown` with `missing_reason: no_local_evidence` where local evidence did not directly disclose direct/distributor/ecommerce/other channel split.
  - `002463.SZ` refreshed old-schema target values, including old `L1.stock_attr.tags` extra key and old `L1.position.growth_rank` keys, into the current schema.
  - Parent restored `scores.formula` formatting after child safe-dump wrapping in `002289.SZ` and `002396.SZ`.
- Structural diff after run:
  - all 4 files changed only `L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`
  - Non-`nodes` YAML payload is unchanged for all 4 files
- Post-run cheap_extract dry-run:
  - all 4 stocks now show `Fillable: 0`
- Scoped closed-loop verifier:
  - full verifier output: `/tmp/ai_compute_closed_loop_after_batch77.json`
  - full hard violations: 0
  - target-node violations filtered to the 24 batch dpids: 0
  - target-node evidence_quality type and old-key check: 0 bad target nodes
  - target-file soft warnings: 29 historical non-target warnings only
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count: 163836`
- Test gate after batch: `tests/test_apply_yaml_patch.py tests/test_prompt_gen_schema_block.py tests/test_prompt_gen_governance.py tests/test_schema_validator.py` passed, 83 tests
- Diff hygiene after batch: `git diff --check` passed
- Scope audit after batch: `fillable_total=111786`, `skipped_total=23186`, `cheap_extract=9288`

## Completed batch 78

- Batch target: `AI_COMPUTE`, A-share, `cheap_extract`
- Stocks completed: `002491.SZ`, `002544.SZ`, `002583.SZ`, `002792.SZ`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Nodes handled: 24 cheap_extract targets
- Execution note:
  - Child runs consumed the generated GPT-5.5 prompts and applied patches through `scripts/apply_yaml_patch.py --strict-schema`.
  - `002491.SZ`, `002544.SZ`, `002583.SZ`, and `002792.SZ` each changed exactly the 6 target dpids.
  - `002544.SZ:L3.channel.mix` was kept `Unknown` with `missing_reason: no_local_evidence` where local evidence did not directly disclose a direct/distributor/ecommerce/other channel split.
  - `002491.SZ:L3.channel.mix` used annual-report sales-mode evidence showing direct sales at 100%.
  - `002583.SZ:L3.channel.mix` used direct/non-direct sales-mode evidence; parent also corrected one `L1.model.tag` evidence excerpt to exactly match `runtime/hot.sqlite:L1.company.main_business`.
  - `002792.SZ:L3.channel.mix` used direct/distributor sales-mode evidence (`direct_pct=89.58`, `distributor_pct=10.42`).
  - Parent restored `scores.formula` formatting after child safe-dump wrapping in `002491.SZ` and `002544.SZ`.
- Structural diff after run:
  - all 4 files changed only `L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`
  - Non-`nodes` YAML payload is unchanged for all 4 files
- Post-run cheap_extract dry-run:
  - all 4 stocks now show `Fillable: 0` / `没有可填字段`
- Scoped closed-loop verifier:
  - full verifier output: `/tmp/ai_compute_closed_loop_after_batch78.json`
  - full hard violations: 0
  - target-node violations filtered to the 24 batch dpids: 0
  - target-node evidence_quality type and old-key check: 0 bad target nodes
  - target-file soft warnings: 16 historical non-target warnings only
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count: 163813`
- Test gate after batch: `tests/test_apply_yaml_patch.py tests/test_prompt_gen_schema_block.py tests/test_prompt_gen_governance.py tests/test_schema_validator.py` passed, 83 tests
- Diff hygiene after batch: `git diff --check` passed
- Scope audit after batch: `fillable_total=111762`, `skipped_total=23210`, `cheap_extract=9264`

## Completed batch 79

- Batch target: `AI_COMPUTE`, A-share, `cheap_extract`
- Stocks completed: `002796.SZ`, `002881.SZ`, `002897.SZ`, `002916.SZ`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Nodes handled: 24 cheap_extract targets
- Execution note:
  - Child runs consumed the generated GPT-5.5 prompts and applied patches through `scripts/apply_yaml_patch.py --strict-schema`.
  - `002796.SZ`, `002881.SZ`, `002897.SZ`, and `002916.SZ` each changed exactly the 6 target dpids.
  - `002796.SZ:L3.channel.mix` used annual-report sales-mode evidence showing direct sales at 100%.
  - `002881.SZ:L3.channel.mix` used annual-report sales-mode evidence (`direct_pct=92.78`, `distributor_pct=7.22`).
  - `002897.SZ:L3.channel.mix` used annual-report sales-mode evidence showing factory direct sales at 100%.
  - `002916.SZ:L3.channel.mix` was kept `Unknown` with `missing_reason: no_local_evidence` because local evidence did not directly disclose direct/distributor/ecommerce/other channel split; its other 5 target nodes were refreshed from the fingerprint trigger.
  - Parent restored `scores.formula` formatting after child safe-dump wrapping in `002796.SZ` and `002897.SZ`.
- Structural diff after run:
  - all 4 files changed only `L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`
  - Non-`nodes` YAML payload is unchanged for all 4 files
- Post-run cheap_extract dry-run:
  - all 4 stocks now show `Fillable: 0` / `没有可填字段`
- Scoped closed-loop verifier:
  - full verifier output: `/tmp/ai_compute_closed_loop_after_batch79.json`
  - full hard violations: 0
  - target-node violations filtered to the 24 batch dpids: 0
  - target-node evidence_quality type and old-key check: 0 bad target nodes
  - target-file soft warnings: 28 historical non-target warnings only
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count: 163796`
- Test gate after batch: `tests/test_apply_yaml_patch.py tests/test_prompt_gen_schema_block.py tests/test_prompt_gen_governance.py tests/test_schema_validator.py` passed, 83 tests
- Diff hygiene after batch: `git diff --check` passed
- Scope audit after batch: `fillable_total=111738`, `skipped_total=23234`, `cheap_extract=9240`

## Completed batch 80

- Batch target: `AI_COMPUTE`, A-share, `cheap_extract`
- Stocks completed: `002929.SZ`, `002970.SZ`, `002990.SZ`, `003031.SZ`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Nodes handled: 24 cheap_extract targets
- Execution note:
  - Child runs consumed the generated GPT-5.5 prompts and applied patches through `scripts/apply_yaml_patch.py --strict-schema`.
  - `002929.SZ`, `002970.SZ`, `002990.SZ`, and `003031.SZ` each changed exactly the 6 target dpids.
  - `002929.SZ:L3.channel.mix` used annual-report sales-mode evidence showing direct sales at 100%.
  - `002970.SZ:L3.channel.mix` was kept `Unknown` with `missing_reason: no_local_evidence` because local evidence did not directly disclose direct/distributor/ecommerce/other channel split.
  - `002990.SZ:L3.channel.mix` used annual-report sales-mode evidence showing direct sales at 100%.
  - `003031.SZ:L3.channel.mix` used annual-report sales-mode evidence showing direct sales at 100%.
  - Parent restored `scores.formula` formatting after child safe-dump wrapping in `002970.SZ` and `002990.SZ`.
- Structural diff after run:
  - all 4 files changed only `L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`
  - Non-`nodes` YAML payload is unchanged for all 4 files
- Post-run cheap_extract dry-run:
  - all 4 stocks now show `Fillable: 0` / `没有可填字段`
- Scoped closed-loop verifier:
  - full verifier output: `/tmp/ai_compute_closed_loop_after_batch80.json`
  - full hard violations: 0
  - target-node violations filtered to the 24 batch dpids: 0
  - target-node evidence_quality type and old-key check: 0 bad target nodes
  - target-file soft warnings: 16 historical non-target warnings only
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count: 163773`
- Test gate after batch: `tests/test_apply_yaml_patch.py tests/test_prompt_gen_schema_block.py tests/test_prompt_gen_governance.py tests/test_schema_validator.py` passed, 83 tests
- Diff hygiene after batch: `git diff --check` passed
- Scope audit after batch: `fillable_total=111714`, `skipped_total=23258`, `cheap_extract=9216`

## Completed batch 81

- Batch target: `AI_COMPUTE`, A-share, `cheap_extract`
- Stocks completed: `300042.SZ`, `300113.SZ`, `300130.SZ`, `300302.SZ`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Nodes handled: 24 cheap_extract targets
- Execution note:
  - Child runs consumed the generated GPT-5.5 prompts and applied patches through `scripts/apply_yaml_patch.py --strict-schema`.
  - `300042.SZ`, `300113.SZ`, `300130.SZ`, and `300302.SZ` each changed exactly the 6 target dpids.
  - `300042.SZ:L3.channel.mix` used annual-report online/offline sales-mode evidence (`ecommerce_pct=16.27`, `others_pct=83.73`) and did not infer direct/distributor split.
  - `300113.SZ:L3.channel.mix` used annual-report sales-mode evidence showing direct sales at 100%.
  - `300130.SZ:L3.channel.mix` was kept `Unknown` with `missing_reason: no_local_evidence` because local evidence did not directly disclose direct/distributor/ecommerce/other channel split.
  - `300302.SZ:L3.channel.mix` used annual-report sales-mode evidence showing direct sales at 100%.
  - Parent restored `scores.formula` formatting after child safe-dump wrapping in `300130.SZ`.
- Structural diff after run:
  - all 4 files changed only `L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`
  - Non-`nodes` YAML payload is unchanged for all 4 files
- Post-run cheap_extract dry-run:
  - all 4 stocks now show `Fillable: 0` / `没有可填字段`
- Scoped closed-loop verifier:
  - full verifier output: `/tmp/ai_compute_closed_loop_after_batch81.json`
  - full hard violations: 0
  - target-node violations filtered to the 24 batch dpids: 0
  - target-node evidence_quality type and old-key check: 0 bad target nodes
  - target-file soft warnings: 16 historical non-target warnings only
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count: 163750`
- Test gate after batch: `tests/test_apply_yaml_patch.py tests/test_prompt_gen_schema_block.py tests/test_prompt_gen_governance.py tests/test_schema_validator.py` passed, 83 tests
- Diff hygiene after batch: `git diff --check` passed
- Scope audit after batch: `fillable_total=111690`, `skipped_total=23282`, `cheap_extract=9192`

## Completed batch 82

- Batch target: `AI_COMPUTE`, A-share, `cheap_extract`
- Stocks completed: `300308.SZ`, `300353.SZ`, `300383.SZ`, `300394.SZ`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Nodes handled: 24 cheap_extract targets
- Execution note:
  - Child runs consumed the generated GPT-5.5 prompts and applied patches through `scripts/apply_yaml_patch.py --strict-schema`.
  - `300308.SZ`, `300353.SZ`, `300383.SZ`, and `300394.SZ` each changed exactly the 6 target dpids.
  - `300308.SZ:L3.channel.mix` used annual-report sales-mode evidence (`direct_pct=98.69`, `distributor_pct=1.31`), mapping channel sales to distributor.
  - `300353.SZ:L3.channel.mix` used annual-report sales-mode evidence (`direct_pct=87.85`, `distributor_pct=12.15`), mapping agency sales to distributor.
  - `300383.SZ:L3.channel.mix` was kept `Unknown` with `missing_reason: no_local_evidence` because local evidence did not directly disclose direct/distributor/ecommerce/other channel split.
  - `300394.SZ:L3.channel.mix` used annual-report sales-mode evidence showing direct sales at 100%.
  - Parent restored `scores.formula` formatting after child safe-dump wrapping in `300308.SZ` and `300383.SZ`.
- Structural diff after run:
  - all 4 files changed only `L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`
  - Non-`nodes` YAML payload is unchanged for all 4 files
- Post-run cheap_extract dry-run:
  - all 4 stocks now show `Fillable: 0` / `没有可填字段`
- Scoped closed-loop verifier:
  - full verifier output: `/tmp/ai_compute_closed_loop_after_batch82.json`
  - full hard violations: 0
  - target-node violations filtered to the 24 batch dpids: 0
  - target-node evidence_quality type and old-key check: 0 bad target nodes
  - target-file soft warnings: 22 historical non-target warnings only
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count: 163739`
- Test gate after batch: `tests/test_apply_yaml_patch.py tests/test_prompt_gen_schema_block.py tests/test_prompt_gen_governance.py tests/test_schema_validator.py` passed, 83 tests
- Diff hygiene after batch: `git diff --check` passed
- Scope audit after batch: `fillable_total=111666`, `skipped_total=23306`, `cheap_extract=9168`

## Completed batch 83

- Batch target: `AI_COMPUTE`, A-share, `cheap_extract`
- Stocks completed: `300442.SZ`, `300455.SZ`, `300502.SZ`, `300548.SZ`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Nodes handled: 24 cheap_extract targets
- Execution note:
  - Child runs consumed the generated GPT-5.5 prompts and applied patches through `scripts/apply_yaml_patch.py --strict-schema`.
  - `300442.SZ`, `300455.SZ`, `300502.SZ`, and `300548.SZ` each changed exactly the 6 target dpids.
  - `300442.SZ:L3.channel.mix` used annual-report sales-mode evidence showing direct sales at 100%.
  - `300455.SZ:L3.channel.mix` used annual-report sales-mode evidence showing direct sales at 100%.
  - `300502.SZ:L3.channel.mix` used annual-report sales-mode evidence (`direct_pct=98.01`, `distributor_pct=1.99`).
  - `300548.SZ:L3.channel.mix` used annual-report sales-mode evidence (`direct_pct=93.32`, `distributor_pct=6.68`).
  - Parent restored `scores.formula` formatting after child safe-dump wrapping in `300455.SZ`.
- Structural diff after run:
  - all 4 files changed only `L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`
  - Non-`nodes` YAML payload is unchanged for all 4 files
- Post-run cheap_extract dry-run:
  - all 4 stocks now show `Fillable: 0` / `没有可填字段`
- Scoped closed-loop verifier:
  - full verifier output: `/tmp/ai_compute_closed_loop_after_batch83.json`
  - full hard violations: 0
  - target-node violations filtered to the 24 batch dpids: 0
  - target-node evidence_quality type and old-key check: 0 bad target nodes
  - target-file soft warnings: 22 historical non-target warnings only
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count: 163721`
- Test gate after batch: `tests/test_apply_yaml_patch.py tests/test_prompt_gen_schema_block.py tests/test_prompt_gen_governance.py tests/test_schema_validator.py` passed, 83 tests
- Diff hygiene after batch: `git diff --check` passed
- Scope audit after batch: `fillable_total=111642`, `skipped_total=23330`, `cheap_extract=9144`

## Completed batch 84

- Batch target: `AI_COMPUTE`, A-share, `cheap_extract`
- Stocks completed: `300570.SZ`, `300620.SZ`, `300627.SZ`, `300628.SZ`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Nodes handled: 24 cheap_extract targets
- Execution note:
  - Child runs consumed the generated GPT-5.5 prompts and applied patches through `scripts/apply_yaml_patch.py --strict-schema`.
  - `300570.SZ`, `300620.SZ`, `300627.SZ`, and `300628.SZ` each changed exactly the 6 target dpids.
  - `300570.SZ:L3.channel.mix` used annual-report sales-mode evidence showing direct sales at 100%.
  - `300620.SZ:L3.channel.mix` used annual-report sales-mode evidence (`direct_pct=99.86`, `distributor_pct=0.14`).
  - `300627.SZ:L3.channel.mix` and `300628.SZ:L3.channel.mix` were kept `Unknown` with `missing_reason: no_local_evidence` because local evidence did not directly disclose direct/distributor/ecommerce/other channel split.
  - Parent restored `scores.formula` formatting after child safe-dump wrapping in `300570.SZ`, `300620.SZ`, and `300627.SZ`.
- Structural diff after run:
  - all 4 files changed only `L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`
  - Non-`nodes` YAML payload is unchanged for all 4 files
- Post-run cheap_extract dry-run:
  - all 4 stocks now show `Fillable: 0` / `没有可填字段`
- Scoped closed-loop verifier:
  - full verifier output: `/tmp/ai_compute_closed_loop_after_batch84.json`
  - full hard violations: 0
  - target-node violations filtered to the 24 batch dpids: 0
  - target-node evidence_quality type and old-key check: 0 bad target nodes
  - target-file soft warnings: 16 historical non-target warnings only
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count: 163699`
- Test gate after batch: `tests/test_apply_yaml_patch.py tests/test_prompt_gen_schema_block.py tests/test_prompt_gen_governance.py tests/test_schema_validator.py` passed, 83 tests
- Diff hygiene after batch: `git diff --check` passed
- Scope audit after batch: `fillable_total=111618`, `skipped_total=23354`, `cheap_extract=9120`

## Completed batch 85

- Batch target: `AI_COMPUTE`, A-share, `cheap_extract`
- Stocks completed: `300638.SZ`, `300738.SZ`, `300790.SZ`, `300846.SZ`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Nodes handled: 24 cheap_extract targets
- Execution note:
  - Child runs consumed the generated GPT-5.5 prompts and applied patches through `scripts/apply_yaml_patch.py --strict-schema`.
  - `300638.SZ`, `300738.SZ`, `300790.SZ`, and `300846.SZ` each changed exactly the 6 target dpids.
  - `300638.SZ:L3.channel.mix` used annual-report sales-mode evidence (`direct_pct=87.83`, `distributor_pct=12.17`).
  - `300738.SZ:L3.channel.mix` and `300790.SZ:L3.channel.mix` were kept `Unknown` with `missing_reason: no_local_evidence` because local evidence did not directly disclose direct/distributor/ecommerce/other channel split.
  - `300846.SZ:L3.channel.mix` used annual-report sales-mode evidence showing direct sales at 100%.
  - Parent restored `scores.formula` formatting after child safe-dump wrapping in `300638.SZ` and `300790.SZ`.
- Structural diff after run:
  - all 4 files changed only `L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`
  - Non-`nodes` YAML payload is unchanged for all 4 files
- Post-run cheap_extract dry-run:
  - all 4 stocks now show `Fillable: 0` / `没有可填字段`
- Scoped closed-loop verifier:
  - full verifier output: `/tmp/ai_compute_closed_loop_after_batch85.json`
  - full hard violations: 0
  - target-node violations filtered to the 24 batch dpids: 0
  - target-node evidence_quality type and old-key check: 0 bad target nodes
  - target-file soft warnings: 16 historical non-target warnings only
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count: 163677`
- Test gate after batch: `tests/test_apply_yaml_patch.py tests/test_prompt_gen_schema_block.py tests/test_prompt_gen_governance.py tests/test_schema_validator.py` passed, 83 tests
- Diff hygiene after batch: `git diff --check` passed
- Scope audit after batch: `fillable_total=111594`, `skipped_total=23378`, `cheap_extract=9096`

## Pipeline hardening after batch 85

- User requirement addressed: keep LLM fill script multi-stock/parallel, but make the supervised run path more complete and stable before scaling further.
- Script hardened: `scripts/run_c1_fill.sh`
  - validates `C1_PARALLEL` as a positive integer
  - validates runner executability before starting a batch
  - supports `C1_PROMPT_DIR`, `C1_LOG_DIR`, and per-run `C1_RESULT_DIR`
  - clears per-stock stale prompt/log/skip state before regenerating prompts, preventing old `.SKIP` files from hiding newly fillable nodes
  - records per-stock statuses: `prompt_ready`, `skipped`, `prompt_failed`, `processed`, `failed`
  - propagates runner failures after parallel execution while still letting other same-batch jobs finish
  - parses the prompt's `当前状态：N 条` line for accurate fillable count logging, with the old grep as fallback
  - supports `-h` / `--help` as a real usage path, preventing accidental help invocations from being treated as stock codes
- Verification:
  - `bash -n scripts/run_c1_fill.sh scripts/codex_dispatch.sh scripts/codex_run_stocks_chunk.sh` passed
  - help-path smoke: `scripts/run_c1_fill.sh --help` printed usage and exited 0 without generating prompts or status files
  - skip-path smoke: `C1_PARALLEL=2 C1_RUNNER=/usr/bin/true MODEL_TIER=cheap_extract scripts/run_c1_fill.sh 300638.SZ 300738.SZ 300790.SZ 300846.SZ` produced `processed=0`, `skipped=4`, `failed=0`
  - failure-path smoke: `C1_PARALLEL=1 C1_RUNNER=/usr/bin/false MODEL_TIER=cheap_extract scripts/run_c1_fill.sh 301382.SZ` produced accurate `6 fillable`, `failed=1`, and exited non-zero
  - related unit tests passed: `tests/test_apply_yaml_patch.py tests/test_prompt_gen_schema_block.py tests/test_prompt_gen_governance.py tests/test_schema_validator.py` (83 tests)
  - `mvp20.cli validate-overlays`: `ok=True`, `error_count=0`, `warning_count=163677`
  - `git diff --check` passed for the LLM pipeline/script/test/audit files

## Completed batch 86

- Batch target: `AI_COMPUTE`, A-share, `cheap_extract`
- Stocks completed: `300857.SZ`, `300913.SZ`, `300959.SZ`, `301165.SZ`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Parallel runner: `C1_PARALLEL=2`, via hardened `scripts/run_c1_fill.sh`
- Nodes handled: 24 cheap_extract targets
- Execution note:
  - All 4 child runs exited 0 and the hardened status summary reported `processed=4`, `failed=0`.
  - `300857.SZ`, `300913.SZ`, `300959.SZ`, and `301165.SZ` each changed exactly the 6 target dpids.
  - `300857.SZ:L3.channel.mix` used annual-report sales-mode evidence showing direct sales at 100%.
  - `300913.SZ:L3.channel.mix` and `300959.SZ:L3.channel.mix` were kept `Unknown` with `missing_reason: no_local_evidence` because local evidence did not directly disclose direct/distributor/ecommerce/other channel split.
  - `301165.SZ:L3.channel.mix` used annual-report sales-mode evidence (`direct_pct=54.36`, `distributor_pct=45.64`, `ecommerce_pct=0`, `others_pct=0`).
  - Parent restored `scores.formula` formatting after child safe-dump wrapping in `300857.SZ`, `300959.SZ`, and `301165.SZ`.
  - Parent corrected one target-node excerpt mis-cite in `301165.SZ:L1.model.tag` by replacing a non-contiguous main-business/business-scope excerpt with a verified contiguous `L1.company.main_business` excerpt.
- Structural diff after run:
  - all 4 files changed only `L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`
  - Non-`nodes` YAML payload is unchanged for all 4 files
- Post-run cheap_extract dry-run:
  - all 4 stocks now show `Fillable: 0` / `没有可填字段`
- Scoped closed-loop verifier:
  - full verifier output: `/tmp/ai_compute_closed_loop_after_batch86.json`
  - full hard violations: 0
  - full soft warnings: 11865
  - target-node violations filtered to the 24 batch dpids: 0
  - target-node evidence_quality type and old-key check: 0 bad target nodes
  - target-file soft warnings: 16 historical non-target warnings only
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count: 163655`
- Test gate after batch: `tests/test_apply_yaml_patch.py tests/test_prompt_gen_schema_block.py tests/test_prompt_gen_governance.py tests/test_schema_validator.py` passed, 83 tests
- Diff hygiene after batch: `git diff --check` passed
- Scope audit after batch: `fillable_total=111570`, `skipped_total=23402`, `cheap_extract=9072`

## Completed batch 87

- Batch target: `AI_COMPUTE`, A-share, `cheap_extract`
- Stocks completed: `301205.SZ`, `301307.SZ`, `301382.SZ`, `301486.SZ`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Parallel runner: `C1_PARALLEL=2`, via hardened `scripts/run_c1_fill.sh`
- Nodes handled: 24 cheap_extract targets
- Execution note:
  - All 4 child runs exited 0 and the hardened status summary reported `processed=4`, `failed=0`.
  - `301205.SZ`, `301307.SZ`, `301382.SZ`, and `301486.SZ` each changed exactly the 6 target dpids.
  - `301205.SZ:L3.channel.mix` used annual-report sales-mode evidence (`direct_pct=93.65`, `distributor_pct=6.35`, `ecommerce_pct=0`, `others_pct=0`).
  - `301307.SZ:L3.channel.mix` used annual-report sales-mode evidence showing direct sales at 100%.
  - `301382.SZ:L3.channel.mix` and `301486.SZ:L3.channel.mix` were kept `Unknown` with `missing_reason: no_local_evidence` because local evidence did not directly disclose direct/distributor/ecommerce/other channel split.
  - Parent restored `scores.formula` formatting after child safe-dump wrapping in all 4 files.
- Structural diff after run:
  - all 4 files changed only `L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`
  - Non-`nodes` YAML payload is unchanged for all 4 files
- Post-run cheap_extract dry-run:
  - all 4 stocks now show `Fillable: 0` / `没有可填字段`
- Scoped closed-loop verifier:
  - full verifier output: `/tmp/ai_compute_closed_loop_after_batch87.json`
  - full hard violations: 0
  - full soft warnings: 11865
  - target-node violations filtered to the 24 batch dpids: 0
  - target-node evidence_quality type and old-key check: 0 bad target nodes
  - target-file soft warnings: 15 historical non-target warnings only
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count: 163633`
- Test gate after batch: `tests/test_apply_yaml_patch.py tests/test_prompt_gen_schema_block.py tests/test_prompt_gen_governance.py tests/test_schema_validator.py` passed, 83 tests
- Diff hygiene after batch: `git diff --check` passed
- Scope audit after batch: `fillable_total=111546`, `skipped_total=23426`, `cheap_extract=9048`

## Completed batch 88

- Batch target: `AI_COMPUTE`, A-share, `cheap_extract`
- Candidate note: `600050.SH` was checked first but current prompt generation returned `没有可填字段`, so it was skipped without invoking LLM.
- Stocks completed: `301589.SZ`, `301600.SZ`, `600100.SH`, `600105.SH`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Parallel runner: `C1_PARALLEL=2`, via hardened `scripts/run_c1_fill.sh`
- Nodes handled: 24 cheap_extract targets
- Execution note:
  - All 4 child runs exited 0 and the hardened status summary reported `processed=4`, `failed=0`.
  - `301589.SZ`, `301600.SZ`, `600100.SH`, and `600105.SH` each changed exactly the 6 target dpids.
  - `301589.SZ:L3.channel.mix` used annual-report sales-mode evidence (`direct_pct=67.09`, `distributor_pct=32.91`, `ecommerce_pct=0`, `others_pct=0`).
  - `301600.SZ:L3.channel.mix` and `600100.SH:L3.channel.mix` were kept `Unknown` with `missing_reason: no_local_evidence` because local evidence did not directly disclose direct/distributor/ecommerce/other channel split.
  - `600105.SH:L3.channel.mix` used annual-report sales-mode evidence showing direct sales at 100%.
  - Parent restored `scores.formula` formatting after child safe-dump wrapping in `301589.SZ`, `301600.SZ`, and `600105.SH`.
- Structural diff after run:
  - all 4 files changed only `L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`
  - Non-`nodes` YAML payload is unchanged for all 4 files
- Post-run cheap_extract dry-run:
  - all 4 stocks now show `Fillable: 0` / `没有可填字段`
- Scoped closed-loop verifier:
  - full verifier output: `/tmp/ai_compute_closed_loop_after_batch88.json`
  - full hard violations: 0
  - full soft warnings: 11865
  - target-node violations filtered to the 24 batch dpids: 0
  - target-node evidence_quality type and old-key check: 0 bad target nodes
  - target-file soft warnings: 16 historical non-target warnings only
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count: 163611`
- Test gate after batch: `tests/test_apply_yaml_patch.py tests/test_prompt_gen_schema_block.py tests/test_prompt_gen_governance.py tests/test_schema_validator.py` passed, 83 tests
- Diff hygiene after batch: `git diff --check` passed
- Scope audit after batch: `fillable_total=111522`, `skipped_total=23450`, `cheap_extract=9024`

## Completed batch 89

- Batch target: `AI_COMPUTE`, A-share, `cheap_extract`
- Stocks completed: `600345.SH`, `600487.SH`, `600498.SH`, `600522.SH`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Parallel runner: `C1_PARALLEL=2`, via hardened `scripts/run_c1_fill.sh`
- Nodes handled: 24 cheap_extract targets
- Execution note:
  - All 4 child runs exited 0 and the hardened status summary reported `processed=4`, `failed=0`.
  - `600345.SH`, `600487.SH`, `600498.SH`, and `600522.SH` each changed exactly the 6 target dpids.
  - `600345.SH:L3.channel.mix` and `600487.SH:L3.channel.mix` used annual-report sales-mode evidence showing direct sales at 100%.
  - `600498.SH:L3.channel.mix` and `600522.SH:L3.channel.mix` were kept `Unknown` with `missing_reason: no_local_evidence` because local evidence did not directly disclose direct/distributor/ecommerce/other channel split.
  - Parent restored `scores.formula` formatting after child safe-dump wrapping in `600487.SH`.
- Structural diff after run:
  - all 4 files changed only `L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`
  - Non-`nodes` YAML payload is unchanged for all 4 files
- Post-run cheap_extract dry-run:
  - all 4 stocks now show `Fillable: 0` / `没有可填字段`
- Scoped closed-loop verifier:
  - full verifier output: `/tmp/ai_compute_closed_loop_after_batch89.json`
  - full hard violations: 0
  - full soft warnings: 11843
  - target-node violations filtered to the 24 batch dpids: 0
  - target-node evidence_quality type and old-key check: 0 bad target nodes
  - target-file soft warnings: 34 historical non-target warnings only
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count: 163600`
- Test gate after batch: `tests/test_apply_yaml_patch.py tests/test_prompt_gen_schema_block.py tests/test_prompt_gen_governance.py tests/test_schema_validator.py` passed, 83 tests
- Diff hygiene after batch: `git diff --check` passed
- Scope audit after batch: `fillable_total=111498`, `skipped_total=23474`, `cheap_extract=9000`

## Completed batch 90

- Batch target: `AI_COMPUTE`, A-share, `cheap_extract`
- Stocks completed: `600776.SH`, `600941.SH`, `601138.SH`, `601728.SH`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Parallel runner: `C1_PARALLEL=2`, via hardened `scripts/run_c1_fill.sh`
- Nodes handled: 24 cheap_extract targets
- Execution note:
  - All 4 child runs exited 0 and the hardened status summary reported `processed=4`, `failed=0`.
  - `600776.SH`, `600941.SH`, `601138.SH`, and `601728.SH` each changed exactly the 6 target dpids.
  - All 4 `L3.channel.mix` nodes were kept `Unknown` with `missing_reason: no_local_evidence` because local evidence did not directly disclose direct/distributor/ecommerce/other channel split.
  - Parent restored `scores.formula` formatting after child safe-dump wrapping in `601728.SH`.
- Structural diff after run:
  - all 4 files changed only `L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`
  - Non-`nodes` YAML payload is unchanged for all 4 files
- Post-run cheap_extract dry-run:
  - all 4 stocks now show `Fillable: 0` / `没有可填字段`
- Scoped closed-loop verifier:
  - full verifier output: `/tmp/ai_compute_closed_loop_after_batch90.json`
  - full hard violations: 0
  - full soft warnings: 11811
  - target-node violations filtered to the 24 batch dpids: 0
  - target-node evidence_quality type and old-key check: 0 bad target nodes
  - target-file soft warnings: 39 historical non-target warnings only
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count: 163598`
- Test gate after batch: `tests/test_apply_yaml_patch.py tests/test_prompt_gen_schema_block.py tests/test_prompt_gen_governance.py tests/test_schema_validator.py` passed, 83 tests
- Diff hygiene after batch: `git diff --check` passed
- Scope audit after batch: `fillable_total=111474`, `skipped_total=23498`, `cheap_extract=8976`

## Completed batch 91

- Batch target: `AI_COMPUTE`, A-share, `cheap_extract`
- Stocks completed: `601869.SH`, `603019.SH`, `603083.SH`, `603118.SH`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Parallel runner: `C1_PARALLEL=2`, via hardened `scripts/run_c1_fill.sh`
- Nodes handled: 24 cheap_extract targets
- Execution note:
  - All 4 child runs exited 0 and the hardened status summary reported `processed=4`, `failed=0`.
  - `601869.SH`, `603019.SH`, `603083.SH`, and `603118.SH` each changed exactly the 6 target dpids.
  - `603019.SH:L3.channel.mix` used annual-report sales-mode evidence showing direct sales at 95.4404% and distributor sales at 4.5596%.
  - `601869.SH:L3.channel.mix`, `603083.SH:L3.channel.mix`, and `603118.SH:L3.channel.mix` were kept `Unknown` with `missing_reason: no_local_evidence` because local evidence did not directly disclose direct/distributor/ecommerce/other channel split.
  - Parent restored standard single-line `scores.formula` formatting after child safe-dump wrapping in all 4 files.
- Structural diff after run:
  - all 4 files changed only `L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`
  - Non-`nodes` YAML payload is unchanged for all 4 files
- Post-run cheap_extract dry-run:
  - all 4 stocks now show `Fillable: 0` / `没有可填字段`
- Scoped closed-loop verifier:
  - full verifier output: `/tmp/ai_compute_closed_loop_after_batch91.json`
  - full hard violations: 0
  - full soft warnings: 11797
  - target-node violations filtered to the 24 batch dpids: 0
  - target-node evidence_quality type and old-key check: 0 bad target nodes
  - target-file soft warnings: 35 historical non-target warnings only
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count: 163583`
- Test gate after batch: `tests/test_apply_yaml_patch.py tests/test_prompt_gen_schema_block.py tests/test_prompt_gen_governance.py tests/test_schema_validator.py` passed, 83 tests
- Diff hygiene after batch: `git diff --check` passed
- Scope audit after batch: `fillable_total=111450`, `skipped_total=23522`, `cheap_extract=8952`

## Completed batch 92

- Batch target: `AI_COMPUTE`, A-share, `cheap_extract`
- Stocks completed: `603881.SH`, `688027.SH`, `688205.SH`, `920045.BJ`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Parallel runner: `C1_PARALLEL=2`, via hardened `scripts/run_c1_fill.sh`
- Nodes handled: 24 cheap_extract targets
- Execution note:
  - All 4 child runs exited 0 and the hardened status summary reported `processed=4`, `failed=0`.
  - `603881.SH`, `688027.SH`, `688205.SH`, and `920045.BJ` each changed exactly the 6 target dpids.
  - All 4 `L3.channel.mix` nodes were kept `Unknown` with `missing_reason: no_local_evidence` because local evidence did not directly disclose direct/distributor/ecommerce/other channel split.
  - Parent restored standard single-line `scores.formula` formatting after child safe-dump wrapping in `603881.SH` and `688027.SH`.
- Structural diff after run:
  - all 4 files changed only `L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`
  - Non-`nodes` YAML payload is unchanged for all 4 files
- Post-run cheap_extract dry-run:
  - all 4 stocks now show `Fillable: 0` / `没有可填字段`
- Scoped closed-loop verifier:
  - full verifier output: `/tmp/ai_compute_closed_loop_after_batch92.json`
  - full hard violations: 0
  - full soft warnings: 11797
  - target-node violations filtered to the 24 batch dpids: 0
  - target-node evidence_quality type and old-key check: 0 bad target nodes
  - target-file soft warnings: 8 historical non-target warnings only
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count: 163563`
- Test gate after batch: `tests/test_apply_yaml_patch.py tests/test_prompt_gen_schema_block.py tests/test_prompt_gen_governance.py tests/test_schema_validator.py` passed, 83 tests
- Diff hygiene after batch: `git diff --check` passed
- Scope audit after batch: `fillable_total=111426`, `skipped_total=23546`, `cheap_extract=8928`

## Completed batch 93

- Batch target: `AI_COMPUTE`, A-share, `cheap_extract`
- Stocks completed: `603220.SH`, `603236.SH`, `603516.SH`, `605118.SH`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Parallel runner: `C1_PARALLEL=2`, via hardened `scripts/run_c1_fill.sh`
- Nodes handled: 24 cheap_extract targets
- Execution note:
  - All 4 child runs exited 0 and the hardened status summary reported `processed=4`, `failed=0`.
  - `603220.SH`, `603236.SH`, `603516.SH`, and `605118.SH` each changed exactly the 6 target dpids.
  - All 4 `L3.channel.mix` nodes were kept `Unknown` with `missing_reason: no_local_evidence` because local evidence did not directly disclose direct/distributor/ecommerce/other channel split.
  - Parent restored standard single-line `scores.formula` formatting after child safe-dump wrapping in `603220.SH`, `603236.SH`, and `605118.SH`.
- Structural diff after run:
  - all 4 files changed only `L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`
  - Non-`nodes` YAML payload is unchanged for all 4 files
- Post-run cheap_extract dry-run:
  - all 4 stocks now show `Fillable: 0` / `没有可填字段`
- Scoped closed-loop verifier:
  - full verifier output: `/tmp/ai_compute_closed_loop_after_batch93.json`
  - full hard violations: 0
  - full soft warnings: 11797
  - target-node violations filtered to the 24 batch dpids: 0
  - target-node evidence_quality type and old-key check: 0 bad target nodes
  - target-file soft warnings: 16 historical non-target warnings only
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count: 163543`
- Test gate after batch: `tests/test_apply_yaml_patch.py tests/test_prompt_gen_schema_block.py tests/test_prompt_gen_governance.py tests/test_schema_validator.py` passed, 83 tests
- Diff hygiene after batch: `git diff --check` passed
- Scope audit after batch: `fillable_total=111402`, `skipped_total=23570`, `cheap_extract=8904`

## Pipeline hardening after batch 93

- `scripts/run_c1_fill.sh` now accepts `C1_INDUSTRY` while preserving the default `AI_COMPUTE` behavior.
- Safety guard: non-`AI_COMPUTE` runs require explicit stock arguments, so the legacy AI default stock list cannot be accidentally used for another industry.
- Smoke checks:
  - `C1_INDUSTRY=NONFERROUS_METALS C1_RUNNER=/usr/bin/true MODEL_TIER=cheap_extract scripts/run_c1_fill.sh` exited 1 with the expected explicit-stock-args error.
  - `C1_INDUSTRY=NONFERROUS_METALS C1_PARALLEL=1 C1_RUNNER=/usr/bin/true MODEL_TIER=cheap_extract ... scripts/run_c1_fill.sh 000933.SZ` generated a NONFERROUS prompt with 6 fillable nodes and reported `processed=1`, `failed=0`.

## Completed batch 94

- Batch target: `NONFERROUS_METALS`, A-share, `cheap_extract`
- Stocks completed: `000933.SZ`, `603407.SH`, `600301.SH`, `601069.SH`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Parallel runner: `C1_INDUSTRY=NONFERROUS_METALS`, `C1_PARALLEL=2`, via hardened `scripts/run_c1_fill.sh`
- Nodes handled: 24 cheap_extract targets
- Execution note:
  - All 4 child runs exited 0 and the hardened status summary reported `processed=4`, `failed=0`.
  - `000933.SZ`, `603407.SH`, `600301.SH`, and `601069.SH` each changed exactly the 6 target dpids.
  - `000933.SZ:L3.channel.mix` and `600301.SH:L3.channel.mix` used annual-report sales-mode evidence showing direct sales at 100%.
  - `603407.SH:L3.channel.mix` and `601069.SH:L3.channel.mix` were kept `Unknown` with `missing_reason: no_local_evidence` because local evidence did not directly disclose direct/distributor/ecommerce/other channel split.
  - Parent restored standard single-line `scores.formula` formatting after child safe-dump wrapping in `603407.SH` and `601069.SH`.
- Structural diff after run:
  - all 4 files changed only `L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`
  - Non-`nodes` YAML payload is unchanged for all 4 files
- Post-run cheap_extract dry-run:
  - all 4 stocks now show `Fillable: 0` / `没有可填字段`
- Scoped closed-loop verifier:
  - full verifier output: `/tmp/nonferrous_closed_loop_after_batch94.json`
  - full hard violations: 0
  - full soft warnings: 11797
  - target-node violations filtered to the 24 batch dpids: 0
  - target-node evidence_quality type and old-key check: 0 bad target nodes
  - target-file soft warnings: 6 historical non-target warnings only
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count: 163521`
- Test gate after batch: `tests/test_apply_yaml_patch.py tests/test_prompt_gen_schema_block.py tests/test_prompt_gen_governance.py tests/test_schema_validator.py` passed, 83 tests
- Diff hygiene after batch: `git diff --check` passed
- Scope audit after batch: `fillable_total=111378`, `skipped_total=23594`, `cheap_extract=8880`

## Completed batch 95

- Batch target: `NONFERROUS_METALS`, A-share, `cheap_extract`
- Stocks completed: `601212.SH`, `001337.SZ`, `002532.SZ`, `301531.SZ`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Parallel runner: `C1_INDUSTRY=NONFERROUS_METALS`, `C1_PARALLEL=2`, via hardened `scripts/run_c1_fill.sh`
- Nodes handled: 24 cheap_extract targets
- Execution note:
  - All 4 child runs exited 0 and the hardened status summary reported `processed=4`, `failed=0`.
  - `601212.SH`, `001337.SZ`, `002532.SZ`, and `301531.SZ` each changed exactly the 6 target dpids.
  - All 4 `L3.channel.mix` nodes were kept `Unknown` with `missing_reason: no_local_evidence` because local evidence did not directly disclose direct/distributor/ecommerce/other channel split.
  - Parent restored standard single-line `scores.formula` formatting after child safe-dump wrapping in `601212.SH`, `002532.SZ`, and `301531.SZ`.
- Structural diff after run:
  - all 4 files changed only `L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`
  - Non-`nodes` YAML payload is unchanged for all 4 files
- Post-run cheap_extract dry-run:
  - all 4 stocks now show `Fillable: 0` / `没有可填字段`
- Scoped closed-loop verifier:
  - full verifier output: `/tmp/nonferrous_closed_loop_after_batch95.json`
  - full hard violations: 0
  - full soft warnings: 11797
  - target-node violations filtered to the 24 batch dpids: 0
  - target-node evidence_quality type and old-key check: 0 bad target nodes
  - target-file soft warnings: 9 historical non-target warnings only
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count: 163501`
- Test gate after batch: `tests/test_apply_yaml_patch.py tests/test_prompt_gen_schema_block.py tests/test_prompt_gen_governance.py tests/test_schema_validator.py` passed, 83 tests
- Diff hygiene after batch: `git diff --check` passed
- Scope audit after batch: `fillable_total=111354`, `skipped_total=23618`, `cheap_extract=8856`

## Completed batch 96

- Batch target: `NONFERROUS_METALS`, A-share, `cheap_extract`
- Stocks completed: `600219.SH`, `600459.SH`, `600988.SH`, `601677.SH`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Parallel runner: `C1_INDUSTRY=NONFERROUS_METALS`, `C1_PARALLEL=2`, via hardened `scripts/run_c1_fill.sh`
- Nodes handled: 24 cheap_extract targets
- Execution note:
  - All 4 child runs exited 0 and the hardened status summary reported `processed=4`, `failed=0`.
  - `600219.SH`, `600459.SH`, `600988.SH`, and `601677.SH` each changed exactly the 6 target dpids.
  - All 4 `L3.channel.mix` nodes were kept `Unknown` with `missing_reason: no_local_evidence` because local evidence did not directly disclose direct/distributor/ecommerce/other channel split.
  - Parent restored standard single-line `scores.formula` formatting after child safe-dump wrapping in `600219.SH`, `600459.SH`, and `600988.SH`.
- Structural diff after run:
  - all 4 files changed only `L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`
  - Non-`nodes` YAML payload is unchanged for all 4 files
- Post-run cheap_extract dry-run:
  - all 4 stocks now show `Fillable: 0` / `没有可填字段`
- Scoped closed-loop verifier:
  - full verifier output: `/tmp/nonferrous_closed_loop_after_batch96.json`
  - full hard violations: 0
  - full soft warnings: 11797
  - target-node violations filtered to the 24 batch dpids: 0
  - target-node evidence_quality type and old-key check: 0 bad target nodes
  - target-file soft warnings: 4 historical non-target warnings only
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count: 163481`
- Test gate after batch: `tests/test_apply_yaml_patch.py tests/test_prompt_gen_schema_block.py tests/test_prompt_gen_governance.py tests/test_schema_validator.py` passed, 83 tests
- Diff hygiene after batch: `git diff --check` passed
- Scope audit after batch: `fillable_total=111330`, `skipped_total=23642`, `cheap_extract=8832`

## Completed batch 97

- Batch target: `NONFERROUS_METALS`, A-share, `cheap_extract`
- Stocks completed: `601958.SH`, `688811.SH`, `920068.BJ`, `000060.SZ`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Parallel runner: `C1_INDUSTRY=NONFERROUS_METALS`, `C1_PARALLEL=2`, via hardened `scripts/run_c1_fill.sh`
- Nodes handled: 24 cheap_extract targets
- Execution note:
  - All 4 child runs exited 0 and the hardened status summary reported `processed=4`, `failed=0`.
  - `601958.SH`, `688811.SH`, `920068.BJ`, and `000060.SZ` each changed exactly the 6 target dpids.
  - `000060.SZ:L3.channel.mix` used 2025 annual-report sales-mode evidence showing direct sales at 100%.
  - `601958.SH:L3.channel.mix`, `688811.SH:L3.channel.mix`, and `920068.BJ:L3.channel.mix` were kept `Unknown` with `missing_reason: no_local_evidence` because local evidence did not directly disclose direct/distributor/ecommerce/other channel split.
  - Parent restored standard single-line `scores.formula` formatting after child safe-dump wrapping in `688811.SH`, `920068.BJ`, and `000060.SZ`.
  - The target-node guard caught and normalized English notes/summaries plus indentation drift in `000060.SZ` before final validation.
- Structural diff after run:
  - all 4 files changed only `L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`
  - Non-`nodes` YAML payload is unchanged for all 4 files
- Post-run cheap_extract dry-run:
  - all 4 stocks now show `Fillable: 0` / `没有可填字段`
- Scoped closed-loop verifier:
  - full verifier output: `/tmp/nonferrous_closed_loop_after_batch97.json`
  - full hard violations: 0
  - full soft warnings: 11797
  - target-node violations filtered to the 24 batch dpids: 0
  - target-node evidence_quality type, old-key, and English-residue check: 0 bad target nodes
  - target-file soft warnings: 9 historical non-target warnings only
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count: 163460`
- Test gate after batch: `tests/test_apply_yaml_patch.py tests/test_prompt_gen_schema_block.py tests/test_prompt_gen_governance.py tests/test_schema_validator.py` passed, 83 tests
- Diff hygiene after batch: `git diff --check` passed
- Scope audit after batch: `fillable_total=111306`, `skipped_total=23666`, `cheap_extract=8808`

## Completed batch 98

- Batch target: `ANTI_INVOLUTION_CYCLICAL`, A-share, `cheap_extract`
- Stocks completed: `000510.SZ`, `000762.SZ`, `000877.SZ`, `001212.SZ`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Parallel runner: `C1_INDUSTRY=ANTI_INVOLUTION_CYCLICAL`, `C1_PARALLEL=2`, via hardened `scripts/run_c1_fill.sh`
- Nodes handled: 24 cheap_extract targets
- Execution note:
  - All 4 child runs exited 0 and the hardened status summary reported `processed=4`, `failed=0`.
  - `000510.SZ`, `000762.SZ`, `000877.SZ`, and `001212.SZ` each changed exactly the 6 target dpids.
  - All 4 `L3.channel.mix` nodes were kept `Unknown` because local annual-report/main-business evidence did not directly disclose direct/distributor/ecommerce/other channel split.
  - Parent restored standard single-line `scores.formula` formatting after child safe-dump wrapping in all 4 files.
- Structural diff after run:
  - all 4 files changed only `L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`
  - Non-`nodes` YAML payload is unchanged for all 4 files
- Post-run cheap_extract dry-run:
  - all 4 stocks now show `Fillable: 0` / `没有可填字段`
- Scoped closed-loop verifier:
  - full verifier output: `/tmp/anti_inv_closed_loop_after_batch98.json`
  - full hard violations: 0
  - full soft warnings: 11797
  - target-node violations filtered to the 24 batch dpids: 0
  - target-node evidence_quality type, old-key, and English-residue check: 0 bad target nodes
  - target-file soft warnings: 12 historical non-target warnings only
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count: 163440`
- Test gate after batch: `tests/test_apply_yaml_patch.py tests/test_prompt_gen_schema_block.py tests/test_prompt_gen_governance.py tests/test_schema_validator.py` passed, 83 tests
- Diff hygiene after batch: `git diff --check` passed
- Scope audit after batch: `fillable_total=111282`, `skipped_total=23690`, `cheap_extract=8784`

## Pipeline hardening after batch 98

- `scripts/run_c1_fill.sh` now normalizes processed overlay files after a successful batch.
- The normalizer is intentionally narrow: it only rewrites the known two-line wrapped `scores.formula` text back to the standard single-line formula, and does not parse or re-dump YAML.
- This covers child Codex runs that edit overlay YAML directly instead of applying changes through `scripts/apply_yaml_patch.py`.

## Completed batch 99

- Batch target: `ANTI_INVOLUTION_CYCLICAL`, A-share, `cheap_extract`
- Stocks completed: `002080.SZ`, `002096.SZ`, `002170.SZ`, `002497.SZ`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Parallel runner: `C1_INDUSTRY=ANTI_INVOLUTION_CYCLICAL`, `C1_PARALLEL=2`, via hardened `scripts/run_c1_fill.sh`
- Nodes handled: 24 cheap_extract targets
- Execution note:
  - All 4 child runs exited 0 and the hardened status summary reported `processed=4`, `failed=0`.
  - `002080.SZ`, `002096.SZ`, `002170.SZ`, and `002497.SZ` each changed exactly the 6 target dpids.
  - All 4 `L3.channel.mix` nodes were kept `Unknown`; `002170.SZ` only disclosed direct/dealer combined sales mode at 100% without a split, and the other three did not directly disclose direct/distributor/ecommerce/other channel shares.
  - Runner post-processing automatically restored wrapped `scores.formula` in `002080.SZ`, `002096.SZ`, and `002497.SZ` (`formula_normalized=3`).
- Structural diff after run:
  - all 4 files changed only `L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`
  - Non-`nodes` YAML payload is unchanged for all 4 files
- Post-run cheap_extract dry-run:
  - all 4 stocks now show `Fillable: 0` / `没有可填字段`
- Scoped closed-loop verifier:
  - full verifier output: `/tmp/anti_inv_closed_loop_after_batch99.json`
  - full hard violations: 0
  - full soft warnings: 11797
  - target-node violations filtered to the 24 batch dpids: 0
  - target-node evidence_quality type, old-key, and English-residue check: 0 bad target nodes
  - target-file soft warnings: 12 historical non-target warnings only
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count: 163420`
- Test gate after batch: `tests/test_apply_yaml_patch.py tests/test_prompt_gen_schema_block.py tests/test_prompt_gen_governance.py tests/test_schema_validator.py` passed, 83 tests
- Diff hygiene after batch: `git diff --check` passed
- Scope audit after batch: `fillable_total=111258`, `skipped_total=23714`, `cheap_extract=8760`

## Completed batch 100

- Batch target: `ANTI_INVOLUTION_CYCLICAL`, A-share, `cheap_extract`
- Stocks completed: `002588.SZ`, `600010.SH`, `600307.SH`, `600326.SH`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Parallel runner: `C1_INDUSTRY=ANTI_INVOLUTION_CYCLICAL`, `C1_PARALLEL=2`, via hardened `scripts/run_c1_fill.sh`
- Nodes handled: 24 cheap_extract targets
- Execution note:
  - All 4 child runs exited 0 and the hardened status summary reported `processed=4`, `failed=0`.
  - `002588.SZ`, `600010.SH`, `600307.SH`, and `600326.SH` each changed exactly the 6 target dpids.
  - `002588.SZ:L3.channel.mix` used 2025 annual-report sales-mode evidence: distributor sales 80.05%, direct-and-other combined 19.95%; direct and other were not split, so `direct_pct` remains null and `others_pct` carries the combined residual with notes.
  - `600010.SH`, `600307.SH`, and `600326.SH` kept `L3.channel.mix` as `Unknown` because local evidence did not directly disclose direct/distributor/ecommerce/other channel split.
  - Runner post-processing automatically restored wrapped `scores.formula` in `002588.SZ`, `600010.SH`, and `600326.SH` (`formula_normalized=3`).
- Structural diff after run:
  - all 4 files changed only `L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`
  - Non-`nodes` YAML payload is unchanged for all 4 files
- Post-run cheap_extract dry-run:
  - all 4 stocks now show `Fillable: 0` / `没有可填字段`
- Scoped closed-loop verifier:
  - full verifier output: `/tmp/anti_inv_closed_loop_after_batch100.json`
  - full hard violations: 0
  - full soft warnings: 11797
  - target-node violations filtered to the 24 batch dpids: 0
  - target-node evidence_quality type, old-key, and English-residue check: 0 bad target nodes
  - target-file soft warnings: 12 historical non-target warnings only
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count: 163399`
- Test gate after batch: `tests/test_apply_yaml_patch.py tests/test_prompt_gen_schema_block.py tests/test_prompt_gen_governance.py tests/test_schema_validator.py` passed, 83 tests
- Diff hygiene after batch: `git diff --check` passed
- Scope audit after batch: `fillable_total=111234`, `skipped_total=23738`, `cheap_extract=8736`

## Completed batch 101

- Batch target: `ANTI_INVOLUTION_CYCLICAL`, A-share, `cheap_extract`
- Stocks completed: `600331.SH`, `600378.SH`, `600507.SH`, `601005.SH`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Parallel runner: `C1_INDUSTRY=ANTI_INVOLUTION_CYCLICAL`, `C1_PARALLEL=2`, via hardened `scripts/run_c1_fill.sh`
- Nodes handled: 24 cheap_extract targets
- Execution note:
  - All 4 child runs exited 0 and the hardened status summary reported `processed=4`, `failed=0`.
  - `600331.SH`, `600378.SH`, `600507.SH`, and `601005.SH` each changed exactly the 6 target dpids.
  - `600378.SH:L3.channel.mix` used 2025 annual-report sales-mode evidence: direct sales 94.0283%, distributor sales 5.9717%, ecommerce and other 0%.
  - `600331.SH`, `600507.SH`, and `601005.SH` kept `L3.channel.mix` as `Unknown` because local evidence did not directly disclose direct/distributor/ecommerce/other channel split.
  - Runner post-processing found no wrapped `scores.formula` to restore (`formula_normalized=0`).
  - One English channel-mix note in `600507.SH` was normalized to Chinese before final validation.
- Structural diff after run:
  - all 4 files changed only `L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`
  - Non-`nodes` YAML payload is unchanged for all 4 files
- Post-run cheap_extract dry-run:
  - all 4 stocks now show `Fillable: 0` / `没有可填字段`
- Scoped closed-loop verifier:
  - full verifier output: `/tmp/anti_inv_closed_loop_after_batch101.json`
  - full hard violations: 0
  - full soft warnings: 11797
  - target-node violations filtered to the 24 batch dpids: 0
  - target-node evidence_quality type, old-key, and English-residue check: 0 bad target nodes
  - target-file soft warnings: 12 historical non-target warnings only
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count: 163378`
- Test gate after batch: `tests/test_apply_yaml_patch.py tests/test_prompt_gen_schema_block.py tests/test_prompt_gen_governance.py tests/test_schema_validator.py` passed, 83 tests
- Diff hygiene after batch: `git diff --check` passed
- Scope audit after batch: `fillable_total=111210`, `skipped_total=23762`, `cheap_extract=8712`

## Completed batch 102

- Batch target: `ANTI_INVOLUTION_CYCLICAL`, A-share, `cheap_extract`
- Stocks completed: `601026.SH`, `601992.SH`, `603406.SH`, `603663.SH`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Parallel runner: `C1_INDUSTRY=ANTI_INVOLUTION_CYCLICAL`, `C1_PARALLEL=2`, via hardened `scripts/run_c1_fill.sh`
- Nodes handled: 24 cheap_extract targets
- Execution note:
  - All 4 child runs exited 0 and the hardened status summary reported `processed=4`, `failed=0`.
  - `601026.SH`, `601992.SH`, `603406.SH`, and `603663.SH` each changed exactly the 6 target dpids.
  - `603406.SH:L3.channel.mix` used annual-report sales-mode evidence showing direct sales at 100%.
  - `601026.SH`, `601992.SH`, and `603663.SH` kept `L3.channel.mix` as `Unknown` because local evidence did not directly disclose direct/distributor/ecommerce/other channel split.
  - Runner post-processing automatically restored wrapped `scores.formula` in `603663.SH` (`formula_normalized=1`).
- Structural diff after run:
  - all 4 files changed only `L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`
  - Non-`nodes` YAML payload is unchanged for all 4 files
- Post-run cheap_extract dry-run:
  - all 4 stocks now show `Fillable: 0` / `没有可填字段`
- Scoped closed-loop verifier:
  - full verifier output: `/tmp/anti_inv_closed_loop_after_batch102.json`
  - full hard violations: 0
  - full soft warnings: 11797
  - target-node violations filtered to the 24 batch dpids: 0
  - target-node evidence_quality type, old-key, and English-residue check: 0 bad target nodes
  - target-file soft warnings: 12 historical non-target warnings only
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count: 163357`
- Test gate after batch: `tests/test_apply_yaml_patch.py tests/test_prompt_gen_schema_block.py tests/test_prompt_gen_governance.py tests/test_schema_validator.py` passed, 83 tests
- Diff hygiene after batch: `git diff --check` passed
- Scope audit after batch: `fillable_total=111186`, `skipped_total=23786`, `cheap_extract=8688`

## Completed batch 103

- Batch target: `ANTI_INVOLUTION_CYCLICAL`, A-share, `cheap_extract`
- Stocks completed: `603737.SH`, `603938.SH`, `605016.SH`, `605318.SH`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Parallel runner: `C1_INDUSTRY=ANTI_INVOLUTION_CYCLICAL`, `C1_PARALLEL=2`, via hardened `scripts/run_c1_fill.sh`
- Nodes handled: 24 cheap_extract targets
- Execution note:
  - All 4 child runs exited 0 and the hardened status summary reported `processed=4`, `failed=0`.
  - `603737.SH`, `603938.SH`, `605016.SH`, and `605318.SH` each changed exactly the 6 target dpids.
  - `603938.SH:L3.channel.mix` was corrected after reviewer check against the local 2025 annual-report PDF: direct sales 52.0985%, distributor sales 47.9015%, ecommerce and other 0%.
  - The initial model output for `603938.SH:L3.channel.mix` was too conservative; the local annual report includes an explicit sales-channel table with direct and distributor revenue. The non-closed-loop PDF text excerpt was removed from `evidence_sources` after verifier flagged it as an excerpt mis-cite against the metadata-only `L9.disclosure.annual_report` node.
  - `603737.SH`, `605016.SH`, and `605318.SH` kept `L3.channel.mix` as `Unknown` because local evidence did not directly disclose direct/distributor/ecommerce/other channel split.
  - Runner post-processing automatically restored wrapped `scores.formula` in `603737.SH` and `603938.SH` (`formula_normalized=2`).
- Structural diff after run:
  - all 4 files changed only `L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`
  - Non-`nodes` YAML payload is unchanged for all 4 files
- Post-run cheap_extract dry-run:
  - all 4 stocks now show `Fillable: 0` / `没有可填字段`
- Scoped closed-loop verifier:
  - full verifier output: `/tmp/anti_inv_closed_loop_after_batch103.json`
  - full hard violations: 0
  - full soft warnings: 11797
  - target-node violations filtered to the 24 batch dpids: 0
  - target-node evidence_quality type, old-key, and English-residue check: 0 bad target nodes
  - target-file soft warnings: 12 historical non-target warnings only
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count: 163336`
- Test gate after batch: `tests/test_apply_yaml_patch.py tests/test_prompt_gen_schema_block.py tests/test_prompt_gen_governance.py tests/test_schema_validator.py` passed, 83 tests
- Diff hygiene after batch: `git diff --check` passed
- Scope audit after batch: `fillable_total=111162`, `skipped_total=23810`, `cheap_extract=8664`

## Completed batch 104

- Batch target: `DOMESTIC_CONSUMPTION`, A-share, `cheap_extract`
- Stocks completed: `000088.SZ`, `000099.SZ`, `002320.SZ`, `600004.SH`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Parallel runner: `C1_INDUSTRY=DOMESTIC_CONSUMPTION`, `C1_PARALLEL=2`, via hardened `scripts/run_c1_fill.sh`
- Nodes handled: 24 cheap_extract targets
- Execution note:
  - All 4 child runs exited 0 and the hardened status summary reported `processed=4`, `failed=0`.
  - `000088.SZ`, `000099.SZ`, `002320.SZ`, and `600004.SH` each changed exactly the 6 target dpids.
  - `000088.SZ`, `000099.SZ`, and `600004.SH` kept `L3.channel.mix` as `Unknown` because local evidence disclosed business, customer, region, or revenue structure, but not a direct/distributor/ecommerce/other channel split.
  - `002320.SZ:L3.channel.mix` was filled as `Known`: direct sales 95.50%, ecommerce 0%, other 4.50%. The 2025 annual report discloses direct sales 95.50% and agency/consignment sales 4.50%; because the schema has no agency field, the 4.50% agency share is mapped to `others_pct`.
  - Runner post-processing automatically restored wrapped `scores.formula` in `002320.SZ` (`formula_normalized=1`).
- Structural diff after run:
  - all 4 files changed only `L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`
  - Non-`nodes` YAML payload is unchanged for all 4 files
- Post-run cheap_extract dry-run:
  - all 4 stocks now show `Fillable: 0` / `没有可填字段`
- Scoped closed-loop verifier:
  - full verifier output: `/tmp/domestic_closed_loop_after_batch104.json`
  - full hard violations: 0
  - full soft warnings: 11797
  - target-node violations filtered to the 24 batch dpids: 0
  - target-node evidence_quality type, old-key, and English-residue check: 0 bad target nodes
  - target-file soft warnings: 12 historical non-target warnings only
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count: 163315`
- Test gate after batch: `tests/test_apply_yaml_patch.py tests/test_prompt_gen_schema_block.py tests/test_prompt_gen_governance.py tests/test_schema_validator.py` passed, 83 tests
- Diff hygiene after batch: `git diff --check` passed
- Scope audit after batch: `fillable_total=111138`, `skipped_total=23834`, `cheap_extract=8640`

## Completed batch 105

- Batch target: `DOMESTIC_CONSUMPTION`, A-share, `cheap_extract`
- Stocks completed: `600012.SH`, `600233.SH`, `600269.SH`, `600350.SH`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Parallel runner: `C1_INDUSTRY=DOMESTIC_CONSUMPTION`, `C1_PARALLEL=2`, via hardened `scripts/run_c1_fill.sh`
- Nodes handled: 24 cheap_extract targets
- Execution note:
  - All 4 child runs exited 0 and the hardened status summary reported `processed=4`, `skipped=0`, `prompt_failed=0`, `failed=0`.
  - `600012.SH`, `600233.SH`, `600269.SH`, and `600350.SH` each changed exactly the 6 target dpids.
  - All 4 kept `L3.channel.mix` as `Unknown` because local annual-report/main-business evidence disclosed customer, product, region, business-line, or revenue structure, but not a direct/distributor/ecommerce/other channel split.
  - `600350.SH:L1.stock_attr.tags` was manually tightened after review: the model attached a PE percentile excerpt to `L6.path.tag`; the `高PE分位` tag and numeric excerpt were removed, leaving only main-business evidence and the local valuation-path tag.
  - Runner post-processing automatically restored wrapped `scores.formula` in `600269.SH` and `600350.SH` (`formula_normalized=2`).
- Structural diff after run:
  - all 4 files changed only `L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`
  - Non-`nodes` YAML payload is unchanged for all 4 files
- Post-run cheap_extract dry-run:
  - all 4 stocks now show `Fillable: 0` / `没有可填字段`
- Scoped closed-loop verifier:
  - full verifier output: `/tmp/domestic_closed_loop_after_batch105.json`
  - full hard violations: 0
  - full soft warnings: 11797
  - target-node violations filtered to the 24 batch dpids: 0
  - target-node evidence_quality type, old-key, English-residue, and PE-evidence residue check: 0 bad target nodes
  - target-file soft warnings: 12 historical non-target warnings only
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count: 163295`
- Test gate after batch: `tests/test_apply_yaml_patch.py tests/test_prompt_gen_schema_block.py tests/test_prompt_gen_governance.py tests/test_schema_validator.py` passed, 83 tests
- Diff hygiene after batch: `git diff --check` passed
- Scope audit after batch: `fillable_total=111114`, `skipped_total=23858`, `cheap_extract=8616`

## Completed batch 106

- Batch target: `DOMESTIC_CONSUMPTION`, A-share, `cheap_extract`
- Stocks completed: `600377.SH`, `600428.SH`, `600515.SH`, `600548.SH`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Parallel runner: `C1_INDUSTRY=DOMESTIC_CONSUMPTION`, `C1_PARALLEL=2`, via hardened `scripts/run_c1_fill.sh`
- Nodes handled: 24 cheap_extract targets
- Prompt hardening before run:
  - Added `L1.stock_attr.tags` guidance to allow `L6.path.tag` text labels but reject PE/PB percentile, valuation multiple, or percentile-number labels and numeric `L6.path.tag` evidence excerpts.
  - Added schema-block test coverage for this rule; prompt/schema tests passed before running the batch.
- Execution note:
  - All 4 child runs exited 0 and the hardened status summary reported `processed=4`, `skipped=0`, `prompt_failed=0`, `failed=0`.
  - `600377.SH`, `600428.SH`, `600515.SH`, and `600548.SH` each changed exactly the 6 target dpids.
  - All 4 kept `L3.channel.mix` as `Unknown` because local evidence disclosed customer concentration, product/region/business-line structure, or main business, but not a direct/distributor/ecommerce/other channel split.
  - Stock-attribute PE/PB misuse check after run found 0 issues: no PE/PB percentile tag and no numeric excerpt under `L6.path.tag`.
  - Runner post-processing automatically restored wrapped `scores.formula` in all 4 files (`formula_normalized=4`).
- Structural diff after run:
  - all 4 files changed only `L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`
  - Non-`nodes` YAML payload is unchanged for all 4 files
- Post-run cheap_extract dry-run:
  - all 4 stocks now show `Fillable: 0` / `没有可填字段`
- Scoped closed-loop verifier:
  - full verifier output: `/tmp/domestic_closed_loop_after_batch106.json`
  - full hard violations: 0
  - full soft warnings: 11797
  - target-node violations filtered to the 24 batch dpids: 0
  - target-node evidence_quality type, old-key, English-residue, and stock-attribute valuation-misuse check: 0 bad target nodes
  - target-file soft warnings: 12 historical non-target warnings only
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count: 163275`
- Test gate after batch: `tests/test_apply_yaml_patch.py tests/test_prompt_gen_schema_block.py tests/test_prompt_gen_governance.py tests/test_schema_validator.py` passed, 84 tests
- Diff hygiene after batch: `git diff --check` passed
- Scope audit after batch: `fillable_total=111090`, `skipped_total=23882`, `cheap_extract=8592`

## Completed batch 107

- Batch target: `DOMESTIC_CONSUMPTION`, A-share, `cheap_extract`
- Stocks completed: `600611.SH`, `600717.SH`, `601000.SH`, `601006.SH`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Parallel runner: `C1_INDUSTRY=DOMESTIC_CONSUMPTION`, `C1_PARALLEL=2`, via hardened `scripts/run_c1_fill.sh`
- Nodes handled: 24 cheap_extract targets
- Execution note:
  - All 4 child runs exited 0 and the hardened status summary reported `processed=4`, `skipped=0`, `prompt_failed=0`, `failed=0`.
  - `600611.SH`, `600717.SH`, `601000.SH`, and `601006.SH` each changed exactly the 6 target dpids.
  - All 4 kept `L3.channel.mix` as `Unknown` because local evidence disclosed business-line, customer concentration, revenue, or operating structure, but not a direct/distributor/ecommerce/other channel split.
  - `600611.SH` had English natural-language residue in `L3.channel.mix` and `L1.position.growth_rank`; it was manually corrected to Chinese before validation.
  - Stock-attribute PE/PB misuse check after run found 0 issues: no PE/PB percentile tag and no numeric excerpt under `L6.path.tag`.
  - Runner post-processing automatically restored wrapped `scores.formula` in `600611.SH`, `601000.SH`, and `601006.SH` (`formula_normalized=3`).
- Structural diff after run:
  - all 4 files changed only `L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`
  - Non-`nodes` YAML payload is unchanged for all 4 files
- Post-run cheap_extract dry-run:
  - all 4 stocks now show `Fillable: 0` / `没有可填字段`
- Scoped closed-loop verifier:
  - full verifier output: `/tmp/domestic_closed_loop_after_batch107.json`
  - full hard violations: 0
  - full soft warnings: 11797
  - target-node violations filtered to the 24 batch dpids: 0
  - target-node evidence_quality type, old-key, English-residue, and stock-attribute valuation-misuse check: 0 bad target nodes
  - target-file soft warnings: 12 historical non-target warnings only
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count: 163255`
- Test gate after batch: `tests/test_apply_yaml_patch.py tests/test_prompt_gen_schema_block.py tests/test_prompt_gen_governance.py tests/test_schema_validator.py` passed, 84 tests
- Diff hygiene after batch: `git diff --check` passed
- Scope audit after batch: `fillable_total=111066`, `skipped_total=23906`, `cheap_extract=8568`

## Completed batch 108

- Batch target: `DOMESTIC_CONSUMPTION`, A-share, `cheap_extract`
- Stocks completed: `601018.SH`, `601083.SH`, `601228.SH`, `601298.SH`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Parallel runner: `C1_INDUSTRY=DOMESTIC_CONSUMPTION`, `C1_PARALLEL=2`, via hardened `scripts/run_c1_fill.sh`
- Nodes handled: 24 cheap_extract targets
- Prompt hardening before run:
  - Added company-prompt and schema-block rules requiring natural-language fields such as `value.evidence_summary`, `value.notes`, and `missing_reason` to be Chinese; enums, dp_ids, source names, and `no_local_evidence` remain unchanged.
  - Added regression coverage for this language rule; prompt/schema tests passed before running the batch.
- Execution note:
  - All 4 child runs exited 0 and the hardened status summary reported `processed=4`, `skipped=0`, `prompt_failed=0`, `failed=0`.
  - `601018.SH`, `601083.SH`, `601228.SH`, and `601298.SH` each changed exactly the 6 target dpids.
  - All 4 kept `L3.channel.mix` as `Unknown` because local evidence disclosed industry/product/customer/region/trade structure, but not a direct/distributor/ecommerce/other channel split.
  - Natural-language English residue check after run found 0 issues.
  - Stock-attribute PE/PB misuse check after run found 0 issues: no PE/PB percentile tag and no numeric excerpt under `L6.path.tag`.
  - Runner post-processing automatically restored wrapped `scores.formula` in `601018.SH` and `601083.SH` (`formula_normalized=2`).
- Structural diff after run:
  - all 4 files changed only `L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`
  - Non-`nodes` YAML payload is unchanged for all 4 files
- Post-run cheap_extract dry-run:
  - all 4 stocks now show `Fillable: 0` / `没有可填字段`
- Scoped closed-loop verifier:
  - full verifier output: `/tmp/domestic_closed_loop_after_batch108.json`
  - full hard violations: 0
  - full soft warnings: 11797
  - target-node violations filtered to the 24 batch dpids: 0
  - target-node evidence_quality type, old-key, English-residue, and stock-attribute valuation-misuse check: 0 bad target nodes
  - target-file soft warnings: 12 historical non-target warnings only
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count: 163235`
- Test gate after batch: `tests/test_apply_yaml_patch.py tests/test_prompt_gen_schema_block.py tests/test_prompt_gen_governance.py tests/test_schema_validator.py` passed, 85 tests
- Diff hygiene after batch: `git diff --check` passed
- Scope audit after batch: `fillable_total=111042`, `skipped_total=23930`, `cheap_extract=8544`

## Completed batch 109

- Batch target: `DOMESTIC_CONSUMPTION`, A-share, `cheap_extract`
- Stocks completed: `601326.SH`, `601333.SH`, `601598.SH`, `601866.SH`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Parallel runner: `C1_INDUSTRY=DOMESTIC_CONSUMPTION`, `C1_PARALLEL=2`, via hardened `scripts/run_c1_fill.sh`
- Nodes handled: 24 cheap_extract targets
- Execution note:
  - All 4 child runs exited 0 and the hardened status summary reported `processed=4`, `skipped=0`, `prompt_failed=0`, `failed=0`.
  - `601326.SH`, `601333.SH`, `601598.SH`, and `601866.SH` each changed exactly the 6 target dpids.
  - All 4 kept `L3.channel.mix` as `Unknown` because local evidence disclosed business-line, customer, region, revenue, or operating structure, but not a direct/distributor/ecommerce/other channel split.
  - Natural-language English residue check after run found 0 issues.
  - Stock-attribute PE/PB misuse check after run found 0 issues: no PE/PB percentile tag and no numeric excerpt under `L6.path.tag`.
  - Runner post-processing found no wrapped `scores.formula` to restore (`formula_normalized=0`).
- Structural diff after run:
  - all 4 files changed only `L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`
  - Non-`nodes` YAML payload is unchanged for all 4 files
- Post-run cheap_extract dry-run:
  - all 4 stocks now show `Fillable: 0` / `没有可填字段`
- Scoped closed-loop verifier:
  - full verifier output: `/tmp/domestic_closed_loop_after_batch109.json`
  - full hard violations: 0
  - full soft warnings: 11797
  - target-node violations filtered to the 24 batch dpids: 0
  - target-node evidence_quality type, old-key, English-residue, and stock-attribute valuation-misuse check: 0 bad target nodes
  - target-file soft warnings: 12 historical non-target warnings only
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count: 163215`
- Test gate after batch: `tests/test_apply_yaml_patch.py tests/test_prompt_gen_schema_block.py tests/test_prompt_gen_governance.py tests/test_schema_validator.py` passed, 85 tests
- Diff hygiene after batch: `git diff --check` passed
- Scope audit after batch: `fillable_total=111018`, `skipped_total=23954`, `cheap_extract=8520`

## Completed batch 110

- Batch target: `DOMESTIC_CONSUMPTION`, A-share, `cheap_extract`
- Stocks completed: `601872.SH`, `601880.SH`, `603565.SH`, `603871.SH`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Parallel runner: `C1_INDUSTRY=DOMESTIC_CONSUMPTION`, `C1_PARALLEL=2`, via hardened `scripts/run_c1_fill.sh`
- Nodes handled: 24 cheap_extract targets
- Execution note:
  - All 4 child runs exited 0 and the hardened status summary reported `processed=4`, `skipped=0`, `prompt_failed=0`, `failed=0`.
  - `601872.SH`, `601880.SH`, `603565.SH`, and `603871.SH` each changed exactly the 6 target dpids.
  - All 4 kept `L3.channel.mix` as `Unknown` because local evidence disclosed business-line, customer, region, revenue, product, or operating structure, but not a direct/distributor/ecommerce/other channel split.
  - Natural-language English residue check after run found 0 issues.
  - Stock-attribute PE/PB misuse check after run found 0 issues: no PE/PB percentile tag and no numeric excerpt under `L6.path.tag`.
  - Runner post-processing restored wrapped `scores.formula` in `603871.SH` (`formula_normalized=1`).
- Structural diff after run:
  - all 4 files changed only `L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`
  - Non-`nodes` YAML payload is unchanged for all 4 files
- Post-run cheap_extract dry-run:
  - all 4 stocks now show `Fillable: 0` / `没有可填字段`
- Scoped closed-loop verifier:
  - full verifier output: `/tmp/domestic_closed_loop_after_batch110.json`
  - full hard violations: 0
  - full soft warnings: 11797
  - target-node violations filtered to the 24 batch dpids: 0
  - target-node evidence_quality type, old-key, English-residue, and stock-attribute valuation-misuse check: 0 bad target nodes
  - target-file soft warnings: 12 historical non-target warnings only
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count: 163195`
- Test gate after batch: `tests/test_apply_yaml_patch.py tests/test_prompt_gen_schema_block.py tests/test_prompt_gen_governance.py tests/test_schema_validator.py` passed, 85 tests
- Diff hygiene after batch: `git diff --check` passed
- Scope audit after batch: `fillable_total=110994`, `skipped_total=23978`, `cheap_extract=8496`
- Residual scope note: `DOMESTIC_CONSUMPTION` no longer appears in the current top cheap_extract candidate list; next top cheap_extract candidates start with `SEMI_EQUIPMENT/688268.SH`, `STORAGE_GRID/001393.SZ`, and `STORAGE_GRID/301599.SZ`.

## Completed batch 111

- Batch target: `FINANCIAL_HIGH_DIVIDEND`, A-share, `cheap_extract`
- Stocks completed: `000539.SZ`, `000543.SZ`, `000875.SZ`, `000958.SZ`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Parallel runner: `C1_INDUSTRY=FINANCIAL_HIGH_DIVIDEND`, `C1_PARALLEL=2`, via hardened `scripts/run_c1_fill.sh`
- Nodes handled: 24 cheap_extract targets
- Execution note:
  - All 4 child runs exited 0 and the hardened status summary reported `processed=4`, `skipped=0`, `prompt_failed=0`, `failed=0`.
  - `000539.SZ`, `000543.SZ`, `000875.SZ`, and `000958.SZ` each changed exactly the 6 target dpids.
  - All 4 kept `L3.channel.mix` as `Unknown` because local evidence disclosed customer, product, region, revenue, or payment/sales-mode structure, but not a direct/distributor/ecommerce/other channel split.
  - Natural-language English residue check after run found 0 issues.
  - Stock-attribute PE/PB misuse check after run found 0 issues: no PE/PB percentile tag and no numeric excerpt under `L6.path.tag`.
  - Runner post-processing restored wrapped `scores.formula` in `000543.SZ` and `000958.SZ` (`formula_normalized=2`).
- Structural diff after run:
  - all 4 files changed only `L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`
  - Non-`nodes` YAML payload is unchanged for all 4 files
- Post-run cheap_extract dry-run:
  - all 4 stocks now show `Fillable: 0` / `没有可填字段`
- Scoped closed-loop verifier:
  - full verifier output: `/tmp/domestic_closed_loop_after_batch111.json`
  - full hard violations: 0
  - full soft warnings: 11797
  - target-node violations filtered to the 24 batch dpids: 0
  - target-node evidence_quality type, old-key, English-residue, and stock-attribute valuation-misuse check: 0 bad target nodes
  - target-file soft warnings: 12 historical non-target warnings only
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count: 163175`
- Test gate after batch: `tests/test_apply_yaml_patch.py tests/test_prompt_gen_schema_block.py tests/test_prompt_gen_governance.py tests/test_schema_validator.py` passed, 85 tests
- Diff hygiene after batch: `git diff --check` passed
- Scope audit after batch: `fillable_total=110970`, `skipped_total=24002`, `cheap_extract=8472`
- Residual scope note: next cheap_extract candidates still include singleton/small industry groups first, then `FINANCIAL_HIGH_DIVIDEND` continues at `000983.SZ`, `002128.SZ`, `002608.SZ`, and `002911.SZ`.

## Completed batch 112

- Batch target: `FINANCIAL_HIGH_DIVIDEND`, A-share, `cheap_extract`
- Stocks completed: `000983.SZ`, `002128.SZ`, `002608.SZ`, `002911.SZ`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Parallel runner: `C1_INDUSTRY=FINANCIAL_HIGH_DIVIDEND`, `C1_PARALLEL=2`, via hardened `scripts/run_c1_fill.sh`
- Nodes handled: 24 cheap_extract targets
- Execution note:
  - All 4 child runs exited 0 and the hardened status summary reported `processed=4`, `skipped=0`, `prompt_failed=0`, `failed=0`.
  - `000983.SZ`, `002128.SZ`, `002608.SZ`, and `002911.SZ` each changed exactly the 6 target dpids.
  - All 4 kept `L3.channel.mix` as `Unknown` because local evidence disclosed customer, product, region, revenue, business-model, or sales-mode structure, but not a direct/distributor/ecommerce/other channel split.
  - Natural-language English residue check after run found 0 issues.
  - Stock-attribute PE/PB misuse check after run found 0 issues: no PE/PB percentile tag and no numeric excerpt under `L6.path.tag`.
  - Runner post-processing restored wrapped `scores.formula` in all 4 files (`formula_normalized=4`).
- Structural diff after run:
  - all 4 files changed only `L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`
  - Non-`nodes` YAML payload is unchanged for all 4 files
- Post-run cheap_extract dry-run:
  - all 4 stocks now show `Fillable: 0` / `没有可填字段`
- Scoped closed-loop verifier:
  - full verifier output: `/tmp/domestic_closed_loop_after_batch112.json`
  - full hard violations: 0
  - full soft warnings: 11797
  - target-node violations filtered to the 24 batch dpids: 0
  - target-node evidence_quality type, old-key, English-residue, and stock-attribute valuation-misuse check: 0 bad target nodes
  - target-file soft warnings: 12 historical non-target warnings only
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count: 163155`
- Test gate after batch: `tests/test_apply_yaml_patch.py tests/test_prompt_gen_schema_block.py tests/test_prompt_gen_governance.py tests/test_schema_validator.py` passed, 85 tests
- Diff hygiene after batch: `git diff --check` passed
- Scope audit after batch: `fillable_total=110946`, `skipped_total=24026`, `cheap_extract=8448`
- Residual scope note: `FINANCIAL_HIGH_DIVIDEND` continues at `600021.SH`, `600027.SH`, `600032.SH`, and `600095.SH`.

## Completed batch 113

- Batch target: `FINANCIAL_HIGH_DIVIDEND`, A-share, `cheap_extract`
- Stocks completed: `600021.SH`, `600027.SH`, `600032.SH`, `600095.SH`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Parallel runner: `C1_INDUSTRY=FINANCIAL_HIGH_DIVIDEND`, `C1_PARALLEL=2`, via hardened `scripts/run_c1_fill.sh`
- Nodes handled: 24 cheap_extract targets
- Execution note:
  - All 4 child runs exited 0 and the hardened status summary reported `processed=4`, `skipped=0`, `prompt_failed=0`, `failed=0`.
  - `600021.SH`, `600027.SH`, `600032.SH`, and `600095.SH` each changed exactly the 6 target dpids.
  - `600021.SH` filled `L3.channel.mix` as Known because local disclosure explicitly listed the sales mode as direct sales; the other 3 kept `L3.channel.mix` as `Unknown` because local evidence disclosed customer, product, region, revenue, or business structure, but not a direct/distributor/ecommerce/other channel split.
  - Natural-language English residue check after run found 0 issues.
  - Stock-attribute PE/PB misuse check after run found 0 issues: no PE/PB percentile tag and no numeric excerpt under `L6.path.tag`.
  - Runner post-processing restored wrapped `scores.formula` in `600027.SH`, `600032.SH`, and `600095.SH` (`formula_normalized=3`).
- Structural diff after run:
  - all 4 files changed only `L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`
  - Non-`nodes` YAML payload is unchanged for all 4 files
- Post-run cheap_extract dry-run:
  - all 4 stocks now show `Fillable: 0` / `没有可填字段`
- Scoped closed-loop verifier:
  - full verifier output: `/tmp/domestic_closed_loop_after_batch113.json`
  - full hard violations: 0
  - full soft warnings: 11797
  - target-node violations filtered to the 24 batch dpids: 0
  - target-node evidence_quality type, old-key, English-residue, and stock-attribute valuation-misuse check: 0 bad target nodes
  - target-file soft warnings: 12 historical non-target warnings only
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count: 163134`
- Test gate after batch: `tests/test_apply_yaml_patch.py tests/test_prompt_gen_schema_block.py tests/test_prompt_gen_governance.py tests/test_schema_validator.py` passed, 85 tests
- Diff hygiene after batch: `git diff --check` passed
- Scope audit after batch: `fillable_total=110922`, `skipped_total=24050`, `cheap_extract=8424`
- Residual scope note: `FINANCIAL_HIGH_DIVIDEND` continues at `600098.SH`, `600116.SH`, `600157.SH`, and `600163.SH`.

## Completed batch 114

- Batch target: `FINANCIAL_HIGH_DIVIDEND`, A-share, `cheap_extract`
- Stocks completed: `600098.SH`, `600116.SH`, `600157.SH`, `600163.SH`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Parallel runner: `C1_INDUSTRY=FINANCIAL_HIGH_DIVIDEND`, `C1_PARALLEL=2`, via hardened `scripts/run_c1_fill.sh`
- Nodes handled: 24 cheap_extract targets
- Prompt hardening before run:
  - Added company-prompt self-check limits: child LLM runs must not run default full-overlay or whole-industry `verify_overlay_closed_loop.py`; any child self-check must be scoped to a temporary single-file overlay directory because the outer runner performs the authoritative full verifier/validator/pytest pass.
  - Added regression coverage for this self-check boundary.
- Execution note:
  - Initial batch summary reported `processed=4`, but structural diff detected `600157.SH` had changed 0 target nodes. This false success was corrected by a single-stock rerun of `600157.SH`.
  - Final effective result: all 4 stocks changed exactly the 6 target dpids.
  - `600157.SH` filled `L3.channel.mix` as Known because local disclosure explicitly listed direct sales; the other 3 kept `L3.channel.mix` as `Unknown` because local evidence disclosed customer, product, region, revenue, or business structure, but not a direct/distributor/ecommerce/other channel split.
  - Natural-language English residue check after run found 0 issues.
  - Stock-attribute PE/PB misuse check after run found 0 issues: no PE/PB percentile tag and no numeric excerpt under `L6.path.tag`.
  - Runner post-processing restored wrapped `scores.formula` in `600116.SH`, `600157.SH`, and `600163.SH` during the first batch run (`formula_normalized=3`); the corrective single-stock rerun normalized 0 formulas.
- Structural diff after run:
  - all 4 files changed only `L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`
  - Non-`nodes` YAML payload is unchanged for all 4 files
- Post-run cheap_extract dry-run:
  - all 4 stocks now show `Fillable: 0` / `没有可填字段`
- Scoped closed-loop verifier:
  - full verifier output: `/tmp/domestic_closed_loop_after_batch114.json`
  - full hard violations: 0
  - full soft warnings: 11797
  - target-node violations filtered to the 24 batch dpids: 0
  - target-node evidence_quality type, old-key, English-residue, and stock-attribute valuation-misuse check: 0 bad target nodes
  - target-file soft warnings: 12 historical non-target warnings only
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count: 163113`
- Test gate after batch: `tests/test_apply_yaml_patch.py tests/test_prompt_gen_schema_block.py tests/test_prompt_gen_governance.py tests/test_schema_validator.py` passed, 86 tests
- Diff hygiene after batch: `git diff --check` passed
- Scope audit after batch: `fillable_total=110898`, `skipped_total=24074`, `cheap_extract=8400`
- Residual scope note: `FINANCIAL_HIGH_DIVIDEND` continues at `600167.SH`, `600236.SH`, `600348.SH`, and `600452.SH`.

## Completed batch 115

- Batch target: `FINANCIAL_HIGH_DIVIDEND`, A-share, `cheap_extract`
- Stocks completed: `600167.SH`, `600236.SH`, `600348.SH`, `600452.SH`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Parallel runner: `C1_INDUSTRY=FINANCIAL_HIGH_DIVIDEND`, `C1_PARALLEL=2`, via hardened `scripts/run_c1_fill.sh`
- Nodes handled: 24 cheap_extract targets
- Execution note:
  - All 4 child runs exited 0 and the hardened status summary reported `processed=4`, `skipped=0`, `prompt_failed=0`, `failed=0`.
  - `600167.SH`, `600236.SH`, `600348.SH`, and `600452.SH` each changed exactly the 6 target dpids.
  - `600236.SH` and `600348.SH` filled `L3.channel.mix` as Known because local disclosure explicitly listed direct sales; `600167.SH` and `600452.SH` kept `L3.channel.mix` as `Unknown` because local evidence disclosed customer, product, region, revenue, or business structure, but not a direct/distributor/ecommerce/other channel split.
  - Natural-language English residue check after run found 0 issues.
  - Stock-attribute PE/PB misuse check after run found 0 issues: no PE/PB percentile tag and no numeric excerpt under `L6.path.tag`.
  - Runner post-processing restored wrapped `scores.formula` in `600167.SH`, `600348.SH`, and `600452.SH` (`formula_normalized=3`).
- Structural diff after run:
  - all 4 files changed only `L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`
  - Non-`nodes` YAML payload is unchanged for all 4 files
- Post-run cheap_extract dry-run:
  - all 4 stocks now show `Fillable: 0` / `没有可填字段`
- Scoped closed-loop verifier:
  - full verifier output: `/tmp/domestic_closed_loop_after_batch115.json`
  - full hard violations: 0
  - full soft warnings: 11797
  - target-node violations filtered to the 24 batch dpids: 0
  - target-node evidence_quality type, old-key, English-residue, and stock-attribute valuation-misuse check: 0 bad target nodes
  - target-file soft warnings: 12 historical non-target warnings only
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count: 163091`
- Test gate after batch: `tests/test_apply_yaml_patch.py tests/test_prompt_gen_schema_block.py tests/test_prompt_gen_governance.py tests/test_schema_validator.py` passed, 86 tests
- Diff hygiene after batch: `git diff --check` passed
- Scope audit after batch: `fillable_total=110874`, `skipped_total=24098`, `cheap_extract=8376`
- Residual scope note: `FINANCIAL_HIGH_DIVIDEND` continues at `600475.SH`, `600483.SH`, `600508.SH`, and `600509.SH`.

## Completed batch 116

- Batch target: `FINANCIAL_HIGH_DIVIDEND`, A-share, `cheap_extract`
- Stocks completed: `600475.SH`, `600483.SH`, `600508.SH`, `600509.SH`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Parallel runner: `C1_INDUSTRY=FINANCIAL_HIGH_DIVIDEND`, `C1_PARALLEL=2`, via hardened `scripts/run_c1_fill.sh`
- Nodes handled: 24 cheap_extract targets
- Execution note:
  - All 4 child runs exited 0 and the hardened status summary reported `processed=4`, `skipped=0`, `prompt_failed=0`, `failed=0`.
  - `600475.SH`, `600483.SH`, `600508.SH`, and `600509.SH` each changed exactly the 6 target dpids.
  - `600475.SH` filled `L3.channel.mix` as Known because local disclosure explicitly listed direct sales; the other 3 kept `L3.channel.mix` as `Unknown` because local evidence disclosed customer, product, region, revenue, or business structure, but not a direct/distributor/ecommerce/other channel split.
  - Natural-language English residue check after run found 0 issues.
  - Stock-attribute PE/PB misuse check after run found 0 issues: no PE/PB percentile tag and no numeric excerpt under `L6.path.tag`.
  - Runner post-processing restored wrapped `scores.formula` in `600509.SH` (`formula_normalized=1`).
- Structural diff after run:
  - all 4 files changed only `L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`
  - Non-`nodes` YAML payload is unchanged for all 4 files
- Post-run cheap_extract dry-run:
  - all 4 stocks now show `Fillable: 0` / `没有可填字段`
- Scoped closed-loop verifier:
  - full verifier output: `/tmp/domestic_closed_loop_after_batch116.json`
  - full hard violations: 0
  - full soft warnings: 11797
  - target-node violations filtered to the 24 batch dpids: 0
  - target-node evidence_quality type, old-key, English-residue, and stock-attribute valuation-misuse check: 0 bad target nodes
  - target-file soft warnings: 12 historical non-target warnings only
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count: 163070`
- Test gate after batch: `tests/test_apply_yaml_patch.py tests/test_prompt_gen_schema_block.py tests/test_prompt_gen_governance.py tests/test_schema_validator.py` passed, 86 tests
- Diff hygiene after batch: `git diff --check` passed
- Scope audit after batch: `fillable_total=110850`, `skipped_total=24122`, `cheap_extract=8352`
- Residual scope note: `FINANCIAL_HIGH_DIVIDEND` continues at `600517.SH`, `600546.SH`, `600575.SH`, and `600578.SH`.

## Completed batch 117

- Batch target: `FINANCIAL_HIGH_DIVIDEND`, A-share, `cheap_extract`
- Stocks completed: `600517.SH`, `600546.SH`, `600575.SH`, `600578.SH`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Parallel runner: `C1_INDUSTRY=FINANCIAL_HIGH_DIVIDEND`, `C1_PARALLEL=2`, via hardened `scripts/run_c1_fill.sh`
- Nodes handled: 24 cheap_extract targets
- Execution note:
  - All 4 child runs exited 0 and the hardened status summary reported `processed=4`, `skipped=0`, `prompt_failed=0`, `failed=0`.
  - `600517.SH`, `600546.SH`, `600575.SH`, and `600578.SH` each changed exactly the 6 target dpids.
  - `600546.SH` filled `L3.channel.mix` as Known because local disclosure explicitly listed direct sales and agency sales; the other 3 kept `L3.channel.mix` as `Unknown` because local evidence disclosed customer, product, region, revenue, or business structure, but not a direct/distributor/ecommerce/other channel split.
  - Natural-language English residue check after run found 0 issues.
  - Stock-attribute PE/PB misuse check after run found 0 issues: no PE/PB percentile tag and no numeric excerpt under `L6.path.tag`.
  - Runner post-processing restored wrapped `scores.formula` in `600517.SH`, `600546.SH`, and `600575.SH` (`formula_normalized=3`).
- Structural diff after run:
  - all 4 files changed only `L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`
  - Non-`nodes` YAML payload is unchanged for all 4 files
- Post-run cheap_extract dry-run:
  - all 4 stocks now show `Fillable: 0` / `没有可填字段`
- Scoped closed-loop verifier:
  - full verifier output: `/tmp/domestic_closed_loop_after_batch117.json`
  - full hard violations: 0
  - full soft warnings: 11797
  - target-node violations filtered to the 24 batch dpids: 0
  - target-node evidence_quality type, old-key, English-residue, and stock-attribute valuation-misuse check: 0 bad target nodes
  - target-file soft warnings: 12 historical non-target warnings only
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count: 163049`
- Test gate after batch: `tests/test_apply_yaml_patch.py tests/test_prompt_gen_schema_block.py tests/test_prompt_gen_governance.py tests/test_schema_validator.py` passed, 86 tests
- Diff hygiene after batch: `git diff --check` passed
- Scope audit after batch: `fillable_total=110826`, `skipped_total=24146`, `cheap_extract=8328`
- Residual scope note: `FINANCIAL_HIGH_DIVIDEND` continues at `600635.SH`, `600642.SH`, `600674.SH`, and `600726.SH`.

## Completed batch 118

- Batch target: `FINANCIAL_HIGH_DIVIDEND`, A-share, `cheap_extract`
- Stocks completed: `600635.SH`, `600642.SH`, `600674.SH`, `600726.SH`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Parallel runner: `C1_INDUSTRY=FINANCIAL_HIGH_DIVIDEND`, `C1_PARALLEL=2`, via hardened `scripts/run_c1_fill.sh`
- Nodes handled: 24 cheap_extract targets
- Execution note:
  - All 4 child runs exited 0 and the hardened status summary reported `processed=4`, `skipped=0`, `prompt_failed=0`, `failed=0`.
  - `600635.SH`, `600642.SH`, `600674.SH`, and `600726.SH` each changed exactly the 6 target dpids.
  - All 4 kept `L3.channel.mix` as `Unknown` because local evidence disclosed customer concentration, business lines, product revenue, region revenue, or trade/business scope, but not a direct/distributor/ecommerce/other channel split.
  - Natural-language English residue check after run found 0 issues.
  - Stock-attribute PE/PB misuse check after run found 0 issues: no PE/PB percentile tag and no numeric excerpt under `L6.path.tag`.
  - Runner post-processing restored wrapped `scores.formula` in `600635.SH`, `600674.SH`, and `600726.SH` (`formula_normalized=3`).
- Structural diff after run:
  - all 4 files changed only `L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`
  - Non-`nodes` YAML payload is unchanged for all 4 files
- Post-run cheap_extract dry-run:
  - all 4 stocks now show `Fillable: 0` / `没有可填字段`
- Scoped closed-loop verifier:
  - full verifier output: `/tmp/domestic_closed_loop_after_batch118.json`
  - full hard violations: 0
  - full soft warnings: 11797
  - target-node violations filtered to the 24 batch dpids: 0
  - target-node evidence_quality type, old-key, English-residue, and stock-attribute valuation-misuse check: 0 bad target nodes
  - target-file soft warnings: 12 historical non-target warnings only
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count: 163029`
- Test gate after batch: `tests/test_apply_yaml_patch.py tests/test_prompt_gen_schema_block.py tests/test_prompt_gen_governance.py tests/test_schema_validator.py` passed, 86 tests
- Diff hygiene after batch: `git diff --check` passed
- Scope audit after batch: `fillable_total=110802`, `skipped_total=24170`, `cheap_extract=8304`
- Residual scope note: `FINANCIAL_HIGH_DIVIDEND` continues at `600740.SH`, `600744.SH`, `600795.SH`, and `600821.SH`.

## Completed batch 119

- Batch target: `FINANCIAL_HIGH_DIVIDEND`, A-share, `cheap_extract`
- Stocks completed: `600740.SH`, `600744.SH`, `600795.SH`, `600821.SH`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Parallel runner: `C1_INDUSTRY=FINANCIAL_HIGH_DIVIDEND`, `C1_PARALLEL=2`, via hardened `scripts/run_c1_fill.sh`
- Nodes handled: 24 cheap_extract targets
- Execution note:
  - All 4 child runs exited 0 and the hardened status summary reported `processed=4`, `skipped=0`, `prompt_failed=0`, `failed=0`.
  - `600740.SH`, `600744.SH`, `600795.SH`, and `600821.SH` each changed exactly the 6 target dpids.
  - `600744.SH` filled `L3.channel.mix` as Known because local annual-report disclosure explicitly listed direct sales by sales mode; the other 3 kept `L3.channel.mix` as `Unknown` because local evidence disclosed customer, product, region, revenue, or business structure, but not a direct/distributor/ecommerce/other channel split.
  - Natural-language English residue check after run found 0 issues.
  - Stock-attribute PE/PB misuse check after run found 0 issues: no PE/PB percentile tag and no numeric excerpt under `L6.path.tag`.
  - Runner post-processing restored wrapped `scores.formula` in `600744.SH` and `600821.SH` (`formula_normalized=2`).
- Structural diff after run:
  - all 4 files changed only `L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`
  - Non-`nodes` YAML payload is unchanged for all 4 files
- Post-run cheap_extract dry-run:
  - all 4 stocks now show `Fillable: 0` / `没有可填字段`
- Scoped closed-loop verifier:
  - full verifier output: `/tmp/domestic_closed_loop_after_batch119.json`
  - full hard violations: 0
  - full soft warnings: 11797
  - target-node violations filtered to the 24 batch dpids: 0
  - target-node evidence_quality type, old-key, English-residue, and stock-attribute valuation-misuse check: 0 bad target nodes
  - target-file soft warnings: 12 historical non-target warnings only
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count: 163008`
- Test gate after batch: `tests/test_apply_yaml_patch.py tests/test_prompt_gen_schema_block.py tests/test_prompt_gen_governance.py tests/test_schema_validator.py` passed, 86 tests
- Diff hygiene after batch: `git diff --check` passed
- Scope audit after batch: `fillable_total=110778`, `skipped_total=24194`, `cheap_extract=8280`
- Residual scope note: `FINANCIAL_HIGH_DIVIDEND` continues at `600863.SH`, `600864.SH`, `600886.SH`, and `600905.SH`.

## Completed batch 120

- Batch target: `FINANCIAL_HIGH_DIVIDEND`, A-share, `cheap_extract`
- Stocks completed: `600863.SH`, `600864.SH`, `600886.SH`, `600905.SH`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Parallel runner: `C1_INDUSTRY=FINANCIAL_HIGH_DIVIDEND`, `C1_PARALLEL=2`, via hardened `scripts/run_c1_fill.sh`
- Nodes handled: 24 cheap_extract targets
- Execution note:
  - All 4 child runs exited 0 and the hardened status summary reported `processed=4`, `skipped=0`, `prompt_failed=0`, `failed=0`.
  - `600863.SH`, `600864.SH`, `600886.SH`, and `600905.SH` each changed exactly the 6 target dpids.
  - `600863.SH` filled `L3.channel.mix` as Known because local annual-report disclosure explicitly listed direct sales by sales mode; the other 3 kept `L3.channel.mix` as `Unknown` because local evidence disclosed customer, product, region, revenue, or business structure, but not a direct/distributor/ecommerce/other channel split.
  - Natural-language English residue check after run found 0 issues.
  - Stock-attribute PE/PB misuse check after run found 0 issues: no PE/PB percentile tag and no numeric excerpt under `L6.path.tag`.
  - Runner post-processing restored wrapped `scores.formula` in `600886.SH` and `600905.SH` (`formula_normalized=2`).
- Structural diff after run:
  - all 4 files changed only `L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`
  - Non-`nodes` YAML payload is unchanged for all 4 files
- Post-run cheap_extract dry-run:
  - all 4 stocks now show `Fillable: 0` / `没有可填字段`
- Scoped closed-loop verifier:
  - full verifier output: `/tmp/domestic_closed_loop_after_batch120.json`
  - full hard violations: 0
  - full soft warnings: 11797
  - target-node violations filtered to the 24 batch dpids: 0
  - target-node evidence_quality type, old-key, English-residue, and stock-attribute valuation-misuse check: 0 bad target nodes
  - target-file soft warnings: 12 historical non-target warnings only
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count: 162987`
- Test gate after batch: `tests/test_apply_yaml_patch.py tests/test_prompt_gen_schema_block.py tests/test_prompt_gen_governance.py tests/test_schema_validator.py` passed, 86 tests
- Diff hygiene after batch: `git diff --check` passed
- Scope audit after batch: `fillable_total=110754`, `skipped_total=24218`, `cheap_extract=8256`
- Residual scope note: `FINANCIAL_HIGH_DIVIDEND` continues at `600925.SH`, `600927.SH`, `600956.SH`, and `600971.SH`.

## Completed batch 121

- Batch target: `FINANCIAL_HIGH_DIVIDEND`, A-share, `cheap_extract`
- Stocks completed: `600925.SH`, `600927.SH`, `600956.SH`, `600971.SH`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Parallel runner: `C1_INDUSTRY=FINANCIAL_HIGH_DIVIDEND`, `C1_PARALLEL=2`, via hardened `scripts/run_c1_fill.sh`
- Nodes handled: 24 cheap_extract targets
- Execution note:
  - All 4 child runs exited 0 and the hardened status summary reported `processed=4`, `skipped=0`, `prompt_failed=0`, `failed=0`.
  - `600925.SH`, `600927.SH`, `600956.SH`, and `600971.SH` each changed exactly the 6 target dpids.
  - `600925.SH` filled `L3.channel.mix` as Known because local annual-report disclosure explicitly listed direct sales by sales mode; the other 3 kept `L3.channel.mix` as `Unknown` because local evidence disclosed customer, product, region, revenue, trade or business structure, but not a direct/distributor/ecommerce/other channel split.
  - Natural-language English residue check after run found 0 issues.
  - Stock-attribute PE/PB misuse check after run found 0 issues: no PE/PB percentile tag and no numeric excerpt under `L6.path.tag`.
  - Runner post-processing restored wrapped `scores.formula` in `600925.SH` and `600927.SH` (`formula_normalized=2`).
- Structural diff after run:
  - all 4 files changed only `L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`
  - Non-`nodes` YAML payload is unchanged for all 4 files
- Post-run cheap_extract dry-run:
  - all 4 stocks now show `Fillable: 0` / `没有可填字段`
- Scoped closed-loop verifier:
  - full verifier output: `/tmp/domestic_closed_loop_after_batch121.json`
  - full hard violations: 0
  - full soft warnings: 11797
  - target-node violations filtered to the 24 batch dpids: 0
  - target-node evidence_quality type, old-key, English-residue, and stock-attribute valuation-misuse check: 0 bad target nodes
  - target-file soft warnings: 9 historical non-target warnings only
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count: 162966`
- Test gate after batch: `tests/test_apply_yaml_patch.py tests/test_prompt_gen_schema_block.py tests/test_prompt_gen_governance.py tests/test_schema_validator.py` passed, 86 tests
- Diff hygiene after batch: `git diff --check` passed
- Scope audit after batch: `fillable_total=110730`, `skipped_total=24242`, `cheap_extract=8232`
- Residual scope note: `FINANCIAL_HIGH_DIVIDEND` continues at `600985.SH`, `600995.SH`, `601001.SH`, and `601016.SH`.

## Completed batch 122

- Batch target: `FINANCIAL_HIGH_DIVIDEND`, A-share, `cheap_extract`
- Stocks completed: `600985.SH`, `600995.SH`, `601001.SH`, `601016.SH`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Parallel runner: `C1_INDUSTRY=FINANCIAL_HIGH_DIVIDEND`, `C1_PARALLEL=2`, via hardened `scripts/run_c1_fill.sh`
- Nodes handled: 24 cheap_extract targets
- Execution note:
  - All 4 child runs exited 0 and the hardened status summary reported `processed=4`, `skipped=0`, `prompt_failed=0`, `failed=0`.
  - `600985.SH`, `600995.SH`, `601001.SH`, and `601016.SH` each changed exactly the 6 target dpids.
  - `600985.SH` and `601001.SH` filled `L3.channel.mix` as Known because local annual-report disclosure explicitly listed direct sales by sales mode; `601001.SH` channel `trend` was manually normalized from a Chinese free-text value to `direct_sales_dominant` for consistency with prior batches. The other 2 kept `L3.channel.mix` as `Unknown` because local evidence disclosed customer, product, region, revenue, or business structure, but not a direct/distributor/ecommerce/other channel split.
  - Natural-language English residue check after run found 0 issues.
  - Stock-attribute PE/PB misuse check after run found 0 issues: no PE/PB percentile tag and no numeric excerpt under `L6.path.tag`.
  - Runner post-processing restored wrapped `scores.formula` in `600985.SH` and `600995.SH` (`formula_normalized=2`).
- Structural diff after run:
  - all 4 files changed only `L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`
  - Non-`nodes` YAML payload is unchanged for all 4 files
- Post-run cheap_extract dry-run:
  - all 4 stocks now show `Fillable: 0` / `没有可填字段`
- Scoped closed-loop verifier:
  - full verifier output: `/tmp/domestic_closed_loop_after_batch122.json`
  - full hard violations: 0
  - full soft warnings: 11797
  - target-node violations filtered to the 24 batch dpids: 0
  - target-node evidence_quality type, old-key, English-residue, and stock-attribute valuation-misuse check: 0 bad target nodes
  - target-file soft warnings: 12 historical non-target warnings only
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count: 162944`
- Test gate after batch: `tests/test_apply_yaml_patch.py tests/test_prompt_gen_schema_block.py tests/test_prompt_gen_governance.py tests/test_schema_validator.py` passed, 86 tests
- Diff hygiene after batch: `git diff --check` passed
- Scope audit after batch: `fillable_total=110706`, `skipped_total=24266`, `cheap_extract=8208`
- Residual scope note: `FINANCIAL_HIGH_DIVIDEND` continues at `601139.SH`, `601619.SH`, `601666.SH`, and `601699.SH`, with `601918.SH` also still showing cheap_extract fillables.

## Completed batch 123

- Batch target: `FINANCIAL_HIGH_DIVIDEND`, A-share, `cheap_extract`
- Stocks completed: `601139.SH`, `601619.SH`, `601666.SH`, `601699.SH`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Parallel runner: `C1_INDUSTRY=FINANCIAL_HIGH_DIVIDEND`, `C1_PARALLEL=2`, via hardened `scripts/run_c1_fill.sh`
- Nodes handled: 24 cheap_extract targets
- Execution note:
  - All 4 child runs exited 0 and the hardened status summary reported `processed=4`, `skipped=0`, `prompt_failed=0`, `failed=0`.
  - `601139.SH`, `601619.SH`, `601666.SH`, and `601699.SH` each changed exactly the 6 target dpids.
  - All 4 kept `L3.channel.mix` as `Unknown` because local evidence disclosed customer, product, region, revenue, or business structure, but not a direct/distributor/ecommerce/other channel split.
  - Natural-language English residue check after run found 0 issues.
  - Stock-attribute PE/PB misuse check after run found 0 issues: no PE/PB percentile tag and no numeric excerpt under `L6.path.tag`.
  - Runner post-processing restored wrapped `scores.formula` in all 4 target overlays (`formula_normalized=4`).
- Structural diff after run:
  - all 4 files changed only `L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`
  - Non-`nodes` YAML payload is unchanged for all 4 files
- Post-run cheap_extract dry-run:
  - all 4 stocks now show `Fillable: 0` / `没有可填字段`
- Scoped closed-loop verifier:
  - full verifier output: `/tmp/domestic_closed_loop_after_batch123.json`
  - full hard violations: 0
  - full soft warnings: 11797
  - target-node violations filtered to the 24 batch dpids: 0
  - target-node evidence_quality type, old-key, English-residue, and stock-attribute valuation-misuse check: 0 bad target nodes
  - target-file soft warnings: 12 historical non-target warnings only
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count: 162924`
- Test gate after batch: `tests/test_apply_yaml_patch.py tests/test_prompt_gen_schema_block.py tests/test_prompt_gen_governance.py tests/test_schema_validator.py` passed, 86 tests
- Diff hygiene after batch: `git diff --check` passed
- Scope audit after batch: `fillable_total=110682`, `skipped_total=24290`, `cheap_extract=8184`
- Residual scope note: `FINANCIAL_HIGH_DIVIDEND` has only `601918.SH` still showing cheap_extract fillables.

## Completed batch 124

- Batch target: `FINANCIAL_HIGH_DIVIDEND`, A-share, `cheap_extract`
- Stocks completed: `601918.SH`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Parallel runner: `C1_INDUSTRY=FINANCIAL_HIGH_DIVIDEND`, `C1_PARALLEL=1`, via hardened `scripts/run_c1_fill.sh`
- Nodes handled: 6 cheap_extract targets
- Execution note:
  - The single child run exited 0 and the hardened status summary reported `processed=1`, `skipped=0`, `prompt_failed=0`, `failed=0`.
  - `601918.SH` changed exactly the 6 target dpids.
  - `601918.SH` kept `L3.channel.mix` as `Unknown` because local evidence disclosed customer, product, region, revenue, or business structure, but not a direct/distributor/ecommerce/other channel split.
  - Natural-language English residue check after run found 0 issues.
  - Stock-attribute PE/PB misuse check after run found 0 issues: no PE/PB percentile tag and no numeric excerpt under `L6.path.tag`.
  - Runner post-processing did not need to restore wrapped `scores.formula` (`formula_normalized=0`).
- Structural diff after run:
  - the file changed only `L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`
  - Non-`nodes` YAML payload is unchanged
- Post-run cheap_extract dry-run:
  - `601918.SH` now shows `Fillable: 0` / `没有可填字段`
- Scoped closed-loop verifier:
  - full verifier output: `/tmp/domestic_closed_loop_after_batch124.json`
  - full hard violations: 0
  - full soft warnings: 11797
  - target-node violations filtered to the 6 batch dpids: 0
  - target-node evidence_quality type, old-key, English-residue, and stock-attribute valuation-misuse check: 0 bad target nodes
  - target-file soft warnings: 3 historical non-target warnings only
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count: 162919`
- Test gate after batch: `tests/test_apply_yaml_patch.py tests/test_prompt_gen_schema_block.py tests/test_prompt_gen_governance.py tests/test_schema_validator.py` passed, 86 tests
- Diff hygiene after batch: `git diff --check` passed
- Scope audit after batch: `fillable_total=110676`, `skipped_total=24296`, `cheap_extract=8178`
- Residual scope note: `FINANCIAL_HIGH_DIVIDEND` has no cheap_extract residuals; next visible same-industry candidates include `HK_CN_INTERNET` (`000917.SZ`, `002261.SZ`, `002405.SZ`, `300229.SZ`).

## Completed batch 125

- Batch target: `HK_CN_INTERNET`, A-share, `cheap_extract`
- Stocks completed: `000917.SZ`, `002261.SZ`, `002405.SZ`, `300229.SZ`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Parallel runner: `C1_INDUSTRY=HK_CN_INTERNET`, `C1_PARALLEL=2`, via hardened `scripts/run_c1_fill.sh`
- Nodes handled: 24 cheap_extract targets
- Execution note:
  - All 4 child runs exited 0 and the hardened status summary reported `processed=4`, `skipped=0`, `prompt_failed=0`, `failed=0`.
  - `000917.SZ`, `002261.SZ`, `002405.SZ`, and `300229.SZ` each changed exactly the 6 target dpids.
  - All 4 kept `L3.channel.mix` as `Unknown` because local evidence disclosed customer, product, region, revenue, or business structure, but not a direct/distributor/ecommerce/other channel split.
  - Natural-language English residue check after run found 0 issues.
  - Stock-attribute PE/PB misuse check after run found 0 issues: no PE/PB percentile tag and no numeric excerpt under `L6.path.tag`.
  - Runner post-processing restored wrapped `scores.formula` in `000917.SZ`, `002261.SZ`, and `300229.SZ` (`formula_normalized=3`).
- Structural diff after run:
  - all 4 files changed only `L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`
  - Non-`nodes` YAML payload is unchanged for all 4 files
- Post-run cheap_extract dry-run:
  - all 4 stocks now show `Fillable: 0` / `没有可填字段`
- Scoped closed-loop verifier:
  - full verifier output: `/tmp/domestic_closed_loop_after_batch125.json`
  - full hard violations: 0
  - full soft warnings: 11797
  - target-node violations filtered to the 24 batch dpids: 0
  - target-node evidence_quality type, old-key, English-residue, and stock-attribute valuation-misuse check: 0 bad target nodes
  - target-file soft warnings: 12 historical non-target warnings only
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count: 162899`
- Test gate after batch: `tests/test_apply_yaml_patch.py tests/test_prompt_gen_schema_block.py tests/test_prompt_gen_governance.py tests/test_schema_validator.py` passed, 86 tests
- Diff hygiene after batch: `git diff --check` passed
- Scope audit after batch: `fillable_total=110652`, `skipped_total=24320`, `cheap_extract=8154`
- Residual scope note: `HK_CN_INTERNET` continues at `300377.SZ`, `300674.SZ`, `300682.SZ`, and `301248.SZ`.

## Completed batch 126

- Batch target: `HK_CN_INTERNET`, A-share, `cheap_extract`
- Stocks completed: `300377.SZ`, `300674.SZ`, `300682.SZ`, `301248.SZ`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Parallel runner: `C1_INDUSTRY=HK_CN_INTERNET`, `C1_PARALLEL=2`, via hardened `scripts/run_c1_fill.sh`
- Nodes handled: 24 cheap_extract targets
- Execution note:
  - All 4 child runs exited 0 and the hardened status summary reported `processed=4`, `skipped=0`, `prompt_failed=0`, `failed=0`.
  - `300377.SZ`, `300674.SZ`, `300682.SZ`, and `301248.SZ` each changed exactly the 6 target dpids.
  - `300682.SZ` filled `L3.channel.mix` as Known because local annual-report disclosure explicitly listed direct sales by sales mode; its channel `trend` was manually normalized from a Chinese free-text value to `direct_sales_dominant` for consistency with prior batches. The other 3 kept `L3.channel.mix` as `Unknown` because local evidence disclosed customer, product, region, revenue, or business structure, but not a direct/distributor/ecommerce/other channel split.
  - Natural-language English residue check after run found 0 issues.
  - Stock-attribute PE/PB misuse check after run found 0 issues: no PE/PB percentile tag and no numeric excerpt under `L6.path.tag`.
  - Runner post-processing restored wrapped `scores.formula` in `300377.SZ`, `300674.SZ`, and `301248.SZ` (`formula_normalized=3`).
- Structural diff after run:
  - all 4 files changed only `L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`
  - Non-`nodes` YAML payload is unchanged for all 4 files
- Post-run cheap_extract dry-run:
  - all 4 stocks now show `Fillable: 0` / `没有可填字段`
- Scoped closed-loop verifier:
  - full verifier output: `/tmp/domestic_closed_loop_after_batch126.json`
  - full hard violations: 0
  - full soft warnings: 11797
  - target-node violations filtered to the 24 batch dpids: 0
  - target-node evidence_quality type, old-key, English-residue, and stock-attribute valuation-misuse check: 0 bad target nodes
  - target-file soft warnings: 12 historical non-target warnings only
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count: 162878`
- Test gate after batch: `tests/test_apply_yaml_patch.py tests/test_prompt_gen_schema_block.py tests/test_prompt_gen_governance.py tests/test_schema_validator.py` passed, 86 tests
- Diff hygiene after batch: `git diff --check` passed
- Scope audit after batch: `fillable_total=110628`, `skipped_total=24344`, `cheap_extract=8130`
- Residual scope note: `HK_CN_INTERNET` continues at `301638.SZ`, `600131.SH`, `600271.SH`, and `600373.SH`.

## Completed batch 127

- Batch target: `HK_CN_INTERNET`, A-share, `cheap_extract`
- Stocks completed: `301638.SZ`, `600131.SH`, `600271.SH`, `600373.SH`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Parallel runner: `C1_INDUSTRY=HK_CN_INTERNET`, `C1_PARALLEL=2`, via hardened `scripts/run_c1_fill.sh`
- Nodes handled: 24 cheap_extract targets
- Execution note:
  - All 4 child runs exited 0 and the hardened status summary reported `processed=4`, `skipped=0`, `prompt_failed=0`, `failed=0`.
  - `301638.SZ`, `600131.SH`, `600271.SH`, and `600373.SH` each changed exactly the 6 target dpids.
  - `301638.SZ` filled `L3.channel.mix` as Known because local annual-report disclosure explicitly listed direct sales and distribution sales by sales mode; the other 3 kept `L3.channel.mix` as `Unknown` because local evidence disclosed customer, product, region, revenue, or business structure, but not a direct/distributor/ecommerce/other channel split.
  - Natural-language English residue check after run found 0 issues.
  - Stock-attribute PE/PB misuse check after run found 0 issues: no PE/PB percentile tag and no numeric excerpt under `L6.path.tag`.
  - Runner post-processing restored wrapped `scores.formula` in all 4 target overlays (`formula_normalized=4`).
- Structural diff after run:
  - all 4 files changed only `L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`
  - Non-`nodes` YAML payload is unchanged for all 4 files
- Post-run cheap_extract dry-run:
  - all 4 stocks now show `Fillable: 0` / `没有可填字段`
- Scoped closed-loop verifier:
  - full verifier output: `/tmp/domestic_closed_loop_after_batch127.json`
  - full hard violations: 0
  - full soft warnings: 11797
  - target-node violations filtered to the 24 batch dpids: 0
  - target-node evidence_quality type, old-key, English-residue, and stock-attribute valuation-misuse check: 0 bad target nodes
  - target-file soft warnings: 12 historical non-target warnings only
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count: 162857`
- Test gate after batch: `tests/test_apply_yaml_patch.py tests/test_prompt_gen_schema_block.py tests/test_prompt_gen_governance.py tests/test_schema_validator.py` passed, 86 tests
- Diff hygiene after batch: `git diff --check` passed
- Scope audit after batch: `fillable_total=110604`, `skipped_total=24368`, `cheap_extract=8106`
- Residual scope note: `HK_CN_INTERNET` continues at `600446.SH`, `600589.SH`, `600637.SH`, and `600666.SH`.

## Completed batch 128

- Batch target: `HK_CN_INTERNET`, A-share, `cheap_extract`
- Stocks completed: `600446.SH`, `600589.SH`, `600637.SH`, `600666.SH`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Parallel runner: `C1_INDUSTRY=HK_CN_INTERNET`, `C1_PARALLEL=2`, via hardened `scripts/run_c1_fill.sh`
- Nodes handled: 24 cheap_extract targets
- Execution note:
  - All 4 child runs exited 0 and the hardened status summary reported `processed=4`, `skipped=0`, `prompt_failed=0`, `failed=0`.
  - `600446.SH`, `600589.SH`, `600637.SH`, and `600666.SH` each changed exactly the 6 target dpids.
  - `600589.SH` filled `L3.channel.mix` as Known because local disclosure explicitly described direct sales; the other 3 kept `L3.channel.mix` as `Unknown` because local evidence disclosed customer, product, region, revenue, or business structure, but not a direct/distributor/ecommerce/other channel split.
  - Natural-language English residue check after run found 0 issues.
  - Stock-attribute PE/PB misuse check after run found 0 issues: no PE/PB percentile tag and no numeric excerpt under `L6.path.tag`.
  - Runner post-processing restored wrapped `scores.formula` in `600589.SH`, `600637.SH`, and `600666.SH` (`formula_normalized=3`).
- Structural diff after run:
  - all 4 files changed only `L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`
  - Non-`nodes` YAML payload is unchanged for all 4 files
- Post-run cheap_extract dry-run:
  - all 4 stocks now show `Fillable: 0` / `没有可填字段`
- Scoped closed-loop verifier:
  - full verifier output: `/tmp/domestic_closed_loop_after_batch128.json`
  - full hard violations: 0
  - full soft warnings: 11797
  - target-node violations filtered to the 24 batch dpids: 0
  - target-node evidence_quality type, old-key, English-residue, and stock-attribute valuation-misuse check: 0 bad target nodes
  - target-file soft warnings: 12 historical non-target warnings only
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count: 162836`
- Test gate after batch: `tests/test_apply_yaml_patch.py tests/test_prompt_gen_schema_block.py tests/test_prompt_gen_governance.py tests/test_schema_validator.py` passed, 86 tests
- Diff hygiene after batch: `git diff --check` passed
- Scope audit after batch: `fillable_total=110580`, `skipped_total=24392`, `cheap_extract=8082`
- Residual scope note: `HK_CN_INTERNET` continues at `600728.SH`, `600850.SH`, `600959.SH`, and `600977.SH`.

## Completed batch 129

- Batch target: `HK_CN_INTERNET`, A-share, `cheap_extract`
- Stocks completed: `600728.SH`, `600850.SH`, `600959.SH`, `600977.SH`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Parallel runner: `C1_INDUSTRY=HK_CN_INTERNET`, `C1_PARALLEL=2`, via hardened `scripts/run_c1_fill.sh`
- Nodes handled: 24 cheap_extract targets
- Execution note:
  - All 4 child runs exited 0 and the hardened status summary reported `processed=4`, `skipped=0`, `prompt_failed=0`, `failed=0`.
  - `600728.SH`, `600850.SH`, `600959.SH`, and `600977.SH` each changed exactly the 6 target dpids.
  - All 4 kept `L3.channel.mix` as `Unknown` because local evidence disclosed business structure, customer, product, platform, revenue, or regional context, but not a direct/distributor/ecommerce/other channel split.
  - Natural-language English residue check after run found 0 issues.
  - Stock-attribute PE/PB misuse check after run found 0 issues: no PE/PB percentile tag and no numeric excerpt under `L6.path.tag`.
  - Runner post-processing restored wrapped `scores.formula` in all 4 files (`formula_normalized=4`).
- Structural diff after run:
  - all 4 files changed only `L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`
  - Non-`nodes` YAML payload is unchanged for all 4 files
- Post-run cheap_extract dry-run:
  - all 4 stocks now show `Fillable: 0` / `没有可填字段`
- Scoped closed-loop verifier:
  - full verifier output: `/tmp/domestic_closed_loop_after_batch129.json`
  - full hard violations: 0
  - full soft warnings: 11797
  - target-node violations filtered to the 24 batch dpids: 0
  - target-node evidence_quality type, old-key, English-residue, and stock-attribute valuation-misuse check: 0 bad target nodes
  - target-file soft warnings: 12 historical non-target warnings only
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count: 162816`
- Test gate after batch: `tests/test_apply_yaml_patch.py tests/test_prompt_gen_schema_block.py tests/test_prompt_gen_governance.py tests/test_schema_validator.py` passed, 86 tests
- Diff hygiene after batch: `git diff --check` passed
- Scope audit after batch: `fillable_total=110556`, `skipped_total=24416`, `cheap_extract=8058`
- Residual scope note: `HK_CN_INTERNET` continues at `600986.SH`, `600996.SH`, `601019.SH`, and `601098.SH`.

## Completed batch 130

- Batch target: `HK_CN_INTERNET`, A-share, `cheap_extract`
- Stocks completed: `600986.SH`, `600996.SH`, `601019.SH`, `601098.SH`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Parallel runner: `C1_INDUSTRY=HK_CN_INTERNET`, `C1_PARALLEL=2`, via hardened `scripts/run_c1_fill.sh`
- Nodes handled: 24 cheap_extract targets
- Execution note:
  - All 4 child runs exited 0 and the hardened status summary reported `processed=4`, `skipped=0`, `prompt_failed=0`, `failed=0`.
  - `600986.SH`, `600996.SH`, `601019.SH`, and `601098.SH` each changed exactly the 6 target dpids.
  - All 4 kept `L3.channel.mix` as `Unknown` because local evidence disclosed business structure, customer concentration, revenue structure, or regional context, but not a direct/distributor/ecommerce/other channel split.
  - Natural-language English residue check after run found 0 issues.
  - Stock-attribute PE/PB misuse check after run found 0 issues: no PE/PB percentile tag and no numeric excerpt under `L6.path.tag`.
  - Runner post-processing did not need to normalize wrapped `scores.formula` (`formula_normalized=0`).
- Structural diff after run:
  - all 4 files changed only `L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`
  - Non-`nodes` YAML payload is unchanged for all 4 files
- Post-run cheap_extract dry-run:
  - all 4 stocks now show `Fillable: 0` / `没有可填字段`
- Scoped closed-loop verifier:
  - full verifier output: `/tmp/domestic_closed_loop_after_batch130.json`
  - full hard violations: 0
  - full soft warnings: 11797
  - target-node violations filtered to the 24 batch dpids: 0
  - target-node evidence_quality type, old-key, English-residue, and stock-attribute valuation-misuse check: 0 bad target nodes
  - target-file soft warnings: 12 historical non-target warnings only
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count: 162796`
- Test gate after batch: `tests/test_apply_yaml_patch.py tests/test_prompt_gen_schema_block.py tests/test_prompt_gen_governance.py tests/test_schema_validator.py` passed, 86 tests
- Diff hygiene after batch: `git diff --check` passed
- Scope audit after batch: `fillable_total=110532`, `skipped_total=24440`, `cheap_extract=8034`
- Residual scope note: `HK_CN_INTERNET` continues at `601801.SH`, `601811.SH`, `601900.SH`, and `601921.SH`.

## Completed batch 131

- Batch target: `HK_CN_INTERNET`, A-share, `cheap_extract`
- Stocks completed: `601801.SH`, `601811.SH`, `601900.SH`, `601921.SH`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Parallel runner: `C1_INDUSTRY=HK_CN_INTERNET`, `C1_PARALLEL=2`, via hardened `scripts/run_c1_fill.sh`
- Nodes handled: 24 cheap_extract targets
- Execution note:
  - All 4 child runs exited 0 and the hardened status summary reported `processed=4`, `skipped=0`, `prompt_failed=0`, `failed=0`.
  - `601801.SH`, `601811.SH`, `601900.SH`, and `601921.SH` each changed exactly the 6 target dpids.
  - All 4 kept `L3.channel.mix` as `Unknown` because local evidence disclosed product, business-line, region, customer, or revenue structure, but not a direct/distributor/ecommerce/other channel split. The prompt boundary correctly avoided inferring channel share from publishing/distribution business categories.
  - Natural-language English residue check after run found 0 issues.
  - Stock-attribute PE/PB misuse check after run found 0 issues: no PE/PB percentile tag and no numeric excerpt under `L6.path.tag`.
  - Runner post-processing restored wrapped `scores.formula` in all 4 files (`formula_normalized=4`).
- Structural diff after run:
  - all 4 files changed only `L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`
  - Non-`nodes` YAML payload is unchanged for all 4 files
- Post-run cheap_extract dry-run:
  - all 4 stocks now show `Fillable: 0` / `没有可填字段`
- Scoped closed-loop verifier:
  - full verifier output: `/tmp/domestic_closed_loop_after_batch131.json`
  - full hard violations: 0
  - full soft warnings: 11797
  - target-node violations filtered to the 24 batch dpids: 0
  - target-node evidence_quality type, old-key, English-residue, and stock-attribute valuation-misuse check: 0 bad target nodes
  - target-file soft warnings: 12 historical non-target warnings only
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count: 162776`
- Test gate after batch: `tests/test_apply_yaml_patch.py tests/test_prompt_gen_schema_block.py tests/test_prompt_gen_governance.py tests/test_schema_validator.py` passed, 86 tests
- Diff hygiene after batch: `git diff --check` passed
- Scope audit after batch: `fillable_total=110508`, `skipped_total=24464`, `cheap_extract=8010`
- Residual scope note: `HK_CN_INTERNET` continues at `601928.SH`, `603039.SH`, `603103.SH`, and `603171.SH`.

## Completed batch 132

- Batch target: `HK_CN_INTERNET`, A-share, `cheap_extract`
- Stocks completed: `601928.SH`, `603039.SH`, `603103.SH`, `603171.SH`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Parallel runner: `C1_INDUSTRY=HK_CN_INTERNET`, `C1_PARALLEL=2`, via hardened `scripts/run_c1_fill.sh`
- Nodes handled: 24 cheap_extract targets
- Execution note:
  - All 4 child runs exited 0 and the hardened status summary reported `processed=4`, `skipped=0`, `prompt_failed=0`, `failed=0`.
  - `601928.SH`, `603039.SH`, `603103.SH`, and `603171.SH` each changed exactly the 6 target dpids.
  - `603171.SH` filled `L3.channel.mix` as Known because local annual-report evidence directly disclosed the sales mode as direct sales and the amount equaled total main-business revenue. The other 3 kept `L3.channel.mix` as `Unknown` because local evidence disclosed business, customer, product, or revenue structure, but not a direct/distributor/ecommerce/other channel split.
  - Natural-language English residue check after run found 0 issues.
  - Stock-attribute PE/PB misuse check after run found 0 issues: no PE/PB percentile tag and no numeric excerpt under `L6.path.tag`.
  - Runner post-processing restored wrapped `scores.formula` in all 4 files (`formula_normalized=4`).
- Structural diff after run:
  - all 4 files changed only `L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`
  - Non-`nodes` YAML payload is unchanged for all 4 files
- Post-run cheap_extract dry-run:
  - all 4 stocks now show `Fillable: 0` / `没有可填字段`
- Scoped closed-loop verifier:
  - full verifier output: `/tmp/domestic_closed_loop_after_batch132.json`
  - full hard violations: 0
  - full soft warnings: 11797
  - target-node violations filtered to the 24 batch dpids: 0
  - target-node evidence_quality type, old-key, English-residue, and stock-attribute valuation-misuse check: 0 bad target nodes
  - target-file soft warnings: 12 historical non-target warnings only
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count: 162755`
- Test gate after batch: `tests/test_apply_yaml_patch.py tests/test_prompt_gen_schema_block.py tests/test_prompt_gen_governance.py tests/test_schema_validator.py` passed, 86 tests
- Diff hygiene after batch: `git diff --check` passed
- Scope audit after batch: `fillable_total=110484`, `skipped_total=24488`, `cheap_extract=7986`
- Residual scope note: `HK_CN_INTERNET` continues at `603533.SH`, `603613.SH`, `603927.SH`, and `688158.SH`.

## Completed batch 133

- Batch target: `HK_CN_INTERNET`, A-share, `cheap_extract`
- Stocks completed: `603533.SH`, `603613.SH`, `603927.SH`, `688158.SH`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Parallel runner: `C1_INDUSTRY=HK_CN_INTERNET`, `C1_PARALLEL=2`, via hardened `scripts/run_c1_fill.sh`
- Nodes handled: 24 cheap_extract targets
- Execution note:
  - All 4 child runs exited 0 and the hardened status summary reported `processed=4`, `skipped=0`, `prompt_failed=0`, `failed=0`.
  - `603533.SH`, `603613.SH`, `603927.SH`, and `688158.SH` each changed exactly the 6 target dpids.
  - All 4 kept `L3.channel.mix` as `Unknown` because local evidence disclosed business, customer, product, online/offline sales mode, or revenue structure, but not a direct/distributor/ecommerce/other channel split. `603613.SH` correctly did not treat online/offline revenue as ecommerce-channel percentage.
  - Natural-language English residue check after run found 0 issues.
  - Stock-attribute PE/PB misuse check after run found 0 issues: no PE/PB percentile tag and no numeric excerpt under `L6.path.tag`.
  - Runner post-processing restored wrapped `scores.formula` in all 4 files (`formula_normalized=4`).
- Structural diff after run:
  - all 4 files changed only `L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`
  - Non-`nodes` YAML payload is unchanged for all 4 files
- Post-run cheap_extract dry-run:
  - all 4 stocks now show `Fillable: 0` / `没有可填字段`
- Scoped closed-loop verifier:
  - full verifier output: `/tmp/domestic_closed_loop_after_batch133.json`
  - full hard violations: 0
  - full soft warnings: 11797
  - target-node violations filtered to the 24 batch dpids: 0
  - target-node evidence_quality type, old-key, English-residue, and stock-attribute valuation-misuse check: 0 bad target nodes
  - target-file soft warnings: 12 historical non-target warnings only
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count: 162735`
- Test gate after batch: `tests/test_apply_yaml_patch.py tests/test_prompt_gen_schema_block.py tests/test_prompt_gen_governance.py tests/test_schema_validator.py` passed, 86 tests
- Diff hygiene after batch: `git diff --check` passed
- Scope audit after batch: `fillable_total=110460`, `skipped_total=24512`, `cheap_extract=7962`
- Residual scope note: `HK_CN_INTERNET` continues at `688191.SH`, `688327.SH`, `688343.SH`, and `688507.SH`.

## Completed batch 134

- Batch target: `HK_CN_INTERNET`, A-share, `cheap_extract`
- Stocks completed: `688191.SH`, `688327.SH`, `688343.SH`, `688507.SH`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Parallel runner: `C1_INDUSTRY=HK_CN_INTERNET`, `C1_PARALLEL=2`, via hardened `scripts/run_c1_fill.sh`
- Nodes handled: 24 cheap_extract targets
- Execution note:
  - All 4 child runs exited 0 and the hardened status summary reported `processed=4`, `skipped=0`, `prompt_failed=0`, `failed=0`.
  - `688191.SH`, `688327.SH`, `688343.SH`, and `688507.SH` each changed exactly the 6 target dpids.
  - `688327.SH` filled `L3.channel.mix` as Known because local annual-report evidence directly disclosed sales-mode revenue split between direct sales and distributors. `688507.SH` filled `L3.channel.mix` as Known because local annual-report evidence directly disclosed all main-business revenue as direct sales. `688191.SH` and `688343.SH` kept `L3.channel.mix` as `Unknown` because customer concentration and revenue structure do not establish channel split.
  - Natural-language English residue check after run found 0 issues.
  - Stock-attribute PE/PB misuse check after run found 0 issues: no PE/PB percentile tag and no numeric excerpt under `L6.path.tag`.
  - Runner post-processing restored wrapped `scores.formula` in `688507.SH` (`formula_normalized=1`).
- Structural diff after run:
  - all 4 files changed only `L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`
  - Non-`nodes` YAML payload is unchanged for all 4 files
- Post-run cheap_extract dry-run:
  - all 4 stocks now show `Fillable: 0` / `没有可填字段`
- Scoped closed-loop verifier:
  - full verifier output: `/tmp/domestic_closed_loop_after_batch134.json`
  - full hard violations: 0
  - full soft warnings: 11797
  - target-node violations filtered to the 24 batch dpids: 0
  - target-node evidence_quality type, old-key, English-residue, and stock-attribute valuation-misuse check: 0 bad target nodes
  - target-file soft warnings: 12 historical non-target warnings only
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count: 162713`
- Test gate after batch: `tests/test_apply_yaml_patch.py tests/test_prompt_gen_schema_block.py tests/test_prompt_gen_governance.py tests/test_schema_validator.py` passed, 86 tests
- Diff hygiene after batch: `git diff --check` passed
- Scope audit after batch: `fillable_total=110436`, `skipped_total=24536`, `cheap_extract=7938`
- Residual scope note: `HK_CN_INTERNET` continues at `688561.SH`, `688568.SH`, `688692.SH`, and `920116.BJ`.

## Completed batch 135

- Batch target: `HK_CN_INTERNET`, A-share, `cheap_extract`
- Stocks completed: `688561.SH`, `688568.SH`, `688692.SH`, `920116.BJ`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Parallel runner: `C1_INDUSTRY=HK_CN_INTERNET`, `C1_PARALLEL=2`, via hardened `scripts/run_c1_fill.sh`
- Nodes handled: 24 cheap_extract targets
- Execution note:
  - All 4 child runs exited 0 and the hardened status summary reported `processed=4`, `skipped=0`, `prompt_failed=0`, `failed=0`.
  - `688561.SH`, `688568.SH`, `688692.SH`, and `920116.BJ` each changed exactly the 6 target dpids.
  - All 4 kept `L3.channel.mix` as `Unknown` because local evidence disclosed business line, region, customer, or revenue structure, but not a direct/distributor/ecommerce/other channel split.
  - Natural-language English residue check after run found 0 issues.
  - Stock-attribute PE/PB misuse check after run found 0 issues: no PE/PB percentile tag and no numeric excerpt under `L6.path.tag`.
  - Runner post-processing restored wrapped `scores.formula` in `688561.SH` and `688692.SH` (`formula_normalized=2`).
- Structural diff after run:
  - all 4 files changed only `L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`
  - Non-`nodes` YAML payload is unchanged for all 4 files
- Post-run cheap_extract dry-run:
  - all 4 stocks now show `Fillable: 0` / `没有可填字段`
- Scoped closed-loop verifier:
  - full verifier output: `/tmp/domestic_closed_loop_after_batch135.json`
  - full hard violations: 0
  - full soft warnings: 11797
  - target-node violations filtered to the 24 batch dpids: 0
  - target-node evidence_quality type, old-key, English-residue, and stock-attribute valuation-misuse check: 0 bad target nodes
  - target-file soft warnings: 9 historical non-target warnings only
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count: 162693`
- Test gate after batch: `tests/test_apply_yaml_patch.py tests/test_prompt_gen_schema_block.py tests/test_prompt_gen_governance.py tests/test_schema_validator.py` passed, 86 tests
- Diff hygiene after batch: `git diff --check` passed
- Scope audit after batch: `fillable_total=110412`, `skipped_total=24560`, `cheap_extract=7914`
- Residual scope note: `HK_CN_INTERNET` still has lower-residual A-share cheap_extract entries; continue at `000034.SZ`, `000156.SZ`, `000158.SZ`, and `000555.SZ` while skipping HK/US tickers for this A-share goal.

## Completed batch 136

- Batch target: `HK_CN_INTERNET`, A-share, `cheap_extract`
- Stocks completed: `000034.SZ`, `000156.SZ`, `000158.SZ`, `000555.SZ`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Parallel runner: `C1_INDUSTRY=HK_CN_INTERNET`, `C1_PARALLEL=2`, via hardened `scripts/run_c1_fill.sh`
- Nodes handled: 24 cheap_extract targets
- Execution note:
  - All 4 child runs exited 0 and the hardened status summary reported `processed=4`, `skipped=0`, `prompt_failed=0`, `failed=0`.
  - `000034.SZ`, `000156.SZ`, `000158.SZ`, and `000555.SZ` each changed exactly the 6 target dpids.
  - `000156.SZ` filled `L3.channel.mix` as Known because local annual-report evidence directly disclosed direct-sales and agent-sales mode percentages. `000158.SZ` filled `L3.channel.mix` as Known because local annual-report evidence directly disclosed all revenue as direct sales. `000034.SZ` and `000555.SZ` kept `L3.channel.mix` as `Unknown` because customer concentration and revenue structure do not establish channel split.
  - Natural-language English residue check after run found 0 issues.
  - Stock-attribute PE/PB misuse check after run found 0 issues: no PE/PB percentile tag and no numeric excerpt under `L6.path.tag`.
  - Manual consistency fix normalized `L3.channel.mix.value.trend` in `000156.SZ` and `000158.SZ` from Chinese free text to enum-like strings.
  - Runner post-processing restored wrapped `scores.formula` in `000156.SZ` and `000555.SZ` (`formula_normalized=2`).
- Structural diff after run:
  - all 4 files changed only `L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`
  - Non-`nodes` YAML payload is unchanged for all 4 files
- Post-run cheap_extract dry-run:
  - all 4 stocks now show `Fillable: 0` / `没有可填字段`
- Scoped closed-loop verifier:
  - full verifier output: `/tmp/domestic_closed_loop_after_batch136.json`
  - full hard violations: 0
  - full soft warnings: 11797
  - target-node violations filtered to the 24 batch dpids: 0
  - target-node evidence_quality type, old-key, English-residue, and stock-attribute valuation-misuse check: 0 bad target nodes
  - target-file soft warnings: 15 historical non-target warnings only
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count: 162671`
- Test gate after batch: `tests/test_apply_yaml_patch.py tests/test_prompt_gen_schema_block.py tests/test_prompt_gen_governance.py tests/test_schema_validator.py` passed, 86 tests
- Diff hygiene after batch: `git diff --check` passed
- Scope audit after batch: `fillable_total=110388`, `skipped_total=24584`, `cheap_extract=7890`
- Residual scope note: `HK_CN_INTERNET` continues at `000681.SZ`, `000719.SZ`, `000938.SZ`, and `001330.SZ`, skipping HK/US tickers for this A-share goal.

## Completed batch 137

- Batch target: `HK_CN_INTERNET`, A-share, `cheap_extract`
- Stocks completed: `000681.SZ`, `000719.SZ`, `000938.SZ`, `001330.SZ`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Parallel runner: `C1_INDUSTRY=HK_CN_INTERNET`, `C1_PARALLEL=2`, via hardened `scripts/run_c1_fill.sh`
- Nodes handled: 24 cheap_extract targets
- Execution note:
  - All 4 child runs exited 0 and the hardened status summary reported `processed=4`, `skipped=0`, `prompt_failed=0`, `failed=0`.
  - `000681.SZ`, `000719.SZ`, `000938.SZ`, and `001330.SZ` each changed exactly the 6 target dpids.
  - `000719.SZ`, `000938.SZ`, and `001330.SZ` filled `L3.channel.mix` as Known because local annual-report evidence directly disclosed sales-mode channel shares. `000681.SZ` kept `L3.channel.mix` as `Unknown` because the local sales-mode line disclosed only aggregate revenue and not a channel split.
  - Natural-language English residue check after run found 0 issues.
  - Stock-attribute PE/PB misuse check after run found 0 issues: no PE/PB percentile tag and no numeric excerpt under `L6.path.tag`.
  - Manual consistency fix normalized `L3.channel.mix.value.trend` in `000719.SZ` and `000938.SZ` from Chinese free text to enum-like strings.
  - Runner post-processing restored wrapped `scores.formula` in `000938.SZ` (`formula_normalized=1`).
- Structural diff after run:
  - all 4 files changed only `L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`
  - Non-`nodes` YAML payload is unchanged for all 4 files
- Post-run cheap_extract dry-run:
  - all 4 stocks now show `Fillable: 0` / `没有可填字段`
- Scoped closed-loop verifier:
  - full verifier output: `/tmp/domestic_closed_loop_after_batch137.json`
  - full hard violations: 0
  - full soft warnings: 11797
  - target-node violations filtered to the 24 batch dpids: 0
  - target-node evidence_quality type, old-key, English-residue, and stock-attribute valuation-misuse check: 0 bad target nodes
  - target-file soft warnings: 16 historical non-target warnings only
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count: 162648`
- Test gate after batch: `tests/test_apply_yaml_patch.py tests/test_prompt_gen_schema_block.py tests/test_prompt_gen_governance.py tests/test_schema_validator.py` passed, 86 tests
- Diff hygiene after batch: `git diff --check` passed
- Scope audit after batch: `fillable_total=110364`, `skipped_total=24608`, `cheap_extract=7866`
- Residual scope note: `HK_CN_INTERNET` continues at `002024.SZ`, `002027.SZ`, `002063.SZ`, and `002065.SZ`, skipping HK/US tickers for this A-share goal.

## Completed batch 138

- Batch target: `HK_CN_INTERNET`, A-share, `cheap_extract`
- Stocks completed: `002024.SZ`, `002027.SZ`, `002063.SZ`, `002065.SZ`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Parallel runner: `C1_INDUSTRY=HK_CN_INTERNET`, `C1_PARALLEL=2`, via hardened `scripts/run_c1_fill.sh`
- Nodes handled: 24 cheap_extract targets
- Execution note:
  - All 4 child runs exited 0 and the hardened status summary reported `processed=4`, `skipped=0`, `prompt_failed=0`, `failed=0`.
  - `002024.SZ`, `002027.SZ`, `002063.SZ`, and `002065.SZ` each changed exactly the 6 target dpids.
  - `002063.SZ` filled `L3.channel.mix` as Known because local annual-report evidence directly disclosed all sales as direct sales. The other 3 kept `L3.channel.mix` as `Unknown` because business, product, region, customer, and revenue structure do not establish channel split.
  - Natural-language English residue check after run found 0 issues.
  - Stock-attribute PE/PB misuse check after run found 0 issues: no PE/PB percentile tag and no numeric excerpt under `L6.path.tag`.
  - Manual consistency fix normalized `L3.channel.mix.value.trend` in `002063.SZ` from Chinese free text to an enum-like string.
  - Runner post-processing restored wrapped `scores.formula` in `002027.SZ`, `002063.SZ`, and `002065.SZ` (`formula_normalized=3`).
- Structural diff after run:
  - all 4 files changed only `L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`
  - Non-`nodes` YAML payload is unchanged for all 4 files
- Post-run cheap_extract dry-run:
  - all 4 stocks now show `Fillable: 0` / `没有可填字段`
- Scoped closed-loop verifier:
  - full verifier output: `/tmp/domestic_closed_loop_after_batch138.json`
  - full hard violations: 0
  - full soft warnings: 11797
  - target-node violations filtered to the 24 batch dpids: 0
  - target-node evidence_quality type, old-key, English-residue, and stock-attribute valuation-misuse check: 0 bad target nodes
  - target-file soft warnings: 15 historical non-target warnings only
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count: 162627`
- Test gate after batch: `tests/test_apply_yaml_patch.py tests/test_prompt_gen_schema_block.py tests/test_prompt_gen_governance.py tests/test_schema_validator.py` passed, 86 tests
- Diff hygiene after batch: `git diff --check` passed
- Scope audit after batch: `fillable_total=110340`, `skipped_total=24632`, `cheap_extract=7842`
- Residual scope note: `HK_CN_INTERNET` continues at `002153.SZ`, `002174.SZ`, `002181.SZ`, and `002195.SZ`, skipping HK/US tickers for this A-share goal.

## Completed batch 139

- Batch target: `HK_CN_INTERNET`, A-share, `cheap_extract`
- Stocks completed: `002153.SZ`, `002174.SZ`, `002181.SZ`, `002195.SZ`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Parallel runner: `C1_INDUSTRY=HK_CN_INTERNET`, `C1_PARALLEL=2`, via hardened `scripts/run_c1_fill.sh`
- Nodes handled: 24 cheap_extract targets
- Execution note:
  - All 4 child runs exited 0 and the hardened status summary reported `processed=4`, `skipped=0`, `prompt_failed=0`, `failed=0`.
  - `002153.SZ`, `002174.SZ`, `002181.SZ`, and `002195.SZ` each changed exactly the 6 target dpids.
  - `002153.SZ` and `002181.SZ` filled `L3.channel.mix` as Known because local annual-report evidence directly disclosed sales-mode channel shares. `002174.SZ` and `002195.SZ` kept `L3.channel.mix` as `Unknown` because business, customer, product, region, and revenue structure do not establish channel split.
  - Natural-language English residue check after run found 0 issues.
  - Stock-attribute PE/PB misuse check after run found 0 issues: no PE/PB percentile tag and no numeric excerpt under `L6.path.tag`.
  - Runner post-processing restored wrapped `scores.formula` in all 4 files (`formula_normalized=4`).
- Structural diff after run:
  - all 4 files changed only `L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`
  - Non-`nodes` YAML payload is unchanged for all 4 files
- Post-run cheap_extract dry-run:
  - all 4 stocks now show `Fillable: 0` / `没有可填字段`
- Scoped closed-loop verifier:
  - full verifier output: `/tmp/domestic_closed_loop_after_batch139.json`
  - full hard violations: 0
  - full soft warnings: 11797
  - target-node violations filtered to the 24 batch dpids: 0
  - target-node evidence_quality type, old-key, English-residue, and stock-attribute valuation-misuse check: 0 bad target nodes
  - target-file soft warnings: 16 historical non-target warnings only
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count: 162605`
- Test gate after batch: `tests/test_apply_yaml_patch.py tests/test_prompt_gen_schema_block.py tests/test_prompt_gen_governance.py tests/test_schema_validator.py` passed, 86 tests
- Diff hygiene after batch: `git diff --check` passed
- Scope audit after batch: `fillable_total=110316`, `skipped_total=24656`, `cheap_extract=7818`
- Residual scope note: `HK_CN_INTERNET` continues at `002230.SZ`, `002292.SZ`, `002315.SZ`, and `002354.SZ`, skipping HK/US tickers for this A-share goal.

## Completed batch 140

- Batch target: `HK_CN_INTERNET`, A-share, `cheap_extract`
- Stocks completed: `002230.SZ`, `002292.SZ`, `002315.SZ`, `002354.SZ`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Parallel runner: `C1_INDUSTRY=HK_CN_INTERNET`, `C1_PARALLEL=2`, via hardened `scripts/run_c1_fill.sh`
- Nodes handled: 24 cheap_extract targets
- Execution note:
  - All 4 child runs exited 0 and the hardened status summary reported `processed=4`, `skipped=0`, `prompt_failed=0`, `failed=0`.
  - `002230.SZ`, `002292.SZ`, `002315.SZ`, and `002354.SZ` each changed exactly the 6 target dpids.
  - `002315.SZ` filled `L3.channel.mix` as Known because local annual-report evidence directly disclosed direct-sales and distribution channel shares. The other 3 kept `L3.channel.mix` as `Unknown` because business, customer, product, region, B/G project, and revenue structure do not establish channel split.
  - Natural-language English residue check after run found 0 issues.
  - Stock-attribute PE/PB misuse check after run found 0 issues: no PE/PB percentile tag and no numeric excerpt under `L6.path.tag`.
  - Channel trend hardening worked in this batch: 0 Chinese free-text `L3.channel.mix.value.trend` values after run.
  - Runner post-processing restored wrapped `scores.formula` in `002354.SZ` (`formula_normalized=1`).
- Structural diff after run:
  - all 4 files changed only `L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`
  - Non-`nodes` YAML payload is unchanged for all 4 files
- Post-run cheap_extract dry-run:
  - all 4 stocks now show `Fillable: 0` / `没有可填字段`
- Scoped closed-loop verifier:
  - full verifier output: `/tmp/domestic_closed_loop_after_batch140.json`
  - full hard violations: 0
  - full soft warnings: 11786
  - target-node violations filtered to the 24 batch dpids: 0
  - target-node evidence_quality type, old-key, English-residue, stock-attribute valuation-misuse, and channel-trend Chinese free-text check: 0 bad target nodes
  - target-file soft warnings: 29 historical non-target warnings only
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count: 162590`
- Test gate after batch: `tests/test_apply_yaml_patch.py tests/test_prompt_gen_schema_block.py tests/test_prompt_gen_governance.py tests/test_schema_validator.py` passed, 86 tests
- Diff hygiene after batch: `git diff --check` passed
- Scope audit after batch: `fillable_total=110292`, `skipped_total=24680`, `cheap_extract=7794`
- Residual scope note: `HK_CN_INTERNET` continues at `002373.SZ`, `002400.SZ`, `002410.SZ`, and `002421.SZ`, skipping HK/US tickers for this A-share goal.

## Completed batch 141

- Batch target: `HK_CN_INTERNET`, A-share, `cheap_extract`
- Stocks completed: `002373.SZ`, `002400.SZ`, `002410.SZ`, `002421.SZ`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Parallel runner: `C1_INDUSTRY=HK_CN_INTERNET`, `C1_PARALLEL=2`, via hardened `scripts/run_c1_fill.sh`
- Nodes handled: 24 cheap_extract targets
- Execution note:
  - All 4 child runs exited 0 and the hardened status summary reported `processed=4`, `skipped=0`, `prompt_failed=0`, `failed=0`.
  - `002373.SZ`, `002400.SZ`, `002410.SZ`, and `002421.SZ` each changed exactly the 6 target dpids.
  - All 4 kept `L3.channel.mix` as `Unknown` because local evidence disclosed business, customer, product, region, quarterly revenue, or revenue structure, but not a direct/distributor/ecommerce/other channel split.
  - Natural-language English residue check after run found 0 issues.
  - Stock-attribute PE/PB misuse check after run found 0 issues: no PE/PB percentile tag and no numeric excerpt under `L6.path.tag`.
  - Channel trend hardening held: 0 Chinese free-text `L3.channel.mix.value.trend` values after run.
  - Runner post-processing restored wrapped `scores.formula` in `002373.SZ`, `002410.SZ`, and `002421.SZ` (`formula_normalized=3`).
- Structural diff after run:
  - all 4 files changed only `L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`
  - Non-`nodes` YAML payload is unchanged for all 4 files
- Post-run cheap_extract dry-run:
  - all 4 stocks now show `Fillable: 0` / `没有可填字段`
- Scoped closed-loop verifier:
  - full verifier output: `/tmp/domestic_closed_loop_after_batch141.json`
  - full hard violations: 0
  - full soft warnings: 11786
  - target-node violations filtered to the 24 batch dpids: 0
  - target-node evidence_quality type, old-key, English-residue, stock-attribute valuation-misuse, and channel-trend Chinese free-text check: 0 bad target nodes
  - target-file soft warnings: 16 historical non-target warnings only
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count: 162570`
- Test gate after batch: `tests/test_apply_yaml_patch.py tests/test_prompt_gen_schema_block.py tests/test_prompt_gen_governance.py tests/test_schema_validator.py` passed, 86 tests
- Diff hygiene after batch: `git diff --check` passed
- Scope audit after batch: `fillable_total=110268`, `skipped_total=24704`, `cheap_extract=7770`
- Residual scope note: `HK_CN_INTERNET` continues at `002439.SZ`, `002517.SZ`, `002555.SZ`, and `002558.SZ`, skipping HK/US tickers for this A-share goal.

## Completed batch 142

- Batch target: `HK_CN_INTERNET`, A-share, `cheap_extract`
- Stocks completed: `002439.SZ`, `002517.SZ`, `002555.SZ`, `002558.SZ`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Parallel runner: `C1_INDUSTRY=HK_CN_INTERNET`, `C1_PARALLEL=2`, via hardened `scripts/run_c1_fill.sh`
- Nodes handled: 24 cheap_extract targets
- Execution note:
  - All 4 child runs exited 0 and the hardened status summary reported `processed=4`, `skipped=0`, `prompt_failed=0`, `failed=0`.
  - `002439.SZ`, `002517.SZ`, `002555.SZ`, and `002558.SZ` each changed exactly the 6 target dpids.
  - `002439.SZ` filled `L3.channel.mix` as Known because local annual-report evidence directly disclosed direct-sales and distribution channel shares. `002517.SZ`, `002555.SZ`, and `002558.SZ` kept `L3.channel.mix` as `Unknown` because self-operated/joint-operation/authorized-operation modes and game publishing/operation business lines do not establish direct/distributor/ecommerce/other channel split.
  - Natural-language English residue check after run found 0 issues.
  - Stock-attribute PE/PB misuse check after run found 0 issues: no PE/PB percentile tag and no numeric excerpt under `L6.path.tag`.
  - Channel trend hardening held: 0 Chinese free-text `L3.channel.mix.value.trend` values after run.
  - Runner post-processing restored wrapped `scores.formula` in `002517.SZ` and `002558.SZ` (`formula_normalized=2`).
- Structural diff after run:
  - all 4 files changed only `L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`
  - Non-`nodes` YAML payload is unchanged for all 4 files
- Post-run cheap_extract dry-run:
  - all 4 stocks now show `Fillable: 0` / `没有可填字段`
- Scoped closed-loop verifier:
  - full verifier output: `/tmp/domestic_closed_loop_after_batch142.json`
  - full hard violations: 0
  - full soft warnings: 11777
  - target-node violations filtered to the 24 batch dpids: 0
  - target-node evidence_quality type, old-key, English-residue, stock-attribute valuation-misuse, and channel-trend Chinese free-text check: 0 bad target nodes
  - target-file soft warnings: 31 historical non-target warnings only
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count: 162555`
- Test gate after batch: `tests/test_apply_yaml_patch.py tests/test_prompt_gen_schema_block.py tests/test_prompt_gen_governance.py tests/test_schema_validator.py` passed, 86 tests
- Diff hygiene after batch: `git diff --check` passed
- Scope audit after batch: `fillable_total=110244`, `skipped_total=24728`, `cheap_extract=7746`
- Residual scope note: `HK_CN_INTERNET` continues at `002602.SZ`, `002624.SZ`, `002739.SZ`, and `002987.SZ`, skipping HK/US tickers for this A-share goal.

## Completed batch 143

- Batch target: `HK_CN_INTERNET`, A-share, `cheap_extract`
- Stocks completed: `002602.SZ`, `002624.SZ`, `002739.SZ`, `002987.SZ`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Parallel runner: `C1_INDUSTRY=HK_CN_INTERNET`, `C1_PARALLEL=2`, via hardened `scripts/run_c1_fill.sh`
- Nodes handled: 24 cheap_extract targets
- Execution note:
  - All 4 child runs exited 0 and the hardened status summary reported `processed=4`, `skipped=0`, `prompt_failed=0`, `failed=0`.
  - `002602.SZ`, `002624.SZ`, `002739.SZ`, and `002987.SZ` each changed exactly the 6 target dpids.
  - `002987.SZ` filled `L3.channel.mix` as Known because local annual-report evidence directly disclosed the sales mode as self-operated/direct. `002602.SZ`, `002624.SZ`, and `002739.SZ` kept `L3.channel.mix` as `Unknown` because business lines, platform listings, customer/product/region structure, and revenue structure do not establish direct/distributor/ecommerce/other channel split.
  - Natural-language English residue check after run found 0 issues.
  - Stock-attribute PE/PB misuse check after run found 0 issues: no PE/PB percentile tag and no numeric excerpt under `L6.path.tag`.
  - Channel trend hardening held: 0 Chinese free-text `L3.channel.mix.value.trend` values after run.
  - Runner post-processing restored wrapped `scores.formula` in `002987.SZ` (`formula_normalized=1`).
- Structural diff after run:
  - all 4 files changed only `L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`
  - Non-`nodes` YAML payload is unchanged for all 4 files
- Post-run cheap_extract dry-run:
  - all 4 stocks now show `nothing to fill (skip)` / `prompt_ready=0`
- Scoped closed-loop verifier:
  - full verifier output: `/tmp/domestic_closed_loop_after_batch143.json`
  - full hard violations: 0
  - full soft warnings: 11751
  - target-node violations filtered to the 24 batch dpids: 0
  - target-node evidence_quality type, old-key, English-residue, stock-attribute valuation-misuse, and channel-trend Chinese free-text check: 0 bad target nodes
  - target-file soft warnings: 44 historical non-target warnings only
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count: 162545`
- Test gate after batch: `tests/test_apply_yaml_patch.py tests/test_prompt_gen_schema_block.py tests/test_prompt_gen_governance.py tests/test_schema_validator.py` passed, 86 tests
- Diff hygiene after batch: `git diff --check` passed before the audit append; will be rerun after this audit update
- Scope audit after batch: `fillable_total=110220`, `skipped_total=24752`, `cheap_extract=7722`
- Pipeline hardening during batch:
  - `scripts/run_c1_fill.sh` now supports `--list-only` / `--dry-run`, generating prompts and reporting `prompt_ready` / `skipped` / `prompt_failed` without invoking the LLM runner or writing overlays.
  - The script no longer requires the runner to be executable in list-only mode, making preflight safe even when only prompt generation is needed.
  - Verified with `scripts/run_c1_fill.sh -h`, pre-run list-only for batch 143, post-run list-only for batch 143, and list-only candidate check for the next HK_CN_INTERNET batch.
- Residual scope note: `HK_CN_INTERNET` continues at `300002.SZ`, `300017.SZ`, `300031.SZ`, and `300033.SZ`, skipping HK/US tickers for this A-share goal.

## Completed batch 144

- Batch target: `HK_CN_INTERNET`, A-share, `cheap_extract`
- Stocks completed: `300002.SZ`, `300017.SZ`, `300031.SZ`, `300033.SZ`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Parallel runner: `C1_INDUSTRY=HK_CN_INTERNET`, `C1_PARALLEL=2`, via hardened `scripts/run_c1_fill.sh`
- Nodes handled: 24 cheap_extract targets
- Execution note:
  - All 4 child runs exited 0 and the hardened status summary reported `processed=4`, `skipped=0`, `prompt_failed=0`, `failed=0`.
  - `300002.SZ`, `300017.SZ`, `300031.SZ`, and `300033.SZ` each changed exactly the 6 target dpids.
  - `300002.SZ` filled `L3.channel.mix` as Known because the annual report directly disclosed a "sales mode" table with direct sales, distributor sales, self-operated, and joint-operated mode shares; self-operated and joint-operated shares were mapped to schema `others_pct`.
  - `300031.SZ` filled `L3.channel.mix` as Known because the annual report directly disclosed a "sales mode" table with agency-operation and direct-operation shares; agency-operation share was mapped to schema `others_pct`.
  - `300017.SZ` and `300033.SZ` kept `L3.channel.mix` as `Unknown` because business-line, platform, customer, product, region, and revenue-structure evidence does not establish direct/distributor/ecommerce/other channel split.
  - Natural-language English residue check after run found 0 issues.
  - Stock-attribute PE/PB misuse check after run found 0 issues: no PE/PB percentile tag and no numeric excerpt under `L6.path.tag`.
  - Channel trend hardening held: 0 Chinese free-text `L3.channel.mix.value.trend` values after run.
  - Runner post-processing found no wrapped `scores.formula` issue in this batch (`formula_normalized=0`).
- Structural diff after run:
  - all 4 files changed only `L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`
  - Non-`nodes` YAML payload is unchanged for all 4 files
- Post-run cheap_extract dry-run:
  - all 4 stocks now show `nothing to fill (skip)` / `prompt_ready=0`
- Scoped closed-loop verifier:
  - full verifier output: `/tmp/domestic_closed_loop_after_batch144.json`
  - full hard violations: 0
  - full soft warnings: 11739
  - target-node violations filtered to the 24 batch dpids: 0
  - target-node evidence_quality type, old-key, English-residue, stock-attribute valuation-misuse, and channel-trend Chinese free-text check: 0 bad target nodes
  - target-file soft warnings: 44 historical non-target warnings only
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count: 162529`
- Test gate after batch: `tests/test_apply_yaml_patch.py tests/test_prompt_gen_schema_block.py tests/test_prompt_gen_governance.py tests/test_schema_validator.py` passed, 86 tests
- Scope audit after batch: `fillable_total=110196`, `skipped_total=24776`, `cheap_extract=7698`
- Residual scope note: `HK_CN_INTERNET` continues at `300058.SZ`, `300059.SZ`, `300085.SZ`, and `300133.SZ`, skipping HK/US tickers for this A-share goal.

## Completed batch 145

- Batch target: `HK_CN_INTERNET`, A-share, `cheap_extract`
- Stocks completed: `300058.SZ`, `300059.SZ`, `300085.SZ`, `300133.SZ`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Parallel runner: `C1_INDUSTRY=HK_CN_INTERNET`, `C1_PARALLEL=2`, via hardened `scripts/run_c1_fill.sh`
- Nodes handled: 24 cheap_extract targets
- Execution note:
  - All 4 child runs exited 0 and the hardened status summary reported `processed=4`, `skipped=0`, `prompt_failed=0`, `failed=0`.
  - `300058.SZ`, `300059.SZ`, `300085.SZ`, and `300133.SZ` each changed exactly the 6 target dpids.
  - All four stocks kept `L3.channel.mix` as `Unknown` because local evidence disclosed business lines, platform/service types, customer concentration, supplier structure, product/region/revenue composition, or key works revenue, but did not directly disclose direct/distributor/ecommerce/other channel shares.
  - Natural-language English residue check after run found 0 issues.
  - Stock-attribute PE/PB misuse check after run found 0 issues: no PE/PB percentile tag and no numeric excerpt under `L6.path.tag`.
  - Channel trend hardening held: 0 Chinese free-text `L3.channel.mix.value.trend` values after run.
  - Runner post-processing restored wrapped `scores.formula` in `300058.SZ` and `300085.SZ` (`formula_normalized=2`).
- Structural diff after run:
  - all 4 files changed only `L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`
  - Non-`nodes` YAML payload is unchanged for all 4 files
- Post-run cheap_extract dry-run:
  - all 4 stocks now show `nothing to fill (skip)` / `prompt_ready=0`
- Scoped closed-loop verifier:
  - full verifier output: `/tmp/domestic_closed_loop_after_batch145.json`
  - full hard violations: 0
  - full soft warnings: 11728
  - target-node violations filtered to the 24 batch dpids: 0
  - target-node evidence_quality type, old-key, English-residue, stock-attribute valuation-misuse, and channel-trend Chinese free-text check: 0 bad target nodes
  - target-file soft warnings: 34 historical non-target warnings only
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count: 162515`
- Test gate after batch: `tests/test_apply_yaml_patch.py tests/test_prompt_gen_schema_block.py tests/test_prompt_gen_governance.py tests/test_schema_validator.py` passed, 86 tests
- Scope audit after batch: `fillable_total=110172`, `skipped_total=24800`, `cheap_extract=7674`
- Residual scope note: `HK_CN_INTERNET` continues at `300166.SZ`, `300170.SZ`, `300182.SZ`, and `300209.SZ`, skipping HK/US tickers for this A-share goal.

## Completed batch 146

- Batch target: `HK_CN_INTERNET`, A-share, `cheap_extract`
- Stocks completed: `300166.SZ`, `300170.SZ`, `300182.SZ`, `300209.SZ`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Parallel runner: `C1_INDUSTRY=HK_CN_INTERNET`, `C1_PARALLEL=2`, via hardened `scripts/run_c1_fill.sh`
- Nodes handled: 24 cheap_extract targets
- Execution note:
  - All 4 child runs exited 0 and the hardened status summary reported `processed=4`, `skipped=0`, `prompt_failed=0`, `failed=0`.
  - `300166.SZ`, `300170.SZ`, `300182.SZ`, and `300209.SZ` each changed exactly the 6 target dpids.
  - `300166.SZ` and `300170.SZ` filled `L3.channel.mix` as Known because annual-report evidence directly disclosed direct-sales shares of 100%.
  - `300182.SZ` kept `L3.channel.mix` as `Unknown` because customer concentration, business-line revenue, and region structure did not directly disclose direct/distributor/ecommerce/other channel shares.
  - `300209.SZ` was manually corrected back to `Unknown/no_local_evidence`: the LLM initially mapped online/offline disclosure to `ecommerce_pct/others_pct`, but online/offline is not a direct/distributor/ecommerce/other channel split under this schema.
  - Natural-language English residue check after run found 0 issues.
  - Stock-attribute PE/PB misuse check after run found 0 issues: no PE/PB percentile tag and no numeric excerpt under `L6.path.tag`.
  - Channel trend hardening held: 0 Chinese free-text `L3.channel.mix.value.trend` values after run.
  - Runner post-processing restored wrapped `scores.formula` in `300170.SZ` and `300182.SZ` (`formula_normalized=2`).
  - `300166.SZ:L1.model.tag` evidence excerpt was shortened to an exact local source substring after the scoped verifier caught one target-node excerpt warning.
- Pipeline hardening during batch:
  - `scripts/codex_prompt_gen.py` now explicitly says online/offline, domestic/overseas, and product/service type structures cannot be mapped to `ecommerce/others`; absent direct channel evidence must remain `Unknown`.
  - The same rule was added to the prompt self-check boundary.
  - `tests/test_prompt_gen_governance.py` now asserts this online/offline channel rule appears in the schema block.
- Structural diff after run:
  - all 4 files changed only `L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`
  - Non-`nodes` YAML payload is unchanged for all 4 files
- Post-run cheap_extract dry-run:
  - all 4 stocks now show `nothing to fill (skip)` / `prompt_ready=0`
- Scoped closed-loop verifier:
  - full verifier output: `/tmp/domestic_closed_loop_after_batch146.json`
  - full hard violations: 0
  - full soft warnings: 11728
  - target-node violations filtered to the 24 batch dpids: 0 after the `300166.SZ:L1.model.tag` excerpt correction
  - target-node evidence_quality type, old-key, English-residue, stock-attribute valuation-misuse, and channel-trend Chinese free-text check: 0 bad target nodes
  - target-file soft warnings: 16 historical non-target warnings only
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count: 162493`
- Test gate after batch: `tests/test_apply_yaml_patch.py tests/test_prompt_gen_schema_block.py tests/test_prompt_gen_governance.py tests/test_schema_validator.py` passed, 86 tests
- Scope audit after batch: `fillable_total=110148`, `skipped_total=24824`, `cheap_extract=7650`
- Residual scope note: `HK_CN_INTERNET` skips already-complete `300229.SZ` and continues at `300251.SZ`, `300253.SZ`, `300315.SZ`, and `300339.SZ`, skipping HK/US tickers for this A-share goal.

## Completed batch 147

- Batch target: `HK_CN_INTERNET`, A-share, `cheap_extract`
- Stocks completed: `300251.SZ`, `300253.SZ`, `300315.SZ`, `300339.SZ`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Parallel runner: `C1_INDUSTRY=HK_CN_INTERNET`, `C1_PARALLEL=2`, via hardened `scripts/run_c1_fill.sh`
- Nodes handled: 24 cheap_extract targets
- Execution note:
  - All 4 child runs exited 0 and the hardened status summary reported `processed=4`, `skipped=0`, `prompt_failed=0`, `failed=0`.
  - `300251.SZ`, `300253.SZ`, `300315.SZ`, and `300339.SZ` each changed exactly the 6 target dpids.
  - `300251.SZ` filled `L3.channel.mix` as Known because annual-report evidence directly disclosed direct-sales share of 100% in both 2025 and 2024.
  - `300339.SZ` filled `L3.channel.mix` as Known because annual-report evidence directly disclosed direct-sales share of 100%.
  - `300253.SZ` kept `L3.channel.mix` as `Unknown` because customer, product, region, and quarterly revenue structures did not directly disclose direct/distributor/ecommerce/other channel shares.
  - `300315.SZ` kept `L3.channel.mix` as `Unknown`; its local source mentioned network sales / other sales modes, but the hardened online/offline rule prevented mapping that to `ecommerce/others` without direct channel evidence.
  - Natural-language English residue check after run found 0 issues.
  - Stock-attribute PE/PB misuse check after run found 0 issues: no PE/PB percentile tag and no numeric excerpt under `L6.path.tag`.
  - Channel trend hardening held: 0 Chinese free-text `L3.channel.mix.value.trend` values after run.
  - Runner post-processing restored wrapped `scores.formula` in `300251.SZ`, `300253.SZ`, and `300315.SZ` (`formula_normalized=3`).
  - Scoped verifier initially found 4 target-node excerpt warnings; these were fixed by replacing two `L6.path.tag` excerpts with exact source substrings and removing/replacing non-source business-scope snippets in `300339.SZ` target evidence.
- Structural diff after run:
  - all 4 files changed only `L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`
  - Non-`nodes` YAML payload is unchanged for all 4 files
- Post-run cheap_extract dry-run:
  - all 4 stocks now show `nothing to fill (skip)` / `prompt_ready=0`
- Scoped closed-loop verifier:
  - full verifier output: `/tmp/domestic_closed_loop_after_batch147.json`
  - full hard violations: 0
  - full soft warnings: 11728
  - target-node violations filtered to the 24 batch dpids: 0 after excerpt corrections
  - target-node evidence_quality type, old-key, English-residue, stock-attribute valuation-misuse, and channel-trend Chinese free-text check: 0 bad target nodes
  - target-file soft warnings: 16 historical non-target warnings only
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count: 162471`
- Test gate after batch: `tests/test_apply_yaml_patch.py tests/test_prompt_gen_schema_block.py tests/test_prompt_gen_governance.py tests/test_schema_validator.py` passed, 86 tests
- Scope audit after batch: `fillable_total=110124`, `skipped_total=24848`, `cheap_extract=7626`
- Residual scope note: `HK_CN_INTERNET` skips already-complete `300377.SZ` and continues at `300364.SZ`, `300413.SZ`, `300418.SZ`, and `300454.SZ`, skipping HK/US tickers for this A-share goal.

## Completed batch 148

- Batch target: `HK_CN_INTERNET`, A-share, `cheap_extract`
- Stocks completed: `300364.SZ`, `300413.SZ`, `300418.SZ`, `300454.SZ`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Parallel runner: `C1_INDUSTRY=HK_CN_INTERNET`, `C1_PARALLEL=2`, via hardened `scripts/run_c1_fill.sh`
- Nodes handled: 24 cheap_extract targets
- Execution note:
  - All 4 child runs exited 0 and the hardened status summary reported `processed=4`, `skipped=0`, `prompt_failed=0`, `failed=0`.
  - `300364.SZ`, `300413.SZ`, `300418.SZ`, and `300454.SZ` each changed exactly the 6 target dpids.
  - `300454.SZ` filled `L3.channel.mix` as Known because annual-report evidence directly disclosed sales-mode shares for channel and direct sales.
  - `300364.SZ`, `300413.SZ`, and `300418.SZ` kept `L3.channel.mix` as `Unknown` because local evidence covered customer/business/revenue, business-line, program/R&D, or business-scope information but did not directly disclose direct/distributor/ecommerce/other channel shares.
  - Natural-language English residue check after run found 0 issues.
  - Stock-attribute PE/PB misuse check after run found 0 issues: no PE/PB percentile tag and no numeric excerpt under `L6.path.tag`.
  - Channel trend hardening held: 0 Chinese free-text `L3.channel.mix.value.trend` values after run.
  - Runner post-processing restored wrapped `scores.formula` in `300364.SZ`, `300413.SZ`, and `300454.SZ` (`formula_normalized=3`).
- Structural diff after run:
  - all 4 files changed only `L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`
  - Non-`nodes` YAML payload is unchanged for all 4 files
- Post-run cheap_extract dry-run:
  - all 4 stocks now show `nothing to fill (skip)` / `prompt_ready=0`
- Scoped closed-loop verifier:
  - full verifier output: `/tmp/domestic_closed_loop_after_batch148.json`
  - full hard violations: 0
  - full soft warnings: 11699
  - target-node violations filtered to the 24 batch dpids: 0
  - target-node evidence_quality type, old-key, English-residue, stock-attribute valuation-misuse, and channel-trend Chinese free-text check: 0 bad target nodes
  - target-file soft warnings: 64 historical non-target warnings only
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count: 162462`
- Test gate after batch: `tests/test_apply_yaml_patch.py tests/test_prompt_gen_schema_block.py tests/test_prompt_gen_governance.py tests/test_schema_validator.py` passed, 86 tests
- Scope audit after batch: `fillable_total=110100`, `skipped_total=24872`, `cheap_extract=7602`
- Residual scope note: `HK_CN_INTERNET` continues at `300459.SZ`, `300468.SZ`, `300469.SZ`, and `300496.SZ`, skipping HK/US tickers for this A-share goal.

## Completed batch 149

- Batch target: `HK_CN_INTERNET`, A-share, `cheap_extract`
- Stocks completed: `300459.SZ`, `300468.SZ`, `300469.SZ`, `300496.SZ`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Parallel runner: `C1_INDUSTRY=HK_CN_INTERNET`, `C1_PARALLEL=2`, via hardened `scripts/run_c1_fill.sh`
- Nodes handled: 24 cheap_extract targets
- Execution note:
  - All 4 child runs exited 0 and the hardened status summary reported `processed=4`, `skipped=0`, `prompt_failed=0`, `failed=0`.
  - `300459.SZ`, `300468.SZ`, `300469.SZ`, and `300496.SZ` each changed exactly the 6 target dpids.
  - `300468.SZ` and `300496.SZ` filled `L3.channel.mix` as Known because annual-report evidence directly disclosed direct-sales share of 100%.
  - `300459.SZ` kept `L3.channel.mix` as `Unknown`; its local evidence mentioned online mobile applications and offline IP derivatives/new commercial services, but the hardened online/offline rule prevented mapping that structure to channel percentages.
  - `300469.SZ` kept `L3.channel.mix` as `Unknown` because customer, industry, product, and region revenue structures did not directly disclose direct/distributor/ecommerce/other channel shares.
  - Natural-language English residue check after run found 0 issues.
  - Stock-attribute PE/PB misuse check after run found 0 issues: no PE/PB percentile tag and no numeric excerpt under `L6.path.tag`.
  - Channel trend hardening held: 0 Chinese free-text `L3.channel.mix.value.trend` values after run.
  - Runner post-processing restored wrapped `scores.formula` in `300459.SZ`, `300468.SZ`, and `300469.SZ` (`formula_normalized=3`).
- Structural diff after run:
  - all 4 files changed only `L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`
  - Non-`nodes` YAML payload is unchanged for all 4 files
- Post-run cheap_extract dry-run:
  - all 4 stocks now show `nothing to fill (skip)` / `prompt_ready=0`
- Scoped closed-loop verifier:
  - full verifier output: `/tmp/domestic_closed_loop_after_batch149.json`
  - full hard violations: 0
  - full soft warnings: 11699
  - target-node violations filtered to the 24 batch dpids: 0
  - target-node evidence_quality type, old-key, English-residue, stock-attribute valuation-misuse, and channel-trend Chinese free-text check: 0 bad target nodes
  - target-file soft warnings: 16 historical non-target warnings only
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count: 162440`
- Test gate after batch: `tests/test_apply_yaml_patch.py tests/test_prompt_gen_schema_block.py tests/test_prompt_gen_governance.py tests/test_schema_validator.py` passed, 86 tests
- Scope audit after batch: `fillable_total=110076`, `skipped_total=24896`, `cheap_extract=7578`
- Residual scope note: `HK_CN_INTERNET` skips already-complete `300674.SZ` and `300682.SZ` and continues at `300624.SZ`, `300634.SZ`, `300687.SZ`, and `300803.SZ`, skipping HK/US tickers for this A-share goal.

## Completed batch 150

- Batch target: `HK_CN_INTERNET`, A-share, `cheap_extract`
- Stocks completed: `300624.SZ`, `300634.SZ`, `300687.SZ`, `300803.SZ`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Parallel runner: `C1_INDUSTRY=HK_CN_INTERNET`, `C1_PARALLEL=2`, via hardened `scripts/run_c1_fill.sh`
- Nodes handled: 24 cheap_extract targets
- Execution note:
  - All 4 child runs exited 0 and the hardened status summary reported `processed=4`, `skipped=0`, `prompt_failed=0`, `failed=0`.
  - `300624.SZ`, `300634.SZ`, `300687.SZ`, and `300803.SZ` each changed exactly the 6 target dpids.
  - `300624.SZ` filled `L3.channel.mix` as Known because annual-report evidence directly disclosed sales-mode shares for direct sales, distribution, and distributor sales; distribution and distributor shares were combined into `distributor_pct`.
  - `300634.SZ` and `300687.SZ` filled `L3.channel.mix` as Known because annual-report evidence directly disclosed direct-sales share of 100%.
  - `300803.SZ` kept `L3.channel.mix` as `Unknown`; local evidence disclosed online sales only, and the hardened online/offline rule prevents mapping online sales to direct/distributor/ecommerce/other channel percentages.
  - Natural-language English residue check after run found 0 issues.
  - Stock-attribute PE/PB misuse check after run found 0 issues: no PE/PB percentile tag and no numeric excerpt under `L6.path.tag`.
  - Channel trend hardening held: 0 Chinese free-text `L3.channel.mix.value.trend` values after run.
  - Runner post-processing restored wrapped `scores.formula` in `300634.SZ` (`formula_normalized=1`).
- Structural diff after run:
  - all 4 files changed only `L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`
  - Non-`nodes` YAML payload is unchanged for all 4 files
- Post-run cheap_extract dry-run:
  - all 4 stocks now show `nothing to fill (skip)` / `prompt_ready=0`
- Scoped closed-loop verifier:
  - full verifier output: `/tmp/domestic_closed_loop_after_batch150.json`
  - full hard violations: 0
  - full soft warnings: 11699
  - target-node violations filtered to the 24 batch dpids: 0
  - target-node evidence_quality type, old-key, English-residue, stock-attribute valuation-misuse, and channel-trend Chinese free-text check: 0 bad target nodes
  - target-file soft warnings: 16 historical non-target warnings only
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count: 162417`
- Test gate after batch: `tests/test_apply_yaml_patch.py tests/test_prompt_gen_schema_block.py tests/test_prompt_gen_governance.py tests/test_schema_validator.py` passed, 86 tests
- Scope audit after batch: `fillable_total=110052`, `skipped_total=24920`, `cheap_extract=7554`
- Residual scope note: `HK_CN_INTERNET` skips already-complete `301248.SZ` and continues at `301095.SZ`, `301171.SZ`, `301236.SZ`, and `301269.SZ`, skipping HK/US tickers for this A-share goal.

## Completed batch 151

- Batch target: `HK_CN_INTERNET`, A-share, `cheap_extract`
- Stocks completed: `301095.SZ`, `301171.SZ`, `301236.SZ`, `301269.SZ`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Parallel runner: `C1_INDUSTRY=HK_CN_INTERNET`, `C1_PARALLEL=2`, via hardened `scripts/run_c1_fill.sh`
- Nodes handled: 24 cheap_extract targets
- Execution note:
  - All 4 child runs exited 0 and the hardened status summary reported `processed=4`, `skipped=0`, `prompt_failed=0`, `failed=0`.
  - `301095.SZ`, `301171.SZ`, `301236.SZ`, and `301269.SZ` each changed exactly the 6 target dpids.
  - `301095.SZ` filled `L3.channel.mix` as Known because annual-report evidence directly disclosed sales-mode shares for direct sales and distributor sales.
  - `301236.SZ` filled `L3.channel.mix` as Known because annual-report evidence directly disclosed sales-mode shares for direct sales and distributor sales, with direct share slightly down.
  - `301171.SZ` and `301269.SZ` kept `L3.channel.mix` as `Unknown`; local evidence covered customer, product, region, or other business structures but did not directly disclose direct/distributor/ecommerce/other channel percentages.
  - Natural-language English residue check after run found 0 issues.
  - Stock-attribute PE/PB misuse check after run found 0 issues: no PE/PB percentile tag and no numeric excerpt under `L6.path.tag`.
  - Channel trend hardening held: 0 Chinese free-text `L3.channel.mix.value.trend` values after run.
  - Runner post-processing restored wrapped `scores.formula` in `301236.SZ` and `301269.SZ` (`formula_normalized=2`).
- Structural diff after run:
  - all 4 files changed only `L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`
  - Non-`nodes` YAML payload is unchanged for all 4 files
- Post-run cheap_extract dry-run:
  - all 4 stocks now show `nothing to fill (skip)` / `prompt_ready=0`
- Scoped closed-loop verifier:
  - full verifier output: `/tmp/domestic_closed_loop_after_batch151.json`
  - full hard violations: 0
  - full soft warnings: 11699
  - target-node violations filtered to the 24 batch dpids: 0
  - target-node evidence_quality type, old-key, English-residue, stock-attribute valuation-misuse, and channel-trend Chinese free-text check: 0 bad target nodes
  - target-file soft warnings: 16 historical non-target warnings only
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count: 162395`
- Test gate after batch: `tests/test_apply_yaml_patch.py tests/test_prompt_gen_schema_block.py tests/test_prompt_gen_governance.py tests/test_schema_validator.py` passed, 86 tests
- Scope audit after batch: `fillable_total=110028`, `skipped_total=24944`, `cheap_extract=7530`
- Residual scope note: `HK_CN_INTERNET` skips already-complete `301638.SZ`, `600131.SH`, `600271.SH`, `600373.SH`, and `600446.SH`; the next prompt-ready A-share batch is `301316.SZ`, `301396.SZ`, `600410.SH`, and `600536.SH`.

## Completed batch 152

- Batch target: `HK_CN_INTERNET`, A-share, `cheap_extract`
- Stocks completed: `301316.SZ`, `301396.SZ`, `600410.SH`, `600536.SH`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Parallel runner: `C1_INDUSTRY=HK_CN_INTERNET`, `C1_PARALLEL=2`, via hardened `scripts/run_c1_fill.sh`
- Nodes handled: 24 cheap_extract targets
- Execution note:
  - All 4 child runs exited 0 and the hardened status summary reported `processed=4`, `skipped=0`, `prompt_failed=0`, `failed=0`.
  - `301316.SZ`, `301396.SZ`, `600410.SH`, and `600536.SH` each changed exactly the 6 target dpids.
  - `301316.SZ` filled `L3.channel.mix` as Known because annual-report evidence directly disclosed direct-sales share of 100%.
  - `301396.SZ`, `600410.SH`, and `600536.SH` kept `L3.channel.mix` as `Unknown`; local evidence covered customer structure, business-line, region, revenue, or operating structure but did not directly disclose direct/distributor/ecommerce/other channel percentages.
  - Natural-language English residue check after run found 0 issues.
  - Stock-attribute PE/PB misuse check after run found 0 issues: no PE/PB percentile tag and no numeric excerpt under `L6.path.tag`.
  - Channel trend hardening held: 0 Chinese free-text `L3.channel.mix.value.trend` values after run.
  - Runner post-processing restored wrapped `scores.formula` in all 4 batch files (`formula_normalized=4`).
- Structural diff after run:
  - all 4 files changed only `L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`
  - Non-`nodes` YAML payload is unchanged for all 4 files
- Post-run cheap_extract dry-run:
  - all 4 stocks now show `nothing to fill (skip)` / `prompt_ready=0`
- Scoped closed-loop verifier:
  - full verifier output: `/tmp/domestic_closed_loop_after_batch152.json`
  - full hard violations: 0
  - full soft warnings: 11699
  - target-node violations filtered to the 24 batch dpids: 0
  - target-node evidence_quality type, old-key, English-residue, stock-attribute valuation-misuse, and channel-trend Chinese free-text check: 0 bad target nodes
  - target-file soft warnings: 15 historical non-target warnings only
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count: 162374`
- Test gate after batch: `tests/test_apply_yaml_patch.py tests/test_prompt_gen_schema_block.py tests/test_prompt_gen_governance.py tests/test_schema_validator.py` passed, 86 tests
- Scope audit after batch: `fillable_total=110004`, `skipped_total=24968`, `cheap_extract=7506`
- Residual scope note: `HK_CN_INTERNET` continues at `600570.SH`, `600588.SH`, `600602.SH`, and `600633.SH`, skipping HK/US tickers and already-complete A-share overlays for this A-share goal.

## Completed batch 153

- Batch target: `HK_CN_INTERNET`, A-share, `cheap_extract`
- Stocks completed: `600570.SH`, `600588.SH`, `600602.SH`, `600633.SH`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Parallel runner: `C1_INDUSTRY=HK_CN_INTERNET`, `C1_PARALLEL=2`, via hardened `scripts/run_c1_fill.sh`
- Nodes handled: 24 cheap_extract targets
- Execution note:
  - All 4 child runs exited 0 and the hardened status summary reported `processed=4`, `skipped=0`, `prompt_failed=0`, `failed=0`.
  - `600570.SH`, `600588.SH`, `600602.SH`, and `600633.SH` each changed exactly the 6 target dpids.
  - `600570.SH` filled `L3.channel.mix` as Known because annual-report evidence directly disclosed direct-sales share of 100%.
  - `600588.SH`, `600602.SH`, and `600633.SH` kept `L3.channel.mix` as `Unknown`; local evidence covered customer concentration, revenue deduction, business overview, R&D, industry/region structure, or main-business disclosures but did not directly disclose direct/distributor/ecommerce/other channel percentages.
  - Natural-language English residue check after run found 0 issues.
  - Stock-attribute PE/PB misuse check after run found 0 issues: no PE/PB percentile tag and no numeric excerpt under `L6.path.tag`.
  - Channel trend hardening held: 0 Chinese free-text `L3.channel.mix.value.trend` values after run.
  - Runner post-processing restored wrapped `scores.formula` in `600633.SH` (`formula_normalized=1`).
- Structural diff after run:
  - all 4 files changed only `L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`
  - Non-`nodes` YAML payload is unchanged for all 4 files
- Post-run cheap_extract dry-run:
  - all 4 stocks now show `nothing to fill (skip)` / `prompt_ready=0`
- Scoped closed-loop verifier:
  - full verifier output: `/tmp/domestic_closed_loop_after_batch153.json`
  - full hard violations: 0
  - full soft warnings: 11699
  - target-node violations filtered to the 24 batch dpids: 0
  - target-node evidence_quality type, old-key, English-residue, stock-attribute valuation-misuse, and channel-trend Chinese free-text check: 0 bad target nodes
  - target-file soft warnings: 16 historical non-target warnings only
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count: 162353`
- Test gate after batch: `tests/test_apply_yaml_patch.py tests/test_prompt_gen_schema_block.py tests/test_prompt_gen_governance.py tests/test_schema_validator.py` passed, 86 tests
- Scope audit after batch: `fillable_total=109980`, `skipped_total=24992`, `cheap_extract=7482`
- Residual scope note: `HK_CN_INTERNET` skips already-complete `600637.SH`, `600666.SH`, `600728.SH`, `600850.SH`, `600959.SH`, `600977.SH`, `600986.SH`, `600996.SH`, `601019.SH`, `601098.SH`, `601801.SH`, `601811.SH`, `601900.SH`, `601921.SH`, and `601928.SH`; the next prompt-ready A-share batch is `600845.SH`, `601360.SH`, `601519.SH`, and `601858.SH`.

## Completed batch 154

- Batch target: `HK_CN_INTERNET`, A-share, `cheap_extract`
- Stocks completed: `600845.SH`, `601360.SH`, `601519.SH`, `601858.SH`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Parallel runner: `C1_INDUSTRY=HK_CN_INTERNET`, `C1_PARALLEL=2`, via hardened `scripts/run_c1_fill.sh`
- Nodes handled: 24 cheap_extract targets
- Execution note:
  - All 4 child runs exited 0 and the hardened status summary reported `processed=4`, `skipped=0`, `prompt_failed=0`, `failed=0`.
  - `600845.SH`, `601360.SH`, `601519.SH`, and `601858.SH` each changed exactly the 6 target dpids.
  - `601858.SH` filled `L3.channel.mix` as Known because annual-report evidence directly disclosed sales-mode shares for direct sales and distributor sales.
  - `600845.SH`, `601360.SH`, and `601519.SH` kept `L3.channel.mix` as `Unknown`; local evidence covered business scope, service content, Q&A, customer concentration, revenue deduction, or business segments but did not directly disclose direct/distributor/ecommerce/other channel percentages.
  - Natural-language English residue check after run found 0 issues.
  - Stock-attribute PE/PB misuse check after run found 0 issues: no PE/PB percentile tag and no numeric excerpt under `L6.path.tag`.
  - Channel trend hardening held: 0 Chinese free-text `L3.channel.mix.value.trend` values after run.
  - Runner post-processing restored wrapped `scores.formula` in `600845.SH`, `601519.SH`, and `601858.SH` (`formula_normalized=3`).
  - Post-verifier fix: `601858.SH:L1.model.tag` initially had one target-node excerpt warning because a business-scope phrase was cited against `L1.company.main_business`; the node was tightened to the actual local main-business excerpt and unsupported digital-service wording was removed.
- Structural diff after run:
  - all 4 files changed only `L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`
  - Non-`nodes` YAML payload is unchanged for all 4 files
- Post-run cheap_extract dry-run:
  - all 4 stocks now show `nothing to fill (skip)` / `prompt_ready=0`
- Scoped closed-loop verifier:
  - full verifier output: `/tmp/domestic_closed_loop_after_batch154.json`
  - full hard violations: 0
  - full soft warnings: 11686
  - target-node violations filtered to the 24 batch dpids after fix: 0
  - target-node evidence_quality type, old-key, English-residue, stock-attribute valuation-misuse, and channel-trend Chinese free-text check: 0 bad target nodes
  - target-file soft warnings: 22 historical non-target warnings only
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count: 162338`
- Test gate after batch: `tests/test_apply_yaml_patch.py tests/test_prompt_gen_schema_block.py tests/test_prompt_gen_governance.py tests/test_schema_validator.py` passed, 86 tests
- Scope audit after batch: `fillable_total=109956`, `skipped_total=25016`, `cheap_extract=7458`
- Residual scope note: `HK_CN_INTERNET` skips already-complete `603039.SH`, `603103.SH`, `603171.SH`, `603533.SH`, `603613.SH`, `603927.SH`, and `688031.SH`; the next prompt-ready A-share batch is `603000.SH`, `603444.SH`, `603629.SH`, and `603859.SH`.

## Completed batch 155

- Batch target: `HK_CN_INTERNET`, A-share, `cheap_extract`
- Stocks completed: `603000.SH`, `603444.SH`, `603629.SH`, `603859.SH`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Parallel runner: `C1_INDUSTRY=HK_CN_INTERNET`, `C1_PARALLEL=2`, via hardened `scripts/run_c1_fill.sh`
- Nodes handled: 24 cheap_extract targets
- Execution note:
  - All 4 child runs exited 0 and the hardened status summary reported `processed=4`, `skipped=0`, `prompt_failed=0`, `failed=0`.
  - `603000.SH`, `603444.SH`, `603629.SH`, and `603859.SH` each changed exactly the 6 target dpids.
  - `603859.SH` filled `L3.channel.mix` as Known because annual-report evidence directly disclosed direct-sales share of 100%.
  - `603000.SH`, `603444.SH`, and `603629.SH` kept `L3.channel.mix` as `Unknown`; local evidence covered customer concentration, product/region revenue structures, main-business text, or equipment distribution revenue but did not directly disclose direct/distributor/ecommerce/other channel percentages.
  - Natural-language English residue check after run found 0 issues.
  - Stock-attribute PE/PB misuse check after run found 0 issues: no PE/PB percentile tag and no numeric excerpt under `L6.path.tag`.
  - Channel trend hardening held: 0 Chinese free-text `L3.channel.mix.value.trend` values after run.
  - Runner post-processing restored wrapped `scores.formula` in `603444.SH` (`formula_normalized=1`).
  - Post-verifier fix: `603000.SH:L1.stock_attr.tags` initially had one target-node excerpt warning because a business-scope phrase was cited against `L1.company.main_business`; the node was tightened to the actual local main-business excerpt and unsupported government-digitization wording was removed.
- Structural diff after run:
  - all 4 files changed only `L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`
  - Non-`nodes` YAML payload is unchanged for all 4 files
- Post-run cheap_extract dry-run:
  - all 4 stocks now show `nothing to fill (skip)` / `prompt_ready=0`
- Scoped closed-loop verifier:
  - full verifier output: `/tmp/domestic_closed_loop_after_batch155.json`
  - full hard violations: 0
  - full soft warnings: 11686
  - target-node violations filtered to the 24 batch dpids after fix: 0
  - target-node evidence_quality type, old-key, English-residue, stock-attribute valuation-misuse, and channel-trend Chinese free-text check: 0 bad target nodes
  - target-file soft warnings: 16 historical non-target warnings only
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count: 162317`
- Test gate after batch: `tests/test_apply_yaml_patch.py tests/test_prompt_gen_schema_block.py tests/test_prompt_gen_governance.py tests/test_schema_validator.py` passed, 86 tests
- Scope audit after batch: `fillable_total=109932`, `skipped_total=25040`, `cheap_extract=7434`
- Residual scope note: `HK_CN_INTERNET` skips already-complete `688158.SH` and `688191.SH`; the next prompt-ready A-share batch is `603888.SH`, `688088.SH`, `688111.SH`, and `688206.SH`.

## Completed batch 156

- Batch target: `HK_CN_INTERNET`, A-share, `cheap_extract`
- Stocks completed: `603888.SH`, `688088.SH`, `688111.SH`, `688206.SH`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Parallel runner: `C1_INDUSTRY=HK_CN_INTERNET`, `C1_PARALLEL=2`, via hardened `scripts/run_c1_fill.sh`
- Nodes handled: 24 cheap_extract targets
- Execution note:
  - All 4 child runs exited 0 and the hardened status summary reported `processed=4`, `skipped=0`, `prompt_failed=0`, `failed=0`.
  - `603888.SH`, `688088.SH`, `688111.SH`, and `688206.SH` each changed exactly the 6 target dpids.
  - `688088.SH` filled `L3.channel.mix` as Known because annual-report evidence directly disclosed direct-sales share of 100%.
  - `603888.SH`, `688111.SH`, and `688206.SH` kept `L3.channel.mix` as `Unknown`; local evidence covered business-line revenue, customer concentration, supplier information, region/product structures, or main-business descriptions but did not directly disclose direct/distributor/ecommerce/other channel percentages.
  - Natural-language English residue check after run found 0 issues.
  - Stock-attribute PE/PB misuse check after run found 0 issues: no PE/PB percentile tag and no numeric excerpt under `L6.path.tag`.
  - Channel trend hardening held: 0 Chinese free-text `L3.channel.mix.value.trend` values after run.
  - Runner post-processing restored wrapped `scores.formula` in `603888.SH` and `688206.SH` (`formula_normalized=2`).
- Structural diff after run:
  - all 4 files changed only `L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`
  - Non-`nodes` YAML payload is unchanged for all 4 files
- Post-run cheap_extract dry-run:
  - all 4 stocks now show `nothing to fill (skip)` / `prompt_ready=0`
- Scoped closed-loop verifier:
  - full verifier output: `/tmp/domestic_closed_loop_after_batch156.json`
  - full hard violations: 0
  - full soft warnings: 11677
  - target-node violations filtered to the 24 batch dpids: 0
  - target-node evidence_quality type, old-key, English-residue, stock-attribute valuation-misuse, and channel-trend Chinese free-text check: 0 bad target nodes
  - target-file soft warnings: 21 historical non-target warnings only
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count: 162302`
- Test gate after batch: `tests/test_apply_yaml_patch.py tests/test_prompt_gen_schema_block.py tests/test_prompt_gen_governance.py tests/test_schema_validator.py` passed, 86 tests
- Scope audit after batch: `fillable_total=109908`, `skipped_total=25064`, `cheap_extract=7410`
- Residual scope note:
  - `HK_CN_INTERNET` skips already-complete `688327.SH`, `688343.SH`, `688507.SH`, `688561.SH`, `688568.SH`, `688692.SH`, and `920116.BJ`; remaining prompt-ready A-share tail is `688258.SH`, `688318.SH`, and `688615.SH`.
  - Next full four-stock prompt-ready batch, if moving to the next industry, is `INNOVATIVE_PHARMA`: `000028.SZ`, `000403.SZ`, `000513.SZ`, and `000534.SZ`.

## Completed batch 157

- Batch target: `HK_CN_INTERNET`, A-share, `cheap_extract`
- Stocks completed: `688258.SH`, `688318.SH`, `688615.SH`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Parallel runner: `C1_INDUSTRY=HK_CN_INTERNET`, `C1_PARALLEL=2`, via hardened `scripts/run_c1_fill.sh`
- Nodes handled: 18 cheap_extract targets
- Execution note:
  - All 3 child runs exited 0 and the hardened status summary reported `processed=3`, `skipped=0`, `prompt_failed=0`, `failed=0`.
  - `688258.SH`, `688318.SH`, and `688615.SH` each changed exactly the 6 target dpids.
  - All 3 batch stocks filled `L3.channel.mix` as Known because annual-report evidence directly disclosed sales-mode shares: `688258.SH` direct/distribution sales, `688318.SH` direct-sales share of 100%, and `688615.SH` direct, distributor, and third-party platform cooperation promotion modes.
  - Natural-language English residue check after run found 0 issues.
  - Stock-attribute PE/PB misuse check after run found 0 issues: no PE/PB percentile tag and no numeric excerpt under `L6.path.tag`.
  - Channel trend hardening held: 0 Chinese free-text `L3.channel.mix.value.trend` values after run.
  - Runner post-processing restored wrapped `scores.formula` in `688258.SH` (`formula_normalized=1`).
- Structural diff after run:
  - all 3 files changed only `L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`
  - Non-`nodes` YAML payload is unchanged for all 3 files
- Post-run cheap_extract dry-run:
  - all 3 stocks now show `nothing to fill (skip)` / `prompt_ready=0`
  - `HK_CN_INTERNET` tail check on `688258.SH`, `688318.SH`, `688615.SH`, `688692.SH`, and `920116.BJ` returned `prompt_ready=0`, confirming no remaining prompt-ready A-share cheap_extract targets in this industry tail.
- Scoped closed-loop verifier:
  - full verifier output: `/tmp/domestic_closed_loop_after_batch157.json`
  - full hard violations: 0
  - full soft warnings: 11677
  - target-node violations filtered to the 18 batch dpids: 0
  - target-node evidence_quality type, old-key, English-residue, stock-attribute valuation-misuse, and channel-trend Chinese free-text check: 0 bad target nodes
  - target-file soft warnings: 12 historical non-target warnings only
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count: 162284`
- Test gate after batch: `tests/test_apply_yaml_patch.py tests/test_prompt_gen_schema_block.py tests/test_prompt_gen_governance.py tests/test_schema_validator.py` passed, 86 tests
- Scope audit after batch: `fillable_total=109890`, `skipped_total=25082`, `cheap_extract=7392`
- Residual scope note:
  - `HK_CN_INTERNET` current A-share `cheap_extract` prompt-ready queue is clear under the checked tail.
  - Next prompt-ready A-share batch is `INNOVATIVE_PHARMA`: `000028.SZ`, `000403.SZ`, `000513.SZ`, and `000534.SZ`.

## Completed batch 158

- Batch target: `INNOVATIVE_PHARMA`, A-share, `cheap_extract`
- Stocks completed: `000028.SZ`, `000403.SZ`, `000513.SZ`, `000534.SZ`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Parallel runner: `C1_INDUSTRY=INNOVATIVE_PHARMA`, `C1_PARALLEL=2`, via hardened `scripts/run_c1_fill.sh`
- Nodes handled: 24 cheap_extract targets
- Execution note:
  - All 4 child runs exited 0 and the hardened status summary reported `processed=4`, `skipped=0`, `prompt_failed=0`, `failed=0`.
  - `000028.SZ`, `000403.SZ`, `000513.SZ`, and `000534.SZ` each changed exactly the 6 target dpids.
  - All 4 batch stocks filled `L3.channel.mix` as Known because annual-report evidence directly disclosed sales-mode shares.
  - Natural-language English residue check after run found 0 issues.
  - Stock-attribute PE/PB misuse check after run found 0 issues: no PE/PB percentile tag and no numeric excerpt under `L6.path.tag`.
  - Channel trend hardening held: 0 Chinese free-text `L3.channel.mix.value.trend` values after run.
  - Runner post-processing restored wrapped `scores.formula` in `000403.SZ` and `000534.SZ` (`formula_normalized=2`).
- Structural diff after run:
  - all 4 files changed only `L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`
  - Non-`nodes` YAML payload is unchanged for all 4 files
- Post-run cheap_extract dry-run:
  - all 4 stocks now show `nothing to fill (skip)` / `prompt_ready=0`
- Scoped closed-loop verifier:
  - full verifier output: `/tmp/domestic_closed_loop_after_batch158.json`
  - full hard violations: 0
  - full soft warnings: 11677
  - target-node violations filtered to the 24 batch dpids: 0
  - target-node evidence_quality type, old-key, English-residue, stock-attribute valuation-misuse, and channel-trend Chinese free-text check: 0 bad target nodes
  - target-file soft warnings: 15 historical non-target warnings only
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count: 162260`
- Test gate after batch: `tests/test_apply_yaml_patch.py tests/test_prompt_gen_schema_block.py tests/test_prompt_gen_governance.py tests/test_schema_validator.py` passed, 86 tests
- Scope audit after batch: `fillable_total=109866`, `skipped_total=25106`, `cheap_extract=7368`
- Residual scope note: `INNOVATIVE_PHARMA` continues at `000661.SZ`, `000739.SZ`, `000766.SZ`, and `000908.SZ`.

## Completed batch 159

- Batch target: `INNOVATIVE_PHARMA`, A-share, `cheap_extract`
- Stocks completed: `000661.SZ`, `000739.SZ`, `000766.SZ`, `000908.SZ`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Parallel runner: `C1_INDUSTRY=INNOVATIVE_PHARMA`, `C1_PARALLEL=2`, via hardened `scripts/run_c1_fill.sh`
- Nodes handled: 24 cheap_extract targets
- Execution note:
  - All 4 child runs exited 0 and the hardened status summary reported `processed=4`, `skipped=0`, `prompt_failed=0`, `failed=0`.
  - `000661.SZ`, `000739.SZ`, `000766.SZ`, and `000908.SZ` each changed exactly the 6 target dpids.
  - `000661.SZ`, `000766.SZ`, and `000908.SZ` filled `L3.channel.mix` as Known because annual-report evidence directly disclosed sales-mode shares.
  - `000739.SZ` kept `L3.channel.mix` as `Unknown`; local evidence only disclosed customer concentration/trade business customer/product service structures, not direct/distributor/ecommerce/other channel percentages.
  - Natural-language English residue check after run found 0 issues.
  - Stock-attribute PE/PB misuse check after run found 0 issues.
  - Channel trend hardening held: 0 Chinese free-text `L3.channel.mix.value.trend` values after run.
  - Post-run normalization changed `000908.SZ:L3.channel.mix.value.trend` from `direct_share_down` to the established enum style `direct_share_slightly_down`.
  - Runner post-processing restored wrapped `scores.formula` in `000661.SZ` and `000766.SZ` (`formula_normalized=2`).
- Structural diff after run:
  - all 4 files changed only `L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`
  - Non-`nodes` YAML payload is unchanged for all 4 files
- Post-run cheap_extract dry-run:
  - all 4 stocks now show `nothing to fill (skip)` / `prompt_ready=0`
- Scoped closed-loop verifier:
  - full verifier output: `/tmp/domestic_closed_loop_after_batch159.json`
  - full hard violations: 0
  - full soft warnings: 11677
  - target-node violations filtered to the 24 batch dpids: 0
  - target-node evidence_quality type, old-key, English-residue, stock-attribute valuation-misuse, and channel-trend Chinese free-text check: 0 bad target nodes
  - target-file soft warnings: 16 historical non-target warnings only
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count=162237`
- Test gate after batch: `tests/test_apply_yaml_patch.py tests/test_prompt_gen_schema_block.py tests/test_prompt_gen_governance.py tests/test_schema_validator.py` passed, 86 tests
- Scope audit after batch: `fillable_total=109842`, `skipped_total=25130`, `cheap_extract=7344`
- Residual scope note: `INNOVATIVE_PHARMA` continues at `000963.SZ`, `002001.SZ`, `002007.SZ`, and `002019.SZ`.

## Completed batch 160

- Batch target: `INNOVATIVE_PHARMA`, A-share, `cheap_extract`
- Stocks completed: `000963.SZ`, `002001.SZ`, `002007.SZ`, `002019.SZ`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Parallel runner: `C1_INDUSTRY=INNOVATIVE_PHARMA`, `C1_PARALLEL=2`, via hardened `scripts/run_c1_fill.sh`
- Nodes handled: 24 cheap_extract targets
- Execution note:
  - All 4 child runs exited 0 and the hardened status summary reported `processed=4`, `skipped=0`, `prompt_failed=0`, `failed=0`.
  - `000963.SZ`, `002001.SZ`, `002007.SZ`, and `002019.SZ` each changed exactly the 6 target dpids.
  - `000963.SZ`, `002001.SZ`, and `002007.SZ` kept `L3.channel.mix` as `Unknown` because local materials did not directly disclose direct/distributor/ecommerce/other channel percentages.
  - `002019.SZ` filled `L3.channel.mix` as Known because the 2025 annual report disclosed sales-mode shares: direct 16.89% and distributor 83.11%.
  - Natural-language English residue check after post-run cleanup found 0 issues.
  - Stock-attribute PE/PB misuse check after post-run cleanup found 0 issues.
  - Channel trend hardening held: 0 Chinese free-text `L3.channel.mix.value.trend` values after run.
  - Post-run cleanup rewrote natural-language notes that mentioned enum keys or valuation warning terms, without changing enum field values.
  - Runner post-processing restored wrapped `scores.formula` in `000963.SZ` and `002001.SZ` (`formula_normalized=2`).
- Structural diff after run:
  - all 4 files changed only `L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`
  - Non-`nodes` YAML payload is unchanged for all 4 files
- Post-run cheap_extract dry-run:
  - all 4 stocks now show `nothing to fill (skip)` / `prompt_ready=0`
- Scoped closed-loop verifier:
  - full verifier output: `/tmp/domestic_closed_loop_after_batch160.json`
  - full hard violations: 0
  - full soft warnings: 11671
  - target-node violations filtered to the 24 batch dpids: 0
  - target-node evidence_quality type, old-key, English-residue, stock-attribute valuation-misuse, and channel-trend Chinese free-text check: 0 bad target nodes
  - target-file soft warnings: 34 historical non-target warnings only
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count=162221`
- Test gate after batch: `tests/test_apply_yaml_patch.py tests/test_prompt_gen_schema_block.py tests/test_prompt_gen_governance.py tests/test_schema_validator.py` passed, 86 tests
- Scope audit after batch: `fillable_total=109818`, `skipped_total=25154`, `cheap_extract=7320`
- Residual scope note: `INNOVATIVE_PHARMA` continues at `002020.SZ`, `002044.SZ`, `002223.SZ`, and `002252.SZ`.

## Completed batch 161

- Batch target: `INNOVATIVE_PHARMA`, A-share, `cheap_extract`
- Stocks completed: `002020.SZ`, `002044.SZ`, `002223.SZ`, `002252.SZ`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Parallel runner: `C1_INDUSTRY=INNOVATIVE_PHARMA`, `C1_PARALLEL=2`, via hardened `scripts/run_c1_fill.sh`
- Nodes handled: 24 cheap_extract targets
- Execution note:
  - All 4 child runs exited 0 and the hardened status summary reported `processed=4`, `skipped=0`, `prompt_failed=0`, `failed=0`.
  - `002020.SZ`, `002044.SZ`, `002223.SZ`, and `002252.SZ` each changed exactly the 6 target dpids.
  - `002020.SZ`, `002044.SZ`, and `002223.SZ` filled `L3.channel.mix` as Known because annual-report evidence directly disclosed sales-mode shares.
  - `002252.SZ` kept `L3.channel.mix` as `Unknown` because local materials did not directly disclose direct/distributor/ecommerce/other channel percentages.
  - Natural-language English residue check after post-run cleanup found 0 issues.
  - Stock-attribute PE/PB misuse check after post-run cleanup found 0 issues.
  - Channel trend hardening held: 0 Chinese free-text `L3.channel.mix.value.trend` values after run.
  - Post-run cleanup normalized `002020.SZ:L3.channel.mix.value.trend` from `direct_share_down` to `direct_share_slightly_down` and rewrote natural-language notes that mentioned enum keys or valuation warning terms.
  - Runner post-processing restored wrapped `scores.formula` in `002020.SZ` and `002044.SZ` (`formula_normalized=2`).
- Structural diff after run:
  - all 4 files changed only `L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`
  - Non-`nodes` YAML payload is unchanged for all 4 files
- Post-run cheap_extract dry-run:
  - all 4 stocks now show `nothing to fill (skip)` / `prompt_ready=0`
- Scoped closed-loop verifier:
  - full verifier output: `/tmp/domestic_closed_loop_after_batch161.json`
  - full hard violations: 0
  - full soft warnings: 11671
  - target-node violations filtered to the 24 batch dpids: 0
  - target-node evidence_quality type, old-key, English-residue, stock-attribute valuation-misuse, and channel-trend Chinese free-text check: 0 bad target nodes
  - target-file soft warnings: 16 historical non-target warnings only
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count=162198`
- Test gate after batch: `tests/test_apply_yaml_patch.py tests/test_prompt_gen_schema_block.py tests/test_prompt_gen_governance.py tests/test_schema_validator.py` passed, 86 tests
- Scope audit after batch: `fillable_total=109794`, `skipped_total=25178`, `cheap_extract=7296`
- Residual scope note: `INNOVATIVE_PHARMA` continues at `002262.SZ`, `002294.SZ`, `002399.SZ`, and `002422.SZ`.

## Completed batch 162

- Batch target: `INNOVATIVE_PHARMA`, A-share, `cheap_extract`
- Stocks completed: `002262.SZ`, `002294.SZ`, `002399.SZ`, `002422.SZ`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Parallel runner: `C1_INDUSTRY=INNOVATIVE_PHARMA`, `C1_PARALLEL=2`, via hardened `scripts/run_c1_fill.sh`
- Nodes handled: 24 cheap_extract targets
- Execution note:
  - All 4 child runs exited 0 and the hardened status summary reported `processed=4`, `skipped=0`, `prompt_failed=0`, `failed=0`.
  - `002262.SZ`, `002294.SZ`, `002399.SZ`, and `002422.SZ` each changed exactly the 6 target dpids.
  - `002294.SZ` and `002422.SZ` filled `L3.channel.mix` as Known because annual-report evidence directly disclosed sales-mode shares.
  - `002262.SZ` and `002399.SZ` kept `L3.channel.mix` as `Unknown` because local materials did not directly disclose direct/distributor/ecommerce/other channel percentages.
  - Natural-language English residue check after post-run cleanup found 0 issues.
  - Stock-attribute PE/PB misuse check after post-run cleanup found 0 issues.
  - Channel trend hardening held: 0 Chinese free-text `L3.channel.mix.value.trend` values after run.
  - Post-run cleanup rewrote natural-language notes that mentioned enum keys, English abbreviations, or valuation warning terms, while preserving evidence and enum field values.
  - Runner post-processing restored wrapped `scores.formula` in `002262.SZ`, `002399.SZ`, and `002422.SZ` (`formula_normalized=3`).
- Structural diff after run:
  - all 4 files changed only `L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`
  - Non-`nodes` YAML payload is unchanged for all 4 files
- Post-run cheap_extract dry-run:
  - all 4 stocks now show `nothing to fill (skip)` / `prompt_ready=0`
- Scoped closed-loop verifier:
  - full verifier output: `/tmp/domestic_closed_loop_after_batch162.json`
  - full hard violations: 0
  - full soft warnings: 11671
  - target-node violations filtered to the 24 batch dpids: 0
  - target-node evidence_quality type, old-key, English-residue, stock-attribute valuation-misuse, and channel-trend Chinese free-text check: 0 bad target nodes
  - target-file soft warnings: 16 historical non-target warnings only
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count=162176`
- Test gate after batch: `tests/test_apply_yaml_patch.py tests/test_prompt_gen_schema_block.py tests/test_prompt_gen_governance.py tests/test_schema_validator.py` passed, 86 tests
- Scope audit after batch: `fillable_total=109770`, `skipped_total=25202`, `cheap_extract=7272`
- Residual scope note: `INNOVATIVE_PHARMA` continues at `002432.SZ`, `002653.SZ`, `002675.SZ`, and `002755.SZ`.

## Completed batch 163

- Batch target: `INNOVATIVE_PHARMA`, A-share, `cheap_extract`
- Stocks completed: `002432.SZ`, `002653.SZ`, `002675.SZ`, `002755.SZ`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Parallel runner: `C1_INDUSTRY=INNOVATIVE_PHARMA`, `C1_PARALLEL=2`, via hardened `scripts/run_c1_fill.sh`
- Nodes handled: 24 cheap_extract targets
- Execution note:
  - All 4 child runs exited 0 and the hardened status summary reported `processed=4`, `skipped=0`, `prompt_failed=0`, `failed=0`.
  - `002432.SZ`, `002653.SZ`, `002675.SZ`, and `002755.SZ` each changed exactly the 6 target dpids.
  - `002653.SZ` and `002755.SZ` filled `L3.channel.mix` as Known because annual-report evidence directly disclosed sales-mode shares.
  - `002432.SZ` kept `L3.channel.mix` as `Unknown` because annual-report evidence only disclosed online/offline sales mode, which is not mapped to direct/distributor/ecommerce/other channel mix.
  - `002675.SZ` kept `L3.channel.mix` as `Unknown` because local materials did not directly disclose direct/distributor/ecommerce/other channel percentages.
  - Natural-language English residue check after post-run cleanup found 0 issues.
  - Stock-attribute PE/PB misuse check after post-run cleanup found 0 issues.
  - Channel trend hardening held: 0 Chinese free-text `L3.channel.mix.value.trend` values after run.
  - Post-run cleanup rewrote natural-language notes that mentioned enum keys, English abbreviations, or valuation warning terms, while preserving evidence and enum field values.
  - Post-verifier cleanup narrowed `002432.SZ:L1.model.tag` evidence to the exact local main-business excerpt after the first verifier run flagged a target-node excerpt mismatch.
  - Runner post-processing restored wrapped `scores.formula` in `002432.SZ` and `002755.SZ` (`formula_normalized=2`).
- Structural diff after run:
  - all 4 files changed only `L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`
  - Non-`nodes` YAML payload is unchanged for all 4 files
- Post-run cheap_extract dry-run:
  - all 4 stocks now show `nothing to fill (skip)` / `prompt_ready=0`
- Scoped closed-loop verifier:
  - full verifier output: `/tmp/domestic_closed_loop_after_batch163.json`
  - full hard violations: 0
  - full soft warnings: 11671
  - target-node violations filtered to the 24 batch dpids after cleanup: 0
  - target-node evidence_quality type, old-key, English-residue, stock-attribute valuation-misuse, and channel-trend Chinese free-text check: 0 bad target nodes
  - target-file soft warnings: 14 historical non-target warnings only
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count=162154`
- Test gate after batch: `tests/test_apply_yaml_patch.py tests/test_prompt_gen_schema_block.py tests/test_prompt_gen_governance.py tests/test_schema_validator.py` passed, 86 tests
- Scope audit after batch: `fillable_total=109746`, `skipped_total=25226`, `cheap_extract=7248`
- Residual scope note: `INNOVATIVE_PHARMA` continues at `002773.SZ`, `002821.SZ`, `002901.SZ`, and `300003.SZ`.

## Completed batch 164

- Batch target: `INNOVATIVE_PHARMA`, A-share, `cheap_extract`
- Stocks completed: `002773.SZ`, `002821.SZ`, `002901.SZ`, `300003.SZ`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Parallel runner: `C1_INDUSTRY=INNOVATIVE_PHARMA`, `C1_PARALLEL=2`, via hardened `scripts/run_c1_fill.sh`
- Nodes handled: 24 cheap_extract targets
- Execution note:
  - All 4 child runs exited 0 and the hardened status summary reported `processed=4`, `skipped=0`, `prompt_failed=0`, `failed=0`.
  - `002773.SZ`, `002821.SZ`, `002901.SZ`, and `300003.SZ` each changed exactly the 6 target dpids.
  - `002773.SZ`, `002821.SZ`, and `002901.SZ` filled `L3.channel.mix` as Known because annual-report evidence directly disclosed sales-mode shares.
  - `300003.SZ` kept `L3.channel.mix` as `Unknown` because local materials did not directly disclose direct/distributor/ecommerce/other channel percentages.
  - Natural-language English residue check after post-run cleanup found 0 issues.
  - Stock-attribute PE/PB misuse check after post-run cleanup found 0 issues.
  - Channel trend hardening held: 0 Chinese free-text `L3.channel.mix.value.trend` values after run.
  - Post-run cleanup rewrote natural-language notes that mentioned enum keys, English abbreviations, or valuation warning terms, while preserving evidence and enum field values.
  - Runner post-processing restored wrapped `scores.formula` in `002773.SZ` and `002821.SZ` (`formula_normalized=2`).
- Structural diff after run:
  - all 4 files changed only `L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`
  - Non-`nodes` YAML payload is unchanged for all 4 files
- Post-run cheap_extract dry-run:
  - all 4 stocks now show `nothing to fill (skip)` / `prompt_ready=0`
- Scoped closed-loop verifier:
  - full verifier output: `/tmp/domestic_closed_loop_after_batch164.json`
  - full hard violations: 0
  - full soft warnings: 11671
  - target-node violations filtered to the 24 batch dpids: 0
  - target-node evidence_quality type, old-key, English-residue, stock-attribute valuation-misuse, and channel-trend Chinese free-text check: 0 bad target nodes
  - target-file soft warnings: 15 historical non-target warnings only
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count=162131`
- Test gate after batch: `tests/test_apply_yaml_patch.py tests/test_prompt_gen_schema_block.py tests/test_prompt_gen_governance.py tests/test_schema_validator.py` passed, 86 tests
- Scope audit after batch: `fillable_total=109722`, `skipped_total=25250`, `cheap_extract=7224`
- Residual scope note: `INNOVATIVE_PHARMA` continues at `300009.SZ`, `300015.SZ`, `300049.SZ`, and `300122.SZ`.

## Completed batch 165

- Batch target: `INNOVATIVE_PHARMA`, A-share, `cheap_extract`
- Stocks completed: `300009.SZ`, `300015.SZ`, `300049.SZ`, `300122.SZ`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Parallel runner: `C1_INDUSTRY=INNOVATIVE_PHARMA`, `C1_PARALLEL=2`, via hardened `scripts/run_c1_fill.sh`
- Nodes handled: 24 cheap_extract targets
- Execution note:
  - All 4 child runs exited 0 and the hardened status summary reported `processed=4`, `skipped=0`, `prompt_failed=0`, `failed=0`.
  - `300009.SZ`, `300015.SZ`, `300049.SZ`, and `300122.SZ` each changed exactly the 6 target dpids.
  - `300015.SZ` filled `L3.channel.mix` as Known because annual-report evidence directly disclosed direct-sales share of 100%.
  - `300009.SZ`, `300049.SZ`, and `300122.SZ` kept `L3.channel.mix` as `Unknown` because local materials did not directly disclose direct/distributor/ecommerce/other channel percentages.
  - Natural-language English/schema-key residue check after post-run cleanup found 0 issues.
  - Stock-attribute PE/PB valuation wording misuse check after post-run cleanup found 0 issues.
  - Channel trend hardening held: 0 Chinese free-text `L3.channel.mix.value.trend` values after run.
  - Post-run cleanup rewrote natural-language notes that mentioned enum keys, English product/technology abbreviations, or valuation warning terms, while preserving evidence and enum field values.
  - Runner post-processing restored wrapped `scores.formula` in `300049.SZ` and `300122.SZ` (`formula_normalized=2`).
- Pipeline hardening from this batch:
  - `scripts/codex_prompt_gen.py` now tells GPT-5.5 not to copy schema keys or enum keys such as `rank`, `share_pct`, `trend`, `path.tag`, `decline`, or `modest_growth` into natural-language fields.
  - `scripts/codex_prompt_gen.py` now tells GPT-5.5 not to write stock-attribute governance text such as "未把估值倍数/分位数/百分位写入标签" into `value.evidence_summary` or `value.notes`; it should use the neutral Chinese wording "未使用具体估值数值或相对位置作为标签".
  - `mvp20/schema_validator.py` now emits soft warnings for natural-language schema/enum residue, `L1.stock_attr.tags` valuation-guardrail wording, and Chinese free-text in `L3.channel.mix.value.trend`.
  - `tests/test_prompt_gen_schema_block.py`, `tests/test_prompt_gen_governance.py`, `tests/test_schema_validator.py`, and `tests/test_apply_yaml_patch.py` cover these hardening rules.
- Structural diff after run:
  - all 4 files changed only `L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`
  - Non-`nodes` YAML payload is unchanged for all 4 files
- Post-run cheap_extract dry-run:
  - all 4 completed stocks now show `nothing to fill (skip)` / `prompt_ready=0`
- Scoped closed-loop verifier:
  - full verifier output: `/tmp/domestic_closed_loop_after_batch165.json`
  - full hard violations: 0
  - full soft warnings: 12218
  - target-node violations filtered to the 24 batch dpids: 0
  - target-node evidence_quality type, old-key, English/schema-key residue, stock-attribute valuation-misuse, and channel-trend Chinese free-text check: 0 bad target nodes
  - target-file soft warnings: 16 historical non-target warnings only
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count=162110`
- Test gate after batch: `tests/test_apply_yaml_patch.py tests/test_prompt_gen_schema_block.py tests/test_prompt_gen_governance.py tests/test_schema_validator.py` passed, 90 tests
- Scope audit after batch: `fillable_total=109698`, `skipped_total=25274`, `cheap_extract=7200`
- Residual scope note: `INNOVATIVE_PHARMA` continues at `300142.SZ`, `300199.SZ`, `300204.SZ`, and `300244.SZ`.

## Completed batch 166

- Batch target: `INNOVATIVE_PHARMA`, A-share, `cheap_extract`
- Stocks completed: `300142.SZ`, `300199.SZ`, `300204.SZ`, `300244.SZ`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Parallel runner: `C1_INDUSTRY=INNOVATIVE_PHARMA`, `C1_PARALLEL=2`, via hardened `scripts/run_c1_fill.sh`
- Nodes handled: 24 cheap_extract targets
- Execution note:
  - All 4 child runs exited 0 and the hardened status summary reported `processed=4`, `skipped=0`, `prompt_failed=0`, `failed=0`.
  - `300142.SZ`, `300199.SZ`, `300204.SZ`, and `300244.SZ` each changed exactly the 6 target dpids.
  - All 4 stocks filled `L3.channel.mix` as Known because annual-report evidence directly disclosed sales-mode shares.
  - `300244.SZ` disclosed direct/distributor sales-mode shares with internal related-party elimination; the runner preserved the disclosed direct/distributor values and did not force a synthetic normalization.
  - Natural-language English/schema-key residue check after run found 0 issues.
  - Stock-attribute PE/PB valuation wording misuse check after run found 0 issues.
  - Channel trend hardening held: 0 Chinese free-text `L3.channel.mix.value.trend` values after run.
  - The batch did not require post-run natural-language cleanup; the batch 165 prompt/schema hardening held on the next live run.
  - Runner post-processing restored wrapped `scores.formula` in `300142.SZ`, `300204.SZ`, and `300244.SZ` (`formula_normalized=3`).
- Structural diff after run:
  - all 4 files changed only `L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`
  - Non-`nodes` YAML payload is unchanged for all 4 files
- Post-run cheap_extract dry-run:
  - all 4 completed stocks now show `nothing to fill (skip)` / `prompt_ready=0`
- Scoped closed-loop verifier:
  - full verifier output: `/tmp/domestic_closed_loop_after_batch166.json`
  - full hard violations: 0
  - full soft warnings: 12218
  - target-node violations filtered to the 24 batch dpids: 0
  - target-node evidence_quality type, old-key, English/schema-key residue, stock-attribute valuation-misuse, and channel-trend Chinese free-text check: 0 bad target nodes
  - target-file soft warnings: 16 historical non-target warnings only
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count=162086`
- Test gate after batch: `tests/test_apply_yaml_patch.py tests/test_prompt_gen_schema_block.py tests/test_prompt_gen_governance.py tests/test_schema_validator.py` passed, 90 tests
- Scope audit after batch: `fillable_total=109674`, `skipped_total=25298`, `cheap_extract=7176`
- Residual scope note: `INNOVATIVE_PHARMA` continues at `300357.SZ`, `300436.SZ`, `300573.SZ`, and `301301.SZ`.

## Completed batch 167

- Batch target: `INNOVATIVE_PHARMA`, A-share, `cheap_extract`
- Stocks completed: `300357.SZ`, `300436.SZ`, `300573.SZ`, `301301.SZ`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Parallel runner: `C1_INDUSTRY=INNOVATIVE_PHARMA`, `C1_PARALLEL=2`, via hardened `scripts/run_c1_fill.sh`
- Nodes handled: 24 cheap_extract targets
- Execution note:
  - All 4 child runs exited 0 and the hardened status summary reported `processed=4`, `skipped=0`, `prompt_failed=0`, `failed=0`.
  - `300357.SZ`, `300436.SZ`, `300573.SZ`, and `301301.SZ` each changed exactly the 6 target dpids.
  - All 4 stocks kept `L3.channel.mix` as `Unknown` because local materials did not directly disclose direct/distributor/ecommerce/other channel percentages.
  - `300573.SZ` had local text mentioning both distribution and direct-selling operating methods, but no channel share percentages, so the node stayed `Unknown` per the channel-mix evidence rule.
  - Natural-language English/schema-key residue check after run found 0 issues.
  - Stock-attribute PE/PB valuation wording misuse check after run found 0 issues.
  - Channel trend hardening held: 0 Chinese free-text `L3.channel.mix.value.trend` values after run.
  - The batch did not require post-run natural-language cleanup.
  - Runner post-processing restored wrapped `scores.formula` in `300357.SZ` and `301301.SZ` (`formula_normalized=2`).
- Structural diff after run:
  - all 4 files changed only `L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`
  - Non-`nodes` YAML payload is unchanged for all 4 files
- Post-run cheap_extract dry-run:
  - all 4 completed stocks now show `nothing to fill (skip)` / `prompt_ready=0`
- Scoped closed-loop verifier:
  - full verifier output: `/tmp/domestic_closed_loop_after_batch167.json`
  - full hard violations: 0
  - full soft warnings: 12218
  - target-node violations filtered to the 24 batch dpids: 0
  - target-node evidence_quality type, old-key, English/schema-key residue, stock-attribute valuation-misuse, and channel-trend Chinese free-text check: 0 bad target nodes
  - target-file soft warnings: 12 historical non-target warnings only
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count=162066`
- Test gate after batch: `tests/test_apply_yaml_patch.py tests/test_prompt_gen_schema_block.py tests/test_prompt_gen_governance.py tests/test_schema_validator.py` passed, 90 tests
- Scope audit after batch: `fillable_total=109650`, `skipped_total=25322`, `cheap_extract=7152`
- Residual scope note: `INNOVATIVE_PHARMA` continues at `600056.SH`, `600062.SH`, `600511.SH`, and `600763.SH`.

## Completed batch 168

- Batch target: `INNOVATIVE_PHARMA`, A-share, `cheap_extract`
- Stocks completed: `600056.SH`, `600062.SH`, `600511.SH`, `600763.SH`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Parallel runner: `C1_INDUSTRY=INNOVATIVE_PHARMA`, `C1_PARALLEL=2`, via hardened `scripts/run_c1_fill.sh`
- Nodes handled: 24 cheap_extract targets
- Execution note:
  - All 4 child runs exited 0 and the hardened status summary reported `processed=4`, `skipped=0`, `prompt_failed=0`, `failed=0`.
  - `600056.SH`, `600062.SH`, `600511.SH`, and `600763.SH` each changed exactly the 6 target dpids.
  - `600056.SH` and `600763.SH` kept `L3.channel.mix` as `Unknown` because local materials did not directly disclose channel percentages or sales-mode amount tables that can be mapped to the field.
  - `600062.SH` filled `L3.channel.mix` as Known after post-run supervision: the annual report disclosed a complete sales-mode amount table. Commercial distribution was mapped to distributor share, while terminal promotion, agency, and other modes were grouped into other share.
  - `600511.SH` filled `L3.channel.mix` as Known after post-run supervision: the annual report disclosed direct, distribution, industrial, and other sales-mode amounts. Direct and distribution mapped directly; industrial and other modes were grouped into other share; internal eliminations were not treated as a channel.
  - Natural-language English/schema-key residue check after cleanup found 0 issues.
  - Stock-attribute PE/PB valuation wording misuse check after cleanup found 0 issues.
  - Channel trend hardening held: 0 Chinese free-text `L3.channel.mix.value.trend` values after run.
  - Runner post-processing restored wrapped `scores.formula` in `600062.SH` (`formula_normalized=1`).
- Pipeline hardening from this batch:
  - `scripts/codex_prompt_gen.py` now tells GPT-5.5 that `L3.channel.mix` can be filled from a same-table annual-report sales-mode amount disclosure when the modes are directly mappable and the denominator can be checked.
  - The prompt now instructs that industrial/other non-standard sales modes belong in `others_pct`, while internal eliminations are not channels.
  - `tests/test_prompt_gen_schema_block.py` and `tests/test_prompt_gen_governance.py` cover the sales-mode amount calculation guidance.
- Structural diff after run:
  - all 4 files changed only `L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`
  - Non-`nodes` YAML payload is unchanged for all 4 files
- Post-run cheap_extract dry-run:
  - all 4 completed stocks now show `nothing to fill (skip)` / `prompt_ready=0`
- Scoped closed-loop verifier:
  - full verifier output: `/tmp/domestic_closed_loop_after_batch168.json`
  - full hard violations: 0
  - full soft warnings: 12218
  - target-node violations filtered to the 24 batch dpids: 0
  - target-node evidence_quality type, old-key, English/schema-key residue, stock-attribute valuation-misuse, and channel-trend Chinese free-text check: 0 bad target nodes
  - target-file soft warnings: 12 historical non-target warnings only
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count=162044`
- Test gate after batch: `tests/test_apply_yaml_patch.py tests/test_prompt_gen_schema_block.py tests/test_prompt_gen_governance.py tests/test_schema_validator.py` passed, 90 tests
- Scope audit after batch: `fillable_total=109626`, `skipped_total=25346`, `cheap_extract=7128`
- Residual scope note: `INNOVATIVE_PHARMA` continues at `600998.SH`, `603233.SH`, `603882.SH`, and `603939.SH`.

## Completed batch 169

- Batch target: `INNOVATIVE_PHARMA`, A-share, `cheap_extract`
- Stocks completed: `600998.SH`, `603233.SH`, `603882.SH`, `603939.SH`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Parallel runner: `C1_INDUSTRY=INNOVATIVE_PHARMA`, `C1_PARALLEL=2`, via hardened `scripts/run_c1_fill.sh`
- Nodes handled: 24 cheap_extract targets
- Execution note:
  - All 4 child runs exited 0 and the hardened status summary reported `processed=4`, `skipped=0`, `prompt_failed=0`, `failed=0`.
  - `600998.SH`, `603233.SH`, `603882.SH`, and `603939.SH` each changed exactly the 6 target dpids.
  - All 4 stocks kept `L3.channel.mix` as `Unknown` because local materials did not directly disclose direct/distributor/ecommerce/other channel percentages or a directly mappable sales-mode amount table.
  - For `603233.SH` and `603939.SH`, the local annual-report tables disclosed retail and franchise/distribution under business/industry structure rather than a dedicated sales-mode table, so the runner did not map those business rows into `direct_pct` or `distributor_pct`.
  - Natural-language English/schema-key residue check after run found 0 issues.
  - Stock-attribute PE/PB valuation wording misuse check after run found 0 issues.
  - Channel trend hardening held: 0 Chinese free-text `L3.channel.mix.value.trend` values after run.
  - The batch did not require post-run natural-language cleanup.
  - Runner post-processing restored wrapped `scores.formula` in `600998.SH`, `603882.SH`, and `603939.SH` (`formula_normalized=3`).
- Structural diff after run:
  - all 4 files changed only `L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`
  - Non-`nodes` YAML payload is unchanged for all 4 files
- Post-run cheap_extract dry-run:
  - all 4 completed stocks now show `nothing to fill (skip)` / `prompt_ready=0`
- Scoped closed-loop verifier:
  - full verifier output: `/tmp/domestic_closed_loop_after_batch169.json`
  - full hard violations: 0
  - full soft warnings: 12218
  - target-node violations filtered to the 24 batch dpids: 0
  - target-node evidence_quality type, old-key, English/schema-key residue, stock-attribute valuation-misuse, and channel-trend Chinese free-text check: 0 bad target nodes
  - target-file soft warnings: 12 historical non-target warnings only
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count=162024`
- Test gate after batch: `tests/test_apply_yaml_patch.py tests/test_prompt_gen_schema_block.py tests/test_prompt_gen_governance.py tests/test_schema_validator.py` passed, 90 tests
- Scope audit after batch: `fillable_total=109602`, `skipped_total=25370`, `cheap_extract=7104`
- Residual scope note: `INNOVATIVE_PHARMA` continues at `688114.SH`, `688192.SH`, `688278.SH`, and `688382.SH`.

## Completed batch 170

- Batch target: `INNOVATIVE_PHARMA`, A-share, `cheap_extract`
- Stocks completed: `688114.SH`, `688192.SH`, `688278.SH`, `688382.SH`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Parallel runner: `C1_INDUSTRY=INNOVATIVE_PHARMA`, `C1_PARALLEL=2`, via hardened `scripts/run_c1_fill.sh`
- Nodes handled: 24 cheap_extract targets
- Execution note:
  - All 4 child runs exited 0 and the hardened status summary reported `processed=4`, `skipped=0`, `prompt_failed=0`, `failed=0`.
  - `688114.SH`, `688192.SH`, `688278.SH`, and `688382.SH` each changed exactly the 6 target dpids.
  - `688278.SH` filled `L3.channel.mix` as Known because the annual report disclosed a same-table sales-mode amount structure with distributor and direct revenue that could be checked against total sales-mode revenue.
  - `688114.SH`, `688192.SH`, and `688382.SH` kept `L3.channel.mix` as `Unknown` because local materials did not directly disclose channel percentages or a directly mappable sales-mode amount table.
  - Natural-language English/schema-key residue check after run found 0 issues.
  - Stock-attribute PE/PB valuation wording misuse check after run found 0 issues.
  - Channel trend hardening held: 0 Chinese free-text `L3.channel.mix.value.trend` values after run.
  - The batch did not require post-run natural-language cleanup.
  - Runner post-processing restored wrapped `scores.formula` in `688192.SH` and `688278.SH` (`formula_normalized=2`).
- Structural diff after run:
  - all 4 files changed only `L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`
  - Non-`nodes` YAML payload is unchanged for all 4 files
- Post-run cheap_extract dry-run:
  - all 4 completed stocks now show `nothing to fill (skip)` / `prompt_ready=0`
- Scoped closed-loop verifier:
  - full verifier output: `/tmp/domestic_closed_loop_after_batch170.json`
  - full hard violations: 0
  - full soft warnings: 12218
  - target-node violations filtered to the 24 batch dpids: 0
  - target-node evidence_quality type, old-key, English/schema-key residue, stock-attribute valuation-misuse, and channel-trend Chinese free-text check: 0 bad target nodes
  - target-file soft warnings: 12 historical non-target warnings only
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count=162003`
- Test gate after batch: `tests/test_apply_yaml_patch.py tests/test_prompt_gen_schema_block.py tests/test_prompt_gen_governance.py tests/test_schema_validator.py` passed, 90 tests
- Scope audit after batch: `fillable_total=109578`, `skipped_total=25394`, `cheap_extract=7080`
- Residual scope note: `INNOVATIVE_PHARMA` continues at `688506.SH`, `688520.SH`, `688712.SH`, and `688759.SH`.

## Completed batch 171

- Batch target: `INNOVATIVE_PHARMA`, A-share, `cheap_extract`
- Stocks completed: `688506.SH`, `688520.SH`, `688712.SH`, `688759.SH`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Parallel runner: `C1_INDUSTRY=INNOVATIVE_PHARMA`, `C1_PARALLEL=2`, via hardened `scripts/run_c1_fill.sh`
- Nodes handled: 24 cheap_extract targets
- Execution note:
  - All 4 child runs exited 0 and the hardened status summary reported `processed=4`, `skipped=0`, `prompt_failed=0`, `failed=0`.
  - `688506.SH`, `688520.SH`, `688712.SH`, and `688759.SH` each changed exactly the 6 target dpids.
  - `688712.SH` filled `L3.channel.mix` as Known because the annual report disclosed a same-table sales-mode amount structure that could map distributor, direct, and other channels and be checked against total sales-mode revenue.
  - `688506.SH`, `688520.SH`, and `688759.SH` kept `L3.channel.mix` as `Unknown` because local materials did not directly disclose channel percentages or a directly mappable sales-mode amount table.
  - Natural-language English/schema-key residue check after run found 0 issues.
  - Stock-attribute PE/PB valuation wording misuse check after run found 0 issues.
  - Channel trend hardening held: 0 Chinese free-text `L3.channel.mix.value.trend` values after run.
  - The batch did not require post-run natural-language cleanup.
  - Runner post-processing restored wrapped `scores.formula` in `688520.SH`, `688712.SH`, and `688759.SH` (`formula_normalized=3`).
- Structural diff after run:
  - all 4 files changed only `L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`
  - Non-`nodes` YAML payload is unchanged for all 4 files
- Post-run cheap_extract dry-run:
  - all 4 completed stocks now show `nothing to fill (skip)` / `prompt_ready=0`
  - current `INNOVATIVE_PHARMA` cheap_extract list-only scope now shows `Fillable=0`, `Skipped=29`
- Scoped closed-loop verifier:
  - full verifier output: `/tmp/domestic_closed_loop_after_batch171.json`
  - full hard violations: 0
  - full soft warnings: 12218
  - target-node violations filtered to the 24 batch dpids: 0
  - target-node evidence_quality type, old-key, English/schema-key residue, stock-attribute valuation-misuse, and channel-trend Chinese free-text check: 0 bad target nodes
  - target-file soft warnings: 12 historical non-target warnings only
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count=161983`
- Test gate after batch: `tests/test_apply_yaml_patch.py tests/test_prompt_gen_schema_block.py tests/test_prompt_gen_governance.py tests/test_schema_validator.py` passed, 90 tests
- Scope audit after batch: `fillable_total=109554`, `skipped_total=25418`, `cheap_extract=7056`
- Residual scope note: `INNOVATIVE_PHARMA` cheap_extract is fully drained under the current prompt policy.

## Completed batch 172

- Batch target: `SEMI_EQUIPMENT`, A-share, `cheap_extract`
- Stocks completed: `688268.SH`, `600198.SH`, `600360.SH`, `600460.SH`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Parallel runner: `C1_INDUSTRY=SEMI_EQUIPMENT`, `C1_PARALLEL=2`, via hardened `scripts/run_c1_fill.sh`
- Nodes handled: 24 cheap_extract targets
- Execution note:
  - All 4 child runs exited 0 and the hardened status summary reported `processed=4`, `skipped=0`, `prompt_failed=0`, `failed=0`.
  - `688268.SH`, `600198.SH`, `600360.SH`, and `600460.SH` each changed exactly the 6 target dpids.
  - All 4 stocks kept `L3.channel.mix` as `Unknown` because the local disclosures covered主营业务、客户、业务线或地区收入结构, but did not directly disclose channel percentages or a directly mappable sales-mode amount table.
  - Natural-language English/schema-key residue check after run found 0 issues.
  - Stock-attribute PE/PB valuation wording misuse check after run found 0 issues.
  - Channel trend hardening held: 0 Chinese free-text `L3.channel.mix.value.trend` values after run.
  - The batch did not require post-run natural-language cleanup.
  - Runner post-processing restored wrapped `scores.formula` in `688268.SH` (`formula_normalized=1`).
- Structural diff after run:
  - all 4 files changed only `L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`
  - Non-`nodes` YAML payload is unchanged for all 4 files
- Post-run cheap_extract dry-run:
  - all 4 completed stocks now show `nothing to fill (skip)` / `prompt_ready=0`
- Scoped closed-loop verifier:
  - full verifier output: `/tmp/domestic_closed_loop_after_batch172.json`
  - full hard violations: 0
  - full soft warnings: 12218
  - target-node violations filtered to the 24 batch dpids: 0
  - target-node evidence_quality type, old-key, English/schema-key residue, stock-attribute valuation-misuse, and channel-trend Chinese free-text check: 0 bad target nodes
  - target-file soft warnings: 9 historical non-target warnings only
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count=161963`
- Test gate after batch: `tests/test_apply_yaml_patch.py tests/test_prompt_gen_schema_block.py tests/test_prompt_gen_governance.py tests/test_schema_validator.py` passed, 90 tests
- Scope audit after batch: `fillable_total=109530`, `skipped_total=25442`, `cheap_extract=7032`
- Residual scope note: next global cheap_extract candidates include `STORAGE_GRID/001393.SZ`, `STORAGE_GRID/301599.SZ`, `CONSUMER_ELECTRONICS/600353.SH`, and `EXPORT_MFG/600151.SH`.

## Completed batch 173

- Batch target: `STORAGE_GRID`, A-share, `cheap_extract`
- Stocks completed: `001393.SZ`, `301599.SZ`, `002169.SZ`, `002498.SZ`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Parallel runner: `C1_INDUSTRY=STORAGE_GRID`, `C1_PARALLEL=2`, via hardened `scripts/run_c1_fill.sh`
- Nodes handled: 24 cheap_extract targets
- Execution note:
  - All 4 child runs exited 0 and the hardened status summary reported `processed=4`, `skipped=0`, `prompt_failed=0`, `failed=0`.
  - `001393.SZ`, `301599.SZ`, `002169.SZ`, and `002498.SZ` each changed exactly the 6 target dpids.
  - `002169.SZ` filled `L3.channel.mix` as Known because the annual report sales-mode table directly disclosed all sales as direct sales.
  - `002498.SZ` filled `L3.channel.mix` as Known because the 2025 annual report directly disclosed direct-sales and distributor-sales percentages by sales mode.
  - `001393.SZ` and `301599.SZ` kept `L3.channel.mix` as `Unknown` because local materials did not directly disclose channel percentages or a directly mappable sales-mode amount table.
  - Natural-language English/schema-key residue check after run found 0 issues.
  - Stock-attribute PE/PB valuation wording misuse check after run found 0 issues.
  - Channel trend hardening held: 0 Chinese free-text `L3.channel.mix.value.trend` values after run.
  - The batch did not require post-run natural-language cleanup.
  - Runner post-processing restored wrapped `scores.formula` in `301599.SZ`, `002169.SZ`, and `002498.SZ` (`formula_normalized=3`).
- Structural diff after run:
  - all 4 files changed only `L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`
  - Non-`nodes` YAML payload is unchanged for all 4 files
- Post-run cheap_extract dry-run:
  - all 4 completed stocks now show `nothing to fill (skip)` / `prompt_ready=0`
- Scoped closed-loop verifier:
  - full verifier output: `/tmp/domestic_closed_loop_after_batch173.json`
  - full hard violations: 0
  - full soft warnings: 12218
  - target-node violations filtered to the 24 batch dpids: 0
  - target-node evidence_quality type, old-key, English/schema-key residue, stock-attribute valuation-misuse, and channel-trend Chinese free-text check: 0 bad target nodes
  - target-file soft warnings: 6 historical non-target warnings only
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count=161941`
- Test gate after batch: `tests/test_apply_yaml_patch.py tests/test_prompt_gen_schema_block.py tests/test_prompt_gen_governance.py tests/test_schema_validator.py` passed, 90 tests
- Scope audit after batch: `fillable_total=109506`, `skipped_total=25466`, `cheap_extract=7008`
- Residual scope note: next global cheap_extract candidates include `CONSUMER_ELECTRONICS/600353.SH`, `EXPORT_MFG/600151.SH`, `EXPORT_MFG/600480.SH`, and `EXPORT_MFG/603950.SH`.

## Completed batch 174

- Batch target: `ROBOTICS`, A-share, `cheap_extract`
- Stocks completed: `300276.SZ`, `300480.SZ`, `600343.SH`, `600582.SH`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Parallel runner: `C1_INDUSTRY=ROBOTICS`, `C1_PARALLEL=2`, via hardened `scripts/run_c1_fill.sh`
- Nodes handled: 24 cheap_extract targets
- Execution note:
  - All 4 child runs exited 0 and the hardened status summary reported `processed=4`, `skipped=0`, `prompt_failed=0`, `failed=0`.
  - `300276.SZ`, `300480.SZ`, `600343.SH`, and `600582.SH` each changed exactly the 6 target dpids.
  - All 4 stocks kept `L3.channel.mix` as `Unknown` because local materials did not directly disclose channel percentages or a directly mappable sales-mode amount table.
  - `300480.SZ` initially retained a qualitative `value.trend=direct_sales_dominant` while all channel percentages were null; this was normalized to `trend: null` and converted into a prompt/validator hardening rule after review.
  - Natural-language English/schema-key residue check after run found 0 issues.
  - Stock-attribute PE/PB valuation wording misuse check after run found 0 issues.
  - Channel trend hardening held: 0 Chinese free-text `L3.channel.mix.value.trend` values after run.
  - The batch did not require post-run natural-language cleanup.
  - Runner post-processing restored wrapped `scores.formula` in `300480.SZ` and `600582.SH` (`formula_normalized=2`).
- Structural diff after run:
  - all 4 files changed only `L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`
  - Non-`nodes` YAML payload is unchanged for all 4 files
- Post-run cheap_extract dry-run:
  - all 4 completed stocks now show `nothing to fill (skip)` / `prompt_ready=0`
- Scoped closed-loop verifier:
  - full verifier output after hardening: `/tmp/domestic_closed_loop_after_batch174_hardened.json`
  - full hard violations: 0
  - full soft warnings: 12253
  - target-node violations filtered to the 24 batch dpids: 0
  - target-node evidence_quality type, old-key, English/schema-key residue, stock-attribute valuation-misuse, channel-trend Chinese free-text, and all-null channel-trend check: 0 bad target nodes
  - target-file soft warnings: 12 historical non-target warnings only
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count=161921`
- Test gate after batch: `tests/test_apply_yaml_patch.py tests/test_prompt_gen_schema_block.py tests/test_prompt_gen_governance.py tests/test_schema_validator.py` passed, 91 tests
- Scope audit after batch: `fillable_total=109482`, `skipped_total=25490`, `cheap_extract=6984`
- Residual scope note: next global cheap_extract candidates include `CONSUMER_ELECTRONICS/600353.SH`, `EXPORT_MFG/600151.SH`, `EXPORT_MFG/600480.SH`, and `EXPORT_MFG/603950.SH`.

## Pipeline hardening after batch 174

- Issue found during supervision: one accepted `L3.channel.mix` output kept all four channel percentage fields null but still wrote a qualitative short-enum `value.trend=direct_sales_dominant`.
- Fix applied:
  - `scripts/codex_prompt_gen.py` now tells the LLM that if `direct_pct`, `distributor_pct`, `ecommerce_pct`, and `others_pct` are all `null`, or the node remains Unknown, then `value.trend` must also be `null`; qualitative "direct-sales-dominant" wording belongs in `notes`.
  - `mvp20/schema_validator.py` now emits a warning when `L3.channel.mix.value.trend` is non-null while all four channel percentage fields are null.
  - `config/stock_overlays/ROBOTICS/300480.SZ.yaml` was normalized so the accepted Unknown channel node has `trend: null`.
- Verification:
  - `tests/test_prompt_gen_schema_block.py tests/test_prompt_gen_governance.py tests/test_schema_validator.py` passed, 88 tests.
  - Re-running the batch174 target-node content check found 0 bad target nodes after normalization.
  - Full verifier after hardening kept hard violations at 0; the new validator surfaced 35 additional historical soft warnings outside the batch174 target nodes.

## Completed batch 175

- Batch target: `ROBOTICS`, A-share, `cheap_extract`
- Stocks completed: `603025.SH`, `603698.SH`, `688188.SH`, `688596.SH`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Parallel runner: `C1_INDUSTRY=ROBOTICS`, `C1_PARALLEL=2`, via hardened `scripts/run_c1_fill.sh`
- Nodes handled: 24 cheap_extract targets
- Execution note:
  - All 4 child runs exited 0 and the hardened status summary reported `processed=4`, `skipped=0`, `prompt_failed=0`, `failed=0`.
  - `603025.SH`, `603698.SH`, `688188.SH`, and `688596.SH` each changed exactly the 6 target dpids.
  - `603025.SH`, `603698.SH`, and `688188.SH` filled `L3.channel.mix` as Known because the annual report sales-mode table directly disclosed only direct sales and the direct-sales amount matched the disclosed sales-mode total.
  - `688596.SH` kept `L3.channel.mix` as `Unknown` because local materials did not directly disclose channel percentages or a directly mappable sales-mode amount table.
  - Natural-language English/schema-key residue check after run found 0 issues.
  - Stock-attribute PE/PB valuation wording misuse check after run found 0 issues.
  - Channel trend hardening held: 0 Chinese free-text `L3.channel.mix.value.trend` values after run.
  - All-null channel trend hardening held: 0 non-null `trend` values when all four channel percentage fields are null.
  - The batch did not require post-run natural-language cleanup.
  - Runner post-processing restored wrapped `scores.formula` in `688188.SH` and `688596.SH` (`formula_normalized=2`).
- Structural diff after run:
  - all 4 files changed only `L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`
  - Non-`nodes` YAML payload is unchanged for all 4 files
- Post-run cheap_extract dry-run:
  - all 4 completed stocks now show `nothing to fill (skip)` / `prompt_ready=0`
- Scoped closed-loop verifier:
  - full verifier output: `/tmp/domestic_closed_loop_after_batch175.json`
  - full hard violations: 0
  - full soft warnings: 12253
  - target-node violations filtered to the 24 batch dpids: 0
  - target-node evidence_quality type, old-key, English/schema-key residue, stock-attribute valuation-misuse, channel-trend Chinese free-text, and all-null channel-trend check: 0 bad target nodes
  - target-file soft warnings: 12 historical non-target warnings only
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count=161898`
- Test gate after batch: `tests/test_apply_yaml_patch.py tests/test_prompt_gen_schema_block.py tests/test_prompt_gen_governance.py tests/test_schema_validator.py` passed, 91 tests
- Scope audit after batch: `fillable_total=109458`, `skipped_total=25514`, `cheap_extract=6960`
- Residual scope note: next global cheap_extract candidates include `CONSUMER_ELECTRONICS/600353.SH`, `EXPORT_MFG/600151.SH`, `EXPORT_MFG/600480.SH`, and `EXPORT_MFG/603950.SH`.

## Completed batch 176

- Batch target: `SEMI_EQUIPMENT`, A-share, `cheap_extract`
- Stocks completed: `600641.SH`, `603078.SH`, `603290.SH`, `688047.SH`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Parallel runner: `C1_INDUSTRY=SEMI_EQUIPMENT`, `C1_PARALLEL=2`, via hardened `scripts/run_c1_fill.sh`
- Nodes handled: 24 cheap_extract targets
- Execution note:
  - All 4 child runs exited 0 and the hardened status summary reported `processed=4`, `skipped=0`, `prompt_failed=0`, `failed=0`.
  - `600641.SH`, `603078.SH`, `603290.SH`, and `688047.SH` each changed exactly the 6 target dpids.
  - `603290.SH` and `688047.SH` filled `L3.channel.mix` as Known because the annual report sales-mode table directly disclosed direct and distributor sales amounts with a checkable table total.
  - `600641.SH` and `603078.SH` kept `L3.channel.mix` as `Unknown` because local materials did not directly disclose channel percentages or a directly mappable sales-mode amount table.
  - Natural-language English/schema-key residue check after run found 0 issues.
  - Stock-attribute PE/PB valuation wording misuse check after run found 0 issues.
  - Channel trend hardening held: 0 Chinese free-text `L3.channel.mix.value.trend` values after run.
  - All-null channel trend hardening held: 0 non-null `trend` values when all four channel percentage fields are null.
  - The batch did not require post-run natural-language cleanup.
  - Runner post-processing restored wrapped `scores.formula` in `603078.SH`, `603290.SH`, and `688047.SH` (`formula_normalized=3`).
- Structural diff after run:
  - all 4 files changed only `L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`
  - Non-`nodes` YAML payload is unchanged for all 4 files
- Post-run cheap_extract dry-run:
  - all 4 completed stocks now show `nothing to fill (skip)` / `prompt_ready=0`
- Scoped closed-loop verifier:
  - full verifier output: `/tmp/domestic_closed_loop_after_batch176.json`
  - full hard violations: 0
  - full soft warnings: 12253
  - target-node violations filtered to the 24 batch dpids: 0
  - target-node evidence_quality type, old-key, English/schema-key residue, stock-attribute valuation-misuse, channel-trend Chinese free-text, and all-null channel-trend check: 0 bad target nodes
  - target-file soft warnings: 12 historical non-target warnings only
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count=161876`
- Test gate after batch: `tests/test_apply_yaml_patch.py tests/test_prompt_gen_schema_block.py tests/test_prompt_gen_governance.py tests/test_schema_validator.py` passed, 91 tests
- Scope audit after batch: `fillable_total=109434`, `skipped_total=25538`, `cheap_extract=6936`
- Residual scope note: next global cheap_extract candidates include `CONSUMER_ELECTRONICS/600353.SH`, `EXPORT_MFG/600151.SH`, `EXPORT_MFG/600480.SH`, and `EXPORT_MFG/603950.SH`.

## Completed batch 177

- Batch target: `CONSUMER_ELECTRONICS`, A-share, `cheap_extract`
- Stocks completed: `600353.SH`, `301031.SZ`, `603459.SH`, `688781.SH`, `920438.BJ`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Parallel runner: `C1_INDUSTRY=CONSUMER_ELECTRONICS`, `C1_PARALLEL=2`, via hardened `scripts/run_c1_fill.sh`
- Nodes handled: 30 cheap_extract targets
- Execution note:
  - All 5 child runs exited 0 and the hardened status summary reported `processed=5`, `skipped=0`, `prompt_failed=0`, `failed=0`.
  - `600353.SH`, `301031.SZ`, `603459.SH`, `688781.SH`, and `920438.BJ` each changed exactly the 6 target dpids.
  - `600353.SH` filled `L3.channel.mix` as Known because the annual report sales-mode table disclosed only direct sales and the direct-sales amount matched the disclosed total.
  - `301031.SZ` filled `L3.channel.mix` as Known because the 2025 annual report directly disclosed direct-customer and distributor-customer percentages summing to 100%.
  - `603459.SH`, `688781.SH`, and `920438.BJ` kept `L3.channel.mix` as `Unknown` because local materials did not directly disclose channel percentages or a directly mappable sales-mode amount table.
  - Natural-language English/schema-key residue check after run found 0 issues.
  - Stock-attribute PE/PB valuation wording misuse check after run found 0 issues.
  - Channel trend hardening held: 0 Chinese free-text `L3.channel.mix.value.trend` values after run.
  - All-null channel trend hardening held: 0 non-null `trend` values when all four channel percentage fields are null.
  - The batch did not require post-run natural-language cleanup.
  - Runner post-processing restored wrapped `scores.formula` in `301031.SZ`, `603459.SH`, and `688781.SH` (`formula_normalized=3`).
- Structural diff after run:
  - all 5 files changed only `L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`
  - Non-`nodes` YAML payload is unchanged for all 5 files
- Post-run cheap_extract dry-run:
  - all 5 completed stocks now show `nothing to fill (skip)` / `prompt_ready=0`
- Scoped closed-loop verifier:
  - full verifier output: `/tmp/domestic_closed_loop_after_batch177.json`
  - full hard violations: 0
  - full soft warnings: 12253
  - target-node violations filtered to the 30 batch dpids: 0
  - target-node evidence_quality type, old-key, English/schema-key residue, stock-attribute valuation-misuse, channel-trend Chinese free-text, and all-null channel-trend check: 0 bad target nodes
  - target-file soft warnings: 9 historical non-target warnings only
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count=161849`
- Test gate after batch: `tests/test_apply_yaml_patch.py tests/test_prompt_gen_schema_block.py tests/test_prompt_gen_governance.py tests/test_schema_validator.py` passed, 91 tests
- Scope audit after batch: `fillable_total=109404`, `skipped_total=25568`, `cheap_extract=6906`
- Residual scope note: next global cheap_extract candidates include `EXPORT_MFG/600151.SH`, `EXPORT_MFG/600480.SH`, `EXPORT_MFG/603950.SH`, and `INNOVATIVE_PHARMA/688796.SH`.

## Completed batch 178

- Batch target: `EXPORT_MFG`, A-share, `cheap_extract`
- Stocks completed: `600151.SH`, `600480.SH`, `603950.SH`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Parallel runner: `C1_INDUSTRY=EXPORT_MFG`, `C1_PARALLEL=2`, via hardened `scripts/run_c1_fill.sh`
- Nodes handled: 18 cheap_extract targets
- Execution note:
  - All 3 child runs exited 0 and the hardened status summary reported `processed=3`, `skipped=0`, `prompt_failed=0`, `failed=0`.
  - `600151.SH`, `600480.SH`, and `603950.SH` each changed exactly the 6 target dpids.
  - `600480.SH` filled `L3.channel.mix` as Known because the 2025 annual report sales-mode table disclosed only direct sales and the direct-sales amount matched the disclosed total.
  - `600151.SH` and `603950.SH` kept `L3.channel.mix` as `Unknown` because local materials did not directly disclose channel percentages or a directly mappable sales-mode amount table.
  - Natural-language English/schema-key residue check after run found 0 issues.
  - Stock-attribute PE/PB valuation wording misuse check after run found 0 issues.
  - Channel trend hardening held: 0 Chinese free-text `L3.channel.mix.value.trend` values after run.
  - All-null channel trend hardening held: 0 non-null `trend` values when all four channel percentage fields are null.
  - The batch did not require post-run natural-language cleanup.
  - Runner post-processing restored wrapped `scores.formula` in `600151.SH`, `600480.SH`, and `603950.SH` (`formula_normalized=3`).
- Structural diff after run:
  - all 3 files changed only `L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`
  - Non-`nodes` YAML payload is unchanged for all 3 files
- Post-run cheap_extract dry-run:
  - all 3 completed stocks now show `nothing to fill (skip)` / `prompt_ready=0`
- Scoped closed-loop verifier:
  - full verifier output: `/tmp/domestic_closed_loop_after_batch178.json`
  - full hard violations: 0
  - full soft warnings: 12253
  - target-node violations filtered to the 18 batch dpids: 0
  - target-node evidence_quality type, old-key, English/schema-key residue, stock-attribute valuation-misuse, channel-trend Chinese free-text, and all-null channel-trend check: 0 bad target nodes
  - target-file soft warnings: 9 historical non-target warnings only
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count=161833`
- Test gate after batch: `tests/test_apply_yaml_patch.py tests/test_prompt_gen_schema_block.py tests/test_prompt_gen_governance.py tests/test_schema_validator.py` passed, 91 tests
- Scope audit after batch: `fillable_total=109386`, `skipped_total=25586`, `cheap_extract=6888`
- Residual scope note: next global cheap_extract candidates include `INNOVATIVE_PHARMA/688796.SH`, `SEMI_EQUIPMENT/688106.SH`, `SEMI_EQUIPMENT/688110.SH`, and `SEMI_EQUIPMENT/688262.SH`.

## Completed batch 179

- Batch target: `SEMI_EQUIPMENT`, A-share, `cheap_extract`
- Stocks completed: `688106.SH`, `688110.SH`, `688262.SH`, `688270.SH`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Parallel runner: `C1_INDUSTRY=SEMI_EQUIPMENT`, `C1_PARALLEL=2`, via hardened `scripts/run_c1_fill.sh`
- Nodes handled: 24 cheap_extract targets
- Execution note:
  - All 4 child runs exited 0 and the hardened status summary reported `processed=4`, `skipped=0`, `prompt_failed=0`, `failed=0`.
  - `688106.SH`, `688110.SH`, `688262.SH`, and `688270.SH` each changed exactly the 6 target dpids.
  - `688262.SH` filled `L3.channel.mix` as Known because the annual report sales-mode table directly disclosed direct and distributor sales amounts with a checkable table total.
  - `688106.SH`, `688110.SH`, and `688270.SH` kept `L3.channel.mix` as `Unknown` because local materials did not directly disclose channel percentages or a directly mappable sales-mode amount table.
  - Post-verifier review found one target-node excerpt warning in `688106.SH:L1.model.tag`; `L1.model.tag` and same-file `L1.moat.tags` were tightened to cite only the exact `L1.company.main_business` text that the verifier can match.
  - Natural-language English/schema-key residue check after run found 0 issues.
  - Stock-attribute PE/PB valuation wording misuse check after run found 0 issues.
  - Channel trend hardening held: 0 Chinese free-text `L3.channel.mix.value.trend` values after run.
  - All-null channel trend hardening held: 0 non-null `trend` values when all four channel percentage fields are null.
  - The batch did not require post-run natural-language cleanup.
  - Runner post-processing restored wrapped `scores.formula` in `688110.SH`, `688262.SH`, and `688270.SH` (`formula_normalized=3`).
- Structural diff after run:
  - all 4 files changed only `L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`
  - Non-`nodes` YAML payload is unchanged for all 4 files
- Post-run cheap_extract dry-run:
  - all 4 completed stocks now show `nothing to fill (skip)` / `prompt_ready=0`
- Scoped closed-loop verifier:
  - full verifier output after excerpt fix: `/tmp/domestic_closed_loop_after_batch179_fixed.json`
  - full hard violations: 0
  - full soft warnings: 12253
  - target-node violations filtered to the 24 batch dpids: 0
  - target-node evidence_quality type, old-key, English/schema-key residue, stock-attribute valuation-misuse, channel-trend Chinese free-text, all-null channel-trend, and excerpt check: 0 bad target nodes
  - target-file soft warnings: 12 historical non-target warnings only
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count=161812`
- Test gate after batch: `tests/test_apply_yaml_patch.py tests/test_prompt_gen_schema_block.py tests/test_prompt_gen_governance.py tests/test_schema_validator.py` passed, 91 tests
- Scope audit after batch: `fillable_total=109362`, `skipped_total=25610`, `cheap_extract=6864`
- Residual scope note: next global cheap_extract candidates include `INNOVATIVE_PHARMA/688796.SH`, `SEMI_EQUIPMENT/688380.SH`, `SEMI_EQUIPMENT/688548.SH`, and `SEMI_EQUIPMENT/688582.SH`.

## Completed batch 180

- Batch target: `SEMI_EQUIPMENT`, A-share, `cheap_extract`
- Stocks completed: `688380.SH`, `688548.SH`, `688582.SH`, `688709.SH`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Parallel runner: `C1_INDUSTRY=SEMI_EQUIPMENT`, `C1_PARALLEL=2`, via hardened `scripts/run_c1_fill.sh`
- Nodes handled: 24 cheap_extract targets
- Execution note:
  - All 4 child runs exited 0 and the hardened status summary reported `processed=4`, `skipped=0`, `prompt_failed=0`, `failed=0`.
  - `688380.SH`, `688548.SH`, `688582.SH`, and `688709.SH` each changed exactly the 6 target dpids.
  - `688380.SH` filled `L3.channel.mix` as Known because the annual report sales-mode table directly disclosed distributor and direct sales amounts with a checkable denominator.
  - `688709.SH` filled `L3.channel.mix` as Known because the sales-mode table only listed direct sales and no distributor, ecommerce, or other mode.
  - `688548.SH` kept `L3.channel.mix` as `Unknown` because onsite gas supply and retail gas customer categories were not directly mappable to direct, distributor, ecommerce, or other channel percentages.
  - `688582.SH` kept `L3.channel.mix` as `Unknown` because local materials did not directly disclose channel percentages or a directly mappable sales-mode amount table.
  - Natural-language English/schema-key residue check after run found 0 issues.
  - Stock-attribute PE/PB valuation wording misuse check after run found 0 issues.
  - Channel trend hardening held: 0 Chinese free-text `L3.channel.mix.value.trend` values after run.
  - All-null channel trend hardening held: 0 non-null `trend` values when all four channel percentage fields are null.
  - The batch did not require post-run cleanup.
  - Runner post-processing reported `formula_normalized=0`.
- Structural diff after run:
  - all 4 files changed only `L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`
  - Non-`nodes` YAML payload is unchanged for all 4 files
- Post-run cheap_extract dry-run:
  - all 4 completed stocks now show `nothing to fill (skip)` / `prompt_ready=0`
- Scoped closed-loop verifier:
  - full verifier output: `/tmp/domestic_closed_loop_after_batch180.json`
  - full hard violations: 0
  - full soft warnings: 12253
  - target-node violations filtered to the 24 batch dpids: 0
  - target-node evidence_quality type, old-key, English/schema-key residue, stock-attribute valuation-misuse, channel-trend Chinese free-text, all-null channel-trend, and excerpt check: 0 bad target nodes
  - target-file soft warnings: 12 historical non-target warnings only
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count=161790`
- Test gate after batch: `tests/test_apply_yaml_patch.py tests/test_prompt_gen_schema_block.py tests/test_prompt_gen_governance.py tests/test_schema_validator.py` passed, 91 tests
- Scope audit after batch: `fillable_total=109338`, `skipped_total=25634`, `cheap_extract=6840`
- Residual scope note: next global cheap_extract candidates include `INNOVATIVE_PHARMA/688796.SH`, `SEMI_EQUIPMENT/688727.SH`, `STORAGE_GRID/300769.SZ`, and `STORAGE_GRID/600268.SH`.

## Completed batch 181

- Batch target: `STORAGE_GRID`, A-share, `cheap_extract`
- Stocks completed: `300769.SZ`, `600268.SH`, `600973.SH`, `603092.SH`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Parallel runner: `C1_INDUSTRY=STORAGE_GRID`, `C1_PARALLEL=2`, via hardened `scripts/run_c1_fill.sh`
- Nodes handled: 24 cheap_extract targets
- Execution note:
  - All 4 child runs exited 0 and the hardened status summary reported `processed=4`, `skipped=0`, `prompt_failed=0`, `failed=0`.
  - `300769.SZ`, `600268.SH`, `600973.SH`, and `603092.SH` each changed exactly the 6 target dpids.
  - `600268.SH` filled `L3.channel.mix` as Known because the 2025 annual-report sales-mode table only listed direct sales and provided the full sales-mode revenue amount.
  - `300769.SZ`, `600973.SH`, and `603092.SH` kept `L3.channel.mix` as `Unknown` because local materials did not directly disclose channel percentages or a directly mappable sales-mode amount table.
  - Natural-language English/schema-key residue check after run found 0 issues.
  - Stock-attribute PE/PB valuation wording misuse check after run found 0 issues.
  - Channel trend hardening held: 0 Chinese free-text `L3.channel.mix.value.trend` values after run.
  - All-null channel trend hardening held: 0 non-null `trend` values when all four channel percentage fields are null.
  - The batch did not require post-run cleanup.
  - Runner post-processing restored wrapped `scores.formula` in `300769.SZ` and `600268.SH` (`formula_normalized=2`).
- Structural diff after run:
  - all 4 files changed only `L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`
  - Non-`nodes` YAML payload is unchanged for all 4 files
- Post-run cheap_extract dry-run:
  - all 4 completed stocks now show `nothing to fill (skip)` / `prompt_ready=0`
- Scoped closed-loop verifier:
  - full verifier output: `/tmp/domestic_closed_loop_after_batch181.json`
  - full hard violations: 0
  - full soft warnings: 12253
  - target-node violations filtered to the 24 batch dpids: 0
  - target-node evidence_quality type, old-key, English/schema-key residue, stock-attribute valuation-misuse, channel-trend Chinese free-text, all-null channel-trend, and excerpt check: 0 bad target nodes
  - target-file soft warnings: 12 historical non-target warnings only
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count=161769`
- Test gate after batch: `tests/test_apply_yaml_patch.py tests/test_prompt_gen_schema_block.py tests/test_prompt_gen_governance.py tests/test_schema_validator.py` passed, 91 tests
- Scope audit after batch: `fillable_total=109314`, `skipped_total=25658`, `cheap_extract=6816`
- Residual scope note: next global cheap_extract candidates include `INNOVATIVE_PHARMA/688796.SH`, `SEMI_EQUIPMENT/688727.SH`, `STORAGE_GRID/603248.SH`, and `STORAGE_GRID/603778.SH`.

## Completed batch 182

- Batch target: `STORAGE_GRID`, A-share, `cheap_extract`
- Stocks completed: `603248.SH`, `603778.SH`, `603906.SH`, `688303.SH`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Parallel runner: `C1_INDUSTRY=STORAGE_GRID`, `C1_PARALLEL=2`, via hardened `scripts/run_c1_fill.sh`
- Nodes handled: 24 cheap_extract targets
- Execution note:
  - All 4 child runs exited 0 and the hardened status summary reported `processed=4`, `skipped=0`, `prompt_failed=0`, `failed=0`.
  - `603248.SH`, `603778.SH`, `603906.SH`, and `688303.SH` each changed exactly the 6 target dpids.
  - `603248.SH` filled `L3.channel.mix` as Known because the annual-report sales-mode table directly disclosed direct sales as the full sales-mode revenue.
  - `603778.SH`, `603906.SH`, and `688303.SH` kept `L3.channel.mix` as `Unknown` because local materials did not directly disclose channel percentages or a directly mappable sales-mode amount table.
  - Natural-language English/schema-key residue check after run found 0 issues.
  - Stock-attribute PE/PB valuation wording misuse check after run found 0 issues.
  - Channel trend hardening held: 0 Chinese free-text `L3.channel.mix.value.trend` values after run.
  - All-null channel trend hardening held: 0 non-null `trend` values when all four channel percentage fields are null.
  - The batch did not require post-run cleanup.
  - Runner post-processing restored wrapped `scores.formula` in `603248.SH`, `603906.SH`, and `688303.SH` (`formula_normalized=3`).
- Structural diff after run:
  - all 4 files changed only `L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`
  - Non-`nodes` YAML payload is unchanged for all 4 files
- Post-run cheap_extract dry-run:
  - all 4 completed stocks now show `nothing to fill (skip)` / `prompt_ready=0`
- Scoped closed-loop verifier:
  - full verifier output: `/tmp/domestic_closed_loop_after_batch182.json`
  - full hard violations: 0
  - full soft warnings: 12253
  - target-node violations filtered to the 24 batch dpids: 0
  - target-node evidence_quality type, old-key, English/schema-key residue, stock-attribute valuation-misuse, channel-trend Chinese free-text, all-null channel-trend, and excerpt check: 0 bad target nodes
  - target-file soft warnings: 12 historical non-target warnings only
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count=161748`
- Test gate after batch: `tests/test_apply_yaml_patch.py tests/test_prompt_gen_schema_block.py tests/test_prompt_gen_governance.py tests/test_schema_validator.py` passed, 91 tests
- Scope audit after batch: `fillable_total=109290`, `skipped_total=25682`, `cheap_extract=6792`
- Residual scope note: next global cheap_extract candidates include `INNOVATIVE_PHARMA/688796.SH`, `SEMI_EQUIPMENT/688727.SH`, `STORAGE_GRID/688388.SH`, and `STORAGE_GRID/688611.SH`.

## Completed batch 183

- Batch target: `STORAGE_GRID`, A-share, `cheap_extract`
- Stocks completed: `688388.SH`, `688611.SH`, `688660.SH`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Parallel runner: `C1_INDUSTRY=STORAGE_GRID`, `C1_PARALLEL=2`, via hardened `scripts/run_c1_fill.sh`
- Nodes handled: 18 cheap_extract targets
- Execution note:
  - All 3 child runs exited 0 and the hardened status summary reported `processed=3`, `skipped=0`, `prompt_failed=0`, `failed=0`.
  - `688388.SH`, `688611.SH`, and `688660.SH` each changed exactly the 6 target dpids.
  - `688388.SH` filled `L3.channel.mix` as Known because the annual-report sales-mode table directly disclosed direct, distributor, and other sales-mode amounts with a checkable denominator.
  - `688660.SH` filled `L3.channel.mix` as Known because the annual-report sales-mode table showed direct sales equal to total sales-mode revenue.
  - `688611.SH` kept `L3.channel.mix` as `Unknown` because local materials did not directly disclose channel percentages or a directly mappable sales-mode amount table.
  - Natural-language English/schema-key residue check after run found 0 issues.
  - Stock-attribute PE/PB valuation wording misuse check after run found 0 issues.
  - Channel trend hardening held: 0 Chinese free-text `L3.channel.mix.value.trend` values after run.
  - All-null channel trend hardening held: 0 non-null `trend` values when all four channel percentage fields are null.
  - The batch did not require post-run cleanup.
  - Runner post-processing restored wrapped `scores.formula` in `688388.SH` (`formula_normalized=1`).
- Structural diff after run:
  - all 3 files changed only `L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`
  - Non-`nodes` YAML payload is unchanged for all 3 files
- Post-run cheap_extract dry-run:
  - all 3 completed stocks now show `nothing to fill (skip)` / `prompt_ready=0`
- Scoped closed-loop verifier:
  - full verifier output: `/tmp/domestic_closed_loop_after_batch183.json`
  - full hard violations: 0
  - full soft warnings: 12253
  - target-node violations filtered to the 18 batch dpids: 0
  - target-node evidence_quality type, old-key, English/schema-key residue, stock-attribute valuation-misuse, channel-trend Chinese free-text, all-null channel-trend, and excerpt check: 0 bad target nodes
  - target-file soft warnings: 9 historical non-target warnings only
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count=161731`
- Test gate after batch: `tests/test_apply_yaml_patch.py tests/test_prompt_gen_schema_block.py tests/test_prompt_gen_governance.py tests/test_schema_validator.py` passed, 91 tests
- Scope audit after batch: `fillable_total=109272`, `skipped_total=25700`, `cheap_extract=6774`
- Residual scope note: next global cheap_extract candidates include `INNOVATIVE_PHARMA/688796.SH`, `SEMI_EQUIPMENT/688727.SH`, `ANTI_INVOLUTION_CYCLICAL/000420.SZ`, and `ANTI_INVOLUTION_CYCLICAL/000898.SZ`.

## Completed batch 184

- Batch target: `ANTI_INVOLUTION_CYCLICAL`, A-share, `cheap_extract`
- Stocks completed: `000420.SZ`, `000898.SZ`, `000902.SZ`, `000973.SZ`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Parallel runner: `C1_INDUSTRY=ANTI_INVOLUTION_CYCLICAL`, `C1_PARALLEL=2`, via hardened `scripts/run_c1_fill.sh`
- Nodes handled: 24 cheap_extract targets
- Execution note:
  - All 4 child runs exited 0 and the hardened status summary reported `processed=4`, `skipped=0`, `prompt_failed=0`, `failed=0`.
  - `000420.SZ`, `000898.SZ`, `000902.SZ`, and `000973.SZ` each changed exactly the 6 target dpids.
  - `000898.SZ` filled `L3.channel.mix` as Known because the 2025 annual-report sales-mode table directly disclosed direct and distribution percentages summing to 100%.
  - `000973.SZ` filled `L3.channel.mix` as Known because the annual-report sales-mode table only disclosed direct sales and that amount matched total revenue.
  - `000420.SZ` and `000902.SZ` kept `L3.channel.mix` as `Unknown` because local materials did not directly disclose channel percentages or a directly mappable sales-mode amount table.
  - Natural-language English/schema-key residue check after run found 0 issues.
  - Stock-attribute PE/PB valuation wording misuse check after run found 0 issues.
  - Channel trend hardening held: 0 Chinese free-text `L3.channel.mix.value.trend` values after run.
  - All-null channel trend hardening held: 0 non-null `trend` values when all four channel percentage fields are null.
  - The batch did not require post-run cleanup.
  - Runner post-processing restored wrapped `scores.formula` in `000420.SZ` and `000973.SZ` (`formula_normalized=2`).
- Structural diff after run:
  - all 4 files changed only `L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`
  - Non-`nodes` YAML payload is unchanged for all 4 files
- Post-run cheap_extract dry-run:
  - all 4 completed stocks now show `nothing to fill (skip)` / `prompt_ready=0`
- Scoped closed-loop verifier:
  - full verifier output: `/tmp/domestic_closed_loop_after_batch184.json`
  - full hard violations: 0
  - full soft warnings: 12253
  - target-node violations filtered to the 24 batch dpids: 0
  - target-node evidence_quality type, old-key, English/schema-key residue, stock-attribute valuation-misuse, channel-trend Chinese free-text, all-null channel-trend, and excerpt check: 0 bad target nodes
  - target-file soft warnings: 9 historical non-target warnings only
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count=161709`
- Test gate after batch: `tests/test_apply_yaml_patch.py tests/test_prompt_gen_schema_block.py tests/test_prompt_gen_governance.py tests/test_schema_validator.py` passed, 91 tests
- Scope audit after batch: `fillable_total=109248`, `skipped_total=25724`, `cheap_extract=6750`
- Residual scope note: next global cheap_extract candidates include `INNOVATIVE_PHARMA/688796.SH`, `SEMI_EQUIPMENT/688727.SH`, `ANTI_INVOLUTION_CYCLICAL/002221.SZ`, and `ANTI_INVOLUTION_CYCLICAL/600389.SH`.

## Completed batch 185

- Batch target: `ANTI_INVOLUTION_CYCLICAL`, A-share, `cheap_extract`
- Stocks completed: `002221.SZ`, `600389.SH`, `600688.SH`, `600871.SH`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Parallel runner: `C1_INDUSTRY=ANTI_INVOLUTION_CYCLICAL`, `C1_PARALLEL=2`, via hardened `scripts/run_c1_fill.sh`
- Nodes handled: 24 cheap_extract targets
- Execution note:
  - All 4 child runs exited 0 and the hardened status summary reported `processed=4`, `skipped=0`, `prompt_failed=0`, `failed=0`.
  - `002221.SZ`, `600389.SH`, `600688.SH`, and `600871.SH` each changed exactly the 6 target dpids.
  - `002221.SZ` filled `L3.channel.mix` as Known because the 2025 annual-report sales-mode table directly disclosed direct and distributor percentages summing to 100%.
  - `600389.SH`, `600688.SH`, and `600871.SH` kept `L3.channel.mix` as `Unknown` because local materials did not directly disclose channel percentages or a directly mappable sales-mode amount table.
  - Natural-language English/schema-key residue check after run found 0 issues.
  - Stock-attribute PE/PB valuation wording misuse check after run found 0 issues.
  - Channel trend hardening held: 0 Chinese free-text `L3.channel.mix.value.trend` values after run.
  - All-null channel trend hardening held: 0 non-null `trend` values when all four channel percentage fields are null.
  - The batch did not require post-run cleanup.
  - Runner post-processing restored wrapped `scores.formula` in `002221.SZ`, `600688.SH`, and `600871.SH` (`formula_normalized=3`).
- Structural diff after run:
  - all 4 files changed only `L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`
  - Non-`nodes` YAML payload is unchanged for all 4 files
- Post-run cheap_extract dry-run:
  - all 4 completed stocks now show `nothing to fill (skip)` / `prompt_ready=0`
- Scoped closed-loop verifier:
  - full verifier output: `/tmp/domestic_closed_loop_after_batch185.json`
  - full hard violations: 0
  - full soft warnings: 12253
  - target-node violations filtered to the 24 batch dpids: 0
  - target-node evidence_quality type, old-key, English/schema-key residue, stock-attribute valuation-misuse, channel-trend Chinese free-text, all-null channel-trend, and excerpt check: 0 bad target nodes
  - target-file soft warnings: 9 historical non-target warnings only
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count=161688`
- Test gate after batch: `tests/test_apply_yaml_patch.py tests/test_prompt_gen_schema_block.py tests/test_prompt_gen_governance.py tests/test_schema_validator.py` passed, 91 tests
- Scope audit after batch: `fillable_total=109224`, `skipped_total=25748`, `cheap_extract=6726`
- Residual scope note: next global cheap_extract candidates include `INNOVATIVE_PHARMA/688796.SH`, `SEMI_EQUIPMENT/688727.SH`, `ANTI_INVOLUTION_CYCLICAL/600968.SH`, and `ANTI_INVOLUTION_CYCLICAL/603033.SH`.

## Completed batch 186

- Batch target: `INNOVATIVE_PHARMA`, A-share, `cheap_extract`
- Stocks completed: `688796.SH`, `301267.SZ`, `600216.SH`, `600521.SH`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Parallel runner: `C1_INDUSTRY=INNOVATIVE_PHARMA`, `C1_PARALLEL=2`, via hardened `scripts/run_c1_fill.sh`
- Nodes handled: 24 cheap_extract targets
- Execution note:
  - All 4 child runs exited 0 and the hardened status summary reported `processed=4`, `skipped=0`, `prompt_failed=0`, `failed=0`.
  - `688796.SH`, `301267.SZ`, `600216.SH`, and `600521.SH` each changed exactly the 6 target dpids.
  - `301267.SZ` filled `L3.channel.mix` as Known because the 2025 annual-report sales-mode table directly disclosed all sales as direct sales or service.
  - `688796.SH`, `600216.SH`, and `600521.SH` kept `L3.channel.mix` as `Unknown` because local materials did not directly disclose channel percentages or a directly mappable sales-mode amount table.
  - Natural-language English/schema-key residue check after run found 0 issues.
  - Stock-attribute PE/PB valuation wording misuse check after run found 0 issues.
  - Channel trend hardening held: 0 Chinese free-text `L3.channel.mix.value.trend` values after run.
  - All-null channel trend hardening held: 0 non-null `trend` values when all four channel percentage fields are null.
  - The batch did not require post-run cleanup.
  - Runner post-processing restored wrapped `scores.formula` in `688796.SH`, `301267.SZ`, and `600521.SH` (`formula_normalized=3`).
- Structural diff after run:
  - all 4 files changed only `L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`
  - Non-`nodes` YAML payload is unchanged for all 4 files
- Post-run cheap_extract dry-run:
  - all 4 completed stocks now show `nothing to fill (skip)` / `prompt_ready=0`
- Scoped closed-loop verifier:
  - full verifier output: `/tmp/domestic_closed_loop_after_batch186.json`
  - full hard violations: 0
  - full soft warnings: 12253
  - target-node violations filtered to the 24 batch dpids: 0
  - target-node evidence_quality type, old-key, English/schema-key residue, stock-attribute valuation-misuse, channel-trend Chinese free-text, all-null channel-trend, and excerpt check: 0 bad target nodes
  - target-file soft warnings: 12 historical non-target warnings only
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count=161667`
- Test gate after batch: `tests/test_apply_yaml_patch.py tests/test_prompt_gen_schema_block.py tests/test_prompt_gen_governance.py tests/test_schema_validator.py` passed, 91 tests
- Scope audit after batch: `fillable_total=109200`, `skipped_total=25772`, `cheap_extract=6702`
- Residual scope note: next global cheap_extract candidates include `SEMI_EQUIPMENT/688727.SH`, `ANTI_INVOLUTION_CYCLICAL/600968.SH`, `ANTI_INVOLUTION_CYCLICAL/603033.SH`, and `DOMESTIC_CONSUMPTION/000429.SZ`.

## Completed batch 187

- Batch target: `ANTI_INVOLUTION_CYCLICAL`, A-share, `cheap_extract`
- Stocks completed: `600968.SH`, `603033.SH`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Parallel runner: `C1_INDUSTRY=ANTI_INVOLUTION_CYCLICAL`, `C1_PARALLEL=2`, via hardened `scripts/run_c1_fill.sh`
- Nodes handled: 12 cheap_extract targets
- Execution note:
  - Both child runs exited 0 and the hardened status summary reported `processed=2`, `skipped=0`, `prompt_failed=0`, `failed=0`.
  - `600968.SH` and `603033.SH` each changed exactly the 6 target dpids.
  - `603033.SH` filled `L3.channel.mix` as Known because the annual-report sales-mode table directly disclosed direct, distributor, bid-acquired, and other sales-mode amounts with a checkable denominator; non-standard sales modes were assigned to `others_pct`.
  - `600968.SH` kept `L3.channel.mix` as `Unknown` because local materials did not directly disclose channel percentages or a directly mappable sales-mode amount table.
  - Initial full verifier found one target-node excerpt warning in `600968.SH:L1.model.tag`; the node was tightened to cite only the exact local `L1.company.main_business` text and remove unsupported operating-scope wording.
  - Natural-language English/schema-key residue check after run found 0 issues.
  - Stock-attribute PE/PB valuation wording misuse check after run found 0 issues.
  - Channel trend hardening held: 0 Chinese free-text `L3.channel.mix.value.trend` values after run.
  - All-null channel trend hardening held: 0 non-null `trend` values when all four channel percentage fields are null.
  - Runner post-processing restored wrapped `scores.formula` in both files (`formula_normalized=2`).
- Structural diff after run:
  - both files changed only `L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`
  - Non-`nodes` YAML payload is unchanged for both files
- Post-run cheap_extract dry-run:
  - both completed stocks now show `nothing to fill (skip)` / `prompt_ready=0`
- Scoped closed-loop verifier:
  - full verifier output after excerpt fix: `/tmp/domestic_closed_loop_after_batch187_fixed.json`
  - full hard violations: 0
  - full soft warnings: 12253
  - target-node violations filtered to the 12 batch dpids: 0
  - target-node evidence_quality type, old-key, English/schema-key residue, stock-attribute valuation-misuse, channel-trend Chinese free-text, all-null channel-trend, and excerpt check: 0 bad target nodes
  - target-file soft warnings: 4 historical non-target warnings only
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count=161656`
- Test gate after batch: `tests/test_apply_yaml_patch.py tests/test_prompt_gen_schema_block.py tests/test_prompt_gen_governance.py tests/test_schema_validator.py` passed, 91 tests
- Scope audit after batch: `fillable_total=109188`, `skipped_total=25784`, `cheap_extract=6690`
- Residual scope note: next global cheap_extract candidates include `SEMI_EQUIPMENT/688727.SH`, `DOMESTIC_CONSUMPTION/000429.SZ`, `DOMESTIC_CONSUMPTION/000828.SZ`, and `DOMESTIC_CONSUMPTION/002607.SZ`.

## Completed batch 188

- Batch target: `DOMESTIC_CONSUMPTION`, A-share, `cheap_extract`
- Stocks completed: `000429.SZ`, `000828.SZ`, `002607.SZ`, `600018.SH`
- Prompt policy: `--preserve-known-baseline-missing --preserve-unknown-no-local-evidence`
- GPT-5.5/Codex CLI service tier: `fast`
- Parallel runner: `C1_INDUSTRY=DOMESTIC_CONSUMPTION`, `C1_PARALLEL=2`, via hardened `scripts/run_c1_fill.sh`
- Nodes handled: 24 cheap_extract targets
- Execution note:
  - All 4 child runs exited 0 and the hardened status summary reported `processed=4`, `skipped=0`, `prompt_failed=0`, `failed=0`.
  - `000429.SZ`, `000828.SZ`, `002607.SZ`, and `600018.SH` each changed exactly the 6 target dpids.
  - `002607.SZ` filled `L3.channel.mix` as Known because the annual-report sales-mode table directly disclosed all revenue as direct sales.
  - `000429.SZ`, `000828.SZ`, and `600018.SH` kept `L3.channel.mix` as `Unknown` because local materials did not directly disclose channel percentages or a directly mappable sales-mode amount table; business-line, customer, and region structures were not mapped to channels.
  - Natural-language English/schema-key residue check after run found 0 issues.
  - Stock-attribute PE/PB valuation wording misuse check after run found 0 issues.
  - Channel trend hardening held: 0 Chinese free-text `L3.channel.mix.value.trend` values after run.
  - All-null channel trend hardening held: 0 non-null `trend` values when all four channel percentage fields are null.
  - Runner post-processing restored wrapped `scores.formula` in `000828.SZ` and `002607.SZ` (`formula_normalized=2`).
- Structural diff after run:
  - all 4 files changed only `L3.channel.mix`, `L1.role.tag`, `L1.model.tag`, `L1.moat.tags`, `L1.stock_attr.tags`, `L1.position.growth_rank`
  - Non-`nodes` YAML payload is unchanged for all 4 files
- Post-run cheap_extract dry-run:
  - all 4 completed stocks now show `nothing to fill (skip)` / `prompt_ready=0`
- Scoped closed-loop verifier:
  - full verifier output: `/tmp/domestic_closed_loop_after_batch188.json`
  - full hard violations: 0
  - full soft warnings: 12253
  - target-node violations filtered to the 24 batch dpids: 0
  - target-node evidence_quality type, old-key, English/schema-key residue, stock-attribute valuation-misuse, channel-trend Chinese free-text, all-null channel-trend, and excerpt check: 0 bad target nodes
  - target-file soft warnings: 10 historical non-target warnings only
- Overlay validation after batch: `ok: True`, `error_count: 0`, `warning_count=161635`
- Test gate after batch: `tests/test_apply_yaml_patch.py tests/test_prompt_gen_schema_block.py tests/test_prompt_gen_governance.py tests/test_schema_validator.py` passed, 91 tests
- Scope audit after batch: `fillable_total=109164`, `skipped_total=25808`, `cheap_extract=6666`
- Residual scope note: next global cheap_extract candidates include `SEMI_EQUIPMENT/688727.SH`, `DOMESTIC_CONSUMPTION/600115.SH`, `DOMESTIC_CONSUMPTION/600704.SH`, and `DOMESTIC_CONSUMPTION/600755.SH`.

## Pipeline hardening after batch 139

- Issue found during supervision: several successful child LLM runs wrote `L3.channel.mix.value.trend` as Chinese free text even though downstream batches had been manually normalizing that slot to short enum-like strings.
- Fix applied:
  - `scripts/codex_prompt_gen.py` now tells the LLM that `L3.channel.mix.value.trend` must not be Chinese free text and should use short enum-like values such as `direct_sales_dominant`, `direct_share_up`, `direct_share_slightly_down`, `flat`, or `mixed`; absent trend evidence stays `null`.
  - `tests/test_prompt_gen_governance.py` now asserts that the generated schema block includes this channel trend rule.
- Verification:
  - `tests/test_prompt_gen_governance.py tests/test_prompt_gen_schema_block.py` passed, 54 tests.
  - Prompt spot-check for `HK_CN_INTERNET/002230.SZ` includes the new `value.trend` rule.

## Safe batch commands

Single industry, small A-share-only chunk:

```bash
export CODEX_SERVICE_TIER=fast
export CODEX_WORKDIR=/Users/fanjie/Desktop/Cowork/project-ult-mvp20
export A_SHARE_ONLY=true
export MODEL_TIER=cheap_extract
export PROMPT_FLAGS="--preserve-known-baseline-missing --preserve-unknown-no-local-evidence"
scripts/codex_run_stocks_chunk.sh SEMI_EQUIPMENT 10 forward
```

Whole A-share batch for one tier, after reviewing a small chunk:

```bash
export CODEX_SERVICE_TIER=fast
export CODEX_WORKDIR=/Users/fanjie/Desktop/Cowork/project-ult-mvp20
scripts/codex_dispatch.sh --company-only --a-share-only --model-tier cheap_extract
```

Lower-reasoning GPT-5.5 runner for cost-controlled waves:

```bash
export CODEX_CMD=scripts/codex_run_prompt_low.sh
scripts/codex_dispatch.sh --company-only --a-share-only --model-tier analysis
```

## Verification after each batch

```bash
.venv/bin/python scripts/audit_a_share_llm_target_scope.py --top-n 25
.venv/bin/python scripts/verify_overlay_closed_loop.py --check-schema --check-excerpt --out-json /tmp/a_share_llm_goal/verify_closed_loop_after_batch.json
.venv/bin/python -m mvp20.cli validate-overlays
git diff --check
```

## Execution note

The current queue is too large to run as an unbounded single operation. A full pass would require thousands of GPT-5.5 prompt executions, and the pilot showed that even 6 cheap_extract nodes can be expensive. The safe operating mode is tiered, A-share-only, small chunks first, with verifier and target-scope audit after every batch.
