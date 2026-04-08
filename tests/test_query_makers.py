from __future__ import annotations

import unittest

from inventory_chatbot.handoffs.models import PlannerActivation
from inventory_chatbot.models.domain import SessionState
from inventory_chatbot.query_makers.llm_based import LLMQueryMaker
from tests.helpers import FIXED_TODAY, FakeLLMClient


class LLMQueryMakerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.query_maker = LLMQueryMaker(
            llm_client=FakeLLMClient(),
            today=FIXED_TODAY,
            customer_names=["Acme Corp", "Bright Retail", "Northwind LLC"],
        )

    def test_builds_asset_count_by_site_plan(self) -> None:
        session_state = SessionState(session_id="s1")
        plan = self.query_maker.make_plan(
            "How many assets by site?",
            session_state,
            PlannerActivation(
                agent_name="assets",
                handoff_summary="Group active assets by site and return the grouped count.",
            ),
        )
        self.assertIsNotNone(plan)
        self.assertEqual(plan.base_table, "Assets")
        self.assertEqual(plan.group_by, ["Sites.SiteName"])

    def test_builds_sales_customer_last_month_plan(self) -> None:
        session_state = SessionState(session_id="s1")
        plan = self.query_maker.make_plan(
            "How many sales orders were created for Acme Corp last month?",
            session_state,
            PlannerActivation(
                agent_name="sales",
                handoff_summary="Count sales orders for the named customer during last month.",
            ),
        )
        self.assertIsNotNone(plan)
        self.assertEqual(plan.base_table, "SalesOrders")
        self.assertEqual(plan.filters[0].value, "Acme Corp")


if __name__ == "__main__":
    unittest.main()
