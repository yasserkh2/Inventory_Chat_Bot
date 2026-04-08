from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class AssetReadRepository(ABC):
    @abstractmethod
    def list_assets(self) -> list[dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def list_sites(self) -> list[dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def list_vendors(self) -> list[dict[str, Any]]:
        raise NotImplementedError


class BillingReadRepository(ABC):
    @abstractmethod
    def list_bills(self) -> list[dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def list_vendors(self) -> list[dict[str, Any]]:
        raise NotImplementedError


class ProcurementReadRepository(ABC):
    @abstractmethod
    def list_purchase_orders(self) -> list[dict[str, Any]]:
        raise NotImplementedError


class SalesReadRepository(ABC):
    @abstractmethod
    def list_sales_orders(self) -> list[dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def list_customers(self) -> list[dict[str, Any]]:
        raise NotImplementedError


class CustomerLookupRepository(ABC):
    @abstractmethod
    def find_customer_by_name(self, customer_name: str) -> dict[str, Any] | None:
        raise NotImplementedError

