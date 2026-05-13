{{ config(materialized="table") }}

-- Provider-neutral canonical_v2 fact_forecast_event mart. Aliases provider-
-- shaped identifier and date columns to the canonical names declared in the
-- provider catalog field_mapping for the forecast interface (security id,
-- announcement_date, report_period). Keeps update_flag as part of the forecast
-- event identity. Drops raw-zone lineage columns (they live on
-- mart_lineage_fact_forecast_event.sql).

select
    ts_code as security_id,
    ann_date as announcement_date,
    end_date as report_period,
    forecast_type,
    cast(nullif(trim(cast(p_change_min as varchar)), '') as decimal(38, 18))
        as p_change_min,
    cast(nullif(trim(cast(p_change_max as varchar)), '') as decimal(38, 18))
        as p_change_max,
    cast(nullif(trim(cast(net_profit_min as varchar)), '') as decimal(38, 18))
        as net_profit_min,
    cast(nullif(trim(cast(net_profit_max as varchar)), '') as decimal(38, 18))
        as net_profit_max,
    cast(nullif(trim(cast(last_parent_net as varchar)), '') as decimal(38, 18))
        as last_parent_net,
    first_ann_date,
    summary,
    change_reason,
    update_flag
from {{ ref('int_forecast_events') }}
