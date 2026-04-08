from __future__ import annotations

import json
from datetime import date

from inventory_chatbot.dynamic_sql.schema_catalog import SCHEMA_CATALOG
from inventory_chatbot.orchestrator.metadata import (
    AGENT_RESPONSIBILITIES,
    TABLE_DESCRIPTIONS,
    describe_column,
    describe_column_value_hints,
)


def build_orchestrator_context(*, today: date, customer_names: list[str]) -> str:
    schema_summary = {}
    for table_name, table in SCHEMA_CATALOG.items():
        primary_key = table["primary_key"]
        joins = table["joins"]
        schema_summary[table_name] = {
            "description": TABLE_DESCRIPTIONS.get(table_name, ""),
            "primary_key": primary_key,
            "columns": {
                column_name: _build_column_metadata(
                    table_name=table_name,
                    column_name=column_name,
                    column_type=column_type,
                    primary_key=primary_key,
                    joins=joins,
                )
                for column_name, column_type in table["columns"].items()
            },
            "joins": {
                column: {"table": target[0], "column": target[1]}
                for column, target in joins.items()
            },
        }
    prompt_context = {
        "today": today.isoformat(),
        "customers": customer_names,
        "agents": AGENT_RESPONSIBILITIES,
        "schema": schema_summary,
    }
    return json.dumps(prompt_context, indent=2)


ORCHESTRATOR_SYSTEM_PROMPT = (
    "You are the orchestrator agent for an inventory data copilot. "
    "Analyze the user's need, identify the required tables and columns, choose the right next agent, "
    "and prepare a precise handoff. You may be called in a short bounded reasoning loop, and each pass "
    "should improve the decision by fixing missing data requirements, weak handoff instructions, or an "
    "incorrect agent choice. Think step by step internally, but return JSON only. "
    "Return exactly this shape: "
    "{\"agent\":\"assets|billing|procurement|sales|chat|none\","
    "\"user_need\":\"...\","
    "\"analysis_summary\":\"...\","
    "\"required_data\":[{\"table\":\"...\",\"columns\":[\"...\"],\"reason\":\"...\"}],"
    "\"handoff_instructions\":\"...\","
    "\"clarification_needed\":false,"
    "\"clarification_question\":null}."
)


def build_orchestrator_user_prompt(
    *,
    user_message: str,
    schema_context: str,
    session_history: str,
    iteration_index: int = 1,
    max_iterations: int = 1,
    prior_attempts: list[str] | None = None,
) -> str:
    prior_attempts = prior_attempts or []
    review_section = (
        "Previous orchestration attempts and review feedback:\n"
        + "\n".join(f"- {attempt}" for attempt in prior_attempts)
        + "\n"
        if prior_attempts
        else ""
    )
    return (
        f"User question: {user_message}\n"
        f"Recent session history:\n{session_history}\n"
        f"Iteration: {iteration_index} of {max_iterations}\n"
        "You are routing this request for a multi-agent inventory assistant.\n"
        "Analyze it in this order:\n"
        "1. Understand the business need.\n"
        "2. Determine which tables and columns are needed.\n"
        "3. Choose the owning agent.\n"
        "4. Prepare a useful handoff for that agent.\n"
        f"{review_section}"
        "The schema context below includes:\n"
        "- the role of each agent\n"
        "- the tables each agent is responsible for\n"
        "- the full dataset schema\n"
        "- an explanation of every table\n"
        "- an explanation of every column in every table\n"
        f"Schema context:\n{schema_context}\n"
        "Routing rules:\n"
        "- Route to assets for Assets, Sites, Locations, Items, and AssetTransactions questions.\n"
        "- Route to billing for Bills and vendor billing or invoice questions.\n"
        "- Route to procurement for PurchaseOrders and PurchaseOrderLines questions.\n"
        "- Route to sales for SalesOrders, SalesOrderLines, and Customers questions.\n"
        "- Translate business words to canonical schema references in required_data and handoff instructions (example: currency -> Bills.Currency).\n"
        "- Resolve metric words before handoff: count/how many -> COUNT, total cost/value/amount -> SUM on the matching monetary column, average -> AVG.\n"
        "- If user metric is explicit, preserve it in handoff instructions and do not swap it for another metric.\n"
        "- Never treat a column name as a table name.\n"
        "- Route greetings, schema explanations, table discovery, column discovery, and relationship explanations to chat.\n"
        "- If the user asks to retrieve rows, inspect records, list data, or compute a metric, do not choose chat.\n"
        "- If the query is vague (missing metric target, entity, or date/filter context), set clarification_needed to true and ask one concise question.\n"
        "- If previous review feedback is present, fix those issues in this pass instead of repeating the same draft.\n"
        "- If unsupported, return agent as none.\n"
    )


def _build_column_metadata(
    *,
    table_name: str,
    column_name: str,
    column_type: str,
    primary_key: str,
    joins: dict[str, tuple[str, str]],
) -> dict[str, object]:
    payload: dict[str, object] = {
        "type": column_type,
        "description": describe_column(
            table_name=table_name,
            column_name=column_name,
            primary_key=primary_key,
            joins=joins,
        ),
    }
    value_hints = describe_column_value_hints(table_name=table_name, column_name=column_name)
    if value_hints:
        payload["value_hints"] = value_hints
    return payload
