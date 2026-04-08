from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class SpecialistActivation(BaseModel):
    agent_name: str
    instructions: str
    context: dict[str, Any] = Field(default_factory=dict)


class PlannerActivation(BaseModel):
    agent_name: str
    handoff_summary: str
    context: dict[str, Any] = Field(default_factory=dict)


class DynamicSQLActivation(BaseModel):
    target_agent: str = "dynamic_sql"
    instructions: str
    context: dict[str, Any] = Field(default_factory=dict)
