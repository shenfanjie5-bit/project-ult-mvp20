{{ config(materialized="table") }}

with bars as (
    select
        ts_code,
        trade_date,
        'daily' as freq,
        'daily' as price_source_interface_id,
        open,
        high,
        low,
        close,
        pre_close,
        change,
        pct_chg,
        vol,
        amount,
        source_run_id,
        raw_loaded_at
    from {{ ref('stg_daily') }}

    union all

    select
        ts_code,
        trade_date,
        'weekly' as freq,
        'weekly' as price_source_interface_id,
        open,
        high,
        low,
        close,
        pre_close,
        change,
        pct_chg,
        vol,
        amount,
        source_run_id,
        raw_loaded_at
    from {{ ref('stg_weekly') }}

    union all

    select
        ts_code,
        trade_date,
        'monthly' as freq,
        'monthly' as price_source_interface_id,
        open,
        high,
        low,
        close,
        pre_close,
        change,
        pct_chg,
        vol,
        amount,
        source_run_id,
        raw_loaded_at
    from {{ ref('stg_monthly') }}
),

adj_factor as (
    select
        ts_code,
        trade_date,
        adj_factor,
        source_run_id,
        raw_loaded_at
    from {{ ref('stg_adj_factor') }}
)

select
    bars.ts_code,
    bars.trade_date,
    bars.freq,
    bars.price_source_interface_id,
    bars.open,
    bars.high,
    bars.low,
    bars.close,
    bars.pre_close,
    bars.change,
    bars.pct_chg,
    bars.vol,
    bars.amount,
    adj_factor.adj_factor,
    bars.source_run_id,
    bars.raw_loaded_at,
    bars.source_run_id as price_bar_source_run_id,
    bars.raw_loaded_at as price_bar_raw_loaded_at,
    adj_factor.source_run_id as adj_factor_source_run_id,
    adj_factor.raw_loaded_at as adj_factor_raw_loaded_at
from bars
left join adj_factor
    on bars.ts_code = adj_factor.ts_code
    and bars.trade_date = adj_factor.trade_date
