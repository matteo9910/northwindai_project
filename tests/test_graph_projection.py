from __future__ import annotations

from dataclasses import dataclass

import psycopg
import pytest
from neo4j import GraphDatabase
from neo4j.exceptions import Neo4jError

from backend.config import get_settings
from backend.graph import projection
from data_generation.contract_documents import apply_contract_document_paths
from data_generation.contracts import generate_contract_pdfs


@dataclass
class FakeSettings:
    postgres_dsn: str = "host=fake dbname=fake"


class FakeResult:
    def consume(self):
        return None


class FakeSession:
    def __init__(self):
        self.runs = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def run(self, query, params=None):
        self.runs.append((query, params or {}))
        return FakeResult()


class FakeDriver:
    def __init__(self):
        self.session_instance = FakeSession()

    def session(self):
        return self.session_instance


def test_projection_sets_provenance_on_supplier_product_and_relationship(
    monkeypatch,
):
    rows_by_sql = {
        projection.SUPPLIERS_SQL: [
            {"supplier_id": 4, "company_name": "Tokyo Traders"}
        ],
        projection.PRODUCTS_SQL: [
            {
                "product_id": 9,
                "product_name": "Mishi Kobe Niku",
                "supplier_id": 4,
            }
        ],
    }
    monkeypatch.setattr(
        "backend.graph.projection._fetch_rows",
        lambda _settings, sql: rows_by_sql[sql],
    )
    driver = FakeDriver()

    assert projection.project_suppliers(driver, FakeSettings()) == 1
    assert projection.project_products(driver, FakeSettings()) == 1
    assert projection.project_supplies(driver, FakeSettings()) == 1

    params = [run[1] for run in driver.session_instance.runs]
    assert params[0]["rule_name"] == "supplier_projection"
    assert params[1]["rule_name"] == "product_projection"
    assert params[1]["rows"][0]["supplier_id"] == 4
    assert params[2]["rule_name"] == "supplier_to_product_projection"
    assert params[2]["rows"][0]["product_id"] == 9


def test_projection_extends_customer_order_shipment_path(monkeypatch):
    rows_by_sql = {
        projection.CUSTOMERS_SQL: [
            {"customer_id": "SAVEA", "company_name": "Save-a-lot Markets"}
        ],
        projection.ORDERS_SQL: [
            {"order_id": 12000, "customer_id": "SAVEA", "order_date": "2025-12-01"}
        ],
        projection.SHIPMENTS_SQL: [
            {
                "shipment_id": 501,
                "order_id": 12000,
                "expected_delivery_date": "2025-12-10",
                "actual_delivery_date": "2025-12-15",
                "delay_days": 5,
                "status": "delivered",
            }
        ],
        projection.ORDER_DETAILS_SQL: [
            {"order_id": 12000, "product_id": 9}
        ],
    }
    monkeypatch.setattr(
        "backend.graph.projection._fetch_rows",
        lambda _settings, sql: rows_by_sql[sql],
    )
    driver = FakeDriver()

    assert projection.project_customers(driver, FakeSettings()) == 1
    assert projection.project_orders(driver, FakeSettings()) == 1
    assert projection.project_shipments(driver, FakeSettings()) == 1
    assert projection.project_customer_placed_orders(driver, FakeSettings()) == 1
    assert projection.project_order_contains_products(driver, FakeSettings()) == 1
    assert projection.project_order_fulfilled_by_shipments(
        driver,
        FakeSettings(),
    ) == 1

    params = [run[1] for run in driver.session_instance.runs]
    assert params[0]["rule_name"] == "customer_projection"
    assert params[1]["rule_name"] == "order_projection"
    assert params[2]["rule_name"] == "shipment_projection"
    assert params[3]["rule_name"] == "customer_placed_order_projection"
    assert params[4]["rows"][0]["source_pk"] == "12000:9"
    assert params[4]["rule_name"] == "order_contains_product_projection"
    assert params[5]["rule_name"] == "order_fulfilled_by_shipment_projection"


