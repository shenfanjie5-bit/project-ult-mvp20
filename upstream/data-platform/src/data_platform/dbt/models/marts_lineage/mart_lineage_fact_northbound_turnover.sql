{{ config(materialized="table") }}

select
    ts_code as security_id,
    trade_date,
    market_type,
    try_cast(rank as integer) as rank,
    cast('tushare' as varchar) as source_provider,
    cast('hsgt_top10' as varchar) as source_interface_id,
    source_run_id,
    raw_loaded_at
from {{ ref('stg_hsgt_top10') }}
