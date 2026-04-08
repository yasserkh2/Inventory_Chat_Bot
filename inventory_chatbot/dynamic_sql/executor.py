from __future__ import annotations

from collections import defaultdict
from typing import Any

from inventory_chatbot.dynamic_sql.models import QueryPlan
from inventory_chatbot.dynamic_sql.schema_catalog import SCHEMA_CATALOG


class MockQueryExecutor:
    def execute(self, plan: QueryPlan, data: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
        rows = [self._qualify_row(plan.base_table, row) for row in data[self._key(plan.base_table)]]

        for join in plan.joins:
            right_table = join.right.split(".", 1)[0]
            right_key = self._key(right_table)
            joined_rows: list[dict[str, Any]] = []
            for row in rows:
                left_value = row.get(join.left)
                for right_row in data[right_key]:
                    qualified_right = self._qualify_row(right_table, right_row)
                    if left_value == qualified_right.get(join.right):
                        merged = dict(row)
                        merged.update(qualified_right)
                        joined_rows.append(merged)
            rows = joined_rows

        for query_filter in plan.filters:
            rows = [row for row in rows if self._matches_filter(row.get(query_filter.column), query_filter.operator, query_filter.value)]

        if plan.group_by:
            grouped: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
            for row in rows:
                key = tuple(row.get(column) for column in plan.group_by)
                grouped[key].append(row)
            result_rows = [self._build_group_row(plan, group_rows) for group_rows in grouped.values()]
        elif plan.aggregates:
            result_rows = [self._build_group_row(plan, rows)]
        else:
            result_rows = [self._project_row(plan, row) for row in rows]

        if plan.order_by:
            for order in reversed(plan.order_by):
                result_rows.sort(
                    key=lambda item: self._lookup_order_value(item, order.expression),
                    reverse=order.direction == "DESC",
                )

        if plan.limit:
            result_rows = result_rows[: plan.limit]

        return result_rows

    def _build_group_row(self, plan: QueryPlan, rows: list[dict[str, Any]]) -> dict[str, Any]:
        projected = {}
        sample = rows[0] if rows else {}
        for select in plan.selects:
            projected[select.alias or select.column] = sample.get(select.column)
        for aggregate in plan.aggregates:
            projected[aggregate.alias] = self._aggregate(aggregate.function, aggregate.column, rows)
        return projected

    def _project_row(self, plan: QueryPlan, row: dict[str, Any]) -> dict[str, Any]:
        projected = {}
        for select in plan.selects:
            projected[select.alias or select.column] = row.get(select.column)
        for aggregate in plan.aggregates:
            projected[aggregate.alias] = self._aggregate(aggregate.function, aggregate.column, [row])
        return projected

    def _aggregate(self, function: str, column: str, rows: list[dict[str, Any]]) -> Any:
        if function == "COUNT":
            if column == "*":
                return len(rows)
            return sum(1 for row in rows if row.get(column) is not None)
        values = [row.get(column) for row in rows if row.get(column) is not None]
        if not values:
            return None
        if function == "SUM":
            return sum(values)
        if function == "AVG":
            return sum(values) / len(values)
        if function == "MIN":
            return min(values)
        if function == "MAX":
            return max(values)
        raise KeyError(f"Unsupported aggregate function: {function}")

    def _lookup_order_value(self, row: dict[str, Any], expression: str) -> Any:
        if expression in row:
            return row[expression]
        if "." in expression:
            _, column_name = expression.rsplit(".", 1)
            return row.get(column_name)
        return None

    def _matches_filter(self, candidate: Any, operator: str, value: Any) -> bool:
        if operator == "=":
            return candidate == value
        if operator == "<>":
            return candidate != value
        if operator == ">":
            return candidate is not None and candidate > value
        if operator == ">=":
            return candidate is not None and candidate >= value
        if operator == "<":
            return candidate is not None and candidate < value
        if operator == "<=":
            return candidate is not None and candidate <= value
        if operator == "IN":
            return candidate in value
        if operator == "BETWEEN":
            start, end = value
            return candidate is not None and start <= candidate <= end
        if operator == "LIKE":
            pattern = str(value).replace("%", "")
            return pattern.lower() in str(candidate or "").lower()
        raise KeyError(f"Unsupported filter operator: {operator}")

    def _qualify_row(self, table_name: str, row: dict[str, Any]) -> dict[str, Any]:
        return {
            f"{table_name}.{self._to_schema_column(table_name, key)}": value
            for key, value in row.items()
        }

    def _to_schema_column(self, table_name: str, key: str) -> str:
        normalized_key = key.replace("_", "").lower()
        columns = SCHEMA_CATALOG[table_name]["columns"]
        for column_name in columns:
            if column_name.lower() == normalized_key:
                return column_name
        return "".join(part.capitalize() for part in key.split("_"))

    def _key(self, table_name: str) -> str:
        mapping = {
            "Customers": "customers",
            "Vendors": "vendors",
            "Sites": "sites",
            "Locations": "locations",
            "Items": "items",
            "Assets": "assets",
            "Bills": "bills",
            "PurchaseOrders": "purchase_orders",
            "PurchaseOrderLines": "purchase_order_lines",
            "SalesOrders": "sales_orders",
            "SalesOrderLines": "sales_order_lines",
            "AssetTransactions": "asset_transactions",
        }
        return mapping[table_name]
