from __future__ import annotations

from typing import Any

from inventory_chatbot.config import AppConfig
from inventory_chatbot.models.api import ChatResponse, TokenUsage


def build_response(
    *,
    answer: str,
    sql_query: str,
    result_preview: dict[str, Any] | None = None,
    usage: TokenUsage,
    latency_ms: int,
    config: AppConfig,
    status: str,
) -> ChatResponse:
    return ChatResponse(
        natural_language_answer=answer,
        sql_query=sql_query,
        result_preview=result_preview or {},
        token_usage=usage,
        latency_ms=latency_ms,
        provider=config.provider,
        model=config.model_name,
        status=status,
    )
