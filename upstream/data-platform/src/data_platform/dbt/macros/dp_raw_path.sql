{% macro dp_raw_path(source_id, dataset) -%}
{%- set data_storage_root_path = env_var("DP_DATA_STORAGE_ROOT_PATH", "./data_platform/data").rstrip("/") -%}
{%- set raw_zone_path = env_var("DP_RAW_ZONE_PATH", data_storage_root_path ~ "/raw").rstrip("/") -%}
{{ raw_zone_path ~ "/" ~ source_id ~ "/" ~ dataset ~ "/**/*.parquet" }}
{%- endmacro %}

{% macro dp_raw_manifest_path(source_id, dataset) -%}
{%- set data_storage_root_path = env_var("DP_DATA_STORAGE_ROOT_PATH", "./data_platform/data").rstrip("/") -%}
{%- set raw_zone_path = env_var("DP_RAW_ZONE_PATH", data_storage_root_path ~ "/raw").rstrip("/") -%}
{{ raw_zone_path ~ "/" ~ source_id ~ "/" ~ dataset ~ "/**/_manifest.json" }}
{%- endmacro %}
