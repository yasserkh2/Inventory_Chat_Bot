from __future__ import annotations

from typing import Any

from inventory_chatbot.dynamic_sql.compiler import SQLCompiler
from inventory_chatbot.dynamic_sql.executor import MockQueryExecutor
from inventory_chatbot.dynamic_sql.models import QueryPlan, QueryResult
from inventory_chatbot.dynamic_sql.schema_catalog import SCHEMA_CATALOG
from inventory_chatbot.dynamic_sql.validator import QueryValidator


class DynamicQueryEngine:
    def __init__(
        self,
        schema_catalog: dict[str, dict[str, object]] | None = None,
        validator: QueryValidator | None = None,
        compiler: SQLCompiler | None = None,
        executor: MockQueryExecutor | None = None,
    ) -> None:
        self._schema_catalog = schema_catalog or SCHEMA_CATALOG
        self._validator = validator or QueryValidator(self._schema_catalog)
        self._compiler = compiler or SQLCompiler()
        self._executor = executor or MockQueryExecutor()

    def run(
        self, plan: QueryPlan, data: dict[str, list[dict[str, Any]]]
    ) -> QueryResult:
        validated = self._validator.validate(plan)
        sql = self._compiler.compile(validated)
        rows = self._executor.execute(validated, data)
        return QueryResult(sql=sql, rows=rows)
