from __future__ import annotations

import unittest
from unittest.mock import patch

from inventory_chatbot.config import AppConfig
from inventory_chatbot.pipeline_trace_cli import _print_trace, main as pipeline_trace_main
from inventory_chatbot.models.api import TokenUsage
from inventory_chatbot.models.domain import SessionState
from inventory_chatbot.orchestrator.llm_based import LLMOrchestrator
from inventory_chatbot.orchestrator.prompts import (
    build_orchestrator_context,
    build_orchestrator_user_prompt,
)
from tests.helpers import (
    FIXED_TODAY,
    FakeLLMClient,
    LoopingOrchestratorLLMClient,
    StructuredFailingLLMClient,
)


class OrchestratorTranslationLLMClient(FakeLLMClient):
    def generate_structured_json(
        self, *, system_prompt: str, user_prompt: str
    ) -> tuple[dict | None, TokenUsage]:
        if "orchestrator agent" not in system_prompt.lower():
            return super().generate_structured_json(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
            )
        question = self._extract_user_question(user_prompt).lower().strip()
        if "currency" in question:
            return (
                self._decision(
                    agent="billing",
                    user_need="Find the currencies in billing data.",
                    analysis_summary="This belongs to billing.",
                    required_data=[
                        self._required_data(
                            "Bills",
                            ["BillId", "BillDate"],
                            "Bills contains the billing facts.",
                        )
                    ],
                    handoff_instructions="Return the requested billing answer.",
                ),
                TokenUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
            )
        if question == "show me data":
            return (
                self._decision(
                    agent="assets",
                    user_need="Show data.",
                    analysis_summary="Could be assets.",
                    required_data=[
                        self._required_data(
                            "Assets",
                            ["AssetId"],
                            "Asset rows are available.",
                        )
                    ],
                    handoff_instructions="Try to show rows.",
                ),
                TokenUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
            )
        return super().generate_structured_json(system_prompt=system_prompt, user_prompt=user_prompt)


class OrchestratorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.orchestrator = LLMOrchestrator(
            llm_client=FakeLLMClient(),
            today=FIXED_TODAY,
            customer_names=["Acme Corp", "Bright Retail", "Northwind LLC"],
        )

    def test_context_includes_agent_roles_and_schema_descriptions(self) -> None:
        context = build_orchestrator_context(
            today=FIXED_TODAY,
            customer_names=["Acme Corp", "Bright Retail", "Northwind LLC"],
        )
        self.assertIn('"agents"', context)
        self.assertIn('"assets"', context)
        self.assertIn('"role"', context)
        self.assertIn('"schema"', context)
        self.assertIn('"Customers"', context)
        self.assertIn('"description": "Master data for customers who place sales orders."', context)
        self.assertIn('"CustomerName"', context)
        self.assertIn('"description": "Display name of the customer."', context)
        self.assertIn('"value_hints": [', context)

    def test_orchestrator_returns_structured_decision(self) -> None:
        decision = self.orchestrator.decide(
            "How many assets by site?",
            SessionState(session_id="orchestrator"),
        )
        self.assertIsNotNone(decision)
        self.assertEqual(decision.agent, "assets")
        self.assertGreaterEqual(len(decision.required_data), 1)
        self.assertTrue(decision.handoff_instructions)

    def test_orchestrator_prompt_can_include_iteration_feedback(self) -> None:
        context = build_orchestrator_context(
            today=FIXED_TODAY,
            customer_names=["Acme Corp", "Bright Retail", "Northwind LLC"],
        )
        prompt = build_orchestrator_user_prompt(
            user_message="How many assets by site?",
            schema_context=context,
            session_history="No prior conversation.",
            iteration_index=2,
            max_iterations=3,
            prior_attempts=[
                "Attempt 1: agent=chat, user_need=[missing]. Review feedback: This looks like a data request."
            ],
        )
        self.assertIn("Iteration: 2 of 3", prompt)
        self.assertIn("Previous orchestration attempts and review feedback", prompt)
        self.assertIn("Attempt 1: agent=chat", prompt)

    def test_orchestrator_retries_when_first_decision_is_weak(self) -> None:
        looping_client = LoopingOrchestratorLLMClient()
        orchestrator = LLMOrchestrator(
            llm_client=looping_client,
            today=FIXED_TODAY,
            customer_names=["Acme Corp", "Bright Retail", "Northwind LLC"],
            max_iterations=3,
        )
        decision = orchestrator.decide(
            "How many assets by site?",
            SessionState(session_id="looping"),
        )
        self.assertIsNotNone(decision)
        self.assertEqual(looping_client.orchestrator_calls, 2)
        self.assertEqual(decision.agent, "assets")
        self.assertEqual(decision.required_data[0].table, "Assets")

    def test_orchestrator_records_provider_error_in_debug_trace(self) -> None:
        orchestrator = LLMOrchestrator(
            llm_client=StructuredFailingLLMClient(),
            today=FIXED_TODAY,
            customer_names=["Acme Corp", "Bright Retail", "Northwind LLC"],
        )
        decision = orchestrator.decide(
            "How many assets by site?",
            SessionState(session_id="provider-error"),
        )
        self.assertIsNone(decision)
        self.assertEqual(orchestrator.get_last_debug_trace()["status"], "provider_error")
        self.assertEqual(orchestrator.get_last_debug_trace()["error"], "structured boom")

    @patch("inventory_chatbot.pipeline_trace_cli.build_llm_client")
    @patch("inventory_chatbot.pipeline_trace_cli.AppConfig.from_env")
    def test_pipeline_trace_includes_orchestrator_debug_details(
        self,
        mock_from_env,
        mock_build_llm_client,
    ) -> None:
        mock_from_env.return_value = AppConfig(
            provider="openai",
            openai_api_key="test-key",
            model_name="test-model",
        )
        mock_build_llm_client.return_value = StructuredFailingLLMClient()

        with patch(
            "sys.argv",
            [
                "pipeline_trace_cli",
                "Show total invoice amount by vendor for last quarter",
                "--pretty",
            ],
        ), patch("sys.stdout.write") as stdout_write:
            exit_code = pipeline_trace_main()

        rendered = "".join(call.args[0] for call in stdout_write.call_args_list)
        self.assertEqual(exit_code, 2)
        self.assertIn('"path": "orchestrator_failed"', rendered)
        self.assertIn('"orchestrator_debug"', rendered)
        self.assertIn('"status": "provider_error"', rendered)
        self.assertIn('"error": "structured boom"', rendered)

    @patch(
        "inventory_chatbot.pipeline_trace_cli.OrchestratorHandoffService.build_execution_request",
        side_effect=ValueError("SQL agent decision must include query_plan for execution."),
    )
    @patch("inventory_chatbot.pipeline_trace_cli.build_llm_client")
    @patch("inventory_chatbot.pipeline_trace_cli.AppConfig.from_env")
    def test_pipeline_trace_handles_handoff_build_errors(
        self,
        mock_from_env,
        mock_build_llm_client,
        _mock_build_execution_request,
    ) -> None:
        mock_from_env.return_value = AppConfig(
            provider="openai",
            openai_api_key="test-key",
            model_name="test-model",
        )
        mock_build_llm_client.return_value = FakeLLMClient()

        with patch(
            "sys.argv",
            [
                "pipeline_trace_cli",
                "Show total invoice amount by vendor for last quarter",
                "--pretty",
            ],
        ), patch("sys.stdout.write") as stdout_write:
            exit_code = pipeline_trace_main()

        rendered = "".join(call.args[0] for call in stdout_write.call_args_list)
        self.assertEqual(exit_code, 6)
        self.assertIn('"path": "handoff_failed"', rendered)
        self.assertIn('"handoff_error"', rendered)
        self.assertIn("query_plan", rendered)

    def test_print_trace_serializes_date_values(self) -> None:
        trace = {
            "message": "show the first 5 rows of any table",
            "steps": {
                "sql_output": {
                    "result_preview": {
                        "rows": [
                            {"BillDate": FIXED_TODAY}
                        ]
                    }
                }
            },
        }
        with patch("sys.stdout.write") as stdout_write:
            exit_code = _print_trace(
                trace,
                True,
                0,
            )
        rendered = "".join(call.args[0] for call in stdout_write.call_args_list)
        self.assertEqual(exit_code, 0)
        self.assertIn('"BillDate": "2026-04-07"', rendered)

    def test_orchestrator_translates_currency_to_bills_currency_handoff(self) -> None:
        orchestrator = LLMOrchestrator(
            llm_client=OrchestratorTranslationLLMClient(),
            today=FIXED_TODAY,
            customer_names=["Acme Corp", "Bright Retail", "Northwind LLC"],
            max_iterations=1,
        )
        decision = orchestrator.decide(
            "what currency do we have",
            SessionState(session_id="currency-translation"),
        )
        self.assertIsNotNone(decision)
        self.assertEqual(decision.agent, "billing")
        self.assertTrue(
            any(item.table == "Bills" and "Currency" in item.columns for item in decision.required_data)
        )
        self.assertIn("Bills.Currency", decision.handoff_instructions)
        self.assertIn("not a Currency table", decision.handoff_instructions)

    def test_orchestrator_marks_vague_data_request_for_clarification(self) -> None:
        orchestrator = LLMOrchestrator(
            llm_client=OrchestratorTranslationLLMClient(),
            today=FIXED_TODAY,
            customer_names=["Acme Corp", "Bright Retail", "Northwind LLC"],
            max_iterations=1,
        )
        decision = orchestrator.decide(
            "show me data",
            SessionState(session_id="vague-request"),
        )
        self.assertIsNotNone(decision)
        self.assertTrue(decision.clarification_needed)
        self.assertIn("date range", (decision.clarification_question or "").lower())


if __name__ == "__main__":
    unittest.main()
