from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Customer:
    customer_id: str
    company_name: str
    address: str | None
    city: str | None
    region: str | None
    postal_code: str | None
    country: str | None


@dataclass(frozen=True)
class Product:
    product_id: int
    product_name: str
    supplier_id: int
    category_id: int
    unit_price: float


@dataclass(frozen=True)
class MasterData:
    customers: list[Customer]
    products: list[Product]
    employee_ids: list[int]
    shipper_ids: list[int]


WAREHOUSES = [
    ("AMS-01", "Amsterdam Fulfillment", "Amsterdam, NL", "regional", 48000),
    ("BER-01", "Berlin Dry Goods", "Berlin, DE", "regional", 42000),
    ("LON-01", "London Cross Dock", "London, UK", "cross_dock", 26000),
    ("MAD-01", "Madrid Cold Chain", "Madrid, ES", "cold_chain", 32000),
]


def fetch_master_data(cur) -> MasterData:
    cur.execute(
        """
        select customer_id, company_name, address, city, region, postal_code, country
        from erp_core.customers
        order by customer_id
        """
    )
    customers = [Customer(*row) for row in cur.fetchall()]

    cur.execute(
        """
        select product_id, product_name, supplier_id, category_id,
               coalesce(unit_price, 10)
        from erp_core.products
        order by product_id
        """
    )
    products = [Product(*row) for row in cur.fetchall()]

    cur.execute("select employee_id from erp_core.employees order by employee_id")
    employee_ids = [row[0] for row in cur.fetchall()]

    cur.execute("select shipper_id from erp_core.shippers order by shipper_id")
    shipper_ids = [row[0] for row in cur.fetchall()]

    return MasterData(customers, products, employee_ids, shipper_ids)
