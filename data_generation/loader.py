from __future__ import annotations

from collections.abc import Sequence

import psycopg

from backend.config import get_settings
from data_generation.masters import WAREHOUSES


def connect():
    return psycopg.connect(get_settings().postgres_dsn)


def insert_many(cur, sql: str, rows: Sequence[tuple]) -> None:
    if rows:
        cur.executemany(sql, rows)


def load_generated_data(cur, data: dict[str, list]) -> None:
    insert_many(
        cur,
        """
        insert into erp_core.warehouses
            (code, name, location, warehouse_type, capacity_units)
        values (%s, %s, %s, %s, %s)
        """,
        WAREHOUSES,
    )
    insert_many(
        cur,
        """
        insert into erp_core.orders
            (order_id, customer_id, employee_id, order_date, required_date,
             shipped_date, ship_via, freight, ship_name, ship_address, ship_city,
             ship_region, ship_postal_code, ship_country)
        values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        data["orders"],
    )
    insert_many(
        cur,
        """
        insert into erp_core.order_details
            (order_id, product_id, unit_price, quantity, discount)
        values (%s, %s, %s, %s, %s)
        """,
        data["order_details"],
    )
    insert_many(
        cur,
        """
        insert into erp_core.shipments
            (order_id, carrier, shipper_id, expected_delivery_date, shipped_date,
             actual_delivery_date, status)
        values (%s, %s, %s, %s, %s, %s, %s)
        """,
        data["shipments"],
    )
    insert_many(
        cur,
        """
        insert into erp_core.invoices
            (invoice_number, order_id, invoice_date, due_date, payment_date,
             amount, tax_amount, total_amount, status, payment_method)
        values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        data["invoices"],
    )
    insert_many(
        cur,
        """
        insert into erp_core.inventory_movements
            (product_id, warehouse_id, movement_type, quantity, movement_date,
             reference)
        values (%s, %s, %s, %s, %s, %s)
        """,
        data["inventory_movements"],
    )
    insert_many(
        cur,
        """
        insert into erp_core.price_history
            (product_id, old_price, new_price, effective_date)
        values (%s, %s, %s, %s)
        """,
        data["price_history"],
    )
    insert_many(
        cur,
        """
        insert into erp_docs.supplier_contracts
            (supplier_id, contract_number, lead_time_days, start_date, end_date,
             minimum_order_value, status)
        values (%s, %s, %s, %s, %s, %s, %s)
        """,
        data["supplier_contracts"],
    )
    insert_many(
        cur,
        """
        insert into erp_docs.customer_communications
            (customer_id, order_id, product_id, channel, contact_reason, subject,
             body, sentiment, occurred_at)
        values (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        data["customer_communications"],
    )
    insert_many(
        cur,
        """
        insert into erp_docs.product_specifications
            (product_id, title, spec_text, attributes)
        values (%s, %s, %s, %s::jsonb)
        """,
        data["product_specifications"],
    )
    insert_many(
        cur,
        """
        insert into erp_docs.documents
            (doc_type, title, order_id, supplier_id, customer_id, file_path,
             status, metadata)
        values (%s, %s, %s, %s, %s, %s, %s, %s::jsonb)
        """,
        data["documents"],
    )
    insert_many(
        cur,
        """
        insert into erp_docs.document_entities
            (document_id, entity_type, entity_ref, mention, confidence)
        values (%s, %s, %s, %s, %s)
        """,
        data["document_entities"],
    )
