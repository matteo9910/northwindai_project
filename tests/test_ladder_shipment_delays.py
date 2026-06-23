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
from backend.ladder.shipment_delays import (
    ShipmentDelay,
    ShipmentDelaysResponse,
    answer_shipment_delays,
    build_answer,
    build_answer_trace,
    build_graph_paths,
    build_shipment_delays_cypher,
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


def test_shipment_delays_cypher_validates():
    validation = validate_cypher(build_shipment_delays_cypher())

    assert validation.allowed is True
    assert validation.referenced_labels == [
        "Order",
        "Product",
        "Shipment",
        "ShipmentDelayEvent",
        "Supplier",
    ]
    assert validation.referenced_relationship_types == [
        "CONTAINS",
        "FULFILLED_BY",
        "HAS_DELAY_EVENT",
        "SUPPLIES",
    ]
    assert validation.effective_cypher is not None


def test_shipment_delays_answer_deduplicates_public_rows():
    rows = [
        _record(product_id=9, product_name="Mishi Kobe Niku"),
        _record(product_id=10, product_name="Ikura"),
    ]

    answer = build_answer(rows)

    assert answer == [
        ShipmentDelay(
            order_id=12000,
            shipment_id=501,
            delay_days=5,
            expected_delivery_date="2025-12-10",
            actual_delivery_date="2025-12-15",
        )
    ]
    assert len(build_graph_paths(rows)) == 2


def test_shipment_delays_answer_trace_shape():
    validation = validate_cypher(build_shipment_delays_cypher())
    execution = GraphExecutionResult(
        records=[_record()],
        graph_paths=build_graph_paths([_record()]),
        metrics=QueryMetrics(row_count=1, duration_ms=1.0),
    )

    trace = build_answer_trace(validation, execution)

    assert trace.route == QueryRoute.GRAPH_ONLY
    assert trace.generated_sql is None
    assert trace.generated_cypher is not None
    assert trace.metrics["neo4j"].row_count == 1
    assert trace.graph_paths[0]["event"]["label"] == "ShipmentDelayEvent"
    assert [entry.rule_name for entry in trace.provenance] == [
        "order_projection",
        "order_contains_product_projection",
        "order_contains_product_projection",
        "shipment_projection",
        "shipment_delay_event",
    ]


def test_endpoint_returns_shipment_delays_answer_and_trace(monkeypatch):
    response_model = ShipmentDelaysResponse(
        answer=[
            ShipmentDelay(
                order_id=12000,
                shipment_id=501,
                delay_days=5,
                expected_delivery_date="2025-12-10",
                actual_delivery_date="2025-12-15",
            )
        ],
        answer_trace=AnswerTrace(
            route=QueryRoute.GRAPH_ONLY,
            generated_cypher=build_shipment_delays_cypher(),
            metrics={"neo4j": QueryMetrics(row_count=1, duration_ms=1.0)},
            validation_results=[validate_cypher(build_shipment_delays_cypher())],
            graph_paths=[{"event": {"label": "ShipmentDelayEvent"}}],
            provenance=[
                ProvenanceEntry(
                    source_system="postgresql",
                    source_schema="erp_core",
                    source_table="shipments",
                    source_columns=["delay_days"],
                    rule_name="shipment_delay_event",
                    rule_version="v1",
                )
            ],
        ),
    )
    monkeypatch.setattr(
        "backend.ladder.router.answer_shipment_delays",
        lambda settings: response_model,
    )

    response = TestClient(app).get("/ladder/shipment-delays")

    assert response.status_code == 200
    body = response.json()
    assert body["answer"][0]["order_id"] == 12000
    assert body["answer_trace"]["route"] == "graph_only"


def test_shipment_delays_matches_postgres_and_persists_trace(
    live_settings,
    tmp_path,
):
    first_projection = project_all(settings=live_settings)
    first_counts = _phase06_counts(live_settings)
    second_projection = project_all(settings=live_settings)
    second_counts = _phase06_counts(live_settings)

    assert first_projection.shipment_delay_events > 0
    assert first_projection.customer_complaint_events > 0
    assert second_projection.possibly_related_relationships >= 1
    assert second_counts == first_counts

    response = answer_shipment_delays(settings=live_settings)
    expected = _tokyo_traders_delayed_shipments(live_settings)
    actual = [
        (
            item.order_id,
            item.shipment_id,
            item.delay_days,
            item.expected_delivery_date,
            item.actual_delivery_date,
        )
        for item in response.answer
    ]

    assert actual == expected
    assert response.answer_trace.route == QueryRoute.GRAPH_ONLY
    assert response.answer_trace.validation_results[0].allowed is True
    assert response.answer_trace.graph_paths

    trace_path = persist_answer_trace(
        response.answer_trace,
        tmp_path / "step03_shipment_delays.json",
    )
    assert trace_path.exists()


def _record(product_id=9, product_name="Mishi Kobe Niku"):
    return {
        "supplier_id": 4,
        "supplier_name": "Tokyo Traders",
        "supplier_properties": {
            "source_table": "suppliers",
            "source_pk": 4,
            "rule_name": "supplier_projection",
            "rule_version": "v1",
        },
        "product_id": product_id,
        "product_name": product_name,
        "product_properties": {
            "source_table": "products",
            "source_pk": product_id,
            "rule_name": "product_projection",
            "rule_version": "v1",
        },
        "order_id": 12000,
        "order_properties": {
            "customer_id": "SAVEA",
            "order_date": "2025-12-01",
            "source_table": "orders",
            "source_pk": 12000,
            "rule_name": "order_projection",
            "rule_version": "v1",
        },
        "shipment_id": 501,
        "shipment_properties": {
            "delay_days": 5,
            "expected_delivery_date": "2025-12-10",
            "actual_delivery_date": "2025-12-15",
            "source_table": "shipments",
            "source_pk": 501,
            "rule_name": "shipment_projection",
            "rule_version": "v1",
        },
        "delay_days": 5,
        "event_properties": {
            "shipment_id": 501,
            "delay_days": 5,
            "expected_delivery_date": "2025-12-10",
            "actual_delivery_date": "2025-12-15",
            "derived_from": "erp_core.shipments",
            "source_table": "shipments",
            "source_pk": 501,
            "rule_name": "shipment_delay_event",
            "rule_version": "v1",
        },
    }


def _tokyo_traders_delayed_shipments(settings):
    with psycopg.connect(settings.postgres_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                select distinct
                       o.order_id,
                       s.shipment_id,
                       s.delay_days,
                       s.expected_delivery_date::text,
                       s.actual_delivery_date::text
                from erp_core.orders o
                join erp_core.order_details od on od.order_id = o.order_id
                join erp_core.products p on p.product_id = od.product_id
                join erp_core.shipments s on s.order_id = o.order_id
                where p.supplier_id = 4
                  and s.delay_days > 0
                order by s.delay_days desc, o.order_id, s.shipment_id
                """
            )
            return [
                (int(row[0]), int(row[1]), int(row[2]), row[3], row[4])
                for row in cur.fetchall()
            ]


def _phase06_counts(settings):
    with GraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_user, settings.neo4j_password),
    ) as driver:
        with driver.session() as session:
            return tuple(
                int(
                    session.run(
                        f"MATCH {pattern} RETURN count(*) AS count"
                    ).single()["count"]
                )
                for pattern in [
                    "(n:Customer)",
                    "(n:Order)",
                    "(n:Shipment)",
                    "(n:ShipmentDelayEvent)",
                    "(n:CustomerComplaintEvent)",
                    "(:ShipmentDelayEvent)-[r:POSSIBLY_RELATED_TO]->"
                    "(:CustomerComplaintEvent)",
                ]
            )
