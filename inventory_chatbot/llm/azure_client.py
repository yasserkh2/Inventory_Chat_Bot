from __future__ import annotations

import json

from openai import AzureOpenAI
from openai import OpenAIError

from inventory_chatbot.config import AppConfig
from inventory_chatbot.llm.base import LLMClient, LLMProviderError
from inventory_chatbot.models.api import TokenUsage
from inventory_chatbot.models.domain import ComputedResult


class AzureOpenAIClient(LLMClient):
    def __init__(self, config: AppConfig) -> None:
        self._config = config
        self._client: AzureOpenAI | None = None

    def generate_answer(
        self, *, user_message: str, result: ComputedResult
    ) -> tuple[str, TokenUsage]:
        payload = {
            "model": self._config.azure_openai_deployment,
            "temperature": 0.2,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are a concise business analytics assistant. Rephrase the provided deterministic result. "
                        "Do not invent data, change numbers, or mention hidden reasoning."
                    ),
                },
                {
                    "role": "user",
                    "content": self._build_prompt(user_message=user_message, result=result),
                },
            ],
        }
        return self._perform_chat_completion(payload)

    def generate_structured_json(
        self, *, system_prompt: str, user_prompt: str
    ) -> tuple[dict | None, TokenUsage]:
        self._config.validate_provider_credentials()
        payload = {
            "model": self._config.azure_openai_deployment,
            "temperature": 0,
            "messages": [
                {
                    "role": "system",
                    "content": system_prompt,
                },
                {
                    "role": "user",
                    "content": user_prompt,
                },
            ],
        }
        message, usage = self._perform_chat_completion(payload)
        if message.strip().lower() == "null":
            return None, usage
        try:
            return json.loads(message), usage
        except json.JSONDecodeError as exc:
            raise LLMProviderError(f"Provider returned invalid JSON: {message}") from exc

    def generate_text(
        self, *, system_prompt: str, user_prompt: str
    ) -> tuple[str, TokenUsage]:
        payload = {
            "model": self._config.azure_openai_deployment,
            "temperature": 0.2,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        return self._perform_chat_completion(payload)

    def _perform_chat_completion(self, payload: dict) -> tuple[str, TokenUsage]:
        try:
            response = self._client_or_create().chat.completions.create(**payload)
        except OpenAIError as exc:
            raise LLMProviderError(self._format_provider_error(exc)) from exc

        choices = response.choices
        if not choices:
            raise LLMProviderError("Provider response did not include choices")
        content = choices[0].message.content or ""
        message = str(content).strip()
        if not message:
            raise LLMProviderError("Provider response did not include answer text")
        usage_payload = response.usage
        usage = TokenUsage(
            prompt_tokens=(usage_payload.prompt_tokens if usage_payload else 0) or 0,
            completion_tokens=(usage_payload.completion_tokens if usage_payload else 0) or 0,
            total_tokens=(usage_payload.total_tokens if usage_payload else 0) or 0,
        )
        return message, usage

    @staticmethod
    def _format_provider_error(exc: OpenAIError) -> str:
        primary_message = str(exc).strip() or exc.__class__.__name__
        cause = exc.__cause__
        if cause is None:
            return primary_message

        cause_message = str(cause).strip()
        if not cause_message or cause_message in primary_message:
            return primary_message
        return f"{primary_message} (cause: {cause_message})"

    def _client_or_create(self) -> AzureOpenAI:
        if self._client is None:
            self._config.validate_provider_credentials()
            self._client = AzureOpenAI(
                api_key=self._config.azure_openai_api_key,
                api_version=self._config.azure_openai_api_version,
                azure_endpoint=self._config.azure_openai_endpoint,
                timeout=self._config.request_timeout_seconds,
            )
        return self._client

    @staticmethod
    def _build_prompt(*, user_message: str, result: ComputedResult) -> str:
        facts = json.dumps(result.answer_context, default=str, indent=2)
        return (
            f"User question: {user_message}\n"
            f"Fallback answer: {result.fallback_answer}\n"
            f"Structured facts:\n{facts}\n"
            "Return a short final answer grounded only in those facts."
        )
