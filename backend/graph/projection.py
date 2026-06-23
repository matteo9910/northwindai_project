from __future__ import annotations

import argparse
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

import psycopg
from neo4j import Driver

from backend.config import Settings, get_settings
from backend.graph.connection import neo4j_driver

PROJECTION_VERSION = "v1"
BATCH_SIZE = 1000
SUPPLIER_RULE_NAME = "supplier_projection"
PRODUCT_RULE_NAME = "product_projection"
SUPPLIES_RULE_NAME = "supplier_to_product_projection"
CUSTOMER_RULE_NAME = "customer_projection"
ORDER_RULE_NAME = "order_projection"
SHIPMENT_RULE_NAME = "shipment_projection"
PLACED_RULE_NAME = "customer_placed_order_projection"
CONTAINS_RULE_NAME = "order_contains_product_projection"
FULFILLED_BY_RULE_NAME = "order_fulfilled_by_shipment_projection"
SHIPMENT_DELAY_RULE_NAME = "shipment_delay_event"
CUSTOMER_COMPLAINT_RULE_NAME = "customer_complaint_event"
POSSIBLY_RELATED_RULE_NAME = "delay_complaint_possibly_related"
PLAUSIBLE_LINK_TIME_WINDOW_DAYS = 14
PLAUSIBLE_LINK_CONFIDENCE = 0.8

GRAPH_CONSTRAINTS = [
    """
    CREATE CONSTRAINT supplier_id_unique IF NOT EXISTS
    FOR (n:Supplier) REQUIRE n.supplier_id IS UNIQUE
    """,
    """
    CREATE CONSTRAINT product_id_unique IF NOT EXISTS
    FOR (n:Product) REQUIRE n.product_id IS UNIQUE
    """,
    """
    CREATE CONSTRAINT customer_id_unique IF NOT EXISTS
    FOR (n:Customer) REQUIRE n.customer_id IS UNIQUE
    """,
    """
    CREATE CONSTRAINT order_id_unique IF NOT EXISTS
    FOR (n:Order) REQUIRE n.order_id IS UNIQUE
    """,
    """
    CREATE CONSTRAINT shipment_id_unique IF NOT EXISTS
    FOR (n:Shipment) REQUIRE n.shipment_id IS UNIQUE
    """,
    """
    CREATE CONSTRAINT shipment_delay_event_shipment_id_unique IF NOT EXISTS
    FOR (n:ShipmentDelayEvent) REQUIRE n.shipment_id IS UNIQUE
    """,
    """
    CREATE CONSTRAINT customer_complaint_event_id_unique IF NOT EXISTS
    FOR (n:CustomerComplaintEvent) REQUIRE n.communication_id IS UNIQUE
    """,
]

GRAPH_INDEXES = [
    """
    CREATE INDEX supplier_company_name_index IF NOT EXISTS
    FOR (n:Supplier) ON (n.company_name)
    """,
]

SUPPLIERS_SQL = """
select supplier_id, company_name
from erp_core.suppliers
order by supplier_id
""".strip()

PRODUCTS_SQL = """
select product_id, product_name, supplier_id
from erp_core.products
where supplier_id is not null
order by product_id
""".strip()

CUSTOMERS_SQL = """
select customer_id, company_name
from erp_core.customers
order by customer_id
""".strip()

ORDERS_SQL = """
select order_id, customer_id, order_date
from erp_core.orders
where customer_id is not null
order by order_id
""".strip()

SHIPMENTS_SQL = """
select shipment_id,
       order_id,
       expected_delivery_date,
       actual_delivery_date,
       delay_days,
       status
from erp_core.shipments
order by shipment_id
""".strip()

ORDER_DETAILS_SQL = """
select order_id, product_id
from erp_core.order_details
order by order_id, product_id
""".strip()

SHIPMENT_DELAYS_SQL = """
select shipment_id,
       expected_delivery_date,
       actual_delivery_date,
       delay_days
from erp_core.shipments
where delay_days > 0
order by shipment_id
""".strip()

COMPLAINTS_SQL = """
select communication_id,
       customer_id,
       order_id,
       product_id,
       channel,
       contact_reason,
       sentiment,
       occurred_at
from erp_docs.customer_communications
where contact_reason = 'complaint'
order by communication_id
""".strip()

