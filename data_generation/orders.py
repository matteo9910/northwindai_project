from __future__ import annotations

from datetime import date, timedelta

import numpy as np

from data_generation.config import (
    EXOTIC_LIQUIDS,
    EXOTIC_PRODUCTS,
    FIRST_SYNTHETIC_ORDER_ID,
    GRANDMA_KELLYS,
    HORIZON_START,
    ORDER_COUNT,
    PAVLOVA,
    PAVLOVA_PRODUCTS,
    SCENARIO_B_CUSTOMER_IDS,
    TOKYO_PRODUCTS,
    TOKYO_TRADERS,
    TOP_CUSTOMER_IDS,
)
from data_generation.masters import Customer, MasterData, Product

# A single order carries products from at most one scenario supplier, so each
# controlled scenario stays cleanly separable (e.g. a Tokyo-delayed order never
# also holds a Pavlova product that would force it on-time). Non-scenario
# suppliers mix freely as background noise.
SCENARIO_SUPPLIERS = frozenset(
    {EXOTIC_LIQUIDS, GRANDMA_KELLYS, TOKYO_TRADERS, PAVLOVA}
)


def _scenario_conflict(order_supplier: int | None, candidate_supplier: int) -> bool:
    return (
        candidate_supplier in SCENARIO_SUPPLIERS
        and order_supplier is not None
        and order_supplier != candidate_supplier
    )


def _days_between(start: date, end: date) -> int:
    return (end - start).days + 1


def _seasonality(month: int, category_id: int) -> float:
    if category_id in {1, 2} and month in {11, 12}:
        return 1.35
    if category_id in {3, 8} and month in {5, 6, 7, 8}:
        return 1.25
    if category_id in {4, 5} and month in {1, 2, 9, 10}:
        return 1.15
    return 1.0


def _weighted_choice(rng: np.random.Generator, items, weights):
    index = int(rng.choice(len(items), p=np.array(weights) / np.sum(weights)))
    return items[index]


def _customer_weights(customers: list[Customer]) -> list[float]:
    weights = []
    for customer in customers:
        if customer.customer_id in TOP_CUSTOMER_IDS:
            weights.append(18.0)
        elif customer.customer_id in SCENARIO_B_CUSTOMER_IDS:
            weights.append(0.05)
        else:
            weights.append(1.0)
    return weights


def generate_orders(
    master_data: MasterData,
    rng: np.random.Generator,
) -> dict[str, list]:
    products = master_data.products
    products_by_id = {product.product_id: product for product in products}
    product_weights = [
        max(product.unit_price, 1.0) ** 0.35
        * (1.05 if product.supplier_id in {4, 7} else 1.0)
        for product in products
    ]
    customer_weights = _customer_weights(master_data.customers)

    orders = []
    details = []
    order_products: dict[int, set[int]] = {}
    customer_by_id = {
        customer.customer_id: customer for customer in master_data.customers
    }
    horizon_days = _days_between(HORIZON_START, date(2025, 12, 31))

    for offset in range(ORDER_COUNT):
        order_id = FIRST_SYNTHETIC_ORDER_ID + offset
        order_date = HORIZON_START + timedelta(
            days=int(offset * horizon_days / ORDER_COUNT)
        )
        customer = _weighted_choice(rng, master_data.customers, customer_weights)
        if order_date.year == 2025 and order_date.month >= 10 and offset % 31 == 0:
            customer = customer_by_id[
                SCENARIO_B_CUSTOMER_IDS[offset % len(SCENARIO_B_CUSTOMER_IDS)]
            ]
        elif order_date.year == 2025 and order_date.month >= 10 and offset % 17 == 0:
            customer = customer_by_id[str(rng.choice(TOP_CUSTOMER_IDS))]
        elif (
            order_date.year == 2025
            and order_date.month in {7, 8, 9, 10}
            and offset % 23 == 0
        ):
            customer = customer_by_id[str(rng.choice(TOP_CUSTOMER_IDS))]
        elif order_date.year == 2025 and rng.random() < 0.42:
            customer = customer_by_id[str(rng.choice(TOP_CUSTOMER_IDS))]

        employee_id = int(rng.choice(master_data.employee_ids))
        ship_via = int(rng.choice(master_data.shipper_ids))
        required_date = order_date + timedelta(days=int(rng.integers(14, 29)))
        shipped_date = order_date + timedelta(days=int(rng.integers(1, 6)))
        freight = round(float(rng.lognormal(mean=3.2, sigma=0.45)), 2)
        orders.append(
            (
                order_id,
                customer.customer_id,
                employee_id,
                order_date,
                required_date,
                shipped_date,
                ship_via,
                freight,
                customer.company_name[:40],
                customer.address,
                customer.city,
                customer.region,
                customer.postal_code,
                customer.country,
            )
        )

        line_count = int(rng.choice([1, 2, 3, 4], p=[0.42, 0.34, 0.18, 0.06]))
        chosen: set[int] = set()
        order_supplier: int | None = None
        for _ in range(line_count):
            product = _weighted_choice(rng, products, product_weights)
            attempts = 0
            while (
                product.product_id in chosen
                or _scenario_conflict(order_supplier, product.supplier_id)
            ) and attempts < 8:
                product = _weighted_choice(rng, products, product_weights)
                attempts += 1
            if product.product_id in chosen or _scenario_conflict(
                order_supplier, product.supplier_id
            ):
                continue
            chosen.add(product.product_id)
            if product.supplier_id in SCENARIO_SUPPLIERS:
                order_supplier = product.supplier_id
            trend = 1 + (order_date.year - 2020) * 0.025
            seasonal = _seasonality(order_date.month, product.category_id)
            quantity = int(rng.integers(4, 42))
            if customer.customer_id in TOP_CUSTOMER_IDS and order_date.year == 2025:
                quantity = int(quantity * 2.3)
            unit_price = round(product.unit_price * trend * seasonal, 2)
            discount = float(
                rng.choice([0, 0.05, 0.1, 0.15], p=[0.68, 0.2, 0.09, 0.03])
            )
            details.append(
                (order_id, product.product_id, unit_price, quantity, discount)
            )
        order_products[order_id] = chosen

    _inject_scenario_lines(orders, details, order_products, products_by_id)
    return {
        "orders": orders,
        "order_details": details,
        "order_products": order_products,
    }


