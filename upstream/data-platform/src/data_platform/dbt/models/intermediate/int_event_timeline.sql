{{ config(materialized="table") }}

select
    'announcement' as event_type,
    cast('anns' as varchar) as source_interface_id,
    ts_code,
    ann_date as event_date,
    title,
    name as summary,
    cast(null as varchar) as event_subtype,
    cast(null as date) as related_date,
    url as reference_url,
    rec_time,
    source_run_id,
    raw_loaded_at
from {{ ref('stg_anns') }}

union all

select
    'suspend' as event_type,
    cast('suspend_d' as varchar) as source_interface_id,
    ts_code,
    trade_date as event_date,
    'Trading suspension' as title,
    suspend_timing as summary,
    suspend_type as event_subtype,
    trade_date as related_date,
    cast(null as varchar) as reference_url,
    cast(null as varchar) as rec_time,
    source_run_id,
    raw_loaded_at
from {{ ref('stg_suspend_d') }}

union all

select
    'dividend' as event_type,
    cast('dividend' as varchar) as source_interface_id,
    ts_code,
    ann_date as event_date,
    'Dividend' as title,
    concat('cash_div=', coalesce(cash_div, ''), ';stk_div=', coalesce(stk_div, '')) as summary,
    div_proc as event_subtype,
    end_date as related_date,
    cast(null as varchar) as reference_url,
    cast(null as varchar) as rec_time,
    source_run_id,
    raw_loaded_at
from {{ ref('stg_dividend') }}

union all

select
    'share_float' as event_type,
    cast('share_float' as varchar) as source_interface_id,
    ts_code,
    float_date as event_date,
    'Share float' as title,
    holder_name as summary,
    share_type as event_subtype,
    ann_date as related_date,
    cast(null as varchar) as reference_url,
    cast(null as varchar) as rec_time,
    source_run_id,
    raw_loaded_at
from {{ ref('stg_share_float') }}

union all

select
    'holder_number' as event_type,
    cast('stk_holdernumber' as varchar) as source_interface_id,
    ts_code,
    ann_date as event_date,
    'Holder number' as title,
    holder_num as summary,
    cast(null as varchar) as event_subtype,
    end_date as related_date,
    cast(null as varchar) as reference_url,
    cast(null as varchar) as rec_time,
    source_run_id,
    raw_loaded_at
from {{ ref('stg_stk_holdernumber') }}

union all

select
    'disclosure_date' as event_type,
    cast('disclosure_date' as varchar) as source_interface_id,
    ts_code,
    coalesce(actual_date, pre_date, ann_date, modify_date) as event_date,
    'Disclosure date' as title,
    concat(
        'pre_date=', coalesce(cast(pre_date as varchar), ''),
        ';actual_date=', coalesce(cast(actual_date as varchar), '')
    ) as summary,
    cast(null as varchar) as event_subtype,
    end_date as related_date,
    cast(null as varchar) as reference_url,
    cast(null as varchar) as rec_time,
    source_run_id,
    raw_loaded_at
from {{ ref('stg_disclosure_date') }}

union all

select
    'name_change' as event_type,
    cast('namechange' as varchar) as source_interface_id,
    ts_code,
    start_date as event_date,
    'Name change' as title,
    name as summary,
    change_reason as event_subtype,
    ann_date as related_date,
    cast(null as varchar) as reference_url,
    cast(null as varchar) as rec_time,
    source_run_id,
    raw_loaded_at
from {{ ref('stg_namechange') }}

union all

select
    'block_trade' as event_type,
    cast('block_trade' as varchar) as source_interface_id,
    ts_code,
    trade_date as event_date,
    'Block trade' as title,
    concat(
        'buyer=', coalesce(buyer, ''),
        ';seller=', coalesce(seller, ''),
        ';price=', coalesce(price, ''),
        ';vol=', coalesce(vol, ''),
        ';amount=', coalesce(amount, '')
    ) as summary,
    cast(null as varchar) as event_subtype,
    trade_date as related_date,
    cast(null as varchar) as reference_url,
    cast(null as varchar) as rec_time,
    source_run_id,
    raw_loaded_at
from {{ ref('stg_block_trade') }}

-- M1.13 expansion (precondition 9 closure) — 8 candidate event_timeline
-- sources promoted with canonical taxonomy from
-- `event-timeline-m1-11-candidate-schema-checkin-20260429.md` sign-off table.

union all

select
    'pledge_summary' as event_type,
    cast('pledge_stat' as varchar) as source_interface_id,
    ts_code,
    end_date as event_date,
    'Pledge summary' as title,
    concat(
        'count=', coalesce(pledge_count, ''),
        ';unrest=', coalesce(unrest_pledge, ''),
        ';rest=', coalesce(rest_pledge, ''),
        ';total=', coalesce(total_share, ''),
        ';ratio=', coalesce(pledge_ratio, '')
    ) as summary,
    cast(null as varchar) as event_subtype,
    cast(null as date) as related_date,
    cast(null as varchar) as reference_url,
    cast(null as varchar) as rec_time,
    source_run_id,
    raw_loaded_at
from {{ ref('stg_pledge_stat') }}

union all

