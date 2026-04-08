from __future__ import annotations

import unittest

from inventory_chatbot.data.memory_repository import InMemoryRepository
from inventory_chatbot.dynamic_sql.models import AggregateSpec, JoinSpec, QueryPlan, SelectSpec
from inventory_chatbot.sql_execution.models import SQLExecutionRequest
from inventory_chatbot.sql_execution.service import SQLExecutionService, SQLExecutionServiceError


class SQLExecutionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repository = InMemoryRepository()
        self.service = SQLExecutionService(seed_data=self.repository._data)

    def test_preview_sql_validates_and_compiles(self) -> None:
        request = SQLExecutionRequest(
            user_message="How many active assets by site?",
            query_plan=QueryPlan(
                base_table="Assets",
                selects=[SelectSpec(column="Sites.SiteName", alias="SiteName")],
                aggregates=[
                    AggregateSpec(
                        function="COUNT",
                        column="Assets.AssetId",
                        alias="AssetCount",
                    )
                ],
                joins=[JoinSpec(left="Assets.SiteId", right="Sites.SiteId")],
                group_by=["Sites.SiteName"],
            ),
            source_agent="assets",
            allowed_tables=["Assets", "Sites"],
        )
        sql = self.service.preview_sql(request)
        self.assertIn("FROM Assets", sql)
        self.assertIn("JOIN Sites ON Assets.SiteId = Sites.SiteId", sql)

    def test_execute_returns_rows_and_sql(self) -> None:
        request = SQLExecutionRequest(
            user_message="How many active assets by site?",
            query_plan=QueryPlan(
                base_table="Assets",
                selects=[SelectSpec(column="Sites.SiteName", alias="SiteName")],
                aggregates=[
                    AggregateSpec(
                        function="COUNT",
                        column="Assets.AssetId",
                        alias="AssetCount",
                    )
                ],
                joins=[JoinSpec(left="Assets.SiteId", right="Sites.SiteId")],
                filters=[],
                group_by=["Sites.SiteName"],
            ),
            source_agent="assets",
            allowed_tables=["Assets", "Sites"],
        )
        result, sql = self.service.execute(request)
        self.assertIn("SELECT", sql)
        self.assertGreaterEqual(result.answer_context["row_count"], 1)

    def test_disallowed_table_is_rejected(self) -> None:
        request = SQLExecutionRequest(
            user_message="How many active assets by site?",
            query_plan=QueryPlan(
                base_table="Assets",
                selects=[SelectSpec(column="Vendors.VendorName", alias="VendorName")],
                aggregates=[
                    AggregateSpec(
                        function="COUNT",
                        column="Assets.AssetId",
                        alias="AssetCount",
                    )
                ],
                joins=[JoinSpec(left="Assets.VendorId", right="Vendors.VendorId")],
                group_by=["Vendors.VendorName"],
            ),
            source_agent="assets",
            allowed_tables=["Assets", "Sites"],
        )
        with self.assertRaises(SQLExecutionServiceError):
            self.service.preview_sql(request)


if __name__ == "__main__":
    unittest.main()
