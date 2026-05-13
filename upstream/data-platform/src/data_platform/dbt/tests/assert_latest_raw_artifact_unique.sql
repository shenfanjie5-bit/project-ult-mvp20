{{ config(severity="error") }}
-- depends_on: {{ ref('stg_stock_basic') }}
{% set data_storage_root_path = env_var("DP_DATA_STORAGE_ROOT_PATH", "./data_platform/data").rstrip("/") %}
{% set raw_zone_path = env_var("DP_RAW_ZONE_PATH", data_storage_root_path ~ "/raw").rstrip("/") %}

with raw_manifest_files as (
    select
        cast(source_id as varchar) as manifest_source_id,
        cast(dataset as varchar) as manifest_dataset,
        cast(partition_date as date) as manifest_partition_date,
        artifacts,
        filename as manifest_filename
    from read_json_auto(
        '{{ raw_zone_path }}/tushare/*/**/_manifest.json',
        hive_partitioning=1,
        filename=1
    )
),

raw_artifacts as (
    select
        manifest_filename,
        manifest_source_id,
        manifest_dataset,
        manifest_partition_date,
        cast(artifact.run_id as varchar) as source_run_id,
        try_cast(artifact.written_at as timestamp) as raw_loaded_at
    from raw_manifest_files
    cross join unnest(raw_manifest_files.artifacts) as artifact_item(artifact)
),

max_freshness as (
    select
        manifest_source_id,
        manifest_dataset,
        manifest_partition_date,
        max(raw_loaded_at) as max_raw_loaded_at
    from raw_artifacts
    group by
        manifest_source_id,
        manifest_dataset,
        manifest_partition_date
),

latest_ties as (
    select
        raw_artifacts.manifest_source_id,
        raw_artifacts.manifest_dataset,
        raw_artifacts.manifest_partition_date,
        raw_artifacts.raw_loaded_at,
        count(*) as latest_artifact_count
    from raw_artifacts
    inner join max_freshness
        on raw_artifacts.manifest_source_id = max_freshness.manifest_source_id
        and raw_artifacts.manifest_dataset = max_freshness.manifest_dataset
        and raw_artifacts.manifest_partition_date = max_freshness.manifest_partition_date
        and raw_artifacts.raw_loaded_at = max_freshness.max_raw_loaded_at
    group by
        raw_artifacts.manifest_source_id,
        raw_artifacts.manifest_dataset,
        raw_artifacts.manifest_partition_date,
        raw_artifacts.raw_loaded_at
)

select
    manifest_source_id,
    manifest_dataset,
    manifest_partition_date,
    raw_loaded_at,
    latest_artifact_count
from latest_ties
where latest_artifact_count > 1
