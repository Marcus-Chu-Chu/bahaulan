{% test accepted_range(model, column_name, min_value=none, max_value=none) %}
{% if min_value is none and max_value is none %}
    {{ exceptions.raise_compiler_error("accepted_range needs min_value or max_value") }}
{% endif %}
select {{ column_name }}
from {{ model }}
where {{ column_name }} is not null
and (
    {%- if min_value is not none %} {{ column_name }} < {{ min_value }} {%- endif -%}
    {%- if min_value is not none and max_value is not none %} or {%- endif -%}
    {%- if max_value is not none %} {{ column_name }} > {{ max_value }} {%- endif -%}
)
{% endtest %}
