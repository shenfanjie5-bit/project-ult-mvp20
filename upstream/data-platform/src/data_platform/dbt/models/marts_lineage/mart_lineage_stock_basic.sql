{{ config(materialized="table") }}

-- Provider-aware lineage rows for canonical_v2.stock_basic, joined 1:1 on
-- security_id. Mirrors the int_security_master path that feeds stock_basic
-- (the canonical_v2.stock_basic mart is a thin projection of the same
-- intermediate view), with component-aware run lineage.

select
    ts_code as security_id,
    cast('tushare' as varchar) as source_provider,
    concat_ws(
        '+',
        'stock_basic',
        case when stock_company_source_run_id is not null then 'stock_company' end,
        case when namechange_source_run_id is not null then 'namechange' end
    ) as source_interface_id,
    concat_ws(
        '|',
        concat('stock_basic=', stock_basic_source_run_id),
        case
            when stock_company_source_run_id is not null
                then concat('stock_company=', stock_company_source_run_id)
        end,
        case
            when namechange_source_run_id is not null
                then concat('namechange=', namechange_source_run_id)
        end
    ) as source_run_id,
    greatest(
        stock_basic_raw_loaded_at,
        coalesce(stock_company_raw_loaded_at, stock_basic_raw_loaded_at),
        coalesce(namechange_raw_loaded_at, stock_basic_raw_loaded_at)
    ) as raw_loaded_at
from {{ ref('int_security_master') }}
