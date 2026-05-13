{{ config(materialized="table") }}

with members as (
    select
        index_code,
        index_name,
        con_code,
        con_name,
        in_date as valid_from,
        out_date as valid_to,
        is_new,
        source_run_id,
        raw_loaded_at
    from {{ ref('stg_index_member') }}
),

weights as (
    select
        index_code,
        con_code,
        trade_date,
        weight,
        source_run_id,
        raw_loaded_at
    from {{ ref('stg_index_weight') }}
),

membership_weights as (
    select
        members.index_code,
        members.index_name,
        members.con_code,
        members.con_name,
        members.valid_from,
        members.valid_to,
        weights.trade_date,
        coalesce(weights.trade_date, members.valid_from) as effective_date,
        weights.weight,
        members.is_new,
        coalesce(weights.source_run_id, members.source_run_id) as source_run_id,
        coalesce(weights.raw_loaded_at, members.raw_loaded_at) as raw_loaded_at,
        members.source_run_id as index_member_source_run_id,
        weights.source_run_id as index_weight_source_run_id,
        members.raw_loaded_at as index_member_raw_loaded_at,
        weights.raw_loaded_at as index_weight_raw_loaded_at
    from members
    left join weights
        on members.index_code = weights.index_code
        and members.con_code = weights.con_code
        and weights.trade_date >= members.valid_from
        and (
            members.valid_to is null
            or weights.trade_date <= members.valid_to
        )
),

unmatched_weights as (
    select
        weights.index_code,
        cast(null as varchar) as index_name,
        weights.con_code,
        cast(null as varchar) as con_name,
        cast(null as date) as valid_from,
        cast(null as date) as valid_to,
        weights.trade_date,
        weights.trade_date as effective_date,
        weights.weight,
        cast(null as varchar) as is_new,
        weights.source_run_id,
        weights.raw_loaded_at,
        cast(null as varchar) as index_member_source_run_id,
        weights.source_run_id as index_weight_source_run_id,
        cast(null as timestamp) as index_member_raw_loaded_at,
        weights.raw_loaded_at as index_weight_raw_loaded_at
    from weights
    left join members
        on members.index_code = weights.index_code
        and members.con_code = weights.con_code
        and weights.trade_date >= members.valid_from
        and (
            members.valid_to is null
            or weights.trade_date <= members.valid_to
        )
    where members.index_code is null
),

combined as (
    select
        index_code,
        index_name,
        con_code,
        con_name,
        valid_from,
        valid_to,
        trade_date,
        effective_date,
        weight,
        is_new,
        source_run_id,
        raw_loaded_at,
        index_member_source_run_id,
        index_weight_source_run_id,
        index_member_raw_loaded_at,
        index_weight_raw_loaded_at
    from membership_weights
    union all
    select
        index_code,
        index_name,
        con_code,
        con_name,
        valid_from,
        valid_to,
        trade_date,
        effective_date,
        weight,
        is_new,
        source_run_id,
        raw_loaded_at,
        index_member_source_run_id,
        index_weight_source_run_id,
        index_member_raw_loaded_at,
        index_weight_raw_loaded_at
    from unmatched_weights
)

select
    combined.index_code,
    combined.con_code,
    combined.trade_date,
    combined.effective_date,
    combined.valid_from,
    combined.valid_to,
    combined.weight,
    coalesce(combined.index_name, index_basic.name) as index_name,
    combined.con_name,
    index_basic.market as index_market,
    index_basic.category as index_category,
    combined.is_new,
    combined.source_run_id,
    combined.raw_loaded_at,
    index_basic.source_run_id as index_basic_source_run_id,
    combined.index_member_source_run_id,
    combined.index_weight_source_run_id,
    index_basic.raw_loaded_at as index_basic_raw_loaded_at,
    combined.index_member_raw_loaded_at,
    combined.index_weight_raw_loaded_at
from combined
left join {{ ref('stg_index_basic') }} as index_basic
    on combined.index_code = index_basic.ts_code
