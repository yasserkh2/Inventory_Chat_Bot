from __future__ import annotations

from inventory_chatbot.data.interfaces import BillingReadRepository
from inventory_chatbot.models.domain import ComputedResult, MatchResult, QueryPlan, SessionState
from inventory_chatbot.queries.templates import render_sql
from inventory_chatbot.services.date_parser import DateParser
from inventory_chatbot.specialists.base import Specialist


class BillingSpecialist(Specialist):
    name = "billing"

    def __init__(
        self, repository: BillingReadRepository, date_parser: DateParser
    ) -> None:
        self._repository = repository
        self._date_parser = date_parser

    def match(self, message: str, session_state: SessionState) -> MatchResult | None:
        normalized = self.normalize_text(message)
        last_turn = session_state.last_turn()

        if normalized == "last quarter" and last_turn and last_turn.intent_id == "billed_amount_last_quarter":
            return MatchResult(
                intent_id="billed_amount_last_quarter",
                specialist_name=self.name,
                parameters={"date_range": self._date_parser.last_quarter()},
                uses_session_context=True,
            )

        if not self.contains_any(normalized, ("bill", "billed")):
            return None

        if "last quarter" in normalized:
            return MatchResult(
                intent_id="billed_amount_last_quarter",
                specialist_name=self.name,
                parameters={"date_range": self._date_parser.last_quarter()},
            )

        if "amount" in normalized or "total" in normalized:
            return MatchResult(
                intent_id="billed_amount_last_quarter",
                specialist_name=self.name,
                missing_parameters=["date_range"],
                clarification_message=(
                    "I can report billed amounts for the last quarter. Reply with 'last quarter' to continue."
                ),
            )

        return None

    def build_query_plan(self, match: MatchResult) -> QueryPlan:
        return QueryPlan(
            intent_id=match.intent_id,
            specialist_name=self.name,
            parameters=match.parameters,
        )

    def execute(self, plan: QueryPlan) -> ComputedResult:
        date_range = plan.parameters["date_range"]
        bills = self._repository.list_bills()
        total_amount = round(
            sum(
                bill["total_amount"]
                for bill in bills
                if bill["status"] != "Void"
                and date_range.start_date <= bill["bill_date"] <= date_range.end_date
            ),
            2,
        )
        return ComputedResult(
            intent_id=plan.intent_id,
            specialist_name=self.name,
            answer_context={
                "date_range": date_range.model_dump(mode="json"),
                "total_billed_amount": total_amount,
            },
            fallback_answer=(
                f"The total billed amount for {date_range.label} is ${total_amount:,.2f}."
            ),
        )

    def render_sql(self, plan: QueryPlan) -> str:
        return render_sql(plan.intent_id, plan.parameters)

