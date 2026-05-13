# Canonical Schema Evolution SOP

This runbook covers Canonical Iceberg table changes that are intentionally limited to:

- adding nullable columns
- widening `int32` to `int64`
- widening `float32` to `float64`

Column deletion, column rename, type narrowing, required-column addition, table rebuilds, and
business-default inference are out of scope. Raw Zone files must remain Parquet/JSON artifacts and
must not be converted into an Iceberg layer.

## Preflight

1. Confirm the target table is declared in `src/data_platform/ddl/iceberg_tables.py`.
2. Update the table `TableSpec` to the target schema.
3. Run a schema evolution dry-run from Python:

```bash
PYTHONPATH=src .venv/bin/python - <<'PY'
from data_platform.ddl.iceberg_tables import CANONICAL_FACT_PRICE_BAR_SPEC
from data_platform.serving.catalog import load_catalog
from data_platform.serving.schema_evolution import apply_schema_evolution

plan = apply_schema_evolution(
    load_catalog(),
    "canonical.fact_price_bar",
    CANONICAL_FACT_PRICE_BAR_SPEC.schema,
)
print(plan)
PY
```

The plan must have an empty `rejections` list before apply. `requires_backfill=True` means at least
one nullable column was added and a follow-up overwrite is required to populate explicit values.

## Apply

Apply only after reviewing the dry-run output:

```bash
PYTHONPATH=src .venv/bin/python - <<'PY'
from data_platform.ddl.iceberg_tables import CANONICAL_FACT_PRICE_BAR_SPEC
from data_platform.serving.catalog import load_catalog
from data_platform.serving.schema_evolution import apply_schema_evolution

plan = apply_schema_evolution(
    load_catalog(),
    "canonical.fact_price_bar",
    CANONICAL_FACT_PRICE_BAR_SPEC.schema,
    dry_run=False,
)
print(plan)
PY
```

Type widening is metadata-only. Add-column migrations expose `NULL` for historical rows until a
backfill overwrite is published.

## Backfill

Backfill SQL must explicitly project every business column expected by the canonical table. The
loader still owns `canonical_loaded_at`.

```bash
PYTHONPATH=src .venv/bin/python scripts/canonical_backfill.py \
  --table canonical.fact_price_bar \
  --sql-file backfill.sql \
  --dry-run
```

After the dry-run succeeds, execute without `--dry-run`:

```bash
PYTHONPATH=src .venv/bin/python scripts/canonical_backfill.py \
  --table canonical.fact_price_bar \
  --sql-file backfill.sql
```

The non-dry run returns a `WriteResult` JSON payload with `snapshot_id` and `row_count`.

## Time Travel Verification

Issue #14 validated that the PG-backed Iceberg catalog preserves old snapshots after add-column
schema evolution. Re-run the spike and the focused schema tests before shipping a migration:

```bash
PYTHONPATH=src .venv/bin/python -m pytest \
  tests/spike/test_iceberg_write_chain.py \
  tests/serving/test_schema_evolution.py
```

When PostgreSQL is unavailable, the spike tests skip by design in sandboxed development; run them
against a real `DATABASE_URL` before production rollout.

To verify old snapshot readability manually, record the current snapshot before applying the change:

```bash
PYTHONPATH=src .venv/bin/python - <<'PY'
from data_platform.serving.catalog import load_catalog

table = load_catalog().load_table("canonical.fact_price_bar")
snapshot = table.current_snapshot()
print(snapshot.snapshot_id if snapshot else None)
PY
```

After apply and backfill, scan the recorded snapshot and confirm the old schema does not expose the
new column:

```bash
PYTHONPATH=src .venv/bin/python - <<'PY'
from data_platform.serving.catalog import load_catalog

table = load_catalog().load_table("canonical.fact_price_bar")
old_snapshot_id = 123456789
payload = table.scan(snapshot_id=old_snapshot_id).to_arrow()
print(payload.schema.names)
PY
```

## Rollback

Do not delete or rename columns to roll back a Canonical schema change. Rollback options are:

- stop consumers and keep serving from the previously recorded snapshot while the fix is prepared
- apply a forward-only correction with another allowed add-column or widening change
- overwrite the current table from an explicit backfill query that restores the intended values

Keep the recorded snapshot id, applied plan, backfill SQL, and returned `WriteResult` in the
deployment notes.
