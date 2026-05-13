{{ config(materialized="view") }}

{{ stg_latest_raw(
    "tushare",
    "hsgt_top10",
    [
        "trade_date",
        "ts_code",
        "name",
        "close",
        "change",
        "rank",
        "market_type",
        "amount",
        "net_amount",
        "buy",
        "sell"
    ],
    [
        "strptime(nullif(trim(cast(\"trade_date\" as varchar)), ''), '%Y%m%d')::date as \"trade_date\"",
        "cast(nullif(trim(cast(\"ts_code\" as varchar)), '') as varchar) as \"ts_code\"",
        "cast(nullif(trim(cast(\"name\" as varchar)), '') as varchar) as \"name\"",
        "cast(nullif(trim(cast(\"close\" as varchar)), '') as varchar) as \"close\"",
        "cast(nullif(trim(cast(\"change\" as varchar)), '') as varchar) as \"change\"",
        "cast(nullif(trim(cast(\"rank\" as varchar)), '') as varchar) as \"rank\"",
        "cast(nullif(trim(cast(\"market_type\" as varchar)), '') as varchar) as \"market_type\"",
        "cast(nullif(trim(cast(\"amount\" as varchar)), '') as varchar) as \"amount\"",
        "cast(nullif(trim(cast(\"net_amount\" as varchar)), '') as varchar) as \"net_amount\"",
        "cast(nullif(trim(cast(\"buy\" as varchar)), '') as varchar) as \"buy\"",
        "cast(nullif(trim(cast(\"sell\" as varchar)), '') as varchar) as \"sell\""
    ]
) }}
