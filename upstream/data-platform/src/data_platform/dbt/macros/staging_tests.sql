{% test unique_combination_of_columns(model, combination_of_columns) -%}
select
{%- for column_name in combination_of_columns %}
    {{ adapter.quote(column_name) }}{% if not loop.last %},{% endif %}
{%- endfor %}
from {{ model }}
group by
{%- for column_name in combination_of_columns %}
    {{ adapter.quote(column_name) }}{% if not loop.last %},{% endif %}
{%- endfor %}
having count(*) > 1
{%- endtest %}

{% test parsable_yyyymmdd_or_date(model, column_name) -%}
select {{ column_name }}
from {{ model }}
where {{ column_name }} is not null
  and coalesce(
      try_cast({{ column_name }} as date),
      try_strptime(nullif(trim(cast({{ column_name }} as varchar)), ''), '%Y%m%d')::date
  ) is null
{%- endtest %}
