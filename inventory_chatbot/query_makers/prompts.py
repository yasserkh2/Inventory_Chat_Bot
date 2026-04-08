from __future__ import annotations

import json
from datetime import date

from inventory_chatbot.dynamic_sql.schema_catalog import SCHEMA_CATALOG


def build_schema_context(*, today: date, customer_names: list[str]) -> str:
    schema_summary = {
        table_name: {
            "columns": list(table["columns"].keys()),
            "joins": {
                column: {"table": target[0], "column": target[1]}
                for column, target in table["joins"].items()
            },
        }
        for table_name, table in SCHEMA_CATALOG.items()
    }
    prompt_context = {
        "today": today.isoformat(),
        "customers": customer_names,
        "schema": schema_summary,
    }
    return json.dumps(prompt_context, indent=2)


ASSETS_SYSTEM_PROMPT = (
    "You are the assets query-maker agent. "
    "Your domain includes Assets, Sites, Locations, Items, and AssetTransactions. "
    "Return only valid JSON for a QueryPlan or null."
)


BILLING_SYSTEM_PROMPT = (
    "You are the billing query-maker agent. "
    "Your domain includes Bills and vendor billing/invoice analysis. "
    "Return only valid JSON for a QueryPlan or null."
)


PROCUREMENT_SYSTEM_PROMPT = (
    "You are the procurement query-maker agent. "
    "Your domain includes PurchaseOrders and PurchaseOrderLines. "
    "Return only valid JSON for a QueryPlan or null."
)


SALES_SYSTEM_PROMPT = (
    "You are the sales query-maker agent. "
    "Your domain includes SalesOrders, SalesOrderLines, and Customers. "
    "Return only valid JSON for a QueryPlan or null."
)


def build_planner_user_prompt(
    *,
    user_message: str,
    schema_context: str,
    domain: str,
    orchestrator_handoff: str | None = None,
) -> str:
    handoff_section = (
        f"Orchestrator handoff:\n{orchestrator_handoff}\n" if orchestrator_handoff else ""
    )
    return (
        f"User question: {user_message}\n"
        f"{handoff_section}"
        f"Recent session history:\n{{session_history}}\n"
        f"Schema context:\n{schema_context}\n"
        f"You are planning only for the {domain} domain. "
        "Use only schema-valid tables, columns, and joins. "
        "You may build plans for aggregation questions and also raw data inspection questions such as showing rows, first row, latest records, listing records, or returning selected columns from a table in your domain. "
        "When the user asks for the first row or a sample row, create a non-aggregate QueryPlan with explicit selects, a deterministic order_by using the primary key ascending, and limit 1. "
        "When the user asks for the first N rows, create a non-aggregate QueryPlan with explicit selects, a deterministic order_by using the primary key ascending, and limit N. "
        "When the user asks for records from a table, prefer the most relevant table in your domain even if the wording is informal. "
        "For raw row requests, select the real columns of the target table rather than answering conversationally. "
        f"Examples for {domain}:\n"
        + _domain_examples(domain)
        +
        "Return a JSON object with keys base_table, selects, aggregates, joins, filters, group_by, order_by, and optional limit. "
        "Use ISO date strings for date values. "
        "Return null if the question does not belong to your domain."
    )


CHAT_SYSTEM_PROMPT = (
    "You are a helpful inventory data copilot. "
    "Answer conversationally using the schema context and recent session history. "
    "If the user asks about the data model, explain the tables and relationships clearly. "
    "If they ask for help, suggest questions they can ask about the data. "
    "Do not answer with guessed data results when the user is asking to retrieve rows, calculate metrics, or inspect records from the data."
)


def build_chat_user_prompt(*, user_message: str, schema_context: str, session_history: str) -> str:
    return (
        f"User question: {user_message}\n"
        f"Recent session history:\n{session_history}\n"
        f"Schema context:\n{schema_context}\n"
        "Answer naturally. Do not invent query results. "
        "If the user asks about tables or columns, answer directly from the schema. "
        "If the user asks to show rows, records, first rows, list data, totals, counts, or metrics from the data, do not answer conversationally; that should be handled by a query agent."
    )


def _domain_examples(domain: str) -> str:
    examples = {
        "assets": (
            '- "show the first 5 rows of assets" -> use base_table Assets with explicit selects, order_by Assets.AssetId ASC, limit 5.\n'
            '- "what is the total value of assets per site?" -> use Assets joined to Sites with SUM(Assets.Cost) grouped by Sites.SiteName.\n'
        ),
        "billing": (
            '- "show the first 5 bills" -> use base_table Bills with explicit selects, order_by Bills.BillId ASC, limit 5.\n'
            '- "total invoice amount by vendor for last quarter" -> use Bills joined to Vendors with SUM(Bills.TotalAmount).\n'
        ),
        "procurement": (
            '- "show the first 5 purchase orders" -> use base_table PurchaseOrders with explicit selects, order_by PurchaseOrders.POId ASC, limit 5.\n'
            '- "count open purchase orders" -> use COUNT on PurchaseOrders filtered by Status = Open.\n'
        ),
        "sales": (
            '- "show me the first 5 rows of customers table" -> use base_table Customers with explicit selects of Customers columns, order_by Customers.CustomerId ASC, limit 5.\n'
            '- "show the first row in customers" -> use base_table Customers with explicit selects of Customers columns, order_by Customers.CustomerId ASC, limit 1.\n'
            '- "how many sales orders were created for Acme Corp last month?" -> use SalesOrders joined to Customers with COUNT.\n'
        ),
    }
    return examples.get(domain, "")