def _inject_scenario_lines(
    orders: list,
    details: list,
    order_products: dict[int, set[int]],
    products: dict[int, Product],
) -> None:
    order_customer = {order[0]: order[1] for order in orders}
    # Add high-value scenario products onto deterministic existing orders. Product
    # uniqueness per order is guaranteed via order_products, and the scenario-supplier
    # exclusivity guard keeps each order anchored to a single scenario.
    for order_id in range(
        FIRST_SYNTHETIC_ORDER_ID,
        FIRST_SYNTHETIC_ORDER_ID + ORDER_COUNT,
    ):
        month_index = order_id - FIRST_SYNTHETIC_ORDER_ID
        synthetic_date = HORIZON_START + timedelta(
            days=int(
                month_index
                * _days_between(HORIZON_START, date(2025, 12, 31))
                / ORDER_COUNT
            )
        )
        if synthetic_date.year != 2025:
            continue
        customer_id = order_customer[order_id]
        if (
            synthetic_date.month >= 10
            and customer_id in TOP_CUSTOMER_IDS
            and month_index % 17 == 0
        ):
            _append_unique_detail(
                details, order_products, order_id, TOKYO_PRODUCTS, products, 95
            )
        if (
            synthetic_date.month >= 10
            and customer_id in SCENARIO_B_CUSTOMER_IDS
            and month_index % 31 == 0
        ):
            _append_unique_detail(
                details, order_products, order_id, EXOTIC_PRODUCTS, products, 8
            )
        if (
            synthetic_date.month in {7, 8, 9, 10}
            and customer_id in TOP_CUSTOMER_IDS
            and month_index % 23 == 0
        ):
            _append_unique_detail(
                details, order_products, order_id, PAVLOVA_PRODUCTS, products, 78
            )


def _append_unique_detail(
    details: list,
    order_products: dict[int, set[int]],
    order_id: int,
    product_ids: tuple[int, ...],
    products: dict[int, Product],
    quantity: int,
) -> None:
    existing = order_products[order_id]
    existing_supplier = next(
        (
            products[pid].supplier_id
            for pid in existing
            if products[pid].supplier_id in SCENARIO_SUPPLIERS
        ),
        None,
    )
    for product_id in product_ids:
        if product_id not in existing:
            product = products[product_id]
            if _scenario_conflict(existing_supplier, product.supplier_id):
                return
            details.append(
                (
                    order_id,
                    product_id,
                    round(product.unit_price * 1.16, 2),
                    quantity,
                    0.0,
                )
            )
            existing.add(product_id)
            return
