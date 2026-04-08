from __future__ import annotations

from datetime import date

from inventory_chatbot.llm.base import LLMClient, LLMProviderError
from inventory_chatbot.models.api import TokenUsage
from inventory_chatbot.models.domain import ComputedResult

FIXED_TODAY = date(2026, 4, 7)


class FakeLLMClient(LLMClient):
    def generate_answer(
        self, *, user_message: str, result: ComputedResult
    ) -> tuple[str, TokenUsage]:
        return (
            f"AI summary: {result.fallback_answer}",
            TokenUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
        )

    def generate_structured_json(
        self, *, system_prompt: str, user_prompt: str
    ) -> tuple[dict | None, TokenUsage]:
        question = self._extract_user_question(user_prompt)
        normalized = " ".join(question.lower().split())
        lowered_prompt = user_prompt.lower()
        if "orchestrator agent" in system_prompt.lower():
            if (
                normalized in {"hi", "hello", "hey"}
                or "what are the tables" in normalized
                or ("table" in normalized and ("what" in normalized or "which" in normalized))
                or "what columns are in customers" in normalized
            ):
                return (
                    self._decision(
                        agent="chat",
                        user_need="Explain the schema or help the user navigate the dataset.",
                        analysis_summary="This is a schema-help request, so it belongs to the chat agent.",
                        handoff_instructions="Explain the available tables, columns, or relationships conversationally.",
                    ),
                    TokenUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
                )
            if "asset" in normalized:
                return (
                    self._decision(
                        agent="assets",
                        user_need="Analyze or retrieve asset-related data.",
                        analysis_summary="This request belongs to the assets domain.",
                        required_data=[
                            self._required_data(
                                "Assets",
                                ["AssetId", "Status", "SiteId"],
                                "Asset facts and asset status are needed for the result.",
                            )
                        ],
                        handoff_instructions="Use asset-domain tables and compute the requested asset result.",
                    ),
                    TokenUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
                )
            if "invoice" in normalized or "bill" in normalized:
                return (
                    self._decision(
                        agent="billing",
                        user_need="Analyze billing or invoice data.",
                        analysis_summary="This request belongs to the billing domain.",
                        required_data=[
                            self._required_data(
                                "Bills",
                                ["BillId", "VendorId", "BillDate", "TotalAmount", "Status"],
                                "Bill amounts and dates are needed for billing analysis.",
                            )
                        ],
                        handoff_instructions="Build a billing-focused aggregate or row query for the request.",
                    ),
                    TokenUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
                )
            if "purchase order" in normalized or " po " in f" {normalized} ":
                return (
                    self._decision(
                        agent="procurement",
                        user_need="Analyze purchase order data.",
                        analysis_summary="This request belongs to the procurement domain.",
                        required_data=[
                            self._required_data(
                                "PurchaseOrders",
                                ["POId", "Status", "VendorId", "SiteId"],
                                "Purchase order status and ownership are needed for the result.",
                            )
                        ],
                        handoff_instructions="Use purchase-order data and return the requested procurement result.",
                    ),
                    TokenUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
                )
            if "customers" in normalized or "customer" in normalized:
                return (
                    self._decision(
                        agent="sales",
                        user_need="Analyze customer or sales data.",
                        analysis_summary="Customer data belongs to the sales domain.",
                        required_data=[
                            self._required_data(
                                "Customers",
                                ["CustomerId", "CustomerName"],
                                "Customer identity is needed for the requested result.",
                            )
                        ],
                        handoff_instructions="Use sales-domain tables and customer context to answer the request.",
                    ),
                    TokenUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
                )
            if "sales order" in normalized or (
                "bright retail" in normalized and "sales orders were created for acme corp last month" in lowered_prompt
            ):
                return (
                    self._decision(
                        agent="sales",
                        user_need="Count or inspect sales orders for a customer.",
                        analysis_summary="This request belongs to the sales domain.",
                        required_data=[
                            self._required_data(
                                "SalesOrders",
                                ["SOId", "CustomerId", "SODate"],
                                "Sales order facts are required to answer the request.",
                            ),
                            self._required_data(
                                "Customers",
                                ["CustomerId", "CustomerName"],
                                "Customer names are needed to filter the sales orders.",
                            ),
                        ],
                        handoff_instructions="Count sales orders for the named customer in the requested period.",
                    ),
                    TokenUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
                )
            if "by site" in normalized and "how many assets do i have" in lowered_prompt:
                return (
                    self._decision(
                        agent="assets",
                        user_need="Break down asset counts by site.",
                        analysis_summary="The follow-up needs assets joined to sites for a grouped count.",
                        required_data=[
                            self._required_data(
                                "Assets",
                                ["AssetId", "Status", "SiteId"],
                                "Assets provide the counted records and site link.",
                            ),
                            self._required_data(
                                "Sites",
                                ["SiteId", "SiteName"],
                                "Sites provide the grouping label.",
                            ),
                        ],
                        handoff_instructions="Group active assets by site and return the count per site.",
                    ),
                    TokenUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
                )
            return (
                self._decision(
                    agent="chat",
                    user_need="Provide conversational guidance.",
                    analysis_summary="The request does not clearly map to a data retrieval agent.",
                    handoff_instructions="Answer conversationally without inventing data.",
                ),
                TokenUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
            )

        if "assets query-maker agent" in system_prompt.lower() and (
            "assets by site" in normalized or "by site" in normalized
        ):
            return (
                {
                    "base_table": "Assets",
                    "selects": [{"column": "Sites.SiteName", "alias": "SiteName"}],
                    "aggregates": [
                        {
                            "function": "COUNT",
                            "column": "Assets.AssetId",
                            "alias": "AssetCount",
                        }
                    ],
                    "joins": [{"left": "Assets.SiteId", "right": "Sites.SiteId"}],
                    "filters": [
                        {
                            "column": "Assets.Status",
                            "operator": "<>",
                            "value": "Disposed",
                        }
                    ],
                    "group_by": ["Sites.SiteName"],
                    "order_by": [{"expression": "AssetCount", "direction": "DESC"}],
                },
                TokenUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
            )

        if "assets query-maker agent" in system_prompt.lower() and "how many assets do i have" in normalized:
            return (
                {
                    "base_table": "Assets",
                    "aggregates": [
                        {
                            "function": "COUNT",
                            "column": "Assets.AssetId",
                            "alias": "AssetCount",
                        }
                    ],
                    "filters": [
                        {
                            "column": "Assets.Status",
                            "operator": "<>",
                            "value": "Disposed",
                        }
                    ],
                },
                TokenUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
            )

        if "billing query-maker agent" in system_prompt.lower() and "invoice amount by vendor for last quarter" in normalized:
            return (
                {
                    "base_table": "Bills",
                    "selects": [{"column": "Vendors.VendorName", "alias": "VendorName"}],
                    "aggregates": [
                        {
                            "function": "SUM",
                            "column": "Bills.TotalAmount",
                            "alias": "TotalBilled",
                        }
                    ],
                    "joins": [{"left": "Bills.VendorId", "right": "Vendors.VendorId"}],
                    "filters": [
                        {
                            "column": "Bills.Status",
                            "operator": "<>",
                            "value": "Void",
                        },
                        {
                            "column": "Bills.BillDate",
                            "operator": "BETWEEN",
                            "value": ["2026-01-01", "2026-03-31"],
                        },
                    ],
                    "group_by": ["Vendors.VendorName"],
                    "order_by": [{"expression": "TotalBilled", "direction": "DESC"}],
                },
                TokenUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
            )

        if "billing query-maker agent" in system_prompt.lower() and "total billed amount" in normalized:
            return (
                {
                    "base_table": "Bills",
                    "aggregates": [
                        {
                            "function": "SUM",
                            "column": "Bills.TotalAmount",
                            "alias": "TotalBilledAmount",
                        }
                    ],
                    "filters": [
                        {
                            "column": "Bills.Status",
                            "operator": "<>",
                            "value": "Void",
                        },
                        {
                            "column": "Bills.BillDate",
                            "operator": "BETWEEN",
                            "value": ["2026-01-01", "2026-03-31"],
                        },
                    ],
                },
                TokenUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
            )

        if "procurement query-maker agent" in system_prompt.lower() and "purchase order" in normalized:
            return (
                {
                    "base_table": "PurchaseOrders",
                    "aggregates": [
                        {
                            "function": "COUNT",
                            "column": "PurchaseOrders.POId",
                            "alias": "OpenPurchaseOrderCount",
                        }
                    ],
                    "filters": [
                        {
                            "column": "PurchaseOrders.Status",
                            "operator": "=",
                            "value": "Open",
                        }
                    ],
                },
                TokenUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
            )

        if "sales query-maker agent" in system_prompt.lower() and (
            "sales orders were created for acme corp last month" in normalized
            or (
                "bright retail" in normalized and "sales orders were created for acme corp last month" in lowered_prompt
            )
        ):
            return (
                {
                    "base_table": "SalesOrders",
                    "aggregates": [
                        {
                            "function": "COUNT",
                            "column": "SalesOrders.SOId",
                            "alias": "SalesOrderCount",
                        }
                    ],
                    "joins": [{"left": "SalesOrders.CustomerId", "right": "Customers.CustomerId"}],
                    "filters": [
                        {
                            "column": "Customers.CustomerName",
                            "operator": "=",
                            "value": "Bright Retail" if "bright retail" in normalized else "Acme Corp",
                        },
                        {
                            "column": "SalesOrders.SODate",
                            "operator": "BETWEEN",
                            "value": ["2026-03-01", "2026-03-31"],
                        },
                    ],
                },
                TokenUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
            )

        if "sales query-maker agent" in system_prompt.lower() and (
            "first 5 rows of customers table" in normalized or "first row in customers" in normalized
        ):
            limit = 1 if "first row" in normalized else 5
            return (
                {
                    "base_table": "Customers",
                    "selects": [
                        {"column": "Customers.CustomerId", "alias": "CustomerId"},
                        {"column": "Customers.CustomerCode", "alias": "CustomerCode"},
                        {"column": "Customers.CustomerName", "alias": "CustomerName"},
                        {"column": "Customers.Email", "alias": "Email"},
                        {"column": "Customers.Phone", "alias": "Phone"},
                        {"column": "Customers.BillingAddress1", "alias": "BillingAddress1"},
                        {"column": "Customers.BillingCity", "alias": "BillingCity"},
                        {"column": "Customers.BillingCountry", "alias": "BillingCountry"},
                        {"column": "Customers.CreatedAt", "alias": "CreatedAt"},
                        {"column": "Customers.IsActive", "alias": "IsActive"},
                    ],
                    "aggregates": [],
                    "joins": [],
                    "filters": [],
                    "group_by": [],
                    "order_by": [{"expression": "Customers.CustomerId", "direction": "ASC"}],
                    "limit": limit,
                },
                TokenUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
            )

        return None, TokenUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15)

    def generate_text(
        self, *, system_prompt: str, user_prompt: str
    ) -> tuple[str, TokenUsage]:
        question = self._extract_user_question(user_prompt).lower().strip()
        if question in {"hi", "hello", "hey"}:
            return (
                "Hello. I can help you explore the inventory data, inspect the schema, and answer questions about the data.",
                TokenUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
            )
        if "what are the tables" in question or ("table" in question and "have" in question):
            return (
                "We currently have these tables: Customers, Vendors, Sites, Locations, Items, Assets, Bills, PurchaseOrders, PurchaseOrderLines, SalesOrders, SalesOrderLines, and AssetTransactions.",
                TokenUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
            )
        if "what columns" in question and "assets" in question:
            return (
                "The columns in Assets are AssetId, AssetTag, AssetName, SiteId, LocationId, SerialNumber, Category, Status, Cost, PurchaseDate, VendorId, CreatedAt, and UpdatedAt.",
                TokenUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
            )
        return (
            "I can help you inspect the schema or ask questions about the inventory data. Try asking what tables we have or ask a business question.",
            TokenUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
        )

    @staticmethod
    def _extract_user_question(user_prompt: str) -> str:
        prefix = "User question:"
        for line in user_prompt.splitlines():
            if line.startswith(prefix):
                return line[len(prefix) :].strip()
        return user_prompt

    @staticmethod
    def _required_data(table: str, columns: list[str], reason: str) -> dict:
        return {
            "table": table,
            "columns": columns,
            "reason": reason,
        }

    @staticmethod
    def _decision(
        *,
        agent: str,
        user_need: str,
        analysis_summary: str,
        handoff_instructions: str,
        required_data: list[dict] | None = None,
        clarification_needed: bool = False,
        clarification_question: str | None = None,
    ) -> dict:
        return {
            "agent": agent,
            "user_need": user_need,
            "analysis_summary": analysis_summary,
            "required_data": required_data or [],
            "handoff_instructions": handoff_instructions,
            "clarification_needed": clarification_needed,
            "clarification_question": clarification_question,
        }