PLAUSIBLE_LINKS_SQL = """
select sh.shipment_id, cc.communication_id
from erp_core.shipments sh
join erp_docs.customer_communications cc on cc.order_id = sh.order_id
where sh.delay_days > 0
  and sh.actual_delivery_date is not null
  and cc.contact_reason = 'complaint'
  and cc.occurred_at >= sh.actual_delivery_date::timestamptz
  and cc.occurred_at <= (
      sh.actual_delivery_date + (%s * interval '1 day')
  )::timestamptz
  and (
      lower(coalesce(cc.body, '')) like '%%delay%%'
      or lower(coalesce(cc.body, '')) like '%%late%%'
  )
order by sh.shipment_id, cc.communication_id
""".strip()

SUPPLIER_MERGE = """
MERGE (s:Supplier {supplier_id: $supplier_id})
SET s.company_name = $company_name,
    s.source_system = 'postgresql',
    s.source_schema = 'erp_core',
    s.source_table = 'suppliers',
    s.source_pk = $supplier_id,
    s.projection_version = $version,
    s.rule_name = $rule_name,
    s.rule_version = $rule_version
""".strip()

PRODUCT_MERGE = """
MERGE (p:Product {product_id: $product_id})
SET p.product_name = $product_name,
    p.supplier_id = $supplier_id,
    p.source_system = 'postgresql',
    p.source_schema = 'erp_core',
    p.source_table = 'products',
    p.source_pk = $product_id,
    p.projection_version = $version,
    p.rule_name = $rule_name,
    p.rule_version = $rule_version
""".strip()

SUPPLIES_MERGE = """
MATCH (s:Supplier {supplier_id: $supplier_id})
MATCH (p:Product {product_id: $product_id})
MERGE (s)-[r:SUPPLIES]->(p)
SET r.source_system = 'postgresql',
    r.source_schema = 'erp_core',
    r.source_table = 'products',
    r.source_pk = $product_id,
    r.source_column = 'supplier_id',
    r.projection_version = $version,
    r.rule_name = $rule_name,
    r.rule_version = $rule_version
""".strip()

SUPPLIER_MERGE_BATCH = """
UNWIND $rows AS row
MERGE (s:Supplier {supplier_id: row.supplier_id})
SET s.company_name = row.company_name,
    s.source_system = 'postgresql',
    s.source_schema = 'erp_core',
    s.source_table = 'suppliers',
    s.source_pk = row.supplier_id,
    s.projection_version = $version,
    s.rule_name = $rule_name,
    s.rule_version = $rule_version
""".strip()

PRODUCT_MERGE_BATCH = """
UNWIND $rows AS row
MERGE (p:Product {product_id: row.product_id})
SET p.product_name = row.product_name,
    p.supplier_id = row.supplier_id,
    p.source_system = 'postgresql',
    p.source_schema = 'erp_core',
    p.source_table = 'products',
    p.source_pk = row.product_id,
    p.projection_version = $version,
    p.rule_name = $rule_name,
    p.rule_version = $rule_version
""".strip()

SUPPLIES_MERGE_BATCH = """
UNWIND $rows AS row
MATCH (s:Supplier {supplier_id: row.supplier_id})
MATCH (p:Product {product_id: row.product_id})
MERGE (s)-[r:SUPPLIES]->(p)
SET r.source_system = 'postgresql',
    r.source_schema = 'erp_core',
    r.source_table = 'products',
    r.source_pk = row.product_id,
    r.source_column = 'supplier_id',
    r.projection_version = $version,
    r.rule_name = $rule_name,
    r.rule_version = $rule_version
""".strip()

CUSTOMER_MERGE = """
MERGE (c:Customer {customer_id: $customer_id})
SET c.company_name = $company_name,
    c.source_system = 'postgresql',
    c.source_schema = 'erp_core',
    c.source_table = 'customers',
    c.source_pk = $customer_id,
    c.projection_version = $version,
    c.rule_name = $rule_name,
    c.rule_version = $rule_version
""".strip()

CUSTOMER_MERGE_BATCH = """
UNWIND $rows AS row
MERGE (c:Customer {customer_id: row.customer_id})
SET c.company_name = row.company_name,
    c.source_system = 'postgresql',
    c.source_schema = 'erp_core',
    c.source_table = 'customers',
    c.source_pk = row.customer_id,
    c.projection_version = $version,
    c.rule_name = $rule_name,
    c.rule_version = $rule_version
""".strip()

ORDER_MERGE = """
MERGE (o:Order {order_id: $order_id})
SET o.customer_id = $customer_id,
    o.order_date = $order_date,
    o.source_system = 'postgresql',
    o.source_schema = 'erp_core',
    o.source_table = 'orders',
    o.source_pk = $order_id,
    o.projection_version = $version,
    o.rule_name = $rule_name,
    o.rule_version = $rule_version
""".strip()