def test_derivers_create_complaint_issue_events(monkeypatch):
    rows_by_sql = {
        projection.SHIPMENT_DELAYS_SQL: [
            {
                "shipment_id": 501,
                "expected_delivery_date": "2025-12-10",
                "actual_delivery_date": "2025-12-15",
                "delay_days": 5,
            }
        ],
        projection.COMPLAINTS_SQL: [
            {
                "communication_id": 701,
                "customer_id": "SAVEA",
                "order_id": 12000,
                "product_id": 9,
                "channel": "email",
                "contact_reason": "complaint",
                "subject": "Late delivery affected replenishment",
                "body": "The delivery arrived late.",
                "sentiment": "negative",
                "occurred_at": "2025-12-16T10:00:00+00:00",
            }
        ],
    }
    monkeypatch.setattr(
        "backend.graph.projection._fetch_rows",
        lambda _settings, sql: rows_by_sql[sql],
    )
    monkeypatch.setattr(
        "backend.graph.projection._count_graph_elements",
        lambda _driver, cypher: 1
        if "DeliveryDelayComplaintEvent" in cypher
        or "CLASSIFIED_AS" in cypher
        or "SUPPORTED_BY_DELAY" in cypher
        else 0,
    )
    driver = FakeDriver()

    assert projection.derive_shipment_delay_events(driver, FakeSettings()) == 1
    assert projection.derive_customer_complaint_events(driver, FakeSettings()) == 1
    counts = projection.derive_complaint_issue_events(
        driver,
        FakeSettings(),
    )

    params = [run[1] for run in driver.session_instance.runs]
    assert params[0]["rule_name"] == "shipment_delay_event"
    assert params[1]["rule_name"] == "customer_complaint_event"
    assert params[1]["rows"][0]["issue_type"] == "delivery_delay"
    assert "DeliveryDelayComplaintEvent" in driver.session_instance.runs[5][0]
    assert params[5]["rule_name"] == "delivery_delay_complaint_event"
    assert counts["delivery_delay_complaint_events"] == 1
    assert counts["supported_by_delay_relationships"] == 1


def test_projection_creates_contracts_and_contract_term_events(monkeypatch):
    rows_by_sql = {
        projection.CONTRACTS_SQL: [
            {
                "contract_id": 3,
                "supplier_id": 4,
                "contract_number": "CT-4-2020",
                "lead_time_days": 14,
                "start_date": "2020-01-01",
                "end_date": None,
                "minimum_order_value": "900.00",
                "status": "active",
            }
        ],
    }
    monkeypatch.setattr(
        "backend.graph.projection._fetch_rows",
        lambda _settings, sql: rows_by_sql[sql],
    )
    monkeypatch.setattr(
        "backend.graph.projection._count_graph_elements",
        lambda _driver, cypher: 3
        if "ContractTermEvent" in cypher
        else 1,
    )
    driver = FakeDriver()

    assert projection.project_contracts(driver, FakeSettings()) == 1
    counts = projection.derive_contract_term_events(driver, FakeSettings())

    params = [run[1] for run in driver.session_instance.runs]
    assert params[0]["rule_name"] == "contract_projection"
    assert params[0]["rows"][0]["contract_number"] == "CT-4-2020"
    assert params[1]["rule_name"] == "supplier_has_contract_projection"
    assert params[2]["rule_name"] == "contract_term_projection"
    term_rows = params[2]["rows"]
    assert {row["term_type"] for row in term_rows} == {
        "lead_time",
        "minimum_order_value",
        "contract_validity",
    }
    assert {
        row["term_key"] for row in term_rows
    } == {
        "3:lead_time",
        "3:minimum_order_value",
        "3:contract_validity",
    }
    assert counts["contract_term_events"] == 3
    assert counts["has_term_relationships"] == 3


