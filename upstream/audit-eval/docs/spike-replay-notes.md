# Replay Spike Notes

This spike validates a pure offline replay path for `cycle_20260410` without
connecting to the main system, Iceberg, DuckDB, Dagster, or any model endpoint.

## Constraint Mapping

- Section 6 principle 2, Replay Means Reconstruct, Not Re-run: replay reads
  stored `sanitized_input`, `raw_output`, `parsed_result`, hashes, and snapshot
  refs from fixture audit records. It never calls a model.
- Section 6 principle 4, Manifest-first Audit: `scripts.spike_replay` loads
  `manifest.json` and verifies every replay snapshot ref against
  `manifest_snapshot_set` before loading a file from `formal_snapshots/`.
- Section 11.1 rule C5: `AuditRecordDraft` rejects records where
  `llm_lineage.called` is `true` and any of the five replay bundle fields is
  `None`.
- C1: replay output is reconstructed from persisted history and published
  snapshot refs, not current code or current prompts.
- C2: formal object reads are manifest-bound. A replay record that points to a
  snapshot absent from `cycle_publish_manifest` fails before any historical
  formal object is returned.

## Fixture Shape

The fixture under `tests/fixtures/spike/cycle_20260410/` contains:

- two `audit_record` rows: L4 `world_state` and L7 `recommendation`
- two `replay_record` rows with `replay_mode` fixed to `read_history`
- one manifest containing the published snapshot set
- two historical formal snapshot JSON files

Run the demonstration with:

```bash
python -m scripts.spike_replay --cycle-id cycle_20260410 --object-ref recommendation --fixtures tests/fixtures/spike
```

