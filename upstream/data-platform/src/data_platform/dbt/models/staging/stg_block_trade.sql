{{ config(materialized="view") }}

{{ stg_latest_raw(
    "tushare",
    "block_trade",
    [
        "ts_code",
        "trade_date",
        "price",
        "vol",
        "amount",
        "buyer",
        "seller"
    ],
    [
        "cast(nullif(trim(cast(\"ts_code\" as varchar)), '') as varchar) as \"ts_code\"",
        "strptime(nullif(trim(cast(\"trade_date\" as varchar)), ''), '%Y%m%d')::date as \"trade_date\"",
        "cast(nullif(trim(cast(\"price\" as varchar)), '') as varchar) as \"price\"",
        "cast(nullif(trim(cast(\"vol\" as varchar)), '') as varchar) as \"vol\"",
        "cast(nullif(trim(cast(\"amount\" as varchar)), '') as varchar) as \"amount\"",
        "cast(nullif(trim(cast(\"buyer\" as varchar)), '') as varchar) as \"buyer\"",
        "cast(nullif(trim(cast(\"seller\" as varchar)), '') as varchar) as \"seller\""
    ]
) }}
