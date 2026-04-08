from __future__ import annotations

import re
import time
from datetime import date

from pydantic import ValidationError

from inventory_chatbot.config import AppConfig
from inventory_chatbot.dynamic_sql.models import OrderBySpec, QueryPlan as DynamicQueryPlan, SelectSpec
from inventory_chatbot.dynamic_sql.schema_catalog import SCHEMA_CATALOG
from inventory_chatbot.dynamic_sql.service import DynamicSQLService
from inventory_chatbot.handoffs.service import OrchestratorHandoffService
from inventory_chatbot.llm.base import LLMClient, LLMProviderError
from inventory_chatbot.models.api import ChatRequest, ChatResponse, TokenUsage
from inventory_chatbot.models.domain import AgentReply, AgentTask, SessionTurn
from inventory_chatbot.orchestrator.base import Orchestrator
from inventory_chatbot.orchestrator.models import OrchestratorDecision
from inventory_chatbot.query_makers.base import QueryMaker
from inventory_chatbot.query_makers.prompts import (
    CHAT_SYSTEM_PROMPT,
    build_chat_user_prompt,
    build_schema_context,
)
from inventory_chatbot.router.registry import SpecialistRegistry
from inventory_chatbot.services.response_formatter import build_response
from inventory_chatbot.services.session_store import SessionStore
from inventory_chatbot.sql_agents.models import SQLAgentDecision
from inventory_chatbot.sql_execution.models import SQLExecutionRequest
from inventory_chatbot.sql_execution.service import SQLExecutionService, SQLExecutionServiceError


