from __future__ import annotations

import argparse
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

import psycopg
from neo4j import Driver

from backend.config import Settings, get_settings
from backend.graph.complaint_issue_types import (
    COMPLAINT_ISSUE_TYPES,
    DELIVERY_DELAY,
    ComplaintIssueType,
    complaint_issue_type_for_subject,
)
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
CLASSIFIED_AS_RULE_NAME = "complaint_classified_as_issue"
SUPPORTED_BY_DELAY_RULE_NAME = "delivery_complaint_supported_by_delay"

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
    """
    CREATE CONSTRAINT delivery_delay_complaint_event_id_unique IF NOT EXISTS
    FOR (n:DeliveryDelayComplaintEvent) REQUIRE n.communication_id IS UNIQUE
    """,
    """
    CREATE CONSTRAINT packaging_quality_complaint_event_id_unique IF NOT EXISTS
    FOR (n:PackagingQualityComplaintEvent) REQUIRE n.communication_id IS UNIQUE
    """,
    """
    CREATE CONSTRAINT product_quality_complaint_event_id_unique IF NOT EXISTS
    FOR (n:ProductQualityComplaintEvent) REQUIRE n.communication_id IS UNIQUE
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
       subject,
       body,
       sentiment,
       occurred_at
from erp_docs.customer_communications
where contact_reason = 'complaint'
order by communication_id
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

CUSTOMER_COMPLAINT_EVENT_MERGE_BATCH = """
UNWIND $rows AS row
MERGE (e:CustomerComplaintEvent {communication_id: row.communication_id})
SET e.customer_id = row.customer_id,
    e.order_id = row.order_id,
    e.product_id = row.product_id,
    e.channel = row.channel,
    e.contact_reason = row.contact_reason,
    e.subject = row.subject,
    e.issue_type = row.issue_type,
    e.body = row.body,
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

def issue_event_merge_batch(label: str) -> str:
    return f"""
UNWIND $rows AS row
MERGE (e:{label} {{communication_id: row.communication_id}})
SET e.customer_id = row.customer_id,
    e.order_id = row.order_id,
    e.product_id = row.product_id,
    e.subject = row.subject,
    e.issue_type = row.issue_type,
    e.body = row.body,
    e.sentiment = row.sentiment,
    e.occurred_at = row.occurred_at,
    e.source_system = 'postgresql',
    e.source_schema = 'erp_docs',
    e.source_table = 'customer_communications',
    e.source_pk = row.communication_id,
    e.derived_from = 'erp_docs.customer_communications.subject',
    e.projection_version = $version,
    e.rule_name = $rule_name,
    e.rule_version = $rule_version
""".strip()


DELIVERY_DELAY_EVENT_MERGE_BATCH = """
UNWIND $rows AS row
MATCH (o:Order {order_id: row.order_id})-[:CONTAINS]->(
  :Product {product_id: row.product_id}
)
MATCH (o)-[:FULFILLED_BY]->(:Shipment)-[:HAS_DELAY_EVENT]->(
  :ShipmentDelayEvent
)
MERGE (e:DeliveryDelayComplaintEvent {communication_id: row.communication_id})
SET e.customer_id = row.customer_id,
    e.order_id = row.order_id,
    e.product_id = row.product_id,
    e.subject = row.subject,
    e.issue_type = row.issue_type,
    e.body = row.body,
    e.sentiment = row.sentiment,
    e.occurred_at = row.occurred_at,
    e.source_system = 'postgresql',
    e.source_schema = 'erp_docs',
    e.source_table = 'customer_communications',
    e.source_pk = row.communication_id,
    e.derived_from = 'erp_docs.customer_communications.subject+erp_core.shipments',
    e.projection_version = $version,
    e.rule_name = $rule_name,
    e.rule_version = $rule_version
""".strip()


