from __future__ import annotations

from inventory_chatbot.models.domain import MatchResult, SessionState
from inventory_chatbot.specialists.base import Specialist


class SpecialistRegistry:
    def __init__(self, specialists: list[Specialist]) -> None:
        self._specialists = specialists
        self._by_name = {specialist.name: specialist for specialist in specialists}

    def resolve(
        self, message: str, session_state: SessionState
    ) -> tuple[Specialist, MatchResult] | None:
        for specialist in self._specialists:
            match = specialist.match(message, session_state)
            if match is not None:
                return specialist, match
        return None

    def get(self, name: str) -> Specialist | None:
        return self._by_name.get(name)
