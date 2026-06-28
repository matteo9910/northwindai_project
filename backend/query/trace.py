from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Any

from pydantic import BaseModel, Field

from backend.graph.cypher_validator import CypherValidationResult
from backend.query.executor import QueryMetrics
from backend.query.validator import SqlValidationResult
from backend.vector.validation import VectorValidationResult

ValidationResultUnion = Annotated[
    SqlValidationResult | CypherValidationResult | VectorValidationResult,
    Field(discriminator="dialect"),
]


class QueryRoute(StrEnum):
    SQL_ONLY = "sql_only"
    GRAPH_ONLY = "graph_only"
    VECTOR_ONLY = "vector_only"
    GRAPH_PLUS_SQL = "graph_plus_sql"
    GRAPH_PLUS_VECTOR = "graph_plus_vector"
    SQL_PLUS_GRAPH_PLUS_VECTOR = "sql_plus_graph_plus_vector"


class ProvenanceEntry(BaseModel):
    source_system: str
    source_schema: str
    source_table: str
    source_columns: list[str] = Field(default_factory=list)
    rule_name: str
    rule_version: str


class AnswerTrace(BaseModel):
    route: QueryRoute
    generated_sql: str | None = None
    generated_cypher: str | None = None
    graph_paths: list[dict[str, Any]] = Field(default_factory=list)
    retrieved_chunks: list[dict[str, Any]] = Field(default_factory=list)
    documents_used: list[dict[str, Any]] = Field(default_factory=list)
    metrics: dict[str, QueryMetrics] = Field(default_factory=dict)
    validation_results: list[ValidationResultUnion] = Field(default_factory=list)
    provenance: list[ProvenanceEntry] = Field(default_factory=list)

