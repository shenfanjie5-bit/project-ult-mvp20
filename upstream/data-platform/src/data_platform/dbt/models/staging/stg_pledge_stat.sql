{{ config(materialized="view") }}

{{ stg_latest_raw(
    "tushare",
    "pledge_stat",
    [
        "ts_code",
        "end_date",
        "pledge_count",
        "unrest_pledge",
        "rest_pledge",
        "total_share",
        "pledge_ratio"
    ],
    [
        "cast(nullif(trim(cast(\"ts_code\" as varchar)), '') as varchar) as \"ts_code\"",
        "strptime(nullif(trim(cast(\"end_date\" as varchar)), ''), '%Y%m%d')::date as \"end_date\"",
        "cast(nullif(trim(cast(\"pledge_count\" as varchar)), '') as varchar) as \"pledge_count\"",
        "cast(nullif(trim(cast(\"unrest_pledge\" as varchar)), '') as varchar) as \"unrest_pledge\"",
        "cast(nullif(trim(cast(\"rest_pledge\" as varchar)), '') as varchar) as \"rest_pledge\"",
        "cast(nullif(trim(cast(\"total_share\" as varchar)), '') as varchar) as \"total_share\"",
        "cast(nullif(trim(cast(\"pledge_ratio\" as varchar)), '') as varchar) as \"pledge_ratio\""
    ]
) }}
