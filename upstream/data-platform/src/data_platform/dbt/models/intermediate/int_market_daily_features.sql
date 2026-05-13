{{ config(materialized="table") }}

with market_keys as (
    select ts_code, trade_date
    from {{ ref('stg_daily_basic') }}

    union

    select ts_code, trade_date
    from {{ ref('stg_stk_limit') }}

    union

    select ts_code, trade_date
    from {{ ref('stg_moneyflow') }}
)

select
    market_keys.ts_code,
    market_keys.trade_date,
    daily_basic.close,
    daily_basic.turnover_rate,
    daily_basic.turnover_rate_f,
    daily_basic.volume_ratio,
    daily_basic.pe,
    daily_basic.pe_ttm,
    daily_basic.pb,
    daily_basic.ps,
    daily_basic.ps_ttm,
    daily_basic.dv_ratio,
    daily_basic.dv_ttm,
    daily_basic.total_share,
    daily_basic.float_share,
    daily_basic.free_share,
    daily_basic.total_mv,
    daily_basic.circ_mv,
    stk_limit.up_limit,
    stk_limit.down_limit,
    moneyflow.buy_sm_vol,
    moneyflow.buy_sm_amount,
    moneyflow.sell_sm_vol,
    moneyflow.sell_sm_amount,
    moneyflow.buy_md_vol,
    moneyflow.buy_md_amount,
    moneyflow.sell_md_vol,
    moneyflow.sell_md_amount,
    moneyflow.buy_lg_vol,
    moneyflow.buy_lg_amount,
    moneyflow.sell_lg_vol,
    moneyflow.sell_lg_amount,
    moneyflow.buy_elg_vol,
    moneyflow.buy_elg_amount,
    moneyflow.sell_elg_vol,
    moneyflow.sell_elg_amount,
    moneyflow.net_mf_vol,
    moneyflow.net_mf_amount,
    coalesce(
        daily_basic.source_run_id,
        stk_limit.source_run_id,
        moneyflow.source_run_id
    ) as source_run_id,
    coalesce(
        daily_basic.raw_loaded_at,
        stk_limit.raw_loaded_at,
        moneyflow.raw_loaded_at
    ) as raw_loaded_at,
    daily_basic.source_run_id as daily_basic_source_run_id,
    stk_limit.source_run_id as stk_limit_source_run_id,
    moneyflow.source_run_id as moneyflow_source_run_id,
    daily_basic.raw_loaded_at as daily_basic_raw_loaded_at,
    stk_limit.raw_loaded_at as stk_limit_raw_loaded_at,
    moneyflow.raw_loaded_at as moneyflow_raw_loaded_at
from market_keys
left join {{ ref('stg_daily_basic') }} as daily_basic
    on market_keys.ts_code = daily_basic.ts_code
    and market_keys.trade_date = daily_basic.trade_date
left join {{ ref('stg_stk_limit') }} as stk_limit
    on market_keys.ts_code = stk_limit.ts_code
    and market_keys.trade_date = stk_limit.trade_date
left join {{ ref('stg_moneyflow') }} as moneyflow
    on market_keys.ts_code = moneyflow.ts_code
    and market_keys.trade_date = moneyflow.trade_date
