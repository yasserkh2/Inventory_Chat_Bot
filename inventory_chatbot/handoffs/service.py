from __future__ import annotations

from inventory_chatbot.dynamic_sql.models import QueryPlan
from inventory_chatbot.handoffs.models import (
    DynamicSQLActivation,
    PlannerActivation,
    SpecialistActivation,
)
from inventory_chatbot.orchestrator.models import OrchestratorDecision
from inventory_chatbot.sql_agents.models import SQLAgentDecision
from inventory_chatbot.sql_agents.metadata import SQL_AGENT_METADATA
from inventory_chatbot.sql_execution.models import SQLExecutionRequest


class OrchestratorHandoffService:
    def build_specialist_activation(
        self, decision: OrchestratorDecision
    ) -> SpecialistActivation:
        return SpecialistActivation(
            agent_name=decision.agent,
            instructions=self._build_specialist_instructions(decision),
            context={"orchestrator": decision.model_dump(mode="json")},
        )

    def build_planner_activation(self, decision: OrchestratorDecision) -> PlannerActivation:
        return PlannerActivation(
            agent_name=decision.agent,
            handoff_summary=decision.handoff_instructions or decision.analysis_summary,
            context={
                "orchestrator": decision.model_dump(mode="json"),
                "required_tables": [item.table for item in decision.required_data],
            },
        )

    def build_dynamic_sql_activation(
        self,
        *,
        decision: OrchestratorDecision,
        query_plan: QueryPlan,
    ) -> DynamicSQLActivation:
        return DynamicSQLActivation(
            instructions=(
                f"Execute the query plan prepared for the {decision.agent} agent "
                "and return rows plus SQL."
            ),
            context={
                "query_plan": query_plan.model_dump(),
                "source_agent": decision.agent,
                "orchestrator": decision.model_dump(mode="json"),
            },
        )

    def build_execution_request(
        self,
        *,
        user_message: str,
        orchestrator_decision: OrchestratorDecision,
        sql_agent_decision: SQLAgentDecision,
    ) -> SQLExecutionRequest:
        if sql_agent_decision.query_plan is None:
            raise ValueError("SQL agent decision must include query_plan for execution.")
        return SQLExecutionRequest(
            user_message=user_message,
            query_plan=sql_agent_decision.query_plan,
            sql_query=sql_agent_decision.sql_query,
            source_agent=orchestrator_decision.agent,
            allowed_tables=list(
                SQL_AGENT_METADATA.get(orchestrator_decision.agent, {}).get("tables", [])
            )
            or [item.table for item in sql_agent_decision.required_data]
            or list(self._allowed_tables_from_orchestrator(orchestrator_decision)),
            context={
                "orchestrator": orchestrator_decision.model_dump(mode="json"),
                "sql_agent": sql_agent_decision.model_dump(mode="json"),
            },
        )

    @staticmethod
    def _allowed_tables_from_orchestrator(decision: OrchestratorDecision) -> list[str]:
        return [item.table for item in decision.required_data]

    @staticmethod
    def _build_specialist_instructions(decision: OrchestratorDecision) -> str:
        details = [
            f"Handle this request using the {decision.agent} domain specialist rules.",
            "If clarification is needed, ask for it explicitly.",
        ]
        if decision.user_need:
            details.append(f"User need: {decision.user_need}")
        if decision.analysis_summary:
            details.append(f"Analysis summary: {decision.analysis_summary}")
        if decision.required_data:
            formatted_required_data = "; ".join(
                f"{item.table}({', '.join(item.columns)}) because {item.reason}"
                for item in decision.required_data
            )
            details.append(f"Required data: {formatted_required_data}")
        if decision.handoff_instructions:
            details.append(f"Handoff: {decision.handoff_instructions}")
        return " ".join(details)
