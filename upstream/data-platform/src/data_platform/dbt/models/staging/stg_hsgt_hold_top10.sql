{{ config(materialized="view") }}

{{ stg_latest_raw(
    "tushare",
    "hsgt_hold_top10",
    [
        "code",
        "trade_date",
        "ts_code",
        "name",
        "vol",
        "ratio",
        "exchange"
    ],
    [
        "cast(nullif(trim(cast(\"code\" as varchar)), '') as varchar) as \"code\"",
        "strptime(nullif(trim(cast(\"trade_date\" as varchar)), ''), '%Y%m%d')::date as \"trade_date\"",
        "cast(nullif(trim(cast(\"ts_code\" as varchar)), '') as varchar) as \"ts_code\"",
        "cast(nullif(trim(cast(\"name\" as varchar)), '') as varchar) as \"name\"",
        "cast(nullif(trim(cast(\"vol\" as varchar)), '') as varchar) as \"vol\"",
        "cast(nullif(trim(cast(\"ratio\" as varchar)), '') as varchar) as \"ratio\"",
        "cast(nullif(trim(cast(\"exchange\" as varchar)), '') as varchar) as \"exchange\""
    ]
) }}
