{{ config(materialized="view") }}

{{ stg_latest_raw(
    "tushare",
    "dividend",
    [
        "ts_code",
        "end_date",
        "ann_date",
        "div_proc",
        "stk_div",
        "stk_bo_rate",
        "stk_co_rate",
        "cash_div",
        "cash_div_tax",
        "record_date",
        "ex_date",
        "pay_date",
        "div_listdate",
        "imp_ann_date",
        "base_date",
        "base_share"
    ],
    [
        "cast(nullif(trim(cast(\"ts_code\" as varchar)), '') as varchar) as \"ts_code\"",
        "strptime(nullif(trim(cast(\"end_date\" as varchar)), ''), '%Y%m%d')::date as \"end_date\"",
        "strptime(nullif(trim(cast(\"ann_date\" as varchar)), ''), '%Y%m%d')::date as \"ann_date\"",
        "cast(nullif(trim(cast(\"div_proc\" as varchar)), '') as varchar) as \"div_proc\"",
        "cast(nullif(trim(cast(\"stk_div\" as varchar)), '') as varchar) as \"stk_div\"",
        "cast(nullif(trim(cast(\"stk_bo_rate\" as varchar)), '') as varchar) as \"stk_bo_rate\"",
        "cast(nullif(trim(cast(\"stk_co_rate\" as varchar)), '') as varchar) as \"stk_co_rate\"",
        "cast(nullif(trim(cast(\"cash_div\" as varchar)), '') as varchar) as \"cash_div\"",
        "cast(nullif(trim(cast(\"cash_div_tax\" as varchar)), '') as varchar) as \"cash_div_tax\"",
        "strptime(nullif(trim(cast(\"record_date\" as varchar)), ''), '%Y%m%d')::date as \"record_date\"",
        "strptime(nullif(trim(cast(\"ex_date\" as varchar)), ''), '%Y%m%d')::date as \"ex_date\"",
        "strptime(nullif(trim(cast(\"pay_date\" as varchar)), ''), '%Y%m%d')::date as \"pay_date\"",
        "strptime(nullif(trim(cast(\"div_listdate\" as varchar)), ''), '%Y%m%d')::date as \"div_listdate\"",
        "strptime(nullif(trim(cast(\"imp_ann_date\" as varchar)), ''), '%Y%m%d')::date as \"imp_ann_date\"",
        "strptime(nullif(trim(cast(\"base_date\" as varchar)), ''), '%Y%m%d')::date as \"base_date\"",
        "cast(nullif(trim(cast(\"base_share\" as varchar)), '') as varchar) as \"base_share\""
    ]
) }}
