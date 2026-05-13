{{ config(materialized="table") }}

with latest_namechange as (
    select
        ts_code,
        name,
        start_date,
        end_date,
        ann_date,
        change_reason,
        source_run_id,
        raw_loaded_at
    from (
        select
            ts_code,
            name,
            start_date,
            end_date,
            ann_date,
            change_reason,
            source_run_id,
            raw_loaded_at,
            row_number() over (
                partition by ts_code
                order by coalesce(end_date, start_date, ann_date) desc nulls last,
                         raw_loaded_at desc nulls last,
                         source_run_id desc nulls last
            ) as namechange_rank
        from {{ ref('stg_namechange') }}
    )
    where namechange_rank = 1
)

select
    stock_basic.ts_code,
    stock_basic.symbol,
    stock_basic.name,
    stock_basic.market,
    stock_basic.industry,
    stock_basic.list_date,
    stock_basic.is_active,
    stock_basic.area,
    stock_basic.fullname,
    stock_basic.exchange,
    stock_basic.curr_type,
    stock_basic.list_status,
    stock_basic.delist_date,
    stock_company.setup_date,
    stock_company.province,
    stock_company.city,
    stock_company.reg_capital,
    stock_company.employees,
    stock_company.main_business,
    latest_namechange.name as latest_namechange_name,
    latest_namechange.start_date as latest_namechange_start_date,
    latest_namechange.end_date as latest_namechange_end_date,
    latest_namechange.ann_date as latest_namechange_ann_date,
    latest_namechange.change_reason as latest_namechange_reason,
    stock_basic.source_run_id,
    stock_basic.raw_loaded_at,
    stock_basic.source_run_id as stock_basic_source_run_id,
    stock_company.source_run_id as stock_company_source_run_id,
    latest_namechange.source_run_id as namechange_source_run_id,
    stock_basic.raw_loaded_at as stock_basic_raw_loaded_at,
    stock_company.raw_loaded_at as stock_company_raw_loaded_at,
    latest_namechange.raw_loaded_at as namechange_raw_loaded_at
from {{ ref('stg_stock_basic') }} as stock_basic
left join {{ ref('stg_stock_company') }} as stock_company
    on stock_basic.ts_code = stock_company.ts_code
left join latest_namechange
    on stock_basic.ts_code = latest_namechange.ts_code
