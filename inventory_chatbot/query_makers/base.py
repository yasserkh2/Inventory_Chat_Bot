from __future__ import annotations

from abc import ABC, abstractmethod

from inventory_chatbot.dynamic_sql.models import QueryPlan
from inventory_chatbot.handoffs.models import PlannerActivation
from inventory_chatbot.models.domain import SessionState
from inventory_chatbot.sql_agents.models import SQLAgentDecision


class QueryMaker(ABC):
    @abstractmethod
    def decide(
        self,
        message: str,
        session_state: SessionState,
        activation: PlannerActivation,
    ) -> SQLAgentDecision | None:
        raise NotImplementedError

    def make_plan(
        self,
        message: str,
        session_state: SessionState,
        activation: PlannerActivation,
    ) -> QueryPlan | None:
        decision = self.decide(message, session_state, activation)
        if decision is None or decision.action != "execute":
            return None
        return decision.query_plan

    def get_last_debug_trace(self) -> dict | None:
        return None
