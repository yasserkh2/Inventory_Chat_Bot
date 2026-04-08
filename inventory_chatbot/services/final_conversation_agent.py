from __future__ import annotations

import re
from typing import Any


class FinalConversationAgent:
    """Polishes delegated-agent output into a smoother conversational reply."""

    def compose(
        self,
        *,
        user_message: str,
        raw_answer: str,
        reply_status: str,
        response_status: str,
        sql_query: str,
        result_preview: dict[str, Any] | None = None,
    ) -> str:
        result_preview = result_preview or {}
        answer = (raw_answer or "").strip()
        if not answer:
            answer = "I could not generate a response."

        if reply_status == "needs_clarification":
            return self._ensure_single_follow_up_question(
                answer=answer,
                fallback_question=self._clarification_fallback_question(user_message),
            )

        if response_status == "error":
            return self._ensure_single_follow_up_question(
                answer=answer,
                fallback_question=(
                    "Would you like me to retry with a clearer metric and a specific date range?"
                ),
            )

        if reply_status == "ok" and sql_query.strip():
            row_count = result_preview.get("row_count")
            if isinstance(row_count, int):
                return (
                    f"{answer}\n\nWould you like a breakdown by date, site, or status next?"
                    if row_count > 1
                    else f"{answer}\n\nWould you like me to drill into the matching records?"
                )
        return answer

    @staticmethod
    def _clarification_fallback_question(user_message: str) -> str:
        normalized = re.sub(r"\s+", " ", user_message.lower()).strip()
        if "how many" in normalized or "count" in normalized:
            return "Which entity and date range should I use for the count?"
        if "total" in normalized or "sum" in normalized:
            return "Which amount field and date range should I use for the total?"
        return "Could you confirm the exact metric, filters, and date range?"

    @staticmethod
    def _ensure_single_follow_up_question(*, answer: str, fallback_question: str) -> str:
        stripped = answer.strip()
        if "?" in stripped:
            return stripped
        return f"{stripped} {fallback_question}"