def issue_event_classified_as_batch(label: str) -> str:
    return f"""
UNWIND $rows AS row
MATCH (c:CustomerComplaintEvent {{communication_id: row.communication_id}})
MATCH (e:{label} {{communication_id: row.communication_id}})
MERGE (c)-[r:CLASSIFIED_AS]->(e)
SET r.source_system = 'postgresql',
    r.source_schema = 'erp_docs',
    r.source_table = 'customer_communications',
    r.source_pk = row.communication_id,
    r.source_column = 'subject',
    r.derived_from = 'erp_docs.customer_communications.subject',
    r.projection_version = $version,
    r.rule_name = $rule_name,
    r.rule_version = $rule_version
""".strip()


def issue_event_raised_by_batch(label: str) -> str:
    return f"""
UNWIND $rows AS row
MATCH (e:{label} {{communication_id: row.communication_id}})
MATCH (c:Customer {{customer_id: row.customer_id}})
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


def issue_event_about_order_batch(label: str) -> str:
    return f"""
UNWIND $rows AS row
MATCH (e:{label} {{communication_id: row.communication_id}})
MATCH (o:Order {{order_id: row.order_id}})
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


def issue_event_about_product_batch(label: str) -> str:
    return f"""
UNWIND $rows AS row
MATCH (e:{label} {{communication_id: row.communication_id}})
MATCH (p:Product {{product_id: row.product_id}})
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


DELIVERY_SUPPORTED_BY_DELAY_BATCH = """
UNWIND $rows AS row
MATCH (e:DeliveryDelayComplaintEvent {communication_id: row.communication_id})
MATCH (o:Order {order_id: row.order_id})-[:CONTAINS]->(
  :Product {product_id: row.product_id}
)
MATCH (o)-[:FULFILLED_BY]->(:Shipment)-[:HAS_DELAY_EVENT]->(
  delay:ShipmentDelayEvent
)
MERGE (e)-[r:SUPPORTED_BY_DELAY]->(delay)
SET r.source_system = 'postgresql',
    r.source_schema = 'erp_core+erp_docs',
    r.source_table = 'shipments+customer_communications',
    r.source_pk = row.communication_id,
    r.derived_from = 'erp_core.shipments+erp_docs.customer_communications.subject',
    r.projection_version = $version,
    r.rule_name = $rule_name,
    r.rule_version = $rule_version
""".strip()

RESET_POSSIBLY_RELATED = """
MATCH (:ShipmentDelayEvent)-[r:POSSIBLY_RELATED_TO]->(:CustomerComplaintEvent)
DELETE r
""".strip()
RESET_SUPPORTED_BY_DELAY = """
MATCH (:DeliveryDelayComplaintEvent)-[r:SUPPORTED_BY_DELAY]->(:ShipmentDelayEvent)
DELETE r
""".strip()
RESET_CLASSIFIED_AS = """
MATCH (:CustomerComplaintEvent)-[r:CLASSIFIED_AS]->() DELETE r
""".strip()
RESET_DELIVERY_EVENT_ABOUT_PRODUCT = """
MATCH (:DeliveryDelayComplaintEvent)-[r:ABOUT_PRODUCT]->(:Product) DELETE r
""".strip()
RESET_DELIVERY_EVENT_ABOUT_ORDER = """
MATCH (:DeliveryDelayComplaintEvent)-[r:ABOUT_ORDER]->(:Order) DELETE r
""".strip()
RESET_DELIVERY_EVENT_RAISED_BY = """
MATCH (:DeliveryDelayComplaintEvent)-[r:RAISED_BY]->(:Customer) DELETE r
""".strip()
RESET_PACKAGING_EVENT_ABOUT_PRODUCT = """
MATCH (:PackagingQualityComplaintEvent)-[r:ABOUT_PRODUCT]->(:Product) DELETE r
""".strip()
RESET_PACKAGING_EVENT_ABOUT_ORDER = """
MATCH (:PackagingQualityComplaintEvent)-[r:ABOUT_ORDER]->(:Order) DELETE r
""".strip()
RESET_PACKAGING_EVENT_RAISED_BY = """
MATCH (:PackagingQualityComplaintEvent)-[r:RAISED_BY]->(:Customer) DELETE r
""".strip()
RESET_PRODUCT_QUALITY_EVENT_ABOUT_PRODUCT = """
MATCH (:ProductQualityComplaintEvent)-[r:ABOUT_PRODUCT]->(:Product) DELETE r
""".strip()
RESET_PRODUCT_QUALITY_EVENT_ABOUT_ORDER = """
MATCH (:ProductQualityComplaintEvent)-[r:ABOUT_ORDER]->(:Order) DELETE r
""".strip()
RESET_PRODUCT_QUALITY_EVENT_RAISED_BY = """
MATCH (:ProductQualityComplaintEvent)-[r:RAISED_BY]->(:Customer) DELETE r
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
RESET_DELIVERY_DELAY_COMPLAINT_EVENTS = """
MATCH (n:DeliveryDelayComplaintEvent) DELETE n
""".strip()
RESET_PACKAGING_QUALITY_COMPLAINT_EVENTS = """
MATCH (n:PackagingQualityComplaintEvent) DELETE n
""".strip()
RESET_PRODUCT_QUALITY_COMPLAINT_EVENTS = """
MATCH (n:ProductQualityComplaintEvent) DELETE n
""".strip()
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
    delivery_delay_complaint_events: int
    packaging_quality_complaint_events: int
    product_quality_complaint_events: int
    classified_as_relationships: int
    supported_by_delay_relationships: int


