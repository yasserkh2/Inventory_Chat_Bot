from __future__ import annotations

from typing import Any

from inventory_chatbot.data.interfaces import (
    AssetReadRepository,
    BillingReadRepository,
    CustomerLookupRepository,
    ProcurementReadRepository,
    SalesReadRepository,
)
from inventory_chatbot.sql_backend.errors import SQLBackendRuntimeError
from inventory_chatbot.sql_backend.mapper import map_table_row


class SQLServerRepository(
    AssetReadRepository,
    BillingReadRepository,
    ProcurementReadRepository,
    SalesReadRepository,
    CustomerLookupRepository,
):
    _TABLES = {
        "assets": "Assets",
        "sites": "Sites",
        "vendors": "Vendors",
        "bills": "Bills",
        "purchase_orders": "PurchaseOrders",
        "sales_orders": "SalesOrders",
        "customers": "Customers",
    }

    def __init__(self, *, engine) -> None:
        self._engine = engine

    def list_assets(self) -> list[dict[str, Any]]:
        return self._fetch_table_rows(self._TABLES["assets"])

    def list_sites(self) -> list[dict[str, Any]]:
        return self._fetch_table_rows(self._TABLES["sites"])

    def list_vendors(self) -> list[dict[str, Any]]:
        return self._fetch_table_rows(self._TABLES["vendors"])

    def list_bills(self) -> list[dict[str, Any]]:
        return self._fetch_table_rows(self._TABLES["bills"])

    def list_purchase_orders(self) -> list[dict[str, Any]]:
        return self._fetch_table_rows(self._TABLES["purchase_orders"])

    def list_sales_orders(self) -> list[dict[str, Any]]:
        return self._fetch_table_rows(self._TABLES["sales_orders"])

    def list_customers(self) -> list[dict[str, Any]]:
        return self._fetch_table_rows(self._TABLES["customers"])

    def find_customer_by_name(self, customer_name: str) -> dict[str, Any] | None:
        try:
            from sqlalchemy import text
        except ModuleNotFoundError as exc:  # pragma: no cover - dependency presence
            raise SQLBackendRuntimeError(
                "SQLAlchemy is required for SQL backend mode. Install `sqlalchemy` and `pyodbc`."
            ) from exc

        query = text(
            "SELECT TOP 1 * FROM Customers "
            "WHERE LOWER(CustomerName) = LOWER(:customer_name) "
            "ORDER BY CustomerId ASC"
        )
        try:
            with self._engine.connect() as connection:
                row = connection.execute(query, {"customer_name": customer_name.strip()}).mappings().first()
        except Exception as exc:  # pragma: no cover - depends on runtime DB
            raise SQLBackendRuntimeError(f"Failed to lookup customer: {exc}") from exc
        if row is None:
            return None
        return map_table_row(dict(row))

    def _fetch_table_rows(self, table_name: str) -> list[dict[str, Any]]:
        try:
            from sqlalchemy import text
        except ModuleNotFoundError as exc:  # pragma: no cover - dependency presence
            raise SQLBackendRuntimeError(
                "SQLAlchemy is required for SQL backend mode. Install `sqlalchemy` and `pyodbc`."
            ) from exc

        query = text(f"SELECT * FROM {table_name}")
        try:
            with self._engine.connect() as connection:
                rows = connection.execute(query).mappings().all()
        except Exception as exc:  # pragma: no cover - depends on runtime DB
            raise SQLBackendRuntimeError(f"Failed to fetch {table_name}: {exc}") from exc
        return [map_table_row(dict(row)) for row in rows]

