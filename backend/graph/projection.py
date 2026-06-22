from __future__ import annotations

import argparse
from dataclasses import dataclass
from typing import Any

import psycopg
from neo4j import Driver

from backend.config import Settings, get_settings
from backend.graph.connection import neo4j_driver

PROJECTION_VERSION = "v1"
SUPPLIER_RULE_NAME = "supplier_projection"
PRODUCT_RULE_NAME = "product_projection"
SUPPLIES_RULE_NAME = "supplier_to_product_projection"

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

RESET_SUPPLIES = "MATCH (:Supplier)-[r:SUPPLIES]->(:Product) DELETE r"
RESET_SUPPLIERS = "MATCH (n:Supplier) DELETE n"
RESET_PRODUCTS = "MATCH (n:Product) DELETE n"


@dataclass(frozen=True)
class ProjectionSummary:
    suppliers: int
    products: int
    supplies_relationships: int


def _fetch_rows(settings: Settings, sql: str) -> list[dict[str, Any]]:
    with psycopg.connect(settings.postgres_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
            columns = [desc.name for desc in cur.description or []]
            return [
                dict(zip(columns, row, strict=True))
                for row in cur.fetchall()
            ]


def project_suppliers(driver: Driver, settings: Settings) -> int:
    rows = _fetch_rows(settings, SUPPLIERS_SQL)
    with driver.session() as session:
        for row in rows:
            session.run(
                SUPPLIER_MERGE,
                {
                    **row,
                    "version": PROJECTION_VERSION,
                    "rule_name": SUPPLIER_RULE_NAME,
                    "rule_version": "v1",
                },
            ).consume()
    return len(rows)


def project_products(driver: Driver, settings: Settings) -> int:
    rows = _fetch_rows(settings, PRODUCTS_SQL)
    with driver.session() as session:
        for row in rows:
            session.run(
                PRODUCT_MERGE,
                {
                    **row,
                    "version": PROJECTION_VERSION,
                    "rule_name": PRODUCT_RULE_NAME,
                    "rule_version": "v1",
                },
            ).consume()
    return len(rows)


def project_supplies(driver: Driver, settings: Settings) -> int:
    rows = _fetch_rows(settings, PRODUCTS_SQL)
    with driver.session() as session:
        for row in rows:
            session.run(
                SUPPLIES_MERGE,
                {
                    "supplier_id": row["supplier_id"],
                    "product_id": row["product_id"],
                    "version": PROJECTION_VERSION,
                    "rule_name": SUPPLIES_RULE_NAME,
                    "rule_version": "v1",
                },
            ).consume()
    return len(rows)


def reset_phase05_projection(driver: Driver) -> None:
    with driver.session() as session:
        session.run(RESET_SUPPLIES).consume()
        session.run(RESET_PRODUCTS).consume()
        session.run(RESET_SUPPLIERS).consume()


def project_all(
    settings: Settings | None = None,
    reset: bool = False,
) -> ProjectionSummary:
    settings = settings or get_settings()
    with neo4j_driver(settings) as driver:
        if reset:
            reset_phase05_projection(driver)
        suppliers = project_suppliers(driver, settings)
        products = project_products(driver, settings)
        relationships = project_supplies(driver, settings)
    return ProjectionSummary(
        suppliers=suppliers,
        products=products,
        supplies_relationships=relationships,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Project Phase 05 graph data.")
    parser.add_argument("--reset", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    summary = project_all(settings=get_settings(), reset=args.reset)
    print(
        "Projected "
        f"{summary.suppliers} suppliers, "
        f"{summary.products} products, "
        f"{summary.supplies_relationships} SUPPLIES relationships."
    )


if __name__ == "__main__":
    main()

