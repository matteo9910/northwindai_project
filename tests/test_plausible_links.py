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
        pytest.skip("Postgres/Neo4j are not configured for live link probes.")
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


def test_scenario_a_tokyo_delay_complaint_link_present(live_settings):
    assert _possibly_related_count(live_settings, supplier_id=4) >= 1


def test_scenario_b_exotic_liquids_has_no_plausible_link(live_settings):
    assert _possibly_related_count(live_settings, supplier_id=1) == 0


def test_scenario_c_pavlova_has_no_plausible_link(live_settings):
    assert _possibly_related_count(live_settings, supplier_id=7) == 0


def test_plausible_links_have_required_properties_and_no_causal_names(
    live_settings,
):
    with _driver(live_settings) as driver:
        with driver.session() as session:
            missing_properties = int(
                session.run(
                    """
                    MATCH (:ShipmentDelayEvent)-[r:POSSIBLY_RELATED_TO]
                          ->(:CustomerComplaintEvent)
                    WHERE r.confidence IS NULL
                       OR r.matching_reason IS NULL
                       OR r.time_window_days IS NULL
                       OR r.evidence IS NULL
                    RETURN count(r) AS count
                    """
                ).single()["count"]
            )
            causal_relationships = int(
                session.run(
                    """
                    MATCH ()-[r]->()
                    WHERE type(r) IN [
                      'CAUSED',
                      'CAUSED_BY',
                      'BECAUSE_OF'
                    ]
                    RETURN count(r) AS count
                    """
                ).single()["count"]
            )

    assert missing_properties == 0
    assert causal_relationships == 0


def _possibly_related_count(settings, supplier_id: int) -> int:
    with _driver(settings) as driver:
        with driver.session() as session:
            return int(
                session.run(
                    """
                    MATCH (:Supplier {supplier_id: $supplier_id})
                          -[:SUPPLIES]->(:Product)<-[:CONTAINS]-(:Order)
                          -[:FULFILLED_BY]->(:Shipment)
                          -[:HAS_DELAY_EVENT]->(:ShipmentDelayEvent)
                          -[:POSSIBLY_RELATED_TO]->(:CustomerComplaintEvent)
                    RETURN count(*) AS count
                    """,
                    {"supplier_id": supplier_id},
                ).single()["count"]
            )


def _driver(settings):
    return GraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_user, settings.neo4j_password),
    )
