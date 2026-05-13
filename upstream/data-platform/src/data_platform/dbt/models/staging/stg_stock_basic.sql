{{ config(materialized="view") }}

{{ stg_latest_raw(
    "tushare",
    "stock_basic",
    [
        "ts_code",
        "symbol",
        "name",
        "area",
        "industry",
        "fullname",
        "enname",
        "cnspell",
        "market",
        "exchange",
        "curr_type",
        "list_status",
        "list_date",
        "delist_date",
        "is_hs",
        "act_name",
        "act_ent_type"
    ],
    [
        "cast(nullif(trim(cast(\"ts_code\" as varchar)), '') as varchar) as \"ts_code\"",
        "cast(nullif(trim(cast(\"symbol\" as varchar)), '') as varchar) as \"symbol\"",
        "cast(nullif(trim(cast(\"name\" as varchar)), '') as varchar) as \"name\"",
        "cast(nullif(trim(cast(\"area\" as varchar)), '') as varchar) as \"area\"",
        "cast(nullif(trim(cast(\"industry\" as varchar)), '') as varchar) as \"industry\"",
        "cast(nullif(trim(cast(\"fullname\" as varchar)), '') as varchar) as \"fullname\"",
        "cast(nullif(trim(cast(\"enname\" as varchar)), '') as varchar) as \"enname\"",
        "cast(nullif(trim(cast(\"cnspell\" as varchar)), '') as varchar) as \"cnspell\"",
        "cast(nullif(trim(cast(\"market\" as varchar)), '') as varchar) as \"market\"",
        "cast(nullif(trim(cast(\"exchange\" as varchar)), '') as varchar) as \"exchange\"",
        "cast(nullif(trim(cast(\"curr_type\" as varchar)), '') as varchar) as \"curr_type\"",
        "cast(nullif(trim(cast(\"list_status\" as varchar)), '') as varchar) as \"list_status\"",
        "strptime(nullif(trim(cast(\"list_date\" as varchar)), ''), '%Y%m%d')::date as \"list_date\"",
        "strptime(nullif(trim(cast(\"delist_date\" as varchar)), ''), '%Y%m%d')::date as \"delist_date\"",
        "cast(upper(trim(cast(\"list_status\" as varchar))) = 'L' as boolean) as \"is_active\"",
        "cast(nullif(trim(cast(\"is_hs\" as varchar)), '') as varchar) as \"is_hs\"",
        "cast(nullif(trim(cast(\"act_name\" as varchar)), '') as varchar) as \"act_name\"",
        "cast(nullif(trim(cast(\"act_ent_type\" as varchar)), '') as varchar) as \"act_ent_type\""
    ],
    "static"
) }}
