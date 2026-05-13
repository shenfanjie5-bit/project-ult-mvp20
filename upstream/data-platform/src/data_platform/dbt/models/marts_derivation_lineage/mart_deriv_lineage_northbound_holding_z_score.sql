{{ config(materialized="table") }}

with source_rows as (
    select
        z_score.mart_key,
        z_score.security_id,
        z_score.holder_id,
        z_score.report_date,
        z_score.z_score_metric,
        z_score.window_end_date,
        lineage.report_date as source_report_date,
        lineage.source_interface_id,
        lineage.source_run_id,
        lineage.raw_loaded_at
    from {{ ref('mart_deriv_northbound_holding_z_score') }} as z_score
    inner join {{ ref('mart_lineage_fact_holding_position') }} as lineage
        on z_score.security_id = lineage.security_id
        and z_score.holder_id = lineage.holder_id
        and lineage.holding_source = 'northbound_hold'
        and lineage.report_date between z_score.window_start_date and z_score.window_end_date
)

select
    mart_key,
    security_id,
    holder_id,
    report_date,
    z_score_metric,
    cast('northbound_holding_z_score' as varchar) as dataset,
    concat('northbound_holding_z_score:', mart_key) as snapshot_id,
    window_end_date as as_of_date,
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
    security_id,
    holder_id,
    report_date,
    z_score_metric,
    window_end_date
