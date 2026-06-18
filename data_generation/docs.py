from __future__ import annotations

import json
from datetime import timedelta
from decimal import Decimal

from data_generation.config import (
    EXOTIC_LIQUIDS,
    GRANDMA_KELLYS,
    GRANDMA_PRODUCTS,
    LAST_3M_START,
    PAVLOVA,
    PAVLOVA_PRODUCTS,
    TOKYO_PRODUCTS,
    TOKYO_TRADERS,
    TOP_CUSTOMER_IDS,
)

# Caps keep complaints a realistic minority of overall communications and keep
# Scenario D's complaint balance (Grandma < Tokyo) stable.
PAVLOVA_COMPLAINT_CAP = 40
GRANDMA_COMPLAINT_CAP = 15


def generate_contracts() -> list:
    return [
        (
            EXOTIC_LIQUIDS,
            "CT-1-2020",
            12,
            "2020-01-01",
            None,
            Decimal("500.00"),
            "active",
        ),
        (
            GRANDMA_KELLYS,
            "CT-3-2020",
            30,
            "2020-01-01",
            None,
            Decimal("1200.00"),
            "active",
        ),
        (
            TOKYO_TRADERS,
            "CT-4-2020",
            14,
            "2020-01-01",
            None,
            Decimal("900.00"),
            "active",
        ),
        (PAVLOVA, "CT-7-2020", 10, "2020-01-01", None, Decimal("750.00"), "active"),
    ]


def generate_communications(orders: list, order_details: list, shipments: list) -> list:
    products_by_order: dict[int, set[int]] = {}
    for order_id, product_id, _unit_price, _quantity, _discount in order_details:
        products_by_order.setdefault(order_id, set()).add(product_id)
    orders_by_id = {order[0]: order for order in orders}
    shipment_delay = {
        shipment[0]: (shipment[5] - shipment[3]).days for shipment in shipments
    }

    rows = []
    pavlova_count = 0
    grandma_count = 0
    for order_id in sorted(products_by_order):
        products = products_by_order[order_id]
        order = orders_by_id[order_id]
        order_date = order[3]
        is_top = order[1] in TOP_CUSTOMER_IDS
        if (
            order_date >= LAST_3M_START
            and is_top
            and products.intersection(TOKYO_PRODUCTS)
            and shipment_delay[order_id] > 0
        ):
            rows.append(
                (
                    order[1],
                    order_id,
                    min(products.intersection(TOKYO_PRODUCTS)),
                    "email",
                    "complaint",
                    "Late delivery affected replenishment",
                    "The delivery arrived late and caused a delay in our "
                    "planned replenishment window.",
                    "negative",
                    f"{(order_date + timedelta(days=24)).isoformat()}T10:00:00+00:00",
                )
            )
        elif (
            is_top
            and products.intersection(PAVLOVA_PRODUCTS)
            and shipment_delay[order_id] <= 0
            and pavlova_count < PAVLOVA_COMPLAINT_CAP
        ):
            pavlova_count += 1
            rows.append(
                (
                    order[1],
                    order_id,
                    min(products.intersection(PAVLOVA_PRODUCTS)),
                    "portal",
                    "complaint",
                    "Packaging quality issue",
                    "Several cases arrived with packaging damage; delivery "
                    "timing was acceptable.",
                    "negative",
                    f"{(order_date + timedelta(days=5)).isoformat()}T15:30:00+00:00",
                )
            )
        elif (
            products.intersection(GRANDMA_PRODUCTS)
            and grandma_count < GRANDMA_COMPLAINT_CAP
            and order_id % 7 == 0
        ):
            grandma_count += 1
            rows.append(
                (
                    order[1],
                    order_id,
                    min(products.intersection(GRANDMA_PRODUCTS)),
                    "email",
                    "complaint",
                    "Product quality below expectation",
                    "A portion of the shipment did not meet the expected "
                    "quality grade; delivery timing was fine.",
                    "negative",
                    f"{(order_date + timedelta(days=6)).isoformat()}T11:00:00+00:00",
                )
            )

    rows.extend(_neutral_communications(products_by_order, orders_by_id))
    return rows


def _neutral_communications(
    products_by_order: dict[int, set[int]],
    orders_by_id: dict[int, tuple],
) -> list:
    # Non-complaint traffic so complaints stay a realistic minority of the channel.
    channels = ("email", "phone", "portal")
    templates = (
        ("question", "Order status enquiry", "Requesting an update on the order "
         "status and expected delivery.", "neutral"),
        ("information", "Updated billing contact", "Sharing an updated billing "
         "contact for future invoices.", "neutral"),
        ("question", "Restock availability", "Asking about availability for the "
         "next replenishment cycle.", "positive"),
    )
    rows = []
    for order_id in sorted(products_by_order):
        if order_id % 11 != 0:
            continue
        order = orders_by_id[order_id]
        reason, subject, body, sentiment = templates[order_id % len(templates)]
        rows.append(
            (
                order[1],
                order_id,
                None,
                channels[order_id % len(channels)],
                reason,
                subject,
                body,
                sentiment,
                f"{order[3].isoformat()}T09:30:00+00:00",
            )
        )
    return rows


def generate_product_specifications(product_ids: list[int]) -> list:
    rows = []
    for product_id in product_ids[:40]:
        attributes = {"storage": "ambient", "inspection_required": product_id % 5 == 0}
        rows.append(
            (
                product_id,
                f"Product {product_id} technical specification",
                "Structured product sheet generated for Phase 03 controlled "
                "retrieval tests.",
                json.dumps(attributes),
            )
        )
    return rows


def generate_documents(
    contracts: list,
    communications: list,
    specs: list,
) -> tuple[list, list]:
    documents = []
    entities = []
    document_id = 1
    for supplier_id, contract_number, lead_time, *_rest in contracts:
        documents.append(
            (
                "supplier_contract",
                f"Supplier contract {contract_number}",
                None,
                supplier_id,
                None,
                None,
                "generated",
                json.dumps(
                    {
                        "contract_number": contract_number,
                        "lead_time_days": lead_time,
                    }
                ),
            )
        )
        entities.append(
            (
                document_id,
                "supplier",
                str(supplier_id),
                contract_number,
                Decimal("0.990"),
            )
        )
        document_id += 1
    for (
        customer_id,
        order_id,
        product_id,
        _channel,
        reason,
        subject,
        _body,
        sentiment,
        _at,
    ) in communications[:60]:
        documents.append(
            (
                "customer_communication",
                subject,
                order_id,
                None,
                customer_id,
                None,
                "generated",
                json.dumps(
                    {
                        "contact_reason": reason,
                        "sentiment": sentiment,
                        "product_id": product_id,
                    }
                ),
            )
        )
        entities.append(
            (document_id, "customer", customer_id, subject, Decimal("0.950"))
        )
        document_id += 1
    for product_id, title, _text, attrs in specs:
        documents.append(
            ("product_specification", title, None, None, None, None, "generated", attrs)
        )
        entities.append(
            (document_id, "product", str(product_id), title, Decimal("0.970"))
        )
        document_id += 1
    return documents, entities
