from __future__ import annotations

import re
from datetime import date

from pydantic import ValidationError

from inventory_chatbot.dynamic_sql.compiler import SQLCompiler
from inventory_chatbot.dynamic_sql.models import QueryPlan
from inventory_chatbot.handoffs.models import PlannerActivation
from inventory_chatbot.llm.base import LLMClient, LLMProviderError
from inventory_chatbot.models.domain import SessionState
from inventory_chatbot.orchestrator.models import RequiredDataPoint
from inventory_chatbot.sql_agents.base import SQLAgent
from inventory_chatbot.sql_agents.metadata import SQL_AGENT_METADATA
from inventory_chatbot.sql_agents.models import SQLAgentDecision
from inventory_chatbot.sql_agents.prompts import (
    build_sql_agent_context,
    build_sql_agent_system_prompt,
    build_sql_agent_user_prompt,
)
from inventory_chatbot.sql_review.models import SQLReviewRequest
from inventory_chatbot.sql_review.service import SQLReviewService
from inventory_chatbot.sql_execution.models import SQLExecutionRequest
from inventory_chatbot.sql_execution.service import SQLExecutionService, SQLExecutionServiceError


class LLMSQLAgent(SQLAgent):
    def __init__(
        self,
        *,
        llm_client: LLMClient,
        today: date,
        customer_names: list[str],
        execution_service: SQLExecutionService,
        review_service: SQLReviewService | None = None,
        max_iterations: int = 3,
    ) -> None:
        self._llm_client = llm_client
        self._today = today
        self._customer_names = customer_names
        self._execution_service = execution_service
        self._review_service = review_service or SQLReviewService()
        self._compiler = SQLCompiler()
        self._max_iterations = max(1, max_iterations)
        self._last_debug_trace: dict | None = None

    def decide(
        self,
        message: str,
        session_state: SessionState,
        activation: PlannerActivation,
    ) -> SQLAgentDecision | None:
        agent_name = activation.agent_name
        if agent_name not in SQL_AGENT_METADATA:
            return None

        self._last_debug_trace = {
            "agent_name": agent_name,
            "max_iterations": self._max_iterations,
            "attempts": [],
        }
        schema_context = build_sql_agent_context(
            agent_name=agent_name,
            today=self._today,
            customer_names=self._customer_names,
        )
        session_history = self._format_session_history(session_state)
        prior_attempts: list[str] = []
        best_decision: SQLAgentDecision | None = None

        for iteration_index in range(1, self._max_iterations + 1):
            prompt = build_sql_agent_user_prompt(
                agent_name=agent_name,
                user_message=message,
                schema_context=schema_context,
                session_history=session_history,
                orchestrator_handoff=activation.handoff_summary,
                activation_context=activation.context,
                iteration_index=iteration_index,
                max_iterations=self._max_iterations,
                prior_attempts=prior_attempts,
            )
            attempt_trace = {
                "iteration": iteration_index,
                "prompt": prompt,
            }
            self._last_debug_trace["attempts"].append(attempt_trace)
            try:
                payload, _usage = self._llm_client.generate_structured_json(
                    system_prompt=build_sql_agent_system_prompt(agent_name),
                    user_prompt=prompt,
                )
            except LLMProviderError:
                attempt_trace["provider_error"] = True
                return self._finalize_best_effort(best_decision, message, activation)

            attempt_trace["raw_payload"] = payload
            decision = self._coerce_decision(
                payload=payload,
                agent_name=agent_name,
                message=message,
                activation=activation,
                attempt_trace=attempt_trace,
            )
            if decision is None:
                attempt_trace["decision_validation"] = "invalid"
                prior_attempts.append(
                    f"Attempt {iteration_index} failed to return a valid SQL agent decision."
                )
                continue

            best_decision = decision
            attempt_trace["decision_validation"] = "valid"
            attempt_trace["parsed_decision"] = decision.model_dump(mode="json")
            reviewed_decision, review_feedback = self._review_decision(
                message=message,
                decision=decision,
                attempt_trace=attempt_trace,
            )
            if review_feedback is None:
                attempt_trace["review_feedback"] = None
                return self._finalize_best_effort(reviewed_decision, message, activation)

            attempt_trace["review_feedback"] = review_feedback
            prior_attempts.append(
                self._summarize_attempt(
                    iteration_index=iteration_index,
                    decision=reviewed_decision,
                    review_feedback=review_feedback,
                )
            )

        finalized = self._finalize_best_effort(best_decision, message, activation)
        if finalized is not None:
            if self._last_debug_trace is not None:
                self._last_debug_trace["finalized_decision"] = finalized.model_dump(mode="json")
            return finalized
        fallback = self._build_terminal_fallback(
            message=message,
            activation=activation,
            prior_attempts=prior_attempts,
        )
        if self._last_debug_trace is not None:
            self._last_debug_trace["finalized_decision"] = fallback.model_dump(mode="json")
        return fallback

    def _coerce_decision(
        self,
        *,
        payload,
        agent_name: str,
        message: str,
        activation: PlannerActivation,
        attempt_trace: dict[str, object] | None = None,
    ) -> SQLAgentDecision | None:
        if not isinstance(payload, dict):
            self._record_trace(
                attempt_trace,
                parse_mode="invalid_payload_type",
                validation_error=f"Expected a JSON object but received {type(payload).__name__}.",
            )
            return None
        try:
            decision = SQLAgentDecision.model_validate(payload)
            if decision.agent_name != agent_name:
                decision = decision.model_copy(update={"agent_name": agent_name})
            self._record_trace(attempt_trace, parse_mode="sql_agent_decision")
            return decision
        except ValidationError as exc:
            self._record_trace(
                attempt_trace,
                parse_mode="sql_agent_decision_invalid",
                validation_error=self._format_validation_error(exc),
            )

        try:
            query_plan = QueryPlan.model_validate(payload)
        except ValidationError as exc:
            self._record_trace(
                attempt_trace,
                query_plan_validation_error=self._format_validation_error(exc),
            )
            return None

        orchestrator_context = activation.context.get("orchestrator", {})
        required_data = orchestrator_context.get("required_data", [])
        self._record_trace(attempt_trace, parse_mode="query_plan_fallback")
        return SQLAgentDecision(
            agent_name=agent_name,
            action="execute",
            user_need=message,
            analysis_summary=activation.handoff_summary,
            required_data=[
                RequiredDataPoint.model_validate(item) for item in required_data
            ],
            query_strategy="Build an executable SQL query for the requested result using only domain-owned tables.",
            sql_query=self._compiler.compile(query_plan),
            query_plan=query_plan,
        )

    def _review_decision(
        self,
        *,
        message: str,
        decision: SQLAgentDecision,
        attempt_trace: dict[str, object] | None = None,
    ) -> tuple[SQLAgentDecision, str | None]:
        if not decision.user_need.strip():
            return decision, "Summarize the user need before continuing."
        if not decision.analysis_summary.strip():
            return decision, "Explain the SQL reasoning for why this domain can handle the request."

        if decision.action == "clarify":
            if not (decision.clarification_question or "").strip():
                return decision, "Action is clarify, but clarification_question is empty."
            return decision, None

        if decision.action == "unsupported":
            if not (decision.unsupported_reason or "").strip():
                return decision, "Action is unsupported, but unsupported_reason is empty."
            return decision, None

        if not decision.required_data:
            return decision, "List the exact tables and columns required for the result."
        if not decision.query_strategy.strip():
            return decision, "Describe the query strategy before deciding whether to execute."

        sql_query = (decision.sql_query or "").strip()
        if not sql_query:
            if decision.query_plan is None:
                return decision, "Action is execute, but sql_query is missing."
            sql_query = self._compiler.compile(decision.query_plan)
            decision = decision.model_copy(update={"sql_query": sql_query})

        review_result = self._review_service.review(
            SQLReviewRequest(
                user_message=message,
                sql_query=sql_query,
                source_agent=decision.agent_name,
                allowed_tables=list(SQL_AGENT_METADATA[decision.agent_name]["tables"]),
            )
        )
        self._record_trace(
            attempt_trace,
            sql_review=review_result.model_dump(mode="json"),
        )
        if not review_result.approved or review_result.normalized_query_plan is None:
            issue = review_result.issues[0] if review_result.issues else "SQL review rejected the query."
            return decision, f"The SQL query is not executable yet: {issue}"

        decision = decision.model_copy(
            update={
                "sql_query": review_result.reviewed_sql,
                "query_plan": review_result.normalized_query_plan,
            }
        )

        try:
            self._execution_service.preview_sql(
                SQLExecutionRequest(
                    user_message=message,
                    query_plan=decision.query_plan,
                    sql_query=decision.sql_query,
                    source_agent=decision.agent_name,
                    allowed_tables=list(SQL_AGENT_METADATA[decision.agent_name]["tables"]),
                )
            )
        except SQLExecutionServiceError as exc:
            return decision, f"The reviewed SQL plan is not executable yet: {exc}"

        if self._looks_like_row_request(message):
            if not decision.query_plan.selects:
                return decision, "Row inspection requests must include explicit selects."
            if not decision.query_plan.order_by:
                return decision, "Row inspection requests must include deterministic order_by."
        return decision, None

    @staticmethod
    def _summarize_attempt(
        *,
        iteration_index: int,
        decision: SQLAgentDecision,
        review_feedback: str,
    ) -> str:
        return (
            f"Attempt {iteration_index}: action={decision.action}, "
            f"user_need={decision.user_need or '[missing]'}, "
            f"analysis_summary={decision.analysis_summary or '[missing]'}, "
            f"required_data_count={len(decision.required_data)}, "
            f"query_strategy={decision.query_strategy or '[missing]'}. "
            f"Review feedback: {review_feedback}"
        )

    def _finalize_best_effort(
        self,
        decision: SQLAgentDecision | None,
        message: str,
        activation: PlannerActivation,
    ) -> SQLAgentDecision | None:
        if decision is None:
            return None
        updates: dict[str, object] = {}
        if not decision.user_need.strip():
            updates["user_need"] = message.strip()
        if not decision.analysis_summary.strip():
            updates["analysis_summary"] = activation.handoff_summary or (
                f"This request is being handled by the {decision.agent_name} SQL agent."
            )
        if not decision.query_strategy.strip():
            updates["query_strategy"] = (
                "Identify the required domain tables, then prepare an executable schema-valid SQL query."
            )
        if decision.action == "clarify" and not (decision.clarification_question or "").strip():
            updates["clarification_question"] = (
                "Which exact filter, customer, site, or date range should I use?"
            )
        if decision.action == "unsupported" and not (decision.unsupported_reason or "").strip():
            updates["unsupported_reason"] = (
                "This request does not fit the current SQL agent domain."
            )
        finalized = decision if not updates else decision.model_copy(update=updates)
        if finalized.action != "execute":
            return finalized

        if finalized.query_plan is not None:
            if (finalized.sql_query or "").strip():
                return finalized
            return finalized.model_copy(
                update={"sql_query": self._compiler.compile(finalized.query_plan)}
            )

        sql_query = (finalized.sql_query or "").strip()
        if not sql_query:
            return self._downgrade_execute_to_clarify(
                finalized,
                "I could not finalize an executable query plan from the generated output.",
            )

        review_result = self._review_service.review(
            SQLReviewRequest(
                user_message=message,
                sql_query=sql_query,
                source_agent=finalized.agent_name,
                allowed_tables=list(SQL_AGENT_METADATA[finalized.agent_name]["tables"]),
            )
        )
        if not review_result.approved or review_result.normalized_query_plan is None:
            issue = review_result.issues[0] if review_result.issues else "SQL review rejected the query."
            return self._downgrade_execute_to_clarify(
                finalized,
                f"I could not finalize an executable query plan because: {issue}",
            )

        recovered = finalized.model_copy(
            update={
                "sql_query": review_result.reviewed_sql,
                "query_plan": review_result.normalized_query_plan,
            }
        )
        try:
            self._execution_service.preview_sql(
                SQLExecutionRequest(
                    user_message=message,
                    query_plan=recovered.query_plan,
                    sql_query=recovered.sql_query,
                    source_agent=recovered.agent_name,
                    allowed_tables=list(SQL_AGENT_METADATA[recovered.agent_name]["tables"]),
                )
            )
        except SQLExecutionServiceError as exc:
            return self._downgrade_execute_to_clarify(
                recovered,
                f"I could not finalize an executable query plan because: {exc}",
            )
        return recovered

    @staticmethod
    def _downgrade_execute_to_clarify(
        decision: SQLAgentDecision,
        reason: str,
    ) -> SQLAgentDecision:
        return decision.model_copy(
            update={
                "action": "clarify",
                "clarification_question": (
                    f"{reason} Please restate the exact metric, filters, and date range."
                ),
            }
        )

    @staticmethod
    def _build_terminal_fallback(
        *,
        message: str,
        activation: PlannerActivation,
        prior_attempts: list[str],
    ) -> SQLAgentDecision:
        summary = activation.handoff_summary or (
            f"The {activation.agent_name} SQL agent could not complete a valid planning pass."
        )
        details = " ".join(prior_attempts[-2:]).strip()
        clarification = (
            "I could not finalize a valid SQL plan. Please restate the request with the exact metric, "
            "filters, and date range you want."
        )
        return SQLAgentDecision(
            agent_name=activation.agent_name,
            action="clarify",
            user_need=message.strip(),
            analysis_summary=summary,
            required_data=[],
            query_strategy=(
                "Attempt to build an executable SQL query, but stop and ask for clarification "
                "when repeated planning attempts fail validation."
            ),
            clarification_question=clarification if not details else f"{clarification} Debug context: {details}",
        )

    def get_last_debug_trace(self) -> dict | None:
        return self._last_debug_trace

    @staticmethod
    def _record_trace(attempt_trace: dict[str, object] | None, **updates: object) -> None:
        if attempt_trace is None:
            return
        attempt_trace.update(updates)

    @staticmethod
    def _format_validation_error(exc: ValidationError) -> list[dict[str, object]]:
        formatted: list[dict[str, object]] = []
        for error in exc.errors():
            formatted.append(
                {
                    "location": list(error.get("loc", ())),
                    "message": error.get("msg", ""),
                    "type": error.get("type", ""),
                }
            )
        return formatted

    @staticmethod
    def _format_session_history(session_state: SessionState) -> str:
        if not session_state.turns:
            return "No prior conversation."
        lines = []
        for turn in session_state.turns[-5:]:
            lines.append(f"User: {turn.user_message}")
            if turn.assistant_message:
                lines.append(f"Assistant: {turn.assistant_message}")
        return "\n".join(lines)

    @staticmethod
    def _looks_like_row_request(message: str) -> bool:
        normalized = re.sub(r"\s+", " ", message.lower())
        phrases = (
            "show",
            "list",
            "rows",
            "row",
            "records",
            "first ",
            "latest",
            "sample",
        )
        return any(phrase in normalized for phrase in phrases)
