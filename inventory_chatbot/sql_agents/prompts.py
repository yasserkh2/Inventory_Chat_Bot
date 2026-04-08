from __future__ import annotations

import json
from datetime import date

from inventory_chatbot.dynamic_sql.schema_catalog import SCHEMA_CATALOG
from inventory_chatbot.orchestrator.metadata import TABLE_DESCRIPTIONS, describe_column
from inventory_chatbot.sql_agents.metadata import SQL_AGENT_METADATA


def build_sql_agent_context(*, agent_name: str, today: date, customer_names: list[str]) -> str:
    metadata = SQL_AGENT_METADATA[agent_name]
    tables = metadata["tables"]
    schema_summary = {}
    for table_name in tables:
        table = SCHEMA_CATALOG[table_name]
        primary_key = table["primary_key"]
        joins = table["joins"]
        schema_summary[table_name] = {
            "description": TABLE_DESCRIPTIONS.get(table_name, ""),
            "primary_key": primary_key,
            "columns": {
                column_name: {
                    "type": column_type,
                    "description": describe_column(
                        table_name=table_name,
                        column_name=column_name,
                        primary_key=primary_key,
                        joins=joins,
                    ),
                }
                for column_name, column_type in table["columns"].items()
            },
            "joins": {
                column: {"table": target[0], "column": target[1]}
                for column, target in joins.items()
            },
        }
    payload = {
        "today": today.isoformat(),
        "customers": customer_names,
        "agent": {
            "name": agent_name,
            "role": metadata["role"],
            "tables": tables,
            "capabilities": metadata["capabilities"],
        },
        "schema": schema_summary,
    }
    return json.dumps(payload, indent=2)


def build_sql_agent_system_prompt(agent_name: str) -> str:
    return (
        f"You are the {agent_name} query-maker agent. "
        "You are a SQL-planning agent operating in a short bounded reasoning loop. "
        "Analyze the user's need, identify the exact tables and columns required, decide whether you can "
        "execute now or need clarification, and only produce an executable SQL query when it is safe to do so. "
        "Think step by step internally, but return JSON only. "
        "Return exactly this shape: "
        "{\"agent_name\":\"assets|billing|procurement|sales\","
        "\"action\":\"execute|clarify|unsupported\","
        "\"user_need\":\"...\","
        "\"analysis_summary\":\"...\","
        "\"required_data\":[{\"table\":\"...\",\"columns\":[\"...\"],\"reason\":\"...\"}],"
        "\"query_strategy\":\"...\","
        "\"sql_query\":\"SELECT ...\"|null,"
        "\"query_plan\":null,"
        "\"clarification_question\":null,"
        "\"unsupported_reason\":null}."
    )


def build_sql_agent_user_prompt(
    *,
    agent_name: str,
    user_message: str,
    schema_context: str,
    session_history: str,
    orchestrator_handoff: str,
    activation_context: dict | None = None,
    iteration_index: int = 1,
    max_iterations: int = 1,
    prior_attempts: list[str] | None = None,
) -> str:
    prior_attempts = prior_attempts or []
    activation_section = (
        "Activation context:\n" + json.dumps(activation_context, indent=2) + "\n"
        if activation_context
        else ""
    )
    review_section = (
        "Previous SQL-agent attempts and review feedback:\n"
        + "\n".join(f"- {attempt}" for attempt in prior_attempts)
        + "\n"
        if prior_attempts
        else ""
    )
    return (
        f"User question: {user_message}\n"
        f"Recent session history:\n{session_history}\n"
        f"Orchestrator handoff:\n{orchestrator_handoff}\n"
        f"Iteration: {iteration_index} of {max_iterations}\n"
        f"{activation_section}"
        "Work in this order:\n"
        "1. Identify what the user is asking for.\n"
        "2. Identify the exact tables and columns needed.\n"
        "3. Decide whether you can execute now, need clarification, or must reject as unsupported.\n"
        "4. If executable, build one SQL SELECT query that will be reviewed before execution.\n"
        "5. Only choose action=execute when the SQL is domain-safe and ready for review.\n"
        f"{review_section}"
        "The schema context below includes:\n"
        "- the tables this agent is responsible for\n"
        "- the schema of those tables\n"
        "- an explanation of every column in those tables\n"
        "- this agent's capabilities and execution boundaries\n"
        f"Schema context:\n{schema_context}\n"
        "Rules:\n"
        f"- Stay inside the {agent_name} agent domain.\n"
        "- Use only schema-valid tables, columns, and joins.\n"
        "- Return sql_query as a single SELECT statement using canonical table names and canonical column names.\n"
        "- Do not use table aliases. Use full names like Bills.TotalAmount and Vendors.VendorName.\n"
        "- For row inspection requests, include explicit columns, deterministic ORDER BY, and TOP N when needed.\n"
        "- For aggregate requests, include the needed joins, filters, GROUP BY values, and ORDER BY when useful.\n"
        "- Keep query_plan as null. The review layer will normalize the SQL into the internal execution plan.\n"
        "- If a required business filter is missing, choose action=clarify and ask one concise question.\n"
        "- If the request does not belong to your domain, choose action=unsupported.\n"
        "- If previous review feedback is present, fix those issues in this pass instead of repeating the same draft.\n"
        "- Do not output prose outside the JSON object.\n"
    )
