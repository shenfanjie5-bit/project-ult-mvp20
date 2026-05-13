{{ config(materialized="table") }}

with top_holder_positions as (
    select
        holding_source,
        holder_id,
        security_id,
        report_date,
        announced_date,
        holding_amount,
        holding_ratio
    from {{ ref('mart_fact_holding_position_v2') }}
    where holding_source in ('top_holder', 'top_float_holder')
),

latest_report_positions as (
    select
        holding_source,
        holder_id,
        security_id,
        report_date,
        announced_date,
        holding_amount,
        holding_ratio
    from (
        select
            top_holder_positions.*,
            row_number() over (
                partition by holding_source, holder_id, security_id, report_date
                order by announced_date desc
            ) as announcement_rank
        from top_holder_positions
    ) as ranked_positions
    where announcement_rank = 1
),

period_changes as (
    select
        holding_source,
        holder_id,
        security_id,
        report_date,
        announced_date,
        holding_amount,
        holding_ratio,
        lag(report_date) over (
            partition by holding_source, holder_id, security_id
            order by report_date
        ) as previous_report_date,
        lag(announced_date) over (
            partition by holding_source, holder_id, security_id
            order by report_date
        ) as previous_announced_date,
        lag(holding_amount) over (
            partition by holding_source, holder_id, security_id
            order by report_date
        ) as previous_holding_amount,
        lag(holding_ratio) over (
            partition by holding_source, holder_id, security_id
            order by report_date
        ) as previous_holding_ratio
    from latest_report_positions
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
    ) as mart_key,
    holding_source,
    holder_id,
    security_id,
    report_date,
    announced_date,
    previous_report_date,
    previous_announced_date,
    holding_amount,
    previous_holding_amount,
    holding_amount - previous_holding_amount as holding_amount_delta,
    case
        when previous_holding_amount is null or previous_holding_amount = 0
            then cast(null as decimal(38, 18))
        else (holding_amount - previous_holding_amount) / previous_holding_amount
    end as holding_amount_delta_pct,
    holding_ratio,
    previous_holding_ratio,
    holding_ratio - previous_holding_ratio as holding_ratio_delta
from period_changes
