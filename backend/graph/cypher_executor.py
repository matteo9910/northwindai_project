from __future__ import annotations

import time
from typing import Any

import neo4j
from neo4j import Query
from neo4j.exceptions import Neo4jError
from pydantic import BaseModel, Field

from backend.config import Settings
from backend.graph.connection import neo4j_driver
from backend.query.executor import DEFAULT_TIMEOUT_MS, QueryMetrics
from backend.query.validation import ValidationResult


class CypherExecutionError(RuntimeError):
    """Controlled failure from the governed Cypher execution path."""


class GraphExecutionResult(BaseModel):
    records: list[dict[str, Any]] = Field(default_factory=list)
    graph_paths: list[dict[str, Any]] = Field(default_factory=list)
    metrics: QueryMetrics


def run_validated_cypher(
    validation_result: ValidationResult,
    params: dict[str, Any] | None = None,
    settings: Settings | None = None,
    timeout_ms: int = DEFAULT_TIMEOUT_MS,
) -> GraphExecutionResult:
    if not validation_result.allowed or not validation_result.effective_query:
        raise ValueError("refusing to execute Cypher that failed validation")

    params = params or {}
    cypher = validation_result.effective_query
    timeout_seconds = timeout_ms / 1000

    try:
        with neo4j_driver(settings) as driver:
            with driver.session(default_access_mode=neo4j.READ_ACCESS) as session:
                session.run(
                    Query(f"EXPLAIN {cypher}", timeout=timeout_seconds),
                    params,
                ).consume()
                start = time.perf_counter()
                result = session.run(Query(cypher, timeout=timeout_seconds), params)
                records = [_json_ready(record.data()) for record in result]
                duration_ms = round((time.perf_counter() - start) * 1000, 2)
    except Neo4jError as exc:
        raise CypherExecutionError(f"explain_failed:{exc}") from exc

    return GraphExecutionResult(
        records=records,
        graph_paths=[_graph_path_from_record(record) for record in records],
        metrics=QueryMetrics(row_count=len(records), duration_ms=duration_ms),
    )


def _json_ready(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_ready(item) for item in value]
    return value


def _graph_path_from_record(record: dict[str, Any]) -> dict[str, Any]:
    supplier_properties = record.get("supplier_properties") or {}
    relationship_properties = record.get("relationship_properties") or {}
    product_properties = record.get("product_properties") or {}
    return {
        "supplier": {
            "supplier_id": record.get("supplier_id"),
            "company_name": record.get("supplier_name"),
            **_essential_provenance(supplier_properties),
        },
        "relationship": {
            "type": record.get("relationship_type"),
            **_essential_provenance(relationship_properties),
            "source_column": relationship_properties.get("source_column"),
        },
        "product": {
            "product_id": record.get("product_id"),
            "product_name": record.get("product_name"),
            **_essential_provenance(product_properties),
        },
    }


def _essential_provenance(properties: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "source_system",
        "source_schema",
        "source_table",
        "source_pk",
        "projection_version",
        "rule_name",
        "rule_version",
    )
    return {key: properties.get(key) for key in keys if key in properties}

