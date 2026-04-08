from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class ChatRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=100)
    message: str = Field(min_length=1, max_length=2_000)
    context: dict[str, Any] = Field(default_factory=dict)

    @field_validator("session_id", "message")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value


class TokenUsage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class ChatResponse(BaseModel):
    natural_language_answer: str
    sql_query: str
    result_preview: dict[str, Any] = Field(default_factory=dict)
    token_usage: TokenUsage
    latency_ms: int
    provider: Literal["openai", "azure"]
    model: str
    status: Literal["ok", "error"]
