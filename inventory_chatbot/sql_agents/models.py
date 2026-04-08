from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from inventory_chatbot.dynamic_sql.models import QueryPlan
from inventory_chatbot.orchestrator.models import RequiredDataPoint


class SQLAgentDecision(BaseModel):
    agent_name: Literal["assets", "billing", "procurement", "sales"]
    action: Literal["execute", "clarify", "unsupported"]
    user_need: str = ""
    analysis_summary: str = ""
    required_data: list[RequiredDataPoint] = Field(default_factory=list)
    query_strategy: str = ""
    sql_query: str | None = None
    query_plan: QueryPlan | None = None
    clarification_question: str | None = None
    unsupported_reason: str | None = None