ORDER_MERGE_BATCH = """
UNWIND $rows AS row
MERGE (o:Order {order_id: row.order_id})
SET o.customer_id = row.customer_id,
    o.order_date = row.order_date,
    o.source_system = 'postgresql',
    o.source_schema = 'erp_core',
    o.source_table = 'orders',
    o.source_pk = row.order_id,
    o.projection_version = $version,
    o.rule_name = $rule_name,
    o.rule_version = $rule_version
""".strip()

SHIPMENT_MERGE = """
MERGE (sh:Shipment {shipment_id: $shipment_id})
SET sh.order_id = $order_id,
    sh.expected_delivery_date = $expected_delivery_date,
    sh.actual_delivery_date = $actual_delivery_date,
    sh.delay_days = $delay_days,
    sh.status = $status,
    sh.source_system = 'postgresql',
    sh.source_schema = 'erp_core',
    sh.source_table = 'shipments',
    sh.source_pk = $shipment_id,
    sh.projection_version = $version,
    sh.rule_name = $rule_name,
    sh.rule_version = $rule_version
""".strip()

SHIPMENT_MERGE_BATCH = """
UNWIND $rows AS row
MERGE (sh:Shipment {shipment_id: row.shipment_id})
SET sh.order_id = row.order_id,
    sh.expected_delivery_date = row.expected_delivery_date,
    sh.actual_delivery_date = row.actual_delivery_date,
    sh.delay_days = row.delay_days,
    sh.status = row.status,
    sh.source_system = 'postgresql',
    sh.source_schema = 'erp_core',
    sh.source_table = 'shipments',
    sh.source_pk = row.shipment_id,
    sh.projection_version = $version,
    sh.rule_name = $rule_name,
    sh.rule_version = $rule_version
""".strip()

PLACED_MERGE = """
MATCH (c:Customer {customer_id: $customer_id})
MATCH (o:Order {order_id: $order_id})
MERGE (c)-[r:PLACED]->(o)
SET r.source_system = 'postgresql',
    r.source_schema = 'erp_core',
    r.source_table = 'orders',
    r.source_pk = $order_id,
    r.source_column = 'customer_id',
    r.projection_version = $version,
    r.rule_name = $rule_name,
    r.rule_version = $rule_version
""".strip()

PLACED_MERGE_BATCH = """
UNWIND $rows AS row
MATCH (c:Customer {customer_id: row.customer_id})
MATCH (o:Order {order_id: row.order_id})
MERGE (c)-[r:PLACED]->(o)
SET r.source_system = 'postgresql',
    r.source_schema = 'erp_core',
    r.source_table = 'orders',
    r.source_pk = row.order_id,
    r.source_column = 'customer_id',
    r.projection_version = $version,
    r.rule_name = $rule_name,
    r.rule_version = $rule_version
""".strip()

CONTAINS_MERGE = """
MATCH (o:Order {order_id: $order_id})
MATCH (p:Product {product_id: $product_id})
MERGE (o)-[r:CONTAINS]->(p)
SET r.source_system = 'postgresql',
    r.source_schema = 'erp_core',
    r.source_table = 'order_details',
    r.source_pk = $source_pk,
    r.source_order_id = $order_id,
    r.source_product_id = $product_id,
    r.projection_version = $version,
    r.rule_name = $rule_name,
    r.rule_version = $rule_version
""".strip()

CONTAINS_MERGE_BATCH = """
UNWIND $rows AS row
MATCH (o:Order {order_id: row.order_id})
MATCH (p:Product {product_id: row.product_id})
MERGE (o)-[r:CONTAINS]->(p)
SET r.source_system = 'postgresql',
    r.source_schema = 'erp_core',
    r.source_table = 'order_details',
    r.source_pk = row.source_pk,
    r.source_order_id = row.order_id,
    r.source_product_id = row.product_id,
    r.projection_version = $version,
    r.rule_name = $rule_name,
    r.rule_version = $rule_version
""".strip()

FULFILLED_BY_MERGE = """
MATCH (o:Order {order_id: $order_id})
MATCH (sh:Shipment {shipment_id: $shipment_id})
MERGE (o)-[r:FULFILLED_BY]->(sh)
SET r.source_system = 'postgresql',
    r.source_schema = 'erp_core',
    r.source_table = 'shipments',
    r.source_pk = $shipment_id,
    r.source_column = 'order_id',
    r.projection_version = $version,
    r.rule_name = $rule_name,
    r.rule_version = $rule_version
""".strip()

