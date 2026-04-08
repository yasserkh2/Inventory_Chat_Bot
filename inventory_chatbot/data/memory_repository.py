from __future__ import annotations

from copy import deepcopy
from typing import Any

from inventory_chatbot.data.interfaces import (
    AssetReadRepository,
    BillingReadRepository,
    CustomerLookupRepository,
    ProcurementReadRepository,
    SalesReadRepository,
)
from inventory_chatbot.data.seed_data import build_seed_data


class InMemoryRepository(
    AssetReadRepository,
    BillingReadRepository,
    ProcurementReadRepository,
    SalesReadRepository,
    CustomerLookupRepository,
):
    def __init__(self, seed_data: dict[str, list[dict[str, Any]]] | None = None) -> None:
        self._data = seed_data or build_seed_data()

    def export_seed_data(self) -> dict[str, list[dict[str, Any]]]:
        return deepcopy(self._data)

    def list_assets(self) -> list[dict[str, Any]]:
        return deepcopy(self._data["assets"])

    def list_sites(self) -> list[dict[str, Any]]:
        return deepcopy(self._data["sites"])

    def list_vendors(self) -> list[dict[str, Any]]:
        return deepcopy(self._data["vendors"])

    def list_bills(self) -> list[dict[str, Any]]:
        return deepcopy(self._data["bills"])

    def list_purchase_orders(self) -> list[dict[str, Any]]:
        return deepcopy(self._data["purchase_orders"])

    def list_sales_orders(self) -> list[dict[str, Any]]:
        return deepcopy(self._data["sales_orders"])

    def list_customers(self) -> list[dict[str, Any]]:
        return deepcopy(self._data["customers"])

    def find_customer_by_name(self, customer_name: str) -> dict[str, Any] | None:
        normalized = customer_name.strip().lower()
        for customer in self._data["customers"]:
            if customer["customer_name"].lower() == normalized:
                return deepcopy(customer)
        return None
