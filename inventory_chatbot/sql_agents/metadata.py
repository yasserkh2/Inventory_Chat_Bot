from __future__ import annotations

SQL_AGENT_METADATA: dict[str, dict[str, object]] = {
    "assets": {
        "role": (
            "Owns SQL planning for asset analytics, site and location rollups, asset movement, "
            "inventory asset counts, values, and asset record inspection."
        ),
        "tables": ["Assets", "Sites", "Locations", "Items", "AssetTransactions", "Vendors"],
        "capabilities": [
            "count active assets and grouped asset metrics",
            "inspect raw asset, site, location, and asset transaction rows",
            "aggregate asset value, vendor contribution, and category breakdowns",
            "clarify missing business filters before execution",
        ],
    },
    "billing": {
        "role": (
            "Owns SQL planning for vendor bills, invoice totals, payable trends, due-date analysis, "
            "and bill record inspection."
        ),
        "tables": ["Bills", "Vendors"],
        "capabilities": [
            "sum or aggregate billed amounts",
            "group billing metrics by vendor or status",
            "inspect raw bill records and vendor billing details",
            "clarify missing date ranges or billing filters before execution",
        ],
    },
    "procurement": {
        "role": (
            "Owns SQL planning for purchase orders, purchase order lines, vendor procurement activity, "
            "and raw purchasing record inspection."
        ),
        "tables": ["PurchaseOrders", "PurchaseOrderLines", "Vendors", "Sites", "Items"],
        "capabilities": [
            "count and filter purchase orders by status and time",
            "inspect raw purchase orders and purchase order lines",
            "group procurement workload by vendor, site, or item",
            "clarify missing procurement filters before execution",
        ],
    },
    "sales": {
        "role": (
            "Owns SQL planning for customers, sales orders, sales order lines, demand analysis, "
            "and customer or sales record inspection."
        ),
        "tables": ["SalesOrders", "SalesOrderLines", "Customers", "Sites", "Items"],
        "capabilities": [
            "count and filter sales orders by customer, status, or time",
            "inspect raw customer, sales order, and sales line records",
            "group sales demand by customer, site, or item",
            "clarify missing customer names or date ranges before execution",
        ],
    },
}
