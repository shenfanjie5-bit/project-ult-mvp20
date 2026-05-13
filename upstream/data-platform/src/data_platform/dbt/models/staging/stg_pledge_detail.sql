{{ config(materialized="view") }}

{{ stg_latest_raw(
    "tushare",
    "pledge_detail",
    [
        "ts_code",
        "ann_date",
        "holder_name",
        "pledge_amount",
        "start_date",
        "end_date",
        "is_release",
        "release_date",
        "pledgor",
        "holding_amount",
        "pledged_amount",
        "p_total_ratio",
        "h_total_ratio",
        "is_buyback"
    ],
    [
        "cast(nullif(trim(cast(\"ts_code\" as varchar)), '') as varchar) as \"ts_code\"",
        "strptime(nullif(trim(cast(\"ann_date\" as varchar)), ''), '%Y%m%d')::date as \"ann_date\"",
        "cast(nullif(trim(cast(\"holder_name\" as varchar)), '') as varchar) as \"holder_name\"",
        "cast(nullif(trim(cast(\"pledge_amount\" as varchar)), '') as varchar) as \"pledge_amount\"",
        "strptime(nullif(trim(cast(\"start_date\" as varchar)), ''), '%Y%m%d')::date as \"start_date\"",
        "strptime(nullif(trim(cast(\"end_date\" as varchar)), ''), '%Y%m%d')::date as \"end_date\"",
        "cast(nullif(trim(cast(\"is_release\" as varchar)), '') as varchar) as \"is_release\"",
        "strptime(nullif(trim(cast(\"release_date\" as varchar)), ''), '%Y%m%d')::date as \"release_date\"",
        "cast(nullif(trim(cast(\"pledgor\" as varchar)), '') as varchar) as \"pledgor\"",
        "cast(nullif(trim(cast(\"holding_amount\" as varchar)), '') as varchar) as \"holding_amount\"",
        "cast(nullif(trim(cast(\"pledged_amount\" as varchar)), '') as varchar) as \"pledged_amount\"",
        "cast(nullif(trim(cast(\"p_total_ratio\" as varchar)), '') as varchar) as \"p_total_ratio\"",
        "cast(nullif(trim(cast(\"h_total_ratio\" as varchar)), '') as varchar) as \"h_total_ratio\"",
        "cast(nullif(trim(cast(\"is_buyback\" as varchar)), '') as varchar) as \"is_buyback\""
    ]
) }}
