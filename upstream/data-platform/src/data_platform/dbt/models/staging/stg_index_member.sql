{{ config(materialized="view") }}

{{ stg_latest_raw(
    "tushare",
    "index_member",
    [
        "index_code",
        "index_name",
        "con_code",
        "con_name",
        "in_date",
        "out_date",
        "is_new"
    ],
    [
        "cast(nullif(trim(cast(\"index_code\" as varchar)), '') as varchar) as \"index_code\"",
        "cast(nullif(trim(cast(\"index_name\" as varchar)), '') as varchar) as \"index_name\"",
        "cast(nullif(trim(cast(\"con_code\" as varchar)), '') as varchar) as \"con_code\"",
        "cast(nullif(trim(cast(\"con_name\" as varchar)), '') as varchar) as \"con_name\"",
        "strptime(nullif(trim(cast(\"in_date\" as varchar)), ''), '%Y%m%d')::date as \"in_date\"",
        "strptime(nullif(trim(cast(\"out_date\" as varchar)), ''), '%Y%m%d')::date as \"out_date\"",
        "cast(nullif(trim(cast(\"is_new\" as varchar)), '') as varchar) as \"is_new\""
    ]
) }}
