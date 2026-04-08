from __future__ import annotations

from abc import ABC, abstractmethod

from inventory_chatbot.handoffs.models import PlannerActivation
from inventory_chatbot.models.domain import SessionState
from inventory_chatbot.sql_agents.models import SQLAgentDecision


class SQLAgent(ABC):
    @abstractmethod
    def decide(
        self,
        message: str,
        session_state: SessionState,
        activation: PlannerActivation,
    ) -> SQLAgentDecision | None:
        raise NotImplementedError

    def get_last_debug_trace(self) -> dict | None:
        return None
