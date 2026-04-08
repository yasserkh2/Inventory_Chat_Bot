from __future__ import annotations

from abc import ABC, abstractmethod

from inventory_chatbot.models.api import TokenUsage
from inventory_chatbot.models.domain import ComputedResult


class LLMProviderError(RuntimeError):
    """Raised when a provider request cannot complete successfully."""


class LLMClient(ABC):
    @abstractmethod
    def generate_answer(
        self, *, user_message: str, result: ComputedResult
    ) -> tuple[str, TokenUsage]:
        raise NotImplementedError

    @abstractmethod
    def generate_structured_json(
        self, *, system_prompt: str, user_prompt: str
    ) -> tuple[dict | None, TokenUsage]:
        raise NotImplementedError

    @abstractmethod
    def generate_text(
        self, *, system_prompt: str, user_prompt: str
    ) -> tuple[str, TokenUsage]:
        raise NotImplementedError
