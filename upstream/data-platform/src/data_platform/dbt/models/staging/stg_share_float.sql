{{ config(materialized="view") }}

{{ stg_latest_raw(
    "tushare",
    "share_float",
    [
        "ts_code",
        "ann_date",
        "float_date",
        "float_share",
        "float_ratio",
        "holder_name",
        "share_type"
    ],
    [
        "cast(nullif(trim(cast(\"ts_code\" as varchar)), '') as varchar) as \"ts_code\"",
        "strptime(nullif(trim(cast(\"ann_date\" as varchar)), ''), '%Y%m%d')::date as \"ann_date\"",
        "strptime(nullif(trim(cast(\"float_date\" as varchar)), ''), '%Y%m%d')::date as \"float_date\"",
        "cast(nullif(trim(cast(\"float_share\" as varchar)), '') as varchar) as \"float_share\"",
        "cast(nullif(trim(cast(\"float_ratio\" as varchar)), '') as varchar) as \"float_ratio\"",
        "cast(nullif(trim(cast(\"holder_name\" as varchar)), '') as varchar) as \"holder_name\"",
        "cast(nullif(trim(cast(\"share_type\" as varchar)), '') as varchar) as \"share_type\""
    ]
) }}
