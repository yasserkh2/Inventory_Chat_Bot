from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from inventory_chatbot.config import AppConfig
from inventory_chatbot.data.memory_repository import InMemoryRepository
from inventory_chatbot.data.seed_data import build_seed_data
from inventory_chatbot.dynamic_sql.service import DynamicSQLService
from inventory_chatbot.sql_execution.service import SQLExecutionService


@dataclass
class DataBackendRuntime:
    repository: Any
    dynamic_sql_service: DynamicSQLService | None
    sql_execution_service: SQLExecutionService


def build_data_backend_runtime(
    config: AppConfig,
    *,
    repository: Any | None = None,
) -> DataBackendRuntime:
    if config.data_backend in {"sqlserver", "sqlite"}:
        if repository is not None:
            raise ValueError(
                "Custom repository injection is not supported when DATA_BACKEND is sqlserver or sqlite."
            )
        from inventory_chatbot.sql_backend.bootstrap import build_sql_backend

        sql_backend = build_sql_backend(config)
        return DataBackendRuntime(
            repository=sql_backend.repository,
            dynamic_sql_service=None,
            sql_execution_service=SQLExecutionService(query_runner=sql_backend.query_runner),
        )

    resolved_repository = repository or InMemoryRepository()
    if isinstance(resolved_repository, InMemoryRepository):
        seed_data = resolved_repository.export_seed_data()
    else:
        seed_data = build_seed_data()
    dynamic_sql_service = DynamicSQLService(seed_data=seed_data)
    return DataBackendRuntime(
        repository=resolved_repository,
        dynamic_sql_service=dynamic_sql_service,
        sql_execution_service=SQLExecutionService(dynamic_sql_service=dynamic_sql_service),
    )
