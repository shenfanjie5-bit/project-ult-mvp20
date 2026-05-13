{{ config(materialized="table") }}

with index_daily_with_exchange as (
    select
        ts_code,
        trade_date,
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
        raw_loaded_at,
        case
            when upper(ts_code) like '%.SH' then 'SSE'
            when upper(ts_code) like '%.SZ' then 'SZSE'
            when upper(ts_code) like '%.BJ' then 'BSE'
            else null
        end as calendar_exchange
    from {{ ref('stg_index_daily') }}
),

trade_calendar as (
    select
        exchange,
        upper(exchange) as calendar_exchange,
        cal_date,
        is_open,
        pretrade_date,
        source_run_id,
        raw_loaded_at
    from (
        select
            exchange,
            cal_date,
            is_open,
            pretrade_date,
            source_run_id,
            raw_loaded_at,
            row_number() over (
                partition by cal_date, upper(exchange)
                order by raw_loaded_at desc nulls last,
                         source_run_id desc nulls last
            ) as calendar_rank
        from {{ ref('stg_trade_cal') }}
        where exchange is not null
    )
    where calendar_rank = 1
)

select
    index_daily.ts_code as index_code,
    index_daily.trade_date,
    index_daily.open,
    index_daily.high,
    index_daily.low,
    index_daily.close,
    index_daily.pre_close,
    index_daily.change,
    index_daily.pct_chg,
    index_daily.vol,
    index_daily.amount,
    trade_cal.exchange,
    trade_cal.is_open,
    trade_cal.pretrade_date,
    coalesce(index_daily.source_run_id, trade_cal.source_run_id) as source_run_id,
    coalesce(index_daily.raw_loaded_at, trade_cal.raw_loaded_at) as raw_loaded_at
from index_daily_with_exchange as index_daily
left join trade_calendar as trade_cal
    on index_daily.trade_date = trade_cal.cal_date
    and index_daily.calendar_exchange = trade_cal.calendar_exchange
