from __future__ import annotations

import psycopg
import pytest

from backend.config import get_settings
from data_generation.scenarios import TOP_CUSTOMERS_SQL


@pytest.fixture(scope="module")
def db_conn():
    settings = get_settings()
    if (
        "__set_me__" in settings.postgres_dsn
        or "<project-ref>" in settings.postgres_dsn
    ):
        pytest.skip("Postgres DSN is not configured for live scenario probes.")
    try:
        with psycopg.connect(settings.postgres_dsn) as conn:
            yield conn
    except psycopg.OperationalError as exc:
        pytest.skip(f"Postgres is not reachable: {exc}")


def top_customer_ids(cur) -> set[str]:
    cur.execute(TOP_CUSTOMERS_SQL)
    return {row[0] for row in cur.fetchall()}


def test_scenario_a_tokyo_traders_delays_for_top_customers(db_conn):
    with db_conn.cursor() as cur:
        top_customers = top_customer_ids(cur)
        cur.execute(
            """
            select avg(s.delay_days), count(distinct cc.communication_id)
            from erp_core.orders o
            join erp_core.order_details od on od.order_id = o.order_id
            join erp_core.products p on p.product_id = od.product_id
            join erp_core.shipments s on s.order_id = o.order_id
            left join erp_docs.customer_communications cc
              on cc.order_id = o.order_id
             and cc.contact_reason = 'complaint'
             and lower(cc.body) similar to '%%(delay|late)%%'
            where p.supplier_id = 4
              and o.customer_id = any(%s)
              and o.order_date between date '2025-10-01' and date '2025-12-31'
            """,
            (list(top_customers),),
        )
        avg_delay, complaint_count = cur.fetchone()

    assert avg_delay is not None
    assert float(avg_delay) > 0
    assert complaint_count >= 1


def test_scenario_b_exotic_liquids_delays_are_non_top_customer(db_conn):
    with db_conn.cursor() as cur:
        top_customers = top_customer_ids(cur)
        cur.execute(
            """
            select count(*)
            from erp_core.orders o
            join erp_core.order_details od on od.order_id = o.order_id
            join erp_core.products p on p.product_id = od.product_id
            join erp_core.shipments s on s.order_id = o.order_id
            where p.supplier_id = 1
              and s.delay_days > 0
              and not (o.customer_id = any(%s))
            """,
            (list(top_customers),),
        )
        delayed_count = cur.fetchone()[0]

    assert delayed_count >= 1


def test_scenario_c_pavlova_has_non_delay_complaints_without_delays(db_conn):
    with db_conn.cursor() as cur:
        top_customers = top_customer_ids(cur)
        cur.execute(
            """
            select coalesce(max(s.delay_days), 0), count(distinct cc.communication_id)
            from erp_core.orders o
            join erp_core.order_details od on od.order_id = o.order_id
            join erp_core.products p on p.product_id = od.product_id
            join erp_core.shipments s on s.order_id = o.order_id
            left join erp_docs.customer_communications cc
              on cc.order_id = o.order_id
             and cc.contact_reason = 'complaint'
             and lower(cc.body) not similar to '%%(delay|late)%%'
            where p.supplier_id = 7
              and o.customer_id = any(%s)
            """,
            (list(top_customers),),
        )
        max_delay, complaint_count = cur.fetchone()

    assert max_delay <= 0
    assert complaint_count >= 1


def test_scenario_d_grandma_has_worse_terms_and_fewer_complaints(db_conn):
    with db_conn.cursor() as cur:
        cur.execute(
            """
            select
                (select lead_time_days
                 from erp_docs.supplier_contracts
                 where supplier_id = 3),
                (select lead_time_days
                 from erp_docs.supplier_contracts
                 where supplier_id = 4),
                (select count(*)
                 from erp_docs.customer_communications cc
                 join erp_core.order_details od on od.order_id = cc.order_id
                 join erp_core.products p on p.product_id = od.product_id
                 where p.supplier_id = 3 and cc.contact_reason = 'complaint'),
                (select count(*)
                 from erp_docs.customer_communications cc
                 join erp_core.order_details od on od.order_id = cc.order_id
                 join erp_core.products p on p.product_id = od.product_id
                 where p.supplier_id = 4 and cc.contact_reason = 'complaint')
            """
        )
        grandma_lead, tokyo_lead, grandma_complaints, tokyo_complaints = cur.fetchone()

    assert grandma_lead > tokyo_lead
    assert grandma_complaints < tokyo_complaints
