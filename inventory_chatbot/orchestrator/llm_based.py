from __future__ import annotations

from datetime import date
import re

from pydantic import ValidationError

from inventory_chatbot.llm.base import LLMClient, LLMProviderError
from inventory_chatbot.models.domain import SessionState
from inventory_chatbot.orchestrator.base import Orchestrator
from inventory_chatbot.orchestrator.models import OrchestratorDecision
from inventory_chatbot.orchestrator.prompts import (
    ORCHESTRATOR_SYSTEM_PROMPT,
    build_orchestrator_context,
    build_orchestrator_user_prompt,
)


class LLMOrchestrator(Orchestrator):
    _DOMAIN_AGENTS = {"assets", "billing", "procurement", "sales"}

    def __init__(
        self,
        *,
        llm_client: LLMClient,
        today: date,
        customer_names: list[str],
        max_iterations: int = 3,
    ) -> None:
        self._llm_client = llm_client
        self._today = today
        self._customer_names = customer_names
        self._max_iterations = max(1, max_iterations)
        self._last_debug_trace: dict | None = None

    def decide(
        self, message: str, session_state: SessionState
    ) -> OrchestratorDecision | None:
        self._last_debug_trace = {
            "message": message,
            "max_iterations": self._max_iterations,
            "attempts": [],
            "status": "started",
        }
        schema_context = build_orchestrator_context(
            today=self._today,
            customer_names=self._customer_names,
        )
        session_history = self._format_session_history(session_state)
        prior_attempts: list[str] = []
        best_decision: OrchestratorDecision | None = None

        for iteration_index in range(1, self._max_iterations + 1):
            try:
                payload, _usage = self._llm_client.generate_structured_json(
                    system_prompt=ORCHESTRATOR_SYSTEM_PROMPT,
                    user_prompt=build_orchestrator_user_prompt(
                        user_message=message,
                        schema_context=schema_context,
                        session_history=session_history,
                        iteration_index=iteration_index,
                        max_iterations=self._max_iterations,
                        prior_attempts=prior_attempts,
                    ),
                )
            except LLMProviderError as exc:
                self._last_debug_trace["status"] = "provider_error"
                self._last_debug_trace["failed_iteration"] = iteration_index
                self._last_debug_trace["error"] = str(exc)
                self._last_debug_trace["best_decision"] = (
                    best_decision.model_dump(mode="json") if best_decision is not None else None
                )
                return self._finalize_best_effort(best_decision, message)

            if not isinstance(payload, dict):
                self._last_debug_trace["attempts"].append(
                    {
                        "iteration": iteration_index,
                        "status": "invalid_payload_type",
                        "payload_type": type(payload).__name__,
                    }
                )
                prior_attempts.append(
                    f"Attempt {iteration_index} returned a non-object response. Return the required JSON object."
                )
                continue

            try:
                decision = OrchestratorDecision.model_validate(payload)
            except ValidationError as exc:
                errors = exc.errors()
                self._last_debug_trace["attempts"].append(
                    {
                        "iteration": iteration_index,
                        "status": "validation_error",
                        "errors": errors,
                        "raw_payload": payload,
                    }
                )
                prior_attempts.append(
                    f"Attempt {iteration_index} returned invalid JSON shape. Fix the schema: {errors}"
                )
                continue

            best_decision = decision
            review_feedback = self._review_decision(message, decision)
            if review_feedback is None:
                self._last_debug_trace["attempts"].append(
                    {
                        "iteration": iteration_index,
                        "status": "accepted",
                        "decision": decision.model_dump(mode="json"),
                    }
                )
                self._last_debug_trace["status"] = "accepted"
                return self._finalize_best_effort(decision, message)

            self._last_debug_trace["attempts"].append(
                {
                    "iteration": iteration_index,
                    "status": "review_failed",
                    "decision": decision.model_dump(mode="json"),
                    "review_feedback": review_feedback,
                }
            )
            prior_attempts.append(
                self._summarize_attempt(
                    iteration_index=iteration_index,
                    decision=decision,
                    review_feedback=review_feedback,
                )
            )

        self._last_debug_trace["status"] = "max_iterations_reached"
        self._last_debug_trace["best_decision"] = (
            best_decision.model_dump(mode="json") if best_decision is not None else None
        )
        return self._finalize_best_effort(best_decision, message)

    def get_last_debug_trace(self) -> dict | None:
        return self._last_debug_trace

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

    def _review_decision(
        self, message: str, decision: OrchestratorDecision
    ) -> str | None:
        if decision.clarification_needed and not (decision.clarification_question or "").strip():
            return "Clarification is required, but clarification_question is empty."

        if decision.agent == "chat":
            if self._looks_like_data_request(message) and not self._looks_like_schema_request(message):
                return (
                    "This looks like a data retrieval or metric request. Reconsider whether a domain agent "
                    "should own it instead of chat."
                )
            if not decision.handoff_instructions.strip():
                return "Explain what the chat agent should do for the user."
            return None

        if decision.agent == "none":
            if self._looks_like_supported_domain_request(message):
                return (
                    "The request appears to be in scope for the dataset. Reconsider the chosen agent instead of none."
                )
            if not decision.analysis_summary.strip():
                return "Explain why the request is unsupported."
            return None

        if decision.agent in self._DOMAIN_AGENTS:
            missing_parts = []
            if not decision.user_need.strip():
                missing_parts.append("summarize the user need")
            if not decision.analysis_summary.strip():
                missing_parts.append("explain why this agent owns the request")
            if not decision.required_data:
                missing_parts.append("list the required tables and columns")
            elif not any(item.columns for item in decision.required_data):
                missing_parts.append("include the relevant columns for at least one required table")
            if not decision.handoff_instructions.strip():
                missing_parts.append("provide a concrete handoff for the next agent")
            if missing_parts:
                return "Please " + ", ".join(missing_parts) + "."
            return None

        return "Choose one of the supported agents: assets, billing, procurement, sales, chat, or none."

    @staticmethod
    def _summarize_attempt(
        *,
        iteration_index: int,
        decision: OrchestratorDecision,
        review_feedback: str,
    ) -> str:
        return (
            f"Attempt {iteration_index}: agent={decision.agent}, "
            f"user_need={decision.user_need or '[missing]'}, "
            f"analysis_summary={decision.analysis_summary or '[missing]'}, "
            f"required_data_count={len(decision.required_data)}, "
            f"handoff={decision.handoff_instructions or '[missing]'}. "
            f"Review feedback: {review_feedback}"
        )

    def _finalize_best_effort(
        self, decision: OrchestratorDecision | None, message: str
    ) -> OrchestratorDecision | None:
        if decision is None:
            return None

        updates: dict[str, object] = {}
        if not decision.user_need.strip():
            updates["user_need"] = message.strip()
        if not decision.analysis_summary.strip():
            updates["analysis_summary"] = self._default_analysis_summary(decision.agent)
        if not decision.handoff_instructions.strip():
            updates["handoff_instructions"] = self._default_handoff(decision.agent)
        if decision.clarification_needed and not (decision.clarification_question or "").strip():
            updates["clarification_question"] = (
                "Which exact metric, filter, or date range should I use for this request?"
            )
        if not updates:
            return decision
        return decision.model_copy(update=updates)

    @classmethod
    def _default_analysis_summary(cls, agent: str) -> str:
        summaries = {
            "assets": "This request belongs to the assets domain.",
            "billing": "This request belongs to the billing domain.",
            "procurement": "This request belongs to the procurement domain.",
            "sales": "This request belongs to the sales domain.",
            "chat": "This request is best handled as conversational schema or help guidance.",
            "none": "This request does not map to a supported workflow in the current dataset.",
        }
        return summaries.get(agent, "This request needs an orchestrator decision.")

    @classmethod
    def _default_handoff(cls, agent: str) -> str:
        handoffs = {
            "assets": "Use the assets-domain tables and return the requested asset result.",
            "billing": "Use the billing-domain tables and return the requested billing result.",
            "procurement": "Use the procurement-domain tables and return the requested procurement result.",
            "sales": "Use the sales-domain tables and return the requested sales result.",
            "chat": "Answer conversationally using the schema and session context without inventing data.",
            "none": "Explain that the current dataset does not support this request.",
        }
        return handoffs.get(agent, "Prepare the next step for the selected agent.")

    @staticmethod
    def _looks_like_data_request(message: str) -> bool:
        normalized = re.sub(r"\s+", " ", message.lower())
        phrases = (
            "how many",
            "count",
            "sum",
            "total",
            "average",
            "avg",
            "rows",
            "row",
            "records",
            "list",
            "show",
            "filter",
            "breakdown",
            "group by",
            "latest",
            "top",
        )
        return any(phrase in normalized for phrase in phrases)

    @staticmethod
    def _looks_like_supported_domain_request(message: str) -> bool:
        normalized = re.sub(r"\s+", " ", message.lower())
        keywords = (
            "asset",
            "site",
            "location",
            "item",
            "vendor",
            "bill",
            "invoice",
            "purchase order",
            "po ",
            "customer",
            "sales order",
        )
        return any(keyword in normalized for keyword in keywords)

    @staticmethod
    def _looks_like_schema_request(message: str) -> bool:
        normalized = re.sub(r"\s+", " ", message.lower())
        schema_terms = (
            "what tables",
            "which tables",
            "list tables",
            "show tables",
            "what columns",
            "which columns",
            "show columns",
            "schema",
            "relationship",
            "relationships",
        )
        return any(term in normalized for term in schema_terms)
