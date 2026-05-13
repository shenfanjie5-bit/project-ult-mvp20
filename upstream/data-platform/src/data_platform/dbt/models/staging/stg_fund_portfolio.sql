{{ config(materialized="view") }}

{{ stg_latest_raw(
    "tushare",
    "fund_portfolio",
    [
        "ts_code",
        "ann_date",
        "end_date",
        "symbol",
        "mkv",
        "amount",
        "stk_mkv_ratio",
        "stk_float_ratio"
    ],
    [
        "cast(nullif(trim(cast(\"ts_code\" as varchar)), '') as varchar) as \"ts_code\"",
        "strptime(nullif(trim(cast(\"ann_date\" as varchar)), ''), '%Y%m%d')::date as \"ann_date\"",
        "strptime(nullif(trim(cast(\"end_date\" as varchar)), ''), '%Y%m%d')::date as \"end_date\"",
        "cast(nullif(trim(cast(\"symbol\" as varchar)), '') as varchar) as \"symbol\"",
        "cast(nullif(trim(cast(\"mkv\" as varchar)), '') as varchar) as \"mkv\"",
        "cast(nullif(trim(cast(\"amount\" as varchar)), '') as varchar) as \"amount\"",
        "cast(nullif(trim(cast(\"stk_mkv_ratio\" as varchar)), '') as varchar) as \"stk_mkv_ratio\"",
        "cast(nullif(trim(cast(\"stk_float_ratio\" as varchar)), '') as varchar) as \"stk_float_ratio\""
    ]
) }}
