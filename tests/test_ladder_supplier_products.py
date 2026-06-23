from __future__ import annotations

import psycopg
import pytest
from fastapi.testclient import TestClient
from neo4j import GraphDatabase
from neo4j.exceptions import Neo4jError

from backend.config import get_settings
from backend.graph.cypher_executor import GraphExecutionResult
from backend.graph.cypher_validator import validate_cypher
from backend.graph.projection import project_all
from backend.ladder.supplier_products import (
    SupplierProduct,
    SupplierProductsResponse,
    answer_supplier_products,
    build_answer_trace,
    build_supplier_products_cypher,
    persist_answer_trace,
)
from backend.main import app
from backend.query.executor import QueryMetrics
from backend.query.trace import AnswerTrace, ProvenanceEntry, QueryRoute


@pytest.fixture(scope="module")
def live_settings():
    settings = get_settings()
    if (
        "__set_me__" in settings.postgres_dsn
        or "<project-ref>" in settings.postgres_dsn
        or "__set_me__" in settings.neo4j_password
    ):
        pytest.skip("Postgres/Neo4j are not configured for live ladder probes.")
    try:
        with psycopg.connect(settings.postgres_dsn, connect_timeout=3) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                cur.fetchone()
        with GraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_user, settings.neo4j_password),
            connection_timeout=3,
        ) as driver:
            driver.verify_connectivity()
    except (psycopg.OperationalError, Neo4jError) as exc:
        pytest.skip(f"Postgres/Neo4j are not reachable: {exc}")
    return settings


def test_supplier_products_cypher_validates():
    validation = validate_cypher(build_supplier_products_cypher())

    assert validation.allowed is True
    assert validation.referenced_labels == ["Product", "Supplier"]
    assert validation.referenced_relationship_types == ["SUPPLIES"]
    assert validation.effective_cypher is not None


def test_supplier_products_answer_trace_shape():
    validation = validate_cypher(build_supplier_products_cypher())
    execution = GraphExecutionResult(
        records=[
            {
                "product_id": 9,
                "product_name": "Mishi Kobe Niku",
            }
        ],
        graph_paths=[
            {
                "supplier": {
                    "supplier_id": 4,
                    "company_name": "Tokyo Traders",
                    "rule_name": "supplier_projection",
                    "rule_version": "v1",
                },
                "relationship": {
                    "type": "SUPPLIES",
                    "source_pk": 9,
                    "source_column": "supplier_id",
                    "rule_name": "supplier_to_product_projection",
                    "rule_version": "v1",
                },
                "product": {
                    "product_id": 9,
                    "product_name": "Mishi Kobe Niku",
                    "rule_name": "product_projection",
                    "rule_version": "v1",
                },
            }
        ],
        metrics=QueryMetrics(row_count=1, duration_ms=1.0),
    )

    trace = build_answer_trace(validation, execution)

    assert trace.route == QueryRoute.GRAPH_ONLY
    assert trace.generated_sql is None
    assert trace.generated_cypher is not None
    assert trace.metrics["neo4j"].row_count == 1
    assert trace.graph_paths[0]["relationship"]["source_column"] == "supplier_id"
    assert [entry.rule_name for entry in trace.provenance] == [
        "supplier_projection",
        "product_projection",
        "supplier_to_product_projection",
    ]


def test_endpoint_returns_supplier_products_answer_and_trace(monkeypatch):
    response_model = SupplierProductsResponse(
        answer=[SupplierProduct(product_id=9, product_name="Mishi Kobe Niku")],
        answer_trace=AnswerTrace(
            route=QueryRoute.GRAPH_ONLY,
            generated_cypher="MATCH (:Supplier)-[:SUPPLIES]->(p:Product) RETURN p",
            metrics={"neo4j": QueryMetrics(row_count=1, duration_ms=1.0)},
            validation_results=[
                validate_cypher("MATCH (:Supplier)-[:SUPPLIES]->(p:Product) RETURN p")
            ],
            graph_paths=[
                {
                    "supplier": {"supplier_id": 4},
                    "relationship": {"type": "SUPPLIES"},
                    "product": {"product_id": 9},
                }
            ],
            provenance=[
                ProvenanceEntry(
                    source_system="postgresql",
                    source_schema="erp_core",
                    source_table="products",
                    source_columns=["supplier_id"],
                    rule_name="supplier_to_product_projection",
                    rule_version="v1",
                )
            ],
        ),
    )
    monkeypatch.setattr(
        "backend.ladder.router.answer_supplier_products",
        lambda settings: response_model,
    )

    response = TestClient(app).get("/ladder/supplier-products")

    assert response.status_code == 200
    body = response.json()
    assert body["answer"] == [
        {"product_id": 9, "product_name": "Mishi Kobe Niku"}
    ]
    assert body["answer_trace"]["route"] == "graph_only"


def test_supplier_products_matches_postgres_and_persists_trace(
    live_settings,
    tmp_path,
):
    first_projection = project_all(settings=live_settings)
    first_counts = _phase05_counts(live_settings)
    second_projection = project_all(settings=live_settings)
    second_counts = _phase05_counts(live_settings)

    assert first_projection.suppliers > 0
    assert first_projection.products > 0
    assert second_projection.supplies_relationships == first_projection.products
    assert second_counts == first_counts

    response = answer_supplier_products(settings=live_settings)
    expected = _tokyo_traders_products(live_settings)
    actual = [(item.product_id, item.product_name) for item in response.answer]

    assert actual == expected
    assert response.answer_trace.route == QueryRoute.GRAPH_ONLY
    assert response.answer_trace.validation_results[0].allowed is True
    assert response.answer_trace.graph_paths

    trace_path = persist_answer_trace(
        response.answer_trace,
        tmp_path / "step02_supplier_products.json",
    )
    assert trace_path.exists()


def _tokyo_traders_products(settings) -> list[tuple[int, str]]:
    with psycopg.connect(settings.postgres_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                select p.product_id, p.product_name
                from erp_core.products p
                where p.supplier_id = 4
                order by p.product_name
                """
            )
            return [(int(row[0]), str(row[1])) for row in cur.fetchall()]


def _phase05_counts(settings) -> tuple[int, int, int]:
    with GraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_user, settings.neo4j_password),
    ) as driver:
        with driver.session() as session:
            supplier_count = session.run(
                "MATCH (s:Supplier) RETURN count(s) AS count"
            ).single()["count"]
            product_count = session.run(
                "MATCH (p:Product) RETURN count(p) AS count"
            ).single()["count"]
            supplies_count = session.run(
                "MATCH (:Supplier)-[r:SUPPLIES]->(:Product) "
                "RETURN count(r) AS count"
            ).single()["count"]
    return int(supplier_count), int(product_count), int(supplies_count)

