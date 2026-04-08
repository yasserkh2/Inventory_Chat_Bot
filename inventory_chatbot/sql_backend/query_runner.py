from __future__ import annotations

import re
from typing import Any

from inventory_chatbot.dynamic_sql.models import QueryPlan
from inventory_chatbot.sql_backend.errors import SQLBackendRuntimeError
from inventory_chatbot.sql_backend.mapper import map_dynamic_result_rows


class SQLServerQueryRunner:
    def __init__(self, *, engine) -> None:
        self._engine = engine

    def execute_sql(self, *, sql_query: str, query_plan: QueryPlan) -> list[dict[str, Any]]:
        try:
            from sqlalchemy import text
        except ModuleNotFoundError as exc:  # pragma: no cover - dependency presence
            raise SQLBackendRuntimeError(
                "SQLAlchemy is required for SQL backend mode. Install `sqlalchemy` and `pyodbc`."
            ) from exc

        executable_sql = self._normalize_sql_for_engine(sql_query)
        try:
            with self._engine.connect() as connection:
                rows = connection.execute(text(executable_sql)).mappings().all()
        except Exception as exc:  # pragma: no cover - depends on runtime DB
            raise SQLBackendRuntimeError(f"Failed to execute SQL query: {exc}") from exc

        raw_rows = [dict(row) for row in rows]
        return map_dynamic_result_rows(raw_rows, query_plan)

    def _normalize_sql_for_engine(self, sql_query: str) -> str:
        backend_name = self._engine.url.get_backend_name()
        if backend_name != "sqlite":
            return sql_query

        sql = sql_query.strip().rstrip(";")
        top_match = re.match(r"(?is)^SELECT\s+TOP\s+\(?(?P<limit>\d+)\)?\s+(?P<body>.+)$", sql)
        if top_match is None:
            return sql_query

        limit = top_match.group("limit")
        body = top_match.group("body").strip()
        if re.search(r"(?is)\s+LIMIT\s+\d+\s*$", body):
            return f"SELECT {body};"
        return f"SELECT {body} LIMIT {limit};"