FULFILLED_BY_MERGE_BATCH = """
UNWIND $rows AS row
MATCH (o:Order {order_id: row.order_id})
MATCH (sh:Shipment {shipment_id: row.shipment_id})
MERGE (o)-[r:FULFILLED_BY]->(sh)
SET r.source_system = 'postgresql',
    r.source_schema = 'erp_core',
    r.source_table = 'shipments',
    r.source_pk = row.shipment_id,
    r.source_column = 'order_id',
    r.projection_version = $version,
    r.rule_name = $rule_name,
    r.rule_version = $rule_version
""".strip()

SHIPMENT_DELAY_EVENT_MERGE = """
MATCH (sh:Shipment {shipment_id: $shipment_id})
MERGE (e:ShipmentDelayEvent {shipment_id: $shipment_id})
SET e.delay_days = $delay_days,
    e.expected_delivery_date = $expected_delivery_date,
    e.actual_delivery_date = $actual_delivery_date,
    e.source_system = 'postgresql',
    e.source_schema = 'erp_core',
    e.source_table = 'shipments',
    e.source_pk = $shipment_id,
    e.derived_from = 'erp_core.shipments',
    e.projection_version = $version,
    e.rule_name = $rule_name,
    e.rule_version = $rule_version
MERGE (sh)-[r:HAS_DELAY_EVENT]->(e)
SET r.source_system = 'postgresql',
    r.source_schema = 'erp_core',
    r.source_table = 'shipments',
    r.source_pk = $shipment_id,
    r.derived_from = 'erp_core.shipments',
    r.projection_version = $version,
    r.rule_name = $rule_name,
    r.rule_version = $rule_version
""".strip()

SHIPMENT_DELAY_EVENT_MERGE_BATCH = """
UNWIND $rows AS row
MATCH (sh:Shipment {shipment_id: row.shipment_id})
MERGE (e:ShipmentDelayEvent {shipment_id: row.shipment_id})
SET e.delay_days = row.delay_days,
    e.expected_delivery_date = row.expected_delivery_date,
    e.actual_delivery_date = row.actual_delivery_date,
    e.source_system = 'postgresql',
    e.source_schema = 'erp_core',
    e.source_table = 'shipments',
    e.source_pk = row.shipment_id,
    e.derived_from = 'erp_core.shipments',
    e.projection_version = $version,
    e.rule_name = $rule_name,
    e.rule_version = $rule_version
MERGE (sh)-[r:HAS_DELAY_EVENT]->(e)
SET r.source_system = 'postgresql',
    r.source_schema = 'erp_core',
    r.source_table = 'shipments',
    r.source_pk = row.shipment_id,
    r.derived_from = 'erp_core.shipments',
    r.projection_version = $version,
    r.rule_name = $rule_name,
    r.rule_version = $rule_version
""".strip()

CUSTOMER_COMPLAINT_EVENT_MERGE = """
MERGE (e:CustomerComplaintEvent {communication_id: $communication_id})
SET e.customer_id = $customer_id,
    e.order_id = $order_id,
    e.product_id = $product_id,
    e.channel = $channel,
    e.contact_reason = $contact_reason,
    e.sentiment = $sentiment,
    e.occurred_at = $occurred_at,
    e.source_system = 'postgresql',
    e.source_schema = 'erp_docs',
    e.source_table = 'customer_communications',
    e.source_pk = $communication_id,
    e.derived_from = 'erp_docs.customer_communications',
    e.projection_version = $version,
    e.rule_name = $rule_name,
    e.rule_version = $rule_version
""".strip()

CUSTOMER_COMPLAINT_EVENT_MERGE_BATCH = """
UNWIND $rows AS row
MERGE (e:CustomerComplaintEvent {communication_id: row.communication_id})
SET e.customer_id = row.customer_id,
    e.order_id = row.order_id,
    e.product_id = row.product_id,
    e.channel = row.channel,
    e.contact_reason = row.contact_reason,
    e.sentiment = row.sentiment,
    e.occurred_at = row.occurred_at,
    e.source_system = 'postgresql',
    e.source_schema = 'erp_docs',
    e.source_table = 'customer_communications',
    e.source_pk = row.communication_id,
    e.derived_from = 'erp_docs.customer_communications',
    e.projection_version = $version,
    e.rule_name = $rule_name,
    e.rule_version = $rule_version
""".strip()

