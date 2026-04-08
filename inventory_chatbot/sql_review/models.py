from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from inventory_chatbot.dynamic_sql.models import QueryPlan


class SQLReviewRequest(BaseModel):
    user_message: str
    sql_query: str
    source_agent: str | None = None
    allowed_tables: list[str] = Field(default_factory=list)
    context: dict[str, Any] = Field(default_factory=dict)


class SQLReviewResult(BaseModel):
    approved: bool
    review_summary: str
    issues: list[str] = Field(default_factory=list)
    reviewed_sql: str | None = None
    normalized_query_plan: QueryPlan | None = None
