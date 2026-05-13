{{ config(materialized="view") }}

{{ stg_latest_raw(
    "tushare",
    "hm_detail",
    [
        "trade_date",
        "ts_code",
        "ts_name",
        "buy_amount",
        "sell_amount",
        "net_amount",
        "hm_name",
        "hm_orgs"
    ],
    [
        "strptime(nullif(trim(cast(\"trade_date\" as varchar)), ''), '%Y%m%d')::date as \"trade_date\"",
        "cast(nullif(trim(cast(\"ts_code\" as varchar)), '') as varchar) as \"ts_code\"",
        "cast(nullif(trim(cast(\"ts_name\" as varchar)), '') as varchar) as \"ts_name\"",
        "cast(nullif(trim(cast(\"buy_amount\" as varchar)), '') as varchar) as \"buy_amount\"",
        "cast(nullif(trim(cast(\"sell_amount\" as varchar)), '') as varchar) as \"sell_amount\"",
        "cast(nullif(trim(cast(\"net_amount\" as varchar)), '') as varchar) as \"net_amount\"",
        "cast(nullif(trim(cast(\"hm_name\" as varchar)), '') as varchar) as \"hm_name\"",
        "cast(nullif(trim(cast(\"hm_orgs\" as varchar)), '') as varchar) as \"hm_orgs\""
    ]
) }}