class RouterService:
    def __init__(
        self,
        *,
        config: AppConfig,
        registry: SpecialistRegistry,
        session_store: SessionStore,
        llm_client: LLMClient,
        dynamic_sql_service: DynamicSQLService | None = None,
        sql_execution_service: SQLExecutionService | None = None,
        orchestrator: Orchestrator | None = None,
        query_maker: QueryMaker | None = None,
        handoff_service: OrchestratorHandoffService | None = None,
        customer_names: list[str] | None = None,
    ) -> None:
        self._config = config
        self._registry = registry
        self._session_store = session_store
        self._llm_client = llm_client
        self._dynamic_sql_service = dynamic_sql_service
        self._sql_execution_service = sql_execution_service or SQLExecutionService(
            dynamic_sql_service=dynamic_sql_service
        )
        self._orchestrator = orchestrator
        self._query_maker = query_maker
        self._handoff_service = handoff_service or OrchestratorHandoffService()
        self._customer_names = customer_names or []

    def handle_chat(self, request: ChatRequest) -> ChatResponse:
        started_at = time.perf_counter()
        session_state = self._session_store.get(request.session_id)
        if self._sql_execution_service and self._sql_execution_service.can_handle(request.context):
            try:
                execution_request = SQLExecutionRequest(
                    user_message=request.message,
                    query_plan=DynamicQueryPlan.model_validate(request.context["query_plan"]),
                    source_agent=request.context.get("source_agent"),
                    context=request.context,
                )
            except ValidationError as exc:
                reply = AgentReply(
                    request_id=f"{request.session_id}:1:dynamic_sql",
                    agent_name="dynamic_sql",
                    status="error",
                    intent_id="dynamic_sql_query",
                    message=f"Invalid query plan: {exc.errors()}",
                    parameters=request.context,
                )
                return self._finalize_agent_reply(request, started_at, reply)
            reply = self._dispatch_sql_execution_agent(
                execution_request,
                target_agent="dynamic_sql",
            )
            return self._finalize_agent_reply(request, started_at, reply)

        preview_plan = self._build_table_preview_plan(request.message)
        if preview_plan is not None and self._sql_execution_service:
            reply = self._dispatch_sql_execution_agent(
                SQLExecutionRequest(
                    user_message=request.message,
                    query_plan=preview_plan,
                    source_agent="preview",
                ),
                target_agent="dynamic_sql",
            )
            return self._finalize_agent_reply(request, started_at, reply)

        domain_agents = {"assets", "billing", "procurement", "sales"}
        if self._orchestrator:
            decision = self._orchestrator.decide(request.message, session_state)
            if decision is not None:
                if decision.clarification_needed:
                    return self._finalize_agent_reply(
                        request,
                        started_at,
                        self._build_clarification_reply(request, session_state, decision),
                    )

                if decision.agent == "chat":
                    return self._handle_llm_chat(request, started_at, session_state)

                if decision.agent in domain_agents:
                    specialist_activation = self._handoff_service.build_specialist_activation(
                        decision
                    )
                    specialist_reply = self._dispatch_specialist_agent(
                        self._build_agent_task(
                            request=request,
                            session_state=session_state,
                            target_agent=specialist_activation.agent_name,
                            instructions=specialist_activation.instructions,
                            context=specialist_activation.context,
                        ),
                        session_state,
                    )
                    if specialist_reply and specialist_reply.status == "ok":
                        return self._finalize_agent_reply(request, started_at, specialist_reply)

                    if self._sql_execution_service and self._query_maker:
                        planner_activation = self._handoff_service.build_planner_activation(
                            decision
                        )
                        sql_agent_decision = self._query_maker.decide(
                            request.message,
                            session_state,
                            planner_activation,
                        )
                        if sql_agent_decision is not None:
                            if sql_agent_decision.action == "clarify":
                                return self._finalize_agent_reply(
                                    request,
                                    started_at,
                                    self._build_sql_agent_clarification_reply(
                                        request=request,
                                        session_state=session_state,
                                        sql_agent_decision=sql_agent_decision,
                                    ),
                                )
                            if sql_agent_decision.action == "unsupported":
                                return self._finalize_agent_reply(
                                    request,
                                    started_at,
                                    self._build_sql_agent_unsupported_reply(
                                        request=request,
                                        session_state=session_state,
                                        sql_agent_decision=sql_agent_decision,
                                    ),
                                )
                            try:
                                execution_request = self._handoff_service.build_execution_request(
                                    user_message=request.message,
                                    orchestrator_decision=decision,
                                    sql_agent_decision=sql_agent_decision,
                                )
                            except ValueError as exc:
                                return self._finalize_agent_reply(
                                    request,
                                    started_at,
                                    AgentReply(
                                        request_id=(
                                            f"{request.session_id}:"
                                            f"{len(session_state.turns) + 1}:"
                                            f"{sql_agent_decision.agent_name}_sql_agent"
                                        ),
                                        agent_name=f"{sql_agent_decision.agent_name}_sql_agent",
                                        status="error",
                                        intent_id="sql_agent_handoff_error",
                                        message=str(exc),
                                        parameters={"sql_agent": sql_agent_decision.model_dump(mode="json")},
                                    ),
                                )
                            reply = self._dispatch_sql_execution_agent(
                                execution_request,
                                target_agent="dynamic_sql",
                            )
                            return self._finalize_agent_reply(request, started_at, reply)

                    if specialist_reply and specialist_reply.status == "needs_clarification":
                        return self._finalize_agent_reply(request, started_at, specialist_reply)

        resolved = self._registry.resolve(request.message, session_state)
        if resolved is not None:
            specialist, _match = resolved
            reply = self._dispatch_specialist_agent(
                self._build_agent_task(
                    request=request,
                    session_state=session_state,
                    target_agent=specialist.name,
                    instructions=(
                        f"Handle this request using the {specialist.name} domain specialist rules."
                    ),
                ),
                session_state,
            )
            if reply is not None:
                return self._finalize_agent_reply(request, started_at, reply)

        return self._handle_llm_chat(request, started_at, session_state)

    def _build_table_preview_plan(self, message: str) -> DynamicQueryPlan | None:
        normalized = re.sub(r"[^a-z0-9\s_]+", " ", message.lower()).strip()
        if "table" not in normalized and "rows" not in normalized and "row" not in normalized:
            return None

        match = re.search(
            r"(?:list|show|give|display)?\s*(?:me\s+)?(?:the\s+)?first\s+(?:(?P<count>\d+)\s+rows?|row)\s+(?:in|of|from)\s+(?P<table>[a-z_ ]+?)(?:\s+table)?$",
            normalized,
        )
        if match is None:
            return None

        raw_table_name = " ".join((match.group("table") or "").split())
        table_name = self._resolve_schema_table(raw_table_name)
        if table_name is None:
            return None

        limit = 1 if "first row" in normalized else int(match.group("count") or "5")
        table_schema = SCHEMA_CATALOG[table_name]
        primary_key = table_schema["primary_key"]
        columns = list(table_schema["columns"].keys())
        selects = [
            SelectSpec(column=f"{table_name}.{column_name}", alias=column_name)
            for column_name in columns
        ]
        return DynamicQueryPlan(
            base_table=table_name,
            selects=selects,
            order_by=[OrderBySpec(expression=f"{table_name}.{primary_key}", direction="ASC")],
            limit=limit,
        )

    @staticmethod
    def _resolve_schema_table(raw_table_name: str) -> str | None:
        normalized = raw_table_name.replace("_", " ").strip().lower()
        compact = normalized.replace(" ", "")
        for table_name in SCHEMA_CATALOG:
            table_normalized = table_name.lower()
            if compact == table_normalized or normalized == table_normalized:
                return table_name
        return None

    def _build_agent_task(
        self,
        *,
        request: ChatRequest,
        session_state,
        target_agent: str,
        instructions: str,
        context: dict | None = None,
    ) -> AgentTask:
        request_id = f"{request.session_id}:{len(session_state.turns) + 1}:{target_agent}"
        return AgentTask(
            request_id=request_id,
            user_message=request.message,
            target_agent=target_agent,
            instructions=instructions,
            context=context or {},
        )

    def _dispatch_specialist_agent(
        self,
        task: AgentTask,
        session_state,
    ) -> AgentReply | None:
        specialist = self._registry.get(task.target_agent)
        if specialist is None:
            return None
        try:
            return specialist.handle_task(task, session_state)
        except Exception as exc:  # pragma: no cover - safety net
            return AgentReply(
                request_id=task.request_id,
                agent_name=task.target_agent,
                status="error",
                message=str(exc),
            )

    def _dispatch_sql_execution_agent(
        self,
        request: SQLExecutionRequest,
        *,
        target_agent: str,
    ) -> AgentReply:
        try:
            result, sql_query = self._sql_execution_service.execute(request)
        except SQLExecutionServiceError as exc:
            return AgentReply(
                request_id=f"{request.source_agent or 'sql'}:{target_agent}",
                agent_name=target_agent,
                status="error",
                intent_id="dynamic_sql_query",
                message=str(exc),
                parameters=request.context,
            )
        return AgentReply(
            request_id=f"{request.source_agent or 'sql'}:{target_agent}",
            agent_name=target_agent,
            status="ok",
            intent_id="dynamic_sql_query",
            sql_query=sql_query,
            parameters=request.context,
            computed_result=result,
        )

    def _build_clarification_reply(
        self,
        request: ChatRequest,
        session_state,
        decision: OrchestratorDecision,
    ) -> AgentReply:
        task = self._build_agent_task(
            request=request,
            session_state=session_state,
            target_agent="orchestrator",
            instructions="Ask for the missing detail before routing the request.",
            context={"orchestrator": decision.model_dump(mode="json")},
        )
        return AgentReply(
            request_id=task.request_id,
            agent_name=task.target_agent,
            status="needs_clarification",
            intent_id="orchestrator_clarification",
            message=decision.clarification_question
            or "I need one more detail before I can route that request.",
            parameters={"orchestrator": decision.model_dump(mode="json")},
        )

    def _build_sql_agent_clarification_reply(
        self,
        *,
        request: ChatRequest,
        session_state,
        sql_agent_decision: SQLAgentDecision,
    ) -> AgentReply:
        task = self._build_agent_task(
            request=request,
            session_state=session_state,
            target_agent=f"{sql_agent_decision.agent_name}_sql_agent",
            instructions="Ask for the missing detail before building the query plan.",
            context={"sql_agent": sql_agent_decision.model_dump(mode="json")},
        )
        return AgentReply(
            request_id=task.request_id,
            agent_name=task.target_agent,
            status="needs_clarification",
            intent_id="sql_agent_clarification",
            message=sql_agent_decision.clarification_question
            or "I need one more detail before I can build the SQL query.",
            parameters={"sql_agent": sql_agent_decision.model_dump(mode="json")},
        )

    def _build_sql_agent_unsupported_reply(
        self,
        *,
        request: ChatRequest,
        session_state,
        sql_agent_decision: SQLAgentDecision,
    ) -> AgentReply:
        task = self._build_agent_task(
            request=request,
            session_state=session_state,
            target_agent=f"{sql_agent_decision.agent_name}_sql_agent",
            instructions="Explain why the SQL agent cannot support this request.",
            context={"sql_agent": sql_agent_decision.model_dump(mode="json")},
        )
        return AgentReply(
            request_id=task.request_id,
            agent_name=task.target_agent,
            status="unsupported",
            intent_id="sql_agent_unsupported",
            message=sql_agent_decision.unsupported_reason
            or "The SQL planning agent could not support that request.",
            parameters={"sql_agent": sql_agent_decision.model_dump(mode="json")},
        )

    def _finalize_agent_reply(
        self,
        request: ChatRequest,
        started_at: float,
        reply: AgentReply,
    ) -> ChatResponse:
        if reply.status == "ok":
            try:
                answer, usage = self._llm_client.generate_answer(
                    user_message=request.message,
                    result=reply.computed_result,
                )
                status = "ok"
            except LLMProviderError as exc:
                answer = f"Unable to contact the configured AI provider: {exc}"
                usage = TokenUsage()
                status = "error"
        elif reply.status == "needs_clarification":
            answer = reply.message or "I need more information before I can run that request."
            usage = TokenUsage()
            status = "ok"
        else:
            answer = reply.message or "The delegated agent could not complete the request."
            usage = TokenUsage()
            status = "error"

        latency_ms = self._latency_ms(started_at)
        response = build_response(
            answer=answer,
            sql_query=reply.sql_query,
            result_preview=reply.computed_result.answer_context if reply.computed_result else {},
            usage=usage,
            latency_ms=latency_ms,
            config=self._config,
            status=status,
        )
        self._session_store.append_turn(
            request.session_id,
            SessionTurn(
                user_message=request.message,
                status=status,
                assistant_message=answer,
                sql_query=reply.sql_query,
                specialist_name=reply.agent_name,
                intent_id=reply.intent_id,
                parameters=reply.parameters,
                missing_parameters=reply.missing_parameters,
                clarification_message=reply.message
                if reply.status == "needs_clarification"
                else None,
            ),
        )
        return response

    def _handle_llm_chat(
        self, request: ChatRequest, started_at: float, session_state
    ) -> ChatResponse:
        schema_context = build_schema_context(
            today=date.today(),
            customer_names=self._customer_names,
        )
        history_lines = []
        for turn in session_state.turns[-5:]:
            history_lines.append(f"User: {turn.user_message}")
            if turn.assistant_message:
                history_lines.append(f"Assistant: {turn.assistant_message}")
        session_history = "\n".join(history_lines) if history_lines else "No prior conversation."

        try:
            answer, usage = self._llm_client.generate_text(
                system_prompt=CHAT_SYSTEM_PROMPT,
                user_prompt=build_chat_user_prompt(
                    user_message=request.message,
                    schema_context=schema_context,
                    session_history=session_history,
                ),
            )
            status = "ok"
        except LLMProviderError as exc:
            answer = f"Unable to contact the configured AI provider: {exc}"
            usage = TokenUsage()
            status = "error"

        latency_ms = self._latency_ms(started_at)
        response = build_response(
            answer=answer,
            sql_query="",
            result_preview={},
            usage=usage,
            latency_ms=latency_ms,
            config=self._config,
            status=status,
        )
        self._session_store.append_turn(
            request.session_id,
            SessionTurn(
                user_message=request.message,
                status=status,
                assistant_message=answer,
                specialist_name="llm_chat",
                intent_id="chat",
            ),
        )
        return response

    @staticmethod
    def _latency_ms(started_at: float) -> int:
        return round((time.perf_counter() - started_at) * 1000)
