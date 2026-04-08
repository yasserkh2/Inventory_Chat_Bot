from __future__ import annotations

import re
from typing import Any

from inventory_chatbot.dynamic_sql.compiler import SQLCompiler
from inventory_chatbot.dynamic_sql.models import (
    AggregateSpec,
    FilterSpec,
    JoinSpec,
    OrderBySpec,
    QueryPlan,
    SelectSpec,
)
from inventory_chatbot.dynamic_sql.schema_catalog import SCHEMA_CATALOG
from inventory_chatbot.dynamic_sql.validator import QueryValidationError, QueryValidator
from inventory_chatbot.sql_review.models import SQLReviewRequest, SQLReviewResult


class SQLReviewService:
    def __init__(self, *, schema_catalog: dict[str, dict[str, object]] | None = None) -> None:
        self._schema_catalog = schema_catalog or SCHEMA_CATALOG
        self._validator = QueryValidator(self._schema_catalog)
        self._compiler = SQLCompiler()

    def review(self, request: SQLReviewRequest) -> SQLReviewResult:
        try:
            plan = self._parse_sql(request.sql_query)
            self._validate_allowed_tables(plan, request.allowed_tables)
            validated = self._validator.validate(plan)
        except (ValueError, QueryValidationError) as exc:
            return SQLReviewResult(
                approved=False,
                review_summary="SQL review rejected the generated query.",
                issues=[str(exc)],
                reviewed_sql=request.sql_query,
            )

        return SQLReviewResult(
            approved=True,
            review_summary="SQL review approved the generated query.",
            reviewed_sql=self._compiler.compile(validated),
            normalized_query_plan=validated,
        )

    def _parse_sql(self, sql_query: str) -> QueryPlan:
        sql = " ".join(sql_query.strip().rstrip(";").split())
        if not sql:
            raise ValueError("SQL query is empty.")

        select_match = re.match(r"(?is)^SELECT\s+(?P<select>.+?)\s+FROM\s+(?P<rest>.+)$", sql)
        if select_match is None:
            raise ValueError("SQL must start with SELECT ... FROM ...")

        select_section, has_distinct, limit = self._extract_select_modifiers(
            select_match.group("select")
        )
        remainder = select_match.group("rest")

        from_section, remainder = self._split_next_clause(remainder, ("WHERE", "GROUP BY", "ORDER BY"))
        base_table, joins, alias_lookup = self._parse_from_section(from_section)
        remainder, trailing_limit = self._extract_trailing_limit(remainder)
        if limit is not None and trailing_limit is not None:
            raise ValueError("Multiple row-limit clauses are not supported.")
        if limit is None:
            limit = trailing_limit
        selects, aggregates, select_alias_lookup = self._parse_selects(select_section, alias_lookup)
        filters, group_by, order_by = self._parse_tail_sections(remainder, alias_lookup)
        group_by = [
            select_alias_lookup.get(group_expression.lower(), group_expression)
            for group_expression in group_by
        ]
        if has_distinct:
            if aggregates:
                raise ValueError("DISTINCT with aggregate expressions is not supported.")
            if not selects:
                raise ValueError("DISTINCT requires at least one selected column.")
            if not group_by:
                group_by = [item.column for item in selects]

        return QueryPlan(
            base_table=base_table,
            selects=selects,
            aggregates=aggregates,
            joins=joins,
            filters=filters,
            group_by=group_by,
            order_by=order_by,
            limit=limit,
        )

    @staticmethod
    def _extract_trailing_limit(remainder: str) -> tuple[str, int | None]:
        text = remainder.strip()
        if not text:
            return text, None
        match = re.match(r"(?is)^(?P<body>.+?)\s+LIMIT\s+(?P<limit>\d+)\s*$", text)
        if match is None:
            return text, None
        return match.group("body").strip(), int(match.group("limit"))

    def _extract_select_modifiers(self, select_section: str) -> tuple[str, bool, int | None]:
        text = select_section.strip()
        has_distinct = False
        limit: int | None = None

        while True:
            modifier_applied = False
            if re.match(r"(?is)^DISTINCT\b", text):
                has_distinct = True
                text = re.sub(r"(?is)^DISTINCT\b", "", text, count=1).strip()
                modifier_applied = True
            top_match = re.match(r"(?is)^TOP\s*\(?(?P<limit>\d+)\)?\s+(?P<rest>.+)$", text)
            if top_match is not None:
                if limit is not None:
                    raise ValueError("Multiple TOP clauses are not supported.")
                limit = int(top_match.group("limit"))
                text = top_match.group("rest").strip()
                modifier_applied = True
            if not modifier_applied:
                break

        if not text:
            raise ValueError("SELECT must include at least one select expression.")
        return text, has_distinct, limit

    @staticmethod
    def _split_next_clause(text: str, keywords: tuple[str, ...]) -> tuple[str, str]:
        upper_text = text.upper()
        positions = [upper_text.find(f" {keyword} ") for keyword in keywords if f" {keyword} " in upper_text]
        if not positions:
            return text.strip(), ""
        next_position = min(positions)
        return text[:next_position].strip(), text[next_position + 1 :].strip()

    def _parse_from_section(self, from_section: str) -> tuple[str, list[JoinSpec], dict[str, str]]:
        segments = re.split(r"(?i)\s+(?:INNER\s+)?JOIN\s+", from_section)
        base_table, base_aliases = self._parse_table_reference(segments[0].strip())
        alias_lookup = dict(base_aliases)

        joins: list[JoinSpec] = []
        for join_segment in segments[1:]:
            match = re.match(
                r"(?is)^(?P<table_ref>.+?)\s+ON\s+(?P<left>[\w.]+)\s*=\s*(?P<right>[\w.]+)$",
                join_segment.strip(),
            )
            if match is None:
                raise ValueError(f"Unsupported JOIN clause: {join_segment}")
            table_name, table_aliases = self._parse_table_reference(match.group("table_ref"))
            for alias_key, resolved_table in table_aliases.items():
                existing = alias_lookup.get(alias_key)
                if existing is not None and existing != resolved_table:
                    raise ValueError(
                        f"Alias '{alias_key}' maps to multiple tables: {existing} and {resolved_table}."
                    )
                alias_lookup[alias_key] = resolved_table
            joins.append(
                JoinSpec(
                    left=self._normalize_column_reference(match.group("left"), alias_lookup),
                    right=self._normalize_column_reference(match.group("right"), alias_lookup),
                    join_type="INNER",
                )
            )
        return base_table, joins, alias_lookup

    def _parse_table_reference(self, table_reference: str) -> tuple[str, dict[str, str]]:
        match = re.match(
            r"(?is)^(?P<table>\w+)(?:\s+(?:AS\s+)?(?P<alias>\w+))?$",
            table_reference.strip(),
        )
        if match is None:
            raise ValueError(f"Unsupported table reference: {table_reference}")
        table_name = match.group("table")
        if "." in table_name:
            raise ValueError(f"Invalid table name: {table_name}")
        self._require_table(table_name)
        alias = match.group("alias")
        aliases: dict[str, str] = {table_name.lower(): table_name}
        if alias:
            aliases[alias.lower()] = table_name
        return table_name, aliases

    def _parse_tail_sections(
        self, remainder: str, alias_lookup: dict[str, str]
    ) -> tuple[list[FilterSpec], list[str], list[OrderBySpec]]:
        filters: list[FilterSpec] = []
        group_by: list[str] = []
        order_by: list[OrderBySpec] = []

        text = remainder.strip()
        if not text:
            return filters, group_by, order_by

        where_section = ""
        group_section = ""
        order_section = ""

        if text.upper().startswith("WHERE "):
            where_section, text = self._split_next_clause(text[6:], ("GROUP BY", "ORDER BY"))
        if text.upper().startswith("GROUP BY "):
            group_section, text = self._split_next_clause(text[9:], ("ORDER BY",))
        if text.upper().startswith("ORDER BY "):
            order_section = text[9:].strip()

        if where_section:
            filters = self._parse_filters(where_section, alias_lookup)
        if group_section:
            group_by = [
                self._normalize_column_reference(part.strip(), alias_lookup)
                for part in self._split_csv(group_section)
                if part.strip()
            ]
        if order_section:
            order_by = self._parse_order_by(order_section, alias_lookup)
        return filters, group_by, order_by

    def _parse_selects(
        self, select_section: str, alias_lookup: dict[str, str]
    ) -> tuple[list[SelectSpec], list[AggregateSpec], dict[str, str]]:
        selects: list[SelectSpec] = []
        aggregates: list[AggregateSpec] = []
        select_alias_lookup: dict[str, str] = {}
        for part in self._split_csv(select_section):
            item = part.strip()
            aggregate_match = re.match(
                r"(?is)^(COUNT|SUM|AVG|MIN|MAX)\((\*|[\w.]+)\)(?:\s+AS\s+(\w+))?$",
                item,
            )
            if aggregate_match is not None:
                function, column, alias = aggregate_match.groups()
                resolved_column = (
                    column
                    if column == "*"
                    else self._normalize_column_reference(column, alias_lookup)
                )
                aggregates.append(
                    AggregateSpec(
                        function=function.upper(),
                        column=resolved_column,
                        alias=alias or f"{function.upper()}_{resolved_column.replace('.', '_')}",
                    )
                )
                continue

            select_match = re.match(r"(?is)^([\w.]+)(?:\s+AS\s+(\w+))?$", item)
            if select_match is None:
                raise ValueError(f"Unsupported SELECT item: {item}")
            column, alias = select_match.groups()
            resolved_column = self._normalize_column_reference(column, alias_lookup)
            selects.append(SelectSpec(column=resolved_column, alias=alias))
            if alias:
                select_alias_lookup[alias.lower()] = resolved_column
        return selects, aggregates, select_alias_lookup

    def _parse_filters(
        self, where_section: str, alias_lookup: dict[str, str]
    ) -> list[FilterSpec]:
        clauses = self._split_and_conditions(where_section)
        filters: list[FilterSpec] = []
        for clause in clauses:
            between_match = re.match(
                r"(?is)^([\w.]+)\s+BETWEEN\s+(.+?)\s+AND\s+(.+)$",
                clause,
            )
            if between_match is not None:
                column, start, end = between_match.groups()
                filters.append(
                    FilterSpec(
                        column=self._normalize_column_reference(column, alias_lookup),
                        operator="BETWEEN",
                        value=[self._parse_literal(start), self._parse_literal(end)],
                    )
                )
                continue

            in_match = re.match(r"(?is)^([\w.]+)\s+IN\s+\((.+)\)$", clause)
            if in_match is not None:
                column, payload = in_match.groups()
                filters.append(
                    FilterSpec(
                        column=self._normalize_column_reference(column, alias_lookup),
                        operator="IN",
                        value=[self._parse_literal(item) for item in self._split_csv(payload)],
                    )
                )
                continue

            binary_match = re.match(r"(?is)^([\w.]+)\s*(=|<>|>=|<=|>|<|LIKE)\s*(.+)$", clause)
            if binary_match is None:
                raise ValueError(f"Unsupported WHERE condition: {clause}")
            column, operator, value = binary_match.groups()
            filters.append(
                FilterSpec(
                    column=self._normalize_column_reference(column, alias_lookup),
                    operator=operator.upper(),
                    value=self._parse_literal(value),
                )
            )
        return filters

    def _parse_order_by(
        self, order_section: str, alias_lookup: dict[str, str]
    ) -> list[OrderBySpec]:
        items: list[OrderBySpec] = []
        for part in self._split_csv(order_section):
            match = re.match(r"(?is)^([\w.]+)(?:\s+(ASC|DESC))?$", part.strip())
            if match is None:
                raise ValueError(f"Unsupported ORDER BY item: {part}")
            expression, direction = match.groups()
            items.append(
                OrderBySpec(
                    expression=self._normalize_column_reference(expression, alias_lookup),
                    direction=(direction or "ASC").upper(),
                )
            )
        return items

    @staticmethod
    def _normalize_column_reference(column_reference: str, alias_lookup: dict[str, str]) -> str:
        if "." not in column_reference:
            return column_reference
        table_token, column_name = column_reference.split(".", 1)
        canonical_table = alias_lookup.get(table_token.lower(), table_token)
        return f"{canonical_table}.{column_name}"

    @staticmethod
    def _split_csv(text: str) -> list[str]:
        items: list[str] = []
        current: list[str] = []
        depth = 0
        for char in text:
            if char == "(":
                depth += 1
            elif char == ")":
                depth = max(0, depth - 1)
            if char == "," and depth == 0:
                items.append("".join(current).strip())
                current = []
                continue
            current.append(char)
        if current:
            items.append("".join(current).strip())
        return items

    @staticmethod
    def _split_and_conditions(text: str) -> list[str]:
        parts: list[str] = []
        tokens = text.split()
        current: list[str] = []
        between_pending = False
        for token in tokens:
            if token.upper() == "BETWEEN":
                between_pending = True
                current.append(token)
                continue
            if token.upper() == "AND" and not between_pending:
                parts.append(" ".join(current).strip())
                current = []
                continue
            current.append(token)
            if between_pending and token.upper() == "AND":
                continue
            if between_pending and len(current) >= 5 and "BETWEEN" in (item.upper() for item in current):
                between_pending = False
        if current:
            parts.append(" ".join(current).strip())
        return parts

    def _validate_allowed_tables(self, plan: QueryPlan, allowed_tables: list[str]) -> None:
        if not allowed_tables:
            return
        used_tables = {plan.base_table}
        for select in plan.selects:
            if "." in select.column:
                used_tables.add(select.column.split(".", 1)[0])
        for aggregate in plan.aggregates:
            if "." in aggregate.column:
                used_tables.add(aggregate.column.split(".", 1)[0])
        for join in plan.joins:
            used_tables.add(join.left.split(".", 1)[0])
            used_tables.add(join.right.split(".", 1)[0])
        for query_filter in plan.filters:
            used_tables.add(query_filter.column.split(".", 1)[0])
        for group_by_expression in plan.group_by:
            if "." in group_by_expression:
                used_tables.add(group_by_expression.split(".", 1)[0])
        for order_by_expression in plan.order_by:
            if "." in order_by_expression.expression:
                used_tables.add(order_by_expression.expression.split(".", 1)[0])
        disallowed = sorted(table for table in used_tables if table not in set(allowed_tables))
        if disallowed:
            raise ValueError(
                "SQL references tables outside the agent domain: " + ", ".join(disallowed)
            )

    def _require_table(self, table_name: str) -> None:
        if table_name not in self._schema_catalog:
            raise ValueError(f"Unknown table: {table_name}")

    @staticmethod
    def _parse_literal(raw_value: str) -> Any:
        value = raw_value.strip()
        if value.upper() == "NULL":
            return None
        if value.startswith("'") and value.endswith("'"):
            return value[1:-1].replace("''", "'")
        if re.fullmatch(r"-?\d+", value):
            return int(value)
        if re.fullmatch(r"-?\d+\.\d+", value):
            return float(value)
        return value
