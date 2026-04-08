from __future__ import annotations

import sys
import types
import unittest
from datetime import date, datetime
from decimal import Decimal
from unittest.mock import patch

from inventory_chatbot.dynamic_sql.models import QueryPlan, SelectSpec
from inventory_chatbot.sql_backend.mapper import (
    map_dynamic_result_rows,
    map_table_row,
    to_snake_case,
)
from inventory_chatbot.sql_backend.query_runner import SQLServerQueryRunner
from inventory_chatbot.sql_backend.repository import SQLServerRepository


class SQLBackendMapperTests(unittest.TestCase):
    def test_to_snake_case_converts_schema_column_names(self) -> None:
        self.assertEqual(to_snake_case("CustomerName"), "customer_name")
        self.assertEqual(to_snake_case("SODate"), "so_date")

    def test_map_table_row_normalizes_keys_and_decimals(self) -> None:
        mapped = map_table_row(
            {
                "AssetId": 1,
                "Cost": Decimal("1200.00"),
                "PurchaseDate": date(2026, 1, 15),
                "CreatedAt": datetime(2026, 1, 1, 9, 0, 0),
            }
        )
        self.assertEqual(mapped["asset_id"], 1)
        self.assertEqual(mapped["cost"], 1200.0)
        self.assertEqual(mapped["purchase_date"], date(2026, 1, 15))
        self.assertEqual(mapped["created_at"], datetime(2026, 1, 1, 9, 0, 0))

    def test_map_dynamic_result_rows_preserves_expected_projection_keys(self) -> None:
        query_plan = QueryPlan(
            base_table="Bills",
            selects=[SelectSpec(column="Bills.Currency")],
            order_by=[],
            joins=[],
            filters=[],
            group_by=[],
            aggregates=[],
        )
        mapped = map_dynamic_result_rows([{"Currency": "USD"}], query_plan)
        self.assertEqual(mapped[0]["Bills.Currency"], "USD")


class SQLServerRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repository = SQLServerRepository(engine=object())

    def test_repository_methods_route_to_expected_tables(self) -> None:
        with patch.object(self.repository, "_fetch_table_rows", return_value=[{"id": 1}]) as fetch:
            self.assertEqual(self.repository.list_assets(), [{"id": 1}])
            fetch.assert_any_call("Assets")
            self.assertEqual(self.repository.list_sites(), [{"id": 1}])
            fetch.assert_any_call("Sites")
            self.assertEqual(self.repository.list_vendors(), [{"id": 1}])
            fetch.assert_any_call("Vendors")
            self.assertEqual(self.repository.list_bills(), [{"id": 1}])
            fetch.assert_any_call("Bills")
            self.assertEqual(self.repository.list_purchase_orders(), [{"id": 1}])
            fetch.assert_any_call("PurchaseOrders")
            self.assertEqual(self.repository.list_sales_orders(), [{"id": 1}])
            fetch.assert_any_call("SalesOrders")
            self.assertEqual(self.repository.list_customers(), [{"id": 1}])
            fetch.assert_any_call("Customers")

    def test_find_customer_by_name_returns_mapped_row(self) -> None:
        fake_sqlalchemy = types.SimpleNamespace(text=lambda query: query)

        class FakeResult:
            @staticmethod
            def mappings():
                return FakeResult()

            @staticmethod
            def first():
                return {
                    "CustomerId": 1,
                    "CustomerName": "Acme Corp",
                    "CreatedAt": datetime(2026, 1, 1, 9, 0, 0),
                }

        class FakeConnection:
            @staticmethod
            def execute(*_args, **_kwargs):
                return FakeResult()

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

        class FakeEngine:
            @staticmethod
            def connect():
                return FakeConnection()

        repository = SQLServerRepository(engine=FakeEngine())
        with patch.dict(sys.modules, {"sqlalchemy": fake_sqlalchemy}):
            row = repository.find_customer_by_name("Acme Corp")
        self.assertEqual(row["customer_id"], 1)
        self.assertEqual(row["customer_name"], "Acme Corp")


class SQLBackendQueryRunnerTests(unittest.TestCase):
    def test_sqlite_normalizes_top_to_limit(self) -> None:
        class _Url:
            @staticmethod
            def get_backend_name() -> str:
                return "sqlite"

        class _Engine:
            url = _Url()

        runner = SQLServerQueryRunner(engine=_Engine())
        normalized = runner._normalize_sql_for_engine(
            "SELECT TOP 5 Assets.AssetId FROM Assets ORDER BY Assets.AssetId ASC;"
        )
        self.assertEqual(
            normalized,
            "SELECT Assets.AssetId FROM Assets ORDER BY Assets.AssetId ASC LIMIT 5;",
        )


if __name__ == "__main__":
    unittest.main()