COMPLAINT_RAISED_BY_MERGE = """
MATCH (e:CustomerComplaintEvent {communication_id: $communication_id})
MATCH (c:Customer {customer_id: $customer_id})
MERGE (e)-[r:RAISED_BY]->(c)
SET r.source_system = 'postgresql',
    r.source_schema = 'erp_docs',
    r.source_table = 'customer_communications',
    r.source_pk = $communication_id,
    r.source_column = 'customer_id',
    r.derived_from = 'erp_docs.customer_communications',
    r.projection_version = $version,
    r.rule_name = $rule_name,
    r.rule_version = $rule_version
""".strip()

COMPLAINT_RAISED_BY_MERGE_BATCH = """
UNWIND $rows AS row
MATCH (e:CustomerComplaintEvent {communication_id: row.communication_id})
MATCH (c:Customer {customer_id: row.customer_id})
MERGE (e)-[r:RAISED_BY]->(c)
SET r.source_system = 'postgresql',
    r.source_schema = 'erp_docs',
    r.source_table = 'customer_communications',
    r.source_pk = row.communication_id,
    r.source_column = 'customer_id',
    r.derived_from = 'erp_docs.customer_communications',
    r.projection_version = $version,
    r.rule_name = $rule_name,
    r.rule_version = $rule_version
""".strip()

COMPLAINT_ABOUT_ORDER_MERGE = """
MATCH (e:CustomerComplaintEvent {communication_id: $communication_id})
MATCH (o:Order {order_id: $order_id})
MERGE (e)-[r:ABOUT_ORDER]->(o)
SET r.source_system = 'postgresql',
    r.source_schema = 'erp_docs',
    r.source_table = 'customer_communications',
    r.source_pk = $communication_id,
    r.source_column = 'order_id',
    r.derived_from = 'erp_docs.customer_communications',
    r.projection_version = $version,
    r.rule_name = $rule_name,
    r.rule_version = $rule_version
""".strip()

COMPLAINT_ABOUT_ORDER_MERGE_BATCH = """
UNWIND $rows AS row
MATCH (e:CustomerComplaintEvent {communication_id: row.communication_id})
MATCH (o:Order {order_id: row.order_id})
MERGE (e)-[r:ABOUT_ORDER]->(o)
SET r.source_system = 'postgresql',
    r.source_schema = 'erp_docs',
    r.source_table = 'customer_communications',
    r.source_pk = row.communication_id,
    r.source_column = 'order_id',
    r.derived_from = 'erp_docs.customer_communications',
    r.projection_version = $version,
    r.rule_name = $rule_name,
    r.rule_version = $rule_version
""".strip()

COMPLAINT_ABOUT_PRODUCT_MERGE = """
MATCH (e:CustomerComplaintEvent {communication_id: $communication_id})
MATCH (p:Product {product_id: $product_id})
MERGE (e)-[r:ABOUT_PRODUCT]->(p)
SET r.source_system = 'postgresql',
    r.source_schema = 'erp_docs',
    r.source_table = 'customer_communications',
    r.source_pk = $communication_id,
    r.source_column = 'product_id',
    r.derived_from = 'erp_docs.customer_communications',
    r.projection_version = $version,
    r.rule_name = $rule_name,
    r.rule_version = $rule_version
""".strip()

COMPLAINT_ABOUT_PRODUCT_MERGE_BATCH = """
UNWIND $rows AS row
MATCH (e:CustomerComplaintEvent {communication_id: row.communication_id})
MATCH (p:Product {product_id: row.product_id})
MERGE (e)-[r:ABOUT_PRODUCT]->(p)
SET r.source_system = 'postgresql',
    r.source_schema = 'erp_docs',
    r.source_table = 'customer_communications',
    r.source_pk = row.communication_id,
    r.source_column = 'product_id',
    r.derived_from = 'erp_docs.customer_communications',
    r.projection_version = $version,
    r.rule_name = $rule_name,
    r.rule_version = $rule_version
""".strip()

POSSIBLY_RELATED_MERGE = """
MATCH (d:ShipmentDelayEvent {shipment_id: $shipment_id})
MATCH (c:CustomerComplaintEvent {communication_id: $communication_id})
MERGE (d)-[r:POSSIBLY_RELATED_TO]->(c)
SET r.confidence = $confidence,
    r.matching_reason = $matching_reason,
    r.time_window_days = $time_window_days,
    r.evidence = $evidence,
    r.source_system = 'postgresql',
    r.source_schema = 'erp_core+erp_docs',
    r.source_table = 'shipments+customer_communications',
    r.source_pk = $source_pk,
    r.derived_from = 'erp_core.shipments+erp_docs.customer_communications',
    r.projection_version = $version,
    r.rule_name = $rule_name,
    r.rule_version = $rule_version
""".strip()

