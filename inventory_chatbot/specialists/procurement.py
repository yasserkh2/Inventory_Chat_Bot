from __future__ import annotations

from inventory_chatbot.data.interfaces import ProcurementReadRepository
from inventory_chatbot.models.domain import ComputedResult, MatchResult, QueryPlan, SessionState
from inventory_chatbot.queries.templates import render_sql
from inventory_chatbot.specialists.base import Specialist


class ProcurementSpecialist(Specialist):
    name = "procurement"

    def __init__(self, repository: ProcurementReadRepository) -> None:
        self._repository = repository

    def match(self, message: str, session_state: SessionState) -> MatchResult | None:
        normalized = self.normalize_text(message)
        if not self.contains_any(normalized, ("purchase order", "purchase orders", "po")):
            return None
        if self.contains_any(normalized, ("open", "pending")):
            return MatchResult(
                intent_id="open_purchase_order_count",
                specialist_name=self.name,
            )
        return None

    def build_query_plan(self, match: MatchResult) -> QueryPlan:
        return QueryPlan(
            intent_id=match.intent_id,
            specialist_name=self.name,
            parameters=match.parameters,
        )

    def execute(self, plan: QueryPlan) -> ComputedResult:
        purchase_orders = self._repository.list_purchase_orders()
        count = sum(1 for po in purchase_orders if po["status"] == "Open")
        return ComputedResult(
            intent_id=plan.intent_id,
            specialist_name=self.name,
            answer_context={"open_purchase_order_count": count},
            fallback_answer=f"There are {count} open purchase orders currently pending.",
        )

    def render_sql(self, plan: QueryPlan) -> str:
        return render_sql(plan.intent_id, plan.parameters)

