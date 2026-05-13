{{ config(materialized="view") }}

{{ stg_latest_raw(
    "tushare",
    "index_weight",
    [
        "index_code",
        "con_code",
        "trade_date",
        "weight"
    ],
    [
        "cast(nullif(trim(cast(\"index_code\" as varchar)), '') as varchar) as \"index_code\"",
        "cast(nullif(trim(cast(\"con_code\" as varchar)), '') as varchar) as \"con_code\"",
        "strptime(nullif(trim(cast(\"trade_date\" as varchar)), ''), '%Y%m%d')::date as \"trade_date\"",
        "cast(nullif(trim(cast(\"weight\" as varchar)), '') as varchar) as \"weight\""
    ]
) }}
