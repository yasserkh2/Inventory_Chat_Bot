from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from inventory_chatbot.dynamic_sql.models import QueryPlan


class SQLExecutionRequest(BaseModel):
    user_message: str
    query_plan: QueryPlan
    sql_query: str | None = None
    source_agent: str | None = None
    allowed_tables: list[str] = Field(default_factory=list)
    context: dict[str, Any] = Field(default_factory=dict)
