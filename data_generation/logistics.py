from __future__ import annotations

from datetime import timedelta

import numpy as np

from data_generation.config import (
    EXOTIC_PRODUCTS,
    LAST_3M_START,
    PAVLOVA_PRODUCTS,
    TOKYO_PRODUCTS,
    TOP_CUSTOMER_IDS,
)


def generate_shipments_and_inventory(
    orders: list,
    order_details: list,
    rng: np.random.Generator,
) -> dict[str, list]:
    products_by_order: dict[int, set[int]] = {}
    quantities_by_product: dict[int, int] = {}
    for order_id, product_id, _unit_price, quantity, _discount in order_details:
        products_by_order.setdefault(order_id, set()).add(product_id)
        quantities_by_product[product_id] = quantities_by_product.get(
            product_id, 0
        ) + int(quantity)

    shipments = []
    for order in orders:
        order_id = order[0]
        customer_id = order[1]
        order_date = order[3]
        shipper_id = order[6]
        shipped_date = order[5]
        expected = shipped_date + timedelta(days=int(rng.integers(5, 15)))
        products = products_by_order[order_id]
        actual = expected + timedelta(
            days=int(
                rng.choice(
                    [-2, -1, 0, 1, 2, 3],
                    p=[0.08, 0.16, 0.46, 0.18, 0.08, 0.04],
                )
            )
        )
        is_top = customer_id in TOP_CUSTOMER_IDS
        recent = order_date >= LAST_3M_START

        if products.intersection(PAVLOVA_PRODUCTS):
            # Scenario C trap: Pavlova orders ship on time / early.
            expected = shipped_date + timedelta(days=12)
            actual = expected - timedelta(days=int(rng.choice([0, 1, 2])))
        elif recent and is_top and products.intersection(TOKYO_PRODUCTS):
            # Scenario A: Tokyo delays hit top customers (contract 14, actual ~22).
            expected = shipped_date + timedelta(days=14)
            actual = expected + timedelta(days=8)
        elif recent and not is_top and products.intersection(EXOTIC_PRODUCTS):
            # Scenario B: Exotic Liquids delays hit non-top customers only.
            expected = shipped_date + timedelta(days=12)
            actual = expected + timedelta(days=7)

        shipments.append(
            (
                order_id,
                f"Carrier {shipper_id}",
                shipper_id,
                expected,
                shipped_date,
                actual,
                "delivered",
            )
        )

    movements = []
    for product_id, total_quantity in sorted(quantities_by_product.items()):
        for quarter in range(24):
            year = 2020 + quarter // 4
            month = 1 + (quarter % 4) * 3
            warehouse_id = int(rng.integers(1, 5))
            inbound = max(80, int(total_quantity / 24 * float(rng.uniform(1.05, 1.35))))
            movements.append(
                (
                    product_id,
                    warehouse_id,
                    "inbound",
                    inbound,
                    f"{year}-{month:02d}-01T09:00:00+00:00",
                    f"PO-{year}-Q{quarter % 4 + 1}-{product_id}",
                )
            )
        movements.append(
            (
                product_id,
                int(rng.integers(1, 5)),
                "adjustment",
                int(rng.integers(-12, 18)),
                "2025-12-31T18:00:00+00:00",
                f"COUNT-2025-{product_id}",
            )
        )

    return {"shipments": shipments, "inventory_movements": movements}
