from __future__ import annotations

from dataclasses import dataclass

from backend.graph import projection


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


def test_derivers_create_events_and_plausible_link_params(monkeypatch):
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
                "subject": "Late delivery",
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
        "backend.graph.projection._fetch_rows_with_params",
        lambda _settings, _sql, params: [
            {"shipment_id": 501, "communication_id": 701}
        ],
    )
    driver = FakeDriver()

    assert projection.derive_shipment_delay_events(driver, FakeSettings()) == 1
    assert projection.derive_customer_complaint_events(driver, FakeSettings()) == 1
    assert projection.derive_plausible_delay_complaint_links(
        driver,
        FakeSettings(),
    ) == 1

    params = [run[1] for run in driver.session_instance.runs]
    assert params[0]["rule_name"] == "shipment_delay_event"
    assert params[1]["rule_name"] == "customer_complaint_event"
    assert params[-1]["rule_name"] == "delay_complaint_possibly_related"
    assert params[-1]["rows"][0]["time_window_days"] == 14
    assert params[-1]["rows"][0]["source_pk"] == "501:701"


def test_reset_projection_is_scoped():
    driver = FakeDriver()

    projection.reset_projection(driver)

    queries = [query for query, _params in driver.session_instance.runs]
    assert projection.RESET_POSSIBLY_RELATED in queries
    assert projection.RESET_SUPPLIES in queries
    assert projection.RESET_SUPPLIERS == queries[-1]
    assert all("DETACH DELETE" not in query for query in queries)
    assert all("MATCH (n)" not in query for query in queries)

