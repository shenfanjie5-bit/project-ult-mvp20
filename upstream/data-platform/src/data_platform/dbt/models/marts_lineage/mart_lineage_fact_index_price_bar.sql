{{ config(materialized="table") }}

-- Provider-aware lineage rows for canonical_v2.fact_index_price_bar, joined
-- on (index_id, trade_date). int_index_price_bars is sourced from the Tushare
-- index_daily interface (legacy_typed_not_in_catalog per registry).

select
    index_code as index_id,
    trade_date,
    cast('tushare' as varchar) as source_provider,
    cast('index_daily' as varchar) as source_interface_id,
    source_run_id,
    raw_loaded_at
from {{ ref('int_index_price_bars') }}
