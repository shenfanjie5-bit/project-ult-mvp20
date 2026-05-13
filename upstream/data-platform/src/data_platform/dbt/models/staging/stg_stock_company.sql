{{ config(materialized="view") }}

{{ stg_latest_raw(
    "tushare",
    "stock_company",
    [
        "ts_code",
        "exchange",
        "chairman",
        "manager",
        "secretary",
        "reg_capital",
        "setup_date",
        "province",
        "city",
        "introduction",
        "website",
        "email",
        "office",
        "employees",
        "main_business",
        "business_scope"
    ],
    [
        "cast(nullif(trim(cast(\"ts_code\" as varchar)), '') as varchar) as \"ts_code\"",
        "cast(nullif(trim(cast(\"exchange\" as varchar)), '') as varchar) as \"exchange\"",
        "cast(nullif(trim(cast(\"chairman\" as varchar)), '') as varchar) as \"chairman\"",
        "cast(nullif(trim(cast(\"manager\" as varchar)), '') as varchar) as \"manager\"",
        "cast(nullif(trim(cast(\"secretary\" as varchar)), '') as varchar) as \"secretary\"",
        "cast(nullif(trim(cast(\"reg_capital\" as varchar)), '') as varchar) as \"reg_capital\"",
        "strptime(nullif(trim(cast(\"setup_date\" as varchar)), ''), '%Y%m%d')::date as \"setup_date\"",
        "cast(nullif(trim(cast(\"province\" as varchar)), '') as varchar) as \"province\"",
        "cast(nullif(trim(cast(\"city\" as varchar)), '') as varchar) as \"city\"",
        "cast(nullif(trim(cast(\"introduction\" as varchar)), '') as varchar) as \"introduction\"",
        "cast(nullif(trim(cast(\"website\" as varchar)), '') as varchar) as \"website\"",
        "cast(nullif(trim(cast(\"email\" as varchar)), '') as varchar) as \"email\"",
        "cast(nullif(trim(cast(\"office\" as varchar)), '') as varchar) as \"office\"",
        "cast(nullif(trim(cast(\"employees\" as varchar)), '') as varchar) as \"employees\"",
        "cast(nullif(trim(cast(\"main_business\" as varchar)), '') as varchar) as \"main_business\"",
        "cast(nullif(trim(cast(\"business_scope\" as varchar)), '') as varchar) as \"business_scope\""
    ],
    "static"
) }}
