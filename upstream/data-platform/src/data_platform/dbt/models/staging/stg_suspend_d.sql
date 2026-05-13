{{ config(materialized="view") }}

{{ stg_latest_raw(
    "tushare",
    "suspend_d",
    [
        "ts_code",
        "trade_date",
        "suspend_timing",
        "suspend_type"
    ],
    [
        "cast(nullif(trim(cast(\"ts_code\" as varchar)), '') as varchar) as \"ts_code\"",
        "strptime(nullif(trim(cast(\"trade_date\" as varchar)), ''), '%Y%m%d')::date as \"trade_date\"",
        "cast(nullif(trim(cast(\"suspend_timing\" as varchar)), '') as varchar) as \"suspend_timing\"",
        "cast(nullif(trim(cast(\"suspend_type\" as varchar)), '') as varchar) as \"suspend_type\""
    ]
) }}
