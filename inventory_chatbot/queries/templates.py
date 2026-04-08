from __future__ import annotations

from datetime import date
from typing import Any


def _quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _date_literal(value: date) -> str:
    return _quote(value.isoformat())


def render_sql(intent_id: str, parameters: dict[str, Any]) -> str:
    if intent_id == "asset_count":
        return (
            "SELECT COUNT(*) AS AssetCount\n"
            "FROM Assets\n"
            "WHERE Status <> 'Disposed';"
        )

    if intent_id == "asset_count_by_site":
        return (
            "SELECT s.SiteName, COUNT(*) AS AssetCount\n"
            "FROM Assets a\n"
            "JOIN Sites s ON s.SiteId = a.SiteId\n"
            "WHERE a.Status <> 'Disposed'\n"
            "GROUP BY s.SiteName\n"
            "ORDER BY AssetCount DESC, s.SiteName ASC;"
        )

    if intent_id == "asset_value_by_site":
        return (
            "SELECT s.SiteName, SUM(a.Cost) AS TotalAssetValue\n"
            "FROM Assets a\n"
            "JOIN Sites s ON s.SiteId = a.SiteId\n"
            "WHERE a.Status <> 'Disposed'\n"
            "GROUP BY s.SiteName\n"
            "ORDER BY TotalAssetValue DESC, s.SiteName ASC;"
        )

    if intent_id == "assets_purchased_this_year":
        date_range = parameters["date_range"]
        return (
            "SELECT COUNT(*) AS PurchasedAssetCount\n"
            "FROM Assets\n"
            f"WHERE PurchaseDate BETWEEN {_date_literal(date_range.start_date)} "
            f"AND {_date_literal(date_range.end_date)};"
        )

    if intent_id == "top_asset_vendor":
        return (
            "SELECT TOP 1 v.VendorName, COUNT(*) AS AssetCount\n"
            "FROM Assets a\n"
            "JOIN Vendors v ON v.VendorId = a.VendorId\n"
            "WHERE a.Status <> 'Disposed'\n"
            "GROUP BY v.VendorName\n"
            "ORDER BY AssetCount DESC, v.VendorName ASC;"
        )

    if intent_id == "asset_breakdown_by_category":
        return (
            "SELECT Category, COUNT(*) AS AssetCount\n"
            "FROM Assets\n"
            "WHERE Status <> 'Disposed'\n"
            "GROUP BY Category\n"
            "ORDER BY AssetCount DESC, Category ASC;"
        )

    if intent_id == "billed_amount_last_quarter":
        date_range = parameters["date_range"]
        return (
            "SELECT SUM(TotalAmount) AS TotalBilledAmount\n"
            "FROM Bills\n"
            f"WHERE BillDate BETWEEN {_date_literal(date_range.start_date)} "
            f"AND {_date_literal(date_range.end_date)}\n"
            "  AND Status <> 'Void';"
        )

    if intent_id == "open_purchase_order_count":
        return (
            "SELECT COUNT(*) AS OpenPurchaseOrderCount\n"
            "FROM PurchaseOrders\n"
            "WHERE Status = 'Open';"
        )

    if intent_id == "sales_order_count_for_customer_last_month":
        date_range = parameters["date_range"]
        customer_name = _quote(parameters["customer_name"])
        return (
            "SELECT COUNT(*) AS SalesOrderCount\n"
            "FROM SalesOrders so\n"
            "JOIN Customers c ON c.CustomerId = so.CustomerId\n"
            f"WHERE c.CustomerName = {customer_name}\n"
            f"  AND so.SODate BETWEEN {_date_literal(date_range.start_date)} "
            f"AND {_date_literal(date_range.end_date)};"
        )

    raise KeyError(f"Unsupported SQL template for intent: {intent_id}")

