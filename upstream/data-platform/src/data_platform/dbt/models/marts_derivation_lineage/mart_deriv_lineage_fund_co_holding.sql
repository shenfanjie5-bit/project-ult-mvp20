{{ config(materialized="table") }}

with fund_security_positions as (
    select
        report_date,
        holder_id,
        security_id,
        max(announced_date) as latest_announced_date
    from {{ ref('mart_fact_holding_position_v2') }}
    where holding_source = 'fund_portfolio'
    group by report_date, holder_id, security_id
),

fund_pairs as (
    select
        left_position.report_date,
        left_position.security_id as security_id_left,
        right_position.security_id as security_id_right,
        left_position.holder_id,
        left_position.latest_announced_date as left_announced_date,
        right_position.latest_announced_date as right_announced_date
    from fund_security_positions as left_position
    inner join fund_security_positions as right_position
        on left_position.report_date = right_position.report_date
        and left_position.holder_id = right_position.holder_id
        and left_position.security_id < right_position.security_id
),

source_rows as (
    select
        co_holding.mart_key,
        co_holding.report_date,
        co_holding.security_id_left,
        co_holding.security_id_right,
        co_holding.latest_announced_date,
        lineage.report_date as source_report_date,
        lineage.source_interface_id,
        lineage.source_run_id,
        lineage.raw_loaded_at
    from {{ ref('mart_deriv_fund_co_holding') }} as co_holding
    inner join fund_pairs
        on co_holding.report_date = fund_pairs.report_date
        and co_holding.security_id_left = fund_pairs.security_id_left
        and co_holding.security_id_right = fund_pairs.security_id_right
    inner join {{ ref('mart_lineage_fact_holding_position') }} as lineage
        on fund_pairs.report_date = lineage.report_date
        and fund_pairs.holder_id = lineage.holder_id
        and lineage.holding_source = 'fund_portfolio'
        and fund_pairs.security_id_left = lineage.security_id
        and fund_pairs.left_announced_date = lineage.announced_date

    union all

    select
        co_holding.mart_key,
        co_holding.report_date,
        co_holding.security_id_left,
        co_holding.security_id_right,
        co_holding.latest_announced_date,
        lineage.report_date as source_report_date,
        lineage.source_interface_id,
        lineage.source_run_id,
        lineage.raw_loaded_at
    from {{ ref('mart_deriv_fund_co_holding') }} as co_holding
    inner join fund_pairs
        on co_holding.report_date = fund_pairs.report_date
        and co_holding.security_id_left = fund_pairs.security_id_left
        and co_holding.security_id_right = fund_pairs.security_id_right
    inner join {{ ref('mart_lineage_fact_holding_position') }} as lineage
        on fund_pairs.report_date = lineage.report_date
        and fund_pairs.holder_id = lineage.holder_id
        and lineage.holding_source = 'fund_portfolio'
        and fund_pairs.security_id_right = lineage.security_id
        and fund_pairs.right_announced_date = lineage.announced_date
)

select
    mart_key,
    report_date,
    security_id_left,
    security_id_right,
    cast('fund_co_holding' as varchar) as dataset,
    concat('fund_co_holding:', mart_key) as snapshot_id,
    latest_announced_date as as_of_date,
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
    report_date,
    security_id_left,
    security_id_right,
    latest_announced_date
