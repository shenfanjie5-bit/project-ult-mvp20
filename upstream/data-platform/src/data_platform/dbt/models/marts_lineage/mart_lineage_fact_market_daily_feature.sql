{{ config(materialized="table") }}

-- Provider-aware lineage rows for canonical_v2.fact_market_daily_feature,
-- joined on (security_id, trade_date). int_market_daily_features combines the
-- Tushare daily_basic, stk_limit, and moneyflow interfaces; source_run_id
-- records each contributing raw run that exists for the row.

select
    ts_code as security_id,
    trade_date,
    cast('tushare' as varchar) as source_provider,
    concat_ws(
        '+',
        case when daily_basic_source_run_id is not null then 'daily_basic' end,
        case when stk_limit_source_run_id is not null then 'stk_limit' end,
        case when moneyflow_source_run_id is not null then 'moneyflow' end
    ) as source_interface_id,
    concat_ws(
        '|',
        case
            when daily_basic_source_run_id is not null
                then concat('daily_basic=', daily_basic_source_run_id)
        end,
        case
            when stk_limit_source_run_id is not null
                then concat('stk_limit=', stk_limit_source_run_id)
        end,
        case
            when moneyflow_source_run_id is not null
                then concat('moneyflow=', moneyflow_source_run_id)
        end
    ) as source_run_id,
    greatest(
        coalesce(daily_basic_raw_loaded_at, timestamp '1970-01-01 00:00:00'),
        coalesce(stk_limit_raw_loaded_at, timestamp '1970-01-01 00:00:00'),
        coalesce(moneyflow_raw_loaded_at, timestamp '1970-01-01 00:00:00')
    ) as raw_loaded_at
from {{ ref('int_market_daily_features') }}
