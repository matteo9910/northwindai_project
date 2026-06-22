from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass

import pytest
from neo4j.exceptions import CypherSyntaxError

from backend.graph.cypher_executor import (
    CypherExecutionError,
    run_validated_cypher,
)
from backend.query.validator import ValidationResult


@dataclass
class FakeSettings:
    neo4j_uri: str = "bolt://fake"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "password"


class FakeRecord:
    def __init__(self, data):
        self._data = data

    def data(self):
        return self._data


class FakeResult:
    def __init__(self, records=None):
        self.records = records or []

    def consume(self):
        return None

    def __iter__(self):
        return iter(self.records)


class FakeSession:
    def __init__(self, fail_explain=False):
        self.fail_explain = fail_explain
        self.queries = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def run(self, query, params=None):
        text = getattr(query, "text", str(query))
        self.queries.append((text, params))
        if text.startswith("EXPLAIN") and self.fail_explain:
            raise CypherSyntaxError("bad syntax")
        if text.startswith("EXPLAIN"):
            return FakeResult()
        return FakeResult(
            [
                FakeRecord(
                    {
                        "supplier_id": 4,
                        "supplier_name": "Tokyo Traders",
                        "supplier_properties": {
                            "source_table": "suppliers",
                            "source_pk": 4,
                            "rule_name": "supplier_projection",
                            "rule_version": "v1",
                        },
                        "relationship_type": "SUPPLIES",
                        "relationship_properties": {
                            "source_table": "products",
                            "source_pk": 9,
                            "source_column": "supplier_id",
                            "rule_name": "supplier_to_product_projection",
                            "rule_version": "v1",
                        },
                        "product_id": 9,
                        "product_name": "Mishi Kobe Niku",
                        "product_properties": {
                            "source_table": "products",
                            "source_pk": 9,
                            "rule_name": "product_projection",
                            "rule_version": "v1",
                        },
                    }
                )
            ]
        )


class FakeDriver:
    def __init__(self, session):
        self.session_instance = session

    def session(self, default_access_mode=None):
        self.default_access_mode = default_access_mode
        return self.session_instance


def test_cypher_executor_refuses_failed_validation():
    validation = ValidationResult(
        allowed=False,
        violations=["blocked_keyword:create"],
        effective_sql=None,
    )

    with pytest.raises(ValueError, match="failed validation"):
        run_validated_cypher(validation, settings=FakeSettings())


def test_cypher_executor_runs_explain_then_read_query(monkeypatch):
    session = FakeSession()

    @contextmanager
    def fake_driver(_settings):
        yield FakeDriver(session)

    monkeypatch.setattr("backend.graph.cypher_executor.neo4j_driver", fake_driver)
    validation = ValidationResult(
        allowed=True,
        effective_sql="MATCH (:Supplier)-[:SUPPLIES]->(p:Product) RETURN p LIMIT 1",
    )

    result = run_validated_cypher(
        validation,
        params={"company_name": "Tokyo Traders"},
        settings=FakeSettings(),
    )

    assert session.queries[0][0].startswith("EXPLAIN")
    assert result.metrics.row_count == 1
    assert result.records[0]["product_id"] == 9
    assert result.graph_paths[0]["relationship"]["source_column"] == "supplier_id"


def test_cypher_executor_wraps_explain_failure(monkeypatch):
    session = FakeSession(fail_explain=True)

    @contextmanager
    def fake_driver(_settings):
        yield FakeDriver(session)

    monkeypatch.setattr("backend.graph.cypher_executor.neo4j_driver", fake_driver)
    validation = ValidationResult(
        allowed=True,
        effective_sql="MATCH bad",
    )

    with pytest.raises(CypherExecutionError, match="explain_failed"):
        run_validated_cypher(validation, settings=FakeSettings())

