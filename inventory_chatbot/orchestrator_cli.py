from __future__ import annotations

import argparse
import json
import sys
from datetime import date

from inventory_chatbot.config import AppConfig, ConfigurationError
from inventory_chatbot.data.memory_repository import InMemoryRepository
from inventory_chatbot.llm.factory import build_llm_client
from inventory_chatbot.models.domain import SessionState
from inventory_chatbot.orchestrator.llm_based import LLMOrchestrator
from inventory_chatbot.orchestrator.prompts import (
    ORCHESTRATOR_SYSTEM_PROMPT,
    build_orchestrator_context,
    build_orchestrator_user_prompt,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the inventory orchestrator standalone for a single user message."
    )
    parser.add_argument("message", help="User message to route through the orchestrator.")
    parser.add_argument(
        "--session-id",
        default="orchestrator-debug",
        help="Session id used for the standalone run.",
    )
    parser.add_argument(
        "--show-prompt",
        action="store_true",
        help="Print the system prompt and the rendered user prompt before the decision.",
    )
    parser.add_argument(
        "--prompt-only",
        action="store_true",
        help="Print the system prompt and rendered user prompt, then exit without calling the model.",
    )
    parser.add_argument(
        "--show-context",
        action="store_true",
        help="Print only the generated schema context JSON and exit.",
    )
    parser.add_argument(
        "--max-iterations",
        type=int,
        default=3,
        help="Maximum bounded loop iterations for the orchestrator.",
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty-print the final JSON decision.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    repository = InMemoryRepository()
    customer_names = [customer["customer_name"] for customer in repository.list_customers()]
    resolved_today = date.today()
    context = build_orchestrator_context(
        today=resolved_today,
        customer_names=customer_names,
    )

    if args.show_context:
        print(context)
        return 0

    if args.show_prompt or args.prompt_only:
        print("=== SYSTEM PROMPT ===\n")
        print(ORCHESTRATOR_SYSTEM_PROMPT)
        print("\n=== USER PROMPT ===\n")
        print(
            build_orchestrator_user_prompt(
                user_message=args.message,
                schema_context=context,
                session_history="No prior conversation.",
                iteration_index=1,
                max_iterations=args.max_iterations,
            )
        )
        if args.prompt_only:
            return 0

    try:
        config = AppConfig.from_env()
        config.validate_provider_credentials()
    except ConfigurationError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 1

    llm_client = build_llm_client(config)
    orchestrator = LLMOrchestrator(
        llm_client=llm_client,
        today=resolved_today,
        customer_names=customer_names,
        max_iterations=args.max_iterations,
    )

    session_state = SessionState(session_id=args.session_id)
    if args.show_prompt:
        print("\n=== FINAL DECISION ===\n")

    decision = orchestrator.decide(args.message, session_state)
    if decision is None:
        print("null")
        return 2

    payload = decision.model_dump(mode="json")
    if args.pretty or args.show_prompt:
        print(json.dumps(payload, indent=2))
    else:
        print(json.dumps(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
