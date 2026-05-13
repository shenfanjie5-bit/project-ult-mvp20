{{ config(materialized="table") }}

with issuer_top_holders as (
    select
        cast('top_holder' as varchar) as holding_source,
        holder_name as holder_id,
        holder_name as holder_name,
        holder_type as holder_type,
        ts_code as security_id,
        end_date as report_date,
        ann_date as announced_date,
        try_cast(hold_amount as decimal(38, 18)) as holding_amount,
        try_cast(hold_ratio as decimal(38, 18)) as holding_ratio,
        try_cast(hold_float_ratio as decimal(38, 18)) as holding_float_ratio,
        try_cast(hold_change as decimal(38, 18)) as holding_change,
        cast(null as decimal(38, 18)) as market_value,
        cast(null as varchar) as exchange
    from {{ ref('stg_top10_holders') }}
),

issuer_top_float_holders as (
    select
        cast('top_float_holder' as varchar) as holding_source,
        holder_name as holder_id,
        holder_name as holder_name,
        holder_type as holder_type,
        ts_code as security_id,
        end_date as report_date,
        ann_date as announced_date,
        try_cast(hold_amount as decimal(38, 18)) as holding_amount,
        try_cast(hold_ratio as decimal(38, 18)) as holding_ratio,
        try_cast(hold_float_ratio as decimal(38, 18)) as holding_float_ratio,
        try_cast(hold_change as decimal(38, 18)) as holding_change,
        cast(null as decimal(38, 18)) as market_value,
        cast(null as varchar) as exchange
    from {{ ref('stg_top10_floatholders') }}
),

fund_positions as (
    select
        cast('fund_portfolio' as varchar) as holding_source,
        ts_code as holder_id,
        ts_code as holder_name,
        cast('fund' as varchar) as holder_type,
        symbol as security_id,
        end_date as report_date,
        ann_date as announced_date,
        try_cast(amount as decimal(38, 18)) as holding_amount,
        try_cast(stk_float_ratio as decimal(38, 18)) as holding_ratio,
        try_cast(stk_float_ratio as decimal(38, 18)) as holding_float_ratio,
        cast(null as decimal(38, 18)) as holding_change,
        try_cast(mkv as decimal(38, 18)) as market_value,
        cast(null as varchar) as exchange
    from {{ ref('stg_fund_portfolio') }}
),

northbound_positions as (
    select
        cast('northbound_hold' as varchar) as holding_source,
        concat('northbound:', exchange) as holder_id,
        concat('Northbound ', exchange) as holder_name,
        cast('northbound' as varchar) as holder_type,
        ts_code as security_id,
        trade_date as report_date,
        trade_date as announced_date,
        try_cast(vol as decimal(38, 18)) as holding_amount,
        try_cast(ratio as decimal(38, 18)) as holding_ratio,
        try_cast(ratio as decimal(38, 18)) as holding_float_ratio,
        cast(null as decimal(38, 18)) as holding_change,
        cast(null as decimal(38, 18)) as market_value,
        exchange as exchange
    from {{ ref('stg_hsgt_hold_top10') }}
),

holding_positions as (
    select
        holding_source,
        holder_id,
        holder_name,
        holder_type,
        security_id,
        report_date,
        announced_date,
        holding_amount,
        holding_ratio,
        holding_float_ratio,
        holding_change,
        market_value,
        exchange
    from issuer_top_holders

    union all by name

    select
        holding_source,
        holder_id,
        holder_name,
        holder_type,
        security_id,
        report_date,
        announced_date,
        holding_amount,
        holding_ratio,
        holding_float_ratio,
        holding_change,
        market_value,
        exchange
    from issuer_top_float_holders

    union all by name

    select
        holding_source,
        holder_id,
        holder_name,
        holder_type,
        security_id,
        report_date,
        announced_date,
        holding_amount,
        holding_ratio,
        holding_float_ratio,
        holding_change,
        market_value,
        exchange
    from fund_positions

    union all by name

    select
        holding_source,
        holder_id,
        holder_name,
        holder_type,
        security_id,
        report_date,
        announced_date,
        holding_amount,
        holding_ratio,
        holding_float_ratio,
        holding_change,
        market_value,
        exchange
    from northbound_positions
)

select
    md5(
        concat_ws(
            '|',
            holding_source,
            holder_id,
            security_id,
            cast(report_date as varchar),
            cast(announced_date as varchar)
        )
    ) as position_id,
    holding_source,
    holder_id,
    holder_name,
    holder_type,
    security_id,
    report_date,
    announced_date,
    holding_amount,
    holding_ratio,
    holding_float_ratio,
    holding_change,
    market_value,
    exchange,
    cast('holding_position' as varchar) as dataset,
    concat('holding_position:', cast(report_date as varchar)) as snapshot_id,
    announced_date as as_of_date
from holding_positions
