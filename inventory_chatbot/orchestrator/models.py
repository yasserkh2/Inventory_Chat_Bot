from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class RequiredDataPoint(BaseModel):
    table: str
    columns: list[str] = Field(default_factory=list)
    reason: str


class OrchestratorDecision(BaseModel):
    agent: Literal["assets", "billing", "procurement", "sales", "chat", "none"]
    user_need: str = ""
    analysis_summary: str = ""
    required_data: list[RequiredDataPoint] = Field(default_factory=list)
    handoff_instructions: str = ""
    clarification_needed: bool = False
    clarification_question: str | None = None
