{{ config(materialized="view") }}

{{ stg_latest_raw(
    "tushare",
    "disclosure_date",
    [
        "ts_code",
        "ann_date",
        "end_date",
        "pre_date",
        "actual_date",
        "modify_date"
    ],
    [
        "cast(nullif(trim(cast(\"ts_code\" as varchar)), '') as varchar) as \"ts_code\"",
        "strptime(nullif(trim(cast(\"ann_date\" as varchar)), ''), '%Y%m%d')::date as \"ann_date\"",
        "strptime(nullif(trim(cast(\"end_date\" as varchar)), ''), '%Y%m%d')::date as \"end_date\"",
        "strptime(nullif(trim(cast(\"pre_date\" as varchar)), ''), '%Y%m%d')::date as \"pre_date\"",
        "strptime(nullif(trim(cast(\"actual_date\" as varchar)), ''), '%Y%m%d')::date as \"actual_date\"",
        "strptime(nullif(trim(cast(\"modify_date\" as varchar)), ''), '%Y%m%d')::date as \"modify_date\""
    ]
) }}
