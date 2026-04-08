from __future__ import annotations

import unittest
from unittest.mock import patch

from inventory_chatbot.config import AppConfig
from inventory_chatbot.data.memory_repository import InMemoryRepository
from inventory_chatbot.dynamic_sql.models import QueryPlan, SelectSpec
from inventory_chatbot.runtime.backend_factory import build_data_backend_runtime
from inventory_chatbot.sql_backend.bootstrap import SQLBackendComponents
from inventory_chatbot.sql_execution.models import SQLExecutionRequest


class _FakeQueryRunner:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def execute_sql(self, *, sql_query: str, query_plan: QueryPlan) -> list[dict]:
        self.calls.append({"sql_query": sql_query, "query_plan": query_plan})
        return [{"Assets.AssetId": 1}]


class RuntimeBackendFactoryTests(unittest.TestCase):
    def test_memory_backend_runtime_uses_dynamic_sql_service(self) -> None:
        config = AppConfig(
            data_backend="memory",
            provider="openai",
            openai_api_key="test-key",
        )
        repository = InMemoryRepository()

        runtime = build_data_backend_runtime(config, repository=repository)

        self.assertIs(runtime.repository, repository)
        self.assertIsNotNone(runtime.dynamic_sql_service)
        self.assertIsNotNone(runtime.sql_execution_service)

    def test_sqlserver_backend_runtime_uses_bootstrapped_components(self) -> None:
        config = AppConfig(
            data_backend="sqlserver",
            provider="openai",
            openai_api_key="test-key",
            sqlserver_host="127.0.0.1",
            sqlserver_database="InventoryChatbot",
            sqlserver_user="sa",
            sqlserver_password="password",
        )
        fake_repository = object()
        fake_runner = _FakeQueryRunner()
        with patch(
            "inventory_chatbot.sql_backend.bootstrap.build_sql_backend",
            return_value=SQLBackendComponents(
                repository=fake_repository,
                query_runner=fake_runner,
            ),
        ):
            runtime = build_data_backend_runtime(config)

        self.assertIs(runtime.repository, fake_repository)
        self.assertIsNone(runtime.dynamic_sql_service)
        request = SQLExecutionRequest(
            user_message="show one asset",
            query_plan=QueryPlan(
                base_table="Assets",
                selects=[SelectSpec(column="Assets.AssetId")],
                order_by=[],
                joins=[],
                filters=[],
                group_by=[],
                aggregates=[],
            ),
            sql_query="SELECT TOP 1 Assets.AssetId FROM Assets;",
            source_agent="assets",
            allowed_tables=["Assets"],
        )
        runtime.sql_execution_service.execute(request)
        self.assertEqual(len(fake_runner.calls), 1)

    def test_sqlserver_backend_runtime_rejects_custom_repository_injection(self) -> None:
        config = AppConfig(
            data_backend="sqlserver",
            provider="openai",
            openai_api_key="test-key",
            sqlserver_host="127.0.0.1",
            sqlserver_database="InventoryChatbot",
            sqlserver_user="sa",
            sqlserver_password="password",
        )
        with self.assertRaises(ValueError):
            build_data_backend_runtime(config, repository=InMemoryRepository())

    def test_sqlite_backend_runtime_rejects_custom_repository_injection(self) -> None:
        config = AppConfig(
            data_backend="sqlite",
            provider="openai",
            openai_api_key="test-key",
            sqlite_database_path="inventory_chatbot.sqlite3",
        )
        with self.assertRaises(ValueError):
            build_data_backend_runtime(config, repository=InMemoryRepository())


if __name__ == "__main__":
    unittest.main()
