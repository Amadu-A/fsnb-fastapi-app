# path: src/core/utils/__init__.py
from __future__ import annotations

from .case_converter import camel_case_to_snake_case
from .pagination import (
    Pagination,
    build_pagination,
    get_columns,
    get_boolean_fields,
    parse_bool,
    coerce_value,
    get_fk_target_table,
)

__all__ = (
    "camel_case_to_snake_case",
    "Pagination",
    "build_pagination",
    "get_columns",
    "get_boolean_fields",
    "parse_bool",
    "coerce_value",
    "get_fk_target_table",
)
