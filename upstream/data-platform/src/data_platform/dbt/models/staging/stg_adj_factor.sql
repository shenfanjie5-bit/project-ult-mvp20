{{ config(materialized="view") }}

{{ stg_latest_raw(
    "tushare",
    "adj_factor",
    [
        "ts_code",
        "trade_date",
        "adj_factor"
    ],
    [
        "cast(nullif(trim(cast(\"ts_code\" as varchar)), '') as varchar) as \"ts_code\"",
        "strptime(nullif(trim(cast(\"trade_date\" as varchar)), ''), '%Y%m%d')::date as \"trade_date\"",
        "cast(nullif(trim(cast(\"adj_factor\" as varchar)), '') as varchar) as \"adj_factor\""
    ]
) }}
