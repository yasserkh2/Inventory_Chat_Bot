from __future__ import annotations

import unittest

from inventory_chatbot.data.memory_repository import InMemoryRepository
from inventory_chatbot.services.date_parser import DateParser
from inventory_chatbot.specialists.assets import AssetSpecialist
from inventory_chatbot.specialists.billing import BillingSpecialist
from inventory_chatbot.specialists.procurement import ProcurementSpecialist
from inventory_chatbot.specialists.sales import SalesSpecialist
from inventory_chatbot.models.domain import AgentTask, SessionState
from tests.helpers import FIXED_TODAY


class SpecialistTests(unittest.TestCase):
    def setUp(self) -> None:
        repository = InMemoryRepository()
        date_parser = DateParser(today_provider=lambda: FIXED_TODAY)
        self.assets = AssetSpecialist(repository, date_parser)
        self.billing = BillingSpecialist(repository, date_parser)
        self.procurement = ProcurementSpecialist(repository)
        self.sales = SalesSpecialist(repository, date_parser)

    def test_asset_count_by_site_result(self) -> None:
        match = self.assets.match("How many assets by site?", SessionState(session_id="s1"))
        self.assertIsNotNone(match)
        plan = self.assets.build_query_plan(match)
        result = self.assets.execute(plan)
        rows = result.answer_context["rows"]
        self.assertEqual(rows[0]["site_name"], "Cairo Main Warehouse")
        self.assertEqual(rows[0]["asset_count"], 2)
        self.assertIn("GROUP BY s.SiteName", self.assets.render_sql(plan))

    def test_billing_requires_last_quarter_when_missing(self) -> None:
        match = self.billing.match("What is the total billed amount?", SessionState(session_id="s1"))
        self.assertIsNotNone(match)
        self.assertEqual(match.missing_parameters, ["date_range"])

    def test_procurement_open_purchase_orders(self) -> None:
        match = self.procurement.match(
            "How many open purchase orders are currently pending?",
            SessionState(session_id="s1"),
        )
        self.assertIsNotNone(match)
        result = self.procurement.execute(self.procurement.build_query_plan(match))
        self.assertEqual(result.answer_context["open_purchase_order_count"], 2)

    def test_sales_customer_last_month(self) -> None:
        match = self.sales.match(
            "How many sales orders were created for Acme Corp last month?",
            SessionState(session_id="s1"),
        )
        self.assertIsNotNone(match)
        plan = self.sales.build_query_plan(match)
        result = self.sales.execute(plan)
        self.assertEqual(result.answer_context["sales_order_count"], 2)
        self.assertIn("Acme Corp", self.sales.render_sql(plan))

    def test_specialist_handles_task_with_structured_reply(self) -> None:
        reply = self.sales.handle_task(
            AgentTask(
                request_id="req-1",
                user_message="How many sales orders were created for Acme Corp last month?",
                target_agent="sales",
                instructions="Handle this using the sales specialist rules.",
            ),
            SessionState(session_id="s1"),
        )
        self.assertEqual(reply.status, "ok")
        self.assertEqual(reply.agent_name, "sales")
        self.assertEqual(reply.computed_result.answer_context["sales_order_count"], 2)
        self.assertIn("Acme Corp", reply.sql_query)


if __name__ == "__main__":
    unittest.main()
