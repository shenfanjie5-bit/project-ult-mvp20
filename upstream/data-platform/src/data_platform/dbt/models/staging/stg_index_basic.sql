{{ config(materialized="view") }}

{{ stg_latest_raw(
    "tushare",
    "index_basic",
    [
        "ts_code",
        "name",
        "fullname",
        "market",
        "publisher",
        "index_type",
        "category",
        "base_date",
        "base_point",
        "list_date",
        "weight_rule",
        "desc",
        "exp_date"
    ],
    [
        "cast(nullif(trim(cast(\"ts_code\" as varchar)), '') as varchar) as \"ts_code\"",
        "cast(nullif(trim(cast(\"name\" as varchar)), '') as varchar) as \"name\"",
        "cast(nullif(trim(cast(\"fullname\" as varchar)), '') as varchar) as \"fullname\"",
        "cast(nullif(trim(cast(\"market\" as varchar)), '') as varchar) as \"market\"",
        "cast(nullif(trim(cast(\"publisher\" as varchar)), '') as varchar) as \"publisher\"",
        "cast(nullif(trim(cast(\"index_type\" as varchar)), '') as varchar) as \"index_type\"",
        "cast(nullif(trim(cast(\"category\" as varchar)), '') as varchar) as \"category\"",
        "strptime(nullif(trim(cast(\"base_date\" as varchar)), ''), '%Y%m%d')::date as \"base_date\"",
        "cast(nullif(trim(cast(\"base_point\" as varchar)), '') as varchar) as \"base_point\"",
        "strptime(nullif(trim(cast(\"list_date\" as varchar)), ''), '%Y%m%d')::date as \"list_date\"",
        "cast(nullif(trim(cast(\"weight_rule\" as varchar)), '') as varchar) as \"weight_rule\"",
        "cast(nullif(trim(cast(\"desc\" as varchar)), '') as varchar) as \"desc\"",
        "strptime(nullif(trim(cast(\"exp_date\" as varchar)), ''), '%Y%m%d')::date as \"exp_date\""
    ],
    "static"
) }}
