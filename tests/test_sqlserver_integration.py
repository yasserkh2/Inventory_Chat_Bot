from __future__ import annotations

import os
import unittest

from inventory_chatbot.api.server import build_router_service
from inventory_chatbot.config import AppConfig
from inventory_chatbot.models.api import ChatRequest
from inventory_chatbot.runtime.backend_factory import build_data_backend_runtime
from inventory_chatbot.sql_backend.db_init import initialize_database
from inventory_chatbot.sql_execution.models import SQLExecutionRequest
from inventory_chatbot.sql_review.models import SQLReviewRequest
from inventory_chatbot.sql_review.service import SQLReviewService
from tests.helpers import FakeLLMClient


def _bool_env(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@unittest.skipUnless(
    os.getenv("RUN_SQLSERVER_INTEGRATION") == "1",
    "Set RUN_SQLSERVER_INTEGRATION=1 to run SQL Server integration tests.",
)
class SQLServerIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.config = AppConfig(
            data_backend="sqlserver",
            provider="openai",
            openai_api_key="test-key",
            sqlserver_host=os.getenv("SQLSERVER_HOST", "127.0.0.1"),
            sqlserver_port=int(os.getenv("SQLSERVER_PORT", "1433")),
            sqlserver_database=os.getenv("SQLSERVER_DATABASE", "InventoryChatbot"),
            sqlserver_user=os.getenv("SQLSERVER_USER", "sa"),
            sqlserver_password=os.getenv("SQLSERVER_PASSWORD", "YourStrong!Passw0rd"),
            sqlserver_driver=os.getenv("SQLSERVER_DRIVER", "ODBC Driver 18 for SQL Server"),
            sqlserver_encrypt=_bool_env("SQLSERVER_ENCRYPT", False),
            sqlserver_trust_server_certificate=_bool_env(
                "SQLSERVER_TRUST_SERVER_CERTIFICATE", True
            ),
            sqlserver_connection_timeout_seconds=int(
                os.getenv("SQLSERVER_CONNECTION_TIMEOUT_SECONDS", "10")
            ),
        )
        cls.config.validate_sql_backend_configuration()
        initialize_database(cls.config)

    def test_distinct_currency_query_executes_against_sqlserver(self) -> None:
        runtime = build_data_backend_runtime(self.config)
        review_service = SQLReviewService()
        review_result = review_service.review(
            SQLReviewRequest(
                user_message="Tell me the currencies we have in the data",
                sql_query=(
                    "SELECT TOP 10 DISTINCT Bills.Currency "
                    "FROM Bills "
                    "ORDER BY Bills.Currency ASC;"
                ),
                source_agent="billing",
                allowed_tables=["Bills", "Vendors"],
            )
        )
        self.assertTrue(review_result.approved)
        self.assertIsNotNone(review_result.normalized_query_plan)

        execution_request = SQLExecutionRequest(
            user_message="Tell me the currencies we have in the data",
            query_plan=review_result.normalized_query_plan,
            sql_query=review_result.reviewed_sql,
            source_agent="billing",
            allowed_tables=["Bills", "Vendors"],
        )
        result, sql_query = runtime.sql_execution_service.execute(execution_request)

        self.assertIn("FROM Bills", sql_query)
        self.assertGreaterEqual(result.answer_context["row_count"], 1)
        currencies = {row["Bills.Currency"] for row in result.answer_context["rows"]}
        self.assertIn("USD", currencies)

    def test_row_preview_request_succeeds_through_router(self) -> None:
        router = build_router_service(
            config=self.config,
            llm_client=FakeLLMClient(),
        )
        response = router.handle_chat(
            ChatRequest(
                session_id="sqlserver-integration",
                message="show me the first 5 rows of customers table",
                context={},
            )
        )

        self.assertEqual(response.status, "ok")
        self.assertIn("FROM Customers", response.sql_query)
        self.assertIsNotNone(response.result_preview)
        self.assertEqual(response.result_preview["row_count"], 5)

    def test_startup_fails_clearly_when_database_is_unreachable(self) -> None:
        bad_config = self.config.model_copy(
            update={
                "sqlserver_port": self.config.sqlserver_port + 97,
                "sqlserver_connection_timeout_seconds": 1,
            }
        )
        with self.assertRaises(RuntimeError) as context:
            build_data_backend_runtime(bad_config)
        self.assertIn("health check failed", str(context.exception).lower())


if __name__ == "__main__":
    unittest.main()
