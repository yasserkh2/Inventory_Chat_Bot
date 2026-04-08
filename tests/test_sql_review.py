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

    def test_review_rejects_sql_with_aliases(self) -> None:
        result = self.service.review(
            SQLReviewRequest(
                user_message="Show total invoice amount by vendor for last quarter",
                sql_query=(
                    "SELECT V.VendorName AS VendorName, SUM(B.TotalAmount) AS TotalInvoiceAmount "
                    "FROM Bills B INNER JOIN Vendors V ON B.VendorId = V.VendorId;"
                ),
                source_agent="billing",
                allowed_tables=["Bills", "Vendors"],
            )
        )
        self.assertFalse(result.approved)
        self.assertIn("aliases", result.issues[0].lower())

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


if __name__ == "__main__":
    unittest.main()
