from __future__ import annotations

import unittest
from datetime import date

from inventory_chatbot.data.seed_data import build_seed_data
from inventory_chatbot.dynamic_sql.engine import DynamicQueryEngine
from inventory_chatbot.dynamic_sql.models import (
    AggregateSpec,
    FilterSpec,
    JoinSpec,
    OrderBySpec,
    QueryPlan,
    SelectSpec,
)
from inventory_chatbot.dynamic_sql.validator import QueryValidationError, QueryValidator
from inventory_chatbot.dynamic_sql.schema_catalog import SCHEMA_CATALOG


class DynamicSqlTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = DynamicQueryEngine()
        self.data = build_seed_data()

    def test_asset_count_by_site(self) -> None:
        plan = QueryPlan(
            base_table="Assets",
            selects=[SelectSpec(column="Sites.SiteName", alias="SiteName")],
            aggregates=[AggregateSpec(function="COUNT", column="Assets.AssetId", alias="AssetCount")],
            joins=[JoinSpec(left="Assets.SiteId", right="Sites.SiteId")],
            filters=[FilterSpec(column="Assets.Status", operator="<>", value="Disposed")],
            group_by=["Sites.SiteName"],
            order_by=[OrderBySpec(expression="AssetCount", direction="DESC")],
        )

        result = self.engine.run(plan, self.data)

        self.assertIn("JOIN Sites ON Assets.SiteId = Sites.SiteId", result.sql)
        self.assertEqual(result.rows[0]["SiteName"], "Cairo Main Warehouse")
        self.assertEqual(result.rows[0]["AssetCount"], 2)

    def test_total_billed_amount_by_vendor_for_last_quarter(self) -> None:
        plan = QueryPlan(
            base_table="Bills",
            selects=[SelectSpec(column="Vendors.VendorName", alias="VendorName")],
            aggregates=[AggregateSpec(function="SUM", column="Bills.TotalAmount", alias="TotalBilled")],
            joins=[JoinSpec(left="Bills.VendorId", right="Vendors.VendorId")],
            filters=[
                FilterSpec(column="Bills.Status", operator="<>", value="Void"),
                FilterSpec(
                    column="Bills.BillDate",
                    operator="BETWEEN",
                    value=[date(2026, 1, 1), date(2026, 3, 31)],
                ),
            ],
            group_by=["Vendors.VendorName"],
            order_by=[OrderBySpec(expression="TotalBilled", direction="DESC")],
        )

        result = self.engine.run(plan, self.data)

        self.assertEqual(result.rows[0]["VendorName"], "Global Industrial Ltd")
        self.assertEqual(result.rows[0]["TotalBilled"], 7250.5)

    def test_sales_orders_for_customer_in_date_range(self) -> None:
        plan = QueryPlan(
            base_table="SalesOrders",
            aggregates=[AggregateSpec(function="COUNT", column="SalesOrders.SOId", alias="SalesOrderCount")],
            joins=[JoinSpec(left="SalesOrders.CustomerId", right="Customers.CustomerId")],
            filters=[
                FilterSpec(column="Customers.CustomerName", operator="=", value="Acme Corp"),
                FilterSpec(
                    column="SalesOrders.SODate",
                    operator="BETWEEN",
                    value=[date(2026, 3, 1), date(2026, 3, 31)],
                ),
            ],
        )

        result = self.engine.run(plan, self.data)

        self.assertEqual(result.rows[0]["SalesOrderCount"], 2)

    def test_invalid_join_is_rejected(self) -> None:
        validator = QueryValidator(SCHEMA_CATALOG)
        plan = QueryPlan(
            base_table="Assets",
            aggregates=[AggregateSpec(function="COUNT", column="Assets.AssetId", alias="AssetCount")],
            joins=[JoinSpec(left="Assets.SiteId", right="Customers.CustomerId")],
        )

        with self.assertRaises(QueryValidationError):
            validator.validate(plan)


if __name__ == "__main__":
    unittest.main()