POSSIBLY_RELATED_MERGE_BATCH = """
UNWIND $rows AS row
MATCH (d:ShipmentDelayEvent {shipment_id: row.shipment_id})
MATCH (c:CustomerComplaintEvent {communication_id: row.communication_id})
MERGE (d)-[r:POSSIBLY_RELATED_TO]->(c)
SET r.confidence = row.confidence,
    r.matching_reason = row.matching_reason,
    r.time_window_days = row.time_window_days,
    r.evidence = row.evidence,
    r.source_system = 'postgresql',
    r.source_schema = 'erp_core+erp_docs',
    r.source_table = 'shipments+customer_communications',
    r.source_pk = row.source_pk,
    r.derived_from = 'erp_core.shipments+erp_docs.customer_communications',
    r.projection_version = $version,
    r.rule_name = $rule_name,
    r.rule_version = $rule_version
""".strip()

RESET_POSSIBLY_RELATED = """
MATCH (:ShipmentDelayEvent)-[r:POSSIBLY_RELATED_TO]->(:CustomerComplaintEvent)
DELETE r
""".strip()
RESET_ABOUT_PRODUCT = """
MATCH (:CustomerComplaintEvent)-[r:ABOUT_PRODUCT]->(:Product) DELETE r
""".strip()
RESET_ABOUT_ORDER = """
MATCH (:CustomerComplaintEvent)-[r:ABOUT_ORDER]->(:Order) DELETE r
""".strip()
RESET_RAISED_BY = """
MATCH (:CustomerComplaintEvent)-[r:RAISED_BY]->(:Customer) DELETE r
""".strip()
RESET_HAS_DELAY_EVENT = """
MATCH (:Shipment)-[r:HAS_DELAY_EVENT]->(:ShipmentDelayEvent) DELETE r
""".strip()
RESET_FULFILLED_BY = "MATCH (:Order)-[r:FULFILLED_BY]->(:Shipment) DELETE r"
RESET_CONTAINS = "MATCH (:Order)-[r:CONTAINS]->(:Product) DELETE r"
RESET_PLACED = "MATCH (:Customer)-[r:PLACED]->(:Order) DELETE r"
RESET_SUPPLIES = "MATCH (:Supplier)-[r:SUPPLIES]->(:Product) DELETE r"
RESET_COMPLAINT_EVENTS = "MATCH (n:CustomerComplaintEvent) DELETE n"
RESET_DELAY_EVENTS = "MATCH (n:ShipmentDelayEvent) DELETE n"
RESET_SHIPMENTS = "MATCH (n:Shipment) DELETE n"
RESET_ORDERS = "MATCH (n:Order) DELETE n"
RESET_CUSTOMERS = "MATCH (n:Customer) DELETE n"
RESET_PRODUCTS = "MATCH (n:Product) DELETE n"
RESET_SUPPLIERS = "MATCH (n:Supplier) DELETE n"


@dataclass(frozen=True)
class ProjectionSummary:
    suppliers: int
    products: int
    supplies_relationships: int
    customers: int
    orders: int
    shipments: int
    placed_relationships: int
    contains_relationships: int
    fulfilled_by_relationships: int
    shipment_delay_events: int
    customer_complaint_events: int
    possibly_related_relationships: int


