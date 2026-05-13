{{ config(materialized="table") }}

-- Provider-neutral canonical_v2 fact_index_price_bar mart. Renames the
-- provider-shaped index identifier to the canonical index_id per the provider
-- catalog field_mapping; drops raw-zone lineage columns (they live on
-- mart_lineage_fact_index_price_bar.sql). Partition decision on trade_date is
-- deferred to M2.1 per M1-B section 4.

select
    index_code as index_id,
    trade_date,
    cast(nullif(trim(cast(open as varchar)), '') as decimal(38, 18)) as open,
    cast(nullif(trim(cast(high as varchar)), '') as decimal(38, 18)) as high,
    cast(nullif(trim(cast(low as varchar)), '') as decimal(38, 18)) as low,
    cast(nullif(trim(cast(close as varchar)), '') as decimal(38, 18)) as close,
    cast(nullif(trim(cast(pre_close as varchar)), '') as decimal(38, 18)) as pre_close,
    cast(nullif(trim(cast(change as varchar)), '') as decimal(38, 18)) as change,
    cast(nullif(trim(cast(pct_chg as varchar)), '') as decimal(38, 18)) as pct_chg,
    cast(nullif(trim(cast(vol as varchar)), '') as decimal(38, 18)) as vol,
    cast(nullif(trim(cast(amount as varchar)), '') as decimal(38, 18)) as amount,
    exchange,
    case
        when nullif(trim(cast(is_open as varchar)), '') = '1' then true
        when nullif(trim(cast(is_open as varchar)), '') = '0' then false
        else null
    end as is_open,
    pretrade_date
from {{ ref('int_index_price_bars') }}
