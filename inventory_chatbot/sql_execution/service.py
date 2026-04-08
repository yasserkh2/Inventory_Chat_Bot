from __future__ import annotations

from typing import Any

from inventory_chatbot.dynamic_sql.compiler import SQLCompiler
from inventory_chatbot.dynamic_sql.schema_catalog import SCHEMA_CATALOG
from inventory_chatbot.dynamic_sql.service import DynamicSQLService, DynamicSQLServiceError
from inventory_chatbot.dynamic_sql.validator import QueryValidationError, QueryValidator
from inventory_chatbot.models.domain import ComputedResult
from inventory_chatbot.sql_execution.models import SQLExecutionRequest


class SQLExecutionServiceError(ValueError):
    pass


class SQLExecutionService:
    def __init__(
        self,
        *,
        dynamic_sql_service: DynamicSQLService | None = None,
        seed_data: dict[str, list[dict[str, Any]]] | None = None,
        schema_catalog: dict[str, dict[str, object]] | None = None,
    ) -> None:
        self._dynamic_sql_service = dynamic_sql_service or DynamicSQLService(seed_data=seed_data)
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
        self.preview_sql(request)
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
