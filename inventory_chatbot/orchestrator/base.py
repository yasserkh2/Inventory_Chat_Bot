from __future__ import annotations

from abc import ABC, abstractmethod

from inventory_chatbot.models.domain import SessionState
from inventory_chatbot.orchestrator.models import OrchestratorDecision


class Orchestrator(ABC):
    @abstractmethod
    def decide(
        self, message: str, session_state: SessionState
    ) -> OrchestratorDecision | None:
        raise NotImplementedError

    def get_last_debug_trace(self) -> dict | None:
        return None
