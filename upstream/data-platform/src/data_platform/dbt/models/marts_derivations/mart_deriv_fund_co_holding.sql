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

security_counts as (
    select
        report_date,
        security_id,
        count(distinct holder_id) as fund_count
    from fund_security_positions
    group by report_date, security_id
),

fund_pairs as (
    select
        left_position.report_date,
        left_position.security_id as security_id_left,
        right_position.security_id as security_id_right,
        left_position.holder_id,
        greatest(
            left_position.latest_announced_date,
            right_position.latest_announced_date
        ) as latest_announced_date
    from fund_security_positions as left_position
    inner join fund_security_positions as right_position
        on left_position.report_date = right_position.report_date
        and left_position.holder_id = right_position.holder_id
        and left_position.security_id < right_position.security_id
),

co_holding_rows as (
    select
        fund_pairs.report_date,
        fund_pairs.security_id_left,
        fund_pairs.security_id_right,
        count(distinct fund_pairs.holder_id) as co_holding_fund_count,
        left_counts.fund_count as security_left_fund_count,
        right_counts.fund_count as security_right_fund_count,
        cast(count(distinct fund_pairs.holder_id) as double)
            / nullif(
                left_counts.fund_count
                + right_counts.fund_count
                - count(distinct fund_pairs.holder_id),
                0
            ) as jaccard_score,
        max(fund_pairs.latest_announced_date) as latest_announced_date
    from fund_pairs
    inner join security_counts as left_counts
        on fund_pairs.report_date = left_counts.report_date
        and fund_pairs.security_id_left = left_counts.security_id
    inner join security_counts as right_counts
        on fund_pairs.report_date = right_counts.report_date
        and fund_pairs.security_id_right = right_counts.security_id
    group by
        fund_pairs.report_date,
        fund_pairs.security_id_left,
        fund_pairs.security_id_right,
        left_counts.fund_count,
        right_counts.fund_count
)

select
    md5(
        concat_ws(
            '|',
            cast(report_date as varchar),
            security_id_left,
            security_id_right
        )
    ) as mart_key,
    md5(
        concat_ws(
            '|',
            cast(report_date as varchar),
            security_id_left,
            security_id_right
        )
    ) as row_id,
    report_date,
    security_id_left,
    security_id_right,
    co_holding_fund_count,
    security_left_fund_count,
    security_right_fund_count,
    jaccard_score,
    latest_announced_date,
    concat(
        'mart_deriv_fund_co_holding:',
        md5(
            concat_ws(
                '|',
                cast(report_date as varchar),
                security_id_left,
                security_id_right
            )
        )
    ) as evidence_ref
from co_holding_rows
