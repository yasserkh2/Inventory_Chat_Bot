from __future__ import annotations

from collections import defaultdict
from operator import itemgetter
from typing import Any

from inventory_chatbot.data.interfaces import AssetReadRepository
from inventory_chatbot.models.domain import ComputedResult, MatchResult, QueryPlan, SessionState
from inventory_chatbot.queries.templates import render_sql
from inventory_chatbot.services.date_parser import DateParser
from inventory_chatbot.specialists.base import Specialist


class AssetSpecialist(Specialist):
    name = "assets"

    def __init__(
        self, repository: AssetReadRepository, date_parser: DateParser
    ) -> None:
        self._repository = repository
        self._date_parser = date_parser

    def match(self, message: str, session_state: SessionState) -> MatchResult | None:
        normalized = self.normalize_text(message)
        last_success = session_state.last_successful_turn()

        if "site" in normalized and last_success and last_success.intent_id == "asset_count":
            return MatchResult(
                intent_id="asset_count_by_site",
                specialist_name=self.name,
                uses_session_context=True,
            )

        if "asset" not in normalized and not (
            last_success and last_success.intent_id == "asset_count" and "site" in normalized
        ):
            return None

        if self.contains_any(normalized, ("value", "cost")) and "site" in normalized:
            return MatchResult(intent_id="asset_value_by_site", specialist_name=self.name)

        if "purchased" in normalized and "this year" in normalized:
            return MatchResult(
                intent_id="assets_purchased_this_year",
                specialist_name=self.name,
                parameters={"date_range": self._date_parser.this_year()},
            )

        if self.contains_any(normalized, ("vendor", "supplied")) and "most" in normalized:
            return MatchResult(intent_id="top_asset_vendor", specialist_name=self.name)

        if "category" in normalized:
            return MatchResult(
                intent_id="asset_breakdown_by_category",
                specialist_name=self.name,
            )

        if "site" in normalized:
            return MatchResult(intent_id="asset_count_by_site", specialist_name=self.name)

        if self.contains_any(normalized, ("how many", "count", "total")):
            return MatchResult(intent_id="asset_count", specialist_name=self.name)

        return None

    def build_query_plan(self, match: MatchResult) -> QueryPlan:
        return QueryPlan(
            intent_id=match.intent_id,
            specialist_name=self.name,
            parameters=match.parameters,
        )

    def execute(self, plan: QueryPlan) -> ComputedResult:
        assets = self._repository.list_assets()
        sites = {site["site_id"]: site["site_name"] for site in self._repository.list_sites()}
        vendors = {
            vendor["vendor_id"]: vendor["vendor_name"]
            for vendor in self._repository.list_vendors()
        }
        active_assets = [asset for asset in assets if asset["status"] != "Disposed"]

        if plan.intent_id == "asset_count":
            count = len(active_assets)
            return ComputedResult(
                intent_id=plan.intent_id,
                specialist_name=self.name,
                answer_context={"asset_count": count},
                fallback_answer=f"You have {count} active assets in your inventory.",
            )

        if plan.intent_id == "asset_count_by_site":
            grouped: dict[str, int] = defaultdict(int)
            for asset in active_assets:
                grouped[sites[asset["site_id"]]] += 1
            rows = [
                {"site_name": site_name, "asset_count": count}
                for site_name, count in sorted(
                    grouped.items(), key=lambda item: (-item[1], item[0])
                )
            ]
            summary = ", ".join(
                f"{row['site_name']}: {row['asset_count']}" for row in rows
            )
            return ComputedResult(
                intent_id=plan.intent_id,
                specialist_name=self.name,
                answer_context={"rows": rows},
                fallback_answer=f"Here is the asset count by site: {summary}.",
            )

        if plan.intent_id == "asset_value_by_site":
            grouped: dict[str, float] = defaultdict(float)
            for asset in active_assets:
                grouped[sites[asset["site_id"]]] += float(asset["cost"])
            rows = [
                {"site_name": site_name, "total_asset_value": round(total, 2)}
                for site_name, total in sorted(
                    grouped.items(), key=lambda item: (-item[1], item[0])
                )
            ]
            summary = ", ".join(
                f"{row['site_name']}: ${row['total_asset_value']:,.2f}" for row in rows
            )
            return ComputedResult(
                intent_id=plan.intent_id,
                specialist_name=self.name,
                answer_context={"rows": rows},
                fallback_answer=f"Here is the total asset value by site: {summary}.",
            )

        if plan.intent_id == "assets_purchased_this_year":
            date_range = plan.parameters["date_range"]
            count = sum(
                1
                for asset in assets
                if date_range.start_date
                <= asset["purchase_date"]
                <= date_range.end_date
            )
            return ComputedResult(
                intent_id=plan.intent_id,
                specialist_name=self.name,
                answer_context={
                    "date_range": date_range.model_dump(mode="json"),
                    "asset_count": count,
                },
                fallback_answer=(
                    f"{count} assets were purchased during {date_range.label}."
                ),
            )

        if plan.intent_id == "top_asset_vendor":
            grouped: dict[str, int] = defaultdict(int)
            for asset in active_assets:
                grouped[vendors[asset["vendor_id"]]] += 1
            vendor_name, asset_count = sorted(
                grouped.items(), key=lambda item: (-item[1], item[0])
            )[0]
            return ComputedResult(
                intent_id=plan.intent_id,
                specialist_name=self.name,
                answer_context={
                    "vendor_name": vendor_name,
                    "asset_count": asset_count,
                },
                fallback_answer=(
                    f"{vendor_name} supplied the most active assets with {asset_count} assets."
                ),
            )

        if plan.intent_id == "asset_breakdown_by_category":
            grouped: dict[str, int] = defaultdict(int)
            for asset in active_assets:
                grouped[asset["category"]] += 1
            rows = [
                {"category": category, "asset_count": count}
                for category, count in sorted(
                    grouped.items(), key=lambda item: (-item[1], item[0])
                )
            ]
            summary = ", ".join(
                f"{row['category']}: {row['asset_count']}" for row in rows
            )
            return ComputedResult(
                intent_id=plan.intent_id,
                specialist_name=self.name,
                answer_context={"rows": rows},
                fallback_answer=f"Here is the asset breakdown by category: {summary}.",
            )

        raise KeyError(f"Unsupported asset intent: {plan.intent_id}")

    def render_sql(self, plan: QueryPlan) -> str:
        return render_sql(plan.intent_id, plan.parameters)

