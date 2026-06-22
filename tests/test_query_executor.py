from __future__ import annotations

from dataclasses import dataclass

import pytest

from backend.query.executor import run_validated_sql
from backend.query.validator import ValidationResult


@dataclass
class FakeSettings:
    postgres_dsn: str = "host=fake dbname=fake"


class FakeCursor:
    description = [type("Column", (), {"name": "customer_id"})()]

    def __init__(self) -> None:
        self.executed: list[tuple] = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def execute(self, sql, params=None):
        self.executed.append((sql, params))

    def fetchall(self):
        return [("SAVEA",)]


class FakeConnection:
    def __init__(self) -> None:
        self.read_only = False
        self.cursor_instance = FakeCursor()
        self.rolled_back = False

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def cursor(self):
        return self.cursor_instance

    def rollback(self):
        self.rolled_back = True


def test_executor_refuses_failed_validation():
    validation = ValidationResult(
        allowed=False,
        violations=["not_read_only"],
        effective_sql=None,
    )

    with pytest.raises(ValueError, match="failed validation"):
        run_validated_sql(validation, settings=FakeSettings())


def test_executor_uses_read_only_transaction(monkeypatch):
    connection = FakeConnection()
    monkeypatch.setattr(
        "backend.query.executor.psycopg.connect",
        lambda _dsn: connection,
    )
    validation = ValidationResult(
        allowed=True,
        effective_sql="select customer_id from erp_core.customers limit 1",
    )

    result = run_validated_sql(validation, settings=FakeSettings(), timeout_ms=1234)

    assert connection.read_only is True
    assert connection.rolled_back is True
    assert ("begin", None) in connection.cursor_instance.executed
    assert ("set transaction read only", None) in connection.cursor_instance.executed
    assert ("set local statement_timeout = 1234", None) in (
        connection.cursor_instance.executed
    )
    assert result.metrics.row_count == 1
    assert result.rows == [{"customer_id": "SAVEA"}]
