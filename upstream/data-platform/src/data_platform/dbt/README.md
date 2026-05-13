# dbt

dbt project root for data-platform staging, intermediate, and marts models.

## Local profile

Create a local profile from the checked-in example:

```bash
cp src/data_platform/dbt/profiles.yml.example src/data_platform/dbt/profiles.yml
```

Set the runtime paths used by dbt-duckdb:

```bash
export DP_DUCKDB_PATH=./data_platform/duckdb/data_platform.duckdb
export DP_PG_DSN=postgresql://dp:dp@localhost:5432/data_platform
```

Run dbt through the repository wrapper:

```bash
./scripts/dbt.sh parse
./scripts/dbt.sh run
```
