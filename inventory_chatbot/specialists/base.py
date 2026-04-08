from __future__ import annotations

import re
from abc import ABC, abstractmethod
from typing import Iterable

from inventory_chatbot.models.domain import (
    AgentReply,
    AgentTask,
    ComputedResult,
    MatchResult,
    QueryPlan,
    SessionState,
)


class Specialist(ABC):
    name: str

    def handle_task(self, task: AgentTask, session_state: SessionState) -> AgentReply:
        match = self.match(task.user_message, session_state)
        if match is None:
            return AgentReply(
                request_id=task.request_id,
                agent_name=self.name,
                status="unsupported",
                message=f"{self.name} could not handle the requested task.",
            )

        if match.missing_parameters:
            clarification_message = match.clarification_message or (
                "More information is required before this request can be executed."
            )
            return AgentReply(
                request_id=task.request_id,
                agent_name=self.name,
                status="needs_clarification",
                intent_id=match.intent_id,
                message=clarification_message,
                parameters=match.parameters,
                missing_parameters=match.missing_parameters,
            )

        plan = self.build_query_plan(match)
        result = self.execute(plan)
        return AgentReply(
            request_id=task.request_id,
            agent_name=self.name,
            status="ok",
            intent_id=plan.intent_id,
            sql_query=self.render_sql(plan),
            parameters=plan.parameters,
            computed_result=result,
        )

    @abstractmethod
    def match(self, message: str, session_state: SessionState) -> MatchResult | None:
        raise NotImplementedError

    @abstractmethod
    def build_query_plan(self, match: MatchResult) -> QueryPlan:
        raise NotImplementedError

    @abstractmethod
    def execute(self, plan: QueryPlan) -> ComputedResult:
        raise NotImplementedError

    @abstractmethod
    def render_sql(self, plan: QueryPlan) -> str:
        raise NotImplementedError

    @staticmethod
    def normalize_text(text: str) -> str:
        return re.sub(r"[^a-z0-9\s]+", " ", text.lower()).strip()

    @staticmethod
    def contains_any(text: str, candidates: Iterable[str]) -> bool:
        return any(candidate in text for candidate in candidates)

    @staticmethod
    def extract_entity_name(message: str, names: Iterable[str]) -> str | None:
        normalized = message.lower()
        for name in names:
            if name.lower() in normalized:
                return name
        return None
