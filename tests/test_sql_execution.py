from __future__ import annotations

import unittest

from inventory_chatbot.data.memory_repository import InMemoryRepository
from inventory_chatbot.dynamic_sql.models import AggregateSpec, JoinSpec, QueryPlan, SelectSpec
from inventory_chatbot.sql_execution.models import SQLExecutionRequest
from inventory_chatbot.sql_execution.service import SQLExecutionService, SQLExecutionServiceError


class SQLExecutionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repository = InMemoryRepository()
        self.service = SQLExecutionService(seed_data=self.repository.export_seed_data())

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


class _FakeQueryRunner:
    def __init__(self, rows: list[dict]) -> None:
        self._rows = rows
        self.calls: list[dict[str, object]] = []

    def execute_sql(self, *, sql_query: str, query_plan: QueryPlan) -> list[dict]:
        self.calls.append({"sql_query": sql_query, "query_plan": query_plan})
        return list(self._rows)


class SQLExecutionRunnerTests(unittest.TestCase):
    def test_execute_uses_query_runner_when_configured(self) -> None:
        fake_runner = _FakeQueryRunner(rows=[{"Bills.Currency": "USD"}])
        service = SQLExecutionService(query_runner=fake_runner)
        request = SQLExecutionRequest(
            user_message="Tell me currencies",
            query_plan=QueryPlan(
                base_table="Bills",
                selects=[SelectSpec(column="Bills.Currency")],
                order_by=[],
                joins=[],
                filters=[],
                group_by=[],
                aggregates=[],
            ),
            sql_query="SELECT Bills.Currency FROM Bills;",
            source_agent="billing",
            allowed_tables=["Bills", "Vendors"],
        )

        result, sql = service.execute(request)

        self.assertEqual(sql, "SELECT Bills.Currency FROM Bills;")
        self.assertEqual(result.answer_context["row_count"], 1)
        self.assertEqual(result.answer_context["rows"][0]["Bills.Currency"], "USD")
        self.assertEqual(len(fake_runner.calls), 1)
        self.assertEqual(fake_runner.calls[0]["sql_query"], "SELECT Bills.Currency FROM Bills;")

    def test_execute_with_query_runner_still_enforces_allowed_tables(self) -> None:
        fake_runner = _FakeQueryRunner(rows=[])
        service = SQLExecutionService(query_runner=fake_runner)
        request = SQLExecutionRequest(
            user_message="Count bills by vendor",
            query_plan=QueryPlan(
                base_table="Bills",
                selects=[SelectSpec(column="Vendors.VendorName")],
                joins=[JoinSpec(left="Bills.VendorId", right="Vendors.VendorId")],
                filters=[],
                group_by=["Vendors.VendorName"],
                order_by=[],
                aggregates=[
                    AggregateSpec(
                        function="COUNT",
                        column="Bills.BillId",
                        alias="BillCount",
                    )
                ],
            ),
            source_agent="billing",
            allowed_tables=["Bills"],
        )

        with self.assertRaises(SQLExecutionServiceError):
            service.execute(request)
        self.assertEqual(fake_runner.calls, [])


if __name__ == "__main__":
    unittest.main()
