{{ config(materialized="view") }}

{{ stg_latest_raw(
    "tushare",
    "stk_holdertrade",
    [
        "ts_code",
        "ann_date",
        "holder_name",
        "holder_type",
        "in_de",
        "change_vol",
        "change_ratio",
        "after_share",
        "after_ratio",
        "avg_price",
        "total_share"
    ],
    [
        "cast(nullif(trim(cast(\"ts_code\" as varchar)), '') as varchar) as \"ts_code\"",
        "strptime(nullif(trim(cast(\"ann_date\" as varchar)), ''), '%Y%m%d')::date as \"ann_date\"",
        "cast(nullif(trim(cast(\"holder_name\" as varchar)), '') as varchar) as \"holder_name\"",
        "cast(nullif(trim(cast(\"holder_type\" as varchar)), '') as varchar) as \"holder_type\"",
        "cast(nullif(trim(cast(\"in_de\" as varchar)), '') as varchar) as \"in_de\"",
        "cast(nullif(trim(cast(\"change_vol\" as varchar)), '') as varchar) as \"change_vol\"",
        "cast(nullif(trim(cast(\"change_ratio\" as varchar)), '') as varchar) as \"change_ratio\"",
        "cast(nullif(trim(cast(\"after_share\" as varchar)), '') as varchar) as \"after_share\"",
        "cast(nullif(trim(cast(\"after_ratio\" as varchar)), '') as varchar) as \"after_ratio\"",
        "cast(nullif(trim(cast(\"avg_price\" as varchar)), '') as varchar) as \"avg_price\"",
        "cast(nullif(trim(cast(\"total_share\" as varchar)), '') as varchar) as \"total_share\""
    ]
) }}
