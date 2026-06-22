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
    assert params[1]["supplier_id"] == 4
    assert params[2]["rule_name"] == "supplier_to_product_projection"
    assert params[2]["product_id"] == 9


def test_reset_phase05_projection_is_scoped():
    driver = FakeDriver()

    projection.reset_phase05_projection(driver)

    queries = [query for query, _params in driver.session_instance.runs]
    assert queries == [
        projection.RESET_SUPPLIES,
        projection.RESET_PRODUCTS,
        projection.RESET_SUPPLIERS,
    ]
    assert all("DETACH DELETE" not in query for query in queries)
    assert all("MATCH (n)" not in query for query in queries)

