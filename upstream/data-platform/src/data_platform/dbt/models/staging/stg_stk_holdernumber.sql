{{ config(materialized="view") }}

{{ stg_latest_raw(
    "tushare",
    "stk_holdernumber",
    [
        "ts_code",
        "ann_date",
        "end_date",
        "holder_num"
    ],
    [
        "cast(nullif(trim(cast(\"ts_code\" as varchar)), '') as varchar) as \"ts_code\"",
        "strptime(nullif(trim(cast(\"ann_date\" as varchar)), ''), '%Y%m%d')::date as \"ann_date\"",
        "strptime(nullif(trim(cast(\"end_date\" as varchar)), ''), '%Y%m%d')::date as \"end_date\"",
        "cast(nullif(trim(cast(\"holder_num\" as varchar)), '') as varchar) as \"holder_num\""
    ]
) }}
