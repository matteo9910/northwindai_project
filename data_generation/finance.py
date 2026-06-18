from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import numpy as np

from data_generation.masters import Product


def generate_invoices(
    orders: list,
    order_details: list,
    rng: np.random.Generator,
) -> list:
    totals: dict[int, Decimal] = {}
    for order_id, _product_id, unit_price, quantity, discount in order_details:
        line = (
            Decimal(str(unit_price))
            * Decimal(quantity)
            * (Decimal("1") - Decimal(str(discount)))
        )
        totals[order_id] = totals.get(order_id, Decimal("0")) + line

    invoices = []
    for index, order in enumerate(orders, start=1):
        order_id = order[0]
        order_date = order[3]
        amount = totals[order_id].quantize(Decimal("0.01"))
        tax = (amount * Decimal("0.08")).quantize(Decimal("0.01"))
        total = amount + tax
        due_date = order_date + timedelta(days=30)
        if order_date.year < 2025 or rng.random() < 0.88:
            payment_date = due_date - timedelta(days=int(rng.integers(-4, 16)))
            status = "paid" if payment_date <= date(2025, 12, 31) else "issued"
        else:
            payment_date = None
            status = str(rng.choice(["issued", "overdue"], p=[0.35, 0.65]))
        invoices.append(
            (
                f"INV-{order_date.year}-{index:05d}",
                order_id,
                order_date + timedelta(days=1),
                due_date,
                payment_date,
                amount,
                tax,
                total,
                status,
                str(rng.choice(["wire", "card", "ach"], p=[0.44, 0.28, 0.28])),
            )
        )
    return invoices


def generate_price_history(products: list[Product]) -> list:
    rows = []
    for product in products:
        old_price = None
        for year in range(2020, 2026):
            new_price = Decimal(
                str(round(product.unit_price * (1 + (year - 2020) * 0.025), 2))
            )
            rows.append((product.product_id, old_price, new_price, date(year, 1, 1)))
            old_price = new_price
    return rows
