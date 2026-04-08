from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class DateRange(BaseModel):
    start_date: date
    end_date: date
    label: str


class MatchResult(BaseModel):
    intent_id: str
    specialist_name: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    missing_parameters: list[str] = Field(default_factory=list)
    confidence: int = Field(default=100, ge=0, le=100)
    uses_session_context: bool = False
    clarification_message: str | None = None


class QueryPlan(BaseModel):
    intent_id: str
    specialist_name: str
    parameters: dict[str, Any] = Field(default_factory=dict)


class ComputedResult(BaseModel):
    intent_id: str
    specialist_name: str
    answer_context: dict[str, Any] = Field(default_factory=dict)
    fallback_answer: str


class AgentTask(BaseModel):
    request_id: str
    user_message: str
    target_agent: str
    instructions: str | None = None
    context: dict[str, Any] = Field(default_factory=dict)


class AgentReply(BaseModel):
    request_id: str
    agent_name: str
    status: Literal["ok", "needs_clarification", "unsupported", "error"]
    intent_id: str | None = None
    message: str | None = None
    sql_query: str = ""
    parameters: dict[str, Any] = Field(default_factory=dict)
    missing_parameters: list[str] = Field(default_factory=list)
    computed_result: ComputedResult | None = None


class SessionTurn(BaseModel):
    user_message: str
    status: Literal["ok", "error"]
    assistant_message: str | None = None
    sql_query: str | None = None
    specialist_name: str | None = None
    intent_id: str | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)
    missing_parameters: list[str] = Field(default_factory=list)
    clarification_message: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class SessionState(BaseModel):
    session_id: str
    turns: list[SessionTurn] = Field(default_factory=list)

    def last_turn(self) -> SessionTurn | None:
        return self.turns[-1] if self.turns else None

    def last_successful_turn(self) -> SessionTurn | None:
        for turn in reversed(self.turns):
            if turn.status == "ok":
                return turn
        return None
