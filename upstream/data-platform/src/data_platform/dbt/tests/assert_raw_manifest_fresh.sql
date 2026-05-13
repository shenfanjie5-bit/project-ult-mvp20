{{ config(severity="error") }}
-- depends_on: {{ ref('stg_stock_basic') }}
{% set data_storage_root_path = env_var("DP_DATA_STORAGE_ROOT_PATH", "./data_platform/data").rstrip("/") %}
{% set raw_zone_path = env_var("DP_RAW_ZONE_PATH", data_storage_root_path ~ "/raw").rstrip("/") %}

with raw_manifest_files as (
    select
        cast(source_id as varchar) as manifest_source_id,
        cast(dataset as varchar) as manifest_dataset,
        cast(partition_date as varchar) as manifest_partition_date,
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
        cast(artifact.source_id as varchar) as artifact_source_id,
        cast(artifact.dataset as varchar) as artifact_dataset,
        cast(artifact.partition_date as varchar) as artifact_partition_date,
        cast(artifact.run_id as varchar) as source_run_id,
        cast(artifact.path as varchar) as artifact_path,
        try_cast(artifact.row_count as bigint) as row_count,
        try_cast(artifact.written_at as timestamp) as raw_loaded_at
    from raw_manifest_files
    cross join unnest(raw_manifest_files.artifacts) as artifact_item(artifact)
),

raw_parquet_files as (
    select file as artifact_file
    from glob(
        '{{ raw_zone_path }}/tushare/*/**/*.parquet'
    )
),

validated as (
    select
        raw_artifacts.*,
        raw_parquet_files.artifact_file is not null as artifact_exists,
        regexp_matches(
            lower(source_run_id),
            '^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'
        )
        or regexp_matches(
            lower(source_run_id),
            '^[0-9a-f]{12}4[0-9a-f]{3}[89ab][0-9a-f]{15}$'
        )
        or regexp_matches(
            upper(source_run_id),
            '^[0-7][0-9A-HJKMNP-TV-Z]{25}$'
        ) as has_valid_run_id
    from raw_artifacts
    left join raw_parquet_files
        on raw_parquet_files.artifact_file = raw_artifacts.artifact_path
        or raw_parquet_files.artifact_file = (
            '{{ raw_zone_path }}/'
            || raw_artifacts.artifact_path
        )
)

select
    manifest_filename,
    manifest_source_id,
    manifest_dataset,
    manifest_partition_date,
    source_run_id,
    artifact_path,
    row_count,
    raw_loaded_at,
    artifact_exists
from validated
where manifest_source_id != artifact_source_id
   or manifest_dataset != artifact_dataset
   or manifest_partition_date != artifact_partition_date
   or artifact_source_id is null
   or artifact_dataset is null
   or artifact_partition_date is null
   or try_cast(manifest_partition_date as date) is null
   or try_cast(artifact_partition_date as date) is null
   or has_valid_run_id is not true
   or artifact_path is null
   or trim(artifact_path) = ''
   or artifact_exists is not true
   or row_count is null
   or row_count < 0
   or raw_loaded_at is null