def _fetch_rows(settings: Settings, sql: str) -> list[dict[str, Any]]:
    with psycopg.connect(settings.postgres_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
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


def _complaint_rows(settings: Settings) -> list[dict[str, Any]]:
    rows = _fetch_rows(settings, COMPLAINTS_SQL)
    enriched_rows = []
    for row in rows:
        issue = complaint_issue_type_for_subject(row.get("subject"))
        enriched_rows.append(
            {
                **row,
                "issue_type": issue.issue_type if issue else None,
            }
        )
    return enriched_rows


def _rows_for_issue(
    rows: list[dict[str, Any]],
    issue: ComplaintIssueType,
) -> list[dict[str, Any]]:
    return [row for row in rows if row.get("issue_type") == issue.issue_type]


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


def derive_customer_complaint_events(
    driver: Driver,
    settings: Settings,
    rows: list[dict[str, Any]] | None = None,
) -> int:
    rows = _complaint_rows(settings) if rows is None else rows
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


def derive_complaint_issue_events(
    driver: Driver,
    settings: Settings,
    rows: list[dict[str, Any]] | None = None,
) -> dict[str, int]:
    rows = _complaint_rows(settings) if rows is None else rows
    counts = {
        "delivery_delay_complaint_events": 0,
        "packaging_quality_complaint_events": 0,
        "product_quality_complaint_events": 0,
        "classified_as_relationships": 0,
        "supported_by_delay_relationships": 0,
    }

    for issue in COMPLAINT_ISSUE_TYPES:
        issue_rows = _rows_for_issue(rows, issue)
        if issue == DELIVERY_DELAY:
            _run_batches(
                driver,
                DELIVERY_DELAY_EVENT_MERGE_BATCH,
                issue_rows,
                issue.rule_name,
            )
        else:
            _run_batches(
                driver,
                issue_event_merge_batch(issue.event_label),
                issue_rows,
                issue.rule_name,
            )
        _run_batches(
            driver,
            issue_event_classified_as_batch(issue.event_label),
            issue_rows,
            CLASSIFIED_AS_RULE_NAME,
        )
        _run_batches(
            driver,
            issue_event_raised_by_batch(issue.event_label),
            issue_rows,
            issue.rule_name,
        )
        _run_batches(
            driver,
            issue_event_about_order_batch(issue.event_label),
            [row for row in issue_rows if row["order_id"] is not None],
            issue.rule_name,
        )
        _run_batches(
            driver,
            issue_event_about_product_batch(issue.event_label),
            [row for row in issue_rows if row["product_id"] is not None],
            issue.rule_name,
        )

        if issue == DELIVERY_DELAY:
            _run_batches(
                driver,
                DELIVERY_SUPPORTED_BY_DELAY_BATCH,
                issue_rows,
                SUPPORTED_BY_DELAY_RULE_NAME,
            )
            counts["supported_by_delay_relationships"] += _count_graph_elements(
                driver,
                """
                MATCH (:DeliveryDelayComplaintEvent)-[r:SUPPORTED_BY_DELAY]
                      ->(:ShipmentDelayEvent)
                RETURN count(r) AS count
                """,
            )

        label_count = _count_graph_elements(
            driver,
            f"MATCH (n:{issue.event_label}) RETURN count(n) AS count",
        )
        classified_count = _count_graph_elements(
            driver,
            f"""
            MATCH (:CustomerComplaintEvent)-[r:CLASSIFIED_AS]
                  ->(:{issue.event_label})
            RETURN count(r) AS count
            """,
        )
        counts[f"{issue.issue_type}_complaint_events"] = label_count
        counts["classified_as_relationships"] += classified_count

    return counts


def remove_obsolete_plausible_links(driver: Driver) -> None:
    with driver.session() as session:
        session.run(RESET_POSSIBLY_RELATED).consume()


def _count_graph_elements(driver: Driver, cypher: str) -> int:
    with driver.session() as session:
        return int(session.run(cypher.strip()).single()["count"])


def reset_projection(driver: Driver) -> None:
    reset_queries = [
        RESET_POSSIBLY_RELATED,
        RESET_SUPPORTED_BY_DELAY,
        RESET_CLASSIFIED_AS,
        RESET_DELIVERY_EVENT_ABOUT_PRODUCT,
        RESET_DELIVERY_EVENT_ABOUT_ORDER,
        RESET_DELIVERY_EVENT_RAISED_BY,
        RESET_PACKAGING_EVENT_ABOUT_PRODUCT,
        RESET_PACKAGING_EVENT_ABOUT_ORDER,
        RESET_PACKAGING_EVENT_RAISED_BY,
        RESET_PRODUCT_QUALITY_EVENT_ABOUT_PRODUCT,
        RESET_PRODUCT_QUALITY_EVENT_ABOUT_ORDER,
        RESET_PRODUCT_QUALITY_EVENT_RAISED_BY,
        RESET_ABOUT_PRODUCT,
        RESET_ABOUT_ORDER,
        RESET_RAISED_BY,
        RESET_HAS_DELAY_EVENT,
        RESET_FULFILLED_BY,
        RESET_CONTAINS,
        RESET_PLACED,
        RESET_SUPPLIES,
        RESET_DELIVERY_DELAY_COMPLAINT_EVENTS,
        RESET_PACKAGING_QUALITY_COMPLAINT_EVENTS,
        RESET_PRODUCT_QUALITY_COMPLAINT_EVENTS,
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
        remove_obsolete_plausible_links(driver)
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
        # Fetch complaint rows once and reuse for both complaint derivers to
        # avoid a redundant PostgreSQL round-trip and issue-type mapping pass.
        complaint_rows = _complaint_rows(settings)
        customer_complaint_events = derive_customer_complaint_events(
            driver,
            settings,
            rows=complaint_rows,
        )
        issue_event_counts = derive_complaint_issue_events(
            driver,
            settings,
            rows=complaint_rows,
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
        delivery_delay_complaint_events=issue_event_counts[
            "delivery_delay_complaint_events"
        ],
        packaging_quality_complaint_events=issue_event_counts[
            "packaging_quality_complaint_events"
        ],
        product_quality_complaint_events=issue_event_counts[
            "product_quality_complaint_events"
        ],
        classified_as_relationships=issue_event_counts[
            "classified_as_relationships"
        ],
        supported_by_delay_relationships=issue_event_counts[
            "supported_by_delay_relationships"
        ],
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
        f"{summary.delivery_delay_complaint_events} "
        "DeliveryDelayComplaintEvent nodes, "
        f"{summary.packaging_quality_complaint_events} "
        "PackagingQualityComplaintEvent nodes, "
        f"{summary.product_quality_complaint_events} "
        "ProductQualityComplaintEvent nodes, "
        f"{summary.classified_as_relationships} CLASSIFIED_AS relationships, "
        f"{summary.supported_by_delay_relationships} "
        "SUPPORTED_BY_DELAY relationships."
    )


if __name__ == "__main__":
    main()

