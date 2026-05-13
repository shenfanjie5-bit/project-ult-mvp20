{{ config(materialized="table") }}

with issuer_top_holders as (
    select
        cast('top_holder' as varchar) as holding_source,
        holder_name as holder_id,
        ts_code as security_id,
        end_date as report_date,
        ann_date as announced_date,
        cast('tushare' as varchar) as source_provider,
        cast('top10_holders' as varchar) as source_interface_id,
        source_run_id,
        raw_loaded_at
    from {{ ref('stg_top10_holders') }}
),

issuer_top_float_holders as (
    select
        cast('top_float_holder' as varchar) as holding_source,
        holder_name as holder_id,
        ts_code as security_id,
        end_date as report_date,
        ann_date as announced_date,
        cast('tushare' as varchar) as source_provider,
        cast('top10_floatholders' as varchar) as source_interface_id,
        source_run_id,
        raw_loaded_at
    from {{ ref('stg_top10_floatholders') }}
),

fund_positions as (
    select
        cast('fund_portfolio' as varchar) as holding_source,
        ts_code as holder_id,
        symbol as security_id,
        end_date as report_date,
        ann_date as announced_date,
        cast('tushare' as varchar) as source_provider,
        cast('fund_portfolio' as varchar) as source_interface_id,
        source_run_id,
        raw_loaded_at
    from {{ ref('stg_fund_portfolio') }}
),

northbound_positions as (
    select
        cast('northbound_hold' as varchar) as holding_source,
        concat('northbound:', exchange) as holder_id,
        ts_code as security_id,
        trade_date as report_date,
        trade_date as announced_date,
        cast('tushare' as varchar) as source_provider,
        cast('hsgt_hold_top10' as varchar) as source_interface_id,
        source_run_id,
        raw_loaded_at
    from {{ ref('stg_hsgt_hold_top10') }}
)

select
    holding_source,
    holder_id,
    security_id,
    report_date,
    announced_date,
    source_provider,
    source_interface_id,
    source_run_id,
    raw_loaded_at
from issuer_top_holders

union all by name

select
    holding_source,
    holder_id,
    security_id,
    report_date,
    announced_date,
    source_provider,
    source_interface_id,
    source_run_id,
    raw_loaded_at
from issuer_top_float_holders

union all by name

select
    holding_source,
    holder_id,
    security_id,
    report_date,
    announced_date,
    source_provider,
    source_interface_id,
    source_run_id,
    raw_loaded_at
from fund_positions

union all by name

select
    holding_source,
    holder_id,
    security_id,
    report_date,
    announced_date,
    source_provider,
    source_interface_id,
    source_run_id,
    raw_loaded_at
from northbound_positions
