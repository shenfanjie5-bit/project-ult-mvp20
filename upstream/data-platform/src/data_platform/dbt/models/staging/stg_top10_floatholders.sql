{{ config(materialized="view") }}

{{ stg_latest_raw(
    "tushare",
    "top10_floatholders",
    [
        "ts_code",
        "ann_date",
        "end_date",
        "holder_name",
        "hold_amount",
        "hold_ratio",
        "hold_float_ratio",
        "hold_change",
        "holder_type"
    ],
    [
        "cast(nullif(trim(cast(\"ts_code\" as varchar)), '') as varchar) as \"ts_code\"",
        "strptime(nullif(trim(cast(\"ann_date\" as varchar)), ''), '%Y%m%d')::date as \"ann_date\"",
        "strptime(nullif(trim(cast(\"end_date\" as varchar)), ''), '%Y%m%d')::date as \"end_date\"",
        "cast(nullif(trim(cast(\"holder_name\" as varchar)), '') as varchar) as \"holder_name\"",
        "cast(nullif(trim(cast(\"hold_amount\" as varchar)), '') as varchar) as \"hold_amount\"",
        "cast(nullif(trim(cast(\"hold_ratio\" as varchar)), '') as varchar) as \"hold_ratio\"",
        "cast(nullif(trim(cast(\"hold_float_ratio\" as varchar)), '') as varchar) as \"hold_float_ratio\"",
        "cast(nullif(trim(cast(\"hold_change\" as varchar)), '') as varchar) as \"hold_change\"",
        "cast(nullif(trim(cast(\"holder_type\" as varchar)), '') as varchar) as \"holder_type\""
    ],
    request_scoped=true
) }}
