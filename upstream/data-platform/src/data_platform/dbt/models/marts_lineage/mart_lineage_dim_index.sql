{{ config(materialized="table") }}

-- Provider-aware lineage rows for canonical_v2.dim_index, joined 1:1 on
-- index_id. dim_index is derived from index membership data (Tushare
-- index_basic plus index_member / index_weight membership data); source_run_id
-- records each contributing raw run that exists for the row.

select
    index_id,
    cast('tushare' as varchar) as source_provider,
    concat_ws(
        '+',
        case when max(index_basic_source_run_id) is not null then 'index_basic' end,
        case when max(index_member_source_run_id) is not null then 'index_member' end,
        case when max(index_weight_source_run_id) is not null then 'index_weight' end
    ) as source_interface_id,
    concat_ws(
        '|',
        case
            when max(index_basic_source_run_id) is not null
                then concat('index_basic=', max(index_basic_source_run_id))
        end,
        case
            when max(index_member_source_run_id) is not null
                then concat('index_member=', max(index_member_source_run_id))
        end,
        case
            when max(index_weight_source_run_id) is not null
                then concat('index_weight=', max(index_weight_source_run_id))
        end
    ) as source_run_id,
    greatest(
        coalesce(max(index_basic_raw_loaded_at), timestamp '1970-01-01 00:00:00'),
        coalesce(max(index_member_raw_loaded_at), timestamp '1970-01-01 00:00:00'),
        coalesce(max(index_weight_raw_loaded_at), timestamp '1970-01-01 00:00:00')
    ) as raw_loaded_at
from (
    select
        index_code as index_id,
        index_basic_source_run_id,
        index_member_source_run_id,
        index_weight_source_run_id,
        index_basic_raw_loaded_at,
        index_member_raw_loaded_at,
        index_weight_raw_loaded_at
    from {{ ref('int_index_membership') }}
) renamed
where index_id is not null
group by index_id