def _fetch_rows(settings: Settings, sql: str) -> list[dict[str, Any]]:
    with psycopg.connect(settings.postgres_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
            columns = [desc.name for desc in cur.description or []]
            return [
                dict(zip(columns, row, strict=True))
                for row in cur.fetchall()
            ]


def _fetch_rows_with_params(
    settings: Settings,
    sql: str,
    params: tuple[Any, ...],
) -> list[dict[str, Any]]:
    with psycopg.connect(settings.postgres_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            columns = [desc.name for desc in cur.description or []]
            return [
                dict(zip(columns, row, strict=True))
                for row in cur.fetchall()
            ]


def _projection_params(rule_name: str) -> dict[str, str]:
    return {
        "version": PROJECTION_VERSION,
        "rule_name": rule_name,
        "rule_version": "v1",
    }


def _chunks(rows: list[dict[str, Any]], size: int = BATCH_SIZE) -> Iterable[list[dict]]:
    for index in range(0, len(rows), size):
        yield rows[index : index + size]


def _run_batches(
    driver: Driver,
    cypher: str,
    rows: list[dict[str, Any]],
    rule_name: str,
) -> None:
    if not rows:
        return
    params = _projection_params(rule_name)
    with driver.session() as session:
        for batch in _chunks(rows):
            session.run(cypher, {"rows": batch, **params}).consume()


def ensure_graph_schema(driver: Driver) -> None:
    with driver.session() as session:
        for query in [*GRAPH_CONSTRAINTS, *GRAPH_INDEXES]:
            session.run(query.strip()).consume()


def project_suppliers(driver: Driver, settings: Settings) -> int:
    rows = _fetch_rows(settings, SUPPLIERS_SQL)
    _run_batches(driver, SUPPLIER_MERGE_BATCH, rows, SUPPLIER_RULE_NAME)
    return len(rows)


def project_products(driver: Driver, settings: Settings) -> int:
    rows = _fetch_rows(settings, PRODUCTS_SQL)
    _run_batches(driver, PRODUCT_MERGE_BATCH, rows, PRODUCT_RULE_NAME)
    return len(rows)


def project_supplies(driver: Driver, settings: Settings) -> int:
    rows = _fetch_rows(settings, PRODUCTS_SQL)
    _run_batches(driver, SUPPLIES_MERGE_BATCH, rows, SUPPLIES_RULE_NAME)
    return len(rows)


def project_customers(driver: Driver, settings: Settings) -> int:
    rows = _fetch_rows(settings, CUSTOMERS_SQL)
    _run_batches(driver, CUSTOMER_MERGE_BATCH, rows, CUSTOMER_RULE_NAME)
    return len(rows)


def project_orders(driver: Driver, settings: Settings) -> int:
    rows = _fetch_rows(settings, ORDERS_SQL)
    _run_batches(driver, ORDER_MERGE_BATCH, rows, ORDER_RULE_NAME)
    return len(rows)


def project_shipments(driver: Driver, settings: Settings) -> int:
    rows = _fetch_rows(settings, SHIPMENTS_SQL)
    _run_batches(driver, SHIPMENT_MERGE_BATCH, rows, SHIPMENT_RULE_NAME)
    return len(rows)


def project_customer_placed_orders(driver: Driver, settings: Settings) -> int:
    rows = _fetch_rows(settings, ORDERS_SQL)
    _run_batches(driver, PLACED_MERGE_BATCH, rows, PLACED_RULE_NAME)
    return len(rows)


def project_order_contains_products(driver: Driver, settings: Settings) -> int:
    rows = _fetch_rows(settings, ORDER_DETAILS_SQL)
    rows = [
        {
            **row,
            "source_pk": f"{row['order_id']}:{row['product_id']}",
        }
        for row in rows
    ]
    _run_batches(driver, CONTAINS_MERGE_BATCH, rows, CONTAINS_RULE_NAME)
    return len(rows)


def project_order_fulfilled_by_shipments(
    driver: Driver,
    settings: Settings,
) -> int:
    rows = _fetch_rows(settings, SHIPMENTS_SQL)
    _run_batches(
        driver,
        FULFILLED_BY_MERGE_BATCH,
        rows,
        FULFILLED_BY_RULE_NAME,
    )
    return len(rows)


def derive_shipment_delay_events(driver: Driver, settings: Settings) -> int:
    rows = _fetch_rows(settings, SHIPMENT_DELAYS_SQL)
    _run_batches(
        driver,
        SHIPMENT_DELAY_EVENT_MERGE_BATCH,
        rows,
        SHIPMENT_DELAY_RULE_NAME,
    )
    return len(rows)


def derive_customer_complaint_events(driver: Driver, settings: Settings) -> int:
    rows = _fetch_rows(settings, COMPLAINTS_SQL)
    _run_batches(
        driver,
        CUSTOMER_COMPLAINT_EVENT_MERGE_BATCH,
        rows,
        CUSTOMER_COMPLAINT_RULE_NAME,
    )
    _run_batches(
        driver,
        COMPLAINT_RAISED_BY_MERGE_BATCH,
        rows,
        CUSTOMER_COMPLAINT_RULE_NAME,
    )
    _run_batches(
        driver,
        COMPLAINT_ABOUT_ORDER_MERGE_BATCH,
        [row for row in rows if row["order_id"] is not None],
        CUSTOMER_COMPLAINT_RULE_NAME,
    )
    _run_batches(
        driver,
        COMPLAINT_ABOUT_PRODUCT_MERGE_BATCH,
        [row for row in rows if row["product_id"] is not None],
        CUSTOMER_COMPLAINT_RULE_NAME,
    )
    return len(rows)


def derive_plausible_delay_complaint_links(
    driver: Driver,
    settings: Settings,
) -> int:
    rows = _fetch_rows_with_params(
        settings,
        PLAUSIBLE_LINKS_SQL,
        (PLAUSIBLE_LINK_TIME_WINDOW_DAYS,),
    )
    rows = [
        {
            **row,
            "confidence": PLAUSIBLE_LINK_CONFIDENCE,
            "matching_reason": "same_order_delay_keyword_after_delivery",
            "time_window_days": PLAUSIBLE_LINK_TIME_WINDOW_DAYS,
            "evidence": [
                f"erp_core.shipments:{row['shipment_id']}",
                "erp_docs.customer_communications:"
                f"{row['communication_id']}",
            ],
            "source_pk": f"{row['shipment_id']}:{row['communication_id']}",
        }
        for row in rows
    ]
    _run_batches(
        driver,
        POSSIBLY_RELATED_MERGE_BATCH,
        rows,
        POSSIBLY_RELATED_RULE_NAME,
    )
    return len(rows)


def reset_projection(driver: Driver) -> None:
    reset_queries = [
        RESET_POSSIBLY_RELATED,
        RESET_ABOUT_PRODUCT,
        RESET_ABOUT_ORDER,
        RESET_RAISED_BY,
        RESET_HAS_DELAY_EVENT,
        RESET_FULFILLED_BY,
        RESET_CONTAINS,
        RESET_PLACED,
        RESET_SUPPLIES,
        RESET_COMPLAINT_EVENTS,
        RESET_DELAY_EVENTS,
        RESET_SHIPMENTS,
        RESET_ORDERS,
        RESET_CUSTOMERS,
        RESET_PRODUCTS,
        RESET_SUPPLIERS,
    ]
    with driver.session() as session:
        for query in reset_queries:
            session.run(query).consume()


def project_all(
    settings: Settings | None = None,
    reset: bool = False,
) -> ProjectionSummary:
    settings = settings or get_settings()
    with neo4j_driver(settings) as driver:
        ensure_graph_schema(driver)
        if reset:
            reset_projection(driver)
        suppliers = project_suppliers(driver, settings)
        products = project_products(driver, settings)
        customers = project_customers(driver, settings)
        orders = project_orders(driver, settings)
        shipments = project_shipments(driver, settings)
        supplies_relationships = project_supplies(driver, settings)
        placed_relationships = project_customer_placed_orders(driver, settings)
        contains_relationships = project_order_contains_products(driver, settings)
        fulfilled_by_relationships = project_order_fulfilled_by_shipments(
            driver,
            settings,
        )
        shipment_delay_events = derive_shipment_delay_events(driver, settings)
        customer_complaint_events = derive_customer_complaint_events(
            driver,
            settings,
        )
        possibly_related_relationships = derive_plausible_delay_complaint_links(
            driver,
            settings,
        )
    return ProjectionSummary(
        suppliers=suppliers,
        products=products,
        supplies_relationships=supplies_relationships,
        customers=customers,
        orders=orders,
        shipments=shipments,
        placed_relationships=placed_relationships,
        contains_relationships=contains_relationships,
        fulfilled_by_relationships=fulfilled_by_relationships,
        shipment_delay_events=shipment_delay_events,
        customer_complaint_events=customer_complaint_events,
        possibly_related_relationships=possibly_related_relationships,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Project NorthwindAI graph data (Phase 05-06)."
    )
    parser.add_argument("--reset", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    summary = project_all(settings=get_settings(), reset=args.reset)
    print(
        "Projected "
        f"{summary.suppliers} suppliers, "
        f"{summary.products} products, "
        f"{summary.customers} customers, "
        f"{summary.orders} orders, "
        f"{summary.shipments} shipments, "
        f"{summary.supplies_relationships} SUPPLIES relationships, "
        f"{summary.placed_relationships} PLACED relationships, "
        f"{summary.contains_relationships} CONTAINS relationships, "
        f"{summary.fulfilled_by_relationships} FULFILLED_BY relationships, "
        f"{summary.shipment_delay_events} ShipmentDelayEvent nodes, "
        f"{summary.customer_complaint_events} CustomerComplaintEvent nodes, "
        f"{summary.possibly_related_relationships} POSSIBLY_RELATED_TO "
        "relationships."
    )


if __name__ == "__main__":
    main()

