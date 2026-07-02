from __future__ import annotations

import time
from typing import Any

import psycopg
from pydantic import BaseModel, Field

from backend.config import Settings, get_settings
from backend.query.validation import ValidationResult

DEFAULT_TIMEOUT_MS = 5000


class QueryMetrics(BaseModel):
    row_count: int
    duration_ms: float


class QueryExecutionResult(BaseModel):
    columns: list[str] = Field(default_factory=list)
    rows: list[dict[str, Any]] = Field(default_factory=list)
    metrics: QueryMetrics


def run_validated_sql(
    validation_result: ValidationResult,
    params: dict[str, Any] | None = None,
    settings: Settings | None = None,
    timeout_ms: int = DEFAULT_TIMEOUT_MS,
) -> QueryExecutionResult:
    if not validation_result.allowed or not validation_result.effective_query:
        raise ValueError("refusing to execute SQL that failed validation")

    settings = settings or get_settings()
    with psycopg.connect(settings.postgres_dsn) as conn:
        conn.read_only = True
        with conn.cursor() as cur:
            cur.execute("begin")
            cur.execute("set transaction read only")
            cur.execute(f"set local statement_timeout = {int(timeout_ms)}")
            start = time.perf_counter()
            cur.execute(validation_result.effective_query, params or None)
            column_names = [desc.name for desc in cur.description or []]
            tuple_rows = cur.fetchall()
            duration_ms = round((time.perf_counter() - start) * 1000, 2)
        conn.rollback()

    rows = [dict(zip(column_names, row, strict=True)) for row in tuple_rows]
    return QueryExecutionResult(
        columns=column_names,
        rows=rows,
        metrics=QueryMetrics(row_count=len(rows), duration_ms=duration_ms),
    )
