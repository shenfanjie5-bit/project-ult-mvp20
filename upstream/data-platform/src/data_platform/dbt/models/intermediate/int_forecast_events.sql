{{ config(materialized="table") }}

select
    ts_code,
    ann_date,
    end_date,
    "type" as forecast_type,
    p_change_min,
    p_change_max,
    net_profit_min,
    net_profit_max,
    last_parent_net,
    first_ann_date,
    summary,
    change_reason,
    update_flag,
    source_run_id,
    raw_loaded_at
from {{ ref('stg_forecast') }}
