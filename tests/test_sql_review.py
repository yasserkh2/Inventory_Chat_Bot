from __future__ import annotations

import unittest

from inventory_chatbot.sql_review.models import SQLReviewRequest
from inventory_chatbot.sql_review.service import SQLReviewService


class SQLReviewTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = SQLReviewService()

    def test_review_normalizes_supported_sql(self) -> None:
        result = self.service.review(
            SQLReviewRequest(
                user_message="Show total invoice amount by vendor for last quarter",
                sql_query=(
                    "SELECT Vendors.VendorName AS VendorName, "
                    "SUM(Bills.TotalAmount) AS TotalInvoiceAmount "
                    "FROM Bills "
                    "INNER JOIN Vendors ON Bills.VendorId = Vendors.VendorId "
                    "WHERE Bills.BillDate BETWEEN '2026-01-01' AND '2026-03-31' "
                    "GROUP BY Vendors.VendorName "
                    "ORDER BY TotalInvoiceAmount DESC;"
                ),
                source_agent="billing",
                allowed_tables=["Bills", "Vendors"],
            )
        )
        self.assertTrue(result.approved)
        self.assertIsNotNone(result.normalized_query_plan)
        self.assertEqual(result.normalized_query_plan.base_table, "Bills")
        self.assertEqual(result.normalized_query_plan.group_by, ["Vendors.VendorName"])

    def test_review_normalizes_sql_with_aliases(self) -> None:
        result = self.service.review(
            SQLReviewRequest(
                user_message="Show total invoice amount by vendor for last quarter",
                sql_query=(
                    "SELECT V.VendorName AS VendorName, SUM(B.TotalAmount) AS TotalInvoiceAmount "
                    "FROM Bills B INNER JOIN Vendors V ON B.VendorId = V.VendorId "
                    "GROUP BY V.VendorName;"
                ),
                source_agent="billing",
                allowed_tables=["Bills", "Vendors"],
            )
        )
        self.assertTrue(result.approved)
        self.assertIsNotNone(result.normalized_query_plan)
        self.assertEqual(result.normalized_query_plan.base_table, "Bills")
        self.assertEqual(result.normalized_query_plan.group_by, ["Vendors.VendorName"])
        self.assertEqual(result.normalized_query_plan.joins[0].left, "Bills.VendorId")
        self.assertEqual(result.normalized_query_plan.joins[0].right, "Vendors.VendorId")

    def test_review_normalizes_distinct_select_into_group_by_plan(self) -> None:
        result = self.service.review(
            SQLReviewRequest(
                user_message="Tell me the currencies we have in the data",
                sql_query=(
                    "SELECT DISTINCT Bills.Currency "
                    "FROM Bills "
                    "ORDER BY Bills.Currency ASC;"
                ),
                source_agent="billing",
                allowed_tables=["Bills", "Vendors"],
            )
        )
        self.assertTrue(result.approved)
        self.assertIsNotNone(result.normalized_query_plan)
        self.assertEqual(result.normalized_query_plan.base_table, "Bills")
        self.assertEqual(result.normalized_query_plan.selects[0].column, "Bills.Currency")
        self.assertEqual(result.normalized_query_plan.group_by, ["Bills.Currency"])

    def test_review_supports_top_distinct_modifier_order(self) -> None:
        result = self.service.review(
            SQLReviewRequest(
                user_message="Tell me the currencies we have in the data",
                sql_query=(
                    "SELECT TOP 10 DISTINCT Bills.Currency "
                    "FROM Bills "
                    "ORDER BY Bills.Currency ASC;"
                ),
                source_agent="billing",
                allowed_tables=["Bills", "Vendors"],
            )
        )
        self.assertTrue(result.approved)
        self.assertIsNotNone(result.normalized_query_plan)
        self.assertEqual(result.normalized_query_plan.limit, 10)
        self.assertEqual(result.normalized_query_plan.selects[0].column, "Bills.Currency")
        self.assertEqual(result.normalized_query_plan.group_by, ["Bills.Currency"])

    def test_review_supports_sqlite_style_limit_clause(self) -> None:
        result = self.service.review(
            SQLReviewRequest(
                user_message="Show first 5 rows of customers table",
                sql_query=(
                    "SELECT Customers.CustomerId, Customers.CustomerName "
                    "FROM Customers "
                    "ORDER BY Customers.CustomerId ASC "
                    "LIMIT 5;"
                ),
                source_agent="sales",
                allowed_tables=["Customers", "SalesOrders", "SalesOrderLines", "Sites", "Items"],
            )
        )
        self.assertTrue(result.approved)
        self.assertIsNotNone(result.normalized_query_plan)
        self.assertEqual(result.normalized_query_plan.limit, 5)
        self.assertEqual(result.normalized_query_plan.order_by[0].expression, "Customers.CustomerId")

    def test_review_auto_qualifies_unqualified_columns_in_single_table_query(self) -> None:
        result = self.service.review(
            SQLReviewRequest(
                user_message="What are the name and billing city for customer code CUST-1004?",
                sql_query=(
                    "SELECT CustomerName, BillingCity "
                    "FROM Customers "
                    "WHERE CustomerCode = 'CUST-1004';"
                ),
                source_agent="sales",
                allowed_tables=["Customers", "SalesOrders", "SalesOrderLines", "Sites", "Items"],
            )
        )
        self.assertTrue(result.approved)
        self.assertIsNotNone(result.normalized_query_plan)
        plan = result.normalized_query_plan
        self.assertEqual(plan.selects[0].column, "Customers.CustomerName")
        self.assertEqual(plan.selects[1].column, "Customers.BillingCity")
        self.assertEqual(plan.filters[0].column, "Customers.CustomerCode")

    def test_review_auto_qualifies_unqualified_filter_column_for_count_query(self) -> None:
        result = self.service.review(
            SQLReviewRequest(
                user_message="How many active customers do we have?",
                sql_query=(
                    "SELECT COUNT(*) AS ActiveCustomers "
                    "FROM Customers "
                    "WHERE IsActive = 1;"
                ),
                source_agent="sales",
                allowed_tables=["Customers", "SalesOrders", "SalesOrderLines", "Sites", "Items"],
            )
        )
        self.assertTrue(result.approved)
        self.assertIsNotNone(result.normalized_query_plan)
        self.assertEqual(result.normalized_query_plan.filters[0].column, "Customers.IsActive")


if __name__ == "__main__":
    unittest.main()