class FailingLLMClient(LLMClient):
    def generate_answer(
        self, *, user_message: str, result: ComputedResult
    ) -> tuple[str, TokenUsage]:
        raise LLMProviderError("boom")

    def generate_structured_json(
        self, *, system_prompt: str, user_prompt: str
    ) -> tuple[dict | None, TokenUsage]:
        return FakeLLMClient().generate_structured_json(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        )

    def generate_text(
        self, *, system_prompt: str, user_prompt: str
    ) -> tuple[str, TokenUsage]:
        raise LLMProviderError("boom")


class StructuredFailingLLMClient(LLMClient):
    def generate_answer(
        self, *, user_message: str, result: ComputedResult
    ) -> tuple[str, TokenUsage]:
        raise LLMProviderError("structured boom")

    def generate_structured_json(
        self, *, system_prompt: str, user_prompt: str
    ) -> tuple[dict | None, TokenUsage]:
        raise LLMProviderError("structured boom")

    def generate_text(
        self, *, system_prompt: str, user_prompt: str
    ) -> tuple[str, TokenUsage]:
        raise LLMProviderError("structured boom")


class LoopingOrchestratorLLMClient(FakeLLMClient):
    def __init__(self) -> None:
        self.orchestrator_calls = 0

    def generate_structured_json(
        self, *, system_prompt: str, user_prompt: str
    ) -> tuple[dict | None, TokenUsage]:
        if "orchestrator agent" in system_prompt.lower():
            self.orchestrator_calls += 1
            if self.orchestrator_calls == 1:
                return (
                    self._decision(
                        agent="chat",
                        user_need="",
                        analysis_summary="",
                        handoff_instructions="",
                    ),
                    TokenUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
                )
            return (
                self._decision(
                    agent="assets",
                    user_need="Count assets by site.",
                    analysis_summary="This is a metric request over the assets domain.",
                    required_data=[
                        self._required_data(
                            "Assets",
                            ["AssetId", "Status", "SiteId"],
                            "Assets provide the counted records and site reference.",
                        ),
                        self._required_data(
                            "Sites",
                            ["SiteId", "SiteName"],
                            "Sites provide the grouping label for the result.",
                        ),
                    ],
                    handoff_instructions="Group active assets by site and return the count per site.",
                ),
                TokenUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
            )
        return super().generate_structured_json(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        )
