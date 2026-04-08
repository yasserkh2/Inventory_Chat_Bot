from __future__ import annotations

AGENT_RESPONSIBILITIES: dict[str, dict[str, object]] = {
    "assets": {
        "role": (
            "Handles inventory asset analysis, asset counts, asset values, asset movement, "
            "site/location allocation, and asset-centric operational questions."
        ),
        "tables": ["Assets", "Sites", "Locations", "Items", "AssetTransactions", "Vendors"],
    },
    "billing": {
        "role": (
            "Handles vendor billing, bill totals, invoice trends, payment due analysis, "
            "and bill-status questions."
        ),
        "tables": ["Bills", "Vendors"],
    },
    "procurement": {
        "role": (
            "Handles purchase order activity, open procurement workload, purchased items, "
            "and order-line level purchasing analysis."
        ),
        "tables": ["PurchaseOrders", "PurchaseOrderLines", "Vendors", "Sites", "Items"],
    },
    "sales": {
        "role": (
            "Handles customer sales orders, sales order line analysis, customer activity, "
            "and sales demand questions."
        ),
        "tables": ["SalesOrders", "SalesOrderLines", "Customers", "Sites", "Items"],
    },
    "chat": {
        "role": (
            "Handles conversational help, schema explanations, table discovery, column discovery, "
            "and relationship walkthroughs without running data retrieval."
        ),
        "tables": [],
    },
    "none": {
        "role": "Used when the request is unsupported or outside the available dataset.",
        "tables": [],
    },
}

TABLE_DESCRIPTIONS: dict[str, str] = {
    "Customers": "Master data for customers who place sales orders.",
    "Vendors": "Master data for suppliers that provide assets, items, and bills.",
    "Sites": "Physical operating sites, warehouses, service centers, or depots.",
    "Locations": "Sub-locations inside a site such as racks, bays, shelves, or work areas.",
    "Items": "Catalog of purchasable or sellable item definitions.",
    "Assets": "Tracked asset records assigned to sites and locations.",
    "Bills": "Vendor bills or invoices issued for payable amounts.",
    "PurchaseOrders": "Purchase order headers issued to vendors.",
    "PurchaseOrderLines": "Line items that belong to purchase orders.",
    "SalesOrders": "Sales order headers created for customers.",
    "SalesOrderLines": "Line items that belong to sales orders.",
    "AssetTransactions": "Movement or adjustment transactions recorded against assets.",
}

COMMON_COLUMN_DESCRIPTIONS: dict[str, str] = {
    "CreatedAt": "Timestamp when the record was created.",
    "UpdatedAt": "Timestamp when the record was last updated.",
    "IsActive": "Flag showing whether the record is currently active.",
    "Email": "Primary email address for the business contact.",
    "Phone": "Primary phone number for the business contact.",
    "AddressLine1": "First line of the address for the record.",
    "BillingAddress1": "Primary billing street address for the customer.",
    "City": "City associated with the record.",
    "BillingCity": "Billing city for the customer.",
    "Country": "Country associated with the record.",
    "BillingCountry": "Billing country for the customer.",
    "Category": "Business category used to classify the record.",
    "Status": "Lifecycle or processing status of the record.",
    "Description": "Free-text description for the line or record.",
    "LineNumber": "Sequence number of the line within its parent document.",
    "Quantity": "Quantity recorded on the transaction line.",
    "UnitPrice": "Price per unit for the line item.",
    "Currency": "Currency code used for the monetary amount.",
    "TimeZone": "Time zone associated with the site.",
    "Note": "Additional note captured for the transaction.",
    "Cost": "Recorded acquisition cost of the asset.",
    "TotalAmount": "Total monetary amount recorded on the bill.",
    "PurchaseDate": "Date when the asset was purchased.",
    "BillDate": "Date when the bill was issued.",
    "DueDate": "Date when the bill is due for payment.",
    "PODate": "Date when the purchase order was created.",
    "SODate": "Date when the sales order was created.",
    "TxnDate": "Date and time when the asset transaction happened.",
    "TxnType": "Type of asset movement or adjustment that occurred.",
}

COMMON_COLUMN_VALUE_HINTS: dict[str, list[str]] = {
    "IsActive": ["0", "1"],
}

