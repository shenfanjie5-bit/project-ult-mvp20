{{ config(materialized="table") }}

-- Provider-aware lineage rows for canonical_v2.fact_price_bar, joined on
-- (security_id, trade_date, freq). int_price_bars_adjusted combines a price-bar
-- source (daily/weekly/monthly per freq) with adj_factor; source_run_id records
-- both contributing raw runs when both are present.

select
    ts_code as security_id,
    trade_date,
    freq,
    cast('tushare' as varchar) as source_provider,
    concat_ws(
        '+',
        price_source_interface_id,
        case when adj_factor_source_run_id is not null then 'adj_factor' end
    ) as source_interface_id,
    concat_ws(
        '|',
        concat(price_source_interface_id, '=', price_bar_source_run_id),
        case
            when adj_factor_source_run_id is not null
                then concat('adj_factor=', adj_factor_source_run_id)
        end
    ) as source_run_id,
    greatest(
        price_bar_raw_loaded_at,
        coalesce(adj_factor_raw_loaded_at, price_bar_raw_loaded_at)
    ) as raw_loaded_at
from {{ ref('int_price_bars_adjusted') }}
