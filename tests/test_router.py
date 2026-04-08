from __future__ import annotations

import unittest

from inventory_chatbot.config import AppConfig
from inventory_chatbot.data.memory_repository import InMemoryRepository
from inventory_chatbot.dynamic_sql.service import DynamicSQLService
from inventory_chatbot.models.api import ChatRequest
from inventory_chatbot.orchestrator.llm_based import LLMOrchestrator
from inventory_chatbot.query_makers.llm_based import LLMQueryMaker
from inventory_chatbot.router.service import RouterService
from inventory_chatbot.router.registry import SpecialistRegistry
from inventory_chatbot.services.date_parser import DateParser
from inventory_chatbot.services.session_store import SessionStore
from inventory_chatbot.specialists.assets import AssetSpecialist
from inventory_chatbot.specialists.billing import BillingSpecialist
from inventory_chatbot.specialists.procurement import ProcurementSpecialist
from inventory_chatbot.specialists.sales import SalesSpecialist
from tests.helpers import FIXED_TODAY, FakeLLMClient, FailingLLMClient


class RouterTests(unittest.TestCase):
    def setUp(self) -> None:
        repository = InMemoryRepository()
        date_parser = DateParser(today_provider=lambda: FIXED_TODAY)
        registry = SpecialistRegistry(
            [
                AssetSpecialist(repository, date_parser),
                BillingSpecialist(repository, date_parser),
                ProcurementSpecialist(repository),
                SalesSpecialist(repository, date_parser),
            ]
        )
        config = AppConfig(provider="azure", model_name="test-model")
        self.session_store = SessionStore()
        self.router = RouterService(
            config=config,
            registry=registry,
            session_store=self.session_store,
            llm_client=FakeLLMClient(),
            dynamic_sql_service=DynamicSQLService(seed_data=repository._data),
            orchestrator=LLMOrchestrator(
                llm_client=FakeLLMClient(),
                today=FIXED_TODAY,
                customer_names=[customer["customer_name"] for customer in repository.list_customers()],
            ),
            query_maker=LLMQueryMaker(
                llm_client=FakeLLMClient(),
                today=FIXED_TODAY,
                customer_names=[customer["customer_name"] for customer in repository.list_customers()],
            ),
        )
        self.error_router = RouterService(
            config=config,
            registry=registry,
            session_store=SessionStore(),
            llm_client=FailingLLMClient(),
            dynamic_sql_service=DynamicSQLService(seed_data=repository._data),
            orchestrator=LLMOrchestrator(
                llm_client=FailingLLMClient(),
                today=FIXED_TODAY,
                customer_names=[customer["customer_name"] for customer in repository.list_customers()],
            ),
            query_maker=LLMQueryMaker(
                llm_client=FailingLLMClient(),
                today=FIXED_TODAY,
                customer_names=[customer["customer_name"] for customer in repository.list_customers()],
            ),
        )

    def test_asset_follow_up_by_site(self) -> None:
        first_response = self.router.handle_chat(
            ChatRequest(session_id="demo", message="How many assets do I have?", context={})
        )
        self.assertEqual(first_response.status, "ok")

        follow_up = self.router.handle_chat(
            ChatRequest(session_id="demo", message="What about by site?", context={})
        )
        self.assertEqual(follow_up.status, "ok")
        self.assertIn("SiteName", follow_up.sql_query)

    def test_billing_question_is_handled_by_llm_query_flow(self) -> None:
        response = self.router.handle_chat(
            ChatRequest(session_id="billing", message="What is the total billed amount?", context={})
        )
        self.assertEqual(response.status, "ok")
        self.assertIn("SUM(Bills.TotalAmount)", response.sql_query)

    def test_sales_named_customer_carryover(self) -> None:
        first_response = self.router.handle_chat(
            ChatRequest(
                session_id="sales",
                message="How many sales orders were created for Acme Corp last month?",
                context={},
            )
        )
        self.assertEqual(first_response.status, "ok")

        follow_up = self.router.handle_chat(
            ChatRequest(session_id="sales", message="What about Bright Retail?", context={})
        )
        self.assertEqual(follow_up.status, "ok")
        self.assertIn("Bright Retail", follow_up.sql_query)

    def test_provider_error_returns_controlled_response(self) -> None:
        response = self.error_router.handle_chat(
            ChatRequest(session_id="err", message="How many assets do I have?", context={})
        )
        self.assertEqual(response.status, "error")
        self.assertIn("Unable to contact", response.natural_language_answer)
        self.assertIn("SELECT COUNT(*)", response.sql_query)

    def test_dynamic_sql_query_plan_is_executed(self) -> None:
        response = self.router.handle_chat(
            ChatRequest(
                session_id="dynamic",
                message="How many active assets by site?",
                context={
                    "query_plan": {
                        "base_table": "Assets",
                        "selects": [{"column": "Sites.SiteName", "alias": "SiteName"}],
                        "aggregates": [
                            {
                                "function": "COUNT",
                                "column": "Assets.AssetId",
                                "alias": "AssetCount",
                            }
                        ],
                        "joins": [{"left": "Assets.SiteId", "right": "Sites.SiteId"}],
                        "filters": [
                            {
                                "column": "Assets.Status",
                                "operator": "<>",
                                "value": "Disposed",
                            }
                        ],
                        "group_by": ["Sites.SiteName"],
                        "order_by": [{"expression": "AssetCount", "direction": "DESC"}],
                    }
                },
            )
        )
        self.assertEqual(response.status, "ok")
        self.assertIn("JOIN Sites ON Assets.SiteId = Sites.SiteId", response.sql_query)
        self.assertIn("SiteName: Cairo Main Warehouse", response.natural_language_answer)

    def test_llm_query_maker_handles_dynamic_question(self) -> None:
        response = self.router.handle_chat(
            ChatRequest(
                session_id="dynamic-auto",
                message="Show total invoice amount by vendor for last quarter",
                context={},
            )
        )
        self.assertEqual(response.status, "ok")
        self.assertIn("JOIN Vendors ON Bills.VendorId = Vendors.VendorId", response.sql_query)
        self.assertIn("VendorName", response.natural_language_answer)

    def test_router_handles_sql_handoff_build_error_without_crashing(self) -> None:
        def _raise_handoff_error(**_kwargs):
            raise ValueError("SQL agent decision must include query_plan for execution.")

        self.router._handoff_service.build_execution_request = _raise_handoff_error
        response = self.router.handle_chat(
            ChatRequest(
                session_id="dynamic-auto-handoff-error",
                message="Show total invoice amount by vendor for last quarter",
                context={},
            )
        )
        self.assertEqual(response.status, "error")
        self.assertIn("query_plan", response.natural_language_answer)

    def test_orchestrator_delegates_customer_row_request_to_dynamic_sql_agent(self) -> None:
        response = self.router.handle_chat(
            ChatRequest(
                session_id="customers-preview",
                message="show me the first 5 rows of customers table",
                context={},
            )
        )
        self.assertEqual(response.status, "ok")
        self.assertIn("FROM Customers", response.sql_query)
        self.assertIn("ORDER BY Customers.CustomerId ASC", response.sql_query)
        self.assertIn("CustomerId", response.natural_language_answer)
        self.assertEqual(response.result_preview["row_count"], 5)
        self.assertEqual(response.result_preview["rows"][0]["CustomerName"], "Acme Corp")

    def test_customer_row_request_uses_deterministic_preview_without_query_maker(self) -> None:
        repository = InMemoryRepository()
        date_parser = DateParser(today_provider=lambda: FIXED_TODAY)
        registry = SpecialistRegistry(
            [
                AssetSpecialist(repository, date_parser),
                BillingSpecialist(repository, date_parser),
                ProcurementSpecialist(repository),
                SalesSpecialist(repository, date_parser),
            ]
        )
        config = AppConfig(provider="azure", model_name="test-model")
        router = RouterService(
            config=config,
            registry=registry,
            session_store=SessionStore(),
            llm_client=FakeLLMClient(),
            dynamic_sql_service=DynamicSQLService(seed_data=repository._data),
            query_maker=None,
        )

        response = router.handle_chat(
            ChatRequest(
                session_id="customers-preview-no-llm",
                message="list me the first 5 rows in customers table",
                context={},
            )
        )
        self.assertEqual(response.status, "ok")
        self.assertIn("FROM Customers", response.sql_query)
        self.assertEqual(response.result_preview["row_count"], 5)

    def test_give_first_five_rows_in_customers_table_uses_preview_path(self) -> None:
        response = self.router.handle_chat(
            ChatRequest(
                session_id="customers-preview-give",
                message="give first 5 rows in customers table",
                context={},
            )
        )
        self.assertEqual(response.status, "ok")
        self.assertEqual(response.sql_query.startswith("SELECT TOP 5"), True)
        self.assertEqual(response.result_preview["row_count"], 5)

    def test_schema_chat_handles_table_discovery(self) -> None:
        response = self.router.handle_chat(
            ChatRequest(
                session_id="schema",
                message="what are the tables do we have?",
                context={},
            )
        )
        self.assertEqual(response.status, "ok")
        self.assertIn("Customers", response.natural_language_answer)
        self.assertIn("AssetTransactions", response.natural_language_answer)
        self.assertEqual(response.sql_query, "")


if __name__ == "__main__":
    unittest.main()
