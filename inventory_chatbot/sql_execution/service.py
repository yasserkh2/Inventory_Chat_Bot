from __future__ import annotations

from typing import Any
from typing import Protocol

from inventory_chatbot.dynamic_sql.compiler import SQLCompiler
from inventory_chatbot.dynamic_sql.schema_catalog import SCHEMA_CATALOG
from inventory_chatbot.dynamic_sql.service import DynamicSQLService, DynamicSQLServiceError
from inventory_chatbot.dynamic_sql.validator import QueryValidationError, QueryValidator
from inventory_chatbot.dynamic_sql.models import QueryPlan
from inventory_chatbot.models.domain import ComputedResult
from inventory_chatbot.sql_execution.models import SQLExecutionRequest


class SQLExecutionServiceError(ValueError):
    pass


class SQLQueryRunner(Protocol):
    def execute_sql(self, *, sql_query: str, query_plan: QueryPlan) -> list[dict[str, Any]]:
        ...


class SQLExecutionService:
    def __init__(
        self,
        *,
        dynamic_sql_service: DynamicSQLService | None = None,
        seed_data: dict[str, list[dict[str, Any]]] | None = None,
        schema_catalog: dict[str, dict[str, object]] | None = None,
        query_runner: SQLQueryRunner | None = None,
    ) -> None:
        self._dynamic_sql_service = dynamic_sql_service or (
            DynamicSQLService(seed_data=seed_data) if query_runner is None else None
        )
        self._query_runner = query_runner
        self._schema_catalog = schema_catalog or SCHEMA_CATALOG
        self._validator = QueryValidator(self._schema_catalog)
        self._compiler = SQLCompiler()

    def can_handle(self, context: dict[str, Any]) -> bool:
        return "query_plan" in context or "sql_query" in context

    def preview_sql(self, request: SQLExecutionRequest) -> str:
        self._validate_allowed_tables(request)
        try:
            validated = self._validator.validate(request.query_plan)
        except QueryValidationError as exc:
            raise SQLExecutionServiceError(str(exc)) from exc
        return self._compiler.compile(validated)

    def execute(self, request: SQLExecutionRequest) -> tuple[ComputedResult, str]:
        sql_preview = self.preview_sql(request)
        sql_query = request.sql_query or sql_preview
        if self._query_runner is not None:
            try:
                rows = self._query_runner.execute_sql(
                    sql_query=sql_query,
                    query_plan=request.query_plan,
                )
            except Exception as exc:  # pragma: no cover - depends on runtime DB
                raise SQLExecutionServiceError(str(exc)) from exc
            result = ComputedResult(
                intent_id="dynamic_sql_query",
                specialist_name="dynamic_sql",
                answer_context={
                    "row_count": len(rows),
                    "rows": rows,
                },
                fallback_answer=self._build_fallback_answer(request.user_message, rows),
            )
            return result, sql_query

        if self._dynamic_sql_service is None:
            raise SQLExecutionServiceError(
                "SQL execution service has neither dynamic_sql_service nor query_runner configured."
            )
        try:
            return self._dynamic_sql_service.execute(
                user_message=request.user_message,
                context={
                    **request.context,
                    "query_plan": request.query_plan.model_dump(),
                    "sql_query": request.sql_query,
                },
            )
        except DynamicSQLServiceError as exc:
            raise SQLExecutionServiceError(str(exc)) from exc

    @staticmethod
    def _build_fallback_answer(user_message: str, rows: list[dict[str, Any]]) -> str:
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

    def _validate_allowed_tables(self, request: SQLExecutionRequest) -> None:
        if not request.allowed_tables:
            return
        allowed_tables = set(request.allowed_tables)
        used_tables = self._collect_used_tables(request.query_plan)
        disallowed = sorted(table for table in used_tables if table not in allowed_tables)
        if disallowed:
            raise SQLExecutionServiceError(
                "Query plan references tables outside the agent domain: "
                + ", ".join(disallowed)
            )

    @staticmethod
    def _collect_used_tables(query_plan) -> set[str]:
        tables = {query_plan.base_table}
        for select in query_plan.selects:
            if "." in select.column:
                tables.add(select.column.split(".", 1)[0])
        for aggregate in query_plan.aggregates:
            if "." in aggregate.column:
                tables.add(aggregate.column.split(".", 1)[0])
        for join in query_plan.joins:
            tables.add(join.left.split(".", 1)[0])
            tables.add(join.right.split(".", 1)[0])
        for query_filter in query_plan.filters:
            tables.add(query_filter.column.split(".", 1)[0])
        for group_by in query_plan.group_by:
            if "." in group_by:
                tables.add(group_by.split(".", 1)[0])
        for order_by in query_plan.order_by:
            if "." in order_by.expression:
                tables.add(order_by.expression.split(".", 1)[0])
        return tables
