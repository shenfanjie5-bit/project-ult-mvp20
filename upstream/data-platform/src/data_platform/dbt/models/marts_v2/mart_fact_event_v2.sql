{{ config(materialized="table") }}

-- Provider-neutral canonical_v2 event fact.
-- Reads int_event_timeline (which now carries per-branch source_interface_id)
-- and renames the provider-shaped security identifier to entity_id. Derives
-- event_key as a stable md5 hash of (source_interface_id, event_type, title,
-- summary, event_subtype, related_date, reference_url, rec_time) so distinct
-- legacy events on the same (event_type, entity_id, event_date) tuple do NOT
-- collapse. canonical_v2.fact_event covers 8 source interfaces: anns,
-- suspend_d, dividend, share_float, stk_holdernumber, disclosure_date,
-- namechange, and block_trade. M1.6 added namechange / event_type='name_change';
-- M1.8 added block_trade / event_type='block_trade' (with the int_event_timeline
-- uniqueness contract widened to include `summary`). Full event_timeline
-- coverage is not yet achieved: the 8 candidate sources (pledge_*, repurchase,
-- stk_holdertrade, limit_list_*, hm_detail, stk_surv) remain BLOCKED_NO_STAGING.
--
-- The event_key derivation expression is byte-identical to the sibling lineage
-- mart so v2/lineage row sets pair on the composite canonical PK in the
-- canonical_writer pairing validator. The intermediate uniqueness key was
-- intentionally widened in M1.8 to include `summary`; canonical row identity
-- is enforced here at the mart-level event_key + canonical PK parity, and at
-- the writer-side validation in canonical_writer.
--
-- Raw-zone lineage columns are intentionally NOT projected here; they live
-- on the sibling lineage mart. canonical_loaded_at is also NOT projected;
-- the canonical writer injects it.

select
    event_type,
    ts_code as entity_id,
    event_date,
    md5(
        concat_ws(
            '|',
            source_interface_id,
            event_type,
            coalesce(title, ''),
            coalesce(summary, ''),
            coalesce(event_subtype, ''),
            coalesce(cast(related_date as varchar), ''),
            coalesce(reference_url, ''),
            coalesce(rec_time, '')
        )
    ) as event_key,
    title,
    summary,
    event_subtype,
    related_date,
    reference_url,
    rec_time
from {{ ref('int_event_timeline') }}