TABLE_COLUMN_VALUE_HINTS: dict[str, dict[str, list[str]]] = {
    "Assets": {
        "Status": ["Active", "InRepair", "Disposed"],
    },
    "Bills": {
        "Status": ["Open", "Paid", "Void"],
        "Currency": ["USD"],
    },
    "PurchaseOrders": {
        "Status": ["Open", "Approved", "Closed", "Cancelled"],
    },
    "SalesOrders": {
        "Status": ["Open", "Shipped", "Closed", "Cancelled"],
    },
    "AssetTransactions": {
        "TxnType": ["Move", "Adjust", "Dispose", "Create"],
    },
}

TABLE_COLUMN_DESCRIPTIONS: dict[str, dict[str, str]] = {
    "Customers": {
        "CustomerCode": "Business-friendly customer code.",
        "CustomerName": "Display name of the customer.",
    },
    "Vendors": {
        "VendorCode": "Business-friendly vendor code.",
        "VendorName": "Display name of the vendor.",
    },
    "Sites": {
        "SiteCode": "Business-friendly code for the site.",
        "SiteName": "Display name of the site.",
    },
    "Locations": {
        "LocationCode": "Business-friendly code for the location.",
        "LocationName": "Display name of the location.",
        "ParentLocationId": "Optional parent location used to model nested storage areas.",
    },
    "Items": {
        "ItemCode": "Business-friendly item code.",
        "ItemName": "Display name of the item.",
        "UnitOfMeasure": "Default unit of measure used for the item.",
    },
    "Assets": {
        "AssetTag": "Unique asset tag used by operations to identify the asset.",
        "AssetName": "Display name of the asset.",
        "SerialNumber": "Manufacturer or operational serial number of the asset.",
    },
    "Bills": {
        "BillNumber": "Business bill or invoice number.",
    },
    "PurchaseOrders": {
        "PONumber": "Business purchase order number.",
    },
    "PurchaseOrderLines": {
        "ItemCode": "Item code captured on the purchase order line.",
    },
    "SalesOrders": {
        "SONumber": "Business sales order number.",
    },
    "SalesOrderLines": {
        "ItemCode": "Item code captured on the sales order line.",
    },
    "AssetTransactions": {
        "FromLocationId": "Origin location for the asset movement, when applicable.",
        "ToLocationId": "Destination location for the asset movement, when applicable.",
    },
}

TABLE_ENTITY_LABELS: dict[str, str] = {
    "Customers": "customer",
    "Vendors": "vendor",
    "Sites": "site",
    "Locations": "location",
    "Items": "item",
    "Assets": "asset",
    "Bills": "bill",
    "PurchaseOrders": "purchase order",
    "PurchaseOrderLines": "purchase order line",
    "SalesOrders": "sales order",
    "SalesOrderLines": "sales order line",
    "AssetTransactions": "asset transaction",
}


def describe_column(
    *,
    table_name: str,
    column_name: str,
    primary_key: str,
    joins: dict[str, tuple[str, str]],
) -> str:
    table_specific = TABLE_COLUMN_DESCRIPTIONS.get(table_name, {})
    if column_name in table_specific:
        return table_specific[column_name]
    if column_name == primary_key:
        return f"Primary key for the {TABLE_ENTITY_LABELS.get(table_name, table_name.lower())} record."
    if column_name in joins:
        target_table, target_column = joins[column_name]
        return f"Foreign key to {target_table}.{target_column} for the related record."
    if column_name in COMMON_COLUMN_DESCRIPTIONS:
        return COMMON_COLUMN_DESCRIPTIONS[column_name]
    if column_name.endswith("Id"):
        return f"Identifier field stored on the {TABLE_ENTITY_LABELS.get(table_name, table_name.lower())} record."
    return f"{column_name} value stored for the {TABLE_ENTITY_LABELS.get(table_name, table_name.lower())} record."


def describe_column_value_hints(*, table_name: str, column_name: str) -> list[str]:
    table_hints = TABLE_COLUMN_VALUE_HINTS.get(table_name, {})
    if column_name in table_hints:
        return table_hints[column_name]
    return COMMON_COLUMN_VALUE_HINTS.get(column_name, [])
