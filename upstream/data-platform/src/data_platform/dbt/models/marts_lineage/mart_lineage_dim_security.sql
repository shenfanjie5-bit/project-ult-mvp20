{{ config(materialized="table") }}

-- Provider-aware lineage row, 1:1 with canonical_v2.dim_security on
-- security_id. dim_security is assembled from multiple Tushare staging
-- interfaces in int_security_master; source_interface_id and source_run_id are
-- component-aware so company/namechange lineage is not collapsed into the
-- stock_basic run.
-- Per M1-A design §3.

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
