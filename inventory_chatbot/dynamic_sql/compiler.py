from __future__ import annotations

from datetime import date, datetime
from typing import Any

from inventory_chatbot.dynamic_sql.models import QueryPlan


class SQLCompiler:
    def compile(self, plan: QueryPlan) -> str:
        select_parts: list[str] = []
        for select in plan.selects:
            if select.alias:
                select_parts.append(f"{select.column} AS {select.alias}")
            else:
                select_parts.append(select.column)
        for aggregate in plan.aggregates:
            target = "*" if aggregate.function == "COUNT" else aggregate.column
            select_parts.append(f"{aggregate.function}({target}) AS {aggregate.alias}")

        top_clause = f"TOP {plan.limit} " if plan.limit else ""
        lines = [f"SELECT {top_clause}{', '.join(select_parts)}", f"FROM {plan.base_table}"]

        for join in plan.joins:
            right_table = join.right.split(".", 1)[0]
            lines.append(f"{join.join_type} JOIN {right_table} ON {join.left} = {join.right}")

        if plan.filters:
            where_clauses = [self._compile_filter(item.column, item.operator, item.value) for item in plan.filters]
            lines.append("WHERE " + "\n  AND ".join(where_clauses))

        if plan.group_by:
            lines.append("GROUP BY " + ", ".join(plan.group_by))

        if plan.order_by:
            order_parts = [f"{item.expression} {item.direction}" for item in plan.order_by]
            lines.append("ORDER BY " + ", ".join(order_parts))

        return "\n".join(lines) + ";"

    def _compile_filter(self, column: str, operator: str, value: Any) -> str:
        if operator == "BETWEEN":
            start, end = value
            return f"{column} BETWEEN {self._literal(start)} AND {self._literal(end)}"
        if operator == "IN":
            items = ", ".join(self._literal(item) for item in value)
            return f"{column} IN ({items})"
        return f"{column} {operator} {self._literal(value)}"

    def _literal(self, value: Any) -> str:
        if value is None:
            return "NULL"
        if isinstance(value, bool):
            return "1" if value else "0"
        if isinstance(value, (int, float)):
            return str(value)
        if isinstance(value, datetime):
            return "'" + value.isoformat(sep=" ") + "'"
        if isinstance(value, date):
            return "'" + value.isoformat() + "'"
        return "'" + str(value).replace("'", "''") + "'"
