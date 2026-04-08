from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime

from inventory_chatbot.config import AppConfig, ConfigurationError
from inventory_chatbot.handoffs.service import OrchestratorHandoffService
from inventory_chatbot.llm.base import LLMProviderError
from inventory_chatbot.llm.factory import build_llm_client
from inventory_chatbot.models.api import TokenUsage
from inventory_chatbot.models.domain import AgentTask, SessionState
from inventory_chatbot.orchestrator.llm_based import LLMOrchestrator
from inventory_chatbot.query_makers.llm_based import LLMQueryMaker
from inventory_chatbot.runtime.backend_factory import build_data_backend_runtime
from inventory_chatbot.router.registry import SpecialistRegistry
from inventory_chatbot.services.date_parser import DateParser
from inventory_chatbot.specialists.assets import AssetSpecialist
from inventory_chatbot.specialists.billing import BillingSpecialist
from inventory_chatbot.specialists.procurement import ProcurementSpecialist
from inventory_chatbot.specialists.sales import SalesSpecialist
from inventory_chatbot.sql_execution.service import SQLExecutionServiceError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Trace data movement across orchestrator, planner, SQL, and final output."
    )
    parser.add_argument("message", help="User message to run through the traced pipeline.")
    parser.add_argument("--session-id", default="pipeline-trace", help="Session id for the trace run.")
    parser.add_argument(
        "--max-iterations",
        type=int,
        default=3,
        help="Maximum bounded loop iterations for the orchestrator.",
    )
    parser.add_argument(
        "--skip-answer",
        action="store_true",
        help="Skip the final natural-language answer generation step.",
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty-print the trace JSON.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        config = AppConfig.from_env()
        config.validate_provider_credentials()
        runtime = build_data_backend_runtime(config)
    except (ConfigurationError, RuntimeError, ValueError) as exc:
        print(f"Configuration/runtime error: {exc}", file=sys.stderr)
        return 1

    repository = runtime.repository
    resolved_today = date.today()
    date_parser = DateParser(today_provider=lambda: resolved_today)
    llm_client = build_llm_client(config)
    customer_names = [customer["customer_name"] for customer in repository.list_customers()]

    registry = SpecialistRegistry(
        [
            AssetSpecialist(repository, date_parser),
            BillingSpecialist(repository, date_parser),
            ProcurementSpecialist(repository),
            SalesSpecialist(repository, date_parser),
        ]
    )
    orchestrator = LLMOrchestrator(
        llm_client=llm_client,
        today=resolved_today,
        customer_names=customer_names,
        max_iterations=args.max_iterations,
    )
    query_maker = LLMQueryMaker(
        llm_client=llm_client,
        today=resolved_today,
        customer_names=customer_names,
        execution_service=runtime.sql_execution_service,
    )
    sql_execution_service = runtime.sql_execution_service
    handoff_service = OrchestratorHandoffService()
    session_state = SessionState(session_id=args.session_id)

    trace: dict[str, object] = {
        "message": args.message,
        "session_id": args.session_id,
        "path": None,
        "steps": {},
    }

    decision = orchestrator.decide(args.message, session_state)
    orchestrator_debug_trace = orchestrator.get_last_debug_trace()
    if orchestrator_debug_trace is not None:
        trace["steps"]["orchestrator_debug"] = orchestrator_debug_trace
    trace["steps"]["orchestrator_decision"] = (
        decision.model_dump(mode="json") if decision is not None else None
    )
    if decision is None:
        trace["path"] = "orchestrator_failed"
        return _print_trace(trace, args.pretty, 2)

    if decision.clarification_needed:
        trace["path"] = "clarification"
        return _print_trace(trace, args.pretty, 0)

    if decision.agent in {"chat", "none"}:
        trace["path"] = decision.agent
        return _print_trace(trace, args.pretty, 0)

    specialist_activation = handoff_service.build_specialist_activation(decision)
    trace["steps"]["specialist_activation"] = specialist_activation.model_dump(mode="json")

    specialist = registry.get(specialist_activation.agent_name)
    if specialist is None:
        trace["path"] = "missing_specialist"
        return _print_trace(trace, args.pretty, 3)

    specialist_task = AgentTask(
        request_id=f"{args.session_id}:1:{specialist_activation.agent_name}",
        user_message=args.message,
        target_agent=specialist_activation.agent_name,
        instructions=specialist_activation.instructions,
        context=specialist_activation.context,
    )
    specialist_reply = specialist.handle_task(specialist_task, session_state)
    trace["steps"]["specialist_reply"] = specialist_reply.model_dump(mode="json")

    if specialist_reply.status == "ok":
        trace["path"] = "specialist"
        if not args.skip_answer and specialist_reply.computed_result is not None:
            answer, usage = _generate_answer(llm_client, args.message, specialist_reply.computed_result)
            trace["steps"]["final_answer"] = {
                "answer": answer,
                "usage": usage.model_dump(mode="json"),
            }
        return _print_trace(trace, args.pretty, 0)

    if specialist_reply.status == "needs_clarification":
        trace["path"] = "specialist_clarification"
        return _print_trace(trace, args.pretty, 0)

    planner_activation = handoff_service.build_planner_activation(decision)
    trace["steps"]["planner_activation"] = planner_activation.model_dump(mode="json")

    sql_agent_decision = query_maker.decide(
        args.message,
        session_state,
        planner_activation,
    )
    sql_agent_debug_trace = query_maker.get_last_debug_trace()
    if sql_agent_debug_trace is not None:
        trace["steps"]["sql_agent_debug"] = sql_agent_debug_trace
    trace["steps"]["sql_agent_decision"] = (
        sql_agent_decision.model_dump(mode="json") if sql_agent_decision else None
    )
    if sql_agent_decision is None:
        trace["path"] = "planner_failed"
        return _print_trace(trace, args.pretty, 4)
    if sql_agent_decision.action == "clarify":
        trace["path"] = "sql_agent_clarification"
        return _print_trace(trace, args.pretty, 0)
    if sql_agent_decision.action == "unsupported":
        trace["path"] = "sql_agent_unsupported"
        return _print_trace(trace, args.pretty, 0)

    try:
        execution_request = handoff_service.build_execution_request(
            user_message=args.message,
            orchestrator_decision=decision,
            sql_agent_decision=sql_agent_decision,
        )
    except ValueError as exc:
        trace["path"] = "handoff_failed"
        trace["steps"]["handoff_error"] = {"message": str(exc)}
        return _print_trace(trace, args.pretty, 6)
    trace["steps"]["execution_request"] = execution_request.model_dump(mode="json")

    try:
        sql_preview = sql_execution_service.preview_sql(execution_request)
        computed_result, sql_query = sql_execution_service.execute(execution_request)
    except SQLExecutionServiceError as exc:
        trace["path"] = "sql_execution_failed"
        trace["steps"]["sql_execution_error"] = {"message": str(exc)}
        return _print_trace(trace, args.pretty, 5)

    trace["path"] = "sql_agent_to_execution"
    trace["steps"]["sql_output"] = {
        "sql_preview": sql_preview,
        "sql_query": sql_query,
        "result_preview": computed_result.answer_context,
        "fallback_answer": computed_result.fallback_answer,
    }
    if not args.skip_answer:
        answer, usage = _generate_answer(llm_client, args.message, computed_result)
        trace["steps"]["final_answer"] = {
            "answer": answer,
            "usage": usage.model_dump(mode="json"),
        }
    return _print_trace(trace, args.pretty, 0)


def _generate_answer(llm_client, user_message, computed_result) -> tuple[str, TokenUsage]:
    try:
        return llm_client.generate_answer(
            user_message=user_message,
            result=computed_result,
        )
    except LLMProviderError as exc:
        return f"Unable to contact the configured AI provider: {exc}", TokenUsage()


def _print_trace(trace: dict[str, object], pretty: bool, exit_code: int) -> int:
    if pretty:
        print(json.dumps(trace, indent=2, default=_json_default))
    else:
        print(json.dumps(trace, default=_json_default))
    return exit_code


def _json_default(value: object) -> str:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return str(value)


if __name__ == "__main__":
    raise SystemExit(main())
