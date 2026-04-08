from __future__ import annotations

import unittest

from inventory_chatbot.services.date_parser import DateParser
from tests.helpers import FIXED_TODAY


class DateParserTests(unittest.TestCase):
    def setUp(self) -> None:
        self.parser = DateParser(today_provider=lambda: FIXED_TODAY)

    def test_this_year(self) -> None:
        result = self.parser.this_year()
        self.assertEqual(result.start_date.isoformat(), "2026-01-01")
        self.assertEqual(result.end_date.isoformat(), "2026-12-31")

    def test_last_month(self) -> None:
        result = self.parser.last_month()
        self.assertEqual(result.start_date.isoformat(), "2026-03-01")
        self.assertEqual(result.end_date.isoformat(), "2026-03-31")

    def test_last_quarter(self) -> None:
        result = self.parser.last_quarter()
        self.assertEqual(result.start_date.isoformat(), "2026-01-01")
        self.assertEqual(result.end_date.isoformat(), "2026-03-31")


if __name__ == "__main__":
    unittest.main()

