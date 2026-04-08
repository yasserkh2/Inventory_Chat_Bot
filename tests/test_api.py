from __future__ import annotations

import json
import unittest

from inventory_chatbot.api.server import (
    build_router_service,
    handle_chat_payload,
    health_payload,
    history_payload,
)
from inventory_chatbot.config import AppConfig
from tests.helpers import FIXED_TODAY, FakeLLMClient, FailingLLMClient


class ApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = AppConfig(provider="azure", model_name="test-model")

    def _build_router(self, llm_client):
        return build_router_service(
            config=self.config,
            llm_client=llm_client,
            today_provider=lambda: FIXED_TODAY,
        )

    def test_health_endpoint(self) -> None:
        status, payload = health_payload(self.config)
        self.assertEqual(int(status), 200)
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["provider"], "azure")

    def test_chat_api_happy_path(self) -> None:
        router = self._build_router(FakeLLMClient())
        status, payload = handle_chat_payload(
            payload=json.dumps(
                {"session_id": "demo", "message": "How many assets do I have?", "context": {}}
            ).encode("utf-8"),
            router_service=router,
            config=self.config,
        )
        self.assertEqual(int(status), 200)
        self.assertEqual(payload["status"], "ok")
        self.assertIn("SELECT COUNT(*)", payload["sql_query"])

    def test_chat_api_provider_error(self) -> None:
        router = self._build_router(FailingLLMClient())
        status, payload = handle_chat_payload(
            payload=json.dumps(
                {"session_id": "demo", "message": "How many assets do I have?", "context": {}}
            ).encode("utf-8"),
            router_service=router,
            config=self.config,
        )
        self.assertEqual(int(status), 200)
        self.assertEqual(payload["status"], "error")
        self.assertIn("Unable to contact", payload["natural_language_answer"])

    def test_chat_api_validation_error(self) -> None:
        router = self._build_router(FakeLLMClient())
        status, payload = handle_chat_payload(
            payload=b'{"session_id": "demo", "message": "   "}',
            router_service=router,
            config=self.config,
        )
        self.assertEqual(int(status), 400)
        self.assertEqual(payload["status"], "error")
        self.assertIn("validation failed", payload["natural_language_answer"].lower())

    def test_chat_api_dynamic_sql_happy_path(self) -> None:
        router = self._build_router(FakeLLMClient())
        status, payload = handle_chat_payload(
            payload=json.dumps(
                {
                    "session_id": "dynamic-demo",
                    "message": "How many open purchase orders are there?",
                    "context": {
                        "query_plan": {
                            "base_table": "PurchaseOrders",
                            "aggregates": [
                                {
                                    "function": "COUNT",
                                    "column": "PurchaseOrders.POId",
                                    "alias": "OpenPurchaseOrderCount",
                                }
                            ],
                            "filters": [
                                {
                                    "column": "PurchaseOrders.Status",
                                    "operator": "=",
                                    "value": "Open",
                                }
                            ],
                        }
                    },
                }
            ).encode("utf-8"),
            router_service=router,
            config=self.config,
        )
        self.assertEqual(int(status), 200)
        self.assertEqual(payload["status"], "ok")
        self.assertIn("FROM PurchaseOrders", payload["sql_query"])
        self.assertIn("OpenPurchaseOrderCount: 2", payload["natural_language_answer"])
        self.assertEqual(payload["result_preview"]["row_count"], 1)

    def test_chat_api_auto_query_maker_happy_path(self) -> None:
        router = self._build_router(FakeLLMClient())
        status, payload = handle_chat_payload(
            payload=json.dumps(
                {
                    "session_id": "dynamic-auto",
                    "message": "Show total invoice amount by vendor for last quarter",
                    "context": {},
                }
            ).encode("utf-8"),
            router_service=router,
            config=self.config,
        )
        self.assertEqual(int(status), 200)
        self.assertEqual(payload["status"], "ok")
        self.assertIn("JOIN Vendors ON Bills.VendorId = Vendors.VendorId", payload["sql_query"])
        self.assertIn("VendorName", payload["natural_language_answer"])

    def test_chat_api_customer_row_preview_returns_structured_rows(self) -> None:
        router = self._build_router(FakeLLMClient())
        status, payload = handle_chat_payload(
            payload=json.dumps(
                {
                    "session_id": "customer-preview",
                    "message": "list me the first 5 rows in customers table",
                    "context": {},
                }
            ).encode("utf-8"),
            router_service=router,
            config=self.config,
        )
        self.assertEqual(int(status), 200)
        self.assertEqual(payload["status"], "ok")
        self.assertIn("FROM Customers", payload["sql_query"])
        self.assertEqual(payload["result_preview"]["row_count"], 5)
        self.assertEqual(payload["result_preview"]["rows"][0]["CustomerName"], "Acme Corp")

    def test_history_payload_returns_session_turns(self) -> None:
        router = self._build_router(FakeLLMClient())
        handle_chat_payload(
            payload=json.dumps(
                {"session_id": "history-demo", "message": "How many assets do I have?", "context": {}}
            ).encode("utf-8"),
            router_service=router,
            config=self.config,
        )

        status, payload = history_payload(
            session_id="history-demo",
            session_store=router._session_store,
        )

        self.assertEqual(int(status), 200)
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(len(payload["turns"]), 1)
        self.assertEqual(payload["turns"][0]["user_message"], "How many assets do I have?")

    def test_chat_api_schema_tables_question(self) -> None:
        router = self._build_router(FakeLLMClient())
        status, payload = handle_chat_payload(
            payload=json.dumps(
                {"session_id": "schema-demo", "message": "what are the tables do we have", "context": {}}
            ).encode("utf-8"),
            router_service=router,
            config=self.config,
        )
        self.assertEqual(int(status), 200)
        self.assertEqual(payload["status"], "ok")
        self.assertIn("Customers", payload["natural_language_answer"])
        self.assertEqual(payload["sql_query"], "")


if __name__ == "__main__":
    unittest.main()
