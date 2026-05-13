{{ config(materialized="view") }}

{{ stg_latest_raw(
    "tushare",
    "index_classify",
    [
        "index_code",
        "industry_name",
        "level",
        "industry_code",
        "is_pub",
        "parent_code",
        "src"
    ],
    [
        "cast(nullif(trim(cast(\"index_code\" as varchar)), '') as varchar) as \"index_code\"",
        "cast(nullif(trim(cast(\"industry_name\" as varchar)), '') as varchar) as \"industry_name\"",
        "cast(nullif(trim(cast(\"level\" as varchar)), '') as varchar) as \"level\"",
        "cast(nullif(trim(cast(\"industry_code\" as varchar)), '') as varchar) as \"industry_code\"",
        "cast(nullif(trim(cast(\"is_pub\" as varchar)), '') as varchar) as \"is_pub\"",
        "cast(nullif(trim(cast(\"parent_code\" as varchar)), '') as varchar) as \"parent_code\"",
        "cast(nullif(trim(cast(\"src\" as varchar)), '') as varchar) as \"src\""
    ],
    "static"
) }}
