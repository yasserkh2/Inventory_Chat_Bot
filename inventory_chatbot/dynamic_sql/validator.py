from __future__ import annotations

from inventory_chatbot.dynamic_sql.models import QueryPlan


class QueryValidationError(ValueError):
    pass


class QueryValidator:
    def __init__(self, schema_catalog: dict[str, dict[str, object]]) -> None:
        self._schema_catalog = schema_catalog

    def validate(self, plan: QueryPlan) -> QueryPlan:
        self._require_table(plan.base_table)

        for select in plan.selects:
            self._require_qualified_column(select.column)

        for aggregate in plan.aggregates:
            if aggregate.function != "COUNT":
                self._require_qualified_column(aggregate.column)
            elif aggregate.column != "*":
                self._require_qualified_column(aggregate.column)

        for join in plan.joins:
            self._validate_join(join.left, join.right)

        for query_filter in plan.filters:
            self._require_qualified_column(query_filter.column)
            if query_filter.operator == "BETWEEN":
                if not isinstance(query_filter.value, list | tuple) or len(query_filter.value) != 2:
                    raise QueryValidationError("BETWEEN filters must use exactly two values")
            if query_filter.operator == "IN" and not isinstance(query_filter.value, list | tuple):
                raise QueryValidationError("IN filters must use a list of values")

        for group in plan.group_by:
            self._require_qualified_column(group)

        for order in plan.order_by:
            if "." in order.expression:
                self._require_qualified_column(order.expression)

        return plan

    def _require_table(self, table_name: str) -> None:
        if table_name not in self._schema_catalog:
            raise QueryValidationError(f"Unknown table: {table_name}")

    def _require_qualified_column(self, column_ref: str) -> None:
        table_name, column_name = self._split_column_ref(column_ref)
        self._require_table(table_name)
        columns = self._schema_catalog[table_name]["columns"]
        if column_name not in columns:
            raise QueryValidationError(f"Unknown column: {column_ref}")

    def _validate_join(self, left_ref: str, right_ref: str) -> None:
        left_table, left_column = self._split_column_ref(left_ref)
        right_table, right_column = self._split_column_ref(right_ref)
        self._require_qualified_column(left_ref)
        self._require_qualified_column(right_ref)

        left_joins = self._schema_catalog[left_table]["joins"]
        right_joins = self._schema_catalog[right_table]["joins"]

        left_target = left_joins.get(left_column)
        right_target = right_joins.get(right_column)

        valid_from_left = left_target == (right_table, right_column)
        valid_from_right = right_target == (left_table, left_column)

        if not valid_from_left and not valid_from_right:
            raise QueryValidationError(f"Invalid join: {left_ref} = {right_ref}")

    @staticmethod
    def _split_column_ref(column_ref: str) -> tuple[str, str]:
        if "." not in column_ref:
            raise QueryValidationError(f"Columns must be qualified as Table.Column: {column_ref}")
        table_name, column_name = column_ref.split(".", 1)
        return table_name, column_name
