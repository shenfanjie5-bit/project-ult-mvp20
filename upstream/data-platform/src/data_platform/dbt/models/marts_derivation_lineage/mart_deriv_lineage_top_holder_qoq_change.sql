{{ config(materialized="table") }}

with source_rows as (
    select
        qoq.mart_key,
        qoq.holding_source,
        qoq.holder_id,
        qoq.security_id,
        qoq.report_date,
        qoq.announced_date,
        lineage.report_date as source_report_date,
        lineage.announced_date as source_announced_date,
        lineage.source_interface_id,
        lineage.source_run_id,
        lineage.raw_loaded_at
    from {{ ref('mart_deriv_top_holder_qoq_change') }} as qoq
    inner join {{ ref('mart_lineage_fact_holding_position') }} as lineage
        on qoq.holding_source = lineage.holding_source
        and qoq.holder_id = lineage.holder_id
        and qoq.security_id = lineage.security_id
        and qoq.report_date = lineage.report_date
        and qoq.announced_date = lineage.announced_date

    union all

    select
        qoq.mart_key,
        qoq.holding_source,
        qoq.holder_id,
        qoq.security_id,
        qoq.report_date,
        qoq.announced_date,
        lineage.report_date as source_report_date,
        lineage.announced_date as source_announced_date,
        lineage.source_interface_id,
        lineage.source_run_id,
        lineage.raw_loaded_at
    from {{ ref('mart_deriv_top_holder_qoq_change') }} as qoq
    inner join {{ ref('mart_lineage_fact_holding_position') }} as lineage
        on qoq.holding_source = lineage.holding_source
        and qoq.holder_id = lineage.holder_id
        and qoq.security_id = lineage.security_id
        and qoq.previous_report_date = lineage.report_date
        and qoq.previous_announced_date = lineage.announced_date
)

select
    mart_key,
    holding_source,
    holder_id,
    security_id,
    report_date,
    announced_date,
    cast('top_holder_qoq_change' as varchar) as dataset,
    concat('top_holder_qoq_change:', mart_key) as snapshot_id,
    announced_date as as_of_date,
    cast('mart_fact_holding_position_v2' as varchar) as source_mart,
    min(source_report_date) as source_window_start_date,
    max(source_report_date) as source_window_end_date,
    string_agg(distinct source_interface_id, ',') as source_interface_ids,
    count(*) as source_row_count,
    count(*) as source_lineage_row_count,
    string_agg(distinct cast(source_run_id as varchar), ',') as source_run_ids,
    min(raw_loaded_at) as raw_loaded_at_min,
    max(raw_loaded_at) as raw_loaded_at_max,
    concat(
        'source_rows=',
        cast(count(*) as varchar),
        ';lineage_rows=',
        cast(count(*) as varchar)
    ) as source_lineage_summary
from source_rows
group by
    mart_key,
    holding_source,
    holder_id,
    security_id,
    report_date,
    announced_date
