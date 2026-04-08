from __future__ import annotations

import unittest

from inventory_chatbot.services.final_conversation_agent import FinalConversationAgent


class FinalConversationAgentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.agent = FinalConversationAgent()

    def test_clarification_adds_follow_up_question_when_missing(self) -> None:
        text = self.agent.compose(
            user_message="show data",
            raw_answer="I need one more detail before I can run this.",
            reply_status="needs_clarification",
            response_status="ok",
            sql_query="",
            result_preview={},
        )
        self.assertIn("I need one more detail", text)
        self.assertIn("?", text)

    def test_ok_sql_result_adds_next_step_prompt(self) -> None:
        text = self.agent.compose(
            user_message="total unit price",
            raw_answer="The total unit price is 3740.",
            reply_status="ok",
            response_status="ok",
            sql_query="SELECT SUM(SalesOrderLines.UnitPrice) AS TotalUnitPrice FROM SalesOrderLines;",
            result_preview={"row_count": 1},
        )
        self.assertIn("The total unit price is 3740.", text)
        self.assertIn("Would you like me to drill into the matching records?", text)

    def test_non_sql_ok_reply_is_kept_as_is(self) -> None:
        text = self.agent.compose(
            user_message="hello",
            raw_answer="Hello. I can help with schema questions.",
            reply_status="ok",
            response_status="ok",
            sql_query="",
            result_preview={},
        )
        self.assertEqual(text, "Hello. I can help with schema questions.")


if __name__ == "__main__":
    unittest.main()

