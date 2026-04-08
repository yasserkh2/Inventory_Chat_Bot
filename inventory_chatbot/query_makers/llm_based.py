from __future__ import annotations

from datetime import date

from inventory_chatbot.handoffs.models import PlannerActivation
from inventory_chatbot.llm.base import LLMClient, LLMProviderError
from inventory_chatbot.models.domain import SessionState
from inventory_chatbot.query_makers.base import QueryMaker
from inventory_chatbot.sql_agents.llm_based import LLMSQLAgent
from inventory_chatbot.sql_agents.models import SQLAgentDecision
from inventory_chatbot.sql_review.service import SQLReviewService
from inventory_chatbot.sql_execution.service import SQLExecutionService


class LLMQueryMaker(QueryMaker):
    def __init__(
        self,
        *,
        llm_client: LLMClient,
        today: date,
        customer_names: list[str],
        execution_service: SQLExecutionService | None = None,
        review_service: SQLReviewService | None = None,
        max_iterations: int = 3,
    ) -> None:
        self._sql_agent = LLMSQLAgent(
            llm_client=llm_client,
            today=today,
            customer_names=customer_names,
            execution_service=execution_service or SQLExecutionService(),
            review_service=review_service,
            max_iterations=max_iterations,
        )

    def decide(
        self,
        message: str,
        session_state: SessionState,
        activation: PlannerActivation,
    ) -> SQLAgentDecision | None:
        try:
            return self._sql_agent.decide(message, session_state, activation)
        except LLMProviderError:
            return None

    def get_last_debug_trace(self) -> dict | None:
        return self._sql_agent.get_last_debug_trace()
