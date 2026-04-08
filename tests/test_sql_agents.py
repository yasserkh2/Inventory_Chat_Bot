from __future__ import annotations

import unittest

from inventory_chatbot.data.memory_repository import InMemoryRepository
from inventory_chatbot.handoffs.models import PlannerActivation
from inventory_chatbot.models.api import TokenUsage
from inventory_chatbot.models.domain import ComputedResult, SessionState
from inventory_chatbot.sql_agents.llm_based import LLMSQLAgent
from inventory_chatbot.sql_agents.prompts import (
    build_sql_agent_context,
    build_sql_agent_user_prompt,
)
from inventory_chatbot.sql_execution.service import SQLExecutionService
from tests.helpers import FIXED_TODAY, FakeLLMClient


class LoopingSQLAgentLLMClient(FakeLLMClient):
    def __init__(self) -> None:
        self.calls = 0

    def generate_structured_json(
        self, *, system_prompt: str, user_prompt: str
    ) -> tuple[dict | None, TokenUsage]:
        if "sales query-maker agent" in system_prompt.lower():
            self.calls += 1
            if self.calls == 1:
                return (
                    {
                        "agent_name": "sales",
                        "action": "execute",
                        "user_need": "Show customer rows.",
                        "analysis_summary": "This is a customer row request.",
                        "required_data": [],
                        "query_strategy": "",
                        "query_plan": {
                            "base_table": "Customers",
                            "selects": [],
                            "order_by": [],
                        },
                    },
                    TokenUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
                )
        return super().generate_structured_json(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        )


class InvalidSQLAgentLLMClient(FakeLLMClient):
    def generate_structured_json(
        self, *, system_prompt: str, user_prompt: str
    ) -> tuple[dict | None, TokenUsage]:
        if "billing query-maker agent" in system_prompt.lower():
            return (
                {"bad_shape": True},
                TokenUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
            )
        return super().generate_structured_json(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        )


class ReviewRejectedSQLAgentLLMClient(FakeLLMClient):
    def generate_structured_json(
        self, *, system_prompt: str, user_prompt: str
    ) -> tuple[dict | None, TokenUsage]:
        if "billing query-maker agent" in system_prompt.lower():
            return (
                {
                    "agent_name": "billing",
                    "action": "execute",
                    "user_need": "Show total invoice amount by vendor for last quarter.",
                    "analysis_summary": "Billing aggregate grouped by vendor.",
                    "required_data": [
                        self._required_data(
                            "Bills",
                            ["BillId", "VendorId", "BillDate", "TotalAmount"],
                            "Bill totals and dates are required.",
                        ),
                        self._required_data(
                            "Vendors",
                            ["VendorId", "VendorName"],
                            "Vendor name is needed for grouping.",
                        ),
                    ],
                    "query_strategy": "Group billing totals by vendor for last quarter.",
                    "sql_query": (
                        "SELECT Vendors.VendorName, SUM(Bills.UnknownAmount) AS TotalBilled "
                        "FROM Bills "
                        "INNER JOIN Vendors ON Bills.VendorId = Vendors.VendorId "
                        "GROUP BY Vendors.VendorName"
                    ),
                    "query_plan": None,
                },
                TokenUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
            )
        return super().generate_structured_json(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        )


class RepairingSQLAgentLLMClient(FakeLLMClient):
    def __init__(self) -> None:
        self.billing_calls = 0

    def generate_structured_json(
        self, *, system_prompt: str, user_prompt: str
    ) -> tuple[dict | None, TokenUsage]:
        if "assets query-maker agent" in system_prompt.lower():
            self.billing_calls += 1
            if self.billing_calls == 1:
                return (
                    {
                        "agent_name": "assets",
                        "action": "execute",
                        "user_need": "How many assets were purchased this year?",
                        "analysis_summary": "Attempting to count purchases this year.",
                        "required_data": [
                            self._required_data(
                                "Assets",
                                ["AssetId", "PurchaseDate"],
                                "Need purchase date to filter by year.",
                            ),
                        ],
                        "query_strategy": "Count assets for the year.",
                        "sql_query": (
                            "SELECT COUNT(*) AS AssetCount "
                            "FROM Assets "
                            "WHERE PurchaseDate BETWEEN '2026-01-01' AND '2026-12-31';"
                        ),
                        "query_plan": None,
                    },
                    TokenUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
                )
            return (
                {
                    "agent_name": "assets",
                    "action": "execute",
                    "user_need": "How many assets were purchased this year?",
                    "analysis_summary": "Repair the failed query with fully-qualified column names.",
                    "required_data": [
                        self._required_data(
                            "Assets",
                            ["AssetId", "PurchaseDate"],
                            "Need purchase date to filter by year.",
                        ),
                    ],
                    "query_strategy": "Count assets for the year using qualified columns.",
                    "sql_query": (
                        "SELECT COUNT(*) AS AssetCount "
                        "FROM Assets "
                        "WHERE Assets.PurchaseDate BETWEEN '2026-01-01' AND '2026-12-31';"
                    ),
                    "query_plan": None,
                },
                TokenUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
            )
        return super().generate_structured_json(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        )


class SQLAgentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repository = InMemoryRepository()
        self.execution_service = SQLExecutionService(seed_data=self.repository._data)

    def test_context_includes_domain_schema_and_capabilities(self) -> None:
        context = build_sql_agent_context(
            agent_name="sales",
            today=FIXED_TODAY,
            customer_names=["Acme Corp", "Bright Retail"],
        )
        self.assertIn('"role"', context)
        self.assertIn('"capabilities"', context)
        self.assertIn('"Customers"', context)
        self.assertIn('"description": "Display name of the customer."', context)
        self.assertIn('"value_hints": [', context)

    def test_prompt_can_include_iteration_feedback(self) -> None:
        context = build_sql_agent_context(
            agent_name="sales",
            today=FIXED_TODAY,
            customer_names=["Acme Corp", "Bright Retail"],
        )
        prompt = build_sql_agent_user_prompt(
            agent_name="sales",
            user_message="show me the first 5 rows of customers table",
            schema_context=context,
            session_history="No prior conversation.",
            orchestrator_handoff="Retrieve and display the first 5 customer rows.",
            activation_context={"required_tables": ["Customers"]},
            iteration_index=2,
            max_iterations=3,
            prior_attempts=["Attempt 1: action=execute. Review feedback: add explicit selects."],
        )
        self.assertIn("Iteration: 2 of 3", prompt)
        self.assertIn("Previous SQL-agent attempts and review feedback", prompt)
        self.assertIn("required_tables", prompt)

    def test_sql_agent_wraps_query_plan_response_into_execute_decision(self) -> None:
        agent = LLMSQLAgent(
            llm_client=FakeLLMClient(),
            today=FIXED_TODAY,
            customer_names=["Acme Corp", "Bright Retail", "Northwind LLC"],
            execution_service=self.execution_service,
        )
        decision = agent.decide(
            "Show total invoice amount by vendor for last quarter",
            SessionState(session_id="sql-agent"),
            PlannerActivation(
                agent_name="billing",
                handoff_summary="Build a billing aggregate grouped by vendor for last quarter.",
                context={
                    "orchestrator": {
                        "required_data": [
                            {
                                "table": "Bills",
                                "columns": ["BillId", "VendorId", "BillDate", "TotalAmount"],
                                "reason": "Billing facts are needed for the aggregate.",
                            },
                            {
                                "table": "Vendors",
                                "columns": ["VendorId", "VendorName"],
                                "reason": "Vendor names are needed for grouping.",
                            },
                        ]
                    }
                },
            ),
        )
        self.assertIsNotNone(decision)
        self.assertEqual(decision.action, "execute")
        self.assertIsNotNone(decision.query_plan)
        self.assertIn("FROM Bills", decision.sql_query or "")
        self.assertEqual(decision.query_plan.base_table, "Bills")

    def test_sql_agent_retries_weak_first_attempt(self) -> None:
        agent = LLMSQLAgent(
            llm_client=LoopingSQLAgentLLMClient(),
            today=FIXED_TODAY,
            customer_names=["Acme Corp", "Bright Retail", "Northwind LLC"],
            execution_service=self.execution_service,
            max_iterations=3,
        )
        decision = agent.decide(
            "show me the first 5 rows of customers table",
            SessionState(session_id="sql-agent-loop"),
            PlannerActivation(
                agent_name="sales",
                handoff_summary="Retrieve the first 5 rows of the Customers table.",
                context={
                    "orchestrator": {
                        "required_data": [
                            {
                                "table": "Customers",
                                "columns": ["CustomerId", "CustomerName"],
                                "reason": "Customer rows are required.",
                            }
                        ]
                    }
                },
            ),
        )
        self.assertIsNotNone(decision)
        self.assertEqual(decision.action, "execute")
        self.assertIn("SELECT TOP 5", decision.sql_query or "")
        self.assertEqual(decision.query_plan.base_table, "Customers")
        self.assertEqual(decision.query_plan.limit, 5)

    def test_sql_agent_returns_terminal_clarify_when_all_attempts_are_invalid(self) -> None:
        agent = LLMSQLAgent(
            llm_client=InvalidSQLAgentLLMClient(),
            today=FIXED_TODAY,
            customer_names=["Acme Corp", "Bright Retail", "Northwind LLC"],
            execution_service=self.execution_service,
            max_iterations=2,
        )
        decision = agent.decide(
            "Show total invoice amount by vendor for last quarter",
            SessionState(session_id="sql-agent-invalid"),
            PlannerActivation(
                agent_name="billing",
                handoff_summary="Build a billing aggregate grouped by vendor for last quarter.",
                context={},
            ),
        )
        self.assertIsNotNone(decision)
        self.assertEqual(decision.action, "clarify")
        self.assertIn(
            "could not finalize a valid sql plan",
            (decision.clarification_question or "").lower(),
        )
        debug_trace = agent.get_last_debug_trace()
        self.assertIsNotNone(debug_trace)
        attempts = debug_trace["attempts"]
        self.assertEqual(len(attempts), 2)
        self.assertEqual(attempts[0]["parse_mode"], "sql_agent_decision_invalid")
        self.assertIn("validation_error", attempts[0])
        self.assertEqual(attempts[0]["query_plan_validation_error"][0]["location"], ["base_table"])

    def test_sql_agent_downgrades_execute_without_query_plan_when_review_fails(self) -> None:
        agent = LLMSQLAgent(
            llm_client=ReviewRejectedSQLAgentLLMClient(),
            today=FIXED_TODAY,
            customer_names=["Acme Corp", "Bright Retail", "Northwind LLC"],
            execution_service=self.execution_service,
            max_iterations=1,
        )
        decision = agent.decide(
            "Show total invoice amount by vendor for last quarter",
            SessionState(session_id="sql-agent-review-rejected"),
            PlannerActivation(
                agent_name="billing",
                handoff_summary="Build a billing aggregate grouped by vendor for last quarter.",
                context={
                    "orchestrator": {
                        "required_data": [
                            {
                                "table": "Bills",
                                "columns": ["BillId", "VendorId", "BillDate", "TotalAmount"],
                                "reason": "Billing facts are needed for the aggregate.",
                            },
                            {
                                "table": "Vendors",
                                "columns": ["VendorId", "VendorName"],
                                "reason": "Vendor names are needed for grouping.",
                            },
                        ]
                    }
                },
            ),
        )
        self.assertIsNotNone(decision)
        self.assertEqual(decision.action, "clarify")
        self.assertIsNone(decision.query_plan)
        self.assertIn(
            "could not finalize an executable query plan",
            (decision.clarification_question or "").lower(),
        )

    def test_sql_agent_uses_repair_loop_after_review_failure(self) -> None:
        agent = LLMSQLAgent(
            llm_client=RepairingSQLAgentLLMClient(),
            today=FIXED_TODAY,
            customer_names=["Acme Corp", "Bright Retail", "Northwind LLC"],
            execution_service=self.execution_service,
            max_iterations=1,
            repair_iterations=2,
        )
        decision = agent.decide(
            "How many assets were purchased this year?",
            SessionState(session_id="sql-agent-repair"),
            PlannerActivation(
                agent_name="assets",
                handoff_summary="Count purchased assets this year.",
                context={},
            ),
        )
        self.assertIsNotNone(decision)
        self.assertEqual(decision.action, "execute")
        self.assertIsNotNone(decision.query_plan)
        self.assertIn("Assets.PurchaseDate", decision.sql_query or "")
        self.assertEqual(decision.query_plan.base_table, "Assets")
        debug_trace = agent.get_last_debug_trace()
        self.assertIsNotNone(debug_trace)
        if "repair_attempts" in debug_trace:
            self.assertGreaterEqual(len(debug_trace["repair_attempts"]), 1)


if __name__ == "__main__":
    unittest.main()
