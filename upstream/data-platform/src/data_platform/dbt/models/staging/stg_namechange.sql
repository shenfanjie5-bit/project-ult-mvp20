{{ config(materialized="view") }}

{{ stg_latest_raw(
    "tushare",
    "namechange",
    [
        "ts_code",
        "name",
        "start_date",
        "end_date",
        "ann_date",
        "change_reason"
    ],
    [
        "cast(nullif(trim(cast(\"ts_code\" as varchar)), '') as varchar) as \"ts_code\"",
        "cast(nullif(trim(cast(\"name\" as varchar)), '') as varchar) as \"name\"",
        "strptime(nullif(trim(cast(\"start_date\" as varchar)), ''), '%Y%m%d')::date as \"start_date\"",
        "strptime(nullif(trim(cast(\"end_date\" as varchar)), ''), '%Y%m%d')::date as \"end_date\"",
        "strptime(nullif(trim(cast(\"ann_date\" as varchar)), ''), '%Y%m%d')::date as \"ann_date\"",
        "cast(nullif(trim(cast(\"change_reason\" as varchar)), '') as varchar) as \"change_reason\""
    ]
) }}
