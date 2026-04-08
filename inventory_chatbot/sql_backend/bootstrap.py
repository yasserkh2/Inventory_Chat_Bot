from __future__ import annotations

from dataclasses import dataclass

from inventory_chatbot.config import AppConfig
from inventory_chatbot.sql_backend.connection import build_engine, check_health
from inventory_chatbot.sql_backend.query_runner import SQLServerQueryRunner
from inventory_chatbot.sql_backend.repository import SQLServerRepository


@dataclass
class SQLBackendComponents:
    repository: SQLServerRepository
    query_runner: SQLServerQueryRunner


def build_sql_backend(config: AppConfig) -> SQLBackendComponents:
    engine = build_engine(config)
    check_health(engine)
    repository = SQLServerRepository(engine=engine)
    query_runner = SQLServerQueryRunner(engine=engine)
    return SQLBackendComponents(repository=repository, query_runner=query_runner)

