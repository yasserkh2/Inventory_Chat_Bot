from __future__ import annotations

from inventory_chatbot.data.interfaces import SalesReadRepository
from inventory_chatbot.models.domain import ComputedResult, MatchResult, QueryPlan, SessionState
from inventory_chatbot.queries.templates import render_sql
from inventory_chatbot.services.date_parser import DateParser
from inventory_chatbot.specialists.base import Specialist


class SalesSpecialist(Specialist):
    name = "sales"

    def __init__(
        self, repository: SalesReadRepository, date_parser: DateParser
    ) -> None:
        self._repository = repository
        self._date_parser = date_parser

    def match(self, message: str, session_state: SessionState) -> MatchResult | None:
        normalized = self.normalize_text(message)
        customer_names = [
            customer["customer_name"] for customer in self._repository.list_customers()
        ]
        customer_name = self.extract_entity_name(message, customer_names)
        last_turn = session_state.last_turn()
        last_success = session_state.last_successful_turn()

        if (
            customer_name
            and last_success
            and last_success.intent_id == "sales_order_count_for_customer_last_month"
            and self.contains_any(normalized, ("what about", "how about"))
        ):
            return MatchResult(
                intent_id="sales_order_count_for_customer_last_month",
                specialist_name=self.name,
                parameters={
                    "customer_name": customer_name,
                    "date_range": self._date_parser.last_month(),
                },
                uses_session_context=True,
            )

        if normalized == "last month" and last_turn and last_turn.intent_id == "sales_order_count_for_customer_last_month":
            customer_name = last_turn.parameters.get("customer_name")
            if customer_name:
                return MatchResult(
                    intent_id="sales_order_count_for_customer_last_month",
                    specialist_name=self.name,
                    parameters={
                        "customer_name": customer_name,
                        "date_range": self._date_parser.last_month(),
                    },
                    uses_session_context=True,
                )

        if customer_name and last_turn and last_turn.intent_id == "sales_order_count_for_customer_last_month":
            if "customer_name" in last_turn.missing_parameters:
                parameters = dict(last_turn.parameters)
                parameters["customer_name"] = customer_name
                if "date_range" not in parameters:
                    parameters["date_range"] = self._date_parser.last_month()
                return MatchResult(
                    intent_id="sales_order_count_for_customer_last_month",
                    specialist_name=self.name,
                    parameters=parameters,
                    uses_session_context=True,
                )

        if "sales order" not in normalized and "sales orders" not in normalized:
            return None

        missing_parameters = []
        parameters = {}

        if customer_name:
            parameters["customer_name"] = customer_name
        else:
            missing_parameters.append("customer_name")

        if "last month" in normalized:
            parameters["date_range"] = self._date_parser.last_month()
        else:
            missing_parameters.append("date_range")

        clarification_message = None
        if missing_parameters:
            fragments = []
            if "customer_name" in missing_parameters:
                fragments.append("the customer name")
            if "date_range" in missing_parameters:
                fragments.append("the time period 'last month'")
            clarification_message = (
                "I can answer sales order questions for a named customer in the last month. "
                f"Please provide {', '.join(fragments)}."
            )

        return MatchResult(
            intent_id="sales_order_count_for_customer_last_month",
            specialist_name=self.name,
            parameters=parameters,
            missing_parameters=missing_parameters,
            clarification_message=clarification_message,
        )

    def build_query_plan(self, match: MatchResult) -> QueryPlan:
        return QueryPlan(
            intent_id=match.intent_id,
            specialist_name=self.name,
            parameters=match.parameters,
        )

    def execute(self, plan: QueryPlan) -> ComputedResult:
        sales_orders = self._repository.list_sales_orders()
        customers = {
            customer["customer_id"]: customer["customer_name"]
            for customer in self._repository.list_customers()
        }
        customer_name = plan.parameters["customer_name"]
        date_range = plan.parameters["date_range"]
        count = sum(
            1
            for order in sales_orders
            if customers[order["customer_id"]] == customer_name
            and date_range.start_date <= order["so_date"] <= date_range.end_date
        )
        return ComputedResult(
            intent_id=plan.intent_id,
            specialist_name=self.name,
            answer_context={
                "customer_name": customer_name,
                "date_range": date_range.model_dump(mode="json"),
                "sales_order_count": count,
            },
            fallback_answer=(
                f"{customer_name} had {count} sales orders created during {date_range.label}."
            ),
        )

    def render_sql(self, plan: QueryPlan) -> str:
        return render_sql(plan.intent_id, plan.parameters)

