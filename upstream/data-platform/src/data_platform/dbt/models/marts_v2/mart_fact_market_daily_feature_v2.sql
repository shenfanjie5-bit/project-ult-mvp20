{{ config(materialized="table") }}

-- Provider-neutral canonical_v2 fact_market_daily_feature mart. Renames the
-- provider-shaped security identifier to the canonical security_id per the
-- provider catalog field_mapping; drops raw-zone lineage columns (they live
-- on mart_lineage_fact_market_daily_feature.sql). Partition decision on
-- trade_date is deferred to M2.1 per M1-B section 4.

select
    ts_code as security_id,
    trade_date,
    cast(nullif(trim(cast(close as varchar)), '') as decimal(38, 18)) as close,
    cast(nullif(trim(cast(turnover_rate as varchar)), '') as decimal(38, 18))
        as turnover_rate,
    cast(nullif(trim(cast(turnover_rate_f as varchar)), '') as decimal(38, 18))
        as turnover_rate_f,
    cast(nullif(trim(cast(volume_ratio as varchar)), '') as decimal(38, 18))
        as volume_ratio,
    cast(nullif(trim(cast(pe as varchar)), '') as decimal(38, 18)) as pe,
    cast(nullif(trim(cast(pe_ttm as varchar)), '') as decimal(38, 18)) as pe_ttm,
    cast(nullif(trim(cast(pb as varchar)), '') as decimal(38, 18)) as pb,
    cast(nullif(trim(cast(ps as varchar)), '') as decimal(38, 18)) as ps,
    cast(nullif(trim(cast(ps_ttm as varchar)), '') as decimal(38, 18)) as ps_ttm,
    cast(nullif(trim(cast(dv_ratio as varchar)), '') as decimal(38, 18)) as dv_ratio,
    cast(nullif(trim(cast(dv_ttm as varchar)), '') as decimal(38, 18)) as dv_ttm,
    cast(nullif(trim(cast(total_share as varchar)), '') as decimal(38, 18))
        as total_share,
    cast(nullif(trim(cast(float_share as varchar)), '') as decimal(38, 18))
        as float_share,
    cast(nullif(trim(cast(free_share as varchar)), '') as decimal(38, 18))
        as free_share,
    cast(nullif(trim(cast(total_mv as varchar)), '') as decimal(38, 18)) as total_mv,
    cast(nullif(trim(cast(circ_mv as varchar)), '') as decimal(38, 18)) as circ_mv,
    cast(nullif(trim(cast(up_limit as varchar)), '') as decimal(38, 18)) as up_limit,
    cast(nullif(trim(cast(down_limit as varchar)), '') as decimal(38, 18))
        as down_limit,
    cast(nullif(trim(cast(buy_sm_vol as varchar)), '') as decimal(38, 18))
        as buy_sm_vol,
    cast(nullif(trim(cast(buy_sm_amount as varchar)), '') as decimal(38, 18))
        as buy_sm_amount,
    cast(nullif(trim(cast(sell_sm_vol as varchar)), '') as decimal(38, 18))
        as sell_sm_vol,
    cast(nullif(trim(cast(sell_sm_amount as varchar)), '') as decimal(38, 18))
        as sell_sm_amount,
    cast(nullif(trim(cast(buy_md_vol as varchar)), '') as decimal(38, 18))
        as buy_md_vol,
    cast(nullif(trim(cast(buy_md_amount as varchar)), '') as decimal(38, 18))
        as buy_md_amount,
    cast(nullif(trim(cast(sell_md_vol as varchar)), '') as decimal(38, 18))
        as sell_md_vol,
    cast(nullif(trim(cast(sell_md_amount as varchar)), '') as decimal(38, 18))
        as sell_md_amount,
    cast(nullif(trim(cast(buy_lg_vol as varchar)), '') as decimal(38, 18))
        as buy_lg_vol,
    cast(nullif(trim(cast(buy_lg_amount as varchar)), '') as decimal(38, 18))
        as buy_lg_amount,
    cast(nullif(trim(cast(sell_lg_vol as varchar)), '') as decimal(38, 18))
        as sell_lg_vol,
    cast(nullif(trim(cast(sell_lg_amount as varchar)), '') as decimal(38, 18))
        as sell_lg_amount,
    cast(nullif(trim(cast(buy_elg_vol as varchar)), '') as decimal(38, 18))
        as buy_elg_vol,
    cast(nullif(trim(cast(buy_elg_amount as varchar)), '') as decimal(38, 18))
        as buy_elg_amount,
    cast(nullif(trim(cast(sell_elg_vol as varchar)), '') as decimal(38, 18))
        as sell_elg_vol,
    cast(nullif(trim(cast(sell_elg_amount as varchar)), '') as decimal(38, 18))
        as sell_elg_amount,
    cast(nullif(trim(cast(net_mf_vol as varchar)), '') as decimal(38, 18))
        as net_mf_vol,
    cast(nullif(trim(cast(net_mf_amount as varchar)), '') as decimal(38, 18))
        as net_mf_amount
from {{ ref('int_market_daily_features') }}
