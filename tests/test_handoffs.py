from __future__ import annotations

import unittest

from inventory_chatbot.dynamic_sql.models import AggregateSpec, QueryPlan
from inventory_chatbot.handoffs.service import OrchestratorHandoffService
from inventory_chatbot.orchestrator.models import OrchestratorDecision, RequiredDataPoint
from inventory_chatbot.sql_agents.models import SQLAgentDecision


class HandoffTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = OrchestratorHandoffService()
        self.decision = OrchestratorDecision(
            agent="assets",
            user_need="Count active assets by site.",
            analysis_summary="This is an assets-domain aggregate that needs Assets joined to Sites.",
            required_data=[
                RequiredDataPoint(
                    table="Assets",
                    columns=["AssetId", "Status", "SiteId"],
                    reason="Assets provide the counted records and the site link.",
                ),
                RequiredDataPoint(
                    table="Sites",
                    columns=["SiteId", "SiteName"],
                    reason="Sites provide the grouped label for the output.",
                ),
            ],
            handoff_instructions="Group active assets by site and return the grouped count.",
        )

    def test_build_specialist_activation(self) -> None:
        activation = self.service.build_specialist_activation(self.decision)
        self.assertEqual(activation.agent_name, "assets")
        self.assertIn("User need: Count active assets by site.", activation.instructions)
        self.assertIn("Required data: Assets(AssetId, Status, SiteId)", activation.instructions)
        self.assertIn("orchestrator", activation.context)

    def test_build_planner_activation(self) -> None:
        activation = self.service.build_planner_activation(self.decision)
        self.assertEqual(activation.agent_name, "assets")
        self.assertIn(
            "Group active assets by site and return the grouped count.",
            activation.handoff_summary,
        )
        self.assertIn("Required data contract:", activation.handoff_summary)
        self.assertIn("Assets(AssetId, Status, SiteId)", activation.handoff_summary)
        self.assertIn("Sites(SiteId, SiteName)", activation.handoff_summary)
        self.assertEqual(activation.context["required_tables"], ["Assets", "Sites"])

    def test_build_dynamic_sql_activation(self) -> None:
        query_plan = QueryPlan(
            base_table="Assets",
            aggregates=[
                AggregateSpec(
                    function="COUNT",
                    column="Assets.AssetId",
                    alias="AssetCount",
                )
            ],
            group_by=["Sites.SiteName"],
        )
        activation = self.service.build_dynamic_sql_activation(
            decision=self.decision,
            query_plan=query_plan,
        )
        self.assertEqual(activation.target_agent, "dynamic_sql")
        self.assertIn("assets agent", activation.instructions)
        self.assertEqual(activation.context["source_agent"], "assets")
        self.assertEqual(activation.context["query_plan"]["base_table"], "Assets")

    def test_build_execution_request(self) -> None:
        sql_agent_decision = SQLAgentDecision(
            agent_name="assets",
            action="execute",
            user_need="Count active assets by site.",
            analysis_summary="This is an assets aggregate.",
            required_data=self.decision.required_data,
            query_strategy="Count assets grouped by site.",
            query_plan=QueryPlan(
                base_table="Assets",
                aggregates=[
                    AggregateSpec(
                        function="COUNT",
                        column="Assets.AssetId",
                        alias="AssetCount",
                    )
                ],
            ),
        )
        request = self.service.build_execution_request(
            user_message="How many active assets by site?",
            orchestrator_decision=self.decision,
            sql_agent_decision=sql_agent_decision,
        )
        self.assertEqual(request.source_agent, "assets")
        self.assertEqual(
            request.allowed_tables,
            ["Assets", "Sites", "Locations", "Items", "AssetTransactions", "Vendors"],
        )
        self.assertEqual(request.query_plan.base_table, "Assets")


if __name__ == "__main__":
    unittest.main()