select
    'pledge_event' as event_type,
    cast('pledge_detail' as varchar) as source_interface_id,
    ts_code,
    ann_date as event_date,
    'Pledge event' as title,
    concat(
        'holder=', coalesce(holder_name, ''),
        ';pledgor=', coalesce(pledgor, ''),
        ';amount=', coalesce(pledge_amount, ''),
        ';period=[', coalesce(cast(start_date as varchar), ''),
        ',', coalesce(cast(end_date as varchar), ''),
        '];release=', coalesce(is_release, '')
    ) as summary,
    is_release as event_subtype,
    end_date as related_date,
    cast(null as varchar) as reference_url,
    cast(null as varchar) as rec_time,
    source_run_id,
    raw_loaded_at
from {{ ref('stg_pledge_detail') }}

union all

select
    'share_repurchase' as event_type,
    cast('repurchase' as varchar) as source_interface_id,
    ts_code,
    ann_date as event_date,
    'Share repurchase' as title,
    concat(
        'proc=', coalesce(proc, ''),
        ';vol=', coalesce(vol, ''),
        ';amount=', coalesce(amount, ''),
        ';exp=', coalesce(cast(exp_date as varchar), ''),
        ';band=[', coalesce(low_limit, ''),
        ',', coalesce(high_limit, ''), ']'
    ) as summary,
    proc as event_subtype,
    end_date as related_date,
    cast(null as varchar) as reference_url,
    cast(null as varchar) as rec_time,
    source_run_id,
    raw_loaded_at
from {{ ref('stg_repurchase') }}

union all

select
    'shareholder_trade' as event_type,
    cast('stk_holdertrade' as varchar) as source_interface_id,
    ts_code,
    ann_date as event_date,
    'Shareholder trade' as title,
    concat(
        'holder=', coalesce(holder_name, ''),
        ';type=', coalesce(holder_type, ''),
        ';dir=', coalesce(in_de, ''),
        ';vol=', coalesce(change_vol, ''),
        ';ratio=', coalesce(change_ratio, ''),
        ';avg_price=', coalesce(avg_price, '')
    ) as summary,
    in_de as event_subtype,
    cast(null as date) as related_date,
    cast(null as varchar) as reference_url,
    cast(null as varchar) as rec_time,
    source_run_id,
    raw_loaded_at
from {{ ref('stg_stk_holdertrade') }}

union all

select
    'institutional_survey' as event_type,
    cast('stk_surv' as varchar) as source_interface_id,
    ts_code,
    surv_date as event_date,
    'Institutional survey' as title,
    concat(
        'org=', coalesce(rece_org, ''),
        ';type=', coalesce(org_type, ''),
        ';place=', coalesce(rece_place, ''),
        ';mode=', coalesce(rece_mode, ''),
        ';visitors=', coalesce(fund_visitors, '')
    ) as summary,
    org_type as event_subtype,
    cast(null as date) as related_date,
    cast(null as varchar) as reference_url,
    cast(null as varchar) as rec_time,
    source_run_id,
    raw_loaded_at
from {{ ref('stg_stk_surv') }}

union all

select
    'price_limit_status' as event_type,
    cast('limit_list_ths' as varchar) as source_interface_id,
    ts_code,
    trade_date as event_date,
    'Price limit status (THS pool)' as title,
    concat(
        'pool=', coalesce(limit_type, ''),
        ';status=', coalesce(status, ''),
        ';tag=', coalesce(tag, ''),
        ';order=', coalesce(limit_order, ''),
        ';amount=', coalesce(limit_amount, ''),
        ';open_num=', coalesce(open_num, '')
    ) as summary,
    limit_type as event_subtype,
    cast(null as date) as related_date,
    cast(null as varchar) as reference_url,
    cast(null as varchar) as rec_time,
    source_run_id,
    raw_loaded_at
from {{ ref('stg_limit_list_ths') }}

union all

select
    'price_limit_event' as event_type,
    cast('limit_list_d' as varchar) as source_interface_id,
    ts_code,
    trade_date as event_date,
    'Price limit event' as title,
    concat(
        'limit=', coalesce("limit", ''),
        ';times=', coalesce(limit_times, ''),
        ';fd=', coalesce(fd_amount, ''),
        ';first=', coalesce(first_time, ''),
        ';last=', coalesce(last_time, ''),
        ';up_stat=', coalesce(up_stat, '')
    ) as summary,
    "limit" as event_subtype,
    cast(null as date) as related_date,
    cast(null as varchar) as reference_url,
    cast(null as varchar) as rec_time,
    source_run_id,
    raw_loaded_at
from {{ ref('stg_limit_list_d') }}

union all

select
    'hot_money_trade' as event_type,
    cast('hm_detail' as varchar) as source_interface_id,
    ts_code,
    trade_date as event_date,
    'Hot money trade' as title,
    concat(
        'hm=', coalesce(hm_name, ''),
        ';buy=', coalesce(buy_amount, ''),
        ';sell=', coalesce(sell_amount, ''),
        ';net=', coalesce(net_amount, ''),
        ';orgs=', coalesce(hm_orgs, '')
    ) as summary,
    cast(null as varchar) as event_subtype,
    cast(null as date) as related_date,
    cast(null as varchar) as reference_url,
    cast(null as varchar) as rec_time,
    source_run_id,
    raw_loaded_at
from {{ ref('stg_hm_detail') }}
