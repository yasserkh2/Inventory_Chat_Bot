from __future__ import annotations

from inventory_chatbot.dynamic_sql.schema_catalog import SCHEMA_CATALOG


class SchemaChatService:
    def try_answer(self, message: str) -> str | None:
        normalized = " ".join(message.lower().strip().split())
        if not normalized:
            return None

        if normalized in {"hi", "hello", "hey", "good morning", "good evening"}:
            return (
                "I can help you explore the inventory data, inspect the schema, and answer analytics questions. "
                "You can ask what tables we have, what columns are in a table, or ask a business question."
            )

        if (
            "what tables" in normalized
            or "which tables" in normalized
            or normalized == "tables"
            or ("table" in normalized and self._contains_any(normalized, ("have", "available", "exist")))
        ):
            table_names = ", ".join(SCHEMA_CATALOG.keys())
            return f"We currently have these tables: {table_names}."

        if "what columns" in normalized or "which columns" in normalized:
            for table_name in SCHEMA_CATALOG:
                if table_name.lower() in normalized:
                    columns = ", ".join(SCHEMA_CATALOG[table_name]["columns"].keys())
                    return f"The columns in {table_name} are: {columns}."
            return "Tell me which table you want, and I can list its columns."

        if "schema" in normalized and ("show" in normalized or "what" in normalized):
            return (
                "The schema includes Customers, Vendors, Sites, Locations, Items, Assets, Bills, "
                "PurchaseOrders, PurchaseOrderLines, SalesOrders, SalesOrderLines, and AssetTransactions."
            )

        return None

    @staticmethod
    def _contains_any(message: str, patterns: tuple[str, ...]) -> bool:
        return any(pattern in message for pattern in patterns)
