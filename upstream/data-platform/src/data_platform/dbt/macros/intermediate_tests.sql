{% test at_most_one_true_per_group(model, group_by_columns, flag_column) -%}
select
{%- for column_name in group_by_columns %}
    {{ column_name }}{% if not loop.last %},{% endif %}
{%- endfor %}
from {{ model }}
where {{ flag_column }}
group by
{%- for column_name in group_by_columns %}
    {{ column_name }}{% if not loop.last %},{% endif %}
{%- endfor %}
having count(*) > 1
{%- endtest %}