def test_projection_creates_supplier_contract_document_references(monkeypatch):
    rows_by_sql = {
        projection.CONTRACT_DOCUMENTS_SQL: [
            {
                "document_id": 3,
                "doc_type": "supplier_contract",
                "title": "Supplier contract CT-4-2020",
                "supplier_id": 4,
                "file_path": "data/contracts/CT-4-2020.pdf",
                "status": "generated",
                "contract_number": "CT-4-2020",
                "lead_time_days": 14,
            }
        ],
    }
    monkeypatch.setattr(
        "backend.graph.projection._fetch_rows",
        lambda _settings, sql: rows_by_sql[sql],
    )
    driver = FakeDriver()

    assert projection.project_contract_documents(driver, FakeSettings()) == 1

    params = [run[1] for run in driver.session_instance.runs]
    assert params[0]["rule_name"] == "contract_document_reference"
    assert params[0]["rows"][0]["document_id"] == 3
    assert params[1]["rule_name"] == "contract_has_document_projection"
    assert "HAS_DOCUMENT" in driver.session_instance.runs[1][0]


@pytest.fixture(scope="module")
def live_graph_settings():
    settings = get_settings()
    if (
        "__set_me__" in settings.postgres_dsn
        or "<project-ref>" in settings.postgres_dsn
        or "__set_me__" in settings.neo4j_password
    ):
        pytest.skip("Postgres/Neo4j are not configured for live projection probes.")
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
    except (psycopg.OperationalError, Neo4jError, Exception) as exc:
        pytest.skip(f"Postgres/Neo4j are not reachable: {exc}")
    # Document nodes need a non-null file_path to be projected; prepare it without
    # touching Qdrant/Java (no indexing in these graph-only probes).
    generate_contract_pdfs()
    apply_contract_document_paths(settings=settings)
    return settings


def test_projection_is_idempotent_across_full_run(live_graph_settings):
    first = projection.project_all(settings=live_graph_settings)
    second = projection.project_all(settings=live_graph_settings)

    # Idempotency (07A and beyond): re-running the projection must converge to the
    # exact same summary — every MERGE is keyed on identity, never duplicating.
    assert first == second
    assert second.contracts > 0
    assert second.contract_documents > 0
    # Measured relationship counts stay consistent with their endpoints.
    assert second.has_contract_relationships == second.contracts
    assert second.has_document_relationships == second.contract_documents


def test_projected_documents_store_references_not_content(live_graph_settings):
    projection.project_all(settings=live_graph_settings)
    with GraphDatabase.driver(
        live_graph_settings.neo4j_uri,
        auth=(live_graph_settings.neo4j_user, live_graph_settings.neo4j_password),
    ) as driver:
        with driver.session() as session:
            records = session.run(
                "MATCH (d:Document) RETURN properties(d) AS props"
            ).data()

    # ADR 0006: Neo4j Document nodes hold only references (vector_chunk_ids),
    # never chunk text or embeddings — those live in Qdrant alone.
    assert records
    forbidden = {
        "text",
        "body",
        "content",
        "chunk_text",
        "embedding",
        "embeddings",
        "vector",
    }
    for record in records:
        props = record["props"]
        assert "vector_chunk_ids" in props
        assert forbidden.isdisjoint(props.keys())


def test_reset_projection_is_scoped():
    driver = FakeDriver()

    projection.reset_projection(driver)

    queries = [query for query, _params in driver.session_instance.runs]
    assert projection.RESET_POSSIBLY_RELATED in queries
    assert projection.RESET_SUPPORTED_BY_DELAY in queries
    assert projection.RESET_CLASSIFIED_AS in queries
    assert projection.RESET_SUPPLIES in queries
    assert projection.RESET_SUPPLIERS == queries[-1]
    assert all("DETACH DELETE" not in query for query in queries)
    assert all("MATCH (n)" not in query for query in queries)

