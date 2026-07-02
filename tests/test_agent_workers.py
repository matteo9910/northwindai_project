from __future__ import annotations

from typing import Any

from langchain_core.runnables import RunnableLambda

from backend.agent.types import StoreTarget, WorkerResult, WorkerStatus
from backend.agent.workers.cypher_worker import CypherWorker
from backend.agent.workers.sql_worker import SqlWorker
from backend.agent.workers.vector_worker import VectorWorker
from backend.config import Settings
from backend.graph.cypher_executor import GraphExecutionResult
from backend.graph.cypher_validator import CypherValidationResult
from backend.query.executor import QueryExecutionResult, QueryMetrics
from backend.query.validator import SqlValidationResult
from backend.vector.retriever import VectorSearchResult
from backend.vector.validation import VectorValidationResult


class FakeChatModel:
    def __init__(self, responses: list[dict[str, Any]]):
        self.responses = responses
        self.calls: list[str] = []

    def with_structured_output(self, schema, **kwargs):
        def invoke(prompt_value):
            self.calls.append(str(prompt_value))
            return schema.model_validate(self.responses.pop(0))

        return RunnableLambda(invoke)


def test_sql_worker_repairs_generated_mutation_and_executes():
    chat_model = FakeChatModel(
        [
            {"query": "update erp_core.orders set customer_id = customer_id"},
            {"query": "select order_id from erp_core.orders limit 1"},
        ]
    )

    def execute(
        validation: SqlValidationResult,
        params: dict[str, Any] | None,
        settings: Settings | None,
    ):
        assert validation.allowed
        return QueryExecutionResult(
            columns=["order_id"],
            rows=[{"order_id": 1}],
            metrics=QueryMetrics(row_count=1, duration_ms=1.0),
        )

    result = SqlWorker(chat_model, executor=execute).run("sql_1", "List one order")

    assert result.status == WorkerStatus.SUCCESS
    assert result.target_store == StoreTarget.SQL
    assert result.rows == [{"order_id": 1}]
    assert len(result.attempts) == 2
    assert "blocked_statement:update" in result.attempts[0].validation.violations
    assert "Violations" in chat_model.calls[1]


def test_sql_worker_returns_structured_failure_at_repair_cap():
    chat_model = FakeChatModel([{"query": "delete from erp_core.orders"}] * 3)
    settings = Settings(max_repair_attempts=2)

    result = SqlWorker(chat_model, settings=settings).run("sql_1", "Delete orders")

    assert result.status == WorkerStatus.FAILURE
    assert result.failure_reason == "sql_generation_failed_within_repair_cap"
    assert len(result.attempts) == 3


def test_sql_worker_fails_fast_on_infrastructure_error():
    from psycopg import OperationalError

    chat_model = FakeChatModel(
        [{"query": "select order_id from erp_core.orders limit 1"}]
    )

    def execute(
        validation: SqlValidationResult,
        params: dict[str, Any] | None,
        settings: Settings | None,
    ):
        raise OperationalError("connection refused")

    result = SqlWorker(chat_model, executor=execute).run("sql_1", "List one order")

    assert result.status == WorkerStatus.FAILURE
    assert result.failure_reason == "sql_execution_infrastructure_error"
    assert len(result.attempts) == 1
    assert len(chat_model.calls) == 1  # no wasted regeneration on infra failure


def test_cypher_worker_fails_fast_on_infrastructure_error():
    from neo4j.exceptions import ServiceUnavailable

    chat_model = FakeChatModel(
        [{"query": "MATCH (s:Supplier) RETURN s.supplier_id AS supplier_id"}]
    )

    def execute(
        validation: CypherValidationResult,
        params: dict[str, Any] | None,
        settings: Settings | None,
    ):
        raise ServiceUnavailable("could not connect to neo4j")

    result = CypherWorker(chat_model, executor=execute).run(
        "cypher_1",
        "List suppliers",
    )

    assert result.status == WorkerStatus.FAILURE
    assert result.failure_reason == "cypher_execution_infrastructure_error"
    assert len(result.attempts) == 1
    assert len(chat_model.calls) == 1  # no wasted regeneration on infra failure


def test_cypher_worker_repairs_disallowed_label_and_executes():
    chat_model = FakeChatModel(
        [
            {"query": "MATCH (n:Secret) RETURN n"},
            {"query": "MATCH (s:Supplier) RETURN s.supplier_id AS supplier_id"},
        ]
    )

    def execute(
        validation: CypherValidationResult,
        params: dict[str, Any] | None,
        settings: Settings | None,
    ):
        assert validation.allowed
        return GraphExecutionResult(
            records=[{"supplier_id": 4}],
            graph_paths=[],
            metrics=QueryMetrics(row_count=1, duration_ms=1.0),
        )

    result = CypherWorker(chat_model, executor=execute).run(
        "cypher_1",
        "List suppliers",
    )

    assert result.status == WorkerStatus.SUCCESS
    assert len(result.attempts) == 2
    assert "label_not_allowed:Secret" in result.attempts[0].validation.violations
    assert result.rows == [{"supplier_id": 4}]


def test_vector_worker_refuses_unscoped_search():
    result = VectorWorker(settings=Settings()).run(
        "vector_1",
        "Find lead time",
        prior_results=[],
    )

    assert result.status == WorkerStatus.FAILURE
    assert result.validation_results[0].allowed is False
    assert "metadata_filter_required" in result.validation_results[0].violations


def test_vector_worker_uses_graph_resolved_filters():
    graph_result = WorkerResult(
        task_id="graph_1",
        target_store=StoreTarget.CYPHER,
        status=WorkerStatus.SUCCESS,
        sub_question="Resolve contract document",
        rows=[{"supplier_id": 4, "document_id": 3}],
    )

    def search(query_text, collection_name, filters, embeddings, client, top_k):
        assert filters == {"supplier_id": 4, "document_id": 3}
        return VectorSearchResult(
            chunks=[
                {
                    "chunk_id": "c1",
                    "text": "lead time is fourteen business days",
                    "supplier_id": 4,
                    "document_id": 3,
                }
            ],
            metrics=QueryMetrics(row_count=1, duration_ms=1.0),
            validation=VectorValidationResult(
                allowed=True,
                collection_name=collection_name,
                top_k=top_k,
                filters=filters,
            ),
        )

    result = VectorWorker(
        settings=Settings(),
        embeddings=object(),
        client=object(),
        search=search,
    ).run("vector_1", "Find lead time", [graph_result])

    assert result.status == WorkerStatus.SUCCESS
    assert result.chunks[0]["chunk_id"] == "c1"
    assert result.documents_used[0]["document_id"] == 3
