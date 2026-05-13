{{ config(materialized="view") }}

{{ stg_latest_raw(
    "tushare",
    "stk_limit",
    [
        "ts_code",
        "trade_date",
        "up_limit",
        "down_limit"
    ],
    [
        "cast(nullif(trim(cast(\"ts_code\" as varchar)), '') as varchar) as \"ts_code\"",
        "strptime(nullif(trim(cast(\"trade_date\" as varchar)), ''), '%Y%m%d')::date as \"trade_date\"",
        "cast(nullif(trim(cast(\"up_limit\" as varchar)), '') as varchar) as \"up_limit\"",
        "cast(nullif(trim(cast(\"down_limit\" as varchar)), '') as varchar) as \"down_limit\""
    ]
) }}
