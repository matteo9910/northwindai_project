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
        pytest.skip("Postgres/Neo4j are not configured for live issue probes.")
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


def test_delivery_delay_complaints_are_supported_by_delay(live_settings):
    with _driver(live_settings) as driver:
        with driver.session() as session:
            supported = int(
                session.run(
                    """
                    MATCH (:DeliveryDelayComplaintEvent)
                          -[r:SUPPORTED_BY_DELAY]->(:ShipmentDelayEvent)
                    RETURN count(r) AS count
                    """
                ).single()["count"]
            )
            classified = int(
                session.run(
                    """
                    MATCH (:CustomerComplaintEvent)-[r:CLASSIFIED_AS]
                          ->(:DeliveryDelayComplaintEvent)
                    RETURN count(r) AS count
                    """
                ).single()["count"]
            )

    assert supported == 60
    assert classified == 60


def test_packaging_quality_events_have_product_context(live_settings):
    assert _issue_context_count(
        live_settings,
        "PackagingQualityComplaintEvent",
        "ABOUT_PRODUCT",
    ) == 40
    assert _issue_context_count(
        live_settings,
        "PackagingQualityComplaintEvent",
        "ABOUT_ORDER",
    ) == 40
    assert _issue_context_count(
        live_settings,
        "PackagingQualityComplaintEvent",
        "RAISED_BY",
    ) == 40


def test_product_quality_events_have_product_context(live_settings):
    assert _issue_context_count(
        live_settings,
        "ProductQualityComplaintEvent",
        "ABOUT_PRODUCT",
    ) == 15
    assert _issue_context_count(
        live_settings,
        "ProductQualityComplaintEvent",
        "ABOUT_ORDER",
    ) == 15
    assert _issue_context_count(
        live_settings,
        "ProductQualityComplaintEvent",
        "RAISED_BY",
    ) == 15


def test_revised_phase06_does_not_create_possibly_related(live_settings):
    with _driver(live_settings) as driver:
        with driver.session() as session:
            possibly_related = int(
                session.run(
                    """
                    MATCH (:ShipmentDelayEvent)-[r:POSSIBLY_RELATED_TO]
                          ->(:CustomerComplaintEvent)
                    RETURN count(r) AS count
                    """
                ).single()["count"]
            )

    assert possibly_related == 0


def _issue_context_count(settings, label: str, relationship_type: str) -> int:
    with _driver(settings) as driver:
        with driver.session() as session:
            return int(
                session.run(
                    f"""
                    MATCH (n:{label})-[r:{relationship_type}]->()
                    RETURN count(r) AS count
                    """
                ).single()["count"]
            )


def _driver(settings):
    return GraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_user, settings.neo4j_password),
    )
