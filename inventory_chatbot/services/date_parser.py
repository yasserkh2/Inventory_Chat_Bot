from __future__ import annotations

from datetime import date, timedelta
from typing import Callable

from inventory_chatbot.models.domain import DateRange


class DateParser:
    def __init__(self, today_provider: Callable[[], date] | None = None) -> None:
        self._today_provider = today_provider or date.today

    def today(self) -> date:
        return self._today_provider()

    def parse_supported_range(self, text: str) -> DateRange | None:
        normalized = text.strip().lower()
        if "this year" in normalized:
            return self.this_year()
        if "last month" in normalized:
            return self.last_month()
        if "last quarter" in normalized:
            return self.last_quarter()
        return None

    def this_year(self) -> DateRange:
        today = self.today()
        return DateRange(
            start_date=date(today.year, 1, 1),
            end_date=date(today.year, 12, 31),
            label="this year",
        )

    def last_month(self) -> DateRange:
        today = self.today()
        first_of_this_month = date(today.year, today.month, 1)
        end_of_last_month = first_of_this_month - timedelta(days=1)
        start_of_last_month = date(end_of_last_month.year, end_of_last_month.month, 1)
        return DateRange(
            start_date=start_of_last_month,
            end_date=end_of_last_month,
            label="last month",
        )

    def last_quarter(self) -> DateRange:
        today = self.today()
        current_quarter = ((today.month - 1) // 3) + 1
        if current_quarter == 1:
            year = today.year - 1
            quarter = 4
        else:
            year = today.year
            quarter = current_quarter - 1

        start_month = (quarter - 1) * 3 + 1
        end_month = start_month + 2
        start_date = date(year, start_month, 1)
        if end_month == 12:
            end_date = date(year, 12, 31)
        else:
            end_date = date(year, end_month + 1, 1) - timedelta(days=1)
        return DateRange(
            start_date=start_date,
            end_date=end_date,
            label="last quarter",
        )

