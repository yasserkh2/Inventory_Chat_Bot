from __future__ import annotations

from typing import Any

from inventory_chatbot.config import AppConfig
from inventory_chatbot.data.seed_data import build_seed_data
from inventory_chatbot.dynamic_sql.schema_catalog import SCHEMA_CATALOG
from inventory_chatbot.sql_backend.connection import build_engine
from inventory_chatbot.sql_backend.mapper import to_snake_case


def initialize_database(config: AppConfig) -> None:
    metadata = _build_metadata()
    engine = build_engine(config)
    metadata.create_all(engine)

    seed_data = build_seed_data()
    table_to_seed_key = {
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

    with engine.begin() as connection:
        for table in reversed(metadata.sorted_tables):
            connection.execute(table.delete())

        for table in metadata.sorted_tables:
            rows = seed_data.get(table_to_seed_key[table.name], [])
            if not rows:
                continue
            payload = [_map_seed_row_to_table(table.name, row) for row in rows]
            connection.execute(table.insert(), payload)


def _build_metadata():
    try:
        from sqlalchemy import (
            Boolean,
            Column,
            Date,
            DateTime,
            ForeignKey,
            Integer,
            MetaData,
            Numeric,
            String,
            Table,
        )
    except ModuleNotFoundError as exc:  # pragma: no cover - dependency presence
        raise RuntimeError(
            "SQLAlchemy is required for SQL backend mode. Install `sqlalchemy` and `pyodbc`."
        ) from exc

    metadata = MetaData()
    type_mapping = {
        "int": Integer,
        "string": String(255),
        "decimal": Numeric(18, 2),
        "date": Date,
        "datetime": DateTime,
        "bool": Boolean,
    }

    for table_name, schema in SCHEMA_CATALOG.items():
        primary_key = schema["primary_key"]
        columns = schema["columns"]
        joins = schema.get("joins", {})

        table_columns = []
        for column_name, raw_type in columns.items():
            column_type = type_mapping[raw_type]
            foreign_key = None
            if column_name in joins:
                target_table, target_column = joins[column_name]
                foreign_key = ForeignKey(f"{target_table}.{target_column}")
            args = [column_type]
            if foreign_key is not None:
                args.append(foreign_key)
            table_columns.append(
                Column(
                    column_name,
                    *args,
                    primary_key=(column_name == primary_key),
                    nullable=(column_name != primary_key),
                )
            )
        Table(table_name, metadata, *table_columns)

    return metadata


def _map_seed_row_to_table(table_name: str, seed_row: dict[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for column_name in SCHEMA_CATALOG[table_name]["columns"]:
        seed_key = to_snake_case(column_name)
        payload[column_name] = seed_row.get(seed_key)
    return payload


if __name__ == "__main__":
    cfg = AppConfig.from_env()
    cfg.validate_sql_backend_configuration()
    initialize_database(cfg)
    print("SQL backend schema and seed data initialized.")
