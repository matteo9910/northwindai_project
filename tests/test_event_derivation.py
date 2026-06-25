from __future__ import annotations

import psycopg
import pytest
from neo4j import GraphDatabase
from neo4j.exceptions import Neo4jError

from backend.config import get_settings
from backend.graph.projection import project_all


@pytest.fixture(scope="module")
def live_settings():
    settings = get_settings()
    if (
        "__set_me__" in settings.postgres_dsn
        or "<project-ref>" in settings.postgres_dsn
        or "__set_me__" in settings.neo4j_password
    ):
        pytest.skip("Postgres/Neo4j are not configured for live event probes.")
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
    project_all(settings=settings)
    return settings


def test_event_nodes_are_not_materialized_in_postgres(live_settings):
    with psycopg.connect(live_settings.postgres_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                select table_schema, table_name
                from information_schema.tables
                where table_schema in ('erp_core', 'erp_docs')
                  and table_name in (
                    'shipment_delay_events',
                    'customer_complaint_events',
                    'delivery_delay_complaint_events',
                    'packaging_quality_complaint_events',
                    'product_quality_complaint_events'
                  )
                """
            )
            rows = cur.fetchall()

    assert rows == []


def test_shipment_delay_events_match_delayed_shipments(live_settings):
    with psycopg.connect(live_settings.postgres_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "select count(*) from erp_core.shipments where delay_days > 0"
            )
            expected_delay_events = int(cur.fetchone()[0])

    with _driver(live_settings) as driver:
        with driver.session() as session:
            actual_delay_events = int(
                session.run(
                    "MATCH (n:ShipmentDelayEvent) RETURN count(n) AS count"
                ).single()["count"]
            )
            missing_provenance = int(
                session.run(
                    """
                    MATCH (n:ShipmentDelayEvent)
                    WHERE n.rule_name IS NULL
                       OR n.derived_from IS NULL
                       OR n.source_pk IS NULL
                    RETURN count(n) AS count
                    """
                ).single()["count"]
            )

    assert actual_delay_events == expected_delay_events
    assert missing_provenance == 0


def test_customer_complaint_events_include_issue_type_from_subject(live_settings):
    with _driver(live_settings) as driver:
        with driver.session() as session:
            rows = session.run(
                """
                MATCH (n:CustomerComplaintEvent)
                RETURN n.subject AS subject,
                       n.issue_type AS issue_type,
                       count(n) AS count
                ORDER BY subject
                """
            ).data()

    actual = {
        (row["subject"], row["issue_type"]): int(row["count"])
        for row in rows
    }
    assert actual[
        ("Late delivery affected replenishment", "delivery_delay")
    ] == 60
    assert actual[("Packaging quality issue", "packaging_quality")] == 40
    assert actual[
        ("Product quality below expectation", "product_quality")
    ] == 15


def test_specialized_complaint_issue_events_exist(live_settings):
    with _driver(live_settings) as driver:
        with driver.session() as session:
            delivery = int(
                session.run(
                    """
                    MATCH (n:DeliveryDelayComplaintEvent)
                    RETURN count(n) AS count
                    """
                ).single()["count"]
            )
            packaging = int(
                session.run(
                    """
                    MATCH (n:PackagingQualityComplaintEvent)
                    RETURN count(n) AS count
                    """
                ).single()["count"]
            )
            product_quality = int(
                session.run(
                    """
                    MATCH (n:ProductQualityComplaintEvent)
                    RETURN count(n) AS count
                    """
                ).single()["count"]
            )

    assert delivery == 60
    assert packaging == 40
    assert product_quality == 15


def _driver(settings):
    return GraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_user, settings.neo4j_password),
    )
