{{ config(materialized="view") }}

{{ stg_latest_raw(
    "tushare",
    "trade_cal",
    [
        "exchange",
        "cal_date",
        "is_open",
        "pretrade_date"
    ],
    [
        "cast(nullif(trim(cast(\"exchange\" as varchar)), '') as varchar) as \"exchange\"",
        "strptime(nullif(trim(cast(\"cal_date\" as varchar)), ''), '%Y%m%d')::date as \"cal_date\"",
        "cast(nullif(trim(cast(\"is_open\" as varchar)), '') as varchar) as \"is_open\"",
        "strptime(nullif(trim(cast(\"pretrade_date\" as varchar)), ''), '%Y%m%d')::date as \"pretrade_date\""
    ]
) }}
