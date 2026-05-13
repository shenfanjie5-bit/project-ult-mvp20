{% macro stg_latest_raw(source_id, dataset, source_columns, select_list, partition_mode="partitioned", request_scoped=false) -%}
with raw_manifest_files as (
    select
        partition_date,
        artifacts,
        filename
    from read_json_auto(
        '{{ dp_raw_manifest_path(source_id, dataset) }}',
        columns={
            partition_date: 'VARCHAR',
            artifacts: 'STRUCT(run_id VARCHAR, written_at VARCHAR, partition_date VARCHAR, request_params_hash VARCHAR)[]'
        },
        hive_partitioning=1,
        filename=1
    )
),

raw_artifacts as (
    select
        cast(artifact.run_id as varchar) as source_run_id,
        cast(artifact.written_at as timestamp) as raw_loaded_at,
        cast(coalesce(artifact.partition_date, raw_manifest_files.partition_date) as date)
            as partition_date,
        strftime(
            cast(coalesce(artifact.partition_date, raw_manifest_files.partition_date) as date),
            '%Y%m%d'
        ) as partition_yyyymmdd,
        coalesce(
            nullif(cast(artifact.request_params_hash as varchar), ''),
            cast(artifact.run_id as varchar)
        ) as request_scope_key
    from raw_manifest_files
    cross join unnest(raw_manifest_files.artifacts) as artifact_item(artifact)
),

ranked_raw_artifacts as (
    select
        source_run_id,
        raw_loaded_at,
        partition_date,
        partition_yyyymmdd,
        request_scope_key,
        row_number() over (
{%- if partition_mode != "static" and request_scoped %}
            partition by partition_date, request_scope_key
{%- elif partition_mode != "static" %}
            partition by partition_date
{%- elif request_scoped %}
            partition by request_scope_key
{%- endif %}
            order by raw_loaded_at desc, partition_date desc, source_run_id desc
        ) as artifact_rank
    from raw_artifacts
),

latest_raw_artifact as (
    select
        source_run_id,
        raw_loaded_at,
        partition_yyyymmdd
    from ranked_raw_artifacts
    where artifact_rank = 1
),

raw_{{ dataset }}_expected_columns as (
    select
{%- for column_name in source_columns %}
        null as "{{ column_name }}",
{%- endfor %}
        null as dt,
        null as filename
    where false
),

raw_{{ dataset }}_files as (
    select columns(*)
    from read_parquet(
        '{{ dp_raw_path(source_id, dataset) }}',
        hive_partitioning=1,
        filename=1,
        union_by_name=1
    )
),

raw_{{ dataset }} as (
    select
{%- for column_name in source_columns %}
        "{{ column_name }}",
{%- endfor %}
        dt,
        filename
    from (
        select columns(*)
        from raw_{{ dataset }}_expected_columns
        union all by name
        select columns(*)
        from raw_{{ dataset }}_files
    )
),

selected_{{ dataset }} as (
    select
{%- for column_name in source_columns %}
        raw_{{ dataset }}."{{ column_name }}",
{%- endfor %}
        latest_raw_artifact.source_run_id,
        latest_raw_artifact.raw_loaded_at
    from raw_{{ dataset }}
    inner join latest_raw_artifact
        on cast(raw_{{ dataset }}.dt as varchar) = latest_raw_artifact.partition_yyyymmdd
        and regexp_extract(raw_{{ dataset }}.filename, '([^/]+)[.]parquet$', 1)
            = latest_raw_artifact.source_run_id
)

select
{%- for expression in select_list %}
    {{ expression }},
{%- endfor %}
    cast(source_run_id as varchar) as source_run_id,
    cast(raw_loaded_at as timestamp) as raw_loaded_at
from selected_{{ dataset }}
{%- endmacro %}
