{{ config(materialized="table") }}

select
    ts_code as security_id,
    trade_date,
    name as security_name,
    market_type,
    try_cast(rank as integer) as rank,
    try_cast(close as decimal(38, 18)) as close,
    try_cast(change as decimal(38, 18)) as change,
    try_cast(amount as decimal(38, 18)) as amount,
    try_cast(net_amount as decimal(38, 18)) as net_amount,
    try_cast(buy as decimal(38, 18)) as buy_amount,
    try_cast(sell as decimal(38, 18)) as sell_amount
from {{ ref('stg_hsgt_top10') }}
