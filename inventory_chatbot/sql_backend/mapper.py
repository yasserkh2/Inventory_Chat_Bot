from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from inventory_chatbot.dynamic_sql.models import QueryPlan


_FIRST_CAP_RE = re.compile("(.)([A-Z][a-z]+)")
_ALL_CAP_RE = re.compile("([a-z0-9])([A-Z])")


def to_snake_case(name: str) -> str:
    step = _FIRST_CAP_RE.sub(r"\1_\2", name)
    return _ALL_CAP_RE.sub(r"\1_\2", step).lower()


def normalize_scalar(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (date, datetime)):
        return value
    return value


def map_table_row(row: Mapping[str, Any]) -> dict[str, Any]:
    return {to_snake_case(column): normalize_scalar(value) for column, value in row.items()}


def map_dynamic_result_rows(
    rows: list[Mapping[str, Any]],
    query_plan: QueryPlan,
) -> list[dict[str, Any]]:
    select_pairs: list[tuple[str, str]] = []
    for select in query_plan.selects:
        expected = select.alias or select.column
        fallback = select.alias or select.column.rsplit(".", 1)[-1]
        select_pairs.append((expected, fallback))

    aggregate_keys = [aggregate.alias for aggregate in query_plan.aggregates]
    mapped_rows: list[dict[str, Any]] = []
    for row in rows:
        normalized_row = {str(key): normalize_scalar(value) for key, value in row.items()}
        mapped: dict[str, Any] = {}
        if select_pairs:
            for expected_key, fallback_key in select_pairs:
                if expected_key in normalized_row:
                    mapped[expected_key] = normalized_row[expected_key]
                elif fallback_key in normalized_row:
                    mapped[expected_key] = normalized_row[fallback_key]
                else:
                    mapped[expected_key] = _lookup_case_insensitive(
                        normalized_row, expected_key, fallback_key
                    )

        for aggregate_key in aggregate_keys:
            if aggregate_key in normalized_row:
                mapped[aggregate_key] = normalized_row[aggregate_key]
            else:
                mapped[aggregate_key] = _lookup_case_insensitive(normalized_row, aggregate_key)

        if not mapped:
            mapped = dict(normalized_row)
        mapped_rows.append(mapped)
    return mapped_rows


def _lookup_case_insensitive(
    row: Mapping[str, Any], *candidates: str
) -> Any:
    candidate_set = {candidate.lower() for candidate in candidates if candidate}
    for key, value in row.items():
        if key.lower() in candidate_set:
            return value
    return None

