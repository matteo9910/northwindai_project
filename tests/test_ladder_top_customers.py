from __future__ import annotations

from decimal import Decimal

import psycopg
import pytest
from fastapi.testclient import TestClient

from backend.config import get_settings
from backend.ladder.top_customers import (
    TopCustomer,
    TopCustomersResponse,
    answer_top_customers,
    build_top_customers_sql,
    persist_answer_trace,
)
from backend.main import app
from backend.query.executor import QueryMetrics
from backend.query.trace import AnswerTrace, ProvenanceEntry, QueryRoute
from backend.query.validator import validate_sql


@pytest.fixture(scope="module")
def db_conn():
    settings = get_settings()
    if (
        "__set_me__" in settings.postgres_dsn
        or "<project-ref>" in settings.postgres_dsn
    ):
        pytest.skip("Postgres DSN is not configured for live ladder probes.")
    try:
        with psycopg.connect(settings.postgres_dsn) as conn:
            yield conn
    except psycopg.OperationalError as exc:
        pytest.skip(f"Postgres is not reachable: {exc}")


def test_top_customers_sql_validates():
    validation = validate_sql(build_top_customers_sql())

    assert validation.allowed is True
    assert validation.referenced_tables == [
        "erp_core.order_details",
        "erp_core.orders",
    ]
    assert validation.effective_sql is not None


def test_answer_trace_shape_with_empty_graph_and_vector_fields():
    trace = AnswerTrace(
        route=QueryRoute.SQL_ONLY,
        generated_sql="select customer_id from erp_core.customers limit 1",
        metrics={"postgresql": QueryMetrics(row_count=1, duration_ms=1.5)},
        validation_results=[
            validate_sql("select customer_id from erp_core.customers limit 1")
        ],
        provenance=[
            ProvenanceEntry(
                source_system="postgresql",
                source_schema="erp_core",
                source_table="customers",
                source_columns=["customer_id"],
                rule_name="top_customers",
                rule_version="v1",
            )
        ],
    )

    assert trace.route == QueryRoute.SQL_ONLY
    assert trace.generated_cypher is None
    assert trace.graph_paths == []
    assert trace.retrieved_chunks == []
    assert trace.documents_used == []


def test_endpoint_returns_answer_and_trace(monkeypatch):
    response_model = TopCustomersResponse(
        answer=[TopCustomer(customer_id="SAVEA", net_revenue=Decimal("10.00"))],
        answer_trace=AnswerTrace(
            route=QueryRoute.SQL_ONLY,
            generated_sql="select customer_id from erp_core.customers limit 1",
            metrics={"postgresql": QueryMetrics(row_count=1, duration_ms=1.0)},
            validation_results=[
                validate_sql("select customer_id from erp_core.customers limit 1")
            ],
            provenance=[
                ProvenanceEntry(
                    source_system="postgresql",
                    source_schema="erp_core",
                    source_table="customers",
                    source_columns=["customer_id"],
                    rule_name="top_customers",
                    rule_version="v1",
                )
            ],
        ),
    )
    monkeypatch.setattr(
        "backend.ladder.router.answer_top_customers",
        lambda settings: response_model,
    )

    response = TestClient(app).get("/ladder/top-customers")

    assert response.status_code == 200
    body = response.json()
    assert body["answer"][0]["customer_id"] == "SAVEA"
    assert body["answer_trace"]["route"] == "sql_only"


def test_top_customers_matches_direct_sql_and_persists_trace(db_conn, tmp_path):
    response = answer_top_customers()

    assert len(response.answer) == 10
    revenues = [customer.net_revenue for customer in response.answer]
    assert revenues == sorted(revenues, reverse=True)
    assert all(revenue > 0 for revenue in revenues)
    assert response.answer_trace.route == QueryRoute.SQL_ONLY
    assert response.answer_trace.validation_results[0].allowed is True
    assert response.answer_trace.provenance

    with db_conn.cursor() as cur:
        cur.execute(build_top_customers_sql())
        expected = [(row[0], Decimal(str(row[1]))) for row in cur.fetchall()]
    actual = [(row.customer_id, row.net_revenue) for row in response.answer]

    assert actual == expected

    trace_path = persist_answer_trace(
        response.answer_trace,
        tmp_path / "step01_top_customers.json",
    )
    assert trace_path.exists()


def test_net_revenue_parity_with_independent_sql(db_conn):
    response = answer_top_customers()
    first_customer = response.answer[0]

    with db_conn.cursor() as cur:
        cur.execute(
            """
            select round(sum(line_revenue)::numeric, 6)
            from (
                select od.unit_price * od.quantity * (1 - od.discount) as line_revenue
                from erp_core.orders o
                join erp_core.order_details od on od.order_id = o.order_id
                where o.customer_id = %s
                  and o.order_date between date '2025-01-01' and date '2025-12-31'
            ) lines
            """,
            (first_customer.customer_id,),
        )
        expected = Decimal(str(cur.fetchone()[0]))

    assert first_customer.net_revenue.quantize(Decimal("0.000001")) == expected

