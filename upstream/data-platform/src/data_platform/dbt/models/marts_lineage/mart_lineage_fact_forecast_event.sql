{{ config(materialized="table") }}

-- Provider-aware lineage rows for canonical_v2.fact_forecast_event, joined on
-- (security_id, announcement_date, report_period, update_flag, forecast_type).
-- int_forecast_events is sourced from the Tushare forecast interface (with
-- update_flag + forecast_type as row discriminators).

select
    ts_code as security_id,
    ann_date as announcement_date,
    end_date as report_period,
    update_flag,
    forecast_type,
    cast('tushare' as varchar) as source_provider,
    cast('forecast' as varchar) as source_interface_id,
    source_run_id,
    raw_loaded_at
from {{ ref('int_forecast_events') }}
