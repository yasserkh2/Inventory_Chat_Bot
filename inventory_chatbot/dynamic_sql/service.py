from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import ValidationError

from inventory_chatbot.dynamic_sql.engine import DynamicQueryEngine
from inventory_chatbot.dynamic_sql.models import QueryPlan
from inventory_chatbot.dynamic_sql.schema_catalog import SCHEMA_CATALOG
from inventory_chatbot.dynamic_sql.validator import QueryValidationError
from inventory_chatbot.models.domain import ComputedResult


class DynamicSQLServiceError(ValueError):
    pass


class DynamicSQLService:
    def __init__(
        self,
        *,
        engine: DynamicQueryEngine | None = None,
        seed_data: dict[str, list[dict[str, Any]]] | None = None,
    ) -> None:
        self._engine = engine or DynamicQueryEngine()
        self._seed_data = seed_data or {}

    def can_handle(self, context: dict[str, Any]) -> bool:
        return "query_plan" in context

    def execute(self, *, user_message: str, context: dict[str, Any]) -> tuple[ComputedResult, str]:
        raw_plan = context.get("query_plan")
        if not isinstance(raw_plan, dict):
            raise DynamicSQLServiceError("`context.query_plan` must be a JSON object.")

        try:
            plan = QueryPlan.model_validate(raw_plan)
            plan = self._normalize_plan_values(plan)
            query_result = self._engine.run(plan, self._seed_data)
        except ValidationError as exc:
            raise DynamicSQLServiceError(f"Invalid query plan: {exc.errors()}") from exc
        except QueryValidationError as exc:
            raise DynamicSQLServiceError(f"Query plan failed schema validation: {exc}") from exc

        result = ComputedResult(
            intent_id="dynamic_sql_query",
            specialist_name="dynamic_sql",
            answer_context={
                "row_count": len(query_result.rows),
                "rows": query_result.rows,
            },
            fallback_answer=self._build_fallback_answer(user_message, query_result.rows),
        )
        return result, query_result.sql

    def _build_fallback_answer(
        self, user_message: str, rows: list[dict[str, Any]]
    ) -> str:
        if not rows:
            return f"No rows matched the request: {user_message}"
        if len(rows) == 1 and len(rows[0]) == 1:
            key, value = next(iter(rows[0].items()))
            return f"{key}: {value}"
        if len(rows) == 1:
            parts = ", ".join(f"{key}: {value}" for key, value in rows[0].items())
            return f"Result: {parts}"
        preview = "; ".join(
            ", ".join(f"{key}: {value}" for key, value in row.items())
            for row in rows[:3]
        )
        if len(rows) > 3:
            preview += f"; ... ({len(rows)} rows total)"
        return preview

    def _normalize_plan_values(self, plan: QueryPlan) -> QueryPlan:
        for query_filter in plan.filters:
            table_name, column_name = query_filter.column.split(".", 1)
            column_type = SCHEMA_CATALOG[table_name]["columns"].get(column_name)
            if column_type not in {"date", "datetime"}:
                continue
            if query_filter.operator == "BETWEEN" and isinstance(query_filter.value, list | tuple):
                query_filter.value = [
                    self._coerce_temporal_value(item, column_type) for item in query_filter.value
                ]
            else:
                query_filter.value = self._coerce_temporal_value(
                    query_filter.value, column_type
                )
        return plan

    def _coerce_temporal_value(self, value: Any, column_type: str) -> Any:
        if column_type == "date" and isinstance(value, str):
            return date.fromisoformat(value)
        if column_type == "datetime" and isinstance(value, str):
            return datetime.fromisoformat(value)
        return value
