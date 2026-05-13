{{ config(materialized="view") }}

{{ stg_latest_raw(
    "tushare",
    "anns",
    [
        "ts_code",
        "ann_date",
        "name",
        "title",
        "url",
        "rec_time"
    ],
    [
        "cast(nullif(trim(cast(\"ts_code\" as varchar)), '') as varchar) as \"ts_code\"",
        "strptime(nullif(trim(cast(\"ann_date\" as varchar)), ''), '%Y%m%d')::date as \"ann_date\"",
        "cast(nullif(trim(cast(\"name\" as varchar)), '') as varchar) as \"name\"",
        "cast(nullif(trim(cast(\"title\" as varchar)), '') as varchar) as \"title\"",
        "cast(nullif(trim(cast(\"url\" as varchar)), '') as varchar) as \"url\"",
        "cast(nullif(trim(cast(\"rec_time\" as varchar)), '') as varchar) as \"rec_time\""
    ]
) }}
