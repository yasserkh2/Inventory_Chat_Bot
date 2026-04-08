from __future__ import annotations

from inventory_chatbot.config import AppConfig
from inventory_chatbot.llm.azure_client import AzureOpenAIClient
from inventory_chatbot.llm.base import LLMClient
from inventory_chatbot.llm.openai_client import OpenAIClient


def build_llm_client(config: AppConfig) -> LLMClient:
    if config.provider == "openai":
        return OpenAIClient(config)
    return AzureOpenAIClient(config)

