# Iceberg Catalog Runbook

data-platform Lite mode uses a PyIceberg SQL catalog backed by the same
PostgreSQL instance as the queue and control tables. The catalog stores only
Iceberg metadata tables with the `iceberg_` prefix, currently
`iceberg_tables` and `iceberg_namespace_properties`.

Raw Zone files are not registered in Iceberg. The init command creates only
these namespaces:

- `canonical`
- `formal`
- `analytical`

## Initialize Locally

```bash
cd <workspace>/data-platform
mkdir -p <proof-workspace>/dp_warehouse
DP_ICEBERG_WAREHOUSE_PATH=<proof-workspace>/dp_warehouse \
DP_PG_DSN="<postgres-dsn>" \
  python scripts/init_iceberg_catalog.py
```

The command is idempotent. Re-running it keeps the existing catalog tables and
namespaces in place without creating duplicates.

## Verify

```bash
python -c "from data_platform.serving.catalog import load_catalog; print(load_catalog().list_namespaces())"
```

Expected namespaces:

```python
[("canonical",), ("formal",), ("analytical",)]
```

There must be no `raw` namespace. Raw Zone archives remain plain Parquet or
JSON files outside the Iceberg catalog.
