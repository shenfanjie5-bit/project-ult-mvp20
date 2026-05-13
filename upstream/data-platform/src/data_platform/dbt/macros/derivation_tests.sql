{% test derivation_lineage_key_parity(model, business_model, key_columns) -%}
with business_keys as (
    select distinct
    {%- for column_name in key_columns %}
        {{ adapter.quote(column_name) }}{% if not loop.last %},{% endif %}
    {%- endfor %}
    from {{ business_model }}
),

lineage_keys as (
    select distinct
    {%- for column_name in key_columns %}
        {{ adapter.quote(column_name) }}{% if not loop.last %},{% endif %}
    {%- endfor %}
    from {{ model }}
),

missing_from_lineage as (
    select * from business_keys
    except
    select * from lineage_keys
),

extra_in_lineage as (
    select * from lineage_keys
    except
    select * from business_keys
)

select * from missing_from_lineage
union all
select * from extra_in_lineage
{%- endtest %}
