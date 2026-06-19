# Goal coverage audit

- Generated at: `2026-06-19T02:02:05+0800`
- Completion status: `not_complete`

## Summary

| Metric | Value |
|---|---:|
| `requirement_count` | `10` |
| `covered_count` | `10` |
| `missing_evidence_count` | `0` |
| `bounded_or_documented_not_full_count` | `4` |
| `completion_blockers` | `['repo binary/large files are fingerprint-sampled, but file semantics are not exhaustively reviewed', 'DOCKCASE CSV semantic review is signature-stratified and evidence-backed, with a ranked backlog and accumulated deep-sampled backlog batches, but not exhaustive across every CSV row/file', 'A-share score field trace still reports 34 actionable participating gaps']` |

## Requirement Matrix

| Requirement | Status | Evidence strength | Remaining gap |
|---|---|---|---|
| Inventory current project files and read bounded text bodies | `covered` | `metadata_full_walk_plus_bounded_text_body_read` | Bounded text bodies are read and fingerprinted; binary/large files now have sampled head/tail fingerprints, but full semantic interpretation remains incomplete. |
| Inventory DOCKCASE database_all and market_data files | `covered` | `metadata_full_walk` | Metadata inventory is full, but full semantic content review remains bounded by later samples. |
| Read/index source-bearing code roots | `covered` | `static_full_index_selected_roots` | Static indexing is broad but not equivalent to manual semantic review of every implementation path. |
| Open data files enough to verify schema and first-row samples | `covered` | `schema_full_csv_headers_bounded_first_rows` | Does not read every CSV row; JSON/HTML/PDF content remains sampled. |
| Sample real DOCKCASE CSV rows by header signature for semantic checks | `covered` | `signature_stratified_bounded_csv_semantic_rows` | Covers real rows across header-signature strata and reports signature/file sampling boundaries; the semantic backlog ranks remaining high-volume/no-sample/issue-heavy signatures and 3 backlog batches deep-sampled ranks [27, 31, 46, 121, 124, 128], but it still does not exhaustively read every CSV row. |
| Check selected A-share structured data rows for semantic validity | `covered` | `bounded_real_row_semantic_sample` | Covers representative high-value A-share sources, not every symbol/file/row. |
| Check news HTML, announcement PDF text extractability, and entity/event signals | `covered` | `count_all_parse_full_entity_event_signal_pass` | Counts and parses every audited HTML/PDF file; retained examples are bounded for report size, while entity/event classification remains heuristic. |
| Trace A-share spec fields into numeric scoring paths | `covered` | `runtime_trace_and_gap_priority` | All score-relevant valid-real formula gaps are currently governance/intentional; remaining score incompleteness is 34 actionable participating gaps plus 21 governance/intentional gaps. |
| Verify audited user-facing hot paths stay under 1 second | `covered` | `machine_bff_latency_plus_machine_browser_qa_plus_spa_shell_latency_plus_navigation_contract` | BFF latency, browser first-H1 checks, SPA shell latency, and source navigation contract cover the audited Project ULT route/navigation surface; residual risk is browser/device-specific edge cases. |
| Classify locked modules by current runnable status | `covered` | `lockfile_and_latency_evidence` | Classifies locked upstream modules and local surfaces; does not turn skeleton adapters into full services. |
